import io
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

import core
from archive_codec import Archive, SUFFIXES
from asset_mods import Project
import studio_export as finished
from test_asset_mods import resource_archive


class FinishedModTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.root=Path(temp.name)

    def zip(self,name,archive,folder='data'):
        path=self.root/name
        with zipfile.ZipFile(path,'w') as package:
            package.writestr('manifest.json',json.dumps({'Version':1,'Name':name,'Options':[{'Name':'Enabled','Include':[folder]}]}))
            for suffix,blob in zip(SUFFIXES,archive.blobs):
                package.writestr(folder+'/'+archive.path.name+suffix,blob)
        return path

    def test_combined_audio_visual_zip_is_importable_and_preserves_payloads(self):
        visual=resource_archive(payload=b'new texture metadata',gpu=b'new texture')
        audio=resource_archive(0x535a7bd3e650d799,payload=b'new sound bank',gpu=b'')
        a=self.zip('audio.zip',audio,'sounds')
        v=self.zip('visual.zip',visual)
        output=finished.export(self.root/'combined.zip','My gun',[
            ('Audio',finished.zip_patches(a)),('Visual',finished.zip_patches(v))],target='HellForge')
        parsed=core.parse_mod(output)
        self.assertEqual(parsed['name'],'My gun')
        self.assertEqual(parsed['type'],'arsenal')
        self.assertFalse(parsed.get('runtime'))
        reopened=Project.open(output).archives[0]
        by_type={r.type_hash:r for r in reopened.resources}
        for source in (audio,visual):
            row=by_type[source.resources[0].type_hash]
            for section in range(3): self.assertEqual(reopened.payload(row.index,section),source.payload(0,section))
        with zipfile.ZipFile(output) as package:
            self.assertIn('data/9ba626afa44a3aa3.patch_0.gpu_resources',package.namelist())
            self.assertEqual(json.loads(package.read('moddiver-studio.json'))['resources'],2)

    def test_visual_export_excludes_untouched_audio_resources(self):
        texture=resource_archive(); bank=resource_archive(0x535a7bd3e650d799,payload=b'original bank')
        combined=Archive(texture.path,finished.resource_patch([*finished.resource_rows(texture),*finished.resource_rows(bank)],texture.blobs[0]))
        project=Project(self.root/'source.zip',[combined])
        index=next(r.index for r in combined.resources if r.type_hash==texture.resources[0].type_hash)
        project.copy_resource(0,index,resource_archive(payload=b'new look'),0)
        groups=finished.visual_patches(project)
        output=Archive('9ba626afa44a3aa3.patch_0',groups[0][1])
        self.assertEqual(len(output.resources),1)
        self.assertEqual(output.resources[0].type_hash,texture.resources[0].type_hash)

    def test_overlap_is_rejected_atomically_and_identical_resources_deduplicate(self):
        a,b=resource_archive(payload=b'one'),resource_archive(payload=b'two')
        output=self.root/'previous.zip';output.write_bytes(b'previous export')
        with self.assertRaisesRegex(ValueError,'same resource'):
            finished.export(output,'Overlap',[('A',[('9ba626afa44a3aa3',a.blobs)]),('B',[('9ba626afa44a3aa3',b.blobs)])])
        self.assertEqual(output.read_bytes(),b'previous export')
        finished.export(output,'Same',[('A',[('9ba626afa44a3aa3',a.blobs)]),('B',[('9ba626afa44a3aa3',a.blobs)])])
        self.assertEqual(len(Project.open(output).archives[0].resources),1)

    def test_metadata_is_retained_and_patch_priority_is_numeric(self):
        a=resource_archive(); blobs=list(a.blobs); main=bytearray(blobs[0])
        struct.pack_into('<QQ',main,a.table_offset+40,314,159)
        blobs[0]=bytes(main);a=Archive(a.path,blobs)
        output=Archive(a.path,finished.resource_patch(finished.resource_rows(a),a.blobs[0]))
        self.assertEqual(struct.unpack_from('<QQ',output.blobs[0],output.table_offset+40),(314,159))
        b=resource_archive(payload=b'later')
        finished.export(self.root/'priority.zip','Priority',[('One source',[('9ba626afa44a3aa3',a.blobs),('9ba626afa44a3aa3',b.blobs)])])
        self.assertEqual(Project.open(self.root/'priority.zip').archives[0].payload(0,0),b'later')

    def test_hellforge_native_package_is_not_repacked_as_a_cosmetic(self):
        path=self.root/'native.zip'
        with zipfile.ZipFile(path,'w') as package:
            package.writestr('hellforge-mod.json','{"format":1,"id":"test.native","name":"Native"}')
            package.writestr('hellforge-stats.json','{"format":1}')
        with self.assertRaisesRegex(ValueError,'Mod Library'):finished.zip_patches(path)

    def test_finished_pack_named_hellforge_remains_a_cosmetic_pack(self):
        source=resource_archive()
        output=finished.export(self.root/'named.zip','HellForge gun',[
            ('Visual',[('9ba626afa44a3aa3',source.blobs)])],description='Made for HellForge')
        self.assertEqual(core.parse_mod(output)['type'],'arsenal')
        self.assertEqual(len(finished.zip_patches(output)),1)

    def test_orphan_sidecar_is_rejected_and_default_variants_are_selected(self):
        source=resource_archive(payload=b'first')
        later=resource_archive(payload=b'second')
        path=self.root/'variants.zip'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('manifest.json',json.dumps({'Version':1,'Name':'Variants','Options':[
                {'Name':'Style','SubOptions':[{'Name':'First','Include':['a']},{'Name':'Second','Include':['b']}]}]}))
            for prefix,archive in (('a',source),('b',later)):
                for suffix,blob in zip(SUFFIXES,archive.blobs):z.writestr(prefix+'/'+archive.path.name+suffix,blob)
        groups=finished.zip_patches(path)
        self.assertEqual(len(groups),1)
        self.assertEqual(Archive(source.path,groups[0][1]).payload(0,0),b'first')
        orphan=self.root/'orphan.zip'
        with zipfile.ZipFile(orphan,'w') as z:z.writestr('1234567890abcdef.patch_0.stream',b'no main')
        with self.assertRaises(ValueError):finished.zip_patches(orphan)

    def test_manifest_selection_imports_the_whole_hellforge_package(self):
        folder=self.root/'Native';(folder/'src').mkdir(parents=True)
        manifest=folder/'hellforge-mod.json';manifest.write_text('{"format":1,"id":"test.native","name":"Native"}')
        (folder/'manifest.json').write_text('{"Name":"Cosmetic wrapper"}')
        (folder/'src/mod.c').write_text('source')
        with patch.multiple(core,MODS_DIR=self.root/'mods',IMPORTED_MODS_DIR=self.root/'mods/imported'):
            parsed=core.parse_mod(manifest)
            self.assertEqual(parsed['manifest']['id'],'test.native')
            managed=core.add_to_library(manifest)
            self.assertTrue((managed/'src/mod.c').is_file())
            self.assertEqual(core.parse_mod(managed)['type'],'HellForge')

    def test_rar_uses_the_bounded_archive_reader_and_keeps_native_payloads(self):
        path=self.root/'native.rar';path.write_bytes(b'fixture')
        entries=[('hellforge-mod.json',b'{"format":1,"id":"test.rar","name":"Native RAR"}'),('src/mod.c',b'source')]
        with patch.object(core,'_read_7z_entries',return_value=entries):
            parsed=core.parse_mod(path)
        self.assertEqual(parsed['type'],'HellForge')
        self.assertIn(('src/mod.c',b'source'),parsed['package_entries'])


