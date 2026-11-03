"""Post-exit maintenance scoped to the running installation and its local data."""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

IS_WINDOWS = os.name == 'nt'
DATA_FOLDERS = ('ModDiverLab', 'ModDiverLabData', 'ModDiverLabNexus', 'ModDiverLabNexusData')


def baseline_name(data):
    return 'ModDiver Lab Nexus Baseline Data' if Path(data).name.startswith('ModDiverLabNexus') else 'ModDiver Lab Baseline Data'


def operating_system():
    if sys.platform.startswith('linux'):
        try:
            return platform.freedesktop_os_release().get('PRETTY_NAME', 'Linux')
        except OSError:
            return 'Linux'
    return f'{platform.system()} {platform.release()}'


def _inside(path, parent):
    return Path(path).resolve().is_relative_to(Path(parent).resolve())


def package_targets(launcher):
    """Remove individually listed distribution files, never an arbitrary tree."""
    root = Path(launcher).parent.resolve()
    manifest = root/'uninstall-manifest.json'
    if not manifest.is_file():
        return [str(launcher)], []
    metadata = json.loads(manifest.read_text(encoding='utf-8'))
    if metadata.get('application') != 'ModDiver Laboratory':
        raise ValueError('Invalid uninstall manifest.')
    files, folders = {str(launcher)}, set()
    for name in metadata['files']:
        relative = Path(name)
        target = root/relative
        if relative.is_absolute() or '..' in relative.parts or not _inside(target, root) or target.resolve() == root:
            raise ValueError('An uninstall target is outside the app installation.')
        if target.exists() and not target.is_file():
            raise ValueError('An uninstall file target is a directory.')
        files.add(str(target))
        parent = target.parent
        while parent != root:
            folders.add(str(parent))
            parent = parent.parent
    return sorted(files), sorted(folders, key=lambda value: len(Path(value).parts), reverse=True) + [str(root)]


def installation_root(launcher):
    """Authorize exactly the named distribution folder containing this launcher."""
    launcher = Path(launcher)
    root = launcher.parent
    if root.is_symlink() or (hasattr(root, 'is_junction') and root.is_junction()):
        raise ValueError('The installation folder cannot be a link or junction.')
    root = root.resolve()
    if not re.fullmatch(r'ModDiver[ _-]+Lab(?:oratory)?(?:[ _-]+(?:v?\d+(?:\.\d+)*|Windows|Linux))*', root.name, re.I):
        raise ValueError('Uninstall requires the launcher in its own ModDiver Laboratory folder. Move it into that folder first.')
    if root == Path.home().resolve() or root == Path(root.anchor):
        raise ValueError('Cannot uninstall a shared or root folder.')
    if not launcher.is_file() or launcher.is_symlink() or launcher.resolve().parent != root:
        raise ValueError('The launcher must belong to this installation folder.')
    return root


