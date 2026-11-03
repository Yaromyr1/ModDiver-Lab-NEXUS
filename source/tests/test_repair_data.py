import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import repair_data


class Response(io.BytesIO):
    headers = {}


class RepairDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = self.root / 'bundled'
        self.bundle.mkdir()
        self.cache = self.root / 'persistent-cache'
        self.name = 'repair-baseline-123.zip'
        self.payload = b'fixture repair package'
        self.entry = {'size': len(self.payload), 'sha256': hashlib.sha256(self.payload).hexdigest()}
        self.write_manifest()

    def write_manifest(self, name=None):
        (self.bundle / 'repair-data.json').write_text(json.dumps({
            'format': 1, 'tag': 'repair-data-v1', 'packages': {name or self.name: self.entry}}))

    def test_startup_never_downloads(self):
        with patch.object(repair_data.urllib.request, 'urlopen', side_effect=AssertionError('network')):
            self.assertEqual(repair_data.packages(self.bundle, self.cache), [])
        self.assertFalse(self.cache.exists())

    def test_requested_download_is_pinned_and_reused_offline(self):
        with patch.object(repair_data.urllib.request, 'urlopen', return_value=Response(self.payload)) as call:
            result = repair_data.packages(self.bundle, self.cache, download=True)
        self.assertEqual(call.call_args.args[0].full_url,
                         'https://github.com/Yaromyr1/ModDiver-Lab/releases/download/repair-data-v1/' + self.name)
        self.assertEqual(result[0].read_bytes(), self.payload)
        with patch.object(repair_data.urllib.request, 'urlopen', side_effect=AssertionError('network')):
            self.assertEqual(repair_data.packages(self.bundle, self.cache, download=True), result)

    def test_prefetch_downloads_verified_packages_for_later_repair(self):
        destination = self.root / 'prefetch'
        with patch.object(repair_data.urllib.request, 'urlopen', return_value=Response(self.payload)) as call:
            result = repair_data.prefetch(self.bundle, destination)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result, [destination / self.name])
        self.assertEqual(result[0].read_bytes(), self.payload)
        with patch.object(repair_data.urllib.request, 'urlopen', side_effect=AssertionError('network')):
            self.assertEqual(repair_data.prefetch(self.bundle, destination), result)

    def test_incomplete_corrupt_and_oversized_downloads_are_never_cached(self):
        for payload in (self.payload[:-1], b'x' * len(self.payload), self.payload + b'x'):
            with self.subTest(payload=payload), patch.object(
                    repair_data.urllib.request, 'urlopen', return_value=Response(payload)):
                with self.assertRaisesRegex(ValueError, 'integrity|expected size'):
                    repair_data.packages(self.bundle, self.cache, download=True)
                self.assertEqual(list(self.cache.iterdir()), [])

    def test_corrupt_cache_is_replaced_only_by_verified_download(self):
        self.cache.mkdir()
        target = self.cache / self.name
        target.write_bytes(b'bad cache')
        with patch.object(repair_data.urllib.request, 'urlopen', return_value=Response(self.payload)):
            repair_data.packages(self.bundle, self.cache, download=True)
        self.assertEqual(target.read_bytes(), self.payload)

    def test_offline_error_preserves_existing_data_and_cleans_partial(self):
        self.cache.mkdir()
        sentinel = self.cache / 'other-user-data'
        sentinel.write_bytes(b'keep')
        with patch.object(repair_data.urllib.request, 'urlopen', side_effect=OSError('offline')):
            with self.assertRaisesRegex(ValueError, 'retry'):
                repair_data.packages(self.bundle, self.cache, download=True)
        self.assertEqual(list(self.cache.iterdir()), [sentinel])

    def test_manual_offline_package_is_verified_without_network(self):
        target = self.bundle / self.name
        target.write_bytes(self.payload)
        with patch.object(repair_data.urllib.request, 'urlopen', side_effect=AssertionError('network')):
            self.assertEqual(repair_data.packages(self.bundle, self.cache, download=True), [target])
        target.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            repair_data.packages(self.bundle, self.cache, download=True)

    def test_manifest_rejects_path_traversal_and_oversized_packages(self):
        self.write_manifest('../escape.zip')
        with self.assertRaisesRegex(ValueError, 'manifest'):
            repair_data.packages(self.bundle, self.cache, download=True)

    def test_session_removes_zip_and_extracted_data_after_success_or_failure(self):
        import build_archive
        import core
        buffer = io.BytesIO()
        raw = b'archive witness'
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('0123456789abcdef', raw)
            archive.writestr('baseline.json', json.dumps({
                'format': 'moddiver-repair-baseline-1', 'build_id': '123', 'files': {
                    '0123456789abcdef': {'sealed': False, 'sha256': hashlib.sha256(raw).hexdigest()}}}))
        self.payload = buffer.getvalue()
        self.entry = {'size': len(self.payload), 'sha256': hashlib.sha256(self.payload).hexdigest()}
        self.write_manifest()
        persistent = self.root / 'user-history'
        persistent.mkdir()
        sentinel = persistent / 'keep-user-capture'
        sentinel.write_bytes(b'keep')
        for fail in (False, True):
            with self.subTest(fail=fail), patch.object(core, 'APP_DATA', self.root / 'appdata'), \
                    patch.object(build_archive, 'archive_root', return_value=persistent), \
                    patch.object(repair_data.urllib.request, 'urlopen', side_effect=lambda *a, **k: Response(self.payload)):
                try:
                    with build_archive.baseline_session(folder=self.bundle) as roots:
                        session = roots[1] / 'build-123-bundled'
                        self.assertEqual(len(build_archive.builds(roots)), 1)
                        self.assertTrue((Path(core.APP_DATA) / 'tmp' / 'repair-data-prefetch' / self.name).is_file())
                        if fail:
                            raise RuntimeError('repair failed')
                except RuntimeError:
                    self.assertTrue(fail)
                self.assertFalse(session.exists())
                self.assertEqual(sentinel.read_bytes(), b'keep')
        self.entry['size'] = repair_data.MAX_BYTES + 1
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'manifest'):
            repair_data.packages(self.bundle, self.cache, download=True)


if __name__ == '__main__':
    unittest.main()
