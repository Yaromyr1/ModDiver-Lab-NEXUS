"""User-requested, verified built-in updates through the Data Bot repair engine."""
from contextlib import ExitStack, contextmanager
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import threading
import zipfile
import os
import subprocess
import sys
import time

import build_archive
import core
import gameplay_profiles
import hdremix
import nexus_mode
import repair_data
from dlbin_codec import DLBin, content_hash

LOCK = threading.RLock()
ROOT = Path(__file__).parent / 'builtin' / 'gameplay'
NAMES = {'nomofomo': ('contentUnlock' if nexus_mode.NEXUS_BUILD else 'Hidden Content Unlocker'),
         **gameplay_profiles.PROFILES}
TARGETS = {'nomofomo': hdremix.ARMOR,
           'stratagem_bounce_removed': 'generated_stratagem_settings.dl_bin',
           'consistent_vaulting': 'generated_entities.dl_bin'}


@contextmanager
def _baselines(log=lambda message: None, *, game=None, build=None):
    """Share transient repair witnesses across one built-in repair job."""
    if nexus_mode.NEXUS_BUILD:
        if game is None or build is None or build_archive.find_matching_clean_baseline(game, build) is None:
            raise ValueError('Nexus Data Bot requires a clean stock capture from Steam Verify for the currently installed build. Capture clean stock, then retry.')
        yield (build_archive.archive_root(),)
        return
    with build_archive.baseline_session(folder=ROOT, progress=log) as roots:
        yield roots


def _clean_file(game, name, deployed, build):
    current = game / 'data/game' / name
    info = deployed.get(name) or deployed.get('data/game/' + name)
    if not info:
        return current
    # A managed mod retains the stock content hash. Use its original backup,
    # never the installed edits, and refuse stale backups from another build.
    backup = Path(info.get('backup') or '')
    if not backup.is_file():
        raise ValueError('Managed original backup is missing: ' + name)
    if content_hash(DLBin.open(current).plain) != content_hash(DLBin.open(backup).plain):
        # Steam can replace an installed mod during an update. A new build and
        # changed installed bytes prove this is no longer our deployed output.
        prior = info.get('steam_build')
        if prior and prior != build and info.get('installed_sha256') and build_archive.digest(current) != info['installed_sha256']:
            return current
        # Adopt legacy records only when an archived older build independently
        # identifies their original backup. Never substitute an arbitrary backup.
        backup_hash = content_hash(DLBin.open(backup).plain)
        for folder, meta in build_archive.builds():
            relative = 'game/' + name
            witness = folder / 'data' / relative
            if (meta['build_id'] != build and relative in meta['files']
                    and build_archive.digest(witness) == meta['files'][relative]
                    and content_hash(DLBin.open(witness).plain) == backup_hash):
                return current
        raise ValueError('Managed backup does not match the installed build: ' + name)
    return backup


def _retire_previous(work, key, current):
    root = Path(work).resolve()
    for candidate in root.iterdir():
        if candidate == current or candidate.is_symlink() or not candidate.is_dir():
            continue
        if candidate.resolve().parent != root or len(candidate.name) != 64:
            continue
        try:
            metadata = json.loads((candidate / 'verified.json').read_text())
        except (OSError, ValueError):
            continue
        if metadata.get('identity', {}).get('key') == key:
            shutil.rmtree(candidate)


