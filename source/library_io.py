"""Portable library backups, separate from deployed-game exports."""
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

import core

MANIFEST = 'moddiver-library.json'


def _relative(name):
    name = name.replace('\\', '/')
    parts = name.rstrip('/').split('/')
    if not name or name.startswith('/') or ':' in name or any(p in ('', '.', '..') for p in parts):
        raise ValueError('Library contains an unsafe path: ' + name)
    return Path(*parts)


def _extract(archive, folder):
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        if len(infos) > core.MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > core.MAX_ZIP_BYTES:
            raise ValueError('Library ZIP exceeds archive limits.')
        seen = set()
        for info in infos:
            rel = _relative(info.filename)
            key = rel.as_posix().casefold()
            if key in seen or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Library ZIP contains duplicate paths or symbolic links.')
            seen.add(key)
            target = folder / rel
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, target.open('wb') as dst:
                    shutil.copyfileobj(src, dst)


def export_library(cfg, destination, log=print):
    mods = cfg.get('mods', [])
    if not mods:
        raise ValueError('The mod library is empty.')
    destination = Path(destination).resolve()
    # Stage every package before writing the destination, including when it is in a mod folder.
    with tempfile.TemporaryDirectory(prefix='moddiver-library-') as temp:
        stage = Path(temp)
        records = []
        for index, mod in enumerate(mods):
            source = Path(mod['path']).resolve()
            if not source.exists():
                raise FileNotFoundError(f'Mod source is missing: {source}')
            if source == destination or (source.is_dir() and destination.is_relative_to(source)):
                raise ValueError('Save the library ZIP outside its mod sources.')
            suffix = '.zip' if source.is_dir() else source.suffix.lower()
            if suffix not in ('.zip', '.7z', '.rar'):
                raise ValueError(f'Unsupported mod source: {source}')
            package = f'mods/{index:04d}{suffix}'
            target = stage / package
            target.parent.mkdir(exist_ok=True)
            if source.is_dir():
                with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
                    for file in sorted(source.rglob('*')):
                        if file.is_symlink():
                            raise ValueError('Mod folders containing symbolic links cannot be exported.')
                        if file.is_file():
                            z.write(file, file.relative_to(source).as_posix())
            else:
                shutil.copy2(source, target)
            parsed = core.parse_mod(target)
            if not parsed.get('targets') and not parsed.get('runtime'):
                raise ValueError(f'No deployable mod data in {source.name}')
            record = {key: copy.deepcopy(mod[key]) for key in ('name', 'enabled', 'selected', 'category') if key in mod}
            record['package'] = package
            records.append(record)
        (stage / MANIFEST).write_text(json.dumps({'format': 'moddiver-library', 'version': 1, 'mods': records},
                                               ensure_ascii=False, indent=2), encoding='utf-8')
        files = [p for p in stage.rglob('*') if p.is_file()]
        if len(files) > core.MAX_ZIP_ENTRIES or sum(p.stat().st_size for p in files) > core.MAX_ZIP_BYTES:
            raise ValueError('Library is too large for a portable ZIP; export a smaller library.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, partial = tempfile.mkstemp(prefix='.library-', suffix='.zip', dir=destination.parent)
        os.close(fd)
        try:
            with zipfile.ZipFile(partial, 'w', zipfile.ZIP_DEFLATED) as z:
                for file in sorted(stage.rglob('*')):
                    if file.is_file():
                        z.write(file, file.relative_to(stage).as_posix())
            os.replace(partial, destination)
        finally:
            Path(partial).unlink(missing_ok=True)
    log(f'Exported library: {len(records)} mod(s) to {destination}')
    return destination


def import_library(cfg, source, log=print):
    """Append validated packages; preserve existing entries and roll back failed imports."""
    source = Path(source).resolve()
    with tempfile.TemporaryDirectory(prefix='moddiver-import-') as temp:
        root = source
        if source.is_file():
            root = Path(temp) / 'library'
            root.mkdir()
            _extract(source, root)
        manifests = list(root.rglob(MANIFEST)) if root.is_dir() else []
        if len(manifests) > 1:
            raise ValueError('Choose one library at a time.')
        if manifests:
            manifest = manifests[0]
            data = json.loads(manifest.read_text(encoding='utf-8'))
            if data.get('format') != 'moddiver-library' or data.get('version') != 1 or not isinstance(data.get('mods'), list):
                raise ValueError('Unsupported library manifest.')
            packages = []
            for record in data['mods']:
                package = manifest.parent / _relative(record['package'])
                if not package.resolve().is_relative_to(root.resolve()):
                    raise ValueError('Library package points outside the library.')
                packages.append((package, record))
        else:
            packages = [(p, {}) for p in sorted(root.rglob('*')) if p.suffix.lower() in ('.zip', '.7z', '.rar') and p.is_file()]
            if not packages and source.is_file():
                packages = [(source, {})]
        if not packages:
            raise ValueError('No zipped mods found in this library.')
        entries, created = [], []
        previous = cfg.get('mods', [])
        try:
            for package, settings in packages:
                if package.suffix.lower() not in ('.zip', '.7z', '.rar') or not package.is_file():
                    raise ValueError(f'Missing or unsupported mod package: {package.name}')
                parsed = core.parse_mod(package)
                if not parsed.get('targets') and not parsed.get('runtime'):
                    raise ValueError(f'No deployable mod data in {package.name}')
                # Always copy, even when the input folder already lives in the managed library.
                core.IMPORTED_MODS_DIR.mkdir(parents=True, exist_ok=True)
                managed = core._unique_library_path(package.name, False)
                created.append(managed)
                shutil.copy2(package, managed)
                options = parsed.get('options', [])
                selected = settings.get('selected', {})
                if not isinstance(selected, dict):
                    raise ValueError('Invalid library option settings.')
                entry = {'path': str(managed), 'name': str(settings.get('name', parsed['name'])),
                         'type': parsed['type'], 'targets': parsed['targets'],
                         'runtime': bool(parsed.get('runtime')), 'enabled': bool(settings.get('enabled', True)),
                         'options': [o['name'] for o in options],
                         'selected': {o['name']: bool(selected.get(o['name'], o.get('default', True))) for o in options}}
                if settings.get('category') in core.LIBRARY_CATEGORIES:
                    entry['category'] = settings['category']
                entries.append(entry)
            cfg['mods'] = previous + entries
            core.save_config(cfg)
        except Exception:
            cfg['mods'] = previous
            for path in created:
                path.unlink(missing_ok=True)
            raise
    log(f'Imported library: {len(entries)} mod(s). Use Merge and Install All to deploy.')
    return entries
