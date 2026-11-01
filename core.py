"""ModDiver Laboratory core: mod parsing, merge, deploy/purge, YAO pack export."""
import ctypes
import ctypes.util
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from functools import lru_cache
from pathlib import Path

from merge_engine import (MergeSafetyError, atomic_write, diff_runs as _diff_runs,
                          plan_merge_with_runs, validate_sealed_input,
                          apply_file_transaction, recover_file_transaction)

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent

def _load_sodium():
    bundled = ROOT / "vendor" / "shodan" / "libsodium.dll"
    candidates = [str(bundled)] if os.name == "nt" else [
        ctypes.util.find_library("sodium"), "libsodium.so.23", "libsodium.so"]
    for candidate in filter(None, candidates):
        try:
            return ctypes.CDLL(candidate)
        except OSError:
            continue
    raise RuntimeError("libsodium is required. On Linux install the runtime package (for example: sudo apt install libsodium23).")


_sodium = _load_sodium()
_sodium.sodium_init()
_sodium.crypto_box_seal_open.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_ulonglong,
                                         ctypes.c_char_p, ctypes.c_char_p]
_sodium.crypto_box_seal_open.restype = ctypes.c_int
_sodium.crypto_box_seal.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_ulonglong, ctypes.c_char_p]
_sodium.crypto_box_seal.restype = ctypes.c_int

PK = bytes.fromhex("2dc9aa7c30e6eed5f7fd0e0e95c7287299b126f79520cc41de750982ee7ff50c")
SK = bytes.fromhex("a0296b81310b58f013d8a9b343a1c292008003dfd9ab15fcf351543048b49b64")


def _copy_missing_tree(source, destination):
    """Merge legacy data into its new home without replacing files created there."""
    source, destination = Path(source), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for current, dirs, files in os.walk(source):
        current = Path(current)
        relative = current.relative_to(source)
        target_dir = destination / relative
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            original = current / name
            target = target_dir / name
            if not target.exists() and not original.is_symlink():
                shutil.copy2(original, target)

def _pick_data():
    env = os.environ.get("YAO_FORGE_DATA")
    if env:
        path = Path(env)
        path.mkdir(parents=True, exist_ok=True)
        legacy_env = os.environ.get("YAO_FORGE_LEGACY_DATA")
        if legacy_env and not (path / '.skip-legacy-migration').exists():
            legacy = Path(legacy_env)
            if legacy.is_dir() and legacy.resolve() != path.resolve():
                try:
                    for item in legacy.iterdir():
                        dest = path / item.name
                        if item.is_dir() and not item.is_symlink():
                            _copy_missing_tree(item, dest)
                        elif not dest.exists() and not item.is_symlink():
                            shutil.copy2(item, dest)
                except Exception:
                    pass
        return path
    if os.name == "nt":
        data_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    else:
        data_root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    primary = data_root / "ModDiverLab"
    legacy = primary.parent / "YAOModForge"
    try:
        if legacy.is_dir() and not (primary / '.skip-legacy-migration').exists():
            _copy_missing_tree(legacy, primary)
    except Exception:
        pass
    try:
        primary.mkdir(parents=True, exist_ok=True)
        probe = primary / ".write_test"
        probe.write_bytes(b"1")
        probe.unlink()
        return primary
    except Exception:
        fallback = ROOT / "data"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


APP_DATA = _pick_data()
CONFIG = APP_DATA / "config.json"
STOCK = APP_DATA / "stock"
BACKUPS = APP_DATA / "backups"
DEPLOYED = APP_DATA / "deployed.json"
MODS_DIR = APP_DATA / "mods"
IMPORTED_MODS_DIR = MODS_DIR / "imported"


def _inside_mod_library(path):
    try:
        Path(path).resolve().relative_to(MODS_DIR.resolve())
        return True
    except (ValueError, OSError):
        return False


def _unique_library_path(name, is_dir):
    base = Path(name).name or "mod"
    candidate = IMPORTED_MODS_DIR / base
    stem, suffix = (Path(base).stem, Path(base).suffix) if not is_dir else (base, "")
    index = 2
    while candidate.exists():
        candidate = IMPORTED_MODS_DIR / f"{stem} ({index}){suffix}"
        index += 1
    return candidate


def add_to_library(path):
    """Copy an imported archive or folder into the user's managed Mods directory."""
    source = Path(path).expanduser().resolve()
    if _inside_mod_library(source):
        return source
    if not source.exists() or not (source.is_file() or source.is_dir()):
        raise FileNotFoundError(f"mod source does not exist: {source}")
    IMPORTED_MODS_DIR.mkdir(parents=True, exist_ok=True)
    destination = _unique_library_path(source.name, source.is_dir())
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)
    return destination


def migrate_mod_sources(cfg, log=print):
    """Copy configured external mod sources into the managed library, keeping originals."""
    copied = 0
    errors = []
    for mod in cfg.get("mods", []):
        original = mod.get("path")
        if not original:
            continue
        source = Path(original).expanduser()
        if _inside_mod_library(source):
            if source.exists():
                continue
            # If the user moved a managed item into a subfolder, follow it when
            # its original name still identifies exactly one item.
            matches = [p for p in MODS_DIR.rglob(source.name) if p.name == source.name]
            if len(matches) == 1:
                mod["path"] = str(matches[0])
                copied += 1
            else:
                errors.append((str(original), "managed mod file is missing or has an ambiguous moved name"))
                log(f"managed mod source is missing: {original}")
            continue
        try:
            managed = add_to_library(original)
            mod["path"] = str(managed)
            copied += 1
        except Exception as exc:
            errors.append((str(original), str(exc)))
            log(f"could not copy mod into library: {original}: {exc}")
    if copied:
        save_config(cfg)
    return copied, errors


def purge_mod_library(cfg, log=print):
    """Permanently clear managed mod payloads and library entries, without touching game files."""
    root = MODS_DIR.resolve()
    if root.parent != APP_DATA.resolve() or root.name.lower() != "mods":
        raise RuntimeError("refusing to purge a Mods folder outside ModDiverLab data")
    if MODS_DIR.exists():
        shutil.rmtree(MODS_DIR)
    MODS_DIR.mkdir(parents=True, exist_ok=True)
    cfg["mods"] = []
    save_config(cfg)
    log("completely purged the mod library; game files and deployment backups were not changed")

# Fixed-size table strides, for row-aware merge conflicts.
ROW_SIZES = {
    "generated_customization_passive_bonuses.dl_bin": 16,
    "generated_damage_settings.dl_bin": 76,
    "generated_entities.dl_bin": 1232,
    "generated_projectile_settings.dl_bin": 272,
    "generated_stratagem_settings.dl_bin": 400,
}

BUILTIN = ROOT / "builtin"
EDITOR = ROOT / "vendor" / "editor" / "SHODAN Stat Editor"
EDITOR_CCM = ROOT / "vendor" / "editor" / "Combined Community Mods"
EDITOR_CCM_PRESETS = APP_DATA / "editor_presets" / "armory_forge"
IMPORTED_EDITORS = APP_DATA / "editors"


class BuiltinModsUnavailable(ValueError):
    """Selected built-in mods need their verified update/repair action first."""

    def __init__(self, instructions):
        self.instructions = tuple(dict.fromkeys(instructions))
        super().__init__('Selected built-in mods are not ready. Follow the numbered instructions in the log.')


def editor_version(folder):
    for relative in ('app/build.txt', 'README.txt'):
        try:
            text = (Path(folder) / relative).read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        match = re.search(r'(?im)^\s*(?:version\s*=\s*v?|SHODAN Stat Editor Offline v)(\d+(?:\.\d+)+)', text)
        if match:
            return tuple(int(part) for part in match.group(1).split('.'))
    return ()


def _active_editor(kind, fallback):
    imported = IMPORTED_EDITORS / kind
    exe_name = ("SHODAN Stat Editor Offline.exe" if kind == "shodan"
                else "Combined Community Mods.exe")
    if not (imported / exe_name).is_file():
        return fallback
    if kind == 'shodan' and (fallback / exe_name).is_file():
        bundled_version, imported_version = editor_version(fallback), editor_version(imported)
        if imported_version and bundled_version > imported_version:
            return fallback
    return imported


EDITOR = _active_editor("shodan", EDITOR)
EDITOR_CCM = _active_editor("ccm", EDITOR_CCM)