def ensure(cfg, log=lambda message: None, *, refresh=True):
    """Update all three on request, or only read verified caches for deployment.

    Cache identity covers the game bytes, bundled recipe and user options.
    Failed/stale output is never returned to deployment. Nothing writes to game.
    """
    if not cfg.get('game') or core.hellforge_root(cfg) is not None:
        return {}
    with LOCK:
        game = core.game_dir(cfg).resolve()
        if not (game.parent.parent / 'appmanifest_553850.acf').is_file():
            return {}  # Preserve support for non-Steam data installations.
        build = build_archive.steam_build(game)
        deployed = core.load_deployed()
        baselines_ready = False
        engine = hashlib.sha256(b''.join((Path(__file__).parent / name).read_bytes()
            for name in ('builtin_updater.py', 'builtin_prepared.py', 'mod_repair.py', 'dlbin_codec.py', 'portable_hash.py'))).hexdigest()
        work = core.APP_DATA / 'builtin-updates'
        work.mkdir(parents=True, exist_ok=True)
        results = {}
        with ExitStack() as sessions, tempfile.TemporaryDirectory(prefix='.prepare-', dir=work) as temporary:
            view = Path(temporary) / 'clean'
            data = view / 'data/game'
            data.mkdir(parents=True)
            schema = game / 'data/game/dl_library.dl_typelib'
            schema_digest = build_archive.digest(schema) if schema.is_file() else None
            for number, (key, label) in enumerate(NAMES.items(), 1):
                name = TARGETS[key]
                try:
                    started = time.monotonic()
                    if refresh:
                        log(f'Data Bot [{number}/{len(NAMES)}]: checking {label}')
                    original = _clean_file(game, name, deployed, build)
                    raw = original.read_bytes()
                    identity = {'build': build, 'stock': hashlib.sha256(raw).hexdigest(),
                                'engine': engine, 'key': key}
                    if key == 'nomofomo':
                        passive = 'generated_customization_passive_bonuses.dl_bin'
                        if cfg.get('unlock_padding', False):
                            passive_raw = _clean_file(game, passive, deployed, build).read_bytes()
                            identity['passive'] = hashlib.sha256(passive_raw).hexdigest()
                        identity.update(groups=int(cfg.get('unlock_groups', 63)),
                                        padding=bool(cfg.get('unlock_padding', False)),
                                        recipe=hashlib.sha256((Path(hdremix.__file__).read_bytes()
                                            + (hdremix.ROOT / 'Source/Schema.json').read_bytes()
                                            + (hdremix.ROOT / 'Source/Profiles.json').read_bytes())).hexdigest())
                    else:
                        package = ROOT / key
                        if package.is_dir():
                            identity['recipe'] = repair_data.directory_digest(package)[1]
                        else:
                            identity['recipe'] = build_archive.digest(ROOT / (key + '.zip'))
                        identity['schema'] = schema_digest
                    token = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
                    destination = work / token
                    target = destination / name
                    try:
                        meta = json.loads((destination / 'verified.json').read_text())
                        cached = meta['identity'] == identity and build_archive.digest(target) == meta['output']
                    except (OSError, ValueError, KeyError):
                        cached = False
                    if not cached:
                        import builtin_prepared
                        prepared = builtin_prepared.load(key, raw, cfg, build)
                        if prepared is not None:
                            destination.mkdir(parents=True, exist_ok=True)
                            core.atomic_write(target, prepared)
                            core.atomic_write(destination / 'verified.json', json.dumps({
                                'identity': identity, 'output': hashlib.sha256(prepared).hexdigest(),
                                'report': 'Verified release-built output for this exact clean input.'}).encode('utf-8'))
                            cached = True
                            log('Built-in ready: ' + label + ' (verified bundled output).')
                    if not cached:
                        if not refresh:
                            raise ValueError('No verified cached or bundled output matches this game build and options.')
                        if key != 'nomofomo' and not baselines_ready:
                            baseline_roots = sessions.enter_context(_baselines(log, game=game, build=build))
                            baselines_ready = True
                        DLBin(name, raw)  # Authenticate/parse before capturing stock.
                        core.atomic_write(data / name, raw)
                        if key == 'nomofomo' and identity['padding']:
                            core.atomic_write(data / passive, passive_raw)
                        if schema_digest and not (data / schema.name).exists():
                            shutil.copyfile(schema, data / schema.name)
                        log('Data Bot: updating ' + label + ' for Steam build ' + build)
                        with tempfile.TemporaryDirectory(prefix='.update-', dir=work) as stage:
                            stage = Path(stage)
                            source = stage / 'input' / name
                            source.parent.mkdir()
                            if key == 'nomofomo':
                                hdremix.validate_stock(data, identity['padding'])
                                source.write_bytes(hdremix.patch_armor(raw, identity['groups'], identity['padding'], log))
                            else:
                                package = ROOT / key
                                if not package.is_dir():
                                    package = ROOT / (key + '.zip')
                                if package.is_dir():
                                    profile = json.loads((package / 'profile.json').read_text(encoding='utf-8'))
                                    payload = (package / profile['target']).read_bytes()
                                else:
                                    with zipfile.ZipFile(ROOT / (key + '.zip')) as archive:
                                        profile = json.loads(archive.read('profile.json'))
                                        payload = archive.read(profile['target'])
                                if hashlib.sha256(payload).hexdigest() != profile['sha256']:
                                    raise ValueError('Bundled payload checksum mismatch.')
                                source.write_bytes(payload)
                            # Same baseline matching, structural repair, exact export and
                            # hash validation as the Data Bot's automatic updater.
                            if key == 'nomofomo':
                                import mod_repair
                                snapshot = mod_repair.snapshot([data / name], stage)
                                plan = mod_repair.analyse(snapshot / name, data / name, source)
                            else:
                                plan = build_archive.automatic_plan(
                                    source, view, root=baseline_roots,
                                    build_id=build if nexus_mode.NEXUS_BUILD else None)
                            unchanged = source.read_bytes() == raw
                            if plan.errors and not unchanged:
                                raise ValueError('; '.join(plan.errors))
                            output = stage / 'output'
                            output.mkdir()
                            if unchanged:
                                (output / name).write_bytes(raw)
                            else:
                                plan.export(output)
                            (output / 'verified.json').write_text(json.dumps({
                                'identity': identity, 'output': build_archive.digest(output / name),
                                'report': plan.report}, indent=2))
                            if destination.exists():
                                shutil.rmtree(destination)
                            output.rename(destination)
                        log('Data Bot: ' + label + ' repaired, updated and verified.')
                    # A game update during processing must not publish stale stock.
                    if build_archive.steam_build(game) != build or original.read_bytes() != raw:
                        raise ValueError('Game changed during update; click UPDATE/REPAIR built-in mods again.')
                    if key != 'nomofomo' and schema.is_file() and build_archive.digest(schema) != identity['schema']:
                        raise ValueError('Game schema changed during update.')
                    if not refresh:
                        results[key] = target
                        continue
                    core.atomic_write(core.STOCK / name, raw)
                    if key == 'nomofomo' and identity['padding']:
                        core.atomic_write(core.STOCK / passive, passive_raw)
                    # A Steam replacement has superseded this managed install.
                    # Retire its old ownership only after verifying the new mod;
                    # the next deploy will back up the current build normally.
                    if original == game / 'data/game' / name:
                        changed = False
                        for relative in (name, 'data/game/' + name):
                            if relative in deployed:
                                del deployed[relative]
                                changed = True
                        if changed:
                            core.save_deployed(deployed)
                    results[key] = target
                    _retire_previous(work, key, destination)
                    if refresh:
                        log(f'Data Bot [{number}/{len(NAMES)}]: {label} ready ({time.monotonic()-started:.1f}s).')
                except Exception as exc:
                    results[key] = str(exc)
                    if refresh:
                        log('Data Bot: ' + label + ' could not update: ' + str(exc))
        return results


