"""Package a clean Windows CPython installation, preserving its binaries.

Run under the exact CPython version selected by the CI workflow, before pip
installs. No interpreter executable is launched by the packager itself.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import zipfile


def build(prefix, output):
    prefix, output = Path(prefix).resolve(), Path(output).resolve()
    required = ['python.exe', 'pythonw.exe', 'LICENSE.txt', 'Lib/encodings/__init__.py']
    for name in required:
        if not (prefix / name).is_file():
            raise ValueError('Missing CPython runtime input: ' + name)
    if not (prefix / 'tcl').is_dir() or not list((prefix / 'DLLs').glob('_tkinter*.pyd')):
        raise ValueError('Full CPython with Tcl/Tk is required; embeddable Python is insufficient.')
    output.parent.mkdir(parents=True, exist_ok=True)
    # setup-python adds a python3.exe symlink on Windows. The app launches only
    # python.exe/pythonw.exe; omit the unused alias rather than following links.
    paths = [p for p in prefix.iterdir() if p.is_file() and p.name.lower() != 'python3.exe' and
             (p.suffix.lower() in ('.exe', '.dll') or p.name == 'LICENSE.txt')]
    for name in ('Lib', 'DLLs', 'tcl'):
        paths.extend(p for p in (prefix / name).rglob('*') if p.is_file())
    manifest = []
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(paths):
            rel = path.relative_to(prefix)
            if path.is_symlink():
                raise ValueError('Runtime input contains a symlink: ' + str(rel))
            if any(p in {'site-packages', '__pycache__', 'test', 'tests'} for p in rel.parts):
                continue
            if path.suffix.lower() in ('.pyc', '.pyo'):
                continue
            data = path.read_bytes()
            # Fixed archive metadata; executable contents and signatures unchanged.
            info = zipfile.ZipInfo(rel.as_posix(), (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
            manifest.append(dict(path=rel.as_posix(), size=len(data), sha256=hashlib.sha256(data).hexdigest()))
    record = dict(python_version=platform.python_version(), machine=platform.machine(),
                  source='CPython installation selected by actions/setup-python; see workflow run',
                  files=manifest, sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    output.with_suffix('.provenance.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, default=Path(sys.base_prefix))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.prefix, args.out)
    print('Runtime:', len(result['files']), 'files; SHA-256', result['sha256'])
