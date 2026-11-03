"""Maintenance regressions use disposable installations, never the user's data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import maintenance


class MaintenanceTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows directory handle regression')
    def test_uninstall_frees_original_name_while_explorer_handle_is_open(self):
        import ctypes
        from ctypes import wintypes
        import shutil
        import time
        install = self.root/'ModDiver Laboratory'
        install.mkdir()
        exe = install/'ModDiver Laboratory.exe'
        exe.touch()
        (install/'payload.txt').write_text('old install')
        helper_dir = self.root/'helper'
        helper_dir.mkdir()
        shutil.copy2(Path(maintenance.__file__).with_name('loading_screen.cs'), helper_dir/'loading_screen.cs')
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        # Explorer's directory watcher allows rename/delete but keeps the directory
        # object alive. Deleting in place leaves the original name unusable.
        handle = kernel.CreateFileW(str(install), 0x80000000, 7, None, 3, 0x02000000, None)
        self.assertNotEqual(handle, wintypes.HANDLE(-1).value)
        try:
            sleeper = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)'])
            self.addCleanup(lambda: sleeper.poll() is None and sleeper.kill())
            plan = dict(data=str(self.data), pid=sleeper.pid, files=[], folders=[],
                        uninstall=True, install_root=str(install), install_launcher=str(exe),
                        remove_data=True, background='#080808', caption='#141414', caption_text='#ffffff')
            (helper_dir/'plan.json').write_text(json.dumps(plan))
            script = helper_dir/'worker.ps1'
            script.write_text(maintenance.WINDOWS_WORKER, encoding='utf-8-sig')
            helper = subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive',
                                       '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                                      creationflags=subprocess.CREATE_NO_WINDOW)
            self.addCleanup(lambda: helper.poll() is None and helper.kill())
            deadline = time.monotonic()+15
            while exe.exists() and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertFalse(exe.exists())
            # Reinstall immediately, before closing the old Explorer handle.
            install.mkdir()
            replacement = install/'ModDiver Laboratory.exe'
            replacement.write_text('new installation')
            self.assertEqual(helper.wait(timeout=40), 0)
            self.assertEqual(replacement.read_text(), 'new installation')
            self.assertFalse(self.data.exists())
        finally:
            kernel.CloseHandle(handle)

    def test_uninstall_deletes_current_folder_and_all_local_data_keeps_sibling_copy(self):
        current = self.root/'ModDiver Laboratory 2.0.6'
        sibling = self.root/'ModDiver Laboratory 2.0.5'
        current.mkdir(); sibling.mkdir()
        exe = current/'ModDiver Laboratory.exe'; exe.touch()
        (current/'extra user file.txt').touch()
        (sibling/'ModDiver Laboratory.exe').touch()
        (self.data/'config.json').write_text('settings')
        baseline = self.data.parent/'ModDiver Lab Baseline Data'
        baseline.mkdir()
        (baseline/'baseline.zip').write_bytes(b'protected baseline')
        for name in ('Archive/build-100', 'Repaired Mods/BotRepaired-example', 'python/runtime', 'app/2.0.15'):
            payload = self.data/name
            payload.mkdir(parents=True)
            (payload/'payload').write_bytes(b'local data')
        with patch.dict(os.environ, {'YAO_FORGE_EXE': str(exe)}), patch.object(maintenance, 'IS_WINDOWS', True):
            plan = maintenance.make_plan(self.data, self.root, uninstall=True)
        # Don't touch the actual user's desktop shortcut during this isolated test.
        plan['files'] = []
        self.assertEqual(Path(plan['install_root']), current)
        self.assertTrue(plan['remove_data'])
        maintenance.complete(plan, self.root)
        self.assertFalse(current.exists())
        self.assertTrue((sibling/'ModDiver Laboratory.exe').exists())
        self.assertFalse(self.data.exists())
        self.assertFalse(baseline.exists())

    def test_uninstall_rejects_shared_parent_folder(self):
        exe = self.root/'ModDiver Laboratory.exe'; exe.touch()
        with self.assertRaisesRegex(ValueError, 'own ModDiver'):
            maintenance.installation_root(exe)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root/'ModDiverLab'
        self.data.mkdir()

    def test_refuses_broad_deletion_and_launcher_inside_data(self):
        with self.assertRaises(ValueError):
            maintenance.make_plan(self.root, self.root)
        exe = self.data/'ModDiver Laboratory.exe'
        exe.touch()
        with patch.dict(os.environ, {'YAO_FORGE_EXE': str(exe)}), patch.object(maintenance, 'IS_WINDOWS', True):
            with self.assertRaisesRegex(ValueError, 'outside'):
                maintenance.make_plan(self.data, self.root)

    def test_linux_reset_restores_installer_seed_and_restarts(self):
        seed = self.data/'bootstrap'/'source'
        seed.mkdir(parents=True)
        bootstrap = seed/'linux_launcher.py'
        bootstrap.write_text('seed')
        (self.data/'old-settings').write_text('old')
        with patch.dict(os.environ, {'YAO_FORGE_BOOTSTRAP': str(bootstrap)}, clear=True), patch.object(maintenance, 'IS_WINDOWS', False):
            plan = maintenance.make_plan(self.data, seed)
        folder = self.root/'helper'
        folder.mkdir()
        import shutil
        shutil.copytree(self.data/'bootstrap', folder/'bootstrap')
        with patch.object(maintenance.subprocess, 'Popen') as start:
            maintenance.complete(plan, folder)
        self.assertFalse((self.data/'old-settings').exists())
        self.assertEqual(bootstrap.read_text(), 'seed')
        self.assertTrue((self.data/'.skip-legacy-migration').is_file())
        self.assertEqual(start.call_args.args[0], [sys.executable, str(bootstrap)])

    def test_reset_moves_legacy_baselines_outside_local_data(self):
        legacy = self.data/'Archive/build-100-example'
        legacy.mkdir(parents=True)
        (legacy/'build.json').write_text(json.dumps(dict(version=1, build_id='100',
            created_utc='test', files={}, bytes=0)))
        (legacy/'witness').write_bytes(b'historical baseline')
        exe = self.root/'ModDiver Laboratory.exe'
        exe.touch()
        with patch.dict(os.environ, {'YAO_FORGE_EXE': str(exe)}), patch.object(maintenance, 'IS_WINDOWS', True):
            plan = maintenance.make_plan(self.data, self.root, uninstall=False)
        self.assertIsNone(plan['baseline_data'])
        target = self.root/'ModDiver Lab Baseline Data/build-100-example/witness'
        with patch.object(maintenance.subprocess, 'Popen'):
            maintenance.complete(plan, self.root)
        self.assertEqual(target.read_bytes(), b'historical baseline')

    def test_fresh_data_does_not_reimport_legacy_settings(self):
        import core
        legacy = self.root/'YAOModForge'
        legacy.mkdir()
        (legacy/'config.json').write_text('{"old": true}')
        (self.data/'.skip-legacy-migration').touch()
        with patch.dict(os.environ, {'YAO_FORGE_DATA': str(self.data), 'YAO_FORGE_LEGACY_DATA': str(legacy)}):
            self.assertEqual(core._pick_data(), self.data)
        self.assertFalse((self.data/'config.json').exists())

    def test_uninstall_removes_only_installed_targets_and_does_not_restart(self):
        (self.data/'settings').touch()
        launcher = self.root/'ModDiver Laboratory.exe'
        launcher.touch()
        unrelated = self.root/'personal.txt'
        unrelated.write_text('keep')
        plan = dict(data=str(self.data), files=[str(launcher)], uninstall=True)
        with patch.object(maintenance.subprocess, 'Popen') as start:
            maintenance.complete(plan, self.root)
        self.assertFalse(self.data.exists())
        self.assertFalse(launcher.exists())
        self.assertEqual(unrelated.read_text(), 'keep')
        start.assert_not_called()

    def test_packaged_uninstall_owns_files_without_claiming_unrelated_files(self):
        exe = self.root/'ModDiver Laboratory.exe'
        exe.touch()
        source = self.root/'source'
        source.mkdir()
        (source/'core.py').touch()
        (self.root/'personal.txt').touch()
        manifest = self.root/'uninstall-manifest.json'
        metadata = dict(application='ModDiver Laboratory', files=['ModDiver Laboratory.exe', 'source/core.py'])
        manifest.write_text(json.dumps(metadata))
        files, folders = maintenance.package_targets(exe)
        self.assertIn(str(source/'core.py'), files)
        self.assertNotIn(str(self.root/'personal.txt'), files)
        self.assertEqual(folders, [str(source), str(self.root)])
        metadata['files'].append('../outside.txt')
        manifest.write_text(json.dumps(metadata))
        with self.assertRaises(ValueError):
            maintenance.package_targets(exe)

    @unittest.skipUnless(os.name == 'nt', 'Windows helper integration')
    def test_real_powershell_worker_waits_deletes_and_relaunches(self):
        # A tiny disposable launcher records its invocation after reset.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        import build_release
        marker = self.root/'restarted'
        exe = self.root/'ModDiver Laboratory.exe'
        source = self.root/'probe.cs'
        source.write_text('using System.IO; class Probe { static void Main() { File.WriteAllText(@"' + str(marker).replace('"', '""') + '", "restarted"); } }')
        subprocess.run([build_release.find_csc(), '/nologo', '/target:winexe', '/out:'+str(exe), str(source)], check=True, capture_output=True)
        for uninstall in (False, True):
            with self.subTest(uninstall=uninstall):
                marker.unlink(missing_ok=True)
                self.data.mkdir(exist_ok=True)
                (self.data/'old-config').touch()
                folder = self.root/('uninstall-helper' if uninstall else 'reset-helper')
                folder.mkdir()
                sleeper = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)'])
                import shutil
                shutil.copy2(Path(maintenance.__file__).with_name('loading_screen.cs'), folder/'loading_screen.cs')
                script = folder/'worker.ps1'
                script.write_text(maintenance.WINDOWS_WORKER, encoding='utf-8-sig')
                plan = dict(data=str(self.data), pid=sleeper.pid, files=[str(exe)] if uninstall else [],
                            uninstall=uninstall, restart=[str(exe)], cwd=str(self.root), background='#0b1020',
                            baseline_data=str(self.root/'ModDiver Lab Baseline Data') if uninstall else None)
                baseline = self.root/'ModDiver Lab Baseline Data'
                baseline.mkdir(exist_ok=True)
                (baseline/'witness').write_bytes(b'protected baseline')
                (folder/'plan.json').write_text(json.dumps(plan))
                helper = subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script)], creationflags=subprocess.CREATE_NO_WINDOW)
                import time
                deadline = time.monotonic()+10
                while not (folder/'ready').exists() and time.monotonic()<deadline:
                    time.sleep(.05)
                self.assertTrue((folder/'ready').exists())
                self.assertTrue((self.data/'old-config').exists())
                sleeper.wait(timeout=10)
                self.assertEqual(helper.wait(timeout=40), 0)
                self.assertFalse((self.data/'old-config').exists())
                if uninstall:
                    self.assertFalse(baseline.exists())
                    self.assertFalse(exe.exists())
                    self.assertFalse(self.data.exists())
                    self.assertFalse(marker.exists())
                else:
                    self.assertEqual((baseline/'witness').read_bytes(), b'protected baseline')
                    deadline = time.monotonic()+5
                    while not marker.exists() and time.monotonic()<deadline:
                        time.sleep(.05)
                    self.assertTrue(marker.exists())
                    self.assertTrue((self.data/'.skip-legacy-migration').exists())


if __name__ == '__main__':
    unittest.main()
