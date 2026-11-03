"""Persistent local Steam data builds and automatic three-way mod repair."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import uuid
import zipfile

import core
import repair_data
import nexus_mode
from dlbin_codec import DLBin, content_hash
import mod_repair


def archive_root():
    return core.APP_DATA.parent / nexus_mode.BASELINE_DIRECTORY


def migrate_baselines(data=None):
    """Move historical captures out of the directory cleared by Reset Local Data."""
    data = Path(data) if data is not None else core.APP_DATA
    legacy = data / 'Archive'
    root = data.parent / nexus_mode.BASELINE_DIRECTORY
    if root.is_symlink() or (hasattr(root, 'is_junction') and root.is_junction()):
        raise ValueError('Baseline storage must not be a link.')
    if not legacy.exists():
        return
    if legacy.is_symlink() or (hasattr(legacy, 'is_junction') and legacy.is_junction()):
        raise ValueError('Baseline storage must not be a link.')
    root.mkdir(parents=True, exist_ok=True)
    for folder, _ in builds(legacy):
        if folder.is_symlink() or not folder.resolve().is_relative_to(legacy.resolve()):
            raise ValueError('Invalid legacy baseline folder.')
        destination = root / folder.name
        if destination.exists():
            destination = root / (folder.name + '-' + uuid.uuid4().hex[:8])
        folder.rename(destination)


def ensure_baselines():
    """Keep local history valid; startup never downloads remote repair data."""
    migrate_baselines()
    trim_archive()


@contextmanager
def baseline_session(*, folder=None, progress=lambda message: None):
    """Remove extracted witnesses after success or failure; keep verified downloads cached."""
    ensure_baselines()
    if nexus_mode.NEXUS_BUILD:
        # Nexus repairs use only stock files captured from the user's install.
        yield (archive_root(),)
        return
    folder = Path(folder) if folder is not None else Path(__file__).parent / 'builtin/gameplay'
    scratch = core.APP_DATA / 'tmp'
    scratch.mkdir(parents=True, exist_ok=True)
    cache = Path(core.APP_DATA) / 'tmp' / 'repair-data-prefetch'
    session_root = cache / 'baselines'
    session_root.mkdir(parents=True, exist_ok=True)
    for package in repair_data.packages(folder, cache, download=not nexus_mode.NEXUS_BUILD, progress=progress):
        install_bundled_baseline(package, package.stem.removeprefix('repair-baseline-'), root=session_root)
    yield (archive_root(), session_root)


def install_bundled_baseline(package, build_id, *, root=None):
    """Verify and atomically register a complete bundle, including empty tables.

    Package identity invalidates old partial imports when coverage is expanded.
    A data-only bundle never prevents a later full repair-data capture.
    """
    package = Path(package)
    root = Path(root) if root is not None else archive_root()
    root.mkdir(parents=True, exist_ok=True)
    marker = root / ('bundled-' + build_id + '.json')
    checksum = repair_data.directory_digest(package)[1] if package.is_dir() else digest(package)
    try:
        saved = json.loads(marker.read_text(encoding='utf-8'))
        folder = root / saved['folder']
        meta = json.loads((folder / 'build.json').read_text(encoding='utf-8'))
        if (folder.resolve().parent == root.resolve() and not folder.is_symlink()
                and saved['sha256'] == checksum and meta['build_id'] == build_id and meta['files']
                and all(core._safe_rel(name) and digest(folder / 'data' / name) == value
                        for name, value in meta['files'].items())):
            return folder
    except (OSError, ValueError, KeyError):
        pass
    with tempfile.TemporaryDirectory(prefix='.bundle-', dir=root) as temporary:
        staging = Path(temporary)
        if package.is_dir():
            metadata = json.loads((package / 'baseline.json').read_text(encoding='utf-8'))
            read_entry = lambda entry: (package / entry).read_bytes()
        else:
            archive = zipfile.ZipFile(package)
            metadata = json.loads(archive.read('baseline.json'))
            read_entry = archive.read
        try:
            legacy = metadata.get('format') == 'moddiver-plain-baseline-1'
            if (metadata.get('format') not in ('moddiver-repair-baseline-1', 'moddiver-plain-baseline-1')
                    or metadata.get('build_id') != build_id or not metadata.get('files')):
                raise ValueError('Invalid bundled repair baseline.')
            files = {}
            total = 0
            for entry, info in metadata['files'].items():
                name = 'game/' + entry if legacy else entry
                if not core._safe_rel(name) or not repair_file(name) or name.lower() in {n.lower() for n in files}:
                    raise ValueError('Invalid bundled baseline path.')
                raw = read_entry(entry)
                expected = info if legacy else info['sha256']
                sealed = True if legacy else info['sealed']
                if hashlib.sha256(raw).hexdigest() != expected:
                    raise ValueError('Bundled baseline checksum mismatch: ' + name)
                if sealed:
                    raw = core.seal(raw)
                    core.unseal(raw)  # Empty generated tables are valid baselines too.
                target = staging / 'data' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                files[name] = hashlib.sha256(raw).hexdigest()
                total += len(raw)
        finally:
            if not package.is_dir():
                archive.close()
        for parent in {Path(name).parent for name in files}:
            (staging / 'data' / parent / 'snapshot.json').write_text(json.dumps({'version': 1, 'files': {
                Path(name).name: value for name, value in files.items() if Path(name).parent == parent}}), encoding='utf-8')
        scope = metadata.get('scope', 'data-only' if legacy else 'repair-data')
        if scope not in ('data-only', 'repair-data'):
            raise ValueError('Invalid bundled baseline scope.')
        (staging / 'build.json').write_text(json.dumps(dict(version=1, scope=scope, build_id=build_id,
            created_utc=datetime.now(timezone.utc).isoformat(), bytes=total, files=files), indent=2), encoding='utf-8')
        destination = root / ('build-' + build_id + '-bundled-' + uuid.uuid4().hex[:8])
        staging.rename(destination)
    core.atomic_write(marker, json.dumps({'sha256': checksum, 'folder': destination.name}).encode('utf-8'))
    return destination


def capture_stock_folder(game, stock, root=None, *, verification="steam-verify-stock-capture"):
    """Archive already captured clean stock without rereading installed files."""
    if verification not in ('steam-verify-stock-capture', 'user-confirmed-stock-capture'):
        raise ValueError('Unknown clean-stock confirmation method.')
    game, stock = Path(game).resolve(), Path(stock).resolve()
    root = Path(root) if root is not None else archive_root()
    if core.load_deployed():
        raise ValueError('Purge deployed mods before archiving clean stock.')
    files = sorted(path for path in stock.glob('*.dl_bin') if path.is_file())
    build = steam_build(game)
    existing = [(path, meta) for path, meta in builds(root)
                if meta['build_id'] == build and meta.get('scope') == 'repair-data']
    trusted = next((path for path, meta in existing
                    if meta.get('clean_verified') is True
                    and meta.get('clean_verification') == verification), None)
    if len(files) != core.REQUIRED_STOCK_FILES:
        raise ValueError(f'Captured clean stock is incomplete ({len(files)} of {core.REQUIRED_STOCK_FILES} files).')
    if trusted is not None:
        checksums = {path.name: digest(path) for path in files}
        current_files = {path.name: digest(path) for path in (game / 'data/game').glob('*.dl_bin')
                         if path.is_file() and not path.is_symlink()}
        trusted_files = next(meta['files'] for folder, meta in existing if folder == trusted)
        expected = {Path(name).name: checksum for name, checksum in trusted_files.items()
                    if Path(name).parent == Path('game')}
        if checksums == current_files:
            if checksums == expected:
                return trusted
            # A completed Steam verification can legitimately produce a new
            # clean revision for the same labeled build. Preserve the old one.
        else:
            raise ValueError('Captured clean stock does not match the current game files. Repeat Steam verify and stock capture.')
    root.mkdir(parents=True, exist_ok=True)
    meta = {'version': 1, 'scope': 'repair-data', 'clean_verified': True,
            'clean_verification': verification, 'build_id': build,
            'created_utc': datetime.now(timezone.utc).isoformat(), 'bytes': 0, 'files': {}}
    with tempfile.TemporaryDirectory(prefix='.capture-stock-', dir=root) as temporary:
        staging = Path(temporary)
        data = staging / 'data/game'
        data.mkdir(parents=True)
        for source in files:
            target = data / source.name
            shutil.copy2(source, target)
            meta['files']['game/' + source.name] = digest(target)
            meta['bytes'] += target.stat().st_size
        (data / 'snapshot.json').write_text(json.dumps({'version': 1, 'files': {
            Path(name).name: checksum for name, checksum in meta['files'].items()}}), encoding='utf-8')
        (staging / 'build.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
        destination = root / f'build-{build}-verified-{uuid.uuid4().hex[:8]}'
        staging.rename(destination)
    return destination


def steam_build(game):
    game = Path(game)
    manifest = game.parent.parent / 'appmanifest_553850.acf'
    text = manifest.read_text(encoding='utf-8')
    appid = re.search(r'"appid"\s+"(\d+)"', text)
    build = re.search(r'"buildid"\s+"(\d+)"', text)
    state = re.search(r'"StateFlags"\s+"(\d+)"', text)
    if not appid or appid[1] != '553850' or not build:
        raise ValueError('Cannot identify the installed Helldivers 2 Steam build.')
    if state and state[1] != '4':
        raise ValueError('Steam is updating or the installation is incomplete. Wait for Steam to finish.')
    return build[1]


def builds(root=None):
    if isinstance(root, (list, tuple)):
        return [entry for folder in root for entry in builds(folder)]
    root = Path(root) if root is not None else archive_root()
    result = []
    for path in sorted(root.glob('build-*')):
        try:
            meta = json.loads((path / 'build.json').read_text(encoding='utf-8'))
            if (meta.get('version') == 1 and isinstance(meta.get('files'), dict)
                    and re.fullmatch(r'\d+', str(meta.get('build_id', '')))
                    and isinstance(meta.get('bytes'), int) and isinstance(meta.get('created_utc'), str)):
                result.append((path, meta))
        except (OSError, ValueError):
            continue
    return result


def clean_restore_files(game, root=None):
    """Return intact captured originals for this build, even if live files changed."""
    game = Path(game).resolve()
    try:
        build = steam_build(game)
    except (OSError, ValueError):
        return {}
    for folder, meta in sorted(builds(root), key=lambda item: item[1]['created_utc'], reverse=True):
        files = meta.get('files', {})
        if (meta.get('build_id') != build or meta.get('scope') != 'repair-data'
                or meta.get('clean_verified') is not True
                or meta.get('clean_verification') not in ('steam-verify-stock-capture', 'user-confirmed-stock-capture')
                or len(files) != core.REQUIRED_STOCK_FILES):
            continue
        restored = {}
        for name, checksum in files.items():
            rel = Path(name)
            if not core._safe_rel(name) or rel.parent != Path('game') or rel.suffix != '.dl_bin':
                break
            source = folder / 'data' / rel
            if source.is_symlink() or not source.is_file() or digest(source) != checksum:
                break
            restored['data/' + rel.as_posix()] = source
        else:
            return restored
    return {}


def find_matching_clean_baseline(game, build=None, root=None):
    """Return a verified repair baseline only when every archived file matches the game.

    This is a read-only check. It never captures or modifies game or baseline files.
    """
    game = Path(game).resolve()
    root = Path(root) if root is not None else archive_root()
    build = str(build if build is not None else steam_build(game))
    if core.load_deployed():
        return None
    game_data = game / 'data'
    current_files = {}
    for path in game_data.rglob('*'):
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(game_data.resolve()):
            continue
        relative = path.relative_to(game_data)
        # Clean stock capture records the 55 generated DLBin files. Archive
        # sidecars are kept in local repair baselines but are outside that
        # explicit stock-capture contract.
        if relative.parent == Path('game') and relative.suffix.lower() == '.dl_bin':
            current_files[relative.as_posix()] = path
    for folder, meta in builds(root):
        files = meta.get('files', {})
        if (meta.get('build_id') != build or meta.get('scope') != 'repair-data'
                or meta.get('clean_verified') is not True
                or meta.get('clean_verification') not in ('steam-verify-stock-capture', 'user-confirmed-stock-capture')
                or not isinstance(files, dict) or not files):
            continue
        if set(files) != set(current_files):
            continue
        matches = True
        for name, expected in files.items():
            if not core._safe_rel(name):
                matches = False
                break
            baseline = folder / 'data' / name
            current = current_files[name]
            if (not baseline.is_file() or not current.is_file()
                    or digest(baseline) != expected or digest(current) != expected):
                matches = False
                break
        if matches:
            return folder
    return None


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def repaired_root():
    return core.APP_DATA / 'Repaired Mods'


def purge_repaired():
    """Delete only the bot's output storage, never inputs, library mods or baselines."""
    root = repaired_root()
    if root.is_symlink() or (hasattr(root, 'is_junction') and root.is_junction()):
        raise ValueError('Repaired mod storage must not be a link.')
    if root.resolve().parent != core.APP_DATA.resolve():
        raise ValueError('Repaired mod storage is outside app data.')
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)


