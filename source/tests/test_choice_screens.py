import gc
import tkinter as tk
import unittest
from unittest.mock import patch

import core
import lab_storage
import test_v2_ui


class ChoiceScreenTests(unittest.TestCase):
    def setUp(self):
        gc.collect()
        test_v2_ui.DesktopTests.setUp(self)
        self.app._end_loading('startup')
        self.app.deiconify()
        self.app.update()

    def assert_centered(self, screen):
        app = self.app
        app.update()
        self.assertTrue(screen.winfo_viewable())
        self.assertIs(screen.master, app)
        self.assertEqual(screen.winfo_width(), app.winfo_width())
        self.assertEqual(screen.winfo_height(), app.winfo_height())
        self.assertIs(app.grab_current(), screen)
        self.assertLessEqual(abs(screen.card.winfo_x() + screen.card.winfo_width()/2 - screen.winfo_width()/2), 1)
        self.assertLessEqual(abs(screen.card.winfo_y() + screen.card.winfo_height()/2 - screen.winfo_height()/2), 1)
        self.assertGreaterEqual(screen.card.winfo_x(), 0)
        self.assertGreaterEqual(screen.card.winfo_y(), 0)
        self.assertFalse(any(isinstance(child, tk.Toplevel) for child in app.winfo_children()))

    def test_all_three_center_and_resize_without_native_windows(self):
        app = self.app
        for fullscreen in (False, True):
            app._set_fullscreen(fullscreen)
            for create in (app.get_mods, app.open_support_page, lambda: lab_storage.StoragePicker(app, [])):
                screen = create()
                self.assert_centered(screen)
                if not fullscreen:
                    app.geometry('1000x680+20+30')
                    self.assert_centered(screen)
                    app.geometry('1250x850+20+30')
                    self.assert_centered(screen)
                screen.cancel_button.invoke()
                self.assertIsNone(app.grab_current())
                self.assertIsNone(app._choice_screen)
        app._set_fullscreen(False)

    def test_escape_from_options_closes_screen_and_keeps_fullscreen(self):
        app = self.app
        app._set_fullscreen(True)
        for create, focused in ((app.get_mods, lambda screen: app.mod_site_buttons[0]),
                                 (app.open_support_page, lambda screen: screen.support_buttons[0]),
                                 (lambda: lab_storage.StoragePicker(app, []), lambda screen: screen.tree)):
            screen = create()
            app.update()
            focused(screen).event_generate('<Escape>')
            app.update()
            self.assertFalse(screen.winfo_exists())
            self.assertIsNone(app.grab_current())
            self.assertTrue(app.attributes('-fullscreen'))
        app._set_fullscreen(False)

    def test_support_links_and_errors_stay_in_panel(self):
        app = self.app
        for index, url in enumerate(('https://www.patreon.com/cw/YaoDev', 'https://ko-fi.com/yaodev')):
            screen = app.open_support_page()
            with patch.object(app, '_open_browser', return_value=False):
                screen.support_buttons[index].invoke()
                self.assertIn('browser', screen.error.get())
                self.assert_centered(screen)
                self.assertGreaterEqual(screen.card.winfo_height(), screen.card.winfo_reqheight())
            with patch.object(app, '_open_browser', return_value=True) as browser:
                screen.support_buttons[index].invoke()
                browser.assert_called_once_with(url)
                self.assertFalse(screen.winfo_exists())
                self.assertIsNone(app.grab_current())

    def test_repeated_open_reuses_panel(self):
        app = self.app
        for create in (app.get_mods, app.open_support_page):
            screen = create()
            self.assertIs(create(), screen)
            with patch.object(app, '_task') as task:
                self.assertIs(app.add_from_lab_storage(), screen)
                task.assert_not_called()
            screen.destroy()

    def test_storage_selection_keyboard_and_accept_preserve_options(self):
        app = self.app
        records = [dict(name=f'Mod {i}', path=str(core.MODS_DIR/f'{i}.zip'), type='data',
                        targets=[], enabled=True, selected={'Optional': False}) for i in range(3)]
        picker = lab_storage.StoragePicker(app, records)
        self.assert_centered(picker)
        picker.tree.focus('1')
        picker.tree.event_generate('<space>')
        app.update()
        self.assertEqual(picker.checked, {'1'})
        picker.select_all()
        self.assertEqual(picker.checked, {'0', '1', '2'})
        picker.set_checked(('0', '2'))
        with patch.object(app, 'refresh_mods'), patch.object(app, 'refresh_status'):
            picker.add.invoke()
        self.assertEqual([entry['name'] for entry in app.cfg['mods']], ['Mod 0', 'Mod 2'])
        self.assertFalse(app.cfg['mods'][0]['selected']['Optional'])
        self.assertIsNot(app.cfg['mods'][0], records[0])
        self.assertIsNone(app.grab_current())

    def test_empty_storage_cancel_and_loading_completion(self):
        app = self.app
        with patch.object(lab_storage, 'candidates', return_value=[]), \
             patch.object(app, '_task', side_effect=lambda work, done: (setattr(app, '_task_result', work()), done())):
            app.add_from_lab_storage()
        picker = app._choice_screen
        self.assert_centered(picker)
        self.assertIn('disabled', picker.add.state())
        picker.cancel_button.invoke()
        self.assertEqual(app.cfg['mods'], [])

    def test_storage_enter_on_cancel_keeps_library_unchanged(self):
        app = self.app
        records = [dict(name='Example', path=str(core.MODS_DIR/'example.zip'), type='data', targets=[])]
        picker = lab_storage.StoragePicker(app, records)
        self.assert_centered(picker)
        picker.select_all()
        picker.cancel_button.focus_set()
        app.update()
        picker.cancel_button.event_generate('<Return>')
        app.update()
        self.assertFalse(picker.winfo_exists())
        self.assertEqual(app.cfg['mods'], [])
        self.assertIsNone(app.grab_current())
