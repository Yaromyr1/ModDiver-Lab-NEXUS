import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock

import actions
import core
import linux_launcher
import updater
import log_events
from test_updater import make_package,release_for,FakeResponse


class DragOrderTests(unittest.TestCase):
    def test_reorder_stays_in_category_and_preserves_other_slots(self):
        mods=[{'name':n,'category':c} for n,c in [('A','gameplay'),('V','visual'),('B','gameplay'),('C','gameplay')]]
        cfg={'mods':mods}
        with patch.object(core,'save_config'):
            self.assertEqual(actions.reorder_mod(cfg,0,3,True),3)
            self.assertEqual([m['name'] for m in mods],['B','V','C','A'])
            self.assertEqual(actions.reorder_mod(cfg,3,0,False),0)
            self.assertEqual([m['name'] for m in mods],['A','V','B','C'])
            self.assertEqual(actions.reorder_mod(cfg,0,1),0)
            self.assertEqual(mods[0]['category'],'visual')
            self.assertEqual(mods[1]['name'],'V')
            moved=actions.reorder_mod(cfg,0,category='loaders')
            self.assertEqual(mods[moved]['name'],'A')
            self.assertEqual(mods[moved]['category'],'loaders')


class LinuxDesktopTests(unittest.TestCase):
    def test_container_opens_steam_on_host(self):
        import os
        with patch.dict(os.environ, YAO_FORGE_DISTROBOX='moddiver-laboratory'), patch.object(core.shutil, 'which', return_value='/usr/bin/distrobox-host-exec'), patch.object(core.subprocess, 'Popen') as launch:
            core.linux_open('steam://rungameid/553850')
            launch.assert_called_once_with(['distrobox-host-exec', 'xdg-open', 'steam://rungameid/553850'])


class LauncherTests(unittest.TestCase):
    def test_seed_and_update_keep_user_data_and_newest_app(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);seed=base/'source';seed.mkdir();data=base/'data';data.mkdir()
            (seed/'yao_forge.py').write_text('VERSION = "2.0.0"\n')
            (seed/'tool.exe').write_bytes(b'windows');(data/'config.json').write_text('preserve me')
            root,current,previous=linux_launcher.prepare(seed,data)
            self.assertEqual((current,previous),('2.0.0',None));self.assertFalse((root/current/'tool.exe').exists())
            pkg=make_package('2.0.1')
            with patch.object(updater.urllib.request,'urlopen',return_value=FakeResponse(pkg)):
                updater.install_update(release_for(pkg,'2.0.1'),data,2)
            root,current,previous=linux_launcher.prepare(seed,data)
            self.assertEqual((current,previous),('2.0.1','2.0.0'))
            self.assertEqual((data/'config.json').read_text(),'preserve me')

    def test_early_crash_rolls_back_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'app';root.mkdir()
            for version in ('2.0.0','2.0.1'):
                (root/version).mkdir();(root/version/'yao_forge.py').touch();(root/version/updater.OK_MARKER).touch()
            updater._write_pointer(root,'2.0.1','2.0.0')
            launch=Mock(return_value=Mock(wait=Mock(return_value=1)))
            self.assertEqual(linux_launcher.run(root,'2.0.1','2.0.0',Path('bootstrap.py'),io.StringIO(),launch),0)
            self.assertEqual(updater.read_pointer(root),('2.0.0',None));self.assertEqual(launch.call_count,2)
            self.assertIn('YAO_FORGE_BOOTSTRAP',launch.call_args.kwargs['env'])

    def test_successfully_running_process_does_not_roll_back(self):
        launch=Mock(return_value=Mock(wait=Mock(side_effect=subprocess.TimeoutExpired('app',4))))
        self.assertEqual(linux_launcher.run(Path('app'),'2.0.1',None,Path('bootstrap.py'),io.StringIO(),launch),0)
        self.assertEqual(launch.call_count,1)