def repair_file(relative):
    """Only inputs read by automatic_plan, including required archive sidecars."""
    relative = Path(relative)
    if relative.parent == Path('game') and relative.suffix.lower() == '.dl_bin':
        return True
    return relative.parent == Path('.') and re.fullmatch(
        r'[0-9a-fA-F]{16}(?:\.stream|\.gpu_resources)?', relative.name) is not None


def trim_archive(root=None):
    """Migrate full captures to repair inputs, retaining historical repair baselines."""
    root = Path(root) if root is not None else archive_root()
    for folder, meta in builds(root):
        if meta.get('scope', 'full-data') != 'full-data':
            continue
        data = folder / 'data'
        # Validate every target before deleting anything from a legacy capture.
        paths = []
        for name in meta['files']:
            path = data / name
            if (not core._safe_rel(name) or not path.resolve().is_relative_to(data.resolve())
                    or any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction())
                           for p in (folder, data, path, *path.parents))):
                raise ValueError('Unsafe archived file path: ' + name)
            paths.append((name, path))
        keep = {name: meta['files'][name] for name, _ in paths if repair_file(name)}
        for name, path in paths:
            if name not in keep:
                path.unlink(missing_ok=True)
        meta.update(scope='repair-data', files=keep,
                    bytes=sum((data / name).stat().st_size for name in keep))
        for parent in {path.parent for _, path in paths}:
            snapshot = parent / 'snapshot.json'
            if snapshot.exists():
                snapshot.write_text(json.dumps({'version': 1, 'files': {
                    Path(name).name: checksum for name, checksum in keep.items()
                    if (data / name).parent == parent}}), encoding='utf-8')
        from merge_engine import atomic_write
        atomic_write(folder / 'build.json', json.dumps(meta, indent=2).encode('utf-8'))


