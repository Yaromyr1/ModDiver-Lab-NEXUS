"""Purge recovery and runtime data restoration regressions."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import core
import build_archive


class PurgeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / 'game'
        (self.game / 'data/game').mkdir(parents=True)
        self.cfg = {'game': str(self.game), 'mods': [], 'nomofomo': False}
        p = patch.multiple(core, APP_DATA=self.root/'app', BACKUPS=self.root/'backups',
                           DEPLOYED=self.root/'deployed.json', STOCK=self.root/'stock')
        p.start(); self.addCleanup(p.stop)
        p = patch.object(build_archive, 'clean_restore_files', return_value={})
        self.originals = p.start(); self.addCleanup(p.stop)

    def test_receipts_remove_patch_sidecars_and_restore_original(self):
        targets = ['data/123.patch_0', 'data/123.patch_0.stream', 'data/123.patch_0.gpu_resources', 'data/mod/test.lua']
        receipt = {}
        for name in targets:
            path = core.target_path(self.cfg, name); path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'mod'); receipt[name] = {'existed': False}
        original = self.game / 'data/original'
        original.write_bytes(b'changed')
        backup = self.root/'original-backup'; backup.write_bytes(b'clean')
        receipt['data/original'] = {'existed': True, 'backup': str(backup)}
        core.save_deployed(receipt)
        self.assertEqual(core.purge(self.cfg, lambda _: None), 5)
        self.assertEqual(original.read_bytes(), b'clean')
        for name in targets: self.assertFalse(core.target_path(self.cfg, name).exists())
        self.assertEqual(core.load_deployed(), {})
        self.assertEqual(core.purge(self.cfg, lambda _: None), 0)

    def test_runtime_changes_restore_even_without_receipt(self):
        dest = self.game/'data/game/generated_test.dl_bin'; dest.write_bytes(b'runtime changed')
        stock = self.root/'clean'; stock.write_bytes(b'clean')
        self.originals.return_value = {'data/game/generated_test.dl_bin': stock}
        self.assertEqual(core.purge(self.cfg, lambda _: None), 1)
        self.assertEqual(dest.read_bytes(), b'clean')

    def test_missing_backup_fails_and_keeps_receipt(self):
        dest = self.game/'data/original'; dest.write_bytes(b'changed')
        receipt = {'data/original': {'existed': True, 'backup': str(self.root/'missing')}}
        core.save_deployed(receipt)
        with self.assertRaisesRegex(RuntimeError, 'Purge incomplete'):
            core.purge(self.cfg, lambda _: None)
        self.assertEqual(core.load_deployed(), receipt)
        self.assertEqual(dest.read_bytes(), b'changed')

    def test_transaction_failure_keeps_receipt_and_does_not_report_restored(self):
        dest = self.game/'data/mod.lua'; dest.write_bytes(b'mod')
        receipt = {'data/mod.lua': {'existed': False}}
        core.save_deployed(receipt); logs = []
        with patch.object(core, 'apply_file_transaction', side_effect=PermissionError('locked')):
            with self.assertRaisesRegex(RuntimeError, 'Purge incomplete'):
                core.purge(self.cfg, logs.append)
        self.assertEqual(core.load_deployed(), receipt)
        self.assertEqual(dest.read_bytes(), b'mod')
        self.assertFalse(any('restored/removed' in line for line in logs))
