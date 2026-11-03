"""Verified data-only profiles extracted from the user-supplied HD2FM1 mods.

No upstream installer scripts are run. The normal deployment owns backups/purge.
"""
import hashlib
import json
import zipfile
from pathlib import Path

PROFILES = {
    'stratagem_bounce_removed': 'Stratagem Bounce Removed',
    'consistent_vaulting': 'Consistent Vaulting',
}


def fingerprint(data):
    middle = len(data) // 2
    return str(len(data)) + ':' + (data[:32] + data[middle:middle+32] + data[-32:]).hex().upper()


def build_mod(key, stock_folder, updated=None):
    import core
    if key not in PROFILES:
        raise ValueError('Unknown gameplay profile.')
    if updated is not None:
        data = Path(updated).read_bytes()
        target = Path(updated).name
        core.validate_sealed_input(data, PROFILES[key])
        core.unseal(data)
        return {'name': PROFILES[key], '_name': PROFILES[key], 'path': str(updated),
                'targets': [target], 'candidates': {target: data}, 'cand_option': {},
                'files': [], '_sel': {}}
    base = Path(__file__).parent / 'builtin' / 'gameplay' / key
    path = base if base.is_dir() else base.with_suffix('.zip')
    if path.is_dir():
        profile = json.loads((path / 'profile.json').read_text(encoding='utf-8'))
        read_target = lambda name: (path / name).read_bytes()
    else:
        with zipfile.ZipFile(path) as archive:
            profile = json.loads(archive.read('profile.json'))
            read_target = archive.read
    target = profile['target']
    if target not in ('data/game/generated_entities.dl_bin', 'data/game/generated_stratagem_settings.dl_bin'):
        raise ValueError('Invalid gameplay profile target.')
    data = read_target(target)
    if hashlib.sha256(data).hexdigest() != profile['sha256']:
        raise ValueError(PROFILES[key] + ': bundled payload checksum mismatch.')
    stock = Path(stock_folder) / Path(target).name
    if not stock.is_file() or fingerprint(stock.read_bytes()) not in profile['stock_fingerprints']:
        raise ValueError(PROFILES[key] + ': clean stock does not match the supported October 2026 game builds. Capture matching clean stock or disable this option.')
    core.validate_sealed_input(data, PROFILES[key])
    core.unseal(data)
    target = Path(target).name  # Generated-data candidates use stock-relative names.
    return {'name': PROFILES[key], '_name': PROFILES[key], 'path': str(path),
            'targets': [target], 'candidates': {target: data}, 'cand_option': {},
            'files': [], '_sel': {}}