class UpdateProgressTests(unittest.TestCase):
    def test_linux_update_skips_windows_executables(self):
        package=make_package('2.0.1')
        with tempfile.TemporaryDirectory() as folder,patch.object(updater.urllib.request,'urlopen',return_value=FakeResponse(package)):
            updater.install_update(release_for(package,'2.0.1'),folder,2,platform='linux')
            self.assertTrue((Path(folder)/'app/2.0.1/yao_forge.py').is_file())
            self.assertFalse(list(Path(folder).rglob('*.dll')))

    def test_renamed_tool_asset_and_ambiguity(self):
        from release_assets import choose_zip
        release={'assets':[{'name':'chef-release-new-name.zip'},{'name':'source.zip'}]}
        self.assertEqual(choose_zip(release,'old.zip',('chef','loader'))['name'],'chef-release-new-name.zip')
        with self.assertRaises(ValueError):choose_zip({'assets':[{'name':'x.zip'},{'name':'y.zip'}]},'old.zip',('chef',))

    def test_progress_and_duplicate_path_rejection(self):
        package=make_package('2.0.1');events=[]
        with tempfile.TemporaryDirectory() as folder,patch.object(updater.urllib.request,'urlopen',return_value=FakeResponse(package)):
            updater.install_update(release_for(package,'2.0.1'),folder,2,progress=lambda *event:events.append(event))
        self.assertEqual(events[-1],('Ready to restart',1,1))
        self.assertTrue({'Downloading','Verifying','Installing'}.issubset({e[0] for e in events}))
        bad=make_package('2.0.1',extra={'CORE.PY':'collision'})
        with tempfile.TemporaryDirectory() as folder,patch.object(updater.urllib.request,'urlopen',return_value=FakeResponse(bad)):
            with self.assertRaisesRegex(updater.UpdateError,'duplicate'):updater.install_update(release_for(bad,'2.0.1'),folder,2)
            self.assertEqual(updater.read_pointer(Path(folder)/'app'),(None,None))

    def test_unstable_or_malformed_version_rejected(self):
        for value in ('v2.0.0-beta1','release 2.0.0','../2.0.0'):
            with self.assertRaises(updater.UpdateError):updater.canonical_version(value)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.game=self.root/'game';self.game.mkdir();self.stock=self.root/'stock';self.stock.mkdir();(self.stock/'generated_test.dl_bin').write_bytes(b'stock')
        self.patch=patch.multiple(core,APP_DATA=self.root,STOCK=self.stock,BACKUPS=self.root/'backups',DEPLOYED=self.root/'deployed.json')
        self.patch.start();self.addCleanup(self.patch.stop)

    def fixture(self):
        def mod(name,data):return {'name':name,'path':name,'targets':['data/test.txt'],'runtime':False,'candidates':{},'cand_option':{},'files':[{'target':'data/test.txt','option':None,'data':data}]}
        records={'Other':mod('Other',b'other'),'chef shared loader 1':mod('chef shared loader 1',b'chef')}
        cfg={'game':str(self.game),'nomofomo':False,'mods':[{'path':name,'name':name,'enabled':True,'category':'loaders' if 'chef' in name else 'gameplay'} for name in records]}
        return cfg,records

    def test_nexus_chef_preview_deploy_and_purge(self):
        import nexus_mode
        cfg, records = self.fixture()
        messages = []
        with patch.object(nexus_mode, 'NEXUS_BUILD', True), \
             patch.object(core, 'parse_mod', side_effect=lambda path: records[path]):
            self.assertEqual(len(core.deployment_mods(cfg)), 2)
            self.assertEqual(core.deploy(cfg, messages.append, dry_run=True), 1)
            self.assertFalse((self.game / 'data/test.txt').exists())
            self.assertEqual(core.deploy(cfg, messages.append), 1)
            self.assertEqual((self.game / 'data/test.txt').read_bytes(), b'chef')
            self.assertTrue(core.load_deployed())
            core.purge(cfg, messages.append)
            self.assertFalse((self.game / 'data/test.txt').exists())
        self.assertFalse(any('skipped Chef' in message for message in messages))

    def test_chef_last_success_levels_and_purge(self):
        cfg,records=self.fixture();messages=[]
        with patch.object(core,'parse_mod',side_effect=lambda path:records[path]):
            self.assertEqual(core.deploy(cfg,messages.append),1)
        self.assertEqual((self.game/'data/test.txt').read_bytes(),b'chef')
        self.assertEqual(log_events.classify(messages[-1]),'success')
        core.purge(cfg,lambda _:None);self.assertFalse((self.game/'data/test.txt').exists())

    def test_loader_first_and_moving_loader_out_of_group_changes_priority(self):
        cfg, records = self.fixture()
        cfg['loaders_deploy_first'] = True
        with patch.object(core, 'parse_mod', side_effect=lambda path: records[path]):
            core.deploy(cfg, lambda _: None)
        self.assertEqual((self.game/'data/test.txt').read_bytes(), b'other')
        core.purge(cfg, lambda _: None)
        cfg['loaders_deploy_first'] = False
        cfg['mods'][1]['category'] = 'visual'
        with patch.object(core, 'parse_mod', side_effect=lambda path: records[path]):
            core.deploy(cfg, lambda _: None)
        self.assertEqual((self.game/'data/test.txt').read_bytes(), b'other')

    def test_failed_write_keeps_recovery_journal(self):
        cfg,records=self.fixture();original=core.atomic_write
        def fail(path,data):
            if Path(path).name=='test.txt' and data != b'':raise OSError('simulated disk failure')
            original(path,data)
        with patch.object(core,'parse_mod',side_effect=lambda path:records[path]),patch.object(core,'atomic_write',side_effect=fail):
            with self.assertRaises(OSError):core.deploy(cfg,lambda _:None)
        self.assertEqual(core.load_deployed(), {})
        self.assertFalse((self.game/'data/test.txt').exists())

    def test_dry_run_does_not_write_game_or_manifest(self):
        cfg,records=self.fixture()
        with patch.object(core,'parse_mod',side_effect=lambda path:records[path]):self.assertEqual(core.deploy(cfg,lambda _:None,dry_run=True),1)
        self.assertFalse((self.game/'data').exists());self.assertFalse(core.DEPLOYED.exists());self.assertFalse(core.BACKUPS.exists())

    def test_partial_deployment_is_not_green_completion(self):
        cfg,records=self.fixture();cfg['mods'].append({'path':'missing','name':'missing','enabled':True});messages=[]
        with patch.object(core,'parse_mod',side_effect=lambda path:records[path]):core.deploy(cfg,messages.append)
        self.assertEqual(log_events.classify(messages[-1]),'error');self.assertIn('incomplete',messages[-1])


if __name__=='__main__':unittest.main()
