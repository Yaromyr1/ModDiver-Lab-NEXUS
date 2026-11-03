import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import core
import library_io
import localization

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import build_release


class LibraryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.managed = self.root / 'managed'
        self.patch = patch.object(core, 'IMPORTED_MODS_DIR', self.managed)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.save = patch.object(core, 'save_config')
        self.save.start()
        self.addCleanup(self.save.stop)

    def mod(self, name):
        path = self.root / name
        path.mkdir()
        (path / 'manifest.json').write_text(json.dumps({'Name': name, 'Version': 1,
                                                      'Options': [{'Name': 'Extra', 'Include': ['extra']}]}), encoding='utf-8')
        data = path / 'data' / 'game'
        data.mkdir(parents=True)
        (data / 'test.dl_bin').write_bytes(b'mod data')
        return path

    def test_export_import_round_trip_with_folder_and_zip(self):
        folder = self.mod('Folder mod')
        zipped = self.root / 'archive.zip'
        with zipfile.ZipFile(zipped, 'w') as z:
            z.writestr('manifest.json', json.dumps({'Name': 'ZIP mod', 'Version': 1}))
            z.writestr('data/game/other.dl_bin', b'zip data')
        cfg = {'mods': [{'path': str(folder), 'name': 'Русский мод', 'enabled': False, 'category': 'visual', 'selected': {'Extra': False}},
                        {'path': str(zipped), 'name': 'Second', 'enabled': True}]}
        backup = self.root / 'backup.zip'
        original = copy.deepcopy(cfg)
        library_io.export_library(cfg, backup, lambda _: None)
        self.assertEqual(cfg, original)
        # Sources need not exist on the receiving computer.
        import shutil
        shutil.rmtree(folder)
        zipped.unlink()
        restored = {'mods': []}
        library_io.import_library(restored, backup, lambda _: None)
        self.assertEqual([m['name'] for m in restored['mods']], ['Русский мод', 'Second'])
        self.assertFalse(restored['mods'][0]['enabled'])
        self.assertEqual(restored['mods'][0]['category'], 'visual')
        self.assertEqual(restored['mods'][0]['selected'], {'Extra': False})
        with zipfile.ZipFile(restored['mods'][0]['path']) as z:
            self.assertEqual(z.read('data/game/test.dl_bin'), b'mod data')
        self.assertTrue(all(Path(m['path']).is_file() for m in restored['mods']))
        # A second export can be imported again with no manual preparation.
        library_io.export_library(restored, self.root / 'second.zip', lambda _: None)
        library_io.import_library(restored, self.root / 'second.zip', lambda _: None)
        self.assertEqual(len(restored['mods']), 4)

    def test_plain_folder_and_zip_of_zips(self):
        folder = self.root / 'collection'
        folder.mkdir()
        for name in ('a.zip', 'b.zip'):
            with zipfile.ZipFile(folder / name, 'w') as z:
                z.writestr('data/game/test.dl_bin', b'test')
        library = self.root / 'collection.zip'
        with zipfile.ZipFile(library, 'w') as z:
            for file in folder.iterdir():
                z.write(file, 'wrapper/' + file.name)
        for source in (folder, library):
            cfg = {'mods': [{'name': 'Existing'}]}
            library_io.import_library(cfg, source, lambda _: None)
            self.assertEqual(len(cfg['mods']), 3)
            self.assertEqual(cfg['mods'][0]['name'], 'Existing')

    def test_invalid_package_rolls_back_all_additions(self):
        folder = self.root / 'collection'
        folder.mkdir()
        with zipfile.ZipFile(folder / 'a.zip', 'w') as z:
            z.writestr('data/game/test.dl_bin', b'test')
        (folder / 'b.zip').write_bytes(b'bad zip')
        cfg = {'mods': [{'name': 'Existing'}]}
        with self.assertRaises(ValueError):
            library_io.import_library(cfg, folder, lambda _: None)
        self.assertEqual(cfg['mods'], [{'name': 'Existing'}])
        self.assertEqual(list(self.managed.iterdir()), [])

    def test_unsafe_outer_zip_is_rejected(self):
        archive = self.root / 'unsafe.zip'
        for name in ('../escape.zip', 'C:/escape.zip', '/escape.zip'):
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr(name, b'bad')
            with self.assertRaises(ValueError):
                library_io.import_library({'mods': []}, archive, lambda _: None)
        self.assertFalse((self.root / 'escape.zip').exists())

    def test_russian_has_same_ui_coverage_as_chinese(self):
        self.assertFalse(set(localization.ZH) - set(localization.RU))
        localization.set_language('ru')
        self.addCleanup(localization.set_language, 'en')
        self.assertEqual(localization.tr('Import Library'), 'Импорт библиотеки')
        self.assertEqual(localization.tr('12 mods'), '12 модов')

    def test_publish_removes_stale_releases_and_loose_checksums(self):
        output = self.root / 'dist'
        output.mkdir()
        (output / 'ModDiver-Laboratory-app-1.8.0.zip').touch()
        (output / 'SHA256SUMS.txt').touch()
        staging = self.root / 'stage'
        staging.mkdir()
        packages = []
        for name in ('ModDiver-Laboratory-app-2.2.0.zip', build_release.FULL_ZIP_NAME, build_release.LINUX_ZIP_NAME):
            package = staging / name
            package.write_bytes(b'current release')
            packages.append(package)
        build_release.publish_release(packages, output)
        self.assertEqual({p.name for p in output.iterdir()}, {p.name for p in packages})


if __name__ == '__main__':
    unittest.main()