def import_editor(source, expected_kind=None, expected_version=None):
    """Install a SHODAN or CCM editor package, identifying it by executable name."""
    global EDITOR, EDITOR_CCM
    source = Path(source).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(str(source))
    IMPORTED_EDITORS.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="editor-import-", dir=str(IMPORTED_EDITORS)))
    try:
        if source.is_file():
            if source.suffix.lower() != ".zip":
                raise ValueError("Choose an editor ZIP archive or an extracted editor folder.")
            with zipfile.ZipFile(source) as archive:
                infos = archive.infolist()
                if len(infos) > MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > MAX_ZIP_BYTES:
                    raise ValueError("Editor archive exceeds the import size limits.")
                for info in infos:
                    name = info.filename.replace("\\", "/")
                    parts = name.split("/")
                    if name.startswith("/") or any(part in ("", ".", "..") for part in parts if part != ""):
                        raise ValueError("Editor archive contains an unsafe file path.")
                    if any(":" in part for part in parts):
                        raise ValueError("Editor archive contains an absolute path.")
                    mode = (info.external_attr >> 16) & 0o170000
                    if mode == 0o120000:
                        raise ValueError("Editor archive contains a symbolic link.")
                    target = temporary.joinpath(*parts)
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(info) as src, target.open("wb") as dst:
                            shutil.copyfileobj(src, dst)
            search_root = temporary
        elif source.is_dir():
            search_root = source
        else:
            raise ValueError("Choose an editor ZIP archive or an extracted editor folder.")

        expected = {
            "shodan": "SHODAN Stat Editor Offline.exe",
            "ccm": "Combined Community Mods.exe",
        }
        found = []
        for kind, exe_name in expected.items():
            matches = [p for p in search_root.rglob("*")
                       if p.is_file() and p.name.casefold() == exe_name.casefold()]
            if len(matches) > 1:
                raise ValueError(f"The package contains more than one {exe_name}; import a single editor folder.")
            if matches:
                found.append((kind, matches[0].parent))
        if len(found) != 1:
            raise ValueError("Could not identify exactly one supported editor. Expected either "
                             "SHODAN Stat Editor Offline.exe or Combined Community Mods.exe.")

        kind, editor_root = found[0]
        if expected_kind and kind != expected_kind:
            label = "SHODAN Stat Editor" if expected_kind == "shodan" else "Combined Community Mods"
            raise ValueError(f"This package does not contain {label}.")
        if expected_version and editor_version(editor_root) != tuple(expected_version):
            raise ValueError('The package version does not match the GitHub release tag.')
        destination = IMPORTED_EDITORS / kind
        staged = IMPORTED_EDITORS / f".{kind}-{uuid.uuid4().hex}.staging"
        shutil.copytree(editor_root, staged)
        backup = IMPORTED_EDITORS / f".{kind}-{uuid.uuid4().hex}.old"
        try:
            if destination.exists():
                destination.rename(backup)
            staged.rename(destination)
        except Exception:
            if backup.exists() and not destination.exists():
                backup.rename(destination)
            raise
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        if kind == "shodan":
            EDITOR = destination
        else:
            EDITOR_CCM = destination
        return kind, destination
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
DATA_BUILTIN = APP_DATA / "builtin"
if os.name == "nt":
    EDITOR_CFG = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SHODAN" / "StatEditor"
else:
    EDITOR_CFG = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "SHODAN" / "StatEditor"

VANILLA_IDS = []  # removed: Vanilla+ features live in the SHODAN editor, not as Laboratory toggles

MAGIC = b"YAO-DLBRIDGE/1\x00\x00"
MAGIC_QET = b"QET-DLBRIDGE/1\x00\x00"

# Sensible caps for community ZIP imports.
MAX_ZIP_ENTRIES = 20000
MAX_ZIP_BYTES = 2 * 1024 ** 3
MAX_7Z_LIST_BYTES = 32 * 1024 ** 2
ARCHIVE = "9ba626afa44a3aa3.patch_"
TYPE = 0xA14E8DFA2CD117E2

def _default_game():
    if os.name == "nt":
        return r"C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2"
    home = Path.home()
    candidates = [
        home / ".steam" / "steam" / "steamapps" / "common" / "Helldivers 2",
        home / ".steam" / "steam" / "steamapps" / "common" / "HELLDIVERS 2",
        home / ".local" / "share" / "Steam" / "steamapps" / "common" / "Helldivers 2",
        home / ".local" / "share" / "Steam" / "steamapps" / "common" / "HELLDIVERS 2",
        home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam" / "steamapps" / "common" / "Helldivers 2",
    ]
    return str(next((p for p in candidates if p.is_dir()), candidates[0]))


DEFAULT_GAME = _default_game()
DEFAULT_THEME = {
    "preset": "Helldiver",
    "bg": "#080808", "panel": "#141414", "panel2": "#222222",
    "accent": "#ffd400", "accent_text": "#080808",
    "text": "#ffffff", "muted": "#c4c4c4",
    "good": "#6fbf73", "warn": "#e0a84f", "bad": "#e3342f",
    "font": 10, "log_font": 12,
}


# ---------------------------------------------------------------- config
def load_config():
    cfg = {"game": DEFAULT_GAME, "build": 26088801, "theme": dict(DEFAULT_THEME), "mods": [],
           "nomofomo": True, "stratagem_bounce_removed": True, "consistent_vaulting": True}
    try:
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    except Exception:
        pass
    cfg["theme"] = {**DEFAULT_THEME, **cfg.get("theme", {})}
    return cfg


def save_config(cfg):
    APP_DATA.mkdir(parents=True, exist_ok=True)
    # Replace atomically so a crash cannot truncate the user's presets and library.
    fd, pending = tempfile.mkstemp(prefix='.config-', suffix='.json', dir=APP_DATA)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(cfg, handle, ensure_ascii=False, indent=2)
        os.replace(pending, CONFIG)
    finally:
        Path(pending).unlink(missing_ok=True)


def game_dir(cfg):
    return Path(cfg["game"])


def hellforge_root(cfg):
    """Accept either the HellForge installation or its game copy in the folder picker."""
    if not cfg.get('game'):
        return None
    folder = game_dir(cfg)
    for root in (folder, folder.parent if folder.name.lower() == 'game' else folder):
        if any((root / name).is_file() for name in ('hellforge-install.json', 'bts-install.json', 'HellForge.exe')):
            return root
    return None


def game_file(cfg, name):
    return game_dir(cfg) / "data" / "game" / name


def target_path(cfg, target):
    """Resolve a deploy target, refusing anything outside the game's data directory."""
    root = (game_dir(cfg) / "data").resolve()
    raw = str(target)
    dest = game_dir(cfg) / raw if raw.startswith("data/") else game_dir(cfg) / "data" / "game" / raw
    dest = dest.resolve()
    try:
        dest.relative_to(root)
    except ValueError:
        raise RuntimeError("refusing to write outside the game data folder: " + raw)
    return dest


def _safe_rel(target):
    """Reject archive targets that could escape the game's data directory."""
    t = str(target).replace("\\", "/")
    if not t or t.startswith("/") or ":" in t:
        return False
    return all(part not in ("", ".", "..") for part in t.split("/"))


def linux_open(target):
    # Steam and desktop URL handlers belong to the host when using Distrobox.
    command = ['xdg-open', str(target)]
    if os.environ.get('YAO_FORGE_DISTROBOX'):
        if not shutil.which('distrobox-host-exec'):
            raise RuntimeError('Distrobox host integration is missing. Re-enter the container using distrobox enter.')
        command.insert(0, 'distrobox-host-exec')
    return subprocess.Popen(command)


def launch_game():
    if os.name == "nt":
        os.startfile("steam://rungameid/553850")
    else:
        linux_open("steam://rungameid/553850")


def steam_verify():
    if os.name == "nt":
        os.startfile("steam://validate/553850")
    else:
        linux_open("steam://validate/553850")


def steam_content_log(game):
    """Locate Steam's content log from the installed game's appmanifest."""
    game = Path(game).resolve()
    manifest = game.parent.parent / 'appmanifest_553850.acf'
    try:
        text = manifest.read_text(encoding='utf-8', errors='replace')
    except OSError:
        text = ''
    match = re.search(r'"LauncherPath"\s+"([^"]+)"', text, re.IGNORECASE)
    roots = []
    if match:
        roots.append(Path(match[1]).parent)
    if os.name == 'nt':
        for env_name in ('ProgramFiles(x86)', 'ProgramFiles'):
            base = os.environ.get(env_name)
            if base:
                roots.append(Path(base) / 'Steam')
    else:
        roots.extend(Path(p).expanduser() for p in ('~/.local/share/Steam', '~/.steam/steam', '~/.var/app/com.valvesoftware.Steam/.local/share/Steam'))
    for root in roots:
        path = root / 'logs' / 'content_log.txt'
        if path.is_file():
            return path
    return None


