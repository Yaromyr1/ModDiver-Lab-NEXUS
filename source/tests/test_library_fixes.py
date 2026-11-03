import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import core
import lab_storage
import library_presets
import yao_forge


class LibraryFixTests(unittest.TestCase):
    def test_nexus_manual_chef_import_uses_loader_installation(self):
        app = Mock()
        app.busy = False
        app.cfg = {'mods': []}
        app._background_update.side_effect = lambda work, done, label: done(work(), None)
        package = {'name': 'Chef Shared Loader 1.4.1', 'targets': ['boot']}
        with patch.object(yao_forge.nexus_mode, 'NEXUS_BUILD', True), \
             patch.object(core, 'parse_mod', return_value=package), \
             patch.object(core, 'save_config'), \
             patch('tool_installations.replace_chef') as replace:
            yao_forge.App._add_paths(app, ['download.zip'])
        replace.assert_called_once_with(app.cfg, 'download.zip', app.log)
        self.assertFalse(any('not included' in str(call) for call in app.log.call_args_list))

    def test_apply_reads_selection_before_queued_tree_event(self):
        cfg = {'mods': [{'name': 'A'}], 'mod_presets': {'First': {'mods': [{'name': 'B'}]},
                                                    'Second': {'mods': [{'name': 'C'}]}}}
        app = Mock(cfg=cfg, busy=False, gameplay_vars={})
        app.cfg = cfg
        page = Mock(app=app, records={'1': 'Second'}, choice=Mock())
        page.choice.get.side_effect = lambda: page.choice.value
        page.choice.set.side_effect = lambda value: setattr(page.choice, 'value', value)
        page.choice.value = 'First'
        page.list.selection.return_value = ('1',)
        page.selected.side_effect = lambda: library_presets.PresetsPage.selected(page)
        library_presets.PresetsPage.apply(page)
        self.assertEqual(cfg['mods'], [{'name': 'C'}])

    def test_older_imported_editor_does_not_override_new_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundled, imported = root / 'bundle', root / 'editors/shodan'
            for folder, version in ((bundled, '4.6.0'), (imported, '4.1.0')):
                (folder / 'app').mkdir(parents=True)
                (folder / 'SHODAN Stat Editor Offline.exe').write_bytes(b'fixture')
                (folder / 'app/build.txt').write_text('version=' + version)
            with patch.object(core, 'IMPORTED_EDITORS', root / 'editors'):
                self.assertEqual(core._active_editor('shodan', bundled), bundled)
                (imported / 'app/build.txt').write_text('version=4.6.1')
                self.assertEqual(core._active_editor('shodan', bundled), imported)

    def test_storage_excludes_active_and_keeps_saved_component_choices(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'imported').mkdir()
            for name in ('A.zip', 'B.zip'):
                (root / 'imported' / name).write_bytes(b'fixture')
            folder = root / 'imported/Extracted'
            folder.mkdir()
            (folder / 'manifest.json').write_text('{}')
            (folder / 'nested.zip').write_bytes(b'fixture')
            cfg = {'mods': [{'path': str(root / 'imported/A.zip')}],
                   'mod_presets': {'Saved': {'mods': [{'path': str(root / 'imported/B.zip'),
                                                      'selected': {'Part': False}, 'category': 'visual'}]}}}
            def parse(path):
                return dict(path=str(path), name=path.stem, type='data', targets=['example.dl_bin'],
                            options=[{'name': 'Part', 'default': True}])
            with patch.object(core, 'MODS_DIR', root), patch.object(core, 'parse_mod', side_effect=parse):
                records = lab_storage.candidates(cfg)
            self.assertEqual([m['name'] for m in records], ['B', 'Extracted'])
            self.assertEqual(records[0]['selected'], {'Part': False})
            self.assertEqual(records[0]['category'], 'visual')

    def test_unknown_installed_version_offers_download(self):
        for method, updater, current, download in (
            (yao_forge.App.check_shodan_editor_update, yao_forge.shodan_updater, '_current_shodan_version', '_download_shodan_release'),
            (yao_forge.App.check_chef_loader_update, yao_forge.chef_updater, '_current_chef_version', '_download_chef_release')):
            app = Mock(busy=False)
            getattr(app, current).return_value = ()
            app._version_tuple.side_effect = yao_forge.App._version_tuple
            app._check_tool_update.side_effect = lambda *args: yao_forge.App._check_tool_update(app, *args)
            app._update_prompt.side_effect = lambda title, message, confirm: confirm()
            app._background_update.side_effect = lambda work, finished, *args: finished(work(), None)
            app.after.side_effect = lambda delay, callback: callback()
            with patch.object(updater, 'latest_release', return_value={'version': '5.0.0'}), \
                 patch.object(yao_forge.threading, 'Thread') as thread:
                thread.side_effect = lambda target, **kw: SimpleNamespace(start=target)
                method(app)
            getattr(app, download).assert_called_once()

    def test_add_chef_keeps_newer_download_instead_of_reenabling_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            downloaded = root / 'chef.zip'
            downloaded.write_bytes(b'fixture')
            old = dict(name='Chef Shared Loader 1.3.1', path=str(root / 'builtin'), enabled=True)
            new = dict(name='Chef Shared Loader 1.5.0', path=str(downloaded), enabled=False)
            app = Mock(busy=False)
            app.cfg = {'mods': [old, new]}
            app._version_tuple.side_effect = yao_forge.App._version_tuple
            app._task.side_effect = lambda work, done: work()
            with patch.object(core, 'parse_mod', return_value=old.copy()), \
                 patch.object(lab_storage, 'candidates', return_value=[]), \
                 patch('tool_installations.replace_chef') as replace:
                yao_forge.App.install_chef_loader(app)
            replace.assert_called_once_with(app.cfg, str(downloaded), app.log)

    def test_mismatched_editor_version_keeps_existing_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            (source / 'app').mkdir(parents=True)
            (source / 'SHODAN Stat Editor Offline.exe').write_bytes(b'fixture')
            (source / 'app/build.txt').write_text('version=4.1.0')
            active = root / 'editors/shodan'
            active.mkdir(parents=True)
            (active / 'kept.txt').write_text('existing installation')
            with patch.object(core, 'IMPORTED_EDITORS', root / 'editors'):
                with self.assertRaisesRegex(ValueError, 'version'):
                    core.import_editor(source, expected_kind='shodan', expected_version=(4, 5, 1))
            self.assertEqual((active / 'kept.txt').read_text(), 'existing installation')


if __name__ == '__main__':
    unittest.main()
