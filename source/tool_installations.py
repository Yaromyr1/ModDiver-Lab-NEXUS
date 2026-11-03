"""Replace a managed Chef package and retire superseded library versions."""
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile
import core


def is_chef(record):
    name = str(record.get('name', '')).casefold()
    return 'chef' in name and 'loader' in name


def replace_chef(cfg, source, log=lambda message: None):
    source = Path(source).resolve()
    parsed = core.parse_mod(source)
    if not is_chef(parsed) or not parsed.get('targets'):
        raise ValueError('Choose a valid Chef Shared Loader package.')
    root = core.MODS_DIR.resolve()
    destination = root / 'imported' / 'chef-loader.zip'
    destination.parent.mkdir(parents=True, exist_ok=True)
    import lab_storage
    old_paths = {Path(m['path']).resolve() for m in lab_storage.candidates(cfg) if is_chef(m)}
    compositions = [cfg, *cfg.get('mod_presets', {}).values()]
    for composition in compositions:
        old_paths.update(Path(m['path']).resolve() for m in composition.get('mods', []) if is_chef(m))
    before = copy.deepcopy(cfg)
    # A transient rollback exists only during the transaction, never after success.
    with tempfile.TemporaryDirectory(prefix='.chef-update-', dir=destination.parent) as temporary:
        stage = Path(temporary) / 'new.zip'
        previous = Path(temporary) / 'previous.zip'
        if source.is_dir():
            with zipfile.ZipFile(stage, 'w', zipfile.ZIP_DEFLATED) as archive:
                for path in source.rglob('*'):
                    if path.is_symlink():
                        raise ValueError('Loader folders cannot contain symbolic links.')
                    if path.is_file():
                        archive.write(path, path.relative_to(source).as_posix())
        elif source.suffix.lower() == '.7z':
            with zipfile.ZipFile(stage, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, data in core._read_7z_entries(source):
                    archive.writestr(name, data)
        else:
            shutil.copyfile(source, stage)
        checked = core.parse_mod(stage)
        if not is_chef(checked) or not checked.get('targets'):
            raise ValueError('Staged loader failed validation.')
        entry = {key: checked[key] for key in ('name', 'type', 'targets')}
        entry.update(path=str(destination), enabled=True, category='loaders',
                     options=[o['name'] for o in checked.get('options', [])],
                     selected={o['name']: bool(o.get('default', True)) for o in checked.get('options', [])},
                     runtime=bool(checked.get('runtime')))
        if destination.exists():
            destination.rename(previous)
        try:
            stage.rename(destination)
            for index, composition in enumerate(compositions):
                prior = [m for m in composition.get('mods', []) if is_chef(m)]
                if index == 0 or prior:
                    replacement = copy.deepcopy(entry)
                    if index and prior:
                        replacement['enabled'] = any(m.get('enabled', True) for m in prior)
                    composition['mods'] = [replacement] + [m for m in composition.get('mods', []) if not is_chef(m)]
            core.save_config(cfg)
        except Exception:
            cfg.clear()
            cfg.update(before)
            destination.unlink(missing_ok=True)
            if previous.exists():
                previous.rename(destination)
            raise
    for path in old_paths:
        # Never delete an external download, bundled resource or library root.
        if path == destination or path == root or not path.is_relative_to(root) or destination.is_relative_to(path):
            continue
        if path.is_symlink():
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        except OSError as exc:
            log('Could not remove superseded Chef package: ' + str(exc))
    log('Replaced Chef Shared Loader with ' + entry['name'] + '. Deploy to apply it.')
    return entry