class StudioSurfaceTests(unittest.TestCase):
    def setUp(self):
        import test_v2_ui
        test_v2_ui.DesktopTests.setUp(self)

    def test_guide_export_navigation_and_shortcuts_do_not_override_text_editing(self):
        from asset_editor import Editor
        from audio_workspace import AudioWorkspace
        with patch.object(AudioWorkspace,'connect'):
            studio=Editor(self.app)
            studio.audio.toggle_guide()
            self.assertEqual(studio.tabs.select(),str(studio.guide))
            studio.guide.topics.selection_set('shortcuts');studio.guide.show()
            self.assertIn('Ctrl+E',studio.guide.text.get('1.0','end'))
            studio.audio.build()
            self.assertEqual(studio.tabs.select(),str(studio.finish))
            action=Mock()
            event=SimpleNamespace(widget=studio.audio.sound_search_entry)
            studio.shortcut(event,action,'<Control-z>')
            action.assert_not_called()
            self.assertEqual(len(studio.tabs.tabs()),4)
            self.app.deiconify();self.app.update()
            studio.tabs.select(studio.audio);self.app.update()
            studio.audio.sound_search_entry.focus_force()
            self.app.update()
            studio.audio.sound_search_entry.event_generate('<F1>');self.app.update()
            self.assertEqual(studio.tabs.select(),str(studio.guide))
            studio.guide.topics.focus_force()
            self.app.update()
            studio.guide.topics.event_generate('<Control-e>');self.app.update()
            self.assertEqual(studio.tabs.select(),str(studio.finish))
            studio.finish.busy=True
            studio.close();self.assertTrue(studio.winfo_exists())
            studio.finish.busy=False;studio.destroy()


if __name__=='__main__':unittest.main()
