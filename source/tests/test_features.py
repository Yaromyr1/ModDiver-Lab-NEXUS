import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import core
import localization
import single_instance
import yao_forge
import tkinter as tk
from tkinter import ttk
import choice_screen


class InstanceTests(unittest.TestCase):
    def test_duplicate_process_is_blocked_and_crash_releases_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            script = (f'import sys; sys.path.insert(0, {str(Path(core.__file__).parent)!r}); '
                      'from single_instance import InstanceLock; '
                      'lock=InstanceLock(sys.argv[1]); assert lock.acquire(); '
                      'print("locked",flush=True); sys.stdin.readline()')
            child = subprocess.Popen([sys.executable, '-u', '-c', script, folder], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'locked')
                other = single_instance.InstanceLock(folder)
                self.assertEqual(other.owner_pid(), child.pid)
                with patch.object(other, 'activate_existing') as activate:
                    self.assertFalse(other.acquire()); activate.assert_called_once()
            finally:
                child.terminate(); child.communicate(timeout=5)
            self.assertTrue(other.acquire())
            other.release()

    def test_duplicate_main_does_not_construct_app(self):
        with patch('yao_forge.single_instance.InstanceLock') as lock, patch('yao_forge.App') as app:
            lock.return_value.acquire.return_value = False
            yao_forge.main()
            app.assert_not_called()


class FeatureUITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.cfg = {'game': self.tmp.name, 'mods': [], 'nomofomo': False,
                    'theme': dict(core.DEFAULT_THEME), 'check_updates_on_start': False}
        for target, value in [('load_config', self.cfg), ('save_config', None)]:
            mock = patch.object(core, target, return_value=value)
            mock.start(); self.addCleanup(mock.stop)
        self.addCleanup(localization.set_language, 'en')

    def app(self):
        app = yao_forge.App(); app.withdraw(); self.addCleanup(app.destroy)
        for token in app.tk.call('after', 'info'): app.after_cancel(token)
        return app

    def test_settings_replaces_theme_tab_and_saves_language(self):
        app = self.app()
        self.assertIn('settings', app.pages); self.assertNotIn('themes', app.pages)
        self.assertTrue(app.nav_buttons['settings'].cget('image'))
        self.assertEqual(app.nav_buttons['settings'].cget('text').strip(), 'SETTINGS')
        self.assertIsNotNone(app.font_scale)
        app.language_choice.set('简体中文')
        with patch.object(app, '_restart_app') as restart:
            app._save_language()
            restart.assert_called_once_with(checked=True)
        self.assertEqual(self.cfg['language'], 'zh-CN')
        core.save_config.assert_called_with(self.cfg)

    def test_chinese_startup_has_translated_ui_and_guide(self):
        self.cfg['language'] = 'zh-CN'
        app = self.app()
        self.assertEqual(app.btn_get_mods.cget('text'), '获取模组')
        self.assertTrue(app.nav_buttons['settings'].cget('image'))
        self.assertEqual(app.nav_buttons['settings'].cget('text').strip(), '设置')
        self.assertIn('Linux 安装', app.about_text.get('1.0', 'end'))
        app.about_query.set('快捷方式'); app._find_about()
        self.assertTrue(app.about_text.tag_ranges('search'))
        app._show('settings'); self.assertEqual(app.title_label.cget('text'), '设置')

    def test_default_previews_share_one_image_and_removed_mods_release_cache(self):
        app = self.app()
        paths = [str(Path(self.tmp.name) / f'missing-{i}.zip') for i in range(30)]
        images = [app._mod_preview({'path': path}) for path in paths]
        self.assertIsNotNone(images[0])
        self.assertTrue(all(image is images[0] for image in images))
        self.assertLessEqual(max(images[0].width(), images[0].height()), 88)
        self.cfg['mods'] = [{'name': 'Retained', 'path': paths[0], 'enabled': False,
                             'type': 'data', 'targets': []}]
        app.refresh_mods()
        self.assertEqual(set(app._mod_preview_cache), {paths[0]})
        self.assertIs(app._mod_preview_cache[paths[0]], images[0])

    def test_get_mods_colors_urls_and_browser_failure(self):
        app = self.app(); dialog = app.get_mods()
        colors = ['#d66a12', '#008b8b', '#c62828']
        urls = ['https://www.nexusmods.com/games/helldivers2', 'https://ayakamods.com/?game_id=119', 'https://hf-mod.com/']
        for button, color, url in zip(app.mod_site_buttons, colors, urls):
            self.assertEqual(button.cget('bg'), color); self.assertEqual(button.cget('fg'), 'white')
            with patch('yao_forge.webbrowser.open', return_value=True) as browser:
                button.invoke(); browser.assert_called_once_with(url)
        with patch('yao_forge.webbrowser.open', return_value=False), patch('yao_forge.messagebox.showerror') as error:
            app.mod_site_buttons[0].invoke()
            self.assertIn('browser', dialog.error.get())
            error.assert_not_called()
        dialog.destroy()

    def test_startup_checks_even_after_a_recent_check(self):
        app = self.app(); app.cfg.update(check_updates_on_start=True, update_check_timestamp=time.time())
        with patch.object(app, '_check_for_updates') as check:
            app._automatic_update_check(); check.assert_called_once_with(manual=False)
            check.reset_mock(); app.cfg['check_updates_on_start'] = False
            app._automatic_update_check(); check.assert_not_called()

    def test_idle_app_can_close_despite_tk_busy_method(self):
        app = self.app()
        with patch('yao_forge.messagebox.showinfo') as warning:
            self.assertTrue(app._can_close()); warning.assert_not_called()
            app.pages['editor'].repair.busy = True
            self.assertFalse(app._can_close()); warning.assert_called_once()

    def test_manual_builtin_updates_work_with_app_update_checks_off_and_never_retry(self):
        app = self.app()
        app.cfg['check_updates_on_start'] = False
        with patch('yao_forge.messagebox.askyesno', return_value=True), \
             patch.object(app, '_prefetch_repair_data') as prefetch, \
             patch('yao_forge.core.steam_verify') as verify, \
             patch('builtin_updater.run_worker', return_value={}) as update, patch.object(app, '_task') as task:
            app.update_builtin_mods()
            verify.assert_called_once()
            prefetch.assert_called_once()
            self.assertTrue(app._stock_verify_started)
            app._stock_verify_started = False
            app._builtin_repair_verify_confirmed = True
            app.update_builtin_mods()
            task.call_args.args[0]()
            update.assert_called_once()
        app.busy = True
        with patch.object(app, 'after') as later, patch.object(app, '_task') as task:
            app.update_builtin_mods()
            later.assert_not_called()
            task.assert_not_called()

    def test_started_steam_verify_is_handled_automatically(self):
        app = self.app()
        app._stock_verify_started = True
        with patch.object(app, '_capture_stock_then') as capture, \
             patch.object(app, '_task') as task:
            app.update_builtin_mods()
            capture.assert_not_called()
            task.assert_not_called()

    def test_steam_verify_monitor_uses_content_log_phases_and_frontmost_window(self):
        app = self.app()
        app.cfg['game'] = self.tmp.name
        log_path = Path(self.tmp.name) / 'content_log.txt'
        log_path.write_text('', encoding='utf-8')
        with patch('yao_forge.core.steam_content_log', return_value=log_path), \
             patch('yao_forge.core.steam_verify'), \
             patch.object(app, '_prefetch_repair_data'), \
             patch.object(app, 'after') as after:
            app._begin_steam_verification()
            self.assertTrue(app._stock_verify_started)
            self.assertTrue(app.attributes('-topmost'))
            with log_path.open('a', encoding='utf-8') as stream:
                stream.write('[time] AppID 553850 App update changed : Running Update,Verifying Installed,\n')
            app._poll_steam_verification()
            self.assertEqual(app._steam_verify_phase, 'verifying installed files')
            self.assertTrue(after.called)

    def test_stock_capture_refreshes_counter_and_handles_steam_launch_failure(self):
        app = self.app()
        app._show('log')
        with patch('yao_forge.messagebox.askyesno', return_value=True), \
             patch('yao_forge.core.steam_content_log', return_value=None), \
             patch('yao_forge.core.steam_verify', side_effect=OSError('Steam could not start')), \
             patch('yao_forge.messagebox.showerror') as showerror:
            app._combined_stock_action(app.btn_capture, app.stock_action_status)
            showerror.assert_called_once()
            self.assertFalse(app._stock_verify_started)
            self.assertIsNone(app._steam_verify_continuation)
            showerror.assert_called_once()

        screen = choice_screen.ChoiceScreen(app, size=(640, 400))
        status = tk.Label(screen.card, text='')
        status.pack()
        verify = ttk.Button(screen.card, text='verify')
        verify.pack()
        screen.activate(verify)
        with patch('yao_forge.messagebox.askyesno', return_value=True), \
             patch('yao_forge.core.steam_content_log', return_value=None), \
             patch('yao_forge.core.steam_verify'), \
             patch.object(app, '_prefetch_repair_data'), \
             patch.object(app, '_poll_steam_verification'), \
             patch.object(app, 'log'):
            app._combined_stock_action(verify, status, screen=screen)
        self.assertFalse(screen.winfo_exists())
        self.assertTrue(app._stock_verify_started)
        self.assertTrue(app.attributes('-topmost'))
        app.attributes('-topmost', False)

        app._task_error = None
        app._task_result = core.REQUIRED_STOCK_FILES
        app.cfg['game'] = self.tmp.name
        with patch('build_archive.capture_stock_folder'), \
             patch.object(app, 'refresh_status') as refresh, \
             patch.object(app, '_task', side_effect=lambda fn, done: done()):
            app._capture_stock_then(lambda: None)
        self.assertGreaterEqual(refresh.call_count, 1)

    def test_about_warning_is_exact_red_and_above_start_here(self):
        import about_content
        app = self.app()
        text = app.about_text.get('1.0', 'end')
        self.assertIn(about_content.MULTIPLAYER_WARNING, text)
        self.assertLess(text.index(about_content.MULTIPLAYER_WARNING), text.index('START HERE'))
        self.assertEqual(app.about_text.tag_cget('warning', 'foreground'), '#ff3333')
        app.apply_preset('Light')
        self.assertEqual(app.about_text.tag_cget('warning', 'foreground'), '#ff3333')

    @unittest.skipUnless(os.name == 'nt', 'Windows shortcut command')
    def test_manual_shortcut_bypasses_first_run_flag_and_escapes_path(self):
        app = self.app(); app.cfg['shortcut_v2'] = True
        exe = Path(self.tmp.name) / "Yao's app.exe"; exe.touch()
        with patch.dict(os.environ, {'YAO_FORGE_EXE': str(exe)}), patch('yao_forge.subprocess.run') as run, patch('yao_forge.messagebox.showinfo'):
            app.generate_shortcut()
            self.assertIn("Yao''s app.exe", run.call_args.args[0][-1])
            self.assertTrue(run.call_args.kwargs['check'])
            self.assertIn('moddiver_badge_hex.ico', run.call_args.args[0][-1])
            self.assertEqual(app.cfg['shortcut_brand'], 'hex-v1')

    def test_manual_linux_shortcut_keeps_paths_with_spaces(self):
        app = self.app(); root = Path(self.tmp.name)
        bootstrap = root / 'source with spaces' / 'linux_launcher.py'; bootstrap.parent.mkdir(); bootstrap.touch()
        data = root / 'data'; data.mkdir()
        with patch.dict(os.environ, {'YAO_FORGE_BOOTSTRAP': str(bootstrap)}), patch('yao_forge.shutil.which', return_value=None), patch('yao_forge.Path.home', return_value=root), patch.object(core, 'APP_DATA', data), patch('yao_forge.messagebox.showinfo'):
            app._linux_shortcut()
        entry = (root / 'Desktop/ModDiver Laboratory.desktop').read_text(encoding='utf-8')
        self.assertIn('Name=ModDiver Lab', entry)
        self.assertIn('"' + str(bootstrap.resolve()).replace('\\', '\\\\') + '"', entry)
        self.assertTrue((data / 'moddiver_badge_hex.png').is_file())
