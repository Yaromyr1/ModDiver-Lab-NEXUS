"""Build release seeds from the pinned current clean baseline, never a live game."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

SOURCE = Path(__file__).resolve().parents[1] / 'source'
sys.path.insert(0, str(SOURCE))
import core
import builtin_prepared
import hdremix
from portable_hash import content_hash


def main():
    build = '26251122'
    destination = SOURCE / 'builtin/prepared'
    destination.mkdir(exist_ok=True)
    records = []
    with zipfile.ZipFile(SOURCE / f'builtin/gameplay/repair-baseline-{build}.zip') as baseline:
        meta = json.loads(baseline.read('baseline.json'))
        for key, target in (('nomofomo', hdremix.ARMOR),
                ('stratagem_bounce_removed', 'generated_stratagem_settings.dl_bin'),
                ('consistent_vaulting', 'generated_entities.dl_bin')):
            name = 'game/' + target
            plain = baseline.read(name)
            assert meta['files'][name]['sealed'] and hashlib.sha256(plain).hexdigest() == meta['files'][name]['sha256']
            record = dict(key=key, build=build, recipe=builtin_prepared.recipe(key),
                          stock_plain_sha256=hashlib.sha256(plain).hexdigest())
            if key == 'nomofomo':
                payload = hdremix.patch_armor(core.seal(plain), 63, False)
                (destination / 'hidden-content-unlocker.dl_bin').write_bytes(payload)
                record.update(package='prepared/hidden-content-unlocker.dl_bin', groups=63, padding=False)
            else:
                with zipfile.ZipFile(SOURCE / f'builtin/gameplay/{key}.zip') as archive:
                    profile = json.loads(archive.read('profile.json'))
                    payload = archive.read(profile['target'])
                    assert hashlib.sha256(payload).hexdigest() == profile['sha256']
                    record.update(package='gameplay/' + key, member=profile['target'])
            assert content_hash(core.unseal(payload)) == content_hash(plain), key + ': invalid game content hash'
            record['output_sha256'] = hashlib.sha256(payload).hexdigest()
            records.append(record)
            print(key + ': prepared and verified for build ' + build, flush=True)
    (destination / 'manifest.json').write_text(json.dumps({'format': 1, 'mods': records}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
