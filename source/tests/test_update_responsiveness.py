"""Exercise update actions with real Tk widgets and delayed worker I/O."""
import gc
import os
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import core
import test_v2_ui
import yao_forge


class UpdateResponsivenessTests(unittest.TestCase):
    def test_editor_actions_align_at_wide_layout_and_chef_import_stays_gray(self):
        app = self.app
        app.geometry('1900x1000+0+0')
        app._show('tools')
        app.update()
        cards = (app.moddiver_editor_card, app.shodan_editor_card)
        self.assertEqual(cards[0].grid_info()['row'], cards[1].grid_info()['row'])
        for row in (3, 4):
            actions = [card.grid_slaves(row=row)[0] for card in cards]
            self.assertEqual(actions[0].winfo_rooty(), actions[1].winfo_rooty())
        self.assertEqual(app.btn_import_chef.cget('style'), 'Action.Secondary.TButton')
        app.theme.update(accent='#55bbff')
        app.apply_theme()
        app.update()
        self.assertEqual(app.btn_import_chef.cget('style'), 'Action.Secondary.TButton')
        self.assertEqual(app.style.lookup(app.moddiver_editor_card.cget('style'), 'bordercolor'), '#ffd400')
        self.assertEqual(app.creator_audio_card.cget('highlightthickness'), 1)
        self.assertEqual(app.creator_audio_card.cget('highlightbackground'), '#ffd400')
        self.assertFalse(hasattr(app, 'creator_moddiver_card'))
        self.assertFalse(hasattr(app, 'creator_shodan_card'))
        self.assertEqual(int(app.creator_audio_card.grid_info()['row']), 1)
        self.assertEqual(int(app.creator_native_card.grid_info()['row']), 2)

    def test_editor_launch_prepares_off_ui_thread_and_recovers_from_failure(self):
        import moddiver_editor
        entered, release = threading.Event(), threading.Event()
        process = object()
        def launch(**kwargs):
            self.assertNotEqual(threading.get_ident(), self.ui_thread)
            kwargs['progress']('Validating editor data', 1, 2)
            entered.set()
            release.wait(2)
            return process
        with patch.object(self.app, '_multiplayer_warning'), patch.object(moddiver_editor, 'launch', side_effect=launch):
            self.app.open_editor_ccm()
            self.wait(entered.is_set)
            self.assertTrue(self.app.busy)
            beat = []
            self.app.after(0, lambda: beat.append(True))
            self.app.update()
            self.assertTrue(beat)
            release.set()
            self.wait(lambda: not self.app.busy)
            self.assertIs(self.app.editor_proc, process)
        self.app.editor_proc = None
        with patch.object(self.app, '_multiplayer_warning'), patch.object(moddiver_editor, 'launch', side_effect=ValueError('bad stock')), patch.object(self.app, '_message_themed') as notice:
            self.app.open_editor_ccm()
            self.wait(lambda: not self.app.busy)
            notice.assert_called_once_with('ModDiverEditor', 'bad stock')

    def setUp(self):
        gc.collect()
        test_v2_ui.DesktopTests.setUp(self)
        self.app._end_loading('startup')
        self.app.deiconify()
        self.app.update()
        self.ui_thread = threading.get_ident()
        self.callbacks = []
        self.app.report_callback_exception = lambda *args: self.callbacks.append(args)
        original = self.app.after

        def ui_after(*args, **kwargs):
            self.assertEqual(threading.get_ident(), self.ui_thread, 'worker called Tk.after')
            return original(*args, **kwargs)
        self.after_patch = patch.object(self.app, 'after', side_effect=ui_after)
        self.after_patch.start()
        self.addCleanup(self.after_patch.stop)

    def wait(self, condition):
        deadline = time.monotonic() + 3
        while not condition() and time.monotonic() < deadline:
            self.app.update()
            time.sleep(.005)
        self.app.update()
        self.assertEqual(self.callbacks, [])
        self.assertTrue(condition(), 'update did not finish')

    def panel(self):
        return getattr(self.app, '_confirmation_panel', None)

    def close_notice(self):
        panel = self.panel()
        self.assertIsNotNone(panel)
        self.assertTrue(panel.winfo_viewable())
        self.assertIs(self.app.grab_current(), panel)
        beat = []
        self.app.after(0, lambda: beat.append(True))
        self.app.update()
        self.assertTrue(beat)
        panel.cancel_button.invoke()
        self.assertIsNone(self.app.grab_current())

    def test_preview_checks_update_silently_and_defers_prompt_until_preview_finishes(self):
        app = self.app
        releases = [None, {'version': '99.0.0'}]
        for release in releases:
            with patch.object(yao_forge.updater, 'find_update', return_value=release) as find, \
                 patch.object(app, '_task', side_effect=lambda work, done: setattr(app, 'busy', True)), \
                 patch.object(app, '_update_prompt') as prompt, \
                 patch.object(app, '_update_notice') as notice:
                app.busy = False
                app.install_all(dry_run=True)
                self.wait(lambda: find.called)
                for _ in range(12):
                    app.update()
                    time.sleep(.01)
                prompt.assert_not_called()
                notice.assert_not_called()
                app.busy = False
                self.wait(lambda: not app._update_check_active)
                self.assertEqual(prompt.call_count, int(release is not None))
                notice.assert_not_called()

    def test_tool_checks_success_current_failure_and_decline_without_native_modals(self):
        app = self.app
        for button, service, current in ((app.btn_check_chef, yao_forge.chef_updater, '_current_chef_version'),
                                         (app.btn_check_shodan, yao_forge.shodan_updater, '_current_shodan_version')):
            for outcome in ('new', 'current', 'timeout'):
                with self.subTest(button=button.cget('text'), outcome=outcome):
                    beats, workers = [], []
                    def release():
                        workers.append(threading.get_ident())
                        time.sleep(.08)
                        if outcome == 'timeout':
                            raise TimeoutError('test network timeout')
                        return {'version': '9.0.0'}
                    with patch.object(service, 'latest_release', side_effect=release), \
                         patch.object(app, current, return_value=(9, 0, 0) if outcome == 'current' else ()), \
                         patch.object(app, 'wait_window', side_effect=AssertionError('native modal wait')), \
                         patch.object(app, '_download_chef_release') as chef, \
                         patch.object(app, '_download_shodan_release') as shodan:
                        button.invoke()
                        self.assertTrue(app.busy)
                        self.assertFalse(hasattr(app, 'btn_import_ccm'))
                        self.assertIn('disabled', app.btn_check_update.state())
                        app.after(0, lambda: beats.append(True))
                        self.wait(lambda: self.panel() is not None)
                        self.assertTrue(beats)
                        self.assertNotEqual(workers[0], self.ui_thread)
                        self.assertFalse(app.busy)
                        self.assertNotIn('disabled', button.state())
                        self.assertEqual(app._loading_windows[app][0].winfo_manager(), '')
                        self.close_notice()
                        chef.assert_not_called()
                        shodan.assert_not_called()

    def test_accept_loader_update_destroys_prompt_before_download(self):
        app = self.app
        with patch.object(yao_forge.chef_updater, 'latest_release', return_value={'version': '99.0.0'}), \
             patch.object(app, '_download_chef_release') as download:
            app.btn_check_chef.invoke()
            self.wait(lambda: self.panel() is not None)
            self.panel().confirm_button.invoke()
            download.assert_called_once_with({'version': '99.0.0'})
            self.assertIsNone(self.panel())
            self.assertIsNone(app.grab_current())

    def test_fullscreen_failure_prompt_is_inside_app_and_retry_works(self):
        app = self.app
        app._set_fullscreen(True)
        app.update()
        with patch.object(yao_forge.chef_updater, 'latest_release', side_effect=OSError('offline')):
            for _ in range(2):
                app.btn_check_chef.invoke()
                self.wait(lambda: self.panel() is not None)
                self.assertIs(self.panel().master, app)
                self.close_notice()
        app._set_fullscreen(False)

    def test_download_setup_failure_restores_both_tool_buttons(self):
        app = self.app
        for download in (app._download_chef_release, app._download_shodan_release):
            with patch.object(yao_forge.tempfile, 'mkstemp', side_effect=OSError('disk full')):
                download({'version': '9.0.0'})
                self.wait(lambda: self.panel() is not None)
                self.assertFalse(app.busy)
                self.assertNotIn('disabled', app.btn_check_chef.state())
                self.close_notice()

    def test_failed_downloads_and_validation_clean_temporary_files(self):
        app = self.app
        for service, download in ((yao_forge.chef_updater, app._download_chef_release),
                                   (yao_forge.shodan_updater, app._download_shodan_release)):
            for failure in ('network', 'package'):
                with self.subTest(service=service.__name__, failure=failure), \
                     patch.object(core, 'APP_DATA', Path(self.tmp.name)), \
                     patch.object(service, 'download_release', side_effect=OSError('download failed') if failure == 'network' else None), \
                     patch.object(core, 'parse_mod', side_effect=ValueError('invalid loader')), \
                     patch.object(core, 'import_editor', side_effect=ValueError('invalid editor')):
                    download({'version': '9.0.0'})
                    self.wait(lambda: self.panel() is not None)
                    self.assertFalse(list(Path(self.tmp.name).glob('tool-update-*.zip')))
                    self.close_notice()

    def test_loader_download_imports_then_notifies_and_preserves_original(self):
        app = self.app
        data = Path(self.tmp.name)
        managed = data/'mods/imported/chef-loader.zip'
        old = {'name': 'Chef Shared Loader 1.0.0', 'path': str(data/'old.zip'), 'enabled': True,
               'type': 'data', 'targets': []}
        app.cfg['mods'] = [old]
        package = dict(name='Chef Shared Loader 9.0.0', type='data', targets=['test.patch_0'], options=[])
        def parse(path):
            return dict(package, path=str(path))
        def add(path):
            managed.write_bytes(Path(path).read_bytes())
            return managed
        with patch.object(core, 'APP_DATA', data), patch.object(core, 'parse_mod', side_effect=parse), \
             patch.object(core, 'MODS_DIR', data/'mods'), \
             patch.object(yao_forge.chef_updater, 'download_release', side_effect=lambda release, path: path.write_bytes(b'loader')):
            app._download_chef_release({'version': '9.0.0'})
            self.wait(lambda: self.panel() is not None)
            self.assertNotIn(old, app.cfg['mods'])
            self.assertEqual(len(app.cfg['mods']), 1)
            self.assertEqual(app.cfg['mods'][0]['name'], package['name'])
            self.assertTrue(app.cfg['mods'][0]['enabled'])
            self.assertTrue(managed.is_file())
            self.assertFalse(list(data.glob('tool-update-*.zip')))
            self.close_notice()

    def test_shodan_install_and_manual_ccm_import_finish_on_ui_thread(self):
        app = self.app
        with patch.object(core, 'APP_DATA', Path(self.tmp.name)), \
             patch.object(yao_forge.shodan_updater, 'download_release'), \
             patch.object(core, 'import_editor', return_value=('shodan', Path(self.tmp.name))), \
             patch.object(app, '_current_shodan_version', return_value=(9, 0, 0)):
            app._download_shodan_release({'version': '9.0.0'})
            self.wait(lambda: self.panel() is not None)
            self.close_notice()
        for failed in (False, True):
            with patch.object(app, '_choose_import_source', return_value='manual.zip'), \
                 patch.object(core, 'import_editor', return_value=('ccm', Path(self.tmp.name)),
                              side_effect=ValueError('invalid CCM') if failed else None):
                app.import_ccm_editor()
                self.wait(lambda: self.panel() is not None)
                self.assertFalse(app.busy)
                self.close_notice()

    def test_manual_loader_failure_reports_and_releases_controls(self):
        app = self.app
        with patch.object(app, '_choose_import_source', return_value='bad.zip'), \
             patch.object(core, 'parse_mod', side_effect=ValueError('invalid loader')):
            app.btn_import_chef.invoke()
            self.wait(lambda: self.panel() is not None)
            self.assertFalse(app.busy)
            self.close_notice()

    def test_app_checks_current_new_and_network_failure(self):
        app = self.app
        for result in (None, {'version': '99.0.0'}, OSError('offline')):
            with patch.object(yao_forge.updater, 'find_update', return_value=None if isinstance(result, Exception) else result,
                              side_effect=result if isinstance(result, Exception) else None), \
                 patch.object(app, 'wait_window', side_effect=AssertionError('native modal')):
                app.btn_check_update.invoke()
                self.wait(lambda: self.panel() is not None)
                self.assertFalse(app._update_check_active)
                self.close_notice()

    def test_app_install_success_and_failure_and_restart_later(self):
        app = self.app
        for failed in (False, True):
            with patch.dict(os.environ, {'YAO_FORGE_EXE': 'launcher.exe', 'YAO_FORGE_DATA': self.tmp.name}), \
                 patch.object(yao_forge.updater, 'install_update', side_effect=OSError('bad checksum') if failed else None) as install, \
                 patch.object(app, '_restart_updated_app') as restart:
                app._download_update({'version': '99.0.0'})
                self.wait(lambda: self.panel() is not None)
                install.assert_called_once()
                self.assertFalse(app._update_install_active)
                self.assertFalse(app.busy)
                self.close_notice()
                restart.assert_not_called()

    def test_thread_start_failure_is_reported_and_retry_enabled(self):
        with patch.object(yao_forge.threading.Thread, 'start', side_effect=RuntimeError('cannot start thread')):
            self.app.btn_check_chef.invoke()
            self.assertFalse(self.app.busy)
            self.app.update()
            self.close_notice()

    def test_unmeasured_check_progress_keeps_loading_animation_running(self):
        app = self.app
        app._set_buttons(False)
        app.report_progress('Checking Chef Shared Loader for updates', 0, 0)
        app._drain()
        bar = app._loading_windows[app][1]
        self.assertIsNotNone(bar.timer)
        self.assertIsNone(bar['value'])
        self.assertIn('Chef', bar.caption)
        app._set_buttons(True)

    def test_startup_check_waits_for_active_operation(self):
        app = self.app
        app._set_buttons(False)
        with patch.object(app, '_background_update') as background, patch.object(app, 'after') as later:
            app._check_for_updates(manual=False)
            background.assert_not_called()
            delay, retry = later.call_args.args
            self.assertEqual(delay, 500)
            app._set_buttons(True)
            retry()
            background.assert_called_once()

    def test_app_check_result_waits_for_existing_prompt(self):
        app = self.app
        app._update_notice('Existing prompt', 'Review this first')
        original = self.panel()
        app._update_check_active = True
        with patch.object(app, 'after') as later:
            app._update_check_finished(False, {'version': '99.0.0'}, None)
            self.assertIs(self.panel(), original)
            retry = later.call_args.args[1]
            original.cancel_button.invoke()
            retry()
            self.assertFalse(app._update_check_active)
            self.assertIsNotNone(self.panel())
            self.panel().cancel_button.invoke()