def run_worker(cfg, log=lambda message: None):
    """One low-priority process runs the three jobs serially, outside Tk's GIL."""
    options = {}
    if os.name == 'nt':
        options['creationflags'] = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    environment = dict(os.environ, YAO_FORGE_DATA=str(core.APP_DATA), PYTHONIOENCODING='utf-8')
    with subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()), '--worker'],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding='utf-8', env=environment, **options) as process:
        process.stdin.write(json.dumps(cfg) + '\n')
        process.stdin.close()
        result = None
        for line in process.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                log('Built-in worker: ' + line.rstrip())
                continue
            if event.get('type') == 'log':
                log(event['message'])
            elif event.get('type') == 'result':
                result = {key: Path(value['path']) if 'path' in value else value['error']
                          for key, value in event['values'].items()}
        code = process.wait()
        if code or result is None:
            raise RuntimeError('Built-in mod worker stopped before completing; see log.')
        return result


def _worker_main():
    if os.name != 'nt':
        try:
            os.nice(5)
        except OSError:
            pass
    cfg = json.loads(sys.stdin.readline())
    def progress(message):
        print(json.dumps({'type': 'log', 'message': str(message)}), flush=True)
    result = ensure(cfg, progress)
    values = {key: {'path': str(value)} if isinstance(value, Path) else {'error': value}
              for key, value in result.items()}
    print(json.dumps({'type': 'result', 'values': values}), flush=True)


if __name__ == '__main__' and '--worker' in sys.argv:
    _worker_main()