def make_plan(data, source, uninstall=False):
    if Path(data).is_symlink() or (hasattr(Path(data), 'is_junction') and Path(data).is_junction()):
        raise ValueError('The local data directory cannot be a symbolic link.')
    data = Path(data).resolve()
    exe = os.environ.get('YAO_FORGE_EXE')
    bootstrap = os.environ.get('YAO_FORGE_BOOTSTRAP')
    # Only the application's explicitly named data directory can be removed.
    if data.name not in DATA_FOLDERS:
        raise ValueError('The local data directory is not a recognized ModDiver installation.')
    plan = dict(data=str(data), uninstall=uninstall, files=[], folders=[], restart=[], cwd='', bootstrap=None,
                install_root=None, install_launcher=None, remove_data=True,
                baseline_data=str(data.parent/baseline_name(data)))
    if IS_WINDOWS:
        if not exe or not Path(exe).is_file() or Path(exe).name != 'ModDiver Laboratory.exe':
            raise ValueError('Start ModDiver Laboratory.exe before resetting data or uninstalling.')
        install = installation_root(exe) if uninstall else None
        exe = Path(exe).resolve()
        if _inside(exe, data):
            raise ValueError('Move ModDiver Laboratory.exe outside its local data folder first.')
        plan.update(restart=[str(exe)], cwd=str(exe.parent))
        if uninstall:
            plan['install_root'] = str(install)
            plan['install_launcher'] = str(exe)
    else:
        if not bootstrap or not Path(bootstrap).is_file():
            raise ValueError('Start with run-linux.sh before resetting data or uninstalling.')
        bootstrap = Path(bootstrap).resolve()
        plan.update(restart=[sys.executable, str(bootstrap)], cwd=str(bootstrap.parent))
        if _inside(bootstrap, data):
            # The Linux installer places the seed in local data too. Stage it outside
            # that directory before reset so it can be restored after deletion.
            if bootstrap != data/'bootstrap'/'source'/'linux_launcher.py':
                raise ValueError('Unrecognized Linux bootstrap location.')
            plan['bootstrap'] = str(data/'bootstrap')
        if _inside(sys.executable, data):
            raise ValueError('Maintenance requires a system Python outside local data.')
        if uninstall and not _inside(bootstrap, data):
            launcher = bootstrap.parent.parent/'run-linux.sh'
            plan['install_root'] = str(installation_root(launcher))
            plan['install_launcher'] = str(launcher)
        elif uninstall:
            # An installed Linux copy lives entirely in this named app-data folder.
            plan['remove_data'] = True
    if uninstall:
        nexus = data.name.startswith('ModDiverLabNexus')
        shortcut = 'ModDiver Laboratory Nexus' if nexus else 'ModDiver Laboratory'
        desktop = Path.home()/'Desktop'
        if IS_WINDOWS:
            # Known Folder API respects OneDrive and redirected desktops.
            import ctypes
            buffer = ctypes.create_unicode_buffer(32768)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buffer) == 0:
                desktop = Path(buffer.value)
            plan['files'].append(str(desktop/(shortcut+'.lnk')))
        else:
            if shutil.which('xdg-user-dir'):
                result = subprocess.run(['xdg-user-dir', 'DESKTOP'], capture_output=True, text=True, check=True, timeout=5)
                if result.stdout.strip():
                    desktop = Path(result.stdout.strip())
            plan['files'] += [str(desktop/(shortcut+'.desktop')),
                              str(data.parent/'applications'/('moddiver-laboratory-nexus.desktop' if nexus else 'moddiver-laboratory.desktop'))]
    if not uninstall:
        import build_archive
        build_archive.migrate_baselines(data)
    return plan


