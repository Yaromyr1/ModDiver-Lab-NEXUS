"""Release-built outputs, accepted only for an exact clean input and recipe."""
import hashlib
import json
from pathlib import Path
import zipfile

import core
import hdremix

ROOT = Path(__file__).parent / 'builtin'


def recipe(key):
    if key == 'nomofomo':
        return hashlib.sha256(Path(hdremix.__file__).read_bytes() +
            (hdremix.ROOT / 'Source/Schema.json').read_bytes() +
            (hdremix.ROOT / 'Source/Profiles.json').read_bytes()).hexdigest()
    package = ROOT / 'gameplay' / key
    if package.is_dir():
        return hashlib.sha256((package / 'profile.json').read_bytes()).hexdigest()
    with zipfile.ZipFile(package.with_suffix('.zip')) as archive:
        return hashlib.sha256(archive.read('profile.json')).hexdigest()


def load(key, raw, cfg, build):
    manifest = ROOT / 'prepared/manifest.json'
    if not manifest.is_file():
        return None
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('format') != 1:
        raise ValueError('Unsupported prepared built-in manifest.')
    for item in data.get('mods', []):
        if item['key'] != key or str(item['build']) != str(build):
            continue
        if key == 'nomofomo' and (int(cfg.get('unlock_groups', 63)) != item['groups'] or bool(cfg.get('unlock_padding', False)) != item['padding']):
            continue
        if item['recipe'] != recipe(key) or hashlib.sha256(core.unseal(raw)).hexdigest() != item['stock_plain_sha256']:
            continue
        package = (ROOT / item['package']).resolve()
        if not package.is_relative_to(ROOT.resolve()):
            raise ValueError('Unsafe prepared built-in path.')
        member = item.get('member')
        if member:
            if not core._safe_rel(member):
                raise ValueError('Unsafe prepared built-in member.')
            if package.is_dir():
                payload = (package / member).read_bytes()
            else:
                with zipfile.ZipFile(package.with_suffix('.zip')) as archive:
                    payload = archive.read(member)
        else:
            payload = package.read_bytes()
        if hashlib.sha256(payload).hexdigest() != item['output_sha256']:
            raise ValueError('Prepared built-in checksum mismatch: ' + key)
        core.validate_sealed_input(payload, key)
        core.unseal(payload)
        return payload
    return None