def load_deployed():
    try:
        return json.loads(DEPLOYED.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_deployed(d):
    APP_DATA.mkdir(parents=True, exist_ok=True)
    atomic_write(DEPLOYED, (json.dumps(d, indent=2) + "\n").encode("utf-8"))


def recover_deployment(log=print):
    """Recover an interrupted game-file deployment before further mutations."""
    result = recover_file_transaction(DEPLOYED.with_name("deploy-transaction.json"))
    if result == "rolled back":
        log("Recovered an interrupted deployment by restoring its pre-deployment files.")
    elif result == "completed":
        log("Finalized a deployment that had already committed before shutdown.")
    return result


def validate_deployment_plan(plan):
    """Reject duplicate/unsafe game destinations before creating any writes."""
    seen = set()
    for destination, data in plan:
        path = Path(destination).resolve()
        if path in seen:
            raise RuntimeError(f"Deployment plan targets the same file more than once: {path}")
        seen.add(path)
        if not isinstance(data, bytes):
            raise TypeError(f"Deployment payload for {path} is not binary data")
        if not path.is_absolute():
            raise RuntimeError(f"Deployment target is not an absolute path: {path}")


# ---------------------------------------------------------------- crypto
def unseal(data):
    out = ctypes.create_string_buffer(len(data) - 48)
    if _sodium.crypto_box_seal_open(out, data, len(data), PK, SK) != 0:
        raise ValueError("not a game data file")
    return out.raw


def seal(plain):
    out = ctypes.create_string_buffer(len(plain) + 48)
    if _sodium.crypto_box_seal(out, plain, len(plain), PK) != 0:
        raise ValueError("seal failed")
    return out.raw


# ---------------------------------------------------------------- mod parsing
def parse_stream(data):
    if data[:16] not in (MAGIC, MAGIC_QET):
        return None
    osz, csz = struct.unpack_from("<II", data, 28)
    target = data[112:176].split(b"\0")[0].decode("utf-8", "replace")
    if not target:
        return None
    return target, data[256:256 + osz], data[256 + osz:256 + osz + csz]


def game_target(arcname, parts, opt_name, option_dirs):
    if opt_name and parts and parts[0] in option_dirs:
        parts = parts[1:]
    if not parts:
        return None
    if parts[0].lower() == "data":
        return "/".join(parts)
    if parts[0].lower() in ("addon", "mod"):
        return "data/" + "/".join(parts[1:]) if len(parts) > 1 else None
    return "data/" + "/".join(parts)


def _read_7z_entries(path):
    """Read a 7z archive through Windows' bundled bsdtar without shell expansion."""
    if Path(path).stat().st_size > MAX_ZIP_BYTES:
        raise ValueError("archive is too large")
    tar = shutil.which("bsdtar") or shutil.which("tar")
    if not tar:
        raise ValueError("7z import needs tar (bsdtar) on PATH.")
    try:
        listing = subprocess.run([tar, "-tf", str(path)], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, timeout=90)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("timed out while listing the 7z archive") from exc
    if listing.returncode:
        detail = listing.stderr.decode("utf-8", "replace").strip().splitlines()
        reason = detail[-1] if detail else "unsupported or damaged archive"
        raise ValueError("could not read this 7z archive: " + reason[:240])
    if len(listing.stdout) > MAX_7Z_LIST_BYTES:
        raise ValueError("7z archive listing is too large")

    members, seen = [], set()
    for raw in listing.stdout.splitlines():
        try:
            name = raw.decode("utf-8")
        except UnicodeDecodeError:
            name = raw.decode("mbcs" if os.name == "nt" else "utf-8", "replace")
        name = name.replace("\\", "/")
        while name.startswith("./"):
            name = name[2:]
        is_dir = name.endswith("/")
        name = name.rstrip("/")
        if not name:
            continue
        if (name.startswith("/") or ":" in name or
                any(part in ("", ".", "..") for part in name.split("/"))):
            raise ValueError("7z archive contains an unsafe path")
        if name in seen:
            raise ValueError("7z archive contains duplicate paths")
        seen.add(name)
        members.append((name, is_dir))
        if len(members) > MAX_ZIP_ENTRIES:
            raise ValueError(f"archive has too many entries ({len(members)}); limit is {MAX_ZIP_ENTRIES}")

    entries, total_size = [], 0
    with tempfile.TemporaryDirectory(prefix="moddiver-7z-") as temp_dir:
        try:
            extracted = subprocess.run(
                [tar, "-xf", str(path), "-C", temp_dir, "--no-same-owner", "--no-same-permissions"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("timed out while extracting the 7z archive") from exc
        if extracted.returncode:
            detail = extracted.stderr.decode("utf-8", "replace").strip().splitlines()
            reason = detail[-1] if detail else "extraction failed"
            raise ValueError("could not extract this 7z archive: " + reason[:240])

        root = Path(temp_dir).resolve()
        for name, is_dir in members:
            target = root.joinpath(*name.split("/"))
            resolved = target.resolve()
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise ValueError("7z archive contains a path outside its extraction folder") from exc
            if target.is_symlink():
                raise ValueError("7z archives containing symbolic links are not supported")
            if is_dir:
                continue
            if not target.is_file():
                raise ValueError("7z archive contains an unreadable file entry")
            stat = target.stat()
            if stat.st_nlink > 1:
                raise ValueError("7z archives containing hard links are not supported")
            total_size += stat.st_size
            if total_size > MAX_ZIP_BYTES:
                raise ValueError("archive is too large uncompressed")
            entries.append((name, target.read_bytes()))
    return entries


def _strip_single_wrapper(entries):
    """Remove renamed top-level archive folders when every payload file is inside one."""
    result = list(entries)
    while result:
        roots = set()
        can_strip = True
        for name, _data in result:
            normalized = name.replace("\\", "/").strip("/")
            parts = normalized.split("/") if normalized else []
            if len(parts) < 2:
                can_strip = False
                break
            roots.add(parts[0])
            if len(roots) > 1:
                can_strip = False
                break
        if not can_strip:
            return result
        prefix = next(iter(roots)) + "/"
        result = [(name.replace("\\", "/").strip("/")[len(prefix):], data)
                  for name, data in result]
    return result


def parse_mod(path):
    p = Path(path)
    name, manifest = p.stem, {}
    entries = []
    if p.is_dir():
        manifest_names = ("manifest.json", "hellforge-mod.json", "mod.json")
        if not any((p / mf).is_file() for mf in manifest_names):
            nested = [f for f in p.rglob("*") if f.is_file() and f.name.lower() in manifest_names]
            if nested:
                nested.sort(key=lambda f: (len(f.relative_to(p).parts), str(f).casefold()))
                p = nested[0].parent
        for mf in ("manifest.json", "hellforge-mod.json", "mod.json"):
            if (p / mf).exists():
                try:
                    manifest = json.loads((p / mf).read_text(encoding="utf-8"))
                    name = manifest.get("Name") or manifest.get("name") or p.name
                except Exception:
                    pass
                break
        for f in p.rglob("*"):
            if f.is_file():
                try:
                    entries.append((f.relative_to(p).as_posix(), f.read_bytes()))
                except Exception:
                    pass
    elif p.suffix.lower() == ".zip":
        try:
            zf = zipfile.ZipFile(p)
        except Exception:
            return {"path": str(p), "name": name, "type": "unknown", "targets": [], "candidates": {},
                    "cand_option": {}, "files": [], "options": [], "manifest": {}, "runtime": False}
        with zf as z:
            infos = z.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise ValueError(f"archive has too many entries ({len(infos)}); limit is {MAX_ZIP_ENTRIES}")
            if sum(i.file_size for i in infos) > MAX_ZIP_BYTES:
                raise ValueError("archive is too large uncompressed")
            for n in z.namelist():
                if not n.endswith("/"):
                    try:
                        entries.append((n, z.read(n)))
                    except Exception:
                        pass
            entries = _strip_single_wrapper(entries)
            for mf in ("manifest.json", "hellforge-mod.json", "mod.json"):
                item = next(((n, data) for n, data in entries if n.lower() == mf), None)
                if item:
                    try:
                        manifest = json.loads(item[1].decode("utf-8-sig"))
                        name = manifest.get("Name") or manifest.get("name") or p.stem
                    except Exception:
                        pass
                    break
    elif p.suffix.lower() == ".7z":
        entries = _read_7z_entries(p)
        entries = _strip_single_wrapper(entries)
        for mf in ("manifest.json", "hellforge-mod.json", "mod.json"):
            for arcname, data in entries:
                if arcname == mf:
                    try:
                        manifest = json.loads(data.decode("utf-8-sig"))
                        name = manifest.get("Name") or manifest.get("name") or p.stem
                    except Exception:
                        pass
                    break
            if manifest:
                break
    else:
        return {"path": str(p), "name": name, "type": "unknown", "targets": [], "candidates": {},
                "cand_option": {}, "files": [], "options": [], "manifest": {}}

    # HellForge owns the whole package, including JSON specs, C sources, DLLs and
    # Lua directory layout. Never feed those files through the sealed-data merger.
    import hellforge
    compatibility = hellforge.classify(entries, manifest, name)
    if compatibility:
        hellforge._validate_package(p)
        hellforge.validate_entries(entries)
        return {"path": str(p), "name": name, "type": "HellForge", "targets": [n for n, _ in entries],
                "candidates": {}, "cand_option": {}, "files": [], "options": [],
                "manifest": manifest, "runtime": False, "hellforge": True,
                "package_entries": entries}

    options, option_dirs = [], {}
    for gi, opt in enumerate(manifest.get("Options") or manifest.get("options") or []):
        group = opt.get("Name") or opt.get("name") or ("Group %d" % (gi + 1))
        subs = opt.get("SubOptions") or opt.get("suboptions") or []
        if subs:
            for si, sub in enumerate(subs):
                nm = sub.get("Name") or sub.get("name") or (group + " %d" % (si + 1))
                incs = [x for x in (sub.get("Include") or sub.get("include") or []) if isinstance(x, str)]
                options.append({"name": nm, "include": incs, "group": group, "default": si == 0})
                for inc in incs:
                    option_dirs[inc.rstrip("/")] = nm
        else:
            nm = group
            incs = [x for x in (opt.get("Include") or opt.get("include") or []) if isinstance(x, str)]
            options.append({"name": nm, "include": incs, "group": None, "default": gi == 0})
            for inc in incs:
                option_dirs[inc.rstrip("/")] = nm

    has_desc = any(n.lower().endswith(".stream") and d[:16] in (MAGIC, MAGIC_QET) for n, d in entries)
    runtime = False
    candidates, cand_option, files = {}, {}, []
    mtype = "file"
    for arcname, data in entries:
        parts = arcname.split("/")
        base = parts[-1]
        low = base.lower()
        if low in ("manifest.json", "readme.txt", "readme.md", "license.txt", "thumbnail.png"):
            continue
        if low.endswith((".png", ".jpg", ".jpeg", ".ico", ".md", ".ini", ".txt", ".json",
                         ".cmd", ".bat", ".ps1", ".log", ".py")):
            continue
        best_inc, opt_name = None, None
        for inc, nm in option_dirs.items():
            if arcname == inc or arcname.startswith(inc + "/"):
                if best_inc is None or len(inc) > len(best_inc):
                    best_inc, opt_name = inc, nm
        rel = arcname[len(best_inc) + 1:] if best_inc else arcname
        if low.endswith((".dll", ".exe", ".asi")):
            runtime = True
            continue
        if low.endswith(".lua"):
            # Chef-compatible Lua payload: deploy under mod/ so the loader finds it.
            if _safe_rel("mod/" + rel):
                files.append({"target": "mod/" + rel, "data": data, "option": opt_name, "name": base})
            continue
        if low.endswith(".stream"):
            if data[:16] in (MAGIC, MAGIC_QET):
                got = parse_stream(data)
                if got and _safe_rel(got[0]):
                    candidates[got[0]] = got[2]
                    cand_option[got[0]] = opt_name
                    mtype = "yao"
            else:
                target = game_target(rel, rel.split("/"), opt_name, option_dirs)
                if target:
                    files.append({"target": target, "data": data, "option": opt_name, "name": base})
                    if not candidates and mtype == "file":
                        mtype = "mixed"
            continue
        if has_desc and parts[0].lower() == "addon" and low.endswith((".patch_0", ".gpu_resources")):
            continue
        if low.endswith(".dl_bin"):
            candidates[base] = data
            cand_option[base] = opt_name
            if mtype != "yao":
                mtype = "plain"
            continue
        target = game_target(rel, rel.split("/"), opt_name, option_dirs)
        if target and _safe_rel(target):
            files.append({"target": target, "data": data, "option": opt_name, "name": base})
            if not candidates and mtype == "file":
                mtype = "mixed"
    if not candidates and not files and any(n.endswith("config.txt") for n, _ in entries):
        mtype = "stat"
    targets = sorted(set(candidates) | {f["target"] for f in files})
    # Refine the library type label.
    if any(str(t).startswith("mod/") for t in targets):
        mtype = "lua"
    elif "loader" in str(name or "").lower():
        mtype = "loader"
    elif any("patch_" in str(t) for t in targets):
        mtype = "arsenal"
    return {"path": str(p), "name": name, "type": mtype, "targets": targets,
            "candidates": candidates, "cand_option": cand_option, "files": files,
            "options": options, "manifest": manifest, "runtime": runtime}


# ---------------------------------------------------------------- stock
REQUIRED_STOCK_FILES = 55


def stock_dir():
    STOCK.mkdir(parents=True, exist_ok=True)
    return STOCK


def stock_file_count():
    """Count captured game data files in the clean stock baseline."""
    return sum(1 for path in STOCK.glob("*.dl_bin") if path.is_file()) if STOCK.exists() else 0


def capture_stock(cfg, log=print):
    if hellforge_root(cfg) is not None:
        raise RuntimeError('HellForge manages its own clean game copy. Stock capture is only needed for regular game data mods.')
    g = game_dir(cfg) / "data" / "game"
    files = sorted(g.glob("*.dl_bin"))
    if not files:
        raise RuntimeError("No .dl_bin files found in " + str(g))
    if STOCK.exists():
        shutil.rmtree(STOCK, ignore_errors=True)
    STOCK.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, STOCK / f.name)
    log(f"stock captured: {len(files)} files")
    return len(files)


def clean_builtins(cfg):
    """Migrate the supported bundled loader and remove retired bundled features."""
    cfg.setdefault("nomofomo", True)
    keep = []
    for m in cfg["mods"]:
        p = str(m.get("path", "")).replace("\\", "/")
        parts = [part.casefold() for part in p.split("/") if part]
        if p.endswith("builtin/nomofomo"):
            continue
        if len(parts) >= 2 and parts[-2:] == ["builtin", "boot_loader"]:
            continue
        if len(parts) >= 2 and parts[-2:] == ["builtin", "chef_loader"]:
            m["path"] = str(BUILTIN / "chef_loader")
            keep.append(m)
            continue
        if ("/YAOModForge/" in p or "/ModDiver Laboratory/" in p) and "/builtin/" in p:
            continue
        old_name = str(m.get("name", "")).casefold()
        if "boot" in old_name and "loader" in old_name:
            continue
        keep.append(m)
    cfg["mods"] = keep
    save_config(cfg)
    return cfg


def _portable_manifest(name, guid=None, description=None):
    """Manifest fields shared by the ModDiver library and common HD2 managers."""
    return {
        "Version": 1,
        "Guid": guid or str(uuid.uuid4()),
        "Name": name,
        "Description": description or "Portable data mod created by ModDiver Laboratory.",
        "IconPath": "icon.png",
    }


def _portable_entries(mod):
    """Map a parsed mod's payload to archive paths rooted at data/."""
    entries = {}
    for target, data in (mod.get("candidates") or {}).items():
        arc = str(target).replace("\\", "/")
        if not arc.startswith("data/"):
            arc = "data/game/" + arc
        entries[arc] = data
    for item in mod.get("files") or []:
        target = str(item.get("target") or "").replace("\\", "/")
        if not target:
            continue
        if target.startswith("data/"):
            arc = target
        elif "patch_" in target or target.endswith((".stream", ".gpu_resources")):
            arc = "data/" + target
        else:
            arc = "data/game/" + target
        entries[arc] = item["data"]
    return entries


def _portable_readme(label, entries, build=None):
    files = "\n".join("  " + p for p in sorted(entries))
    build_text = str(build) if build else "unknown"
    return (
        "PORTABLE FILE MOD\n"
        "=================\n\n"
        f"{label}\n\n"
        "Created by ModDiver Laboratory.\n\n"
        "Install\n"
        "-------\n"
        "1. Close Helldivers 2.\n"
        "2. Import this ZIP into a file-based mod manager and deploy, or extract\n"
        "   the data folder into your Helldivers 2 folder (the one that contains\n"
        "   bin/ and data/).\n"
        "3. To remove it, restore your backup or verify the game files in Steam.\n\n"
        "Compatibility\n"
        "-------------\n"
        "- This package replaces full files under data/game. It is not a .patch_0\n"
        "  add-on.\n"
        "- Arsenal, HD2 Mod Manager and DDMM deploy .patch_0 add-ons only. Use the\n"
        "  separate *-Arsenal.zip data pack for those managers instead of this ZIP.\n"
        f"- Captured from game build {build_text}. Re-capture after a game update.\n"
        "- Conflicts with any other mod that replaces the same file.\n\n"
        "Files\n"
        "-----\n"
        f"{files}\n"
    )


def export_portable_mod(mod_path, out_path, name=None, guid=None, description=None,
                        build=None, log=print):
    """Write a portable file-mod ZIP with manifest.json and data/ payloads.

    This format is understood by ModDiver itself and by managers/tools that
    install loose files. Arsenal/HD2MM/DDMM only deploy .patch_0 add-ons, so a
    full data-file mod cannot be installed through them.
    """
    m = parse_mod(mod_path)
    entries = _portable_entries(m)
    if not entries:
        raise RuntimeError("This mod has no files that can be packaged as a portable mod.")
    label = name or m.get("name") or Path(mod_path).stem
    description = description or ("Full-file data mod captured with ModDiver Laboratory. "
                                   "This is not a .patch_0 add-on.")
    manifest = _portable_manifest(label, guid, description)
    readme = _portable_readme(label, entries, build)
    out_path = Path(out_path)
    with zipfile.ZipFile(out_path, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        z.writestr("README.txt", readme)
        icon = ROOT / "branding/icon_256.png"
        if icon.exists():
            z.writestr("icon.png", icon.read_bytes())
        for arc, data in sorted(entries.items()):
            info = zipfile.ZipInfo(arc, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if len(data) > 1_000_000 else zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    log(f"portable mod package: {out_path} "
        f"({out_path.stat().st_size} bytes, {len(entries)} files)")
    return str(out_path)


YAO_ARCHIVE = "9ba626afa44a3aa3.patch_"
YAO_LOADER_PATCH = BUILTIN / "yao_loader" / (YAO_ARCHIVE + "0")


def _arsenal_readme(label, targets, build):
    target_lines = "\n".join("  " + t for t in sorted(targets))
    return (
        "ARSENAL DATA PACK\n"
        "=================\n\n"
        f"{label}\n\n"
        "Built with ModDiver Laboratory. Includes the YAO DATA LOADER.\n\n"
        "Install\n"
        "-------\n"
        "1. Close Helldivers 2.\n"
        "2. Import this ZIP into Arsenal, enable it, and Deploy.\n"
        "3. Launch, exit normally, then launch again. The loader applies the\n"
        "   data pack on exit, so the next launch uses it.\n"
        "4. To remove it, disable the mod and Deploy. The loader restores the\n"
        "   original files it backed up.\n\n"
        "Notes\n"
        "-----\n"
        "- Do not enable another boot replacement (Chef or another YAO loader)\n"
        "  together with this package.\n"
        "- The loader refuses to install if the target file is not the exact\n"
        "  original for this build.\n"
        f"- Captured from game build {build}. Re-capture after a game update.\n\n"
        "Targets\n"
        "-------\n"
        f"{target_lines}\n"
    )


def export_arsenal_data_pack(cfg, mod_path, out_path, name=None, guid=None,
                             description=None, log=print):
    """Write an Arsenal/YAO data-pack ZIP: loader patch + one descriptor per file.

    Arsenal only deploys .patch_N files, so this wraps each captured .dl_bin as
    a YAO-DLBRIDGE/1 descriptor and bundles the boot-script loader that applies
    it. The loader keeps a backup and restores it when the pack is removed.
    """
    m = parse_mod(mod_path)
    candidates = {
        str(target).replace("\\", "/"): data
        for target, data in (m.get("candidates") or {}).items()
        if str(target).lower().endswith(".dl_bin")
    }
    if not candidates:
        raise RuntimeError("This mod has no .dl_bin files that can be packaged as a data pack.")
    if not YAO_LOADER_PATCH.is_file():
        raise RuntimeError("The bundled YAO DATA LOADER patch is missing.")
    build = int(cfg.get("build") or 26088801)
    label = name or m.get("name") or Path(mod_path).stem
    guid = guid or str(uuid.uuid4())
    description = description or (
        "Arsenal data pack for " + ", ".join(sorted(candidates)) +
        f" (build {build}). Requires the bundled YAO DATA LOADER.")
    manifest = {
        "Version": 1,
        "Guid": guid,
        "Name": label,
        "Description": description,
        "Options": [{
            "Name": label + " (data pack)",
            "Description": "Enable together with the bundled YAO DATA LOADER.",
            "Include": ["mod"],
            "Image": "icon.png",
        }],
        "IconPath": "icon.png",
    }
    streams = []
    for index, (target, data) in enumerate(sorted(candidates.items()), 1):
        original = STOCK / target
        if not original.is_file():
            raise RuntimeError(f"Stock copy missing for {target}; capture Stock again.")
        mod_id = f"MDL-{guid[:8]}-{index}"
        streams.append((index, make_stream(original.read_bytes(), data, mod_id, target, build),
                        marker_patch(mod_id)))
    out_path = Path(out_path)
    readme = _arsenal_readme(label, candidates, build)
    with zipfile.ZipFile(out_path, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        z.writestr("README.txt", readme)
        icon = ROOT / "branding/icon_256.png"
        if icon.exists():
            z.writestr("icon.png", icon.read_bytes())
        z.writestr(f"mod/{YAO_ARCHIVE}0", YAO_LOADER_PATCH.read_bytes())
        z.writestr(f"mod/{YAO_ARCHIVE}0.gpu_resources", b"")
        z.writestr(f"mod/{YAO_ARCHIVE}0.stream", b"")
        for index, stream, marker in streams:
            z.writestr(f"mod/{YAO_ARCHIVE}{index}", marker)
            z.writestr(f"mod/{YAO_ARCHIVE}{index}.gpu_resources", b"")
            z.writestr(f"mod/{YAO_ARCHIVE}{index}.stream", stream, zipfile.ZIP_STORED)
    log(f"Arsenal data pack: {out_path} "
        f"({out_path.stat().st_size} bytes, {len(streams)} target(s))")
    return str(out_path)


def capture_game_mod(cfg, log=print, name=None):
    """Snapshot changed game files as a library mod, a portable ZIP, and an Arsenal data pack."""
    if load_deployed():
        raise RuntimeError("Purge the current Laboratory deployment before capturing the game.")
    if not STOCK.exists() or not any(STOCK.glob("*.dl_bin")):
        raise RuntimeError("Capture Stock first (on a clean game).")
    g = game_dir(cfg) / "data" / "game"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    mod_dir = APP_DATA / "mods" / f"capture-{stamp}"
    data_dir = mod_dir / "data" / "game"
    data_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(g.glob("*.dl_bin")):
        stock = STOCK / f.name
        if not stock.exists():
            continue
        if f.read_bytes() != stock.read_bytes():
            shutil.copy2(f, data_dir / f.name)
            n += 1
    if not n:
        log("no changes vs the stock snapshot")
        return None
    label = name or f"Game capture {stamp}"
    guid = str(uuid.uuid4())
    description = (f"Full-file data mod captured from Helldivers 2 build "
                   f"{cfg.get('build', 'unknown')}. Not a .patch_0 add-on.")
    manifest = _portable_manifest(label, guid, description)
    (mod_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    icon = ROOT / "branding/icon_256.png"
    if icon.exists():
        shutil.copy2(icon, mod_dir / "icon.png")
    m = parse_mod(mod_dir)
    cfg["mods"].append({"path": m["path"], "name": label, "type": m["type"],
                        "targets": m["targets"], "enabled": True, "guid": guid})
    save_config(cfg)
    log(f"captured {n} changed file(s) as a mod")
    package = None
    try:
        package = export_portable_mod(
            mod_dir, mod_dir.with_suffix(".zip"), name=label, guid=guid,
            description=description, build=cfg.get("build"), log=log)
    except Exception as exc:
        log(f"portable package failed: {exc}")
    m["package"] = package
    arsenal_package = None
    try:
        arsenal_package = export_arsenal_data_pack(
            cfg, mod_dir, mod_dir.parent / (mod_dir.name + "-Arsenal.zip"),
            name=label, guid=guid, log=log)
    except Exception as exc:
        log(f"Arsenal data pack failed: {exc}")
    m["arsenal_package"] = arsenal_package
    return m


def stock_file(name):
    return STOCK / name


# ---------------------------------------------------------------- merge
def diff_runs(a, b):
    """Compatibility wrapper returning inclusive (start, end) tuples."""
    runs = _diff_runs(a, b)
    return None if runs is None else [(r.start, r.end) for r in runs]


def collect_floats(merged, runs, limit=64):
    out = []
    for s, e in runs:
        o = (s // 4) * 4
        while o <= e and len(out) < limit:
            if o + 4 <= len(merged):
                v = struct.unpack_from("<f", merged, o)[0]
                if math.isfinite(v) and 1e-6 < abs(v) < 1e6:
                    out.append(o)
            o += 4
    return out


def correct_and_seal(stock_plain, merged_plain, floats):
    run = APP_DATA / "tmp" / "run"
    run.mkdir(parents=True, exist_ok=True)
    sp, mp, op = run / "stock.bin", run / "merged.bin", run / "out.bin"
    for p in (sp, mp, op):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    sp.write_bytes(stock_plain)
    mp.write_bytes(merged_plain)
    cmd = [sys.executable, "--lua-runner"] if getattr(sys, "frozen", False) else \
        [sys.executable, str(ROOT / "lua_runner.py")]
    cmd += [str(sp), str(mp), str(op), ",".join(str(x) for x in floats)]
    try:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except Exception as exc:
            return None, str(exc)
        if r.returncode != 0 or not op.exists():
            return None, (r.stdout + r.stderr).strip()[-600:]
        return op.read_bytes(), r.stdout.strip()[-300:]
    finally:
        for p in (sp, mp):
            try:
                p.unlink()
            except OSError:
                pass


def merge_target(mods, stock_sealed, target, log=print, row_size=0):
    """Merge same-length candidates against stock; later mods win with conflicts logged."""
    validate_sealed_input(stock_sealed, "stock file")
    stock_plain = unseal(stock_sealed)
    named_candidates = []
    length_mismatch = None
    for m in mods:
        cand = m["candidates"].get(target)
        if cand is None:
            continue
        validate_sealed_input(cand, f"{m['name']} candidate")
        mp = unseal(cand)
        if len(mp) != len(stock_plain):
            length_mismatch = m["name"]
        named_candidates.append((m["name"], mp, cand))
    if not named_candidates:
        raise MergeSafetyError(f"No candidates supplied for {target}")
    if length_mismatch is not None:
        log(f"  {length_mismatch}: changes file length; offset merge is unsafe, using top-priority candidate {named_candidates[-1][0]}")
        return named_candidates[-1][2], "length"
    try:
        merged_plain, conflicts, all_runs = plan_merge_with_runs(
            stock_plain, [(name, plain) for name, plain, _ in named_candidates], row_size=row_size)
    except MergeSafetyError as exc:
        log(f"  merge aborted for {target}: {exc}")
        return named_candidates[-1][2], "fallback"

    if not all_runs:
        return named_candidates[-1][2], "noop"

    if conflicts:
        if row_size:
            total = sum((c.end - c.start + 1 + row_size - 1) // row_size for c in conflicts)
            conflict_measure = f"{total} row conflicts"
        else:
            total = sum(c.end - c.start + 1 for c in conflicts)
            conflict_measure = f"{total} bytes"
        examples = ", ".join(_format_conflict(c, target, row_size) for c in conflicts[:5])
        suffix = f"; +{len(conflicts)-5} more conflict ranges" if len(conflicts) > 5 else ""
        log(f"  merge conflicts: {len(conflicts)} ranges / {conflict_measure}; later mods win: {examples}{suffix}")

    floats = collect_floats(merged_plain, [(run.start, run.end) for run in all_runs])
    sealed, why = correct_and_seal(stock_plain, merged_plain, floats)
    if sealed is None:
        log(f"  hash correction failed ({why}); falling back to {named_candidates[-1][0]}")
        return named_candidates[-1][2], "fallback"
    try:
        validate_sealed_input(sealed, "corrected output")
        verified = unseal(sealed)
        if len(verified) != len(stock_plain):
            raise MergeSafetyError(
                f"corrected output length {len(verified)} != stock length {len(stock_plain)}"
            )
    except Exception as exc:
        log(f"  corrected output failed verification ({exc}); falling back to {named_candidates[-1][0]}")
        return named_candidates[-1][2], "fallback"
    return sealed, "merged"


@lru_cache(maxsize=8)
def _load_conflict_schema(type_library_path, file_path, stamp):
    import game_schema
    from schema_document import Document
    library = game_schema.Library.open(type_library_path)
    document = Document(file_path, library)
    labels = {}
    for resource in document.data.resources:
        typ = library.types.get(resource.type_hash)
        if typ and typ.size <= resource.sizes[0]:
            entries = [item for item in document.entries if item.block == resource.index and item.named]
            for item in entries:
                if item.offset % typ.size == 0:
                    labels[(resource.offsets[0] + item.offset) // typ.size] = item.label
    return labels


def _conflict_record_labels(target):
    try:
        game = game_dir(load_config())
        filename = Path(target).name
        data_dir = game / 'data' / 'game'
        candidates = (data_dir / 'dl_library.dl_typelib', game / 'data' / 'dl_library.dl_typelib')
        library_path = next((p for p in candidates if p.is_file()), None)
        file_path = data_dir / filename
        if library_path is None or not file_path.is_file():
            return {}
        stamp = (library_path.stat().st_mtime_ns, library_path.stat().st_size,
                 file_path.stat().st_mtime_ns, file_path.stat().st_size)
        return _load_conflict_schema(str(library_path.resolve()), str(file_path.resolve()), stamp)
    except Exception:
        return {}


def _format_conflict(conflict, target, row_size):
    if not row_size:
        location = f"bytes 0x{conflict.start:X}-0x{conflict.end:X}"
    else:
        first = conflict.start // row_size
        last = conflict.end // row_size
        labels = _conflict_record_labels(target)
        records = []
        for index in range(first, last + 1):
            name = labels.get(index)
            records.append(f"record {index}" + (f" ({name})" if name else ""))
        location = (", ".join(records) if records else f"record {first}")
        location += f", bytes 0x{conflict.start:X}-0x{conflict.end:X}"
    return f"{location} ({conflict.earlier_mod} -> {conflict.later_mod})"


PATCH_RE = re.compile(r"^(data/[0-9a-f]+\.patch_)(\d+)(\.gpu_resources|\.stream)?$")


def renumber_patches(gen):
    """Give every mod its own patch_N index so multiple Arsenal boot patches coexist."""
    used = set()
    out = {}
    groups = {}
    for t, its in gen.items():
        m = PATCH_RE.match(t)
        if not m:
            out.setdefault(t, []).extend(its)
            continue
        base, n, suf = m.group(1), int(m.group(2)), m.group(3) or ""
        for (o, mod, data) in its:
            groups.setdefault((o, mod["_name"], base), []).append((n, suf, o, mod, data))
    for key, lst in groups.items():
        mains = sorted([x for x in lst if x[1] == ""], key=lambda x: x[2])
        sides = sorted([x for x in lst if x[1] != ""], key=lambda x: (x[1], x[2]))
        n0 = 0
        while any((n0 + i) in used for i in range(len(mains))):
            n0 += 1
        for i, (n, suf, o, mod, data) in enumerate(mains):
            used.add(n0 + i)
            out.setdefault(key[2] + str(n0 + i), []).append((o, mod, data))
        for i, (n, suf, o, mod, data) in enumerate(sides):
            idx = n0 + min(i % max(len(mains), 1), max(len(mains) - 1, 0))
            used.add(idx)
            out.setdefault(key[2] + str(idx) + suf, []).append((o, mod, data))
    return out


# ---------------------------------------------------------------- deploy / purge
def deploy(cfg, log=print, dry_run=False, progress=None):
    root = hellforge_root(cfg)
    if root is not None:
        import hellforge
        return hellforge.deploy(cfg, root, log, dry_run)
    if not dry_run:
        recover_deployment(log)
    if any(m.get('enabled', True) and m.get('type') == 'HellForge' for m in cfg.get('mods', [])):
        raise RuntimeError('HellForge mods require a HellForge installation. Select its folder in Merge and Deploy.')
    from log_events import emit
    failures=0
    mods = []
    import gameplay_profiles
    import builtin_updater
    import hashlib
    import build_archive
    try:
        deployed_build = build_archive.steam_build(game_dir(cfg))
    except (OSError, ValueError, KeyError):
        deployed_build = None
    updated = builtin_updater.ensure(cfg, log, refresh=False)
    unavailable = []
    for key, label in builtin_updater.NAMES.items():
        if cfg.get(key, key == 'nomofomo') and key in updated and not isinstance(updated[key], Path):
            unavailable.append(f'{label}: {updated[key]}')
    if unavailable:
        raise BuiltinModsUnavailable(unavailable)
    # Build and verify all selected profiles before writing any game files.
    for key in gameplay_profiles.PROFILES:
        if cfg.get(key, False):
            mods.append(gameplay_profiles.build_mod(key, STOCK, updated[key]) if key in updated
                        else gameplay_profiles.build_mod(key, STOCK))
    if cfg.get("nomofomo", True):
        import hdremix
        nf = hdremix.build_mod(cfg, log)
        nf["_name"] = "NoMoFOMO + Hidden Content Unlocker HD REMIX 0.5.2"
        nf["_sel"] = {}
        mods.append(nf)
    for mod_index, mc in enumerate(cfg["mods"]):
        if progress:
            progress('Reading mod packages', mod_index, len(cfg['mods']))
        if not mc.get("enabled"):
            continue
        try:
            m = parse_mod(mc["path"])
            if m.get('hellforge'):
                raise RuntimeError('Select a HellForge installation to deploy this package.')
        except Exception as exc:
            emit(log,"  %s: failed to read mod: %s" % (mc.get("name"), exc),'error')
            failures+=1
            continue
        if not m["targets"]:
            continue
        if m.get("runtime"):
            log("  note (runtime files skipped): " + (mc.get("name") or m["name"]))
        m["_name"] = mc.get("name") or m["name"]
        m["_sel"] = mc.get("selected") or {}
        m['_category'] = library_category(mc)
        mods.append(m)
    if cfg.get('nomofomo', True):
        # A neutral stock seed only supplies the armour target when no user mod
        # supplies it. It must never win a length-mismatch fallback over a mod.
        for target in list(nf['candidates']):
            if any(target in m['candidates'] for m in mods if m is not nf):
                del nf['candidates'][target]
    names = [str(m.get("_name", "")) for m in mods]
    chefs = [n for n in names if "chef" in n.casefold() and "loader" in n.casefold()]
    if len(chefs) > 1:
        raise RuntimeError("Only one Chef Shared Loader version can be enabled at a time.")
    if not mods:
        log("no enabled mods with targets")
        return 0
    # The library lists the top mod first; deploy in reverse so the TOP mod has priority.
    mods = mods[::-1]
    # Stable partition keeps the top card's priority inside each group.
    first = cfg.get('loaders_deploy_first', False)
    mods.sort(key=lambda m: (m.get('_category') == 'loaders') != first)
    if not STOCK.exists() or not any(STOCK.glob("*.dl_bin")):
        raise RuntimeError("Capture the stock files first (Deploy tab > Capture Stock).")
    dl, gen = {}, {}
    for order, m in enumerate(mods):
        sel = m["_sel"]
        for t, cand in m["candidates"].items():
            opt = m["cand_option"].get(t)
            if opt is None or sel.get(opt, True):
                dl.setdefault(t, []).append((order, m, cand))
        for f in m["files"]:
            opt = f["option"]
            if opt is None or sel.get(opt, True):
                gen.setdefault(f["target"], []).append((order, m, f["data"]))
    gen = renumber_patches(gen)
    deployed = load_deployed()
    n = 0
    total_files = len(dl) + len(gen)
    planned = []
    next_deployed = dict(deployed)
    for file_index, (t, items) in enumerate(dl.items()):
        if progress:
            progress('Merging and writing files', file_index, total_files)
        stock = stock_file(t)
        if not stock.exists():
            emit(log,"  %s: no stock copy, skipped" % t,'error');failures+=1
            continue
        stock_sealed = stock.read_bytes()
        try:
            # Refuse to deploy corrupt/truncated sealed candidates; the merge validates too.
            validate_sealed_input(stock_sealed, f"stock {t}")
            unseal(stock_sealed)
            for _, mod, candidate in items:
                validate_sealed_input(candidate, f"{mod['_name']} candidate {t}")
                unseal(candidate)
            cand, why = merge_target(
                [{"name": m["_name"], "candidates": {t: c}} for _, m, c in items], stock_sealed, t, log,
                row_size=ROW_SIZES.get(Path(t).name, 0))
        except Exception as exc:
            emit(log,"  %s: failed: %s" % (t, exc),'error');failures+=1
            continue
        if cfg.get('nomofomo', True) and Path(t).name == 'generated_customization_armor_sets.dl_bin':
            import hdremix
            cand = hdremix.patch_armor(cand, int(cfg.get('unlock_groups',63)), bool(cfg.get('unlock_padding',False)), log)
        try:
            dest = target_path(cfg, t)
        except RuntimeError as exc:
            emit(log,"  %s: %s" % (t, exc),'error');failures+=1
            continue
        if dry_run:
            log(f'Would install {t}: {why} ({len(cand)} bytes)');n+=1;continue
        backup = BACKUPS / t
        existed = dest.exists() if t not in deployed else bool(deployed[t].get("existed", True))
        next_deployed[t] = {"backup": str(backup), "existed": existed,
                       "mods": [m["_name"] for _, m, _ in items], "how": why,
                       "sources": [m.get('path','') for _,m,_ in items],
                       "steam_build": deployed_build, "installed_sha256": hashlib.sha256(cand).hexdigest()}
        planned.append((dest, cand))
        n += 1
    for file_index, (t, items) in enumerate(gen.items(), start=len(dl)):
        if progress:
            progress('Merging and writing files', file_index, total_files)
        items.sort(key=lambda x: x[0])
        order, m, data = items[-1]
        try:
            dest = target_path(cfg, t)
        except RuntimeError as exc:
            emit(log,"  %s: %s" % (t, exc),'error');failures+=1
            continue
        if dry_run:
            log(f'Would install {t}: file ({len(data)} bytes)');n+=1;continue
        existed = dest.exists() if t not in deployed else bool(deployed[t].get("existed", True))
        backup = BACKUPS / t
        next_deployed[t] = {"backup": str(backup), "existed": existed,
                       "mods": [x[1]["_name"] for x in items], "how": "file",
                       "sources": [x[1].get('path','') for x in items],
                       "steam_build": deployed_build, "installed_sha256": hashlib.sha256(data).hexdigest()}
        planned.append((dest, data))
        n += 1
    if not dry_run and planned:
        validate_deployment_plan(planned)
        transaction_backup = BACKUPS / ".transactions" / str(int(time.time() * 1000))
        changes = list(planned) + [(DEPLOYED, (json.dumps(next_deployed, indent=2) + "\n").encode("utf-8"))]
        try:
            for t, info in next_deployed.items():
                if t in deployed or not info.get("existed"):
                    continue
                target = target_path(cfg, t)
                backup = Path(info["backup"])
                if not backup.is_file() and target.is_file():
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup)
            journal = DEPLOYED.with_name("deploy-transaction.json")
            apply_file_transaction(changes, journal, transaction_backup,
                                   metadata={"kind": "game-deploy", "files": [str(path) for path, _ in planned],
                                             "manifest_paths": [str(DEPLOYED)]},
                                   writer=atomic_write,
                                   delete_paths=[Path(info["backup"]) for t, info in deployed.items()
                                                 if t not in next_deployed],
                                   preserve_backup_paths=[Path(info["backup"]) for t, info in next_deployed.items()
                                                          if t not in deployed])
        except BaseException:
            # Existing deploy tracking is intentionally preserved until commit.
            # A transaction rollback restores the game files if application failed.
            log("Deployment failed; staged changes were rolled back or remain recorded for recovery.")
            raise
        deployed = next_deployed
        for path, data in planned:
            emit(log, "Installed %s (%d bytes)" % (path.name, len(data)), 'success')
    if dry_run:
        summary = f'PREVIEW COMPLETE: {n} FILE(S) WOULD BE INSTALLED; {failures} FAILED/SKIPPED. NO GAME FILES CHANGED.'
        emit(log, summary, 'success' if failures == 0 else 'warning')
    elif failures:emit(log,f'Deployment incomplete: {n} file(s) installed; {failures} failed/skipped. Review the red messages.','error')
    elif n:emit(log,f'Deployment complete: installed {n} file(s).','success')
    else:emit(log,'No files installed. Check enabled mods and selected options.','warning')
    if progress:
        progress('Files processed', total_files, total_files)
    return n


def purge(cfg, log=print):
    root = hellforge_root(cfg)
    if root is not None:
        import hellforge
        return hellforge.purge(root, log)
    recover_deployment(log)
    import loader_cleanup
    # Runtime-created backups are not in deployed.json and can outlive Steam
    # verification or a prior purge. Recover these before desktop backups win.
    runtime_count = loader_cleanup.cleanup(cfg, APP_DATA, log)
    deployed = load_deployed()
    if not deployed:
        log(f"removed {runtime_count} YAO loader artifact(s)" if runtime_count else "nothing deployed")
        return runtime_count
    n = runtime_count
    failures = []
    restore_plan = []
    for t, info in deployed.items():
        try:
            dest = target_path(cfg, t)
            backup_value = info.get("backup")
            backup = Path(backup_value) if backup_value else None
            if info.get("existed", True):
                if backup is not None and backup.is_file():
                    restore_plan.append((dest, backup.read_bytes()))
                    n += 1
                else:
                    failures.append(f"{t}: original file existed but backup is missing; left destination untouched")
            else:
                restore_plan.append((dest, None))
                n += 1
        except Exception as exc:
            failures.append(f"{t}: {exc}")
    transaction_succeeded = False
    if restore_plan:
        failed_targets = {failure.split(':', 1)[0] for failure in failures}
        remaining = {t: info for t, info in deployed.items() if t in failed_targets}
        transaction_backup = BACKUPS / ".transactions" / ("purge-" + str(int(time.time() * 1000)))
        try:
            apply_file_transaction(
                [(path, data) for path, data in restore_plan]
                + [(DEPLOYED, (json.dumps(remaining, indent=2) + "\n").encode("utf-8"))],
                DEPLOYED.with_name("deploy-transaction.json"), transaction_backup,
                metadata={"kind": "game-purge", "files": [str(path) for path, _ in restore_plan],
                          "manifest_paths": [str(DEPLOYED)]},
                writer=atomic_write,
                delete_paths=[path for path, data in restore_plan if data is None])
            transaction_succeeded = True
        except Exception as exc:
            failures.append(f"purge transaction: {exc}")
    if failures:
        # Keep recovery metadata for failed items so the user can retry rather than losing state.
        remaining = {t: info for t, info in deployed.items()
                     if any(item.startswith(f"{t}:") for item in failures)}
        for failure in failures:
            log("  purge warning: " + failure)
    elif transaction_succeeded:
        shutil.rmtree(BACKUPS, ignore_errors=True)
    log(f"restored/removed {n} file(s)")
    return n


# ---------------------------------------------------------------- YAO pack export
def resource_hash(name: str) -> int:
    data = name.encode("utf-8")
    mask, mix = (1 << 64) - 1, 0xC6A4A7935BD1E995
    value = len(data) * mix & mask
    end = len(data) // 8 * 8
    for (word,) in struct.iter_unpack("<Q", data[:end]):
        word = word * mix & mask
        word ^= word >> 47
        value = (value ^ (word * mix & mask)) * mix & mask
    if data[end:]:
        value = (value ^ int.from_bytes(data[end:], "little")) * mix & mask
    value ^= value >> 47
    value = value * mix & mask
    return value ^ (value >> 47)


def make_archive(resources):
    count = len(resources)
    offset = (104 + 80 * count + 15) & ~15
    entries, body = bytearray(), bytearray(offset)
    for index, (name, resource) in enumerate(sorted(resources.items())):
        entries += struct.pack("<7Q6I", name, TYPE, offset, 0, 0, 0, 0,
                               len(resource), 0, 0, 16, 16, index)
        body += resource
        body += b"\0" * (-len(body) % 16)
        offset = len(body)
    header = struct.pack("<III20sQQ24s", 0xF0000011, 1, count, b"", offset, 0, b"")
    types = struct.pack("<IIQIIII", 0, 0, TYPE, count, 0, 16, 16)
    body[:104 + len(entries)] = header + types + entries
    return bytes(body)


def marker_patch(mod_id):
    body = ("-- YAO data descriptor marker: " + mod_id + "\n").encode()
    return make_archive({resource_hash("yao.marker." + mod_id): struct.pack("<II", len(body), 2) + body})


def make_stream(original, candidate, mod_id, target, build):
    h = bytearray(256)
    h[0:16] = MAGIC
    struct.pack_into("<I", h, 16, 1)
    struct.pack_into("<I", h, 20, 256)
    struct.pack_into("<I", h, 24, build)
    struct.pack_into("<I", h, 28, len(original))
    struct.pack_into("<I", h, 32, len(candidate))
    struct.pack_into("<I", h, 36, 0)
    struct.pack_into("<I", h, 40, 1)
    h[48:48 + len(mod_id)] = mod_id.encode()
    h[112:112 + len(target)] = target.encode()
    return bytes(h) + original + candidate


VISUAL_PREFIXES = (
    "generated_customization_", "generated_animation_", "generated_stamp_",
    "generated_video_", "generated_font_", "generated_language_",
    "generated_weather_", "generated_sky_", "generated_planet_color_",
    "generated_distant_war_effect_", "generated_hit_effect_", "generated_credits_",
    "generated_corporation_logos",
    "units/", "audio/", "animations/", "materials/", "textures/", "particles/",
    "video/", "languages/", "fonts/",
    "data/units/", "data/audio/", "data/animations/", "data/materials/",
    "data/textures/", "data/particles/", "data/video/", "data/languages/", "data/fonts/",
)


LIBRARY_CATEGORIES = ('loaders', 'gameplay', 'visual')


def library_category(mod):
    category = mod.get('category')
    return category if category in LIBRARY_CATEGORIES else mod_category(mod.get('targets', []))


def deployment_mods(cfg):
    """Deployment sequence: lower cards first; loader group at the chosen end."""
    mods = list(reversed(cfg.get('mods', [])))
    first = cfg.get('loaders_deploy_first', False)
    return sorted(mods, key=lambda m: (library_category(m) == 'loaders') != first)


def mod_category(targets):
    """Visual & Audio for cosmetic/vfx/audio-ish files, otherwise Gameplay."""
    if not targets:
        return "gameplay"
    return "visual" if all(str(t).startswith(VISUAL_PREFIXES) for t in targets) else "gameplay"


def export_mod(cfg, out_path, log=print):
    """Export the deployed files as a plain mod ZIP that the ModDiver Laboratory library imports directly."""
    deployed = load_deployed()
    if not deployed:
        raise RuntimeError("Nothing deployed to export.")
    entries = []
    for t in sorted(deployed):
        dest = target_path(cfg, t)
        if not dest.exists():
            continue
        arc = str(t) if str(t).startswith("data/") else "data/game/" + str(t)
        entries.append((arc, dest.read_bytes()))
    if not entries:
        raise RuntimeError("No deployed files to export.")
    manifest = {
        "Version": 1,
        "Name": "ModDiver Laboratory Mod",
        "Description": "Exported from ModDiver Laboratory. Import this ZIP into the ModDiver Laboratory library.",
    }
    readme = ("MODDIVER LABORATORY MOD\n"
              "=================\n\n"
              "Import this ZIP into the ModDiver Laboratory library (Mods -> + Add ZIP), then Deploy.\n"
              "No loader is needed.\n\n"
              + "\n".join("- " + arc for arc, _ in entries) + "\n")
    icon = ROOT / "branding/icon_256.png"
    with zipfile.ZipFile(out_path, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        z.writestr("README.txt", readme)
        if icon.exists():
            z.writestr("icon.png", icon.read_bytes())
        for arc, data in entries:
            info = zipfile.ZipInfo(arc, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if len(data) > 1_000_000 else zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    log(f"exported {out_path} ({Path(out_path).stat().st_size} bytes, {len(entries)} files)")
    return out_path


# ---------------------------------------------------------------- native editor (armour passives)
EDITOR_RUNNER = ROOT / "editor_runner.py"
PASSIVE_FILE = "generated_customization_passive_bonuses.dl_bin"


def dump_passives(g):
    import subprocess
    import sys
    p = Path(g) / "data" / "game" / PASSIVE_FILE
    if not p.exists():
        raise RuntimeError("armour passive file not found")
    out = APP_DATA / "_editor_passives.txt"
    APP_DATA.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    r = subprocess.run([sys.executable, str(EDITOR_RUNNER), "dump", "passives", str(p), str(out)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError("passive dump failed")
    rows = []
    for line in out.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] in ("M", "S"):
            rows.append((parts[0], int(parts[1]), int(parts[2]), float(parts[3])))
    return rows


def apply_passives(g, edits):
    import subprocess
    import sys
    p = Path(g) / "data" / "game" / PASSIVE_FILE
    if not p.exists():
        raise RuntimeError("armour passive file not found")
    txt = APP_DATA / "_editor_edits.txt"
    out = APP_DATA / "_editor_out.dl_bin"
    APP_DATA.mkdir(parents=True, exist_ok=True)
    txt.write_text("\n".join(f"{k} {a} {b} {v:.9g}" for k, a, b, v in edits), encoding="utf-8")
    if out.exists():
        out.unlink()
    r = subprocess.run([sys.executable, str(EDITOR_RUNNER), "apply", "passives", str(p), str(out), "", str(txt)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError("passive apply failed")
    sealed = out.read_bytes()
    BACKUPS.mkdir(parents=True, exist_ok=True)
    bak = BACKUPS / p.name
    if not bak.exists():
        shutil.copy2(p, bak)
    atomic_write(p, sealed)
    return len(sealed)


def dump_weapons(g):
    import subprocess
    import sys
    p = Path(g) / "data" / "game" / "generated_entities.dl_bin"
    if not p.exists():
        raise RuntimeError("entities file not found")
    out = APP_DATA / "_editor_weapons.txt"
    APP_DATA.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    r = subprocess.run([sys.executable, str(EDITOR_RUNNER), "dump", "weapons", str(p), str(out)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError("weapon dump failed")
    rows = []
    for line in out.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] in ("W", "D"):
            rows.append((parts[0], parts[1], parts[2], float(parts[3])))
    return rows


def apply_weapons(g, edits):
    import subprocess
    import sys
    p = Path(g) / "data" / "game" / "generated_entities.dl_bin"
    if not p.exists():
        raise RuntimeError("entities file not found")
    txt = APP_DATA / "_editor_weapons_edits.txt"
    out = APP_DATA / "_editor_weapons_out.dl_bin"
    APP_DATA.mkdir(parents=True, exist_ok=True)
    txt.write_text("\n".join(f"{kind} {key} {field} {v:.9g}" for kind, key, field, v in edits), encoding="utf-8")
    if out.exists():
        out.unlink()
    r = subprocess.run([sys.executable, str(EDITOR_RUNNER), "apply", "weapons", str(p), str(out), "", str(txt)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError("weapon apply failed")
    sealed = out.read_bytes()
    BACKUPS.mkdir(parents=True, exist_ok=True)
    bak = BACKUPS / p.name
    if not bak.exists():
        shutil.copy2(p, bak)
    atomic_write(p, sealed)
    return len(sealed)


def dump_damage(g):
    import subprocess
    import sys
    p = Path(g) / "data" / "game" / "generated_damage_settings.dl_bin"
    if not p.exists():
        raise RuntimeError("damage settings file not found")
    out = APP_DATA / "_editor_damage.txt"
    APP_DATA.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    r = subprocess.run([sys.executable, str(EDITOR_RUNNER), "dump", "weapons", str(p), str(out)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError("damage dump failed")
    rows = []
    for line in out.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] == "D":
            rows.append((parts[1], parts[2], float(parts[3])))
    return rows


def apply_damage(g, edits):
    import subprocess
    import sys
    p = Path(g) / "data" / "game" / "generated_damage_settings.dl_bin"
    if not p.exists():
        raise RuntimeError("damage settings file not found")
    txt = APP_DATA / "_editor_damage_edits.txt"
    out = APP_DATA / "_editor_damage_out.dl_bin"
    APP_DATA.mkdir(parents=True, exist_ok=True)
    txt.write_text("\n".join(f"D {did} {field} {v:.9g}" for did, field, v in edits), encoding="utf-8")
    if out.exists():
        out.unlink()
    r = subprocess.run([sys.executable, str(EDITOR_RUNNER), "apply", "weapons", str(p), str(out), "", str(txt)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError("damage apply failed")
    sealed = out.read_bytes()
    BACKUPS.mkdir(parents=True, exist_ok=True)
    bak = BACKUPS / p.name
    if not bak.exists():
        shutil.copy2(p, bak)
    atomic_write(p, sealed)
    return len(sealed)


# ---------------------------------------------------------------- bundled loaders
def install_builtin(cfg, name, log):
    src = BUILTIN / name
    manifest = src / "manifest.json"
    if not manifest.exists():
        raise RuntimeError(f"built-in {name} not found")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    label = data.get("Name", name)
    mods = cfg.setdefault("mods", [])
    if any(m.get("path") == str(src) for m in mods):
        log(f"{label} is already in the library")
        return
    m = parse_mod(src)
    mods.append({"path": str(src), "name": m["name"], "type": m["type"], "targets": m["targets"],
                 "enabled": True, "selected": {}, "category": "loaders"})
    save_config(cfg)
    log(f"added {label} to the library (Deploy to install it)")


# ---------------------------------------------------------------- Chef Lua patch archives
LUA_TYPE = 0xA14E8DFA2CD117E2
PATCH_MAGIC = 0xF0000011


def resource_hash(name):
    data = name.encode("utf-8")
    mask, mix = (1 << 64) - 1, 0xC6A4A7935BD1E995
    value = len(data) * mix & mask
    end = len(data) // 8 * 8
    for (word,) in struct.iter_unpack("<Q", data[:end]):
        word = word * mix & mask
        word ^= word >> 47
        value = (value ^ (word * mix & mask)) * mix & mask
    if data[end:]:
        value = (value ^ int.from_bytes(data[end:], "little")) * mix & mask
    value ^= value >> 47
    value = value * mix & mask
    value ^= value >> 47
    return value


def lua_resource(src_bytes):
    return struct.pack("<II", len(src_bytes), 2) + src_bytes


def chef_header12_72():
    """The 60-byte header from the bundled Chef archive (a Lua patch known to load)."""
    p = BUILTIN / "chef_loader" / "9ba626afa44a3aa3.patch_0"
    data = p.read_bytes()
    if len(data) < 72 or struct.unpack_from("<I", data, 0)[0] != PATCH_MAGIC:
        raise RuntimeError("bundled Chef archive is not a patch container")
    return data[12:72]


def write_lua_archive(path, entries, header12_72=None):
    """Write a Chef/Boot Lua patch: MAGIC, version, count, header, LUA type row, entries, payloads."""
    header12_72 = header12_72 or chef_header12_72()
    head = struct.pack("<III", PATCH_MAGIC, 1, len(entries)) + header12_72
    head += struct.pack("<QQQII", 0, LUA_TYPE, len(entries), 16, 16)
    cursor = len(head) + 80 * len(entries)
    rows = body = b""
    for i, (fid, data) in enumerate(entries):
        pad = -cursor % 16
        body += b"\0" * pad
        cursor += pad
        rows += struct.pack("<7Q6I", fid, LUA_TYPE, cursor, 0, 0, 0, 0, len(data), 0, 0, 16, 16, i)
        body += data
        cursor += len(data)
    out = head + rows + body
    out += b"\0" * (-len(out) % 16)
    atomic_write(path, out)
    atomic_write(str(path) + ".gpu_resources", b"")
    atomic_write(str(path) + ".stream", b"")
