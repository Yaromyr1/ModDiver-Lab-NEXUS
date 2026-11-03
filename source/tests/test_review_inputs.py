"""Ensure review downloads fail closed on changed bytes and unsafe destinations."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import restore_build_inputs as inputs


class ReviewInputTests(unittest.TestCase):
    def test_rejects_paths_outside_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('../outside', '/outside', 'C:/outside', 'source/../../outside', 'source\\outside'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    inputs.safe_target(Path(directory), name)

    def test_modified_cached_asset_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            spec = dict(url='https://example.invalid/input', size=4, sha256=hashlib.sha256(b'good').hexdigest())
            (cache / ('test-' + spec['sha256'])).write_bytes(b'evil')
            with patch.object(inputs.urllib.request, 'urlopen') as request, self.assertRaises(ValueError):
                inputs.fetch_asset('test', spec, cache)
            request.assert_not_called()

    def test_wrong_member_is_rejected_before_replacing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root/'source/input.bin'
            target.parent.mkdir()
            target.write_bytes(b'preserve')
            manifest = dict(assets={'raw': {}}, files=[dict(path='source/input.bin',asset='raw',member=None,size=4,sha256=hashlib.sha256(b'good').hexdigest())])
            with patch.object(inputs, 'fetch_asset', return_value=b'evil'), self.assertRaises(ValueError):
                inputs.restore(root, manifest, root/'cache')
            self.assertEqual(target.read_bytes(), b'preserve')

    def test_verify_only_never_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = dict(assets={},files=[dict(path='source/input.bin',size=4,sha256=hashlib.sha256(b'good').hexdigest())])
            with patch.object(inputs, 'fetch_asset') as fetch, self.assertRaises(ValueError):
                inputs.restore(root, manifest, root/'cache', verify_only=True)
            fetch.assert_not_called()

    def test_successful_restore_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = dict(assets={'raw': {}},files=[dict(path='source/input.bin',asset='raw',member=None,size=4,sha256=hashlib.sha256(b'good').hexdigest())])
            with patch.object(inputs, 'fetch_asset', return_value=b'good') as fetch:
                inputs.restore(root, manifest, root/'cache')
                inputs.restore(root, manifest, root/'cache')
                self.assertEqual(fetch.call_count, 1)
            self.assertEqual((root/'source/input.bin').read_bytes(), b'good')
