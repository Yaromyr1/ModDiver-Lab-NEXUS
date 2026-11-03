from pathlib import Path
import json
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import core
from dlbin_codec import DLBin
import build_archive as store


class BuildArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.game = self.root / 'steamapps/common/Helldivers 2'
        self.data = self.game / 'data/game'
        self.data.mkdir(parents=True)
        self.archive = self.root / 'Archive'
        self.output = self.root / 'Repaired Mods'
        self.deployed = patch.object(core, 'load_deployed', return_value={})
        self.deployed.start()
        self.addCleanup(self.deployed.stop)
        self.appdata = patch.object(core, 'APP_DATA', self.root / 'appdata')
        self.appdata.start()
        self.addCleanup(self.appdata.stop)
        self.build('100')

    def build(self, number, state='4'):
        (self.game.parent.parent / 'appmanifest_553850.acf').write_text(
            f'"AppState" {{ "appid" "553850" "buildid" "{number}" "StateFlags" "{state}" }}')

    def write(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        header = lambda kind, size: b'LDLD\x01\0\0\0' + struct.pack('<IIQ', kind, size, 1)
        path.write_bytes(core.seal(b'prefix00' + header(123, len(payload)) + payload + header(456, 16) + b'X'*16))

    def fixture(self):
        current = self.data / 'generated_test.dl_bin'
        payload = bytes(range(100))
        self.write(current, payload)
        baseline = store.capture(self.game, self.archive)
        mod = self.root / 'mod' / current.name
        mod.parent.mkdir()
        parsed = DLBin.open(current)
        parsed.replace(0, 0, payload[:40] + b'MOD!' + payload[44:])
        sealed, _ = parsed.prepare()
        mod.write_bytes(sealed)
        self.build('200')
        self.write(current, b'inserted' + payload)
        return current, mod, baseline

    def test_clean_baseline_match_is_read_only_and_mismatch_is_rejected(self):
        current = self.data / 'generated_test.dl_bin'
        self.write(current, bytes(range(100)))
        stock = self.stock_copy(current)
        for i in range(core.REQUIRED_STOCK_FILES - 1):
            extra = self.data / f'generated_extra_{i}.dl_bin'
            self.write(extra, bytes([i % 256]))
            shutil.copy2(extra, stock / extra.name)
        baseline = store.capture_stock_folder(self.game, stock, self.archive)
        self.assertEqual(store.find_matching_clean_baseline(self.game, '100', self.archive), baseline)
        self.write(current, b'X' * 100)
        self.assertIsNone(store.find_matching_clean_baseline(self.game, '100', self.archive))
        self.assertTrue((baseline / 'build.json').is_file())

    def stock_copy(self, current):
        stock = self.root / 'stock'
        stock.mkdir(exist_ok=True)
        shutil.copy2(current, stock / current.name)
        return stock

    def test_unverified_live_capture_never_claims_clean_stock(self):
        current = self.data / 'generated_test.dl_bin'
        self.write(current, bytes(range(100)))
        store.capture(self.game, self.archive)
        self.assertIsNone(store.find_matching_clean_baseline(self.game, '100', self.archive))
        stock = self.stock_copy(current)
        for i in range(core.REQUIRED_STOCK_FILES - 1):
            extra = self.data / f'generated_extra_{i}.dl_bin'
            self.write(extra, bytes([i % 256]))
            shutil.copy2(extra, stock / extra.name)
        verified = store.capture_stock_folder(self.game, stock, self.archive)
        self.assertNotEqual(verified, store.builds(self.archive)[0][0])
        self.assertEqual(len(store.builds(self.archive)), 2)
        self.assertEqual(store.find_matching_clean_baseline(self.game, '100', self.archive), verified)

    def test_verified_recapture_after_reset_keeps_old_build_and_adds_current_hashes(self):
        current = self.data / 'generated_test.dl_bin'
        self.write(current, bytes(range(100)))
        stock = self.stock_copy(current)
        for i in range(core.REQUIRED_STOCK_FILES - 1):
            extra = self.data / f'generated_extra_{i}.dl_bin'
            self.write(extra, bytes([i % 256]))
            shutil.copy2(extra, stock / extra.name)
        old = store.capture_stock_folder(self.game, stock, self.archive)
        self.write(current, b'changed after reset' * 6)
        shutil.copy2(current, stock / current.name)
        newer = store.capture_stock_folder(self.game, stock, self.archive)
        self.assertNotEqual(old, newer)
        self.assertEqual(len(store.builds(self.archive)), 2)
        self.assertEqual(store.find_matching_clean_baseline(self.game, '100', self.archive), newer)

    def test_baseline_match_rejects_new_or_missing_repair_files(self):
        current = self.data / 'generated_test.dl_bin'
        self.write(current, bytes(range(100)))
        stock = self.stock_copy(current)
        for i in range(core.REQUIRED_STOCK_FILES - 1):
            extra = self.data / f'generated_extra_{i}.dl_bin'
            self.write(extra, bytes([i % 256]))
            shutil.copy2(extra, stock / extra.name)
        store.capture_stock_folder(self.game, stock, self.archive)
        extra = self.data / 'generated_extra.dl_bin'
        self.write(extra, b'Y' * 100)
        self.assertIsNone(store.find_matching_clean_baseline(self.game, '100', self.archive))
        extra.unlink()
        current.unlink()
        self.assertIsNone(store.find_matching_clean_baseline(self.game, '100', self.archive))

    def test_retains_builds_and_reuses_same_build(self):
        current, mod, old = self.fixture()
        new = store.capture(self.game, self.archive)
        self.assertEqual(len(store.builds(self.archive)), 2)
        self.assertEqual(store.capture(self.game, self.archive), new)
        self.assertNotEqual(old, new)
        self.assertTrue((old / 'data/game' / current.name).is_file())

    def test_shared_baseline_can_repair_without_local_capture(self):
        current, mod, baseline = self.fixture()
        stock = self.root / 'stock'
        stock.mkdir()
        shutil.copy2(baseline / 'data/game' / current.name, stock / current.name)
        self.build('300')
        archived = store.capture_stock_folder(self.game, stock, self.archive)
        meta = json.loads((archived / 'build.json').read_text())
        self.assertEqual(meta['build_id'], '300')
        self.assertTrue((archived / 'data/game' / current.name).is_file())

    def test_current_stock_archive_rejects_deployed_or_empty_stock(self):
        stock = self.root / 'stock'
        stock.mkdir()
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            store.capture_stock_folder(self.game, stock, self.archive)
        for i in range(core.REQUIRED_STOCK_FILES):
            (stock / f'generated_{i}.dl_bin').write_bytes(b'stock')
        with patch.object(core, 'load_deployed', return_value={'mod': True}):
            with self.assertRaisesRegex(ValueError, 'Purge'):
                store.capture_stock_folder(self.game, stock, self.archive)

    def test_stock_archive_requires_all_captured_files_to_match_game(self):
        current = self.data / 'generated_test.dl_bin'
        self.write(current, bytes(range(100)))
        stock = self.stock_copy(current)
        for i in range(core.REQUIRED_STOCK_FILES - 1):
            extra = self.data / f'generated_extra_{i}.dl_bin'
            self.write(extra, bytes([i % 256]))
            shutil.copy2(extra, stock / extra.name)
        self.assertEqual(len(list(stock.glob('*.dl_bin'))), core.REQUIRED_STOCK_FILES)
        self.assertTrue(store.capture_stock_folder(self.game, stock, self.archive).is_dir())
        bad = self.data / 'generated_extra_0.dl_bin'
        self.write(bad, b'altered after verification')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            store.capture_stock_folder(self.game, stock, self.archive)

    def test_missing_baseline_does_not_publish(self):
        current, mod, _ = self.fixture()
        with self.assertRaisesRegex(ValueError, 'No compatible archived baseline'):
            store.repair(mod, self.game, self.root / 'empty', self.output)
        self.assertFalse(self.output.exists())

    def test_tampered_archive_blocked(self):
        current, mod, baseline = self.fixture()
        (baseline / 'data/game' / current.name).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            store.repair(mod, self.game, self.archive, self.output)

    def test_deployed_and_steam_update_block_capture(self):
        self.write(self.data / 'generated_test.dl_bin', bytes(range(100)))
        with patch.object(core, 'load_deployed', return_value={'mod': 1}):
            with self.assertRaisesRegex(ValueError, 'Purge'):
                store.capture(self.game, self.archive)
        self.build('100', '1024')
        with self.assertRaisesRegex(ValueError, 'Steam is updating'):
            store.capture(self.game, self.archive)
        self.assertEqual(store.builds(self.archive), [])

    def test_mod_zip_and_multi_file_all_or_nothing(self):
        current, mod, _ = self.fixture()
        package = self.root / 'mod.zip'
        with zipfile.ZipFile(package, 'w') as archive:
            archive.write(mod, 'mod/data/game/' + mod.name)
            archive.writestr('README.txt', 'description')
        output, _ = store.repair(package, self.game, self.archive, self.output)
        self.assertTrue((output / 'README.txt').is_file())
        self.assertTrue((output / 'data/game' / mod.name).is_file())
        self.assertEqual(output.name, 'BotRepaired-mod')
        second, _ = store.repair(package, self.game, self.archive, self.output)
        self.assertEqual(second.name, 'BotRepaired-mod (2)')
        self.write(mod.parent / 'generated_missing.dl_bin', bytes(range(100)))
        with self.assertRaises(ValueError):
            store.repair(mod.parent, self.game, self.archive, self.output)
        self.assertEqual(len(list(self.output.glob('BotRepaired-*'))), 2)

    def test_captures_only_repair_inputs_and_retains_archive_sidecars(self):
        self.write(self.data / 'generated_test.dl_bin', bytes(range(100)))
        for name in ('audio.nxa', 'unused.dll', 'game/types.dl_typelib'):
            path = self.game / 'data' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'unused')
        for name in ('0123456789abcdef', '0123456789abcdef.stream', '0123456789abcdef.gpu_resources'):
            (self.game / 'data' / name).write_bytes(b'keep')
        folder = store.capture(self.game, self.archive)
        meta = store.builds(self.archive)[0][1]
        self.assertEqual(meta['scope'], 'repair-data')
        self.assertEqual(len(meta['files']), 4)
        self.assertFalse((folder / 'data/audio.nxa').exists())
        self.assertTrue((folder / 'data/0123456789abcdef.stream').is_file())

    def test_trims_existing_capture_without_losing_repair_baselines(self):
        import json
        current, mod, folder = self.fixture()
        unused = folder / 'data/audio.nxa'
        unused.write_bytes(b'not used in repair')
        meta = store.builds(self.archive)[0][1]
        meta['scope'] = 'full-data'
        meta['files']['audio.nxa'] = store.digest(unused)
        meta['bytes'] += unused.stat().st_size
        (folder / 'build.json').write_text(json.dumps(meta))
        store.trim_archive(self.archive)
        self.assertFalse(unused.exists())
        updated = store.builds(self.archive)[0][1]
        self.assertEqual(updated['scope'], 'repair-data')
        self.assertEqual(updated['bytes'], (folder / 'data/game' / current.name).stat().st_size)
        output, _ = store.repair(mod, self.game, self.archive, self.output)
        self.assertTrue((output / 'data/game' / mod.name).exists())

    def test_purge_only_removes_repaired_storage(self):
        repaired = store.repaired_root() / 'BotRepaired-example'
        repaired.mkdir(parents=True)
        (repaired / 'payload').write_bytes(b'output')
        baseline = core.APP_DATA / 'Archive/keep'
        baseline.parent.mkdir()
        baseline.write_bytes(b'baseline')
        store.purge_repaired()
        self.assertEqual(list(store.repaired_root().iterdir()), [])
        self.assertEqual(baseline.read_bytes(), b'baseline')

    def test_zip_traversal_rejected(self):
        package = self.root / 'bad.zip'
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr('../outside.txt', 'bad')
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            store.repair(package, self.game, self.archive, self.output)
        self.assertFalse((self.root / 'outside.txt').exists())

    def test_game_change_during_capture_does_not_publish(self):
        self.write(self.data / 'generated_test.dl_bin', bytes(range(100)))
        def progress(_):
            self.build('200')
        with self.assertRaisesRegex(ValueError, 'build changed'):
            store.capture(self.game, self.archive, progress)
        self.assertEqual(store.builds(self.archive), [])

    def test_ambiguous_archive_baselines_block_automatic_selection(self):
        name = '0123456789abcdef'
        current = self.game / 'data' / name
        def write(path, payload):
            path.parent.mkdir(parents=True, exist_ok=True)
            header = struct.pack('<III', 0xF0000011, 1, 1) + bytes(60)
            types = struct.pack('<QQQII', 0, 22, 1, 16, 16)
            row = struct.pack('<7Q6I', 1, 22, 184, 0, 0, 0, 0, len(payload), 0, 0, 16, 16, 0)
            path.write_bytes(header + types + row + payload)
        payload = bytes(range(128))
        write(current, payload)
        store.capture(self.game, self.archive)
        self.build('200')
        second = payload[:40] + b'MOD1' + payload[44:]
        write(current, second)
        store.capture(self.game, self.archive)
        self.build('300')
        write(current, payload)
        mod = self.root / 'mod' / (name + '.patch_0')
        write(mod, second[:100] + b'MOD2' + second[104:])
        with self.assertRaisesRegex(ValueError, 'different repairs'):
            store.repair(mod, self.game, self.archive, self.output)
        self.assertFalse(self.output.exists())

    def test_disk_space_check_before_capture(self):
        from types import SimpleNamespace
        self.write(self.data / 'generated_test.dl_bin', bytes(range(100)))
        with patch.object(store.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(ValueError, 'Not enough space'):
                store.capture(self.game, self.archive)
        self.assertEqual(store.builds(self.archive), [])

    def test_imported_data_baseline_does_not_suppress_full_capture(self):
        self.write(self.data / 'generated_test.dl_bin', bytes(range(100)))
        imported = store.import_data_baseline(self.data, '100', self.archive)
        self.assertTrue((imported / 'data/game/snapshot.json').is_file())
        self.assertEqual(store.builds(self.archive)[0][1]['scope'], 'data-only')
        full = store.capture(self.game, self.archive)
        self.assertNotEqual(full, imported)
        self.assertEqual(len(store.builds(self.archive)), 2)

    def test_old_profile_is_validated_but_not_copied_to_new_payload(self):
        import json
        _, mod, _ = self.fixture()
        (mod.parent / 'profile.json').write_text(json.dumps({
            'target': 'data/game/' + mod.name, 'sha256': store.digest(mod)}))
        output, _ = store.repair(mod.parent, self.game, self.archive, self.output)
        self.assertFalse((output / 'profile.json').exists())
        (mod.parent / 'profile.json').write_text(json.dumps({'target': '../escape', 'sha256': 'wrong'}))
        with self.assertRaisesRegex(ValueError, 'Invalid data profile'):
            store.repair(mod.parent, self.game, self.archive, self.output)


if __name__ == '__main__':
    unittest.main()
