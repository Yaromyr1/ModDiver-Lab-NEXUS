import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import core
import custom_tools
import lab_storage
import tool_installations
import test_v2_ui


class CustomToolsTests(unittest.TestCase):
    def test_three_named_slots_and_names_survive_json_roundtrip(self):
        import json
        cfg = {}
        with patch.object(custom_tools.subprocess, 'Popen') as launch:
            for name in ('My editor', 'Lua tools', 'Archive helper'):
                custom_tools.add(cfg, name)
            launch.assert_not_called()
        with self.assertRaises(ValueError):
            custom_tools.add(cfg, 'Fourth')
        self.assertEqual([t['name'] for t in json.loads(json.dumps(cfg))['custom_tools']],
                         ['My editor', 'Lua tools', 'Archive helper'])
        self.assertEqual(len({t['id'] for t in cfg['custom_tools']}), 3)

    def test_invalid_names_and_missing_files_do_not_register(self):
        cfg = {}
        custom_tools.add(cfg, '  Editor  ')
        for value in ('editor', '', 'x'*61, 'bad\nname'):
            with self.assertRaises(ValueError):
                custom_tools.add(cfg, value)
        with tempfile.TemporaryDirectory() as folder:
            record = cfg['custom_tools'][0]
            with self.assertRaises(ValueError):
                custom_tools.attach(record, Path(folder)/'missing.exe')
            self.assertEqual(record['path'], '')

    def test_launch_keeps_spaces_and_metacharacters_as_one_argument(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder)/'my tool & helper.exe'
            exe.write_bytes(b'not executed')
            record = {'name': 'Test'}
            custom_tools.attach(record, exe)
            with patch.object(custom_tools.subprocess, 'Popen') as launch:
                custom_tools.launch(record)
            launch.assert_called_once_with([str(exe.resolve())], cwd=exe.parent, shell=False)
            package = Path(folder)/'loader.zip'
            package.write_bytes(b'not a real archive')
            custom_tools.attach(record, package)
            self.assertEqual(record['kind'], 'loader')
            with self.assertRaises(ValueError):
                custom_tools.launch(record)


class ReplacementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.mods = self.root/'mods'
        self.mods.mkdir()
        p = patch.multiple(core, MODS_DIR=self.mods, IMPORTED_MODS_DIR=self.mods/'imported')
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(core, 'save_config')
        self.save = p.start()
        self.addCleanup(p.stop)

    def test_chef_replaces_active_saved_and_stored_versions(self):
        source = core.BUILTIN/'chef_loader'
        old = self.mods/'old-chef.zip'
        import zipfile
        with zipfile.ZipFile(old, 'w') as z:
            for path in source.rglob('*'):
                if path.is_file():z.write(path,path.relative_to(source).as_posix())
        original = core.parse_mod(old)
        cfg = {'mods': [dict(original, enabled=True)],
               'mod_presets': {'Solo': {'mods': [dict(original, enabled=False)]}}}
        entry = tool_installations.replace_chef(cfg, source)
        self.assertEqual(len(cfg['mods']), 1)
        self.assertFalse(old.exists())
        self.assertTrue(Path(entry['path']).is_file())
        self.assertFalse(cfg['mod_presets']['Solo']['mods'][0]['enabled'])
        self.assertEqual(cfg['mod_presets']['Solo']['mods'][0]['path'], entry['path'])
        tool_installations.replace_chef(cfg, source)
        self.assertEqual(list((self.mods/'imported').iterdir()), [Path(entry['path'])])

    def test_failed_save_rolls_back_existing_chef_and_config(self):
        cfg = {'mods': []}
        entry = tool_installations.replace_chef(cfg, core.BUILTIN/'chef_loader')
        prior = Path(entry['path']).read_bytes()
        before = copy.deepcopy(cfg)
        self.save.side_effect = OSError('disk full')
        with self.assertRaises(OSError):
            tool_installations.replace_chef(cfg, core.BUILTIN/'chef_loader')
        self.assertEqual(cfg, before)
        self.assertEqual(Path(entry['path']).read_bytes(), prior)

    def test_chef_7z_is_repacked_as_valid_managed_zip(self):
        source = self.root/'chef.7z'
        source.write_bytes(b'7z fixture')
        entries = [(p.relative_to(core.BUILTIN/'chef_loader').as_posix(), p.read_bytes())
                   for p in (core.BUILTIN/'chef_loader').rglob('*') if p.is_file()]
        cfg = {'mods': []}
        with patch.object(core, '_read_7z_entries', return_value=entries):
            entry = tool_installations.replace_chef(cfg, source)
        import zipfile
        self.assertTrue(zipfile.is_zipfile(entry['path']))
        self.assertTrue(core.parse_mod(entry['path'])['targets'])
        self.assertTrue(source.exists())

    def test_shodan_replaces_old_payload_without_retained_backup(self):
        source = self.root/'editor-source'
        (source/'app').mkdir(parents=True)
        (source/'SHODAN Stat Editor Offline.exe').write_bytes(b'new fixture; never run')
        (source/'app/build.txt').write_text('version=4.6.0')
        imported = self.root/'editors'
        (imported/'shodan').mkdir(parents=True)
        (imported/'shodan/obsolete.txt').write_text('old')
        with patch.multiple(core, IMPORTED_EDITORS=imported, EDITOR=imported/'shodan'):
            kind, destination = core.import_editor(source, expected_kind='shodan', expected_version=(4,6,0))
        self.assertEqual(kind, 'shodan')
        self.assertFalse((destination/'obsolete.txt').exists())
        self.assertEqual(list(imported.iterdir()), [destination])
        self.assertTrue((source/'SHODAN Stat Editor Offline.exe').is_file())

    def test_storage_delete_removes_only_selected_unused_packages(self):
        selected, keep, active = [self.mods/name for name in ('delete.zip', 'keep.zip', 'active.zip')]
        for path in (selected, keep, active):path.write_bytes(b'keep unless selected')
        cfg = {'mods': [{'path': str(active)}], 'mod_presets': {'Solo': {'mods': [{'path': str(selected)}]}}}
        deleted, failures = lab_storage.delete_packages(cfg, [{'path': str(selected)}])
        self.assertEqual(deleted, {selected})
        self.assertFalse(failures)
        self.assertFalse(selected.exists())
        self.assertTrue(keep.exists())
        self.assertTrue(active.exists())
        self.assertEqual(cfg['mod_presets']['Solo']['mods'], [])
        for path in (active, self.mods, self.root/'outside.zip'):
            with self.assertRaises(ValueError):
                lab_storage.delete_packages(cfg, [{'path': str(path)}])


