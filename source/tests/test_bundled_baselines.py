import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import build_archive as store
import core


class BundledBaselineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        mock = patch.object(core, 'APP_DATA', self.root / 'appdata')
        mock.start()
        self.addCleanup(mock.stop)

    def package(self, files):
        package = self.root / 'repair-baseline-100.zip'
        metadata = dict(format='moddiver-repair-baseline-1', build_id='100',
                        scope='data-only', files={})
        with zipfile.ZipFile(package, 'w') as archive:
            for name, plain in files.items():
                archive.writestr(name, plain)
                metadata['files'][name] = dict(sha256=hashlib.sha256(plain).hexdigest(), sealed=True)
            archive.writestr('baseline.json', json.dumps(metadata))
        return package

    def test_expanded_bundle_replaces_partial_registration_and_keeps_history(self):
        files = {'game/generated_first.dl_bin': b'first'}
        old = store.install_bundled_baseline(self.package(files), '100')
        files['game/generated_second.dl_bin'] = b'second'
        package = self.package(files)
        new = store.install_bundled_baseline(package, '100')
        self.assertNotEqual(old, new)
        self.assertTrue(old.is_dir())
        for name, plain in files.items():
            self.assertEqual(core.unseal((new / 'data' / name).read_bytes()), plain)
        self.assertEqual(store.install_bundled_baseline(package, '100'), new)
        self.assertEqual(len(store.builds()), 2)

    def test_corrupt_cached_file_is_recovered(self):
        name = 'game/generated_first.dl_bin'
        package = self.package({name: b'first'})
        old = store.install_bundled_baseline(package, '100')
        (old / 'data' / name).write_bytes(b'corrupt')
        new = store.install_bundled_baseline(package, '100')
        self.assertNotEqual(old, new)
        self.assertEqual(core.unseal((new / 'data' / name).read_bytes()), b'first')

    def test_empty_table_is_retained_without_requiring_ldld_blocks(self):
        name = 'game/generated_resource_swap.dl_bin'
        plain = bytes(24)
        folder = store.install_bundled_baseline(self.package({name: plain}), '100')
        self.assertEqual(core.unseal((folder / 'data' / name).read_bytes()), plain)
        metadata = json.loads((folder / 'build.json').read_text())
        self.assertEqual(metadata['scope'], 'data-only')
        self.assertEqual(set(metadata['files']), {name})

    def test_invalid_bundle_never_publishes_partial_history(self):
        package = self.package({'game/generated_first.dl_bin': b'first', '../escape': b'bad'})
        with self.assertRaisesRegex(ValueError, 'path'):
            store.install_bundled_baseline(package, '100')
        self.assertEqual(store.builds(), [])

    def test_shipped_old_build_covers_every_supplied_table(self):
        package = Path(store.__file__).parent / 'builtin/gameplay/repair-baseline-26088801.zip'
        with zipfile.ZipFile(package) as archive:
            metadata = json.loads(archive.read('baseline.json'))
            self.assertEqual(len(metadata['files']), 55)
            self.assertEqual(metadata['scope'], 'data-only')
            for name, info in metadata['files'].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), info['sha256'])
            self.assertIn('game/generated_resource_swap.dl_bin', metadata['files'])


if __name__ == '__main__':
    unittest.main()
