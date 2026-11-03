import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import core
import library_presets as presets


class PresetTests(unittest.TestCase):
    def test_switch_and_restart_preserve_order_composition_and_components(self):
        cfg = {'mods': [dict(name='A', path='a.zip', enabled=True, selected={'Part': False}, category='gameplay'),
                        dict(name='B', path='b.zip', enabled=False, category='visual')],
               'loaders_deploy_first': True, 'nomofomo': False}
        presets.save_as(cfg, 'Co-op')
        expected = copy.deepcopy(cfg['mods'])
        presets.save_as(cfg, 'Solo')
        cfg['mods'].reverse()
        cfg['mods'][0]['enabled'] = True
        cfg['mods'][1]['selected']['Part'] = True
        cfg['mods'].append(dict(name='C', path='c.zip', enabled=True))
        cfg['loaders_deploy_first'] = False
        solo = copy.deepcopy(cfg['mods'])
        presets.sync_active(cfg)  # Explicitly update Solo before switching.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(core, 'APP_DATA', root), patch.object(core, 'CONFIG', root/'config.json'):
                core.save_config(cfg)
                loaded = core.load_config()
                presets.activate(loaded, 'Co-op')
                self.assertEqual(loaded['mods'], expected)
                self.assertTrue(loaded['loaders_deploy_first'])
                presets.activate(loaded, 'Solo')
                self.assertEqual(loaded['mods'], solo)
                self.assertFalse(loaded['loaders_deploy_first'])
                core.save_config(loaded)
                self.assertEqual(core.load_config()['active_mod_preset'], 'Solo')

    def test_failed_atomic_save_preserves_previous_config(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root/'config.json'
            target.write_text('{"mods": []}')
            with patch.object(core, 'APP_DATA', root), patch.object(core, 'CONFIG', target), patch.object(core.os, 'replace', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    core.save_config({'mods': ['new']})
            self.assertEqual(json.loads(target.read_text()), {'mods': []})
            self.assertEqual(list(root.iterdir()), [target])

    def test_save_as_does_not_overwrite_existing_preset(self):
        cfg = {'mods': []}
        presets.save_as(cfg, 'A')
        with self.assertRaises(ValueError):
            presets.save_as(cfg, 'A')
        with self.assertRaises(ValueError):
            presets.save_as(cfg, ' ')

    def test_removing_working_library_keeps_saved_preset_across_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            package = root / 'stored-mod.zip'
            package.write_bytes(b'mod package')
            cfg = {'mods': [dict(name='Saved mod', path=str(package), enabled=True,
                                category='gameplay', selected={'Part': False})]}
            presets.save_as(cfg, 'Saved')
            expected = copy.deepcopy(cfg['mods'])
            cfg['mods'][0]['selected']['Part'] = True
            cfg['mods'].clear()
            with patch.object(core, 'APP_DATA', root), patch.object(core, 'CONFIG', root/'config.json'):
                core.save_config(cfg)
                loaded = core.load_config()
                self.assertEqual(loaded['mod_presets']['Saved']['mods'], expected)
                presets.save_as(loaded, 'Empty')
                presets.activate(loaded, 'Saved')
                self.assertEqual(loaded['mods'], expected)
                loaded['mods'].clear()
                presets.activate(loaded, 'Saved')
                self.assertEqual(loaded['mods'], expected)
                self.assertTrue(package.is_file())


if __name__ == '__main__':
    unittest.main()
