"""Prove Studio parity while retaining Nexus-only packaging and runtime limits."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import build_release as release
import maintenance


class NexusStudioReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.root=Path(cls.temp.name)
        cls.stage=release.prepare_nexus_source(cls.root/'source')

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def run_staged(self,code,extra=None):
        env=dict(os.environ)
        env.update(YAO_FORGE_DATA=str(self.root/'test-data'),TEMP=str(self.root),TMP=str(self.root))
        if extra:env.update(extra)
        setup=f'import sys;sys.path[:0]={[str(self.stage),str(release.SOURCE/"tests"),str(self.stage/"vendor/audio_engine/windows") ]!r}\n'
        result=subprocess.run([sys.executable,'-c',setup+code],env=env,capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        return result.stdout

    def test_shared_studio_modules_are_identical_without_general_only_payloads(self):
        for name in ('asset_editor.py','audio_workspace.py','studio_guide.py','studio_finish.py','studio_export.py','AUDIO-STUDIO.md',
                     'schema_document.py','schema_editor.py','game_schema.py','native_names.json'):
            self.assertEqual((self.stage/name).read_bytes(),(release.SOURCE/name).read_bytes(),name)
        for name in ('vendor/editor','builtin/chef_loader','chef_updater.py','shodan_updater.py','moddiver_editor.py','builtin/gameplay/repair-data.json'):
            self.assertFalse((self.stage/name).exists(),name)
        self.assertFalse(any(p.suffix.lower() in ('.zip','.7z','.rar') for p in self.stage.rglob('*') if p.is_file()))
        self.assertTrue((self.stage/'nexus-build.json').is_file())

    def test_native_names_work_without_the_external_editor_bundle(self):
        self.run_staged('''
from pathlib import Path
import schema_document
from schema_document import weapon_names,resource_names
assert not (Path(schema_document.__file__).parent/'vendor/editor').exists()
assert len(weapon_names())>=170
assert all(resource_names()[key]==name for key,name in weapon_names().items())
''')

    def test_default_data_cache_and_baselines_do_not_use_general_locations(self):
        self.run_staged('''
import os
from pathlib import Path
os.environ.pop('YAO_FORGE_DATA',None)
import nexus_mode,core,linux_launcher,build_archive
assert nexus_mode.NEXUS_BUILD
assert core.APP_DATA.name=='ModDiverLabNexus',core.APP_DATA
assert linux_launcher.data_directory().name=='ModDiverLabNexus'
assert build_archive.archive_root().name=='ModDiver Lab Nexus Baseline Data'
assert nexus_mode.SHORTCUT_NAME=='ModDiver Laboratory Nexus'
assert nexus_mode.DESKTOP_ID=='moddiver-laboratory-nexus'
import repair_data,updater
assert repair_data.packages(Path('.'),download=True)==[]
assert not hasattr(updater,'latest_release')
''',{'LOCALAPPDATA':str(self.root/'local'),'XDG_DATA_HOME':str(self.root/'xdg')})

    def test_staged_nexus_studio_opens_and_exports_without_external_editor_imports(self):
        self.run_staged('''
from pathlib import Path
from unittest.mock import patch,Mock
import test_v2_ui,nexus_mode,yao_forge,core
from audio_workspace import AudioWorkspace
from asset_editor import Editor
import studio_export
from test_asset_mods import resource_archive
assert nexus_mode.NEXUS_BUILD
case=test_v2_ui.DesktopTests();case.setUp()
try:
 app=case.app
 assert not app.cfg['check_updates_on_start']
 assert not app.cfg['automated_updates_repairs_on_start']
 assert yao_forge.updater is None and yao_forge.chef_updater is None and yao_forge.shodan_updater is None
 with patch.object(AudioWorkspace,'connect'):
  studio=Editor(app)
  assert len(studio.tabs.tabs())==4
  studio.show_guide();studio.guide.topics.selection_set('shortcuts');studio.guide.show()
  assert 'Ctrl+E' in studio.guide.text.get('1.0','end')
  studio.show_finish()
  source=resource_archive()
  output=Path(core.APP_DATA)/'nexus-finished.zip'
  studio_export.export(output,'Nexus finished mod',[('Visual',[('9ba626afa44a3aa3',source.blobs)])])
  assert core.parse_mod(output)['type']=='arsenal'
  studio.destroy()
finally:case.doCleanups()
''')

    def test_linux_installer_uses_separate_bootstrap_and_menu_shortcut(self):
        source=self.root/'installer';(source/'source').mkdir(parents=True,exist_ok=True)
        (source/'source/nexus-build.json').write_text('{}')
        (source/'source/linux_launcher.py').write_text('# seed')
        (source/'run-linux.sh').write_text('# run')
        data=self.root/'installer-data'
        script=(release.ROOT/'install-linux.sh').read_text(encoding='utf-8')
        code=script.split("<<'PY'\n",1)[1].split('\nPY\n',1)[0]
        with patch.dict(os.environ,XDG_DATA_HOME=str(data)),patch.object(sys,'argv',['installer',str(source)]):
            exec(compile(code,'install-linux.sh','exec'),{})
        self.assertTrue((data/'ModDiverLabNexus/bootstrap/source/nexus-build.json').is_file())
        self.assertFalse((data/'ModDiverLab').exists())
        menu=(data/'applications/moddiver-laboratory-nexus.desktop').read_text(encoding='utf-8')
        self.assertIn('Name=ModDiver Laboratory Nexus',menu)
        self.assertNotIn('/ModDiverLab/bootstrap/',menu)

    def test_nexus_maintenance_rejects_general_baseline_before_touching_any_files(self):
        data=self.root/'ModDiverLabNexus';data.mkdir(exist_ok=True)
        witness=data/'settings';witness.write_text('preserve')
        baseline=self.root/'ModDiver Lab Baseline Data';baseline.mkdir(exist_ok=True)
        plan={'data':str(data),'baseline_data':str(baseline),'uninstall':False}
        with self.assertRaisesRegex(ValueError,'baseline'):
            maintenance.complete(plan,self.root)
        self.assertTrue(witness.is_file())

    def test_nexus_docs_include_handbook_and_state_the_correct_limits(self):
        docs=self.root/'docs';docs.mkdir(exist_ok=True)
        with patch.object(release,'SOURCE',self.stage):release.write_nexus_docs(docs,'2.4.1')
        self.assertEqual((docs/'AUDIO-STUDIO.md').read_bytes(),(release.SOURCE/'AUDIO-STUDIO.md').read_bytes())
        readme=(docs/'NEXUS-README.md').read_text(encoding='utf-8')
        for text in ('ModDiverLabNexus','not included','disabled','local','Finish & export'):
            self.assertIn(text,readme)
        guide=(docs/'HELLFORGE.md').read_text(encoding='utf-8')
        self.assertNotIn('open the Native Data Editor, ModDiverEditor or SHODAN button',guide)


if __name__=='__main__':unittest.main()
