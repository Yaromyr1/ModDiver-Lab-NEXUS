import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import core
import loader_cleanup


class LoaderCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / 'game'
        self.folder = self.game / 'data' / 'game'
        self.folder.mkdir(parents=True)
        self.app = self.root / 'app'
        self.cfg = {'game': str(self.game)}
        for name, value in (('APP_DATA', self.app), ('DEPLOYED', self.app / 'deployed.json'),
                            ('BACKUPS', self.app / 'backups')):
            mock = patch.object(core, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        env = patch.dict(os.environ, {'LOCALAPPDATA': str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        self.name = 'generated_damage_settings.dl_bin'
        self.target = self.folder / self.name
        self.backup = self.folder / (self.name + loader_cleanup.SUFFIXES[0])
        self.original = core.seal(b'original' * 20)
        self.logs = []

    def purge(self):
        return core.purge(self.cfg, self.logs.append)

    def state(self, data):
        (self.root / 'YAO-DATA-LOADER.state').write_text(
            f'{self.name}|mod|{len(self.original)}|{len(data)}|{loader_cleanup.fingerprint(data)}\n')

    def test_all_eleven_reported_files_cleaned_without_receipt(self):
        names = ('customization_passive_bonuses', 'damage_settings', 'destruction_settings',
                 'entities', 'entity_deltas', 'explosion_settings', 'generation_settings',
                 'projectile_settings', 'scenario_settings', 'status_effect_settings', 'stratagem_settings')
        for name in names:
            dest = self.folder / f'generated_{name}.dl_bin'
            dest.write_bytes(self.original)
            dest.with_name(dest.name + loader_cleanup.SUFFIXES[0]).write_bytes(self.original)
        unrelated = self.folder / 'user.original'
        unrelated.write_bytes(b'keep')
        self.assertEqual(self.purge(), 11)
        self.assertEqual(self.purge(), 0)
        self.assertFalse(list(self.folder.glob('*.yao-loader-original')))
        self.assertEqual(len(list((self.app / 'loader-recovery').rglob('*.yao-loader-original'))), 11)
        self.assertEqual(unrelated.read_bytes(), b'keep')

    def test_known_runtime_output_restored(self):
        modified = core.seal(b'modded' * 20)
        self.target.write_bytes(modified)
        self.backup.write_bytes(self.original)
        self.state(modified)
        self.assertEqual(self.purge(), 1)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_steam_updated_file_preserved_and_old_backup_archived(self):
        current = core.seal(b'new game build' * 20)
        self.target.write_bytes(current)
        self.backup.write_bytes(self.original)
        self.state(core.seal(b'old modded data' * 20))
        self.purge()
        self.assertEqual(self.target.read_bytes(), current)
        self.assertFalse(self.backup.exists())
        self.assertEqual(next((self.app / 'loader-recovery').rglob(self.backup.name)).read_bytes(), self.original)

    def test_missing_target_restored(self):
        self.backup.write_bytes(self.original)
        self.purge()
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_corrupt_backup_retained_for_retry(self):
        self.backup.write_bytes(b'broken')
        self.assertEqual(self.purge(), 0)
        self.assertTrue(self.backup.exists())
        self.assertFalse(self.target.exists())
        self.assertTrue(any('purge warning' in entry for entry in self.logs))

    def test_recovery_write_failure_retains_backup(self):
        self.target.write_bytes(self.original)
        self.backup.write_bytes(self.original)
        with patch('loader_cleanup.atomic_write', side_effect=PermissionError('locked')):
            self.assertEqual(self.purge(), 0)
        self.assertTrue(self.backup.exists())
        self.assertEqual(self.purge(), 1)

    def test_temporary_and_rollback_files_archived(self):
        for suffix in loader_cleanup.SUFFIXES[1:]:
            (self.folder / (self.name + suffix)).write_bytes(b'recovery')
        self.assertEqual(self.purge(), 2)
        self.assertFalse(list(self.folder.glob('*.yao-loader-*')))

    def test_desktop_backup_has_final_priority(self):
        modified = core.seal(b'modded' * 20)
        self.target.write_bytes(modified)
        self.backup.write_bytes(self.original)
        self.state(modified)
        desktop_backup = self.root / 'desktop-original'
        desktop_backup.write_bytes(b'desktop original')
        core.save_deployed({self.name: {'existed': True, 'backup': str(desktop_backup)}})
        self.assertEqual(self.purge(), 2)
        self.assertEqual(self.target.read_bytes(), b'desktop original')
        self.assertEqual(core.load_deployed(), {})


if __name__ == '__main__':
    unittest.main()
