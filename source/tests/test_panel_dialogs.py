import gc
from pathlib import Path
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from tkinter import filedialog as native_files, messagebox as native_messages
import asset_editor
import native_editor
import schema_editor
import panel_dialogs
import test_v2_ui
import test_choice_screens


class PanelDialogTests(unittest.TestCase):
    assert_centered = test_choice_screens.ChoiceScreenTests.assert_centered

    def setUp(self):
        gc.collect()
        test_v2_ui.DesktopTests.setUp(self)
        self.app._end_loading('startup')
        self.app.deiconify()
        self.app.update()
        self.root = Path(self.tmp.name)
        (self.root/'subfolder').mkdir()
        (self.root/'one.zip').write_bytes(b'fixture')
        (self.root/'two.ZIP').write_bytes(b'fixture')
        (self.root/'note.txt').write_text('fixture')

    def loaded(self, picker):
        deadline = time.monotonic()+3
        while picker.error.get() == 'Reading folder…' and time.monotonic() < deadline:
            self.app.update()
            time.sleep(.005)
        self.assertEqual(picker.error.get(), '')
        self.assert_centered(picker)
        for button in picker.option_buttons:
            self.assertGreaterEqual(button.winfo_height(), button.winfo_reqheight())

    def test_messages_yes_no_cancel_and_escape_with_live_timers(self):
        app = self.app
        for response, expected in ((0, None), (1, False), (2, True)):
            ticks = []
            def respond():
                screen = app._choice_screen
                ticks.append(True)
                screen.option_buttons[response].invoke()
            app.after(20, respond)
            self.assertIs(panel_dialogs.messagebox.askyesnocancel('Question', 'Choose.', parent=app), expected)
            self.assertTrue(ticks)
            self.assertIsNone(app.grab_current())
        app.after(20, lambda: app._choice_screen.close())
        self.assertFalse(panel_dialogs.messagebox.askyesno('Question', 'Choose.', parent=app))
        for function in (panel_dialogs.messagebox.showinfo, panel_dialogs.messagebox.showerror, panel_dialogs.messagebox.showwarning):
            app.after(20, lambda: app._choice_screen.cancel_button.invoke())
            function('Information', 'Message', parent=app)
            self.assertIsNone(app._choice_screen)

    def test_name_prompt_accept_and_cancel(self):
        def accept():
            screen = self.app._choice_screen
            screen.value.set('My captured changes')
            screen.option_buttons[1].invoke()
        self.app.after(20, accept)
        self.assertEqual(panel_dialogs.simpledialog.askstring('Capture', 'Name', parent=self.app), 'My captured changes')
        self.app.after(20, lambda: self.app._choice_screen.close())
        self.assertIsNone(panel_dialogs.simpledialog.askstring('Capture', 'Name', parent=self.app))

    def test_color_prompt_validates_then_returns_rgb_and_hex(self):
        def accept():
            screen = self.app._choice_screen
            entries = [w for w in screen.content.winfo_children() if isinstance(w, __import__('tkinter').ttk.Entry)]
            entry = entries[0]
            entry.delete(0, 'end'); entry.insert(0, 'invalid')
            screen.option_buttons[1].invoke()
            self.assertTrue(screen.error.get())
            entry.delete(0, 'end'); entry.insert(0, '#1266d8')
            screen.option_buttons[1].invoke()
        self.app.after(20, accept)
        self.assertEqual(panel_dialogs.colorchooser.askcolor(parent=self.app), ((18, 102, 216), '#1266d8'))
        self.app.after(20, lambda: self.app._choice_screen.close())
        self.assertEqual(panel_dialogs.colorchooser.askcolor(parent=self.app), (None, None))

    def test_native_import_picker_cancel_keeps_source_choice_open(self):
        app = self.app
        observations = []
        def choose_archive():
            parent = app._choice_screen
            with patch.object(panel_dialogs.filedialog, 'askopenfilename', return_value='') as native:
                parent.option_buttons[2].invoke()
                native.assert_called_once()
            observations.append((app._choice_screen is parent, app.grab_current() is parent))
            parent.close()
        app.after(20, choose_archive)
        self.assertIsNone(app._choose_import_source('Import package', [('ZIP', '*.zip')]))
        self.assertEqual(observations, [(True, True)])

    def test_unlock_settings_save_cancel_and_guide_are_centered_panels(self):
        app = self.app
        app.cfg['unlock_groups'] = 63
        screen = app.configure_unlocker()
        self.assert_centered(screen)
        for variable in screen.group_values.values(): variable.set(False)
        screen.cancel_button.invoke()
        self.assertEqual(app.cfg['unlock_groups'], 63)
        screen = app.configure_unlocker()
        for variable in screen.group_values.values(): variable.set(False)
        screen.padding_value.set(True)
        screen.option_buttons[1].invoke()
        self.assertEqual(app.cfg['unlock_groups'], 0)
        self.assertTrue(app.cfg['unlock_padding'])
        guide = app.pages['editor'].payload.show_guide()
        self.assert_centered(guide)
        self.assertGreater(len(guide.guide_text.get('1.0', 'end')), 100)
        guide.close()

    def test_editors_keep_native_dialogs_and_separate_windows(self):
        for module in (native_editor, schema_editor):
            self.assertIs(module.filedialog, native_files)
            self.assertIs(module.messagebox, native_messages)
            self.assertTrue(issubclass(module.Editor, tk.Toplevel))


    def test_audio_studio_uses_full_app_surface(self):
        from choice_screen import ChoiceScreen
        self.assertTrue(issubclass(asset_editor.Editor, ChoiceScreen))
        self.assertFalse(issubclass(asset_editor.Editor, tk.Toplevel))
