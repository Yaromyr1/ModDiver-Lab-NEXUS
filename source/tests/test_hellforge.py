import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import actions
import core
import hellforge


class HellForgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.install = self.root / 'HellForge'
        self.install.mkdir()
        (self.install / 'hellforge-install.json').write_text('{}')
        self.data = patch.object(core, 'APP_DATA', self.root / 'appdata')
        self.data.start()
        self.addCleanup(self.data.stop)

    def package(self, name='PSSprogression', extras=None):
        path = self.root / (name + '.zip')
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('wrapper/hellforge-mod.json', json.dumps({'id': 'test.progression', 'name': name}))
            z.writestr('wrapper/hellforge-stats.json', '{"stats": []}')
            z.writestr('wrapper/progression.dll', b'MZ sample')
            z.writestr('wrapper/src/progression.c', b'/* source */')
            for file, data in (extras or {}).items():
                z.writestr(file, data)
        return path

    def test_native_package_preserves_json_code_and_sources(self):
        mod = core.parse_mod(self.package())
        self.assertEqual(mod['type'], 'HellForge')
        self.assertIn('hellforge-stats.json', mod['targets'])
        self.assertIn('progression.dll', mod['targets'])
        self.assertIn('src/progression.c', mod['targets'])
        self.assertFalse(mod['candidates'])
        self.assertFalse(mod['files'])

    def test_runtime_and_dependent_lua_are_labelled(self):
        for name, script in [('HD2Runtime-0.50.1', b'return {}'),
                             ('Some Lua Mod', b'local hd2 = require("mods/skyeshade/hd2runtime")')]:
            path = self.root / (name + '.zip')
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('mods/test/init.lua', script)
            self.assertEqual(core.parse_mod(path)['type'], 'HellForge')

    def test_regular_patch_stays_regular(self):
        path = self.root / 'cosmetic.zip'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('manifest.json', '{"Name":"Cosmetic"}')
            z.writestr('data/abcd.patch_0', b'patch')
        self.assertEqual(core.parse_mod(path)['type'], 'arsenal')

    def test_root_detection_accepts_game_copy(self):
        self.assertEqual(core.hellforge_root({'game':str(self.install / 'game')}), self.install)
        self.assertIsNone(core.hellforge_root({'game':str(self.root)}))

    def test_regular_deploy_refuses_hellforge(self):
        with self.assertRaisesRegex(RuntimeError, 'HellForge installation'):
            core.deploy({'game': str(self.root), 'mods':[{'type':'HellForge', 'enabled':True}]})

    def test_deploy_uses_complete_package_and_purge_owns_only_imports(self):
        path = self.package()
        cfg = {'game':str(self.install), 'mods':[{'path':str(path),'name':'PSSprogression','enabled':True}]}
        rows = [{'id':'someone.else', 'name':'Existing'}]
        calls = []
        def run(root, *args):
            calls.append(args)
            if args[0] == 'mods':return {'mods': list(rows)}
            if args[0] == 'mod-add':
                with zipfile.ZipFile(args[2]) as archive:
                    self.assertEqual(archive.read('wrapper/progression.dll'), b'MZ sample')
                    self.assertIn('wrapper/hellforge-stats.json', archive.namelist())
                rows.append({'id':'test.progression','name':'PSSprogression'})
            if args[0] == 'mod-remove':rows[:] = [m for m in rows if m['id'] != args[2]]
            return {}
        with patch.object(hellforge,'_run', side_effect=run), patch.object(actions,'ensure_stock') as stock:
            self.assertEqual(actions.install_all(cfg, lambda _:None),1)
            stock.assert_not_called()
            self.assertIn(('mod-order','--ids','test.progression'), calls)
            self.assertEqual(core.purge(cfg,lambda _:None),1)
            self.assertEqual(rows,[{'id':'someone.else','name':'Existing'}])

    def test_dry_run_does_not_mutate(self):
        path=self.package()
        with patch.object(hellforge,'_run', return_value={'mods':[]}) as cli:
            self.assertEqual(hellforge.deploy({'mods':[{'path':str(path),'name':'PSS'}]},self.install,lambda _:None,True),1)
            self.assertEqual([c.args[1] for c in cli.call_args_list], ['mods'])
            self.assertFalse(hellforge._receipt_path(self.install).exists())

    def test_unmanaged_same_id_is_preserved(self):
        path=self.package()
        with patch.object(hellforge,'_run', return_value={'mods':[{'id':'test.progression','name':'Old version'}]}) as cli:
            with self.assertRaisesRegex(RuntimeError,'outside Laboratory'):
                hellforge.deploy({'mods':[{'path':str(path),'name':'PSS'}]},self.install,lambda _:None)
            self.assertEqual(cli.call_count,1)

    def test_duplicate_versions_are_rejected_before_install(self):
        first = self.package('First version')
        second = self.package('Second version')
        with patch.object(hellforge,'_run',return_value={'mods':[]}) as cli:
            with self.assertRaisesRegex(RuntimeError,'only one version'):
                hellforge.deploy({'mods':[{'path':str(p),'name':p.stem} for p in (first,second)]},
                                 self.install,lambda _:None)
            self.assertEqual(cli.call_count,1)

    def test_unsafe_and_duplicate_package_paths_rejected(self):
        for entries in [[('../escape.dll',b'')], [('C:/x.dll',b'')], [('a.dll',b''),('A.dll',b'')]]:
            with self.assertRaises(ValueError):hellforge.validate_entries(entries)


if __name__ == '__main__':unittest.main()
