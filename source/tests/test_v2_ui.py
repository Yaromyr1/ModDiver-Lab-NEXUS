import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core
import localization
import yao_forge
from yao_forge import App,VERSION


class DesktopTests(unittest.TestCase):
    def test_library_gradient_resize_does_not_change_requested_geometry(self):
        import ui_polish
        app = self.app
        app.deiconify()
        for geometry in ('1180x820+0+0', '1400x900+0+0', '1000x720+0+0'):
            app.geometry(geometry)
            app.update()
            ui_polish.refresh(app)
            app.update()
            for frame in (app.main_surface, app.content, app.pages['mods']):
                background = frame._library_surface_canvas
                self.assertEqual(background.winfo_manager(), 'place')
                self.assertLessEqual(background.winfo_reqheight(), 2)
                self.assertEqual(background.winfo_height(), frame.winfo_height())
            self.assertEqual(app.btn_lab_storage.winfo_rooty(), app.btn_presets.winfo_rooty())
        app._show('about')
        ui_polish.refresh(app)
        self.assertEqual(app.main_surface._library_surface_canvas.winfo_manager(), '')
        self.assertIn('11', app.about_text.tag_cget('warning', 'font'))
        self.assertNotIn('bold', app.about_text.tag_cget('warning', 'font'))

    def test_presets_are_a_library_subpage_with_saved_compositions(self):
        import library_presets
        app = self.app
        app.cfg['mods'] = [dict(name='A', path=self.tmp.name, enabled=True, type='data', targets=[], selected={'Part': False}),
                           dict(name='B', path=self.tmp.name, enabled=False, type='data', targets=[])]
        app.refresh_mods()
        app.btn_presets.invoke()
        self.assertEqual(app.current, 'presets')
        page = app.pages['presets']
        page.name.insert(0, 'Co-op')
        page.create()
        self.assertEqual(app.cfg['active_mod_preset'], 'Co-op')
        library_presets.save_as(app.cfg, 'Solo')
        app.cfg['mods'].reverse()
        page.choice.set('Co-op')
        page.apply()
        self.assertEqual(app.current, 'mods')
        self.assertEqual([m['name'] for m in app.cfg['mods']], ['A', 'B'])
        self.assertFalse(app.cfg['mods'][0]['selected']['Part'])
        self.assertIs(app.btn_export.master, app.btn_install.master)
        self.assertIs(app.btn_import.master, app.btn_purge.master)
        self.assertIs(app.btn_capture.master, app.btn_export.master)
        self.assertIs(app.btn_lab_storage.master, app.btn_presets.master)
        self.assertEqual(app.mod_card_widgets[0].trash_widget.cget('highlightbackground'), '#e3342f')
        self.assertEqual(len(app.mod_canvas.find_withtag('library-gradient')), 96)

    def test_theme_preserves_cards_and_loading_reports_measured_progress(self):
        app = self.app
        app.cfg['mods'] = [dict(name='Example', path=self.tmp.name, enabled=True,
                                type='data', targets=[], options=[])]
        app.refresh_mods()
        card = app.mod_card_widgets[0]
        app._set_theme(panel='#123456', text='#fafafa')
        self.assertIs(app.mod_card_widgets[0], card)
        self.assertEqual(card.cget('bg'), '#123456')
        app._set_buttons(False)
        app.report_progress('Merging files', 37, 100)
        app._drain()
        panel, bar = app._loading_windows[app]
        self.assertEqual(bar['value'], 37)
        self.assertEqual(bar.itemcget(bar.find_all()[-1], 'text'), '37%')
        self.assertIsNone(bar.timer)
        app._set_buttons(True)

    def test_free_category_drag_trash_and_loader_order(self):
        from types import SimpleNamespace
        app = self.app
        source = Path(self.tmp.name)/'mod.txt'
        source.write_text('keep this source')
        app.cfg['mods'] = [dict(name='Any Mod', path=str(source), enabled=True,
                                type='data', targets=[], category='visual')]
        app.deiconify(); app.update(); app.refresh_mods(); app.update()
        self.assertEqual(list(app._category_headers), ['loaders', 'gameplay', 'visual'])
        self.assertFalse(hasattr(app, 'development_canvas'))
        self.assertFalse(hasattr(app, 'toggle_category'))
        self.assertNotIn('Remove', [b.cget('text') for b in app.mod_action_buttons])
        card = app.mod_card_widgets[0]
        for category in ('loaders', 'gameplay', 'visual'):
            start = card.winfo_rooty()+20
            end = app._category_headers[category].winfo_rooty()+10
            app._drag_mod_press(0, SimpleNamespace(y_root=start))
            app._drag_mod_release(0, SimpleNamespace(y_root=end))
            app.update()
            self.assertEqual(app.cfg['mods'][0]['category'], category)
            self.assertIs(app.mod_card_widgets[0], card)
        self.assertEqual(app.loader_order_button.cget('bg'), '#666666')
        self.assertEqual(app.subtitle_label.cget('text'), 'Add any mods, merge and deploy them with one click')
        self.assertEqual(app._loader_order_icon.get(23, 20), (255, 255, 255))
        self.assertTrue(app._loader_order_icon.transparency_get(23, 18))
        self.assertTrue(app.loader_order_button.cget('image'))
        self.assertEqual(app.loader_order_hint.cget('text'), 'Click to change order')
        app.loader_order_button.invoke()
        self.assertTrue(app.cfg['loaders_deploy_first'])
        self.assertEqual(app.loader_order_button.cget('text'), 'LOADERS DEPLOY FIRST')
        self.assertEqual(app.loader_order_button.cget('bg'), '#ffd400')
        self.assertEqual(app._loader_order_icon.get(23, 18), (17, 17, 17))
        self.assertTrue(app._loader_order_icon.transparency_get(23, 20))
        app.loader_order_button.invoke()
        self.assertFalse(app.cfg['loaders_deploy_first'])
        app.theme['accent'] = '#70b7ff'; app.apply_theme()
        self.assertEqual(app._trash_icon.get(7, 21), (227, 52, 47))
        self.assertEqual(app._trash_icon.get(10, 10), (112, 183, 255))
        app.mod_card_widgets[0].trash_widget.invoke()
        self.assertEqual(app.cfg['mods'], [])
        self.assertEqual(source.read_text(), 'keep this source')

    def test_native_surface_erase_uses_theme_and_fullscreen_repeats(self):
        import os
        if os.name != 'nt':self.skipTest('Windows native surface')
        import ctypes
        from ctypes import wintypes
        app = self.app
        app.deiconify(); app.update()
        user, gdi = ctypes.windll.user32, ctypes.windll.gdi32
        user.GetDC.restype = wintypes.HDC
        user.GetDC.argtypes = [wintypes.HWND]
        user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        gdi.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        gdi.GetPixel.restype = wintypes.COLORREF
        user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        for enabled in (False, True, False, True, False):
            app._set_fullscreen(enabled); app.update()
            self.assertEqual(bool(app.attributes('-fullscreen')), enabled)
        self.assertTrue(user.IsWindow(app._surface_hwnd))
        # A memory DC avoids child-window clipping on the real root surface.
        gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi.CreateCompatibleDC.restype = wintypes.HDC
        gdi.CreateBitmap.restype = wintypes.HBITMAP
        gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        gdi.SelectObject.restype = wintypes.HGDIOBJ
        gdi.DeleteDC.argtypes = [wintypes.HDC]
        dc = gdi.CreateCompatibleDC(None)
        bitmap = gdi.CreateBitmap(8, 8, 1, 32, None)
        previous = gdi.SelectObject(dc, bitmap)
        try:
            user.SendMessageW(app._surface_hwnd, 0x14, dc, 0)
            self.assertEqual(gdi.GetPixel(dc, 5, 5), app._bgr(app.theme['bg']))
        finally:
            gdi.SelectObject(dc, previous)
            gdi.DeleteObject(bitmap)
            gdi.DeleteDC(dc)
            yao_forge.window_surface.repaint(app)

    def test_fullscreen_and_maintenance_controls(self):
        app = self.app
        app.exit_fullscreen_button.invoke()
        app.update_idletasks()
        self.assertFalse(app.attributes('-fullscreen'))
        self.assertEqual(app.exit_fullscreen_button.cget('text'), 'ESC')
        self.assertEqual(app.delete_local_data_button.cget('text'), 'DELETE LOCAL DATA')
        for button in (app.restart_button, app.delete_local_data_button):
            self.assertEqual(button.master.master, app.utilities_section)
            self.assertEqual(app.style.lookup(button.cget('style'), 'background'), '#b83242' if button is app.delete_local_data_button else '#1266a8')
        self.assertEqual(app.restart_button.master, app.delete_local_data_button.master)
        self.assertEqual(app.restart_button.pack_info()['side'], 'left')
        self.assertEqual(app.delete_local_data_button.pack_info()['side'], 'left')
        self.assertEqual(app.shortcut_button.master, app.utilities_section)
        self.assertEqual(app.style.lookup(app.shortcut_button.cget('style'), 'background'), '#555555')
        self.assertEqual(app.delete_local_data_description.master, app.utilities_section)
        self.assertEqual(app.style.lookup(app.os_label.cget('style'), 'bordercolor'), '#258be0')
        self.assertTrue(app.os_label.cget('text'))
        with patch.object(app, '_can_close', return_value=True), patch.object(app, '_ask_themed', return_value=False), patch.object(yao_forge.maintenance, 'launch') as launch:
            app.uninstall_button.invoke()
            launch.assert_not_called()
        with patch.object(app, '_can_close', return_value=True), patch.object(app, '_ask_themed', return_value=True), patch.object(app, '_maintain_installation') as maintain:
            app.uninstall_button.invoke()
            maintain.assert_called_once_with(uninstall=True)
        with patch.object(yao_forge.maintenance, 'make_plan', side_effect=ValueError('bad installation')), patch.object(yao_forge.messagebox, 'showerror'), patch.object(app, '_close') as close:
            app._maintain_installation(False)
            close.assert_not_called()

    def test_maximize_reenters_fullscreen_and_escape_restores_window(self):
        app = self.app
        app.fullscreen_check.invoke()
        app.deiconify()
        app.update()
        app.exit_fullscreen_button.invoke()
        app.update()
        self.assertFalse(app.attributes('-fullscreen'))
        if app.tk.call('tk', 'windowingsystem') == 'x11':
            app.attributes('-zoomed', True)
        else:
            app.state('zoomed')
        app.update()
        self.assertTrue(app.attributes('-fullscreen'))
        app.event_generate('<Escape>')
        app.update()
        self.assertFalse(app.attributes('-fullscreen'))
        self.assertEqual(app.state(), 'normal')

    def test_standard_maximize_is_default_and_fullscreen_option_is_saved(self):
        app = self.app
        app.deiconify()
        app.update()
        self.assertFalse(app.fullscreen_on_maximize.get())
        self.assertFalse(app.attributes('-fullscreen'))
        app.state('zoomed')
        app.update()
        self.assertFalse(app.attributes('-fullscreen'))
        self.assertEqual(app.state(), 'zoomed')
        app.fullscreen_check.invoke()
        app.update()
        self.assertTrue(core.save_config.call_args.args[0]['fullscreen_on_maximize'])
        self.assertTrue(app.attributes('-fullscreen'))
        app.fullscreen_check.invoke()
        app.update()
        self.assertFalse(app.attributes('-fullscreen'))

    def test_uninstall_dialog_uses_yes_no_and_current_theme(self):
        import tkinter as tk
        from tkinter import ttk
        app = self.app
        app.deiconify(); app.update()
        app.theme.update(yao_forge.THEMES['Midnight']); app.apply_theme()
        def decline():
            screen = app._choice_screen
            self.assertEqual(screen.cget('bg'), app.theme['bg'])
            self.assertEqual(screen.cancel_button.cget('text'), 'No')
            screen.cancel_button.invoke()
        app.after(100, decline)
        with patch.object(app, '_maintain_installation') as maintain:
            app._uninstall_app()
            maintain.assert_not_called()

    def test_log_font_is_independent_saved_and_reset(self):
        app = self.app
        self.assertEqual(app.theme.get('log_font'), 12)
        app._set_theme(log_font=17)
        app._apply_pending_theme()
        for widget in (app.log_text, app.deploy_log):
            self.assertEqual(int(widget.tk.splitlist(widget.cget('font'))[1]), 17)
        self.assertEqual(app.cfg['theme']['log_font'], 17)
        self.assertEqual(app.theme['font'], 10)
        app.apply_reset()
        self.assertEqual(app.theme['log_font'], 12)
        self.assertEqual(app.log_font_scale.get(), 12)

    def test_loading_lifecycle_and_theme(self):
        app = self.app
        app._end_loading('startup')
        app._set_buttons(False)
        panel, bar = app._loading_windows[app]
        self.assertEqual(panel.winfo_manager(), 'place')
        self.assertIsNotNone(bar.timer)
        self.assertEqual(bar.itemcget(bar.find_all()[-1], 'text'), 'IN PROGRESS')
        self.assertEqual(panel.brand.label.cget('text'), 'MODDIVER LABORATORY')
        self.assertEqual(panel.brand.label.cget('fg'), app.theme['accent'])
        self.assertTrue(panel.brand.flask.cget('image'))
        app._set_theme(bg='#112233')
        self.assertEqual(panel.cget('bg'), '#112233')
        self.assertEqual(bar.cget('bg'), '#112233')
        app._set_theme(accent='#63e6be')
        self.assertEqual(panel.brand.label.cget('bg'), '#112233')
        self.assertEqual(panel.brand.label.cget('fg'), '#63e6be')
        app._begin_loading('second')
        app._set_buttons(True)
        self.assertEqual(panel.winfo_manager(), 'place')
        app._end_loading('second')
        self.assertEqual(panel.winfo_manager(), '')
        self.assertIsNone(bar.timer)

    def test_builtin_repair_is_only_started_by_creator_button(self):
        app = self.app
        self.assertFalse(any('builtin' in callback for callback in self.startup_callbacks))
        self.assertEqual(app.btn_update_builtins.cget('text'), 'Update / repair built-in mods')
        with patch('builtin_updater.run_worker', return_value={}) as ensure:
            with patch.object(app, '_task', side_effect=lambda work, done: work()):
                app.btn_update_builtins.invoke()
            ensure.assert_called_once_with(dict(app.cfg), app.log)
        self.assertEqual(app.current, 'log')
        for header in app._category_headers.values():
            self.assertTrue(header.cget('image'))
        self.assertTrue(app.btn_get_mods.cget('image'))

    def test_builtin_worker_results_have_exact_green_red_summaries(self):
        import builtin_updater
        app = self.app
        success = {key: Path(self.tmp.name)/key for key in builtin_updater.NAMES}
        for result, message, tag in (
                (success, 'BUILT-IN MODS REPAIRED/UPDATED SUCCESSFULLY', 'success'),
                ({**success, 'nomofomo': 'repair failed'}, 'FAILED TO REPAIR/UPDATE BUILT-IN MODS', 'error'),
                ({}, 'FAILED TO REPAIR/UPDATE BUILT-IN MODS', 'error'),
                (None, 'FAILED TO REPAIR/UPDATE BUILT-IN MODS', 'error')):
            app.clear_log()
            def immediate(work, done):
                app._task_result = result
                done()
            with patch.object(app, '_task', side_effect=immediate):
                app.btn_update_builtins.invoke()
            app._drain()
            index = app.log_text.search(message, '1.0', exact=True)
            self.assertTrue(index)
            self.assertIn(tag, app.log_text.tag_names(index))
        self.assertTrue(app.brand_image.width())
        self.assertFalse(app.about_text.image_names())
        self.assertIn('User guide', app.about_text.get('1.0', 'end'))

    def test_task_error_also_stops_loading(self):
        import time
        app = self.app
        app._end_loading('startup')
        completed = []
        app._task(lambda: (_ for _ in ()).throw(ValueError('test failure')), lambda: completed.append(True))
        deadline = time.monotonic() + 5
        def poll():
            if completed or time.monotonic() > deadline: app.quit()
            else: app.after(20, poll)
        app.after(20, poll)
        app.mainloop()
        self.assertTrue(completed)
        self.assertFalse(app.busy)
        self.assertEqual(app._loading_windows[app][0].winfo_manager(), '')

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        cfg={'game':self.tmp.name,'mods':[],'theme':dict(core.DEFAULT_THEME),'nomofomo':False}
        self.load=patch.object(core,'load_config',return_value=cfg);self.load.start();self.addCleanup(self.load.stop)
        self.save=patch.object(core,'save_config');self.save.start();self.addCleanup(self.save.stop)
        self.app=App();self.app.withdraw();self.addCleanup(self.app.destroy)
        self.startup_callbacks = [str(self.app.tk.call('after', 'info', timer))
                                  for timer in self.app.tk.call('after', 'info')]
        for token in self.app.tk.call('after','info'):self.app.tk.call('after', 'cancel', token)

    def test_theme_accent_and_centered_update_dialog(self):
        import tkinter as tk
        from tkinter import ttk
        app = self.app
        app.deiconify()
        app.update()
        app.theme['accent'] = '#63e6be'
        app.apply_theme()
        self.assertEqual(app.advanced_creator.cget('highlightbackground'), '#ffd400')
        self.assertEqual(app.advanced_creator.cget('highlightthickness'), 1)
        for button in app.mod_action_buttons[:2]:
            self.assertEqual(app.style.lookup(button.cget('style'), 'background'), '#63e6be')

        def accept():
            screen = app._choice_screen
            self.assertEqual(screen.cget('bg'), app.theme['bg'])
            self.assertLessEqual(abs(screen.card.winfo_rootx() + screen.card.winfo_width()/2 -
                                     app.winfo_rootx() - app.winfo_width()/2), 2)
            screen.option_buttons[1].invoke()
        app.after(100, accept)
        self.assertTrue(app._ask_themed('Update', 'Install the update?'))

    def test_shared_popup_scrollbars_and_cursors(self):
        import tkinter as tk
        from tkinter import ttk
        from types import SimpleNamespace
        app = self.app
        popup = tk.Toplevel(app)
        self.addCleanup(popup.destroy)
        button = ttk.Button(popup, text='Action')
        button.pack()
        link = tk.Label(popup, text='Link')
        link.bind('<Button-1>', lambda event: None)
        link.pack()
        entry = ttk.Entry(popup)
        for widget in (button, link, entry):
            app._clickable_cursor(SimpleNamespace(widget=widget))
        self.assertEqual(str(button.cget('cursor')), 'hand2')
        self.assertEqual(str(link.cget('cursor')), 'hand2')
        self.assertNotEqual(str(entry.cget('cursor')), 'hand2')
        button.configure(state='disabled')
        app._clickable_cursor(SimpleNamespace(widget=button))
        self.assertEqual(str(button.cget('cursor')), 'arrow')
        with patch.object(app, '_dark_titlebar') as titlebar:
            app._style_mapped_widget(SimpleNamespace(widget=popup))
            app.update_idletasks()
            titlebar.assert_any_call(popup)
            app.theme.update(panel2='#123456', bg='#eeeeee')
            app.apply_theme()
            titlebar.assert_any_call(popup)
        for orientation in ('Vertical', 'Horizontal'):
            style = orientation + '.TScrollbar'
            self.assertEqual(app.style.lookup(style, 'background'), '#123456')
            self.assertEqual(app.style.lookup(style, 'troughcolor'), '#eeeeee')
            self.assertEqual(app.style.lookup(style, 'background', ('active',)), app.theme['muted'])

    def test_purge_confirmation_is_visible_without_native_modal_or_nested_wait(self):
        import tkinter as tk
        app = self.app
        app.deiconify(); app.update()
        windows = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
        with patch.object(app, '_task') as task, patch.object(app, 'wait_window', side_effect=AssertionError('nested modal')):
            app.purge_mod_library()
            panel = app._confirmation_panel
            app.update()
            self.assertTrue(panel.winfo_viewable())
            self.assertIs(app.grab_current(), panel)
            self.assertEqual([w for w in app.winfo_children() if isinstance(w, tk.Toplevel)], windows)
            # Repeated clicks keep one prompt; timers still run while it is open.
            app.purge_mod_library()
            self.assertIs(app._confirmation_panel, panel)
            beat = []
            app.after(0, lambda: beat.append(True))
            app.update()
            self.assertEqual(beat, [True])
            task.assert_not_called()
            panel.cancel_button.invoke()
            self.assertFalse(panel.winfo_exists())
            self.assertIsNone(app.grab_current())
            task.assert_not_called()
            app.purge_mod_library()
            app._confirmation_panel.confirm_button.invoke()
            task.assert_called_once()
            self.assertIsNone(app._confirmation_panel)
            self.assertIsNone(app.grab_current())

    def test_purge_confirmation_stays_inside_fullscreen_app(self):
        app = self.app
        app.deiconify(); app.update()
        app._set_fullscreen(True); app.update()
        with patch.object(app, '_task') as task:
            app.purge_mod_library()
            app.update()
            panel = app._confirmation_panel
            self.assertTrue(panel.winfo_viewable())
            self.assertIs(panel.master, app)
            panel.cancel_button.invoke()
            app.update()
            self.assertIsNone(app.grab_current())
            task.assert_not_called()
        app._set_fullscreen(False)

    def test_purge_confirmation_escape_and_default_enter_cancel(self):
        app = self.app
        app.deiconify(); app.update()
        with patch.object(app, '_task') as task:
            for key in ('<Escape>', '<Return>'):
                app.purge_mod_library()
                panel = app._confirmation_panel
                app.update()
                panel.cancel_button.event_generate(key)
                app.update()
                self.assertIsNone(app._confirmation_panel)
                self.assertIsNone(app.grab_current())
            task.assert_not_called()

    def test_confirmed_library_purge_completes_in_worker_and_restores_controls(self):
        import time
        import threading
        app = self.app
        app.deiconify(); app.update()
        data = Path(self.tmp.name) / 'isolated-data'
        mods = data / 'mods'
        mods.mkdir(parents=True)
        source = mods / 'example.bin'
        source.write_bytes(b'test library data')
        backup = data / 'backups' / 'keep.bin'
        backup.parent.mkdir(); backup.write_bytes(b'keep')
        app.cfg['mods'] = [dict(name='Example', path=str(source), type='data', targets=[], enabled=True)]
        app.refresh_mods()
        errors = []
        original_purge = core.purge_mod_library
        threads = []
        def slow_purge(*args):
            threads.append(threading.current_thread())
            time.sleep(.15)
            return original_purge(*args)
        with patch.object(core, 'APP_DATA', data), patch.object(core, 'MODS_DIR', mods), \
                patch.object(core, 'purge_mod_library', side_effect=slow_purge), \
                patch.object(app, 'report_callback_exception', side_effect=lambda *args: errors.append(args)):
            app.purge_mod_library()
            self.assertTrue(source.exists())
            app._confirmation_panel.confirm_button.invoke()
            self.assertTrue(app.busy)
            heartbeats = []
            app.after(20, lambda: heartbeats.append(True))
            deadline = time.monotonic() + 5
            while app.busy and time.monotonic() < deadline:
                app.update()
                time.sleep(.005)
            app.update()
        self.assertFalse(app.busy)
        self.assertTrue(heartbeats)
        self.assertNotEqual(threads, [threading.current_thread()])
        self.assertEqual(app.cfg['mods'], [])
        self.assertEqual(app.mod_card_widgets, {})
        self.assertFalse(source.exists())
        self.assertEqual(backup.read_bytes(), b'keep')
        self.assertIsNone(app.grab_current())
        self.assertEqual(errors, [])
        self.assertEqual(str(app.btn_purge_library.cget('state')), 'normal')

    def test_mod_options_are_in_app_and_save_immediately(self):
        import tkinter as tk
        app = self.app
        mod = dict(name='Theme test', path=self.tmp.name, enabled=True,
                   type='data', targets=[], options=['First', 'Second'])
        app.cfg['mods'] = [mod]
        app.refresh_mods(); app.selected_mod_index = 0
        app.deiconify(); app.update(); app.configure_mod(); app.update()
        self.assertEqual(app.current, 'options')
        self.assertFalse(any(isinstance(w, tk.Toplevel) and not getattr(w, '_loading_popup', False) for w in app.winfo_children()))
        page = app.pages['options']
        core.save_config.reset_mock()
        page.buttons['First'].invoke()
        self.assertFalse(mod['selected']['First'])
        core.save_config.assert_called_once_with(app.cfg)
        app._set_theme(accent='#63e6be')
        self.assertEqual(app.style.lookup('Accent.TButton', 'background'), '#63e6be')
        self.assertEqual(app.advanced_creator.cget('highlightbackground'), '#ffd400')
        app._show('mods'); app.configure_mod()
        self.assertFalse(app.pages['options'].variables['First'].get())

    def test_long_and_repeated_options_toggle_and_bulk_save(self):
        app = self.app
        names = ['Very long option name ' * 15] + [f'Option {i}' for i in range(80)] + ['Option 0']
        mod = dict(name='Large options', path=self.tmp.name, enabled=True,
                   type='data', targets=[], options=names)
        app.cfg['mods'] = [mod]
        app.refresh_mods(); app.selected_mod_index = 0
        app.deiconify(); app.update(); app.configure_mod(); app.update()
        page = app.pages['options']
        self.assertEqual(len(page.buttons), len(set(names)))
        first = next(iter(page.buttons.values()))
        self.assertLessEqual(first.winfo_rootx()+first.winfo_width(), page.winfo_rootx()+page.winfo_width())
        for enabled in (False, True, False):
            core.save_config.reset_mock()
            page.set_all(enabled)
            core.save_config.assert_called_once_with(app.cfg)
            self.assertTrue(all(value == enabled for value in mod['selected'].values()))
        page.buttons['Option 0'].invoke()
        self.assertTrue(mod['selected']['Option 0'])
        self.assertTrue(all(not value for key, value in mod['selected'].items() if key != 'Option 0'))

    def test_native_editors_have_standard_window_controls(self):
        import native_editor
        import schema_editor
        for editor_class in (native_editor.Editor, schema_editor.Editor):
            editor = editor_class(self.app)
            try:
                editor.update()
                self.assertFalse(editor.transient())
                self.assertEqual(tuple(map(int, editor.resizable())), (1, 1))
                import ctypes
                user32 = ctypes.windll.user32
                hwnd = user32.GetAncestor(editor.winfo_id(), 2)
                style = user32.GetWindowLongW(hwnd, -16)
                self.assertEqual(style & 0x30000, 0x30000)
            finally:
                editor.destroy()

    def test_mod_options_numbers_and_deployment_borders(self):
        app = self.app
        folder = Path(self.tmp.name)
        app.cfg['mods'] = [{'name': name, 'path': str(folder / name), 'enabled': True,
                            'type': 'data', 'targets': [], 'category': 'gameplay'}
                           for name in ('Installed', 'Pending')]
        receipt = {'data/a': {'mods': ['Installed'], 'sources': [str(folder / 'Installed')]}}
        with patch.object(core, 'load_deployed', return_value=receipt):
            app.refresh_mods()
            self.assertEqual(app.mod_card_widgets[0].preview_widget.cget('highlightbackground'), '#238636')
            self.assertEqual(app.mod_card_widgets[1].preview_widget.cget('highlightbackground'), '#b42318')
            self.assertEqual(app.mod_card_widgets[1].name_widget.cget('text'), '2.  Pending   [missing source]')
            with patch.object(app, 'configure_mod') as configure:
                app.mod_card_widgets[1].options_widget.invoke()
                configure.assert_called_once()
                self.assertEqual(app.selected_mod_index, 1)
        with patch.object(core, 'load_deployed', return_value={}):
            app.refresh_status()
            self.assertEqual(app.mod_card_widgets[0].preview_widget.cget('highlightbackground'), '#b42318')
        app.theme['accent'] = '#70b7ff'
        app.apply_theme()
        self.assertEqual(app.style.lookup('Options.TButton', 'background'), '#70b7ff')
        self.assertEqual(app.style.lookup('Options.TButton', 'background', ('active',)), '#000000')

    def test_release_controls_and_theme_refresh(self):
        app = self.app
        self.assertEqual(VERSION, '2.3.2')
        self.assertEqual(app.sidebar_footer.cget('text'), 'ALL IN ONE APP FOR HD2')
        for style in ('Yellow.TButton', 'Options.TButton', 'Accent.TButton', 'Library.Accent.TButton'):
            for state in (('active',), ('pressed', 'active')):
                self.assertEqual(app.style.lookup(style, 'background', state), '#000000')
            self.assertNotEqual(app.style.lookup(style, 'background', ('disabled', 'active')), '#000000')
        images = dict(app._checkbox_images)
        self.assertNotEqual(images['on'].get(8, 8), images['off'].get(8, 8))
        app.theme.update(accent='#70b7ff', panel='#11223a')
        app.apply_theme()
        self.assertEqual(images, app._checkbox_images)
        self.assertEqual(app._checkbox_images['on'].get(3, 3), (112, 183, 255))
        for style in ('TCheckbutton', 'Yellow.TCheckbutton'):
            self.assertIn('ModDiver.Check.indicator', str(app.style.layout(style)))
            self.assertEqual(app.style.lookup(style, 'foreground', ('disabled',)), app.theme['muted'])

    def test_log_colors_and_about_search(self):
        app=self.app
        app.log('Deployment complete: installed 2 file(s).');app.log('ERROR: Failed to write a file');app._drain()
        app.log('completely purged the mod library; game files and deployment backups were not changed')
        app.log('nothing deployed');app._drain()
        for widget in (app.log_text,app.deploy_log):
            self.assertIn('success',widget.tag_names('1.0'));self.assertIn('error',widget.tag_names('2.0'))
            self.assertIn('success',widget.tag_names('3.0'));self.assertIn('success',widget.tag_names('4.0'))
            self.assertNotEqual(widget.tag_cget('success','foreground'),widget.tag_cget('error','foreground'))
        app.about_query.set('Linux');app._find_about();self.assertTrue(app.about_text.tag_ranges('search'))
        self.assertIn('Version '+VERSION,app.about_text.get('1.0','end'))
        self.assertFalse(hasattr(app,'move_mod'));self.assertNotIn('Up',[b.cget('text') for b in app.mod_action_buttons])
        app.theme.update(bg='#ffffff',panel='#ffffff',text='#111111');app.apply_theme()
        self.assertEqual(app.log_text.tag_cget('error','foreground'),'#b5161c')

    def test_font_slider_does_not_reenter_theme_application(self):
        app = self.app
        app.cfg['mods'] = [{'name': 'Startup example', 'path': self.tmp.name,
                            'enabled': True, 'type': 'data', 'targets': []}]
        app.refresh_mods()
        with patch.object(app, 'apply_theme', wraps=app.apply_theme) as apply:
            app._set_theme(font=app.theme['font'])
            apply.assert_not_called()
            errors = []
            with patch.object(app, 'report_callback_exception', side_effect=lambda *args: errors.append(args)):
                app.font_scale.set(13)
                app.tk.call(app.font_scale.cget('command'), '13')
                app.update()
            self.assertEqual(errors, [])
            self.assertEqual(app.theme['font'], 13)
            self.assertEqual(apply.call_count, 1)
            self.assertEqual(len(app.mod_card_widgets), 1)

    def test_busy_cards_cannot_toggle_or_drag(self):
        app=self.app;app.cfg['mods']=[{'name':'Example','path':self.tmp.name,'enabled':True,'type':'data','targets':[]}]
        app.refresh_mods();app._set_buttons(False)
        app.selected_mod_index=0;app.toggle_mod()
        self.assertTrue(app.cfg['mods'][0]['enabled']);self.assertEqual(app.mod_toggle_widgets[0].cget('state'),'disabled')
        app._drag_mod_press(0,type('Event',(),{'y_root':20})());self.assertIsNone(getattr(app,'_mod_drag',None))
        app._set_buttons(True)

    def test_library_background_scroll_layout_and_profile_checkboxes(self):
        app = self.app
        app.cfg['mods'] = [{'name': f'Example {i}', 'path': self.tmp.name, 'enabled': True,
                            'type': 'data', 'targets': []} for i in range(12)]
        app.deiconify(); app.update(); app.refresh_mods(); app.update()
        self.assertTrue(app.mod_canvas.itemcget(app._library_bg_item, 'image'))
        self.assertLessEqual(app._library_bg.height(), app.mod_canvas.winfo_height())
        app.mod_canvas.yview_moveto(.5); app.update()
        _, y = app.mod_canvas.coords(app._library_bg_item)
        self.assertAlmostEqual(y, app.mod_canvas.canvasy(0)+app.mod_canvas.winfo_height()/2)
        self.assertGreater(app.mod_card_widgets[1].winfo_y(), app.mod_card_widgets[0].winfo_y())
        app._drop_marker = __import__('tkinter').Frame(app.mod_canvas, height=3)
        app.refresh_mods(); app.refresh_mods()
        for key in ('stratagem_bounce_removed', 'consistent_vaulting'):
            self.assertTrue(app.gameplay_vars[key].get())
            app.gameplay_vars[key].set(False); app._toggle_gameplay_profile(key)
            self.assertFalse(app.cfg[key])

    def test_asset_editor_can_open_sample_and_filter_resources(self):
        import asset_editor
        from asset_mods import Project
        from test_asset_mods import resource_archive
        editor = asset_editor.Editor(self.app)
        try:
            editor = editor.native
            editor.project = Project('example.zip', [resource_archive()])
            editor.populate(); self.assertEqual(len(editor.tree.get_children()), 1)
            editor.filter.set('Texture'); self.assertEqual(len(editor.tree.get_children()), 1)
            editor.filter.set('Sound'); self.assertEqual(len(editor.tree.get_children()), 0)
        finally:
            self.app._asset_workspace.destroy()

    def test_drag_reuses_cards_and_updates_button_indices(self):
        from types import SimpleNamespace
        app = self.app
        # Leave room for all cards below the embedded preset controls so this
        # test exercises reordering rather than edge-triggered auto-scroll.
        app.geometry('1180x1100+32000+32000')
        app.cfg['mods'] = [{'name': f'Mod {i}', 'path': self.tmp.name, 'enabled': True,
                            'type': 'data', 'category': 'visual' if i == 1 else 'gameplay',
                            'targets': []} for i in range(4)]
        app.deiconify(); app.update(); app.refresh_mods(); app.update()
        card = app.mod_card_widgets[0]
        target = app.mod_card_widgets[3]
        start = card.winfo_rooty() + 20
        end = target.winfo_rooty() + target.winfo_height() - 2
        app._drag_mod_press(0, SimpleNamespace(y_root=start))
        app._drag_y = end
        app._drag_tick()
        self.assertEqual(app.mod_canvas.type(app._drop_line), 'line')
        with patch.object(app, 'refresh_mods') as refresh:
            app._drag_mod_release(0, SimpleNamespace(y_root=end))
            refresh.assert_not_called()
        app.update()
        self.assertIs(app.mod_card_widgets[3], card)
        self.assertEqual(card.name_widget.cget('text'), '3.  Mod 0')
        with patch.object(app, 'configure_mod') as configure:
            card.options_widget.invoke()
            configure.assert_called_once()
            self.assertEqual(app.selected_mod_index, 3)
        self.assertEqual([m['name'] for m in app.cfg['mods']], ['Mod 2','Mod 1','Mod 3','Mod 0'])
        self.assertEqual(app.mod_canvas.itemcget(app._drop_line,'state'), 'hidden')
        app.mod_toggle_widgets[3].invoke()
        self.assertFalse(app.cfg['mods'][3]['enabled'])

    def test_disable_does_not_install_newly_enabled_mod(self):
        app=self.app;folder=Path(self.tmp.name)
        app.cfg['mods']=[{'name':name,'path':str(folder/name),'enabled':True,'type':'data','targets':[]} for name in ('Old','Kept','New')]
        deployed={'data/old.txt':{'mods':['Old'],'sources':[str(folder/'Old')]},'data/kept.txt':{'mods':['Kept'],'sources':[str(folder/'Kept')]}}
        calls=[]
        app.refresh_mods();app.selected_mod_index=0
        with patch.object(core,'load_deployed',side_effect=[deployed,{}]),patch('actions.purge'),patch('actions.install_all',side_effect=lambda cfg,log:calls.append(copy.deepcopy(cfg))),patch.object(app,'_task',side_effect=lambda work,done:work()):
            app.toggle_mod()
        self.assertEqual([m['name'] for m in calls[0]['mods']],['Kept'])
        self.assertTrue(app.cfg['mods'][2]['enabled'])

    def test_toggle_preserves_cards_canvas_windows_and_scroll(self):
        app = self.app
        app.cfg['mods'] = [{'name': f'Mod {i}', 'path': self.tmp.name,
                            'enabled': True, 'type': 'data', 'targets': []}
                           for i in range(12)]
        app.deiconify(); app.update(); app.refresh_mods(); app.update()
        app.mod_canvas.yview_moveto(.5); app.update()
        cards = dict(app.mod_card_widgets)
        buttons = dict(app.mod_toggle_widgets)
        windows = app.mod_canvas.find_withtag('mod_window')
        view = app.mod_canvas.yview()
        with patch.object(core, 'load_deployed', return_value={}), \
                patch.object(core, 'hellforge_root', return_value=None), \
                patch.object(app, 'refresh_mods') as refresh:
            for enabled in (False, True, False, True):
                buttons[5].invoke(); app.update()
                self.assertEqual(app.cfg['mods'][5]['enabled'], enabled)
                self.assertIn('ON' if enabled else 'OFF', buttons[5].cget('text'))
                self.assertEqual(buttons[5].cget('bg'), '#238636' if enabled else '#b42318')
                self.assertEqual(app.mod_card_widgets, cards)
                self.assertEqual(app.mod_toggle_widgets, buttons)
                self.assertEqual(app.mod_canvas.find_withtag('mod_window'), windows)
                self.assertEqual(app.mod_canvas.yview(), view)
            refresh.assert_not_called()

    def test_progress_and_restart_later_controls(self):
        app=self.app;app._show_update_progress('Downloading',1048576,2097152)
        self.assertEqual(float(app.update_progress['value']),50)
        with patch.object(app, '_ask_themed', return_value=False):
            app._update_install_finished({'version':'2.0.1'},['launcher.exe'],None)
        self.assertEqual(app._update_restart_command,['launcher.exe']);self.assertFalse(app.busy)

    def test_dropdown_popup_tracks_theme_changes(self):
        app = self.app
        box = app.language_box
        popup = app.tk.call('ttk::combobox::PopdownWindow', str(box)) + '.f.l'
        for panel, text, accent in [('#121a2e', '#e6ecff', '#4f8cff'), ('#ffffff', '#111111', '#c8102e')]:
            app.theme.update(panel=panel, text=text, accent=accent)
            app.apply_theme()
            self.assertEqual(app.tk.call(popup, 'cget', '-background'), panel)
            self.assertEqual(app.tk.call(popup, 'cget', '-foreground'), text)
            self.assertEqual(app.tk.call(popup, 'cget', '-selectbackground'), accent)
            self.assertEqual(app.style.lookup('TCombobox', 'fieldbackground', ('readonly',)), panel)

    def test_language_change_saves_and_restarts_with_close_checks(self):
        app = self.app
        app.cfg['language'] = 'en'
        app.language_choice.set(localization.LANGUAGES['zh-CN'])
        with patch.object(app, '_can_close', return_value=False), patch.object(app, '_restart_app') as restart:
            app._save_language()
            restart.assert_not_called()
            self.assertEqual(app.cfg['language'], 'en')
            self.assertEqual(app.language_choice.get(), 'English')
        app.language_choice.set(localization.LANGUAGES['zh-CN'])
        with patch.object(app, '_can_close', return_value=True), patch.object(app, '_close') as close:
            app._save_language()
            self.assertEqual(app.cfg['language'], 'zh-CN')
            core.save_config.assert_called_with(app.cfg)
            self.assertTrue(app._restart_command[-1].endswith('yao_forge.py'))
            close.assert_called_once_with(force=True)

    def test_about_credits_and_idle_progress(self):
        app = self.app
        self.assertEqual(list(app.nav_buttons)[-1], 'settings')
        self.assertEqual(app.update_progress.winfo_manager(), '')
        self.assertEqual(app.update_status.cget('text'), '')
        for language in localization.LANGUAGES:
            content = ''.join(text for text, _ in yao_forge.about_content.blocks(VERSION, language))
            self.assertIn('\n\n• KNOT - ModDiver Laboratory\n• Yao - ModDiver Laboratory and Merge Engine', content)

    def test_restart_releases_instance_lock_before_relaunch(self):
        from unittest.mock import MagicMock
        events = []
        lock = MagicMock()
        lock.acquire.return_value = True
        lock.release.side_effect = lambda: events.append('release')
        app = MagicMock()
        app._restart_command = ['launcher.exe']
        with patch.object(yao_forge.single_instance, 'InstanceLock', return_value=lock), patch.object(yao_forge, 'App', return_value=app), patch.object(yao_forge.subprocess, 'Popen', side_effect=lambda *a, **kw: events.append('launch')):
            yao_forge.main()
        self.assertEqual(events, ['release', 'launch'])



    def test_multiplayer_warning_and_settings_save(self):
        from unittest.mock import Mock
        from pathlib import Path
        app = self.app
        app.multiplayer_warnings.set(True)
        import moddiver_editor
        with patch.object(app, '_message_themed') as popup, patch.object(yao_forge.schema_editor, 'Editor') as native:
            app.open_native_editor()
            popup.assert_called_once_with('MULTIPLAYER WARNING',
                'Do not use stat editing mods in Helldivers 2 public multiplayer!\nsee about for more.')
            native.assert_called_once_with(app)
            popup.reset_mock()
            app.multiplayer_warnings.set(False)
            app.open_native_editor()
            popup.assert_not_called()
        app.multiplayer_warnings.set(True)
        exe = Path(self.tmp.name) / 'editor.exe'
        exe.write_bytes(b'test fixture')
        for launch, attribute, filename in ((app.open_editor, 'EDITOR', 'SHODAN Stat Editor Offline.exe'),
                                            (app.open_editor_ccm, 'EDITOR_CCM', 'Combined Community Mods.exe')):
            (Path(self.tmp.name) / filename).write_bytes(b'test fixture')
            events = []
            with patch.object(core, attribute, Path(self.tmp.name)), patch.object(app, '_message_themed', side_effect=lambda *a, **kw: events.append('warning')), patch.object(yao_forge.subprocess, 'Popen', side_effect=lambda *a, **kw: events.append('launch')), patch.object(moddiver_editor, 'launch', side_effect=lambda *a, **kw: events.append('launch')):
                launch()
            self.assertEqual(events, ['warning', 'launch'])
        app.theme['accent'] = '#63e6be'
        app.multiplayer_warnings.set(False)
        app.startup_updates.set(False)
        app.settings_save_button.invoke()
        saved = core.save_config.call_args.args[0]
        self.assertFalse(saved['show_multiplayer_warning'])
        self.assertFalse(saved['check_updates_on_start'])
        self.assertEqual(saved['theme']['accent'], '#63e6be')
        self.assertEqual(app.settings_save_button.master.grid_info()['row'], 0)
        self.assertEqual(app.multiplayer_warning_check.cget('style'), 'Yellow.TCheckbutton')

    def test_warning_dialog_theme_and_repair_colors(self):
        import tkinter as tk
        from tkinter import ttk
        app = self.app
        app.deiconify(); app.update()
        def accept():
            screen = app._choice_screen
            self.assertEqual(screen.cget('bg'), app.theme['bg'])
            labels = [child for child in screen.content.winfo_children() if isinstance(child, ttk.Label)]
            self.assertIn('Do not use stat editing mods', labels[1].cget('text'))
            self.assertFalse(any(isinstance(w, tk.Toplevel) for w in app.winfo_children()))
            screen.cancel_button.invoke()
        app.after(50, accept)
        app._multiplayer_warning()
        app.log('REPAIRED AND UPDATED SUCCESFULLY')
        app.log('FAILED TO REPAIR OR UPDATE')
        app._drain()
        self.assertTrue(app.log_text.tag_ranges('success'))
        self.assertTrue(app.log_text.tag_ranges('error'))
        self.assertEqual(app.log_text.tag_cget('success', 'foreground'), '#65df92')
        self.assertEqual(app.log_text.tag_cget('error', 'foreground'), '#ff7272')

if __name__=='__main__':unittest.main()



