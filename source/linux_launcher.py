"""Linux bootstrap: per-user app updates, unchanged data location, early-crash rollback."""
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys
import uuid

import updater
import nexus_mode
from single_instance import InstanceLock

LAUNCHER_API=3


def data_directory():
    explicit=os.environ.get('YAO_FORGE_DATA')
    return Path(explicit) if explicit else Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/nexus_mode.DATA_DIRECTORY


def ready(root,version):
    return bool(version and updater._SAFE_FOLDER.fullmatch(version)
                and (root/version/updater.OK_MARKER).is_file() and (root/version/'yao_forge.py').is_file())


def prepare(seed,data):
    seed=Path(seed);root=Path(data)/'app';root.mkdir(parents=True,exist_ok=True)
    match=re.search(r'^VERSION\s*=\s*"([^"]+)"',(seed/'yao_forge.py').read_text(encoding='utf-8'),re.M)
    if not match:raise RuntimeError('The extracted application is incomplete. Download the full Linux ZIP again.')
    version=updater.canonical_version(match[1]);current,previous=updater.read_pointer(root)
    revision = seed/'ui_revision.txt'
    installed_revision = root/version/'ui_revision.txt'
    try:
        pin = (root/'rollback.txt').read_text(encoding='utf-8').splitlines()
        if (len(pin) == 2 and pin[0] == current and ready(root, current)
                and revision.is_file() and pin[1] == revision.read_text(encoding='utf-8').strip()):
            return root, current, previous
    except OSError:
        pass
    refresh_seed = bool(current and current.split('-rollback-', 1)[0] == version) and revision.is_file() and (
        not installed_revision.is_file() or installed_revision.read_bytes() != revision.read_bytes())
    reset_version = (version == '2.1.0' and current in ('2.1.1', '2.1.2', '2.1.3')
                     and revision.is_file() and revision.read_text().strip() in (
                         '2.1.0-library-presets-and-continuous-gradient',
                         '2.1.0-foreground-dialogs-and-storage-checkboxes'))
    if reset_version and (not installed_revision.is_file() or installed_revision.read_bytes() != revision.read_bytes()):
        refresh_seed = True
    if not ready(root,current) or updater._is_newer(version,current) or refresh_seed or reset_version:
        final=root/version
        if not ready(root,version) or refresh_seed:
            stage=root/f'.seed-{uuid.uuid4().hex}'
            try:
                shutil.copytree(seed,stage,ignore=shutil.ignore_patterns('__pycache__','_work','tests','*.pyc','*.exe','*.dll','*.ico'))
                (stage/'app.json').write_text(json.dumps({'version':version,'min_launcher':LAUNCHER_API}),encoding='utf-8')
                (stage/updater.OK_MARKER).write_text(version,encoding='utf-8')
                if final.exists():
                    backup = version + '-rollback-' + uuid.uuid4().hex[:8]
                    was_ready = ready(root, version)
                    final.rename(root/backup)
                    if was_ready and current == version:
                        previous = backup
                stage.rename(final)
            finally:
                if stage.exists():shutil.rmtree(stage)
        previous=current if current != version and ready(root,current) else previous
        current=version;updater._write_pointer(root,current,previous)
    return root,current,previous


def run(root,current,previous,bootstrap,log,launch=subprocess.Popen):
    env=os.environ.copy();env.update(YAO_FORGE_DATA=str(root.parent),YAO_FORGE_BOOTSTRAP=str(bootstrap),YAO_FORGE_LAUNCHER_API=str(LAUNCHER_API))
    env.pop('YAO_FORGE_EXE',None)
    def start(version):
        return launch([sys.executable,str(root/version/'yao_forge.py')],cwd=str(root/version),env=env,stdout=log,stderr=log,start_new_session=True)
    process=start(current)
    try:code=process.wait(timeout=4)
    except subprocess.TimeoutExpired:return 0
    if code and previous!=current and ready(root,previous):
        log.write(f'Update {current} exited early ({code}); restoring {previous}.\n');log.flush()
        updater._write_pointer(root,previous,None)
        start(previous)
        return 0
    return code


def main():
    data=data_directory();data.mkdir(parents=True,exist_ok=True)
    startup=InstanceLock(data, 'launcher.lock')
    if not startup.acquire():return 0
    log_path=data/'launcher-linux.log'
    if log_path.exists() and log_path.stat().st_size>256*1024:
        log_path.replace(data/'launcher-linux.previous.log')
    bootstrap=Path(__file__).resolve()
    try:
        from loading_ui import run_splash
        try: theme=json.loads((data/'config.json').read_text(encoding='utf-8')).get('theme',{})
        except (OSError, ValueError): theme={}
        root,current,previous=run_splash(lambda:prepare(bootstrap.parent,data),theme.get('bg','#080808'),
                                      theme.get('panel'),theme.get('text'),theme.get('accent','#ffd400'))
        with log_path.open('a',encoding='utf-8',buffering=1) as log:
            code=run(root,current,previous,bootstrap,log)
        if code:print(f'ModDiver Laboratory could not start. Details: {log_path}',file=sys.stderr)
        return code
    except Exception as exc:
        print(f'ModDiver Laboratory: {exc}\nSee README-Linux.md for setup and recovery.',file=sys.stderr)
        return 1
    finally:
        startup.release()


if __name__=='__main__':raise SystemExit(main())

