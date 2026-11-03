"""Build a ModDiver Laboratory release.

Run from the repository root (the folder that contains source/ and launcher/):

    python build_release.py                       # build everything into dist/
    python build_release.py --extract-runtime-from "ModDiver Laboratory.exe"
                                                  # one-off: recover runtime.zip from an existing EXE

Outputs in dist/ (attach all of these to the GitHub release):
    ModDiver-Laboratory-app-<version>.zip   app package; this is what in-app updates download
    ModDiver-Laboratory-Windows.zip         full download (EXE + docs). Keep attaching it to every
                                            release: installs older than 1.8.8 update by swapping the EXE.
    ModDiver-Laboratory-Linux.zip            source package with a Linux launch script and instructions

Only the latest release ZIPs remain in dist/. Checksums are saved beside this script
and inside the full platform ZIPs. Older app ZIPs are removed after a successful build.

Every version in play (yao_forge.py, app.json, the app package, the seed inside the EXE) is read back
and compared before the script reports success, so a stale build cannot be published by accident.
Needs: Python 3.10+ and the .NET Framework C# compiler (csc.exe, included with Windows).
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "source"
LAUNCHER_CS = ROOT / "launcher" / "launcher.cs"
MIN_LAUNCHER = 3  # keep equal to LauncherApi in launcher.cs; written into app.json

APP_EXCLUDE_DIRS = {"__pycache__", "tests", "_work"}
APP_EXCLUDE_NAMES = {"README.md", "LICENSES.md", "launcher.log"}
APP_EXCLUDE_SUFFIXES = {".pyc", ".pyo"}
# Keep app updates compatible with the updater already installed by older users.
COMPAT_MAX_PACKAGE_BYTES = 160 * 1024 * 1024
COMPAT_MAX_UNPACKED_BYTES = 600 * 1024 * 1024


def remote_repair_packages(source):
    manifest = source / 'builtin/gameplay/repair-data.json'
    if not manifest.exists():
        return set()
    data = json.loads(manifest.read_text(encoding='utf-8'))
    return {'builtin/gameplay/' + name for name in data['packages']}


# Limits enforced by installs older than 1.8.8 when they swap the EXE from the full ZIP.
# 2.1 includes repair baselines for offline reinstalls. Older automatic updaters
# need a full manual download to cross this packaging boundary.
LEGACY_MAX_ZIP = 1024 * 1024 * 1024
LEGACY_MAX_EXE = 512 * 1024 * 1024
LEGACY_EXE_PATH = "ModDiver Laboratory/ModDiver Laboratory.exe"
FULL_ZIP_NAME = "ModDiver-Laboratory-Windows.zip"
LINUX_ZIP_NAME = "ModDiver-Laboratory-Linux.zip"
APP_ZIP_TEMPLATE = "ModDiver-Laboratory-app-{version}.zip"


class BuildError(RuntimeError):
    pass


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_version(source=SOURCE):
    text = (source / "yao_forge.py").read_text(encoding="utf-8")
    match = re.search(r'^VERSION\s*=\s*"(\d+(?:\.\d+)*)"', text, re.MULTILINE)
    if not match:
        raise BuildError("Could not find VERSION = \"x.y.z\" in source/yao_forge.py")
    return match.group(1)


def write_guides(version):
    """Keep the downloaded guides consistent with the in-app About page."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('release_about', SOURCE / 'about_content.py')
    about = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(about)
    chinese_spec = importlib.util.spec_from_file_location('release_about_zh', SOURCE / 'about_zh.py')
    chinese = importlib.util.module_from_spec(chinese_spec)
    chinese_spec.loader.exec_module(chinese)
    (ROOT / 'README-zh-CN.md').write_text(f'# ModDiver Laboratory {version}\n\n' + '\n\n'.join(
        '## ' + title + '\n\n' + '\n\n'.join(paragraphs) for title, paragraphs in chinese.SECTIONS) + '\n', encoding='utf-8')
    intro = (f'# ModDiver Laboratory {version}\n\n'
             'On Windows, extract the full Windows ZIP and double-click **ModDiver Laboratory.exe**. '
             'Python is included. Keep your existing App Data folder when updating.\n\n'
             'On Linux, extract the Linux ZIP and follow **README-Linux.md**.\n\n'
             'See **INSTALLATION.md** in the full platform download for the OS list and numbered installation guides.\n\n'
             '[License](LICENSE) · [Licensing scope](LICENSING.md) · [Code signing policy](CODE-SIGNING-POLICY.md)\n\n')
    sections = '\n\n'.join('## ' + title + '\n\n' + '\n\n'.join(paragraphs)
                             for title, paragraphs in about.SECTIONS)
    guide = intro + sections + '\n'
    for path in (ROOT / 'README.md', SOURCE / 'README.md', ROOT / 'READ ME' / 'README.md'):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(guide, encoding='utf-8')
    linux_sections = [item for item in about.SECTIONS if item[0].startswith(
        ('LINUX', 'UPDATING', 'NATIVE EDITOR', 'GAME UPDATES'))]
    linux = f'# ModDiver Laboratory {version} for Linux\n\n'
    linux += ('The main app, mod library, merge/deploy/purge, Native Game Data Editor and Data Decoder '
              'run natively. SHODAN requires Windows. ModDiverEditor runs on Windows and on x86-64 Linux through Wine. '
              'See INSTALLATION.md for the OS list and numbered installation guides. '
              'See README.md for the full beginner guide and modder reference.\n\n')
    linux += '\n\n'.join('## ' + title + '\n\n' + '\n\n'.join(paragraphs)
                          for title, paragraphs in linux_sections) + '\n'
    (ROOT / 'README-Linux.md').write_text(linux, encoding='utf-8')
    (ROOT / 'READ-ME-FIRST.txt').write_text(
        f'ModDiver Laboratory {version}\n\n'
        'WINDOWS: Extract the ZIP into a normal folder. Double-click ModDiver Laboratory.exe. '
        'No separate Python installation is needed.\n\n'
        'UPGRADING: Close the old app, extract the new download and run the new EXE. '
        'Keep your ModDiverLab App Data folder; it holds your library and recovery files. '
        'Do not delete it to fix a startup problem.\n\n'
        'FIRST MOD: Read README.md or open About and Update in the app. '
        'Close the game before deploying or restoring mods.\n\n'
        'LINUX: Read README-Linux.md in the Linux download.\n', encoding='utf-8')