def capture(game, root=None, progress=lambda message: None):
    """Save only data and archive components used for mod repair."""
    game = Path(game).resolve()
    root = Path(root) if root is not None else archive_root()
    if core.load_deployed():
        raise ValueError('Purge deployed mods before archiving or repairing. Use verified clean Steam files.')
    trim_archive(root)
    build = steam_build(game)
    existing = [(path, meta) for path, meta in builds(root) if meta['build_id'] == build and meta.get('scope') == 'repair-data']
    if existing:
        return existing[0][0]
    data = game / 'data'
    files = sorted(path for path in data.rglob('*') if path.is_file() and repair_file(path.relative_to(data)))
    if not files:
        raise ValueError('No game data files found. Set the Steam game folder in Merge and Deploy.')
    if any(path.is_symlink() or not path.resolve().is_relative_to(data.resolve())
           or path.resolve().is_relative_to(root.resolve()) for path in files):
        raise ValueError('Game data must not contain links or the Archive folder.')
    required = sum(path.stat().st_size for path in files)
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < required + 256 * 1024 ** 2:
        raise ValueError(f'Not enough space to archive this build ({required / 1024**3:.1f} GiB required).')
    meta = {'version': 1, 'scope': 'repair-data', 'build_id': build, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'bytes': required, 'files': {}}
    with tempfile.TemporaryDirectory(prefix='.capture-', dir=root) as temporary:
        staging = Path(temporary)
        manifests = {}
        stats = {}
        for number, path in enumerate(files, 1):
            relative = path.relative_to(data)
            target = staging / 'data' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            before = path.stat()
            progress(f'Archiving Steam build {build}: {number}/{len(files)} — {relative}')
            shutil.copyfile(path, target)
            checksum = digest(target)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('Game files changed during capture; no build was archived.')
            stats[path] = (after.st_size, after.st_mtime_ns)
            meta['files'][relative.as_posix()] = checksum
            manifests.setdefault(relative.parent, {})[relative.name] = checksum
        if steam_build(game) != build or core.load_deployed() or any(
                (path.stat().st_size, path.stat().st_mtime_ns) != stat for path, stat in stats.items()):
            raise ValueError('Game build changed during capture; try again after Steam finishes.')
        if set(files) != {path for path in data.rglob('*') if path.is_file() and repair_file(path.relative_to(data))}:
            raise ValueError('Game file list changed during capture; try again.')
        for parent, checksums in manifests.items():
            (staging / 'data' / parent / 'snapshot.json').write_text(
                json.dumps({'version': 1, 'files': checksums}), encoding='utf-8')
        (staging / 'build.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
        destination = root / f'build-{build}-{uuid.uuid4().hex[:8]}'
        staging.rename(destination)
        # TemporaryDirectory tolerates its staging path having been renamed.
    return destination


def import_data_baseline(source, build_id, root=None):
    """Import user-provided data history without claiming it is a complete Steam capture."""
    if not re.fullmatch(r'\d+', str(build_id)):
        raise ValueError('Enter the numeric Steam build ID for this baseline.')
    root = Path(root) if root is not None else archive_root()
    root.mkdir(parents=True, exist_ok=True)
    source = Path(source)
    meta = {'version': 1, 'scope': 'data-only', 'provenance': 'User-supplied baseline; build label provided by user.',
            'build_id': str(build_id), 'created_utc': datetime.now(timezone.utc).isoformat(), 'bytes': 0, 'files': {}}
    with tempfile.TemporaryDirectory(prefix='.import-', dir=root) as temporary:
        staging = Path(temporary)
        target = staging / 'data/game'
        target.mkdir(parents=True)
        def add(name, raw):
            if not re.fullmatch(r'generated_[a-zA-Z0-9_]+\.dl_bin', name):
                raise ValueError('Unsupported baseline filename: ' + name)
            if name.lower() in {Path(key).name.lower() for key in meta['files']}:
                raise ValueError('Baseline contains duplicate data filenames.')
            core.unseal(raw)  # Authenticate sealed data; some valid empty tables have no LDLD blocks.
            (target / name).write_bytes(raw)
            meta['files']['game/' + name] = hashlib.sha256(raw).hexdigest()
            meta['bytes'] += len(raw)
        if source.is_dir():
            for path in sorted(source.glob('generated_*.dl_bin')):
                if path.is_symlink() or path.stat().st_size > 2 * 1024**3:
                    raise ValueError('Invalid baseline data file.')
                add(path.name, path.read_bytes())
        else:
            with zipfile.ZipFile(source) as archive:
                entries = [item for item in archive.infolist() if not item.is_dir() and item.filename.lower().endswith('.dl_bin')]
                if sum(item.file_size for item in entries) > 2 * 1024**3:
                    raise ValueError('Baseline data ZIP exceeds the 2 GiB limit.')
                for item in entries:
                    name = item.filename.replace('\\', '/')
                    if not core._safe_rel(name):
                        raise ValueError('Unsafe baseline ZIP path.')
                    add(name.split('/')[-1], archive.read(item))
        if not meta['files']:
            raise ValueError('No generated .dl_bin baseline files found.')
        (target / 'snapshot.json').write_text(json.dumps({'version': 1, 'files': {
            Path(key).name: value for key, value in meta['files'].items()}}), encoding='utf-8')
        (staging / 'build.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
        destination = root / f'build-{build_id}-data-{uuid.uuid4().hex[:8]}'
        staging.rename(destination)
    return destination


def _main_file(path):
    return path.suffix.lower() == '.dl_bin' or re.fullmatch(r'[0-9a-fA-F]{16}(?:\.patch_\d+)?', path.name) is not None


def automatic_plan(mod, game, root=None, *, build_id=None):
    """Never select between baselines that produce different repaired edits."""
    mod, game = Path(mod), Path(game)
    parsed = mod_repair.open_file(mod)
    dlbin = isinstance(parsed, DLBin)
    relative = Path('game') / mod.name if dlbin else Path(mod.name.split('.patch_')[0])
    current = game / 'data' / relative
    if not dlbin and list(current.parent.glob(current.name + '.patch_*')):
        raise ValueError('Current archive has patch layers. Automatic repair requires a resolved clean archive; use Advanced mode.')
    if not current.is_file():
        raise ValueError('Current game file was not found: ' + str(relative))
    candidates = []
    failures = []
    seen = set()
    if root is None:
        roots = [archive_root(), Path(core.APP_DATA) / 'tmp' / 'repair-data-prefetch' / 'baselines']
    else:
        roots = list(root) if isinstance(root, (list, tuple)) else [root]
    for folder, meta in builds(roots):
        if build_id is not None and str(meta.get('build_id')) != str(build_id):
            continue
        checksum = meta['files'].get(relative.as_posix())
        if not checksum or checksum in seen:
            continue
        seen.add(checksum)
        old = folder / 'data' / relative
        try:
            if digest(old) != checksum:
                raise ValueError('Archived file integrity check failed.')
            if dlbin and content_hash(DLBin.open(old).plain) != content_hash(parsed.plain):
                continue
            plan = mod_repair.analyse(old, current, mod)
            if plan.errors:
                failures.extend(plan.errors)
                continue
            candidates.append((plan, meta['build_id']))
        except (OSError, ValueError) as exc:
            failures.append(str(exc))
    if not candidates:
        raise ValueError('No compatible archived baseline found for ' + mod.name
                         + (f' in Steam build {build_id}' if build_id is not None else '')
                         + '. Verified and captured baselines were checked.\n' + '\n'.join(failures[:4]))
    first, build = candidates[0]
    if any(plan.current.replacements != first.current.replacements for plan, _ in candidates[1:]):
        raise ValueError('Several archived builds produce different repairs. Automatic selection is unsafe; use Advanced mode.')
    first.report.insert(0, f'Automatically matched archived Steam build {build}: {mod.name}')
    return first


def repair(source, game, root=None, output_root=None, progress=lambda message: None, *, mod_name=None):
    """Repair a main file or mod folder into a new output; never publish partial mods."""
    if root is None:
        with baseline_session(progress=progress):
            return repair(source, game, archive_root(), output_root, progress, mod_name=mod_name)
    source, game = Path(source).resolve(), Path(game).resolve()
    mod_name = mod_name or (source.stem if source.is_file() and source.suffix.lower() == '.zip' else source.name)
    mod_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', mod_name).rstrip(' .')[:160] or 'Mod'
    if source.suffix.lower() == '.zip' and source.is_file():
        scratch = core.APP_DATA / 'tmp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='repair-import-', dir=scratch) as temporary:
            extracted = Path(temporary)
            with zipfile.ZipFile(source) as archive:
                if sum(item.file_size for item in archive.infolist()) > 8 * 1024**3:
                    raise ValueError('Mod ZIP exceeds the 8 GiB extraction limit.')
                names = set()
                for item in archive.infolist():
                    name = item.filename.replace('\\', '/')
                    target = extracted / name
                    key = name.lower()
                    if (not core._safe_rel(name.rstrip('/')) or not target.resolve().is_relative_to(extracted)
                            or key in names or (item.external_attr >> 16) & 0o170000 == 0o120000):
                        raise ValueError('Mod ZIP contains unsafe or duplicate paths.')
                    names.add(key)
                    if item.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(item) as incoming, target.open('wb') as outgoing:
                            shutil.copyfileobj(incoming, outgoing)
            return repair(extracted, game, root, output_root, progress, mod_name=mod_name)
    if core.load_deployed():
        raise ValueError('Purge deployed mods before repair so current game files are clean.')
    build = steam_build(game)
    sources = sorted(path for path in source.rglob('*') if path.is_file()) if source.is_dir() else [source]
    mains = [path for path in sources if _main_file(path)]
    if not mains:
        raise ValueError('Choose an extracted mod folder or a .dl_bin / archive main file.')
    profile_file = source / 'profile.json' if source.is_dir() else None
    if profile_file is not None and profile_file.is_file():
        profile = json.loads(profile_file.read_text(encoding='utf-8'))
        if not isinstance(profile, dict):
            raise ValueError('Invalid data profile metadata.')
        target = profile.get('target', '')
        if not isinstance(target, str) or not core._safe_rel(target):
            raise ValueError('Invalid data profile target.')
        matching = [path for path in mains if path.name == Path(target).name]
        if len(matching) != 1 or digest(matching[0]) != profile.get('sha256'):
            raise ValueError('Data profile payload checksum or target does not match.')
    if source.is_relative_to(game) or any(path.is_symlink() for path in sources):
        raise ValueError('Choose a separate mod copy outside the game folder, without links.')
    plans = []
    for path in mains:
        progress('Matching archived build and repairing ' + path.name)
        plans.append(automatic_plan(path, game, root))
    output_root = Path(output_root) if output_root is not None else repaired_root()
    output_root.mkdir(parents=True, exist_ok=True)
    report = []
    with tempfile.TemporaryDirectory(prefix='.repair-', dir=output_root) as temporary:
        staging = Path(temporary)
        destinations = set()
        for plan in plans:
            parent = staging / ('data/game' if isinstance(plan.current, DLBin) else 'data')
            parent.mkdir(parents=True, exist_ok=True)
            for exported in plan.export(parent):
                if exported in destinations:
                    raise ValueError('Multiple mod files target the same output; repair separately.')
                destinations.add(exported)
            report.extend(plan.report)
        handled = {path for main in mains for path in [main, *(Path(str(main) + suffix) for suffix in ('.stream', '.gpu_resources'))]}
        for path in sources:
            if path not in handled:
                if profile_file is not None and path == profile_file:
                    continue  # A checksum/fingerprint profile for old bytes must not accompany a new export.
                # Retain ordinary documentation, but never silently omit unknown mod payloads.
                if source.is_dir() and path.suffix.lower() in ('.txt', '.md', '.png', '.jpg', '.jpeg'):
                    target = staging / path.relative_to(source)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
                else:
                    raise ValueError('Mod includes unsupported files. No partial mod was exported: ' + path.name)
        if steam_build(game) != build or core.load_deployed():
            raise ValueError('Game changed during repair. No mod was exported.')
        # Current sources must still match the versions actually used by the plans.
        for plan in plans:
            reread = mod_repair.open_file(plan.current.path)
            if isinstance(reread, DLBin):
                equal = reread.sealed == plan.current.sealed
            else:
                equal = reread.blobs == plan.current.blobs
            if not equal:
                raise ValueError('Current game files changed during repair. No mod was exported.')
        (staging / 'repair-report.txt').write_text('\n'.join(report), encoding='utf-8')
        package_root = staging / 'package'
        package_root.mkdir()
        for path in sorted((staging / 'data').rglob('*')):
            if path.is_file():
                relative = path.relative_to(staging / 'data')
                target = package_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        for path in sorted(staging.iterdir()):
            if path.is_file() and path.name != 'repair-report.txt':
                shutil.copyfile(path, package_root / path.name)
        destination = output_root / ('BotRepaired-' + mod_name)
        number = 2
        while destination.exists():
            destination = output_root / f'BotRepaired-{mod_name} ({number})'
            number += 1
        package_root.rename(destination)
    return destination, report
