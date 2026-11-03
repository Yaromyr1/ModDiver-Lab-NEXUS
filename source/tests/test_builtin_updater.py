import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import builtin_updater as updater
import core
from dlbin_codec import DLBin, content_hash


class BuiltinUpdaterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent.parent)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / 'steamapps/common/Helldivers 2'
        self.data = self.game / 'data/game'
        self.data.mkdir(parents=True)
        self.manifest = self.game.parent.parent / 'appmanifest_553850.acf'
        self.manifest.write_text('"appid" "553850" "buildid" "200" "StateFlags" "4"')
        self.bundle = self.root / 'bundle'
        self.bundle.mkdir()
        self.name = 'generated_test.dl_bin'
        self.current = self.data / self.name
        self.payload = bytes(range(100))
        self.write(self.payload)
        original = self.current.read_bytes()
        parsed = DLBin.open(self.current)
        parsed.replace(0, 0, self.payload[:40] + b'MOD!' + self.payload[44:])
        mod, _ = parsed.prepare()
        with zipfile.ZipFile(self.bundle / 'repair-baseline-26088801.zip', 'w') as archive:
            plain = core.unseal(original)
            archive.writestr(self.name, plain)
            archive.writestr('baseline.json', json.dumps({'format': 'moddiver-plain-baseline-1',
                'build_id': '26088801', 'files': {self.name: hashlib.sha256(plain).hexdigest()}}))
        with zipfile.ZipFile(self.bundle / 'consistent_vaulting.zip', 'w') as archive:
            archive.writestr(self.name, mod)
            archive.writestr('profile.json', json.dumps({'target': self.name,
                'sha256': hashlib.sha256(mod).hexdigest()}))
        self.write(b'inserted' + self.payload)
        for name, value in [('ROOT', self.bundle), ('NAMES', {'consistent_vaulting': 'Vaulting'}),
                            ('TARGETS', {'consistent_vaulting': self.name})]:
            mock = patch.object(updater, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        mock = patch.multiple(core, APP_DATA=self.root / 'appdata', STOCK=self.root / 'stock',
                              DEPLOYED=self.root / 'deployed.json')
        mock.start()
        self.addCleanup(mock.stop)
        self.cfg = {'game': str(self.game), 'mods': []}

    def write(self, payload):
        header = lambda kind, size: b'LDLD\x01\0\0\0' + struct.pack('<IIQ', kind, size, 1)
        self.current.write_bytes(core.seal(b'prefix00' + header(123, len(payload)) + payload
                                          + header(456, 16) + b'X' * 16))

    def test_first_launch_repairs_caches_and_recovers_corrupt_cache(self):
        before = self.current.read_bytes()
        result = updater.ensure(self.cfg)['consistent_vaulting']
        self.assertIsInstance(result, Path)
        parsed = DLBin.open(result)
        self.assertEqual(parsed.payload(0, 0)[48:52], b'MOD!')
        self.assertEqual(content_hash(parsed.plain), content_hash(DLBin.open(self.current).plain))
        with patch.object(updater.build_archive, 'automatic_plan', side_effect=AssertionError('cached')), \
             patch.object(updater, '_baselines', side_effect=AssertionError('cached checks must skip baseline work')):
            self.assertEqual(updater.ensure(self.cfg)['consistent_vaulting'], result)
        result.write_bytes(b'corrupt')
        self.assertIsInstance(updater.ensure(self.cfg)['consistent_vaulting'], Path)
        self.assertEqual(self.current.read_bytes(), before)

    def test_worker_returns_empty_result_without_touching_game(self):
        self.assertEqual(updater.run_worker({'game': ''}), {})

    def test_deployment_only_reads_verified_cache_until_manual_repair(self):
        with patch.object(updater, '_baselines', side_effect=AssertionError('must not repair')), \
             patch.object(updater.build_archive, 'automatic_plan', side_effect=AssertionError('must not repair')):
            result = updater.ensure(self.cfg, refresh=False)
        self.assertIn('No verified', result['consistent_vaulting'])
        self.assertFalse(core.STOCK.exists())
        prepared = updater.ensure(self.cfg)['consistent_vaulting']
        with patch.object(updater, '_baselines', side_effect=AssertionError('must not repair')), \
             patch.object(updater.build_archive, 'automatic_plan', side_effect=AssertionError('must not repair')):
            self.assertEqual(updater.ensure(self.cfg, refresh=False)['consistent_vaulting'], prepared)
            prepared.write_bytes(b'broken cache')
            self.assertIn('No verified', updater.ensure(self.cfg, refresh=False)['consistent_vaulting'])
        self.assertEqual(prepared.read_bytes(), b'broken cache')
        self.assertIsInstance(updater.ensure(self.cfg)['consistent_vaulting'], Path)

    def test_updated_game_invalidates_cache_and_keeps_new_stock(self):
        first = updater.ensure(self.cfg)['consistent_vaulting']
        self.write(b'inserted' + self.payload[:80] + b'GAME' + self.payload[84:])
        second = updater.ensure(self.cfg)['consistent_vaulting']
        self.assertIsInstance(second, Path)
        self.assertNotEqual(first, second)
        self.assertFalse(first.parent.exists(), "Superseded built-in cache must be removed")
        parsed = DLBin.open(second)
        self.assertEqual(parsed.payload(0, 0)[88:92], b'GAME')
        self.assertEqual(parsed.payload(0, 0)[48:52], b'MOD!')

    def test_conflicting_update_never_uses_stale_output(self):
        self.assertIsInstance(updater.ensure(self.cfg)['consistent_vaulting'], Path)
        self.write(b'inserted' + self.payload[:40] + b'GAME' + self.payload[44:])
        self.assertIsInstance(updater.ensure(self.cfg)['consistent_vaulting'], str)

    def test_managed_mod_uses_backup_and_never_captures_installed_edits(self):
        before = self.current.read_bytes()
        result = updater.ensure(self.cfg)['consistent_vaulting']
        backup = self.root / 'backup.dl_bin'
        backup.write_bytes(before)
        self.current.write_bytes(result.read_bytes())
        core.save_deployed({self.name: {'backup': str(backup)}})
        self.assertEqual(updater.ensure(self.cfg)['consistent_vaulting'], result)
        self.assertEqual((core.STOCK / self.name).read_bytes(), before)
        self.assertEqual(self.current.read_bytes(), result.read_bytes())

    def test_incomplete_steam_update_blocks_processing(self):
        self.manifest.write_text('"appid" "553850" "buildid" "200" "StateFlags" "6"')
        with self.assertRaisesRegex(ValueError, 'Steam is updating'):
            updater.ensure(self.cfg)
        self.assertFalse(core.STOCK.exists())

    def test_steam_replacement_updates_without_manual_purge_or_stale_backup(self):
        original = self.current.read_bytes()
        first = updater.ensure(self.cfg)['consistent_vaulting']
        backup = self.root / 'backup.dl_bin'
        backup.write_bytes(original)
        core.save_deployed({self.name: {'backup': str(backup), 'steam_build': '200',
            'installed_sha256': hashlib.sha256(first.read_bytes()).hexdigest()}})
        self.manifest.write_text('"appid" "553850" "buildid" "300" "StateFlags" "4"')
        self.write(b'inserted' + self.payload[:80] + b'GAME' + self.payload[84:])
        current = self.current.read_bytes()
        self.assertIsInstance(updater.ensure(self.cfg)['consistent_vaulting'], Path)
        self.assertEqual(core.load_deployed(), {})
        self.assertEqual((core.STOCK / self.name).read_bytes(), current)
        self.assertEqual(self.current.read_bytes(), current)

    def test_one_failed_profile_does_not_block_other_updates(self):
        with patch.object(updater, 'NAMES', {'broken': 'Broken', 'consistent_vaulting': 'Vaulting'}), \
             patch.object(updater, 'TARGETS', {'broken': self.name, 'consistent_vaulting': self.name}):
            result = updater.ensure(self.cfg)
        self.assertIsInstance(result['broken'], str)
        self.assertIsInstance(result['consistent_vaulting'], Path)

    def test_repair_baselines_open_lazily_only_after_cache_and_prepared_checks(self):
        order = []

        class Session:
            def __enter__(self):
                return ([], [])

            def __exit__(self, *_):
                return False

        def capture(*_args):
            order.append('capture-stock')
            return self.current

        def baseline_session(_log, **kwargs):
            # Model the production session's initial downloaded witnesses.
            order.append('downloaded-baselines')
            return Session()

        with patch.object(updater, '_baselines', side_effect=baseline_session), \
             patch.object(updater, '_clean_file', side_effect=capture), \
             patch.object(updater.core, 'APP_DATA', Path(updater.core.APP_DATA)), \
             patch.object(updater.core, 'STOCK', Path(updater.core.APP_DATA) / 'stock'):
            updater.ensure(self.cfg)
        self.assertEqual(order[0], 'capture-stock')
        self.assertIn('downloaded-baselines', order)
        self.assertIn('capture-stock', order)

    def test_corrupted_bundled_baseline_cannot_be_imported(self):
        package = self.bundle / 'repair-baseline-26088801.zip'
        with zipfile.ZipFile(package) as archive:
            plain = archive.read(self.name)
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr(self.name, plain)
            archive.writestr('baseline.json', json.dumps({'format': 'moddiver-plain-baseline-1',
                'build_id': '26088801', 'files': {self.name: 'wrong-checksum'}}))
        result = updater.ensure(self.cfg)
        self.assertIn('checksum mismatch', result['consistent_vaulting'])
        self.assertFalse(core.STOCK.exists())

    def test_failed_selected_update_blocks_deployment_before_game_writes(self):
        cfg = {**self.cfg, 'nomofomo': False, 'consistent_vaulting': True}
        with patch.object(updater, 'ensure', return_value={'consistent_vaulting': 'blocked'}) as ensure, \
             patch.object(core, 'atomic_write') as write:
            with self.assertRaises(core.BuiltinModsUnavailable):
                core.deploy(cfg)
            self.assertEqual(ensure.call_args_list, [unittest.mock.call(cfg, print, refresh=False),
                                                    unittest.mock.call(cfg, print, refresh=True)])
            write.assert_not_called()
