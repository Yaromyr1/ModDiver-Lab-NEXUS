"""Recover files created by the YAO runtime, independently of deploy receipts."""
import hashlib
import os
from pathlib import Path

from merge_engine import atomic_write


SUFFIXES = ('.yao-loader-original', '.yao-loader-rollback', '.yao-loader-tmp')


def fingerprint(data):
    """Match the runtime's size/head/tail fingerprint."""
    return f'{len(data)}:{data[:64].hex()}:{data[max(0, len(data)-64):].hex()}'


def cleanup(cfg, app_data, log=print):
    import core

    if core.hellforge_root(cfg) is not None:
        return 0

    folder = (Path(cfg['game']) / 'data' / 'game').resolve()
    state = {}
    home = os.environ.get('LOCALAPPDATA') or os.environ.get('TEMP') or '.'
    try:
        for line in (Path(home) / 'YAO-DATA-LOADER.state').read_text(encoding='utf-8').splitlines():
            parts = line.split('|', 4)
            if len(parts) == 5:
                state[parts[0]] = parts[4]
    except FileNotFoundError:
        pass
    except (OSError, UnicodeError) as exc:
        log(f'  purge warning: could not read YAO loader state: {exc}')

    count = 0
    game_id = hashlib.sha256(str(folder).encode('utf-8')).hexdigest()[:16]
    for suffix in SUFFIXES:
        for source in sorted(folder.glob('generated_*.dl_bin' + suffix)):
            try:
                # Do not follow links out of the selected game directory.
                if source.is_symlink() or source.resolve().parent != folder or not source.is_file():
                    raise RuntimeError('refusing linked or non-file loader artifact')
                name = source.name[:-len(suffix)]
                dest = core.target_path(cfg, name)
                if dest.parent != folder or (folder / name).is_symlink():
                    raise RuntimeError('refusing linked loader target')
                data = source.read_bytes()
                current = dest.read_bytes() if dest.exists() else None
                if suffix == SUFFIXES[0] and current != data:
                    if current is None or fingerprint(current) == state.get(name):
                        # A missing target or known loader output can be restored.
                        # Reject truncated/corrupt backups before touching the target.
                        core.unseal(data)
                        atomic_write(dest, data)
                        log(f'Restored YAO loader original: {name}')
                    else:
                        log(f'Preserved current game file: {name}; archived older loader backup')
                # Keep recovery bytes outside the game, including unknown/stale backups.
                digest = hashlib.sha256(data).hexdigest()
                recovery = Path(app_data) / 'loader-recovery' / game_id / digest / source.name
                if not recovery.is_file() or recovery.read_bytes() != data:
                    atomic_write(recovery, data)
                source.unlink()
                count += 1
                log(f'Removed YAO loader artifact: {source.name} (recovery: {recovery})')
            except Exception as exc:
                log(f'  purge warning: {source.name}: {exc}; retry Purge after resolving the error')
    return count
