"""Restore pinned build inputs without executing downloaded code or binaries."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_target(root, relative):
    parts = PurePosixPath(relative).parts
    if not parts or '\\' in relative or ':' in relative or relative.startswith('/') or any(p in ('.', '..') for p in parts):
        raise ValueError('Unsafe input path: ' + relative)
    root = Path(root).resolve()
    target = root.joinpath(*parts).resolve()
    if not target.is_relative_to(root):
        raise ValueError('Input escapes destination: ' + relative)
    return target


def fetch_asset(key, spec, cache):
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / (key + '-' + spec['sha256'])
    if not target.is_file():
        request = urllib.request.Request(spec['url'], headers={'User-Agent': 'ModDiver-source-review'})
        with tempfile.NamedTemporaryFile(dir=cache, delete=False) as output:
            temporary = Path(output.name)
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    total = 0
                    while block := response.read(1024 * 1024):
                        total += len(block)
                        if total > spec['size']:
                            raise ValueError('Unexpected download size: ' + key)
                        output.write(block)
            except BaseException:
                output.close()
                temporary.unlink(missing_ok=True)
                raise
        try:
            data = temporary.read_bytes()
            if len(data) != spec['size'] or digest(data) != spec['sha256']:
                raise ValueError('Download checksum mismatch: ' + key)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    data = target.read_bytes()
    if len(data) != spec['size'] or digest(data) != spec['sha256']:
        raise ValueError('Cached input checksum mismatch: ' + key)
    return data


def windows_seed(data):
    # Read .NET embedded resources as data. Never start the downloaded launcher.
    import sys
    sys.path.insert(0, str(ROOT))
    from build_release import _resource_candidates
    with zipfile.ZipFile(io.BytesIO(data)) as outer:
        executable = outer.read('ModDiver Laboratory/ModDiver Laboratory.exe')
    for offset, length in _resource_candidates(executable):
        blob = executable[offset:offset + length]
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as app:
                if 'yao_forge.py' in app.namelist() and 'app.json' in app.namelist():
                    return blob
        except zipfile.BadZipFile:
            pass
    raise ValueError('Release has no embedded application source')


def restore(root, manifest, cache, verify_only=False):
    archives = {}
    for entry in manifest['files']:
        target = safe_target(root, entry['path'])
        if target.is_file() and target.stat().st_size == entry['size'] and digest(target.read_bytes()) == entry['sha256']:
            continue
        if verify_only:
            raise ValueError('Missing or modified build input: ' + entry['path'])
        key = entry['asset']
        if key not in archives:
            data = fetch_asset(key, manifest['assets'][key], cache)
            if key == 'windows':
                archives[key] = zipfile.ZipFile(io.BytesIO(windows_seed(data)))
            else:
                archives[key] = data
        data = archives[key].read(entry['member']) if entry['member'] else archives[key]
        if len(data) != entry['size'] or digest(data) != entry['sha256']:
            raise ValueError('Build input checksum mismatch: ' + entry['path'])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    print('Verified', len(manifest['files']), 'pinned build inputs.')


def extract_historical(manifest, cache, destination):
    if destination.exists():
        raise ValueError('Historical source destination must not already exist')
    historical = json.loads((ROOT / 'review/v2.3.6-manifest.json').read_text())
    for platform in ('windows', 'linux'):
        data = fetch_asset(platform, manifest['assets'][platform], cache)
        if platform == 'windows':
            data = windows_seed(data)
            if digest(data) != historical['embedded_windows_app_sha256']:
                raise ValueError('Embedded source checksum mismatch')
        prefix = '' if platform == 'windows' else 'ModDiver Laboratory/source/'
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for entry in historical['platforms'][platform]:
                data = archive.read(prefix + entry['path'])
                if len(data) != entry['size'] or digest(data) != entry['sha256']:
                    raise ValueError('Historical member checksum mismatch: ' + entry['path'])
                target = safe_target(destination / platform, entry['path'])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    print('Extracted verified v2.3.6 application sources to', destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, default=ROOT/'build/input-cache')
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--extract-release-source', type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT/'build-inputs.json').read_text())
    if args.extract_release_source:
        if args.verify_only:
            parser.error('--verify-only cannot extract release sources')
        extract_historical(manifest, args.cache_dir, args.extract_release_source)
    else:
        restore(ROOT, manifest, args.cache_dir, args.verify_only)


if __name__ == '__main__':
    main()
