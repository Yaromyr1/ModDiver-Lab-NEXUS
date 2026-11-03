"""Three persistent, user-named shortcuts. Registration never executes a file."""
import os
from pathlib import Path
import subprocess
import sys
import uuid

LIMIT = 3
EXECUTABLES = {'.exe', '.com', '.lnk', '.appimage', '.py', '.ps1', '.bat', '.cmd', '.sh'}
PACKAGES = {'.zip', '.7z'}


def add(cfg, name):
    name = str(name).strip()
    records = cfg.setdefault('custom_tools', [])
    if len(records) >= LIMIT:
        raise ValueError('All three custom tool slots are in use.')
    if not name or len(name) > 60 or any(ord(c) < 32 for c in name):
        raise ValueError('Enter a name between 1 and 60 characters.')
    if any(record['name'].casefold() == name.casefold() for record in records):
        raise ValueError('A custom tool already uses that name.')
    record = {'id': uuid.uuid4().hex, 'name': name, 'path': '', 'kind': 'executable'}
    records.append(record)
    return record


def attach(record, source):
    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise ValueError('Choose an existing tool or loader package.')
    kind = 'loader' if path.is_dir() or path.suffix.lower() in PACKAGES else 'executable'
    if kind == 'executable' and path.suffix.lower() not in EXECUTABLES:
        raise ValueError('Choose an executable, script, shortcut, ZIP, 7z or loader folder.')
    record.update(path=str(path), kind=kind)


def launch(record):
    if not record.get('path'):
        raise ValueError('Choose a file for this tool first.')
    path = Path(record['path'])
    if not path.is_file():
        raise ValueError('This tool has moved. Choose its file again.')
    if record.get('kind') != 'executable' or path.suffix.lower() not in EXECUTABLES:
        raise ValueError('Add loader packages to the library, then Deploy to install.')
    suffix = path.suffix.lower()
    if os.name == 'nt' and suffix in {'.lnk', '.bat', '.cmd'}:
        os.startfile(str(path), cwd=str(path.parent))
        return
    command = ([sys.executable, str(path)] if suffix == '.py' else
               ['powershell.exe', '-NoProfile', '-File', str(path)] if suffix == '.ps1' else
               ['bash', str(path)] if suffix == '.sh' else [str(path)])
    subprocess.Popen(command, cwd=path.parent, shell=False)
