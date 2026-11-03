"""Bridge older HellForge releases through their documented mods folder/state.

Only Laboratory-owned ZIPs are replaced or removed. Game/app/session files are
never written. Current HellForge versions use the mod-management CLI instead.
"""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import uuid
import zipfile


def _state(root):
    path = root / 'mods/hellforge-mods.json'
    state = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {'format': 1}
    if not isinstance(state, dict) or state.get('format', 1) != 1:
        raise ValueError('Unsupported HellForge mod settings. Update HellForge before managing mods here.')
    for key, kind in (('disabled', list), ('order', list), ('packs', dict)):
        if key in state and not isinstance(state[key], kind):
            raise ValueError('Invalid HellForge mod settings: ' + key)
    return state


def _idle():
    if os.name != 'nt':
        raise RuntimeError('Update HellForge to use its mod-management CLI on Linux.')
    result = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True,
                            timeout=15, creationflags=0x08000000)
    if result.returncode:
        raise RuntimeError('Could not check for a running HellForge session. Close the game and try again.')
    names = {row[0].casefold() for row in csv.reader(io.StringIO(result.stdout)) if row}
    if names & {'helldivers2.exe', 'hellforge.session.exe'}:
        raise RuntimeError('Close the game and wait for the HellForge session to finish before changing mods.')


def _identity(parsed):
    manifest = parsed.get('manifest', {})
    if manifest.get('id'):
        return str(manifest['id'])
    if manifest.get('Guid'):
        return 'pack.' + str(manifest['Guid'])
    if parsed.get('type') != 'HellForge':
        return 'pack.' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'moddiver-hellforge-pack:' + parsed['name']))
    return 'pack.' + re.sub(r'[^a-z0-9]+', '-', parsed['name'].lower()).strip('-')


def _catalog(root):
    import core
    state = _state(root)
    mods = root / 'mods'
    rows = []
    if not mods.is_dir():
        return rows
    for source in sorted(mods.iterdir()):
        if source.is_symlink() or source.name.startswith('.'):
            continue
        if not source.is_dir() and source.suffix.lower() != '.zip':
            continue
        parsed = core.parse_mod(source)
        if not parsed.get('targets'):
            continue
        mid = _identity(parsed)
        tags = ['pack'] if parsed.get('type') != 'HellForge' else []
        if source.is_dir() and (source / '.hellforge-bundled.txt').is_file():
            tags.append('bundled')
        if mid == 'zz.local.stats' or source.name == 'zz.local.stats':
            tags.append('local-stats')
        rows.append({'id': mid, 'name': parsed['name'], 'archive': str(source) if source.is_file() else '',
                     'folder': str(source) if source.is_dir() else '', 'tags': tags,
                     'enabled': mid not in state.get('disabled', [])})
    return rows


def run(root, command, *args):
    import core
    import hellforge
    root = Path(root).resolve()
    if (root / 'mods').is_symlink():
        raise ValueError('Linked HellForge mods folders cannot be managed through the legacy bridge.')
    if command == 'mods':
        return {'mods': _catalog(root), 'bridge': 'mods-folder'}
    _idle()
    options = dict(zip(args[::2], args[1::2]))
    state = _state(root)
    mods = root / 'mods'
    mods.mkdir(exist_ok=True)
    if command == 'mod-add':
        source = Path(options['--file'])
        parsed = core.parse_mod(source)
        if not parsed.get('targets'):
            raise ValueError('No supported HellForge package found.')
        hellforge._validate_package(source)
        mid = _identity(parsed)
        old = [r for r in _catalog(root) if r['id'] == mid]
        receipt = hellforge.load_receipt(root)
        if old and mid not in receipt['mods']:
            raise ValueError('This mod is managed outside Laboratory. Manage that copy in HellForge first.')
        if any(not r['archive'] or not Path(r['archive']).name.startswith('moddiver-') for r in old):
            raise ValueError('A copy of this mod is outside Laboratory’s managed ZIPs. Manage it in HellForge first.')
        dest = mods / ('moddiver-' + hashlib.sha256(mid.encode()).hexdigest()[:24] + '.zip')
        if source.suffix.lower() in ('.7z', '.rar'):
            entries = core._read_7z_entries(source)
            hellforge.validate_entries(entries)
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, blob in entries:
                    archive.writestr(name, blob)
            payload = output.getvalue()
        else:
            payload = source.read_bytes()
        if parsed.get('type') != 'HellForge' and not parsed.get('manifest', {}).get('Guid'):
            # Legacy packs without a GUID (including bare patches) need a stable
            # name after being copied to a Laboratory-owned archive filename.
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                entries = core._strip_single_wrapper([(i.filename, archive.read(i))
                          for i in archive.infolist() if not i.is_dir()])
            manifest = dict(parsed.get('manifest', {}))
            manifest.update(Guid=mid.removeprefix('pack.'), Name=parsed['name'])
            manifest.setdefault('Version', 1)
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, blob in entries:
                    if name.casefold() != 'manifest.json': archive.writestr(name, blob)
                archive.writestr('manifest.json', json.dumps(manifest, indent=2))
            payload = output.getvalue()
        # Preserve the original package, including native manifests and wrappers.
        if dest.exists() and not any(Path(r['archive']) == dest for r in old if r['archive']):
            raise ValueError('The managed package destination is already occupied.')
        core.atomic_write(dest, payload)
        return {'id': mid}
    mid = options.get('--id')
    if command == 'mod-remove':
        if mid not in hellforge.load_receipt(root)['mods']:
            raise ValueError('Only Laboratory-managed packages can be removed here.')
        for row in _catalog(root):
            if row['id'] != mid:
                continue
            source = Path(row['archive']) if row['archive'] else None
            if source is None or source.parent != mods or not source.name.startswith('moddiver-'):
                raise ValueError('This package must be managed in HellForge.')
            source.unlink()
        state['disabled'] = [i for i in state.get('disabled', []) if i != mid]
        state['order'] = [i for i in state.get('order', []) if i != mid]
        state.setdefault('packs', {}).pop(mid, None)
    elif command == 'mod-switch':
        disabled = [i for i in state.get('disabled', []) if i != mid]
        if options['--on'] == 'no':
            disabled.append(mid)
        state['disabled'] = disabled
    elif command == 'mod-order':
        ids = [i for i in options['--ids'].split(',') if i]
        state['order'] = list(dict.fromkeys(ids + state.get('order', [])))
    elif command == 'mod-pack':
        pack = state.setdefault('packs', {}).setdefault(mid, {})
        option = options['--option']
        if '--variant' in options:
            pack.setdefault('sub', {})[option] = options['--variant']
        else:
            off = [n for n in pack.get('off', []) if n != option]
            if options['--on'] == 'no':
                off.append(option)
            pack['off'] = off
    else:
        raise ValueError('Unsupported legacy HellForge operation: ' + command)
    core.atomic_write(mods / 'hellforge-mods.json', json.dumps(state, indent=2).encode())
    return {'bridge': 'mods-folder'}