WINDOWS_WORKER = r'''
$ErrorActionPreference = 'Stop'
$taskDir = Split-Path -Parent $PSCommandPath
try {
    $plan = Get-Content -LiteralPath (Join-Path $taskDir 'plan.json') -Raw | ConvertFrom-Json
    $dataPath = [IO.Path]::GetFullPath($plan.data)
    if ((Split-Path -Leaf $dataPath) -notin @('ModDiverLab', 'ModDiverLabData', 'ModDiverLabNexus', 'ModDiverLabNexusData')) { throw 'Invalid data path' }
    $baselineName = if ((Split-Path -Leaf $dataPath) -like 'ModDiverLabNexus*') { 'ModDiver Lab Nexus Baseline Data' } else { 'ModDiver Lab Baseline Data' }
    $baselinePath = $null
    if ($plan.baseline_data) {
        $baselinePath = [IO.Path]::GetFullPath($plan.baseline_data)
        if ((Split-Path -Leaf $baselinePath) -ne $baselineName -or
            (Split-Path -Parent $baselinePath) -ne (Split-Path -Parent $dataPath)) { throw 'Invalid baseline path' }
        if ((Test-Path -LiteralPath $baselinePath) -and
            ((Get-Item -LiteralPath $baselinePath).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Baseline storage is a link' }
    }
    $installPath = $null
    if ($plan.uninstall -and $plan.install_root) {
        $installPath = [IO.Path]::GetFullPath($plan.install_root)
        $launcherPath = [IO.Path]::GetFullPath($plan.install_launcher)
        if ((Split-Path -Parent $launcherPath) -ne $installPath -or
            (Split-Path -Leaf $launcherPath) -ne 'ModDiver Laboratory.exe' -or
            (Split-Path -Leaf $installPath) -notmatch '^ModDiver[ _-]+Lab(oratory)?([ _-]+(v?\d+(\.\d+)*|Windows|Linux))*$' -or
            -not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) { throw 'Invalid installation path' }
        if ((Get-Item -LiteralPath $installPath).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Installation is a link' }
    }
    Add-Type -Path (Join-Path $taskDir 'loading_screen.cs') -ReferencedAssemblies System.Windows.Forms,System.Drawing
    [ModDiverLoading]::AssetDirectory = $taskDir
    [ModDiverLoading]::Show($plan.background, $plan.caption, $plan.caption_text, $plan.secondary)
    $appProcess = Get-Process -Id $plan.pid -ErrorAction SilentlyContinue
    [IO.File]::WriteAllText((Join-Path $taskDir 'ready'), '1')
    if ($appProcess) { $appProcess.WaitForExit() }
    Set-Location -LiteralPath $taskDir
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class ModDiverShell {
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    public static extern void SHChangeNotify(int change, uint flags, string item1, string item2);
}
'@
    $removedInstallPath = $null
    if ($installPath) {
        # Rename on the same volume before deleting. Open Explorer handles can keep
        # a deleted directory pending; the original name must be free for reinstall.
        $parentPath = Split-Path -Parent $installPath
        $removedInstallPath = Join-Path $parentPath ('.moddiver-uninstall-' + [Guid]::NewGuid().ToString('N'))
        $removedInstallPath = [IO.Path]::GetFullPath($removedInstallPath)
        if ((Split-Path -Parent $removedInstallPath) -ne $parentPath -or
            $removedInstallPath -eq $installPath) { throw 'Invalid cleanup path' }
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            try {
                [IO.Directory]::Move($installPath, $removedInstallPath)
                break
            } catch { if ($attempt -eq 59) { throw }; Start-Sleep -Milliseconds 500 }
        }
        # SHCNE_RENAMEFOLDER, SHCNF_PATHW | SHCNF_FLUSH.
        [ModDiverShell]::SHChangeNotify(0x20000, 0x1005, $installPath, $removedInstallPath)
        [IO.File]::SetAttributes($removedInstallPath, ([IO.File]::GetAttributes($removedInstallPath) -bor [IO.FileAttributes]::Hidden))
    }
    # The bootstrapper and runtime may still be releasing DLLs after the UI closes.
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            if (($null -eq $plan.remove_data -or $plan.remove_data) -and (Test-Path -LiteralPath $dataPath)) {
                Remove-Item -LiteralPath $dataPath -Recurse -Force
            }
            if ($baselinePath -and (Test-Path -LiteralPath $baselinePath)) {
                Remove-Item -LiteralPath $baselinePath -Recurse -Force
            }
            foreach ($filePath in $plan.files) {
                if (Test-Path -LiteralPath $filePath -PathType Leaf) { Remove-Item -LiteralPath $filePath -Force }
            }
            if ($removedInstallPath -and (Test-Path -LiteralPath $removedInstallPath)) {
                Remove-Item -LiteralPath $removedInstallPath -Recurse -Force
            }
            break
        } catch { if ($attempt -eq 59) { throw }; Start-Sleep -Milliseconds 500 }
    }
    if ($removedInstallPath) {
        # SHCNE_RMDIR and SHCNE_UPDATEDIR refresh redirected/OneDrive desktops too.
        [ModDiverShell]::SHChangeNotify(0x10, 0x1005, $removedInstallPath, $null)
        [ModDiverShell]::SHChangeNotify(0x1000, 0x1005, $parentPath, $null)
    }
    foreach ($folderPath in $plan.folders) {
        # Only remove empty package directories; unrelated files are retained.
        try { [IO.Directory]::Delete($folderPath, $false) } catch { }
    }
    if (-not $plan.uninstall) {
        [IO.Directory]::CreateDirectory($dataPath) | Out-Null
        [IO.File]::WriteAllText((Join-Path $dataPath '.skip-legacy-migration'), '1')
        Start-Process -FilePath $plan.restart[0] -WorkingDirectory $plan.cwd -WindowStyle Hidden
    }
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show("Maintenance could not finish: $($_.Exception.Message)", 'ModDiver Laboratory') | Out-Null
} finally {
    [ModDiverLoading]::Close()
    Remove-Item -LiteralPath $taskDir -Recurse -Force -ErrorAction SilentlyContinue
}
'''


