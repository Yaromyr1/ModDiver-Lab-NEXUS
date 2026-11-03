import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import core
import yao_forge
from types import SimpleNamespace
from unittest.mock import Mock


class ImportAndCaptureTests(unittest.TestCase):
    def test_tar_silent_failure_retries_installed_7zip(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder) / 'mod.7z'
            package.write_bytes(b'fixture')
            def execute(args, **kwargs):
                if core.os.name == 'nt':
                    self.assertEqual(kwargs.get('creationflags'), subprocess.CREATE_NO_WINDOW)
                if '-tf' in args:
                    return subprocess.CompletedProcess(args, 0, b'payload.bin\n', b'')
                if '-xf' in args:
                    return subprocess.CompletedProcess(args, -1073741819, b'', b'')
                self.assertEqual(args[0], '7z')
                target = Path(next(arg[2:] for arg in args if arg.startswith('-o')))
                (target / 'payload.bin').write_bytes(b'payload')
                return subprocess.CompletedProcess(args, 0, b'', b'')
            with patch.object(core.shutil, 'which', side_effect=lambda name: name if name in ('bsdtar', '7z') else None), \
                 patch.object(core.subprocess, 'run', side_effect=execute):
                self.assertEqual(core._read_7z_entries(package), [('payload.bin', b'payload')])

    def test_failed_extract_reports_exit_status_without_stderr(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder) / 'mod.7z'
            package.write_bytes(b'fixture')
            results = [subprocess.CompletedProcess([], 0, b'payload.bin\n', b''),
                       subprocess.CompletedProcess([], 2, b'', b''),
                       subprocess.CompletedProcess([], 2, b'', b'')]
            with patch.object(core.shutil, 'which', return_value='extractor'), \
                 patch.object(core.subprocess, 'run', side_effect=results):
                with self.assertRaisesRegex(ValueError, 'exit 0x00000002'):
                    core._read_7z_entries(package)

    def test_direct_capture_archives_user_confirmation_before_ready(self):
        app = Mock()
        app.busy = False
        app.cfg = {}
        app._task_error = None
        def run(work, done):
            app._task_result = work()
            done()
        app._task.side_effect = run
        with patch.object(core, 'capture_stock', return_value=core.REQUIRED_STOCK_FILES), \
             patch.object(core, 'game_dir', return_value=Path('game')), \
             patch('build_archive.capture_stock_folder') as archive:
            yao_forge.App.capture_stock(app)
        archive.assert_called_once_with(Path('game'), core.STOCK, verification='user-confirmed-stock-capture')
        app._log_stock_ready_banner.assert_called_once()
        self.assertIn('user-confirmed', app.log.call_args.args[0])

    def test_user_confirmed_baseline_matches_after_restart_and_detects_changes(self):
        import build_archive
        import shutil
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            game, stock, archive = root / 'game', root / 'stock', root / 'archive'
            data = game / 'data/game'
            data.mkdir(parents=True)
            stock.mkdir()
            for index in range(core.REQUIRED_STOCK_FILES):
                path = data / f'generated_{index}.dl_bin'
                path.write_bytes(b'clean data')
                shutil.copy2(path, stock / path.name)
            with patch.object(core, 'load_deployed', return_value={}), \
                 patch.object(build_archive, 'steam_build', return_value='26251122'):
                saved = build_archive.capture_stock_folder(game, stock, archive,
                            verification='user-confirmed-stock-capture')
                self.assertEqual(build_archive.find_matching_clean_baseline(game, '26251122', archive), saved)
                (data / 'generated_0.dl_bin').write_bytes(b'changed data')
                self.assertIsNone(build_archive.find_matching_clean_baseline(game, '26251122', archive))
                restore = build_archive.clean_restore_files(game, archive)
                self.assertEqual(len(restore), core.REQUIRED_STOCK_FILES)
                self.assertEqual(restore['data/game/generated_0.dl_bin'].read_bytes(), b'clean data')
                (saved / 'data/game/generated_0.dl_bin').write_bytes(b'corrupt backup')
                self.assertEqual(build_archive.clean_restore_files(game, archive), {})
