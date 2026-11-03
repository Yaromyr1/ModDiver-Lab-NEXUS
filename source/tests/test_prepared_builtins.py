import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import core
import builtin_updater
import builtin_prepared


class PreparedBuiltinsTests(unittest.TestCase):
    def test_clean_install_uses_all_three_shipped_outputs_without_repair_or_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            game = root / 'steamapps/common/Helldivers 2'
            data = game / 'data/game'
            data.mkdir(parents=True)
            (game.parent.parent / 'appmanifest_553850.acf').write_text('"appid" "553850" "buildid" "26251122" "StateFlags" "4"')
            with zipfile.ZipFile(core.ROOT / 'builtin/gameplay/repair-baseline-26251122.zip') as baseline:
                for name in builtin_updater.TARGETS.values():
                    (data / name).write_bytes(core.seal(baseline.read('game/' + name)))
            cfg = {'game': str(game)}
            with patch.multiple(core, APP_DATA=root/'app', STOCK=root/'stock', DEPLOYED=root/'deployed.json'), \
                 patch.object(builtin_updater, '_baselines', side_effect=AssertionError('No repair/download needed')), \
                 patch.object(builtin_updater.build_archive, 'automatic_plan', side_effect=AssertionError('Already prepared')):
                ready = builtin_updater.ensure(cfg, refresh=False)
                self.assertEqual(set(ready), set(builtin_updater.NAMES))
                self.assertTrue(all(isinstance(value, Path) and value.is_file() for value in ready.values()), ready)
                self.assertFalse(core.STOCK.exists(), 'Prepared output must not recapture stock')
                original = ready['consistent_vaulting'].read_bytes()
                ready['consistent_vaulting'].write_bytes(b'broken cache')
                rebuilt = builtin_updater.ensure(cfg, refresh=False)
                self.assertEqual(rebuilt['consistent_vaulting'].read_bytes(), original)
                raw = (data / builtin_updater.TARGETS['nomofomo']).read_bytes()
                self.assertIsNone(builtin_prepared.load('nomofomo', raw, {'unlock_groups': 0}, '26251122'))
                self.assertIsNone(builtin_prepared.load('nomofomo', raw, {}, 'future-build'))


if __name__ == '__main__':
    unittest.main()