def launch(plan):
    """Start an independent helper and verify it is ready before closing the UI."""
    folder = Path(tempfile.mkdtemp(prefix='moddiver-maintenance-'))
    try:
        if _inside(folder, plan['data']):
            raise ValueError('The temporary helper must be outside local app data.')
        if plan.get('install_root') and _inside(folder, plan['install_root']):
            raise ValueError('The temporary helper must be outside the installation folder.')
        if plan['bootstrap'] and not plan['uninstall']:
            shutil.copytree(plan['bootstrap'], folder/'bootstrap', symlinks=True)
        plan = dict(plan, pid=os.getpid())
        plan.setdefault('background', '#080808')
        (folder/'plan.json').write_text(json.dumps(plan), encoding='utf-8')
        if IS_WINDOWS:
            shutil.copy2(Path(__file__).with_name('loading_screen.cs'), folder/'loading_screen.cs')
            shutil.copy2(Path(__file__).with_name('icon.ico'), folder/'icon.ico')
            script = folder/'worker.ps1'
            script.write_text(WINDOWS_WORKER, encoding='utf-8-sig')
            command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script)]
            options = dict(creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            script = folder/'worker.py'
            shutil.copy2(__file__, script)
            shutil.copy2(Path(__file__).with_name('loading_ui.py'), folder/'loading_ui.py')
            shutil.copy2(Path(__file__).with_name('nav_icons.py'), folder/'nav_icons.py')
            shutil.copytree(Path(__file__).parent/'branding', folder/'branding')
            command = [sys.executable, str(script), str(folder)]
            options = dict(start_new_session=True)
        process = subprocess.Popen(command, cwd=str(folder), close_fds=True, **options)
        deadline = time.monotonic()+10
        while not (folder/'ready').exists():
            if process.poll() is not None or time.monotonic() > deadline:
                process.terminate()
                process.wait(timeout=5)
                raise RuntimeError('The maintenance helper could not start. No data was deleted.')
            time.sleep(.05)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise


def complete(plan, folder):
    """Linux worker, also exercised against isolated installations in tests."""
    data = Path(plan['data']).resolve()
    if data.name not in DATA_FOLDERS:
        raise ValueError('Invalid data path')
    baseline = Path(plan['baseline_data']) if plan.get('baseline_data') else None
    if baseline is not None:
        if (baseline.is_symlink() or baseline.resolve() != data.parent/baseline_name(data)):
            raise ValueError('Invalid baseline path')
    install = None
    if plan.get('install_root'):
        install = installation_root(plan['install_launcher'])
        if install != Path(plan['install_root']).resolve() or not plan['uninstall']:
            raise ValueError('Invalid installation path')
    if plan.get('remove_data', True) and data.exists():
        shutil.rmtree(data)
    if baseline is not None and baseline.exists():
        shutil.rmtree(baseline)
    for filename in plan['files']:
        Path(filename).unlink(missing_ok=True)
    if install and install.exists():
        shutil.rmtree(install)
    if not plan['uninstall']:
        data.mkdir(parents=True)
        (data/'.skip-legacy-migration').write_text('1')
        if plan['bootstrap']:
            shutil.copytree(Path(folder)/'bootstrap', plan['bootstrap'], symlinks=True)
        env = os.environ.copy()
        env.pop('YAO_FORGE_LEGACY_DATA', None)
        subprocess.Popen(plan['restart'], cwd=plan['cwd'], env=env, start_new_session=True)


def worker(folder):
    folder = Path(folder)
    plan = json.loads((folder/'plan.json').read_text(encoding='utf-8'))
    (folder/'ready').write_text('1')
    while True:
        try:
            os.kill(plan['pid'], 0)
        except ProcessLookupError:
            break
        time.sleep(.1)
    try:
        from loading_ui import run_splash
        run_splash(lambda: complete(plan, folder), plan.get('background', '#080808'),
                   plan.get('caption'), plan.get('caption_text'), plan.get('secondary', '#ffd400'))
    except Exception as exc:
        # Retain a visible error after the app has closed.
        import tkinter.messagebox
        tkinter.messagebox.showerror('ModDiver Laboratory', f'Maintenance could not finish:\n{exc}')
    finally:
        shutil.rmtree(folder, ignore_errors=True)


if __name__ == '__main__':
    worker(sys.argv[1])
