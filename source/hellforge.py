"""HellForge package support through its documented external-launcher CLI.

Reference: https://github.com/SkyeShade/HellForge/blob/main/docs/external-launchers.md
HellForge stages/builds mods itself; this adapter never writes into its game copy.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

from merge_engine import atomic_write


def classify(entries, manifest, name):
    names = {n.replace('\\', '/').split('/')[-1].lower() for n, _ in entries}
    if names & {'hellforge-mod.json', 'bts-mod.json', 'hellforge-data.json', 'hellforge-stats.json'}:
        return True
    if manifest.get('ModDiverStudio') == 1:
        return False
    metadata = json.dumps(manifest).casefold()
    if ('hellforge' in metadata and manifest.get('id')) or 'hd2runtime' in str(name).casefold():
        return True
    # HD2Runtime Lua packages also work through HellForge's Lua bridge.
    return any(n.lower().endswith('.lua') and
               (b'require("mods/skyeshade/hd2runtime' in data or
                b"require('mods/skyeshade/hd2runtime" in data)
               for n, data in entries)


def validate_entries(entries):
    import core
    seen = set()
    for name, _ in entries:
        normalized = name.replace('\\', '/')
        if not core._safe_rel(normalized) or normalized.casefold() in seen:
            raise ValueError('HellForge package contains unsafe or duplicate paths: ' + name)
        seen.add(normalized.casefold())


def _validate_package(source):
    if source.is_dir():
        if any(file.is_symlink() for file in source.rglob('*')):
            raise ValueError('Mod folders containing symbolic links are not supported.')
    elif source.suffix.lower() == '.zip':
        with zipfile.ZipFile(source) as archive:
            validate_entries([(i.filename.rstrip('/'), b'') for i in archive.infolist()])
            if any((i.external_attr >> 16) & 0o170000 == 0o120000 for i in archive.infolist()):
                raise ValueError('HellForge packages cannot contain symbolic links.')


def _run(root, *args):
    cli = root / 'app' / 'cli' / 'HellForge.Cli.exe'
    if not cli.is_file():
        raise RuntimeError('This HellForge installation has no external-launcher CLI. Update HellForge or add the packages on its Mods page.')
    command = [str(cli), *args]
    if args[0] != 'check-stats' and not (args[0] == 'build-data' and '--game-data' in args):
        command.extend(['--install', str(root)])
    if os.name != 'nt':
        proton = os.environ.get('PROTON')
        if not proton:
            raise RuntimeError('Set PROTON to the Proton executable used by this HellForge installation.')
        command = [proton, 'run', *command]
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8-sig',
                            errors='replace', timeout=180,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        if 'unknown command' in (result.stderr + result.stdout).casefold() and args[0] in {
                'mods', 'mod-add', 'mod-switch', 'mod-pack', 'mod-order', 'mod-remove'}:
            from hellforge_legacy import run
            return run(root, *args)
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'HellForge command failed.')
    return json.loads(result.stdout) if result.stdout.strip() else {}


def _mods(root):
    result = _run(root, 'mods')
    rows = result if isinstance(result, list) else result.get('mods', [])
    if not isinstance(rows, list) or any(not isinstance(m, dict) or not m.get('id') for m in rows):
        raise RuntimeError('Unsupported HellForge mods response.')
    return rows


def validate_package(source, root):
    """Validate native stats/data specs in scratch space; do not stage a session."""
    import core
    source, root = Path(source), Path(root)
    _validate_package(source)
    parsed = core.parse_mod(source)
    entries = parsed.get('package_entries')
    if not entries:
        raise ValueError('This is a binary patch or sealed-data mod. Data Bot cannot assume it matches '
                         'HellForge’s pinned build. Use a HellForge-native version or rebuild audio/visual '
                         'patches against the selected HellForge game copy.')
    validate_entries(entries)
    report = []
    with tempfile.TemporaryDirectory(prefix='moddiver-hf-check-') as temporary:
        folder = Path(temporary) / 'mod'; folder.mkdir()
        for name, blob in entries:
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
        if (folder / 'hellforge-stats.json').is_file():
            result = _run(root, 'check-stats', '--mod', str(folder))
            report.append('Stats format and names accepted by HellForge: ' + json.dumps(result))
        if (folder / 'hellforge-data.json').is_file():
            _run(root, 'build-data', '--mod', str(folder), '--game-data', str(core.game_dir({'game':str(root)})/'data'),
                 '--out', str(Path(temporary)/'built'))
            report.append('Data spec built against the selected HellForge copy in temporary storage.')
    if not report:
        raise ValueError('No stats or data spec to validate. HellForge checks and builds this code/Lua package when you start a session.')
    report.append('Source package preserved. Runtime layout checks and gameplay still require a HellForge session.')
    return report


def _receipt_path(root):
    import core
    key = hashlib.sha256(str(root.resolve()).casefold().encode()).hexdigest()[:20]
    return core.APP_DATA / ('hellforge-' + key + '.json')


def load_receipt(root):
    path = _receipt_path(root)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'mods': {}}


def _save(root, receipt):
    atomic_write(_receipt_path(root), json.dumps(receipt, indent=2).encode('utf-8'))


def _identity(parsed):
    manifest = parsed.get('manifest', {})
    return manifest.get('id') or ('pack.' + str(manifest['Guid']) if manifest.get('Guid') else None)


def deploy(cfg, root, log=print, dry_run=False):
    import core
    root = Path(root)
    installed = _mods(root)  # The CLI also refuses changes during a session.
    receipt = load_receipt(root)
    prepared = []
    identities = set()
    # Validate every input before the first mutation, including runtime-only mods.
    for mod in core.deployment_mods(cfg):
        if not mod.get('enabled', True):
            continue
        source = Path(mod['path'])
        _validate_package(source)
        parsed = core.parse_mod(source)
        if parsed.get('candidates'):
            raise ValueError(parsed['name'] + ': this package replaces sealed game-data files. '
                             'Use the HellForge Stats Editor to export named gameplay changes for HellForge, '
                             'or use a HellForge-native version of this mod.')
        if not parsed.get('targets') and not parsed.get('runtime'):
            raise ValueError('No deployable package: ' + source.name)
        identity = _identity(parsed)
        duplicate_key = identity or parsed['name'].casefold()
        if duplicate_key in identities:
            raise RuntimeError('Enable only one version of this HellForge mod: ' + parsed['name'])
        identities.add(duplicate_key)
        for existing in installed:
            if existing['id'] not in receipt['mods'] and (existing['id'] == identity or
                    existing.get('name') == parsed['name'] or
                    Path(existing.get('archive') or '').name.casefold() == source.name.casefold()):
                raise RuntimeError('Already installed outside Laboratory: ' + parsed['name'] +
                                   '. Manage that copy in HellForge before importing it here.')
        prepared.append((mod, source, parsed))
    if dry_run:
        for mod, _, _ in prepared:
            log('Would install HellForge package: ' + mod['name'])
        log('HellForge handles staging, compilation and runtime dependencies. Built-in sealed-data profiles are not applied to its game copy.')
        return len(prepared)
    order = []
    for mod, source, parsed in prepared:
        key = str(source.resolve())
        previous = next((mid for mid, info in receipt['mods'].items() if info['source'] == key), None)
        if not previous and _identity(parsed) in receipt['mods']:
            previous = _identity(parsed)
        with tempfile.TemporaryDirectory(prefix='moddiver-hf-') as temp:
            package = source
            if source.is_dir():
                package = Path(temp) / (source.name + '.zip')
                with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as z:
                    for file in sorted(source.rglob('*')):
                        if file.is_symlink():
                            raise ValueError('Mod folders containing symbolic links are not supported.')
                        if file.is_file():
                            z.write(file, file.relative_to(source).as_posix())
            before = {m['id'] for m in _mods(root)}
            _run(root, 'mod-add', '--file', str(package))
            rows = _mods(root)
            matches = [m for m in rows if m['id'] == previous or m['id'] not in before]
            if len(matches) != 1:
                raise RuntimeError('HellForge did not identify one imported mod. Check its Mods page for package notices.')
            mid = matches[0]['id']
            receipt['mods'][mid] = {'source': key, 'name': mod['name']}
            _save(root, receipt)  # Keep recovery information even if a later package fails.
            _run(root, 'mod-switch', '--id', mid, '--on', 'yes')
            if 'pack' in matches[0].get('tags', []):
                selected = mod.get('selected', {})
                for option in parsed.get('options', []):
                    if option.get('group'):
                        if selected.get(option['name'], option.get('default', True)):
                            _run(root, 'mod-pack', '--id', mid, '--option', option['group'], '--variant', option['name'])
                    else:
                        _run(root, 'mod-pack', '--id', mid, '--option', option['name'],
                             '--on', 'yes' if selected.get(option['name'], option.get('default', True)) else 'no')
            order.append(mid)
            log('Installed HellForge package: ' + mod['name'])
    for mid in list(receipt['mods']):
        if mid not in order:
            _run(root, 'mod-remove', '--id', mid)
            del receipt['mods'][mid]
            _save(root, receipt)
    if order:
        # core.deployment_mods is execution order (bottom first); HellForge's
        # interface takes display priority (top first).
        _run(root, 'mod-order', '--ids', ','.join(reversed(order)))
    log('HellForge deployment complete. Open HellForge and press PLAY; it builds and stages the packages. Built-in sealed-data profiles are not applied.')
    return len(order)


def purge(root, log=print):
    receipt = load_receipt(root)
    existing = {m['id'] for m in _mods(root)}
    count = 0
    for mid in list(receipt['mods']):
        if mid in existing:
            _run(root, 'mod-remove', '--id', mid)
        del receipt['mods'][mid]
        _save(root, receipt)
        count += 1
    log(f'Removed {count} Laboratory-managed HellForge package(s).')
    return count