def _app_files(source):
    remote = remote_repair_packages(source)
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        if rel.as_posix() in remote:
            continue
        if any(part in APP_EXCLUDE_DIRS for part in rel.parts[:-1]):
            continue
        if rel.name in APP_EXCLUDE_NAMES or rel.suffix.lower() in APP_EXCLUDE_SUFFIXES:
            continue
        yield path, rel.as_posix()


def build_app_zip(source, out_path, version):
    """Pack source/ into the app package. The same file is the EXE's seed and the update payload."""
    meta = json.dumps({"version": version, "min_launcher": MIN_LAUNCHER}, indent=2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("app.json", meta)
        for path, rel in _app_files(source):
            archive.write(path, rel)
    check_app_zip(out_path, version)
    return out_path


def write_build_revision(source, version):
    """Refresh cached same-version installs whenever shipped app content changes."""
    digest = hashlib.sha256()
    for path, relative in _app_files(source):
        if relative == 'ui_revision.txt':
            continue
        digest.update(relative.encode('utf-8') + b'\0')
        digest.update(bytes.fromhex(sha256_file(path)))
    revision = version + '-build-' + digest.hexdigest()
    (source / 'ui_revision.txt').write_text(revision + '\n', encoding='ascii')
    return revision


def check_app_zip(path, version):
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        nexus = "nexus-build.json" in names
        if not nexus and path.stat().st_size > COMPAT_MAX_PACKAGE_BYTES:
            raise BuildError('App update exceeds the 160 MiB limit of older installed updaters.')
        if not nexus and sum(info.file_size for info in archive.infolist()) > COMPAT_MAX_UNPACKED_BYTES:
            raise BuildError('App update exceeds the 600 MiB unpacked limit of older installed updaters.')
        needed_files = ["app.json", "yao_forge.py", "core.py", "about_content.py", "log_events.py", "localization.py", "about_zh.py", "single_instance.py", "maintenance.py",
                       "schema_document.py", "schema_editor.py", "game_schema.py", "native_names.json",
                       "asset_editor.py", "asset_mods.py", "audio_workspace.py", "audio_backend.py", "studio_export.py", "studio_finish.py", "studio_guide.py", "creator_page.py", "native_asset_editor.py", "hellforge.py", "hellforge_legacy.py", "hellforge_stats.py", "hellforge_stats_ui.py", "vendor/audio_engine/tools/ffmpeg.exe", "vendor/audio_engine/tools/ffprobe.exe", "vendor/audio_engine/tools/vgmstream-cli.exe", "vendor/audio_engine/tools/wav2wem.exe", "gameplay_profiles.py", "decoder_ui.py", "repair_ui.py", "mod_repair.py", "build_archive.py", "repair_reference.py",
                       "icon.ico", "branding/icon_64.png", "branding/icon_256.png", "report_view.py",
                       *(f'branding/sidebar/{side}.png' for side in (212, 256, 265, 318, 384, 424, 512)),
                       *(f'bot_background/{side}.png' for side in (320, 480, 640, 800, 960, 1280, 1600, 1920)),
                       *(f'wordmark_background/{side}.png' for side in (320, 480, 640, 800, 960, 1280, 1600, 1920)),
                       'repair_data.py',
                       "builtin_updater.py",
                       *(f'library_background/{side}.png' for side in (256, 384, 512, 640, 768, 896, 1024))]
        if not nexus:
            needed_files.extend(("updater.py", "builtin/gameplay/repair-data.json",
                                 "builtin/gameplay/consistent_vaulting.zip",
                                 "builtin/gameplay/stratagem_bounce_removed.zip"))
        else:
            needed_files.extend(("updater.py", "nexus_mode.py", "builtin/gameplay/consistent_vaulting/profile.json",
                                "builtin/gameplay/stratagem_bounce_removed/profile.json",
                                "vendor/shodan/lua51.dll", "vendor/shodan/shodan_hash.dll",
                                "vendor/shodan/libsodium.dll", "vendor/shodan/app/gamedata.lua"))
            if any('repair-baseline-' in name or name.endswith('/repair-data.json') for name in names):
                raise BuildError(f"{path.name} must not contain historical repair datasets in the Nexus build")
            blocked = ('vendor/editor/', 'builtin/chef_loader/')
            if any(name.startswith(blocked) or name in {'chef_updater.py', 'shodan_updater.py', 'moddiver_editor.py'}
                   or name.lower().endswith(('.zip', '.7z', '.rar')) for name in names):
                raise BuildError(f"{path.name} contains General-only content or a nested archive")
        for needed in needed_files:
            if needed not in names:
                raise BuildError(f"{path.name} is missing {needed}")
        for name in names:
            if '/' not in name and name.endswith('.py'):
                compile(archive.read(name), name, 'exec')
        declared = json.loads(archive.read("app.json"))["version"]
        match = re.search(r'^VERSION\s*=\s*"([^"]+)"', archive.read("yao_forge.py").decode("utf-8"), re.MULTILINE)
        inside = match.group(1) if match else None
    if declared != version or inside != version:
        raise BuildError(f"{path.name}: app.json says {declared}, yao_forge.py says {inside}, expected {version}")


def _resource_candidates(data):
    """Yield (offset, length) for length-prefixed zip blobs, which is how .NET stores embedded files."""
    marker = b"PK\x03\x04"
    pos = data.find(marker)
    while pos >= 4:
        length = struct.unpack("<I", data[pos - 4:pos])[0]
        if 1024 * 1024 <= length <= len(data) - pos:
            yield pos, length
        pos = data.find(marker, pos + 4)


def extract_runtime(exe_path, out_path):
    data = Path(exe_path).read_bytes()
    for pos, length in _resource_candidates(data):
        blob = data[pos:pos + length]
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                if "pythonw.exe" in archive.namelist():
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(blob)
                    return out_path
        except zipfile.BadZipFile:
            continue
    raise BuildError(f"No embedded Python runtime found in {exe_path}")


def build_runtime_zip(runtime, out_path):
    """Drop the unused NumPy dependency even when reusing an older runtime ZIP."""
    with zipfile.ZipFile(runtime) as source, zipfile.ZipFile(
            out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as target:
        for info in source.infolist():
            parts = info.filename.replace("\\", "/").split("/")
            if len(parts) >= 3 and parts[:2] == ["Lib", "site-packages"]:
                package = parts[2].casefold()
                if package in {"numpy", "numpy.libs"} or (
                        package.startswith("numpy-") and package.endswith(".dist-info")):
                    continue
            target.writestr(info, source.read(info))
    return out_path


def embedded_seed(exe_path):
    """Return (seed zip bytes, app.version text) read back out of a compiled launcher EXE."""
    data = Path(exe_path).read_bytes()
    seed = None
    for pos, length in _resource_candidates(data):
        try:
            with zipfile.ZipFile(io.BytesIO(data[pos:pos + length])) as archive:
                if "app.json" in archive.namelist() and "yao_forge.py" in archive.namelist():
                    seed = data[pos:pos + length]
                    break
        except zipfile.BadZipFile:
            continue
    return seed, data


def verify_exe(exe_path, version):
    seed, data = embedded_seed(exe_path)
    if seed is None:
        raise BuildError(f"{exe_path}: no embedded app package found (is this a pre-1.8.8 EXE?)")
    with zipfile.ZipFile(io.BytesIO(seed)) as archive:
        declared = json.loads(archive.read("app.json"))["version"]
        match = re.search(r'^VERSION\s*=\s*"([^"]+)"', archive.read("yao_forge.py").decode("utf-8"), re.MULTILINE)
    inside = match.group(1) if match else None
    label = version.encode("ascii")
    if not (struct.pack("<I", len(label)) + label) in data:
        raise BuildError(f"{exe_path}: embedded app.version resource is not {version}")
    if declared != version or inside != version:
        raise BuildError(f"{exe_path} embeds app {declared}/{inside}, expected {version}. Do not publish it.")


def find_csc(explicit=None):
    candidates = [explicit] if explicit else []
    found = shutil.which("csc")
    if found:
        candidates.append(found)
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for arch in ("Framework64", "Framework"):
        candidates.append(str(Path(windir) / "Microsoft.NET" / arch / "v4.0.30319" / "csc.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise BuildError("csc.exe not found. Pass --csc <path> (it ships with the .NET Framework under C:\\Windows\\Microsoft.NET).")


def compile_launcher(csc, exe_out, app_zip, runtime_zip, version, work):
    # Interpreter branding files are compiler inputs, not standalone applications.
    with tempfile.TemporaryDirectory(prefix='launcher-', dir=work) as scratch:
        return _compile_launcher(csc, exe_out, app_zip, runtime_zip, version, Path(scratch))


def _compile_launcher(csc, exe_out, app_zip, runtime_zip, version, work):
    from brand_runtime import brand_runtime
    branded_python = brand_runtime(runtime_zip, work, csc, SOURCE / 'icon.ico', version)
    exe_out.parent.mkdir(parents=True, exist_ok=True)
    version_file = work / "app.version"
    version_file.write_text(version, encoding="ascii")
    # Keep Authenticode metadata tied to the same version as the embedded seed.
    # These attributes are generated here so launcher.cs has no stale version.
    parts = version.split('.')
    if not re.fullmatch(r'\d+(?:\.\d+){0,3}', version) or any(int(p) > 65534 for p in parts):
        raise BuildError('Launcher version must contain 1-4 numeric parts in 0..65534.')
    file_version = '.'.join(parts + ['0'] * (4 - len(parts)))
    metadata = work / 'launcher_version.cs'
    metadata.write_text(
        'using System.Reflection;\n'
        f'[assembly: AssemblyVersion("{file_version}")]\n'
        f'[assembly: AssemblyFileVersion("{file_version}")]\n'
        f'[assembly: AssemblyInformationalVersion("{version}")]\n', encoding='ascii')
    command = [
        csc, "/nologo", "/target:winexe", "/optimize+", f"/out:{exe_out}",
        "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll", "/r:System.IO.Compression.dll", "/r:System.IO.Compression.FileSystem.dll",
        f"/resource:{app_zip},app.zip", f"/resource:{runtime_zip},runtime.zip",
        f"/resource:{version_file},app.version",
        f"/resource:{SOURCE / 'ui_revision.txt'},ui.revision",
        f"/resource:{branded_python},moddiver-python.exe",
        f"/resource:{SOURCE / 'icon.ico'},moddiver-icon.ico",
    ]
    if (SOURCE / 'nexus-build.json').is_file():
        command.append('/define:NEXUS_BUILD')
    icon = SOURCE / "icon.ico"
    if icon.is_file():
        command.append(f"/win32icon:{icon}")
    command.extend([str(LAUNCHER_CS), str(SOURCE / "loading_screen.cs"), str(metadata)])
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise BuildError("csc failed:\n" + result.stdout + result.stderr)
    return exe_out


def assemble_full_zip(out_path, exe_path, version, *, docs_root=None, nexus=False):
    """The full download. Layout must stay `ModDiver Laboratory/ModDiver Laboratory.exe` for old updaters."""
    prefix = "ModDiver Laboratory/"
    docs_root = Path(docs_root) if docs_root is not None else ROOT
    checksums = []
    owned_files = []

    def add(archive, name, data, track=True):
        archive.writestr(prefix + name, data)
        owned_files.append(name)
        if track:
            checksums.append(f"{hashlib.sha256(data).hexdigest()}  {name}")

    if out_path.exists():
        out_path.unlink()
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        exe_name = "ModDiver Laboratory.exe"
        exe_data = Path(exe_path).read_bytes()
        exe_info = zipfile.ZipInfo(prefix + exe_name)
        exe_info.compress_type = zipfile.ZIP_STORED
        archive.writestr(exe_info, exe_data)
        owned_files.append(exe_name)
        checksums.append(f"{hashlib.sha256(exe_data).hexdigest()}  {exe_name}")
        docs = ("NEXUS-README.md", "NEXUS-LICENSES.md", "AUDIO-STUDIO.md", "HELLFORGE.md", "NATIVE-EDITOR.md", "NATIVE-EDITOR-COVERAGE.md", "NATIVE-EDITOR-COVERAGE.json") if nexus else (
            f"RELEASE-{version}.md", "INSTALLATION.md", "READ-ME-FIRST.txt", "README.md", "README-zh-CN.md", "HELLFORGE.md", "AUDIO-STUDIO.md", "LICENSES.md", "DATA-DECODER.md", "NATIVE-EDITOR.md", "NATIVE-EDITOR-COVERAGE.md", "NATIVE-EDITOR-COVERAGE.json")
        docs = tuple(docs) + tuple(name for name in (
            'LICENSE', 'LICENSING.md', 'CODE-SIGNING-POLICY.md', 'PRIVACY.md')
            if (docs_root / name).is_file())
        for doc in docs:
            path = docs_root / doc
            if path.is_file():
                text = path.read_bytes()
                if doc == "READ-ME-FIRST.txt":
                    text = text.replace(b"{{VERSION}}", version.encode("ascii"))
                add(archive, doc, text)
        # The EXE already embeds the app, runtime and offline baseline. Shipping
        # source/ here duplicates hundreds of MiB; Linux still needs its source.
        add(archive, 'uninstall-manifest.json', json.dumps({
            'application': 'ModDiver Laboratory', 'files': owned_files + ['SHA256SUMS.txt', 'uninstall-manifest.json']
        }, indent=2).encode('utf-8'))
        archive.writestr(prefix + "SHA256SUMS.txt", "\r\n".join(checksums) + "\r\n")
    size = out_path.stat().st_size
    exe_size = Path(exe_path).stat().st_size
    if size > LEGACY_MAX_ZIP or not (1024 * 1024 <= exe_size <= LEGACY_MAX_EXE):
        raise BuildError(f"Full ZIP ({size:,} bytes) or EXE ({exe_size:,} bytes) exceeds the 2.1 package limits.")
    with zipfile.ZipFile(out_path) as archive:
        archive.getinfo(LEGACY_EXE_PATH)  # raises KeyError if the layout drifted
        bad = archive.testzip()
        if bad:
            raise BuildError(f"Windows package failed ZIP CRC verification: {bad}")
    return out_path


def assemble_linux_zip(out_path, version, *, source=None, docs_root=None, nexus=False):
    """Create the source distribution for Linux systems with Python/Tk/LuaJIT installed."""
    prefix = "ModDiver Laboratory/"
    source = Path(source) if source is not None else SOURCE
    docs_root = Path(docs_root) if docs_root is not None else ROOT
    checksums = []
    if out_path.exists():
        out_path.unlink()
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        docs = ("NEXUS-README.md", "NEXUS-LICENSES.md", "AUDIO-STUDIO.md", "HELLFORGE.md", "NATIVE-EDITOR.md", "NATIVE-EDITOR-COVERAGE.md", "NATIVE-EDITOR-COVERAGE.json", "run-linux.sh", "install-linux.sh", "Install ModDiver.desktop") if nexus else (
            f"RELEASE-{version}.md", "INSTALLATION.md", "README.md", "README-Linux.md", "README-zh-CN.md", "HELLFORGE.md", "AUDIO-STUDIO.md", "run-linux.sh", "install-linux.sh", "install-linux-distrobox.sh", "Install ModDiver.desktop", "LICENSES.md", "DATA-DECODER.md", "NATIVE-EDITOR.md", "NATIVE-EDITOR-COVERAGE.md", "NATIVE-EDITOR-COVERAGE.json")
        docs = tuple(docs) + tuple(name for name in (
            'LICENSE', 'LICENSING.md', 'CODE-SIGNING-POLICY.md', 'PRIVACY.md')
            if (docs_root / name).is_file())
        for rel_name in docs:
            path = docs_root / rel_name
            if not path.is_file():
                raise BuildError(f"Linux package is missing {rel_name}")
            data = path.read_bytes()
            if rel_name.endswith((".sh", ".desktop")):
                data = data.replace(b"\r\n", b"\n")
            info = zipfile.ZipInfo(prefix + rel_name)
            info.compress_type = zipfile.ZIP_DEFLATED
            if rel_name.endswith((".sh", ".desktop")):
                info.external_attr = (0o100755 << 16)
            archive.writestr(info, data)
            checksums.append(f"{hashlib.sha256(data).hexdigest()}  {rel_name}")
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(source)
            if not nexus and rel.as_posix() in remote_repair_packages(source):
                continue
            if ("__pycache__" in rel.parts or "_work" in rel.parts or rel.suffix.lower() in APP_EXCLUDE_SUFFIXES
                    or rel.suffix.lower() in {".dll", ".exe", ".ico"} or rel.name == "launcher.log"):
                continue
            data = path.read_bytes()
            name = "source/" + rel.as_posix()
            archive.writestr(prefix + name, data)
            checksums.append(f"{hashlib.sha256(data).hexdigest()}  {name}")
        archive.writestr(prefix + "SHA256SUMS.txt", "\r\n".join(checksums) + "\r\n")
    with zipfile.ZipFile(out_path) as archive:
        bad = archive.testzip()
        if bad:
            raise BuildError(f"Linux package failed ZIP CRC verification: {bad}")
        archive.getinfo(prefix + "run-linux.sh")
        archive.getinfo(prefix + "source/yao_forge.py")
        script = archive.read(prefix + "source/yao_forge.py").decode("utf-8")
        match = re.search(r'^VERSION\s*=\s*"([^"]+)"', script, re.MULTILINE)
        if not match or match.group(1) != version:
            raise BuildError("Linux package version does not match the current app source")
        if any(name.lower().endswith((".dll", ".exe")) for name in archive.namelist()):
            raise BuildError("Linux package unexpectedly contains Windows binaries")
        if nexus and any(name.lower().endswith((".zip", ".7z", ".rar")) for name in archive.namelist()):
            raise BuildError("Nexus Linux package contains a nested archive")
    return out_path


def prepare_repair_release(destination):
    """Stage pinned repair-data assets for a separate prerelease; never upload here."""
    sys.path.insert(0, str(SOURCE))
    import repair_data
    folder = SOURCE / 'builtin/gameplay'
    data = repair_data.manifest(folder)
    if not data:
        raise BuildError('Missing repair-data manifest.')
    destination = Path(destination) / data['tag']
    destination.mkdir(parents=True, exist_ok=True)
    sums = []
    for name, entry in data['packages'].items():
        source = folder / name
        if not repair_data._verified(source, entry):
            raise BuildError('Repair-data source does not match its pinned manifest: ' + name)
        shutil.copy2(source, destination / name)
        sums.append(f"{entry['sha256']}  {name}\n")
    (destination / 'SHA256SUMS.txt').write_text(''.join(sums), encoding='ascii')
    (destination / 'RELEASE-NOTES.md').write_text(
        '# Repair data for ModDiver Laboratory\n\n'
        'Create a GitHub prerelease in Yaromyr1/ModDiver-Lab with tag **' + data['tag'] + '**. '
        'Enable "Set as a pre-release" so app update checks continue to find the stable app release. '
        'Publish this repair-data prerelease before publishing the app update.\n\n'
        'Upload the repair-baseline ZIPs and SHA256SUMS.txt from this folder. Keep the asset '
        'names unchanged. The app pins each ZIP checksum and downloads it only when repair '
        'is requested. Downloaded ZIPs and extracted data are temporary and deleted after the repair job. '
        'A new repair job downloads the data again. For future repair data, create a new tag and update repair-data.json '
        'in a new app release; replacing the bytes under this tag will fail verification.\n', encoding='utf-8')
    return destination


def _nexus_source_ignore(directory, names):
    directory = Path(directory)
    try:
        relative = directory.relative_to(SOURCE).parts
    except ValueError:
        relative = ()
    ignored = {name for name in names if name in {"__pycache__", "tests", "_work"}
               or name.endswith((".pyc", ".pyo"))}
    if relative == ("vendor",):
        ignored.add("editor")
    if relative == ("vendor", "shodan"):
        # Nexus excludes the SHODAN editor application but retains the minimal
        # offline hash-correction runtime used by Data Bot and the decoder.
        ignored.update(name for name in names
                       if name not in {"app", "libsodium.dll", "lua51.dll", "shodan_hash.dll"})
    if relative == ("builtin",):
        ignored.add("chef_loader")
    if relative == ():
        ignored.update({"chef_updater.py", "shodan_updater.py",
                        "moddiver_editor.py"})
    return ignored


def _extract_release_archive(archive_path, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            parts = [part for part in name.split("/") if part]
            if not parts or name.startswith("/") or any(part in (".", "..") for part in parts):
                raise BuildError(f"Unsafe path in bundled data archive: {info.filename}")
            target = destination.joinpath(*parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)


def _directory_digest(folder):
    digest = hashlib.sha256()
    size = 0
    folder = Path(folder)
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and not p.is_symlink()):
        relative = path.relative_to(folder).as_posix().encode("utf-8")
        data = path.read_bytes()
        size += len(data)
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return size, digest.hexdigest()


def prepare_nexus_source(stage):
    """Create a source tree without network updater modules, Chef, or editor bundles."""
    stage = Path(stage)
    shutil.copytree(SOURCE, stage, ignore=_nexus_source_ignore)
    (stage / "nexus-build.json").write_text(
        json.dumps({"variant": "nexus", "version": read_version(SOURCE)}, indent=2), encoding="utf-8")
    guide = stage / 'HELLFORGE.md'
    if guide.is_file():
        guide.write_text(guide.read_text(encoding='utf-8').replace(
            '2. Gameplay: open the Native Data Editor, ModDiverEditor or SHODAN button in HellForge mode; these open **HellForge Stats Editor**. Alternatively choose its dedicated button in Mod Creator.',
            '2. Gameplay: choose **Open HellForge Stats Editor** in Mod Creator. The Nexus build does not bundle ModDiverEditor or SHODAN.'), encoding='utf-8')
    gameplay = stage / "builtin" / "gameplay"
    for archive in sorted(gameplay.glob("repair-baseline-*.zip")):
        archive.unlink()
    for historical in gameplay.glob("repair-baseline-*"):
        if historical.is_dir():
            shutil.rmtree(historical)
        else:
            historical.unlink()
    (gameplay / "repair-data.json").unlink(missing_ok=True)
    for archive in sorted(gameplay.glob("*.zip")):
        _extract_release_archive(archive, gameplay / archive.stem)
        archive.unlink()
    if any(path.suffix.lower() in {".zip", ".7z", ".rar"} for path in stage.rglob("*")):
        raise BuildError("Nexus source still contains a nested archive after staging.")
    (stage / "repair_data.py").write_text(
        '''"""Offline Nexus helpers; repair references come from captured Steam stock."""
import hashlib
from pathlib import Path

def directory_digest(folder):
    digest = hashlib.sha256()
    total = 0
    folder = Path(folder)
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and not p.is_symlink()):
        relative = path.relative_to(folder).as_posix().encode("utf-8")
        data = path.read_bytes()
        total += len(data)
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return total, digest.hexdigest()

def packages(folder, cache=None, *, download=False, progress=lambda message: None):
    return []

def prefetch(folder, destination, *, progress=lambda message: None):
    return packages(folder, destination)
''', encoding="utf-8")
    (stage / "updater.py").write_text(
        '''"""Offline version and pointer helpers required by the Linux bootstrap."""
import os
import re
import uuid
from pathlib import Path

POINTER_NAME = "current.txt"
OK_MARKER = ".app-ok"
_SAFE_FOLDER = re.compile(r"\\d+(?:\\.\\d+)*(?:-rollback-[0-9a-f]{8})?\\Z")

class UpdateError(RuntimeError):
    pass

def _parts(value):
    text = str(value or "").split("-rollback-", 1)[0]
    if not re.fullmatch(r"[vV]?\\d+(?:\\.\\d+)*", text):
        raise UpdateError("Unrecognized version: " + repr(value))
    return tuple(int(part) for part in text.lstrip("vV").split("."))

def canonical_version(value):
    return ".".join(str(part) for part in _parts(value))

def _is_newer(candidate, current):
    left, right = _parts(candidate), _parts(current)
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) > right + (0,) * (width - len(right))

def read_pointer(app_root):
    try:
        lines = (Path(app_root) / POINTER_NAME).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None, None
    found = [line.strip() for line in lines if _SAFE_FOLDER.fullmatch(line.strip())]
    return (found[0] if found else None), (found[1] if len(found) > 1 else None)

def _write_pointer(app_root, current, previous):
    app_root = Path(app_root)
    target = app_root / POINTER_NAME
    temp = app_root / ("." + POINTER_NAME + "." + uuid.uuid4().hex[:8] + ".tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\\n") as handle:
            handle.write(current + "\\n" + (previous + "\\n" if previous else ""))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp), str(target))
    finally:
        try:
            temp.unlink()
        except OSError:
            pass
''', encoding="utf-8")
    return stage


def write_nexus_docs(folder, version):
    folder = Path(folder)
    for name in ('NATIVE-EDITOR.md','NATIVE-EDITOR-COVERAGE.md','NATIVE-EDITOR-COVERAGE.json'):
        shutil.copy2(ROOT / name, folder / name)
    for name in ('AUDIO-STUDIO.md', 'HELLFORGE.md'):
        shutil.copy2(SOURCE / name, folder / name)
    hellforge = folder / 'HELLFORGE.md'
    text = hellforge.read_text(encoding='utf-8')
    text = text.replace('2. Gameplay: open the Native Data Editor, ModDiverEditor or SHODAN button in HellForge mode; these open **HellForge Stats Editor**. Alternatively choose its dedicated button in Mod Creator.',
                        '2. Gameplay: choose **Open HellForge Stats Editor** in Mod Creator. The Nexus build does not bundle ModDiverEditor or SHODAN.')
    hellforge.write_text(text, encoding='utf-8')
    for name in ('LICENSE', 'LICENSING.md', 'CODE-SIGNING-POLICY.md', 'PRIVACY.md'):
        if (ROOT / name).is_file():
            shutil.copy2(ROOT / name, Path(folder) / name)
    folder = Path(folder)
    for name in ("run-linux.sh", "install-linux.sh", "Install ModDiver.desktop"):
        shutil.copy2(ROOT / name, folder / name)
    (folder / "NEXUS-README.md").write_text(
        f"# ModDiver Laboratory {version} — Nexus build\n\n"
        "[License](LICENSE) · [Licensing scope](LICENSING.md) · [Code signing policy](CODE-SIGNING-POLICY.md)\n\n"
        "This Windows and Linux build includes the Native Game Data Editor, Data Decoder and Audio "
        "Studio. Data Bot builds its repair reference from the user's Steam-verified game files and "
        "uses only a clean capture matching the installed build. The package contains no historical "
        "game-data repair datasets and does not download them. Source and third-party notices: "
        "https://github.com/Yaromyr1/ModDiver-Lab-NEXUS.\n\n"
        "## Studio\n\nThe expanded handbook and shortcuts (F1), themed Finish & export workflow "
        "(Ctrl+E), and combined audio/visual manager-ready ZIP export are included. Read AUDIO-STUDIO.md. "
        "Export creates a mod package from your own projects; it does not install one automatically.\n\n"
        "## Separate from General\n\nNexus uses its own ModDiverLabNexus app-data/cache folder, "
        "Nexus-named shortcuts, and ModDiver Lab Nexus Baseline Data for local repair references. "
        "It never automatically imports General settings, caches or repair datasets. Previous shared "
        "data is left untouched; use Export/Import Mod Library to transfer packages deliberately. "
        "Keep Nexus and General downloads in separate extracted folders.\n\n"
        "## Windows\n\nExtract the complete Windows ZIP to a normal folder and start "
        "**ModDiver Laboratory.exe**. Python is bundled. Keep the application folder together. User "
        "settings, mod library, clean-stock snapshots and recovery data are stored separately under your "
        "user profile.\n\n"
        "## Linux\n\nExtract the Linux ZIP into your home folder. Run **Install ModDiver.desktop**, or "
        "open a terminal in the extracted folder and run 'sh install-linux.sh'. The installer uses your "
        "distribution package manager for required system libraries; it does not use sudo to run the app.\n\n"
        "## Disabled while Nexus reviews this build\n\n"
        "App update controls are disabled. The app displays:\n\n"
        "> Awaiting Nexus Mods confirmation on File Submission Guidelines and Terms of Service. This feature is disabled until further notice.\n\n"
        "Chef Shared Loader, SHODAN Stat Editor and ModDiverEditor are not included. "
        "Import your own Chef Shared Loader ZIP, 7Z or folder through Mod Library; "
        "it is recognized automatically and placed in Loaders. Imported Chef entries remain "
        "in the library after restarting.\n",
        encoding="utf-8")
    notices = (ROOT / "LICENSES.md").read_text(encoding="utf-8")
    start = notices.index("- **SHODAN Stat Editor application**")
    end = notices.index("- **YAO DATA LOADER**", start)
    notices = notices[:start] + notices[end:]
    notices = ("# Third-party notices for the Nexus build\n\n" + notices.split("\n", 1)[1]
               + "\n\nChef Shared Loader, SHODAN Stat Editor and ModDiverEditor are omitted from this build.\n"
               + "Source code and third-party notices: https://github.com/Yaromyr1/ModDiver-Lab-NEXUS\n")
    (folder / "NEXUS-LICENSES.md").write_text(notices, encoding="utf-8")


def build_nexus_release(runtime, out, destination, csc=None):
    """Create manual-upload Windows and Linux packages, without a separate updater ZIP."""
    global SOURCE
    original_source = SOURCE
    work = ROOT / "build"
    work.mkdir(exist_ok=True)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    version = read_version(original_source)
    with tempfile.TemporaryDirectory(prefix="moddiver-nexus-build-", dir=out) as temporary:
        temp_root = Path(temporary)
        stage = prepare_nexus_source(temp_root / "source")
        docs = temp_root / "docs"
        docs.mkdir()
        try:
            SOURCE = stage
            write_nexus_docs(docs, version)
            write_build_revision(stage, version)
            runtime_zip = build_runtime_zip(runtime, temp_root / "runtime.zip")
            app_zip = build_app_zip(stage, temp_root / "app.zip", version)
            exe = compile_launcher(find_csc(csc), temp_root / "ModDiver Laboratory Nexus.exe", app_zip,
                                   runtime_zip, version, work)
            verify_exe(exe, version)
            windows = assemble_full_zip(temp_root / "ModDiver-Laboratory-Nexus-Windows.zip", exe, version,
                                        docs_root=docs, nexus=True)
            linux = assemble_linux_zip(temp_root / "ModDiver-Laboratory-Nexus-Linux.zip", version,
                                       source=stage, docs_root=docs, nexus=True)
            packages = publish_release((windows, linux), destination)
            (Path(destination) / 'SHA256SUMS.txt').write_text(''.join(
                f'{sha256_file(package)}  {package.name}\n' for package in packages), encoding='ascii')
            print("Nexus build artifacts (upload these two platform ZIPs):")
            for package in packages:
                print(f"  {package.name}  {package.stat().st_size:,} bytes  sha256 {sha256_file(package)}")
            return 0
        finally:
            SOURCE = original_source


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(ROOT / "dist"), help="output folder (default: dist)")
    parser.add_argument("--runtime", default=str(ROOT / "build" / "runtime.zip"), help="Python runtime zip to embed")
    parser.add_argument("--csc", help="path to csc.exe if it is not found automatically")
    parser.add_argument("--nexus", action="store_true", help="build Nexus-only Windows and Linux packages")
    parser.add_argument("--extract-runtime-from", metavar="EXE", help="write build/runtime.zip from an existing EXE, then exit")
    args = parser.parse_args(argv)

    runtime = Path(args.runtime)
    if args.extract_runtime_from:
        extract_runtime(args.extract_runtime_from, runtime)
        print(f"runtime written to {runtime} ({runtime.stat().st_size:,} bytes)")
        return 0
    if not runtime.is_file():
        raise BuildError(f"{runtime} not found. Run once with --extract-runtime-from \"<an existing ModDiver Laboratory.exe>\".")

    if args.nexus:
        return build_nexus_release(runtime, args.out, Path(args.out) / "nexus", args.csc)

    version = read_version()
    prepare_repair_release(ROOT / "repair-data-release")
    write_guides(version)
    with tempfile.TemporaryDirectory(prefix='moddiver-release-') as staging:
        return build_release(version, runtime, Path(staging), Path(args.out), args.csc)


def build_release(version, runtime, out, destination, csc=None):
    """Build and verify in staging before replacing the previous distribution."""
    work = ROOT / "build"
    work.mkdir(exist_ok=True)
    print(f"Building ModDiver Laboratory {version}")
    print(f"  build revision {write_build_revision(SOURCE, version)}")

    runtime = build_runtime_zip(runtime, out / "runtime.zip")
    print(f"  Python runtime {runtime.stat().st_size:,} bytes (NumPy excluded)")

    app_zip = build_app_zip(SOURCE, out / APP_ZIP_TEMPLATE.format(version=version), version)
    print(f"  app package    {app_zip.name}  {app_zip.stat().st_size:,} bytes")

    exe = compile_launcher(find_csc(csc), work / "ModDiver Laboratory.exe", app_zip, runtime, version, work)
    verify_exe(exe, version)
    print(f"  launcher EXE   verified: embeds app {version}")

    full = assemble_full_zip(out / FULL_ZIP_NAME, exe, version)
    print(f"  full download  {full.name}  {full.stat().st_size:,} bytes")

    linux = assemble_linux_zip(out / LINUX_ZIP_NAME, version)
    print(f"  Linux package  {linux.name}  {linux.stat().st_size:,} bytes")

    # The loose EXE is what users often double-click while testing this folder.
    # Refresh it only after every release artifact has built successfully.
    shutil.copy2(exe, ROOT / 'ModDiver Laboratory.exe')
    verify_exe(ROOT / 'ModDiver Laboratory.exe', version)
    app_zip, full, linux = publish_release((app_zip, full, linux), destination)
    (ROOT / 'SHA256SUMS.txt').write_text(
        f"{sha256_file(exe)}  ModDiver Laboratory.exe\n" + ''.join(
            f'{sha256_file(path)}  {os.path.relpath(path, ROOT).replace(chr(92), chr(47))}\n'
            for path in (app_zip, full, linux)), encoding='ascii')

    print("\nAttach all three files to the GitHub release tagged v" + version + ":")
    for path in (app_zip, full, linux):
        print(f"  {path.name}\n    sha256 {sha256_file(path)}")
    exe.unlink()  # The verified public EXE and Windows ZIP already contain this copy.
    return 0


def publish_release(packages, destination):
    """Keep only the current release ZIPs; leave unrelated user files alone."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    published = []
    for package in packages:
        target = destination / package.name
        shutil.copy2(package, target)
        published.append(target)
    keep = {p.name for p in published}
    for path in destination.iterdir():
        if path.name in keep or not path.is_file():
            continue
        if re.fullmatch(r'ModDiver-Laboratory-app-\d+(?:\.\d+)*\.zip', path.name) or path.name == 'SHA256SUMS.txt':
            path.unlink()
    return tuple(published)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BuildError as exc:
        print("BUILD FAILED: " + str(exc), file=sys.stderr)
        sys.exit(1)