class ToolsDeckUiTests(unittest.TestCase):
    def setUp(self):
        test_v2_ui.DesktopTests.setUp(self)

    def test_moddiver_editor_is_first_and_has_no_import_update(self):
        self.app._show('tools')
        self.app.update_idletasks()
        first = self.app.moddiver_editor_card.grid_info()
        second = self.app.shodan_editor_card.grid_info()
        self.assertLess((first['row'], first['column']), (second['row'], second['column']))
        self.assertFalse(hasattr(self.app, 'btn_import_ccm'))
        self.assertFalse(hasattr(self.app, 'import_moddiver_editor'))
        self.app._show('creator')
        self.assertLess(self.app.creator_moddiver_card.grid_info()['row'], self.app.creator_shodan_card.grid_info()['row'])
        from tkinter import ttk
        def buttons(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button):
                    yield child
                yield from buttons(child)
        presets = [b for b in buttons(self.app) if b.cget('text') == 'Import presets']
        self.assertGreaterEqual(len(presets), 4)
        for button in presets:
            self.assertEqual(self.app.style.lookup(button.cget('style'), 'background'), self.app.theme['panel2'])

    def test_two_click_registration_and_slot_limit(self):
        app = self.app
        app._show('tools')
        for name in ('Custom editor', 'Custom loader', 'My script'):
            if name == 'Custom editor':
                self.assertEqual(app.add_custom_tool_button['text'], 'Add Custom Tool 1')
            else:
                self.assertEqual(app.add_custom_tool_button['text'], 'Add another tool')
            app.add_custom_tool_button.invoke()
            screen = app._choice_screen
            from tkinter import ttk
            entry = next(w for w in screen.content.winfo_children() if isinstance(w, ttk.Entry))
            entry.insert(0, name)
            screen.option_buttons[1].invoke()
        self.assertIsNone(app.add_custom_tool_button)
        self.assertEqual(len(app.cfg['custom_tools']), 3)
        app.render_custom_tools()
        self.assertEqual(len(app.cfg['custom_tools']), 3)

    def test_rename_validation_then_correction_uses_saved_record(self):
        app = self.app
        first = custom_tools.add(app.cfg, 'First')
        custom_tools.add(app.cfg, 'Second')
        app.render_custom_tools()
        screen = app.add_custom_tool(first)
        from tkinter import ttk
        entry = next(w for w in screen.content.winfo_children() if isinstance(w, ttk.Entry))
        entry.delete(0, 'end')
        entry.insert(0, 'Second')
        screen.option_buttons[1].invoke()
        self.assertTrue(screen.winfo_exists())
        entry.delete(0, 'end')
        entry.insert(0, 'Renamed')
        screen.option_buttons[1].invoke()
        self.assertEqual(app.cfg['custom_tools'][0]['name'], 'Renamed')

    def test_yellow_styles_and_black_hover(self):
        app = self.app
        for style in ('Yellow.TButton', 'Action.Primary.TButton', 'Accent.TButton', 'Options.TButton'):
            self.assertEqual(app.style.lookup(style, 'background'), '#ffd400')
            self.assertEqual(app.style.lookup(style, 'background', ('active',)), '#000000')

    def test_delete_button_tracks_checked_rows(self):
        app = self.app
        picker = lab_storage.StoragePicker(app, [dict(name='One', path=str(core.MODS_DIR/'one.zip'))])
        self.assertIn('disabled', picker.delete.state())
        picker.set_checked(('0',))
        self.assertNotIn('disabled', picker.delete.state())
        screen = picker.delete_selected()
        screen.option_buttons[0].invoke()
        self.assertTrue(picker.winfo_exists())
        self.assertEqual(picker.checked, {'0'})
        picker.destroy()
