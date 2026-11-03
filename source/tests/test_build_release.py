"""Release regressions: smaller runtimes must preserve required interpreter files."""
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import build_release


class RuntimeTests(unittest.TestCase):
    def test_nexus_keeps_manual_loader_installer_without_bundling_chef(self):
        ignored = build_release._nexus_source_ignore(build_release.SOURCE,
                    ['tool_installations.py', 'chef_updater.py'])
        self.assertNotIn('tool_installations.py', ignored)
        self.assertIn('chef_updater.py', ignored)
        self.assertIn('chef_loader', build_release._nexus_source_ignore(
            build_release.SOURCE / 'builtin', ['chef_loader']))

    def test_same_version_rebuild_revision_tracks_shipped_code_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)
            (source / 'yao_forge.py').write_text('old build')
            first = build_release.write_build_revision(source, '2.1.0')
            self.assertEqual(build_release.write_build_revision(source, '2.1.0'), first)
            (source / 'tests').mkdir()
            (source / 'tests/test_fixture.py').write_text('not shipped')
            self.assertEqual(build_release.write_build_revision(source, '2.1.0'), first)
            (source / 'yao_forge.py').write_text('fixed purge confirmation')
            second = build_release.write_build_revision(source, '2.1.0')
            self.assertNotEqual(first, second)
            self.assertEqual((source / 'ui_revision.txt').read_text().strip(), second)

    def test_same_version_linux_install_refreshes_stale_cached_code(self):
        import linux_launcher
        import updater
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed = root / 'seed'
            seed.mkdir()
            (seed / 'yao_forge.py').write_text('VERSION = "2.1.0"\n# corrected purge')
            build_release.write_build_revision(seed, '2.1.0')
            installed = root / 'data/app/2.1.0'
            installed.mkdir(parents=True)
            (installed / 'yao_forge.py').write_text('old modal confirmation')
            (installed / 'ui_revision.txt').write_text('2.1.0-bottom-loading-maximized-rollback')
            (installed / updater.OK_MARKER).write_text('2.1.0')
            updater._write_pointer(installed.parent, '2.1.0', None)
            linux_launcher.prepare(seed, root / 'data')
            self.assertEqual((installed / 'yao_forge.py').read_bytes(), (seed / 'yao_forge.py').read_bytes())

    def test_corrected_210_seed_replaces_only_known_local_versions(self):
        import linux_launcher
        import updater
        for current in ('2.1.3', '2.1.4'):
            with self.subTest(current=current), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                seed = root/'seed'
                seed.mkdir()
                (seed/'yao_forge.py').write_text('VERSION = "2.1.0"\n')
                (seed/'ui_revision.txt').write_text('2.1.0-library-presets-and-continuous-gradient\n')
                installed = root/'data/app'/current
                installed.mkdir(parents=True)
                (installed/'yao_forge.py').write_text('previous build')
                (installed/updater.OK_MARKER).write_text(current)
                updater._write_pointer(installed.parent, current, None)
                linux_launcher.prepare(seed, root/'data')
                active, previous = updater.read_pointer(installed.parent)
                self.assertEqual(active, '2.1.0' if current == '2.1.3' else current)
                if current == '2.1.3':
                    self.assertEqual(previous, current)
                self.assertEqual((installed/'yao_forge.py').read_text(), 'previous build')

    def test_numpy_removed_and_other_runtime_contents_preserved(self):
        entries = {
            'pythonw.exe': b'interpreter',
            'python314.dll': b'python dll',
            'DLLs/_tkinter.pyd': b'tk extension',
            'tcl/tk8.6/tk.tcl': b'tk source',
            'Lib/site-packages/other/__init__.py': b'keep',
            'Lib/site-packages/numpy/__init__.py': b'unused',
            'Lib/site-packages/numpy.libs/blas.dll': b'unused',
            'Lib/site-packages/numpy-2.0.dist-info/LICENSE.txt': b'unused',
        }
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/'original.zip', Path(folder)/'trimmed.zip'
            with zipfile.ZipFile(source, 'w') as archive:
                for name, data in entries.items():
                    archive.writestr(name, data)
            original = source.read_bytes()
            build_release.build_runtime_zip(source, target)
            self.assertEqual(source.read_bytes(), original)
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(set(archive.namelist()), {name for name in entries if '/numpy' not in name})
                for name in archive.namelist():
                    self.assertEqual(archive.read(name), entries[name])

    def test_app_package_omits_scratch_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('core.py', 'builtin/payload.zip', '_work/output.bin',
                         'tests/test_core.py', '__pycache__/core.pyc'):
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            self.assertEqual({rel for _, rel in build_release._app_files(root)},
                             {'core.py', 'builtin/payload.zip'})

    def test_app_update_excludes_separately_hosted_repair_data(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bundle = root / 'builtin/gameplay'
            bundle.mkdir(parents=True)
            name = 'repair-baseline-123.zip'
            (bundle / name).write_bytes(b'remote repair witness')
            (bundle / 'repair-data.json').write_text(json.dumps({'packages': {name: {}}}))
            (root / 'core.py').write_text('# keep')
            self.assertEqual({rel for _, rel in build_release._app_files(root)},
                             {'core.py', 'builtin/gameplay/repair-data.json'})

    def test_linux_installer_packaging_and_user_shortcut(self):
        import os
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            package = build_release.assemble_linux_zip(root/'linux.zip', build_release.read_version())
            with zipfile.ZipFile(package) as archive:
                for name in ('run-linux.sh', 'install-linux.sh', 'install-linux-distrobox.sh', 'Install ModDiver.desktop'):
                    info = archive.getinfo('ModDiver Laboratory/' + name)
                    self.assertTrue((info.external_attr >> 16) & 0o111)
                    self.assertNotIn(b'\r', archive.read(info))
                installer = archive.read('ModDiver Laboratory/install-linux.sh').decode()
            seed = root/'download with spaces'
            (seed/'source').mkdir(parents=True)
            (seed/'source'/'linux_launcher.py').write_text('# seed')
            (seed/'run-linux.sh').write_text('# launch')
            data = root/'user data'
            code = installer.split("<<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
            with patch.dict(os.environ, XDG_DATA_HOME=str(data)), patch.object(sys, 'argv', ['installer', str(seed)]):
                exec(compile(code, 'install-linux.sh', 'exec'), {})
            self.assertTrue((data/'ModDiverLab/bootstrap/source/linux_launcher.py').is_file())
            desktop = (data/'applications/moddiver-laboratory.desktop').read_text()
            self.assertIn('Exec=sh "', desktop)
            self.assertIn('Terminal=false', desktop)
            self.assertIn('user data', desktop)


class LinuxInstallerTests(unittest.TestCase):
    def test_distribution_routing_with_posix_shell(self):
        import os
        import shutil
        import subprocess
        shell = os.environ.get('MODDIVER_TEST_SH') or shutil.which('dash') or shutil.which('sh')
        if not shell:
            self.skipTest('POSIX shell unavailable')
        installer = Path(build_release.ROOT)/'install-linux.sh'
        cases = [('debian', '', 'debian', 'python3-tk'),
                 ('ubuntu', 'debian', 'debian', 'python3-tk'),
                 ('pika', 'debian', 'debian', 'python3-tk'),
                 ('linuxmint', 'ubuntu debian', 'debian', 'python3-tk'),
                 ('pop', 'ubuntu debian', 'debian', 'python3-tk'),
                 ('zorin', 'ubuntu debian', 'debian', 'python3-tk'),
                 ('fedora', '', 'fedora', 'python3-tkinter'),
                 ('nobara', 'fedora', 'fedora', 'python3-tkinter'),
                 ('arch', '', 'arch', 'libarchive'),
                 ('manjaro', 'arch', 'arch', 'libarchive'),
                 ('endeavouros', 'arch', 'arch', 'libarchive'),
                 ('cachyos', 'arch', 'arch', 'libarchive'),
                 ('garuda', 'arch', 'arch', 'libarchive'),
                 ('opensuse-tumbleweed', 'suse opensuse', 'suse', 'bsdtar'),
                 ('opensuse-leap', 'suse opensuse', 'suse', 'bsdtar'),
                 ('alpine', '', 'alpine', 'python3-tkinter')]
        with tempfile.TemporaryDirectory() as folder:
            release = Path(folder)/'os-release'
            for distro, like, family, package in cases:
                with self.subTest(distro=distro):
                    release.write_text(f'ID={distro}\nID_LIKE="{like}"\n', newline='\n')
                    env = dict(os.environ, MODDIVER_OS_RELEASE=release.as_posix())
                    result = subprocess.run([shell, str(installer), '--print-dependencies'],
                                            env=env, capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue(result.stdout.startswith(family + ':'))
                    self.assertIn(package, result.stdout)
            # Immutable desktops must stop before any package-manager action.
            bin_dir = Path(folder)/'bin'
            bin_dir.mkdir()
            (bin_dir/'id').write_text('#!/bin/sh\necho 1000\n', newline='\n')
            (bin_dir/'id').chmod(0o755)
            for distro in ('steamos', 'bazzite', 'silverblue', 'kinoite',
                           'aurora', 'bluefin', 'aeon', 'kalpa'):
                with self.subTest(immutable=distro):
                    release.write_text(f'ID={distro}\n', newline='\n')
                    env = dict(os.environ, MODDIVER_OS_RELEASE=release.as_posix(),
                               PATH=bin_dir.as_posix() + os.pathsep + os.environ['PATH'])
                    result = subprocess.run([shell, str(installer)], env=env,
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn('install-linux-distrobox.sh', result.stderr)
            for script in ('install-linux.sh', 'install-linux-distrobox.sh', 'run-linux.sh'):
                subprocess.run([shell, '-n', str(Path(build_release.ROOT)/script)], check=True)

    def test_container_shortcut_reenters_container(self):
        import os
        from unittest.mock import patch
        installer = (Path(build_release.ROOT)/'install-linux.sh').read_text()
        code = installer.split("<<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed = root/'source folder'
            (seed/'source').mkdir(parents=True)
            (seed/'source'/'linux_launcher.py').write_text('# seed')
            (seed/'run-linux.sh').write_text('# launch')
            data = root/'user data'
            with patch.dict(os.environ, XDG_DATA_HOME=str(data), YAO_FORGE_DISTROBOX='moddiver-laboratory'), patch.object(sys, 'argv', ['installer', str(seed)]):
                exec(compile(code, 'install-linux.sh', 'exec'), {})
            desktop = (data/'applications/moddiver-laboratory.desktop').read_text()
            self.assertIn('Exec=distrobox enter --name "moddiver-laboratory" -- env', desktop)
            self.assertIn('YAO_FORGE_DISTROBOX=moddiver-laboratory', desktop)
            self.assertIn(' sh "', desktop)
