import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

import core
import hellforge
import hellforge_legacy
import hellforge_stats as stats


class HellForgeCompatibilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.install = self.root / 'HellForge'
        (self.install / 'game/data/game').mkdir(parents=True)
        (self.install / 'app/cli').mkdir(parents=True)
        (self.install / 'app/cli/HellForge.Cli.exe').write_bytes(b'fake cli')
        (self.install / 'hellforge-install.json').write_text('{}')
        patches = patch.multiple(core, APP_DATA=self.root/'app', STOCK=self.root/'steam-stock')
        patches.start(); self.addCleanup(patches.stop)
        self.cfg = {'game': str(self.install), 'mods': []}

    def package(self, name, identity=None):
        source = self.root / (name + '.zip')
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr('hellforge-mod.json', json.dumps({'format':1, 'id':identity or 'test.'+name, 'name':name}))
            archive.writestr('hellforge-stats.json', json.dumps({'format':1,'weapons':{'AR-23 Liberator':{'rpm':900}}}))
        return source

    def legacy_cli(self):
        mocked = patch.object(hellforge.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stderr='HellForge: Unknown command', stdout=''))
        mocked.start(); self.addCleanup(mocked.stop)
        idle = patch.object(hellforge_legacy, '_idle')
        idle.start(); self.addCleanup(idle.stop)

    def test_all_folder_picker_levels_resolve_to_one_game_copy(self):
        for path in (self.install, self.install/'game', self.install/'game/data', self.install/'game/data/game'):
            cfg = {'game':str(path)}
            self.assertEqual(core.hellforge_root(cfg), self.install)
            self.assertEqual(core.game_dir(cfg), self.install/'game')
            self.assertEqual(core.game_file(cfg,'test'), self.install/'game/data/game/test')
        self.assertEqual(core.game_dir({'game':str(self.root/'Steam')}),self.root/'Steam')

    def test_legacy_deploy_order_options_and_purge_preserve_foreign_mods_and_settings(self):
        self.legacy_cli()
        mods = self.install / 'mods'; mods.mkdir()
        foreign = mods/'foreign'; foreign.mkdir()
        (foreign/'hellforge-mod.json').write_text('{"format":1,"id":"foreign.mod","name":"Foreign"}')
        (foreign/'hellforge-stats.json').write_text('{"format":1}')
        state = {'format':1, 'disabled':['foreign.mod'], 'order':['foreign.mod'], 'share':False, 'packs':{}}
        (mods/'hellforge-mods.json').write_text(json.dumps(state))
        a,b = self.package('a'),self.package('b')
        self.cfg['mods'] = [{'name':p.stem,'path':str(p),'enabled':True} for p in (a,b)]
        game_before = list((self.install/'game').rglob('*'))
        hellforge.deploy(self.cfg,self.install,lambda _:None)
        after = json.loads((mods/'hellforge-mods.json').read_text())
        self.assertEqual(after['order'][:2], ['test.a','test.b'])
        self.assertFalse(after['share'])
        self.assertEqual(after['disabled'], ['foreign.mod'])
        hellforge.deploy(self.cfg,self.install,lambda _:None)  # repeated sync updates owned packages
        self.assertEqual(len(list(mods.glob('moddiver-*.zip'))),2)
        self.assertEqual(hellforge.purge(self.install,lambda _:None),2)
        self.assertTrue((foreign/'hellforge-mod.json').exists())
        self.assertEqual(json.loads((mods/'hellforge-mods.json').read_text())['order'],['foreign.mod'])
        self.assertEqual(list((self.install/'game').rglob('*')),game_before)

    def test_legacy_dry_run_does_not_create_mods_or_receipt(self):
        self.legacy_cli()
        source = self.package('a')
        self.cfg['mods']=[{'name':'A','path':str(source)}]
        hellforge.deploy(self.cfg,self.install,lambda _:None,dry_run=True)
        self.assertFalse((self.install/'mods').exists())
        self.assertFalse(hellforge._receipt_path(self.install).exists())

    def test_legacy_refuses_foreign_identity_and_active_session(self):
        self.legacy_cli()
        mods=self.install/'mods'; mods.mkdir()
        a=self.package('a'); (mods/'foreign.zip').write_bytes(a.read_bytes())
        self.cfg['mods']=[{'name':'A','path':str(a)}]
        with self.assertRaisesRegex(RuntimeError,'outside Laboratory'):
            hellforge.deploy(self.cfg,self.install,lambda _:None)
        with patch.object(hellforge_legacy,'_idle',side_effect=RuntimeError('session is running')):
            with self.assertRaisesRegex(RuntimeError,'session'):
                hellforge_legacy.run(self.install,'mod-switch','--id','test.a','--on','no')
        self.assertFalse((mods/'hellforge-mods.json').exists())

    def test_legacy_pack_options_preserve_unknown_settings(self):
        self.legacy_cli()
        for args in [('mod-pack','--id','pack.test','--option','Extra','--on','no'),
                     ('mod-pack','--id','pack.test','--option','Style','--variant','Blue')]:
            hellforge._run(self.install,*args)
        settings=json.loads((self.install/'mods/hellforge-mods.json').read_text())
        self.assertEqual(settings['packs']['pack.test'],{'off':['Extra'],'sub':{'Style':'Blue'}})

    def test_legacy_bare_patch_pack_has_stable_identity_after_repeated_sync(self):
        self.legacy_cli()
        source=self.root/'Audio.zip'
        with zipfile.ZipFile(source,'w') as archive:
            archive.writestr('data/1234567890abcdef.patch_0',b'patch test')
        self.cfg['mods']=[{'name':'Audio','path':str(source)}]
        hellforge.deploy(self.cfg,self.install,lambda _:None)
        rows=hellforge._mods(self.install)
        identity=rows[0]['id']
        hellforge.deploy(self.cfg,self.install,lambda _:None)
        self.assertEqual([r['id'] for r in hellforge._mods(self.install)],[identity])

    def test_native_stats_validation_uses_scratch_and_keeps_source(self):
        source=self.package('checked')
        before=source.read_bytes()
        with patch.object(hellforge,'_run',return_value={'edits':1}) as cli:
            report=hellforge.validate_package(source,self.install)
        folder=Path(cli.call_args.args[-1])
        self.assertFalse(folder.exists())
        self.assertEqual(source.read_bytes(),before)
        self.assertIn('accepted',report[0])

    def test_audio_uses_selected_deployment_copy_instead_of_stale_steam_cache(self):
        from audio_workspace import AudioWorkspace
        backend=SimpleNamespace(session=SimpleNamespace(stage='ready',ix=SimpleNamespace(game=SimpleNamespace(data=self.root/'steam/data'))),
                                load=Mock(return_value=[]))
        app=SimpleNamespace(cfg=self.cfg)
        audio=SimpleNamespace(app=app,backend=backend,busy=False,perform=Mock())
        AudioWorkspace.connect(audio)
        work=audio.perform.call_args.args[1]
        work()
        self.assertEqual(backend.load.call_args.args[0],str(self.install/'game'))

    def test_raw_sealed_packages_are_rejected_before_any_mod_mutation(self):
        source=self.root/'sealed.zip'
        with zipfile.ZipFile(source,'w') as archive:
            archive.writestr('data/game/generated_test.dl_bin',core.seal(b'payload'*20))
        with patch.object(hellforge,'_run',return_value={'mods':[]}) as cli:
            with self.assertRaisesRegex(ValueError,'HellForge Stats Editor'):
                hellforge.deploy({'mods':[{'name':'Raw','path':str(source)}]},self.install,lambda _:None)
            self.assertEqual(cli.call_count,1)

    def test_stats_export_is_checked_and_failed_check_preserves_previous_export(self):
        doc={'format':1,'weapons':{'AR-23 Liberator':{'rpm':900}}}
        destination=self.root/'stats.zip'
        with patch.object(hellforge,'_run',return_value={'edits':1}) as cli:
            stats.export(self.install,doc,'My stats',destination)
            self.assertEqual(cli.call_args.args[1:3],('check-stats','--mod'))
        parsed=core.parse_mod(destination)
        self.assertEqual(parsed['type'],'HellForge')
        before=destination.read_bytes()
        with patch.object(hellforge,'_run',side_effect=RuntimeError('unknown field')):
            with self.assertRaisesRegex(RuntimeError,'unknown field'):
                stats.export(self.install,doc,'My stats',destination)
        self.assertEqual(destination.read_bytes(),before)
        with self.assertRaisesRegex(ValueError,'outside HellForge'):
            stats.export(self.install,doc,'My stats',self.install/'mods/test.zip')
        for text in ('NaN','Infinity','1e999','"900"','null'):
            with self.assertRaises(ValueError):stats.value(text)
        self.assertEqual(stats.value('[4,4,4,4]'),[4,4,4,4])

    def test_stats_check_omits_unsupported_install_option(self):
        with patch.object(hellforge.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{}')) as run:
            hellforge._run(self.install,'check-stats','--mod',str(self.root))
        self.assertNotIn('--install',run.call_args.args[0])

    def test_gameplay_editors_route_to_hellforge_stats(self):
        from yao_forge import App
        app=SimpleNamespace(cfg=self.cfg, busy=False, open_hellforge_stats=Mock(return_value='stats editor'))
        for method in (App.open_native_editor,App.open_editor_ccm,App.open_editor):
            self.assertEqual(method(app),'stats editor')

    def test_deployment_ui_does_not_request_steam_stock_for_hellforge(self):
        from yao_forge import App
        app=SimpleNamespace(cfg=self.cfg,busy=False,_task=Mock(),_check_for_updates=Mock())
        App.install_all(app)
        self.assertTrue(app._task.called)
        with self.assertRaisesRegex(ValueError,'HellForge Settings'):
            App._begin_steam_verification(app)


class HellForgeSurfaceTests(unittest.TestCase):
    def setUp(self):
        import test_v2_ui
        test_v2_ui.DesktopTests.setUp(self)

    def test_stats_form_adds_selects_edits_removes_and_preserves_imported_fields(self):
        from hellforge_stats_ui import Editor
        editor=Editor(self.app)
        editor.target.set('AR-23 Liberator'); editor.field.set('rpm'); editor.value.set('900')
        editor.add()
        self.assertEqual(editor.doc['weapons']['AR-23 Liberator']['rpm'],900)
        editor.tree.selection_set('0'); editor.select()
        self.assertEqual(editor.value.get(),'900')
        editor.value.set('750'); editor.add()
        self.assertEqual(editor.doc['weapons']['AR-23 Liberator']['rpm'],750)
        editor.tree.selection_set('0'); editor.remove()
        self.assertEqual(editor.doc['weapons'],{})
        editor.value.set('NaN'); editor.add()
        self.assertEqual(editor.doc['weapons'],{})
        editor.destroy()

    def test_hellforge_mode_disables_steam_only_actions_after_worker_completion(self):
        root=Path(self.tmp.name)/'HellForge';root.mkdir()
        (root/'hellforge-install.json').write_text('{}')
        self.app.cfg['game']=str(root)
        self.app.refresh_status()
        self.app._set_buttons(False);self.app._set_buttons(True)
        self.assertTrue(self.app.btn_verify.instate(['disabled']))
        self.assertTrue(self.app.btn_update_builtins.instate(['disabled']))
        self.assertTrue(all(w.instate(['disabled']) for w in self.app.builtin_widgets))


if __name__ == '__main__':
    unittest.main()
