import tempfile
import unittest
from pathlib import Path

import linux_launcher
import updater


class RevisionTests(unittest.TestCase):
    def test_same_version_refresh_preserves_data_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed, data = root/'download', root/'data'
            seed.mkdir(); data.mkdir()
            (seed/'yao_forge.py').write_text('VERSION = "2.1.0"\n')
            (seed/'ui_revision.txt').write_text('first')
            (data/'config.json').write_text('user settings')
            installed, current, previous = linux_launcher.prepare(seed, data)
            self.assertEqual(current, '2.1.0')
            (seed/'ui_revision.txt').write_text('second')
            (seed/'mod_options.py').write_text('# new options')
            installed, current, previous = linux_launcher.prepare(seed, data)
            self.assertEqual((installed/current/'ui_revision.txt').read_text(), 'second')
            self.assertTrue((installed/current/'mod_options.py').is_file())
            self.assertEqual((data/'config.json').read_text(), 'user settings')
            self.assertNotEqual(previous, current)
            self.assertEqual((installed/previous/'ui_revision.txt').read_text(), 'first')
            self.assertEqual(updater.read_pointer(installed), (current, previous))
            selected = updater.revert_previous(installed)
            self.assertEqual(selected, previous)
            self.assertEqual(linux_launcher.prepare(seed, data)[1], selected)
            self.assertEqual((installed/selected/'ui_revision.txt').read_text(), 'first')
            # A newer download supersedes the manual rollback selection.
            (seed/'ui_revision.txt').write_text('third')
            self.assertEqual(linux_launcher.prepare(seed, data)[1], '2.1.0')
            backups = list(installed.glob('.incomplete-*'))
            linux_launcher.prepare(seed, data)
            self.assertEqual(list(installed.glob('.incomplete-*')), backups)
            # Downloading an older full ZIP must not replace a newer app.
            newer = installed/'2.2.0'; newer.mkdir()
            (newer/updater.OK_MARKER).write_text('2.2.0')
            (newer/'yao_forge.py').write_text('VERSION = "2.2.0"')
            updater._write_pointer(installed, '2.2.0', '2.1.0')
            self.assertEqual(linux_launcher.prepare(seed, data)[1], '2.2.0')

    def test_rollback_recovers_unregistered_backup_and_rejects_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            current = root/'2.1.0'; current.mkdir()
            (current/'ui_revision.txt').write_text('new')
            (current/'yao_forge.py').write_text('new')
            (current/updater.OK_MARKER).write_text('2.1.0')
            updater._write_pointer(root, '2.1.0', None)
            bad = root/'2.0.0'; bad.mkdir()
            (bad/'yao_forge.py').write_text('partial')
            with self.assertRaises(updater.UpdateError):
                updater.revert_previous(root)
            backup = root/'.old-2.1.0-12345678'; backup.mkdir()
            (backup/'yao_forge.py').write_text('old')
            (backup/updater.OK_MARKER).write_text('2.1.0')
            selected = updater.revert_previous(root)
            self.assertEqual((root/selected/'yao_forge.py').read_text(), 'old')
            self.assertEqual(updater.read_pointer(root), (selected, '2.1.0'))

    def test_pointer_never_accepts_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'current.txt').write_text('../outside\n2.1.0-rollback-abcdef12\n')
            self.assertEqual(updater.read_pointer(root), ('2.1.0-rollback-abcdef12', None))
