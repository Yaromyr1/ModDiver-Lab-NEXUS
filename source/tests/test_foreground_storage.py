import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import core
import lab_storage
import yao_forge
import test_v2_ui


class ForegroundTests(unittest.TestCase):
    def setUp(self):
        import gc
        gc.collect()  # Dispose previous Tk roots on the UI thread before workers run.
        test_v2_ui.DesktopTests.setUp(self)

    def test_popup_above_fullscreen_and_nested_dialog(self):
        import tkinter as tk
        app = self.app
        app._end_loading('startup')
        app.deiconify()
        app._set_fullscreen(True)
        app.update()
        app._begin_loading('foreground')
        app.update()
        panel, bar = app._loading_windows[app]
        self.assertTrue(panel.popup.winfo_viewable())
        self.assertTrue(panel.popup.attributes('-topmost'))
        self.assertEqual(str(panel.popup.transient()), str(app))
        app._end_loading('foreground')
        dialog = tk.Toplevel(app)
        dialog.grab_set()
        app.update()
        self.assertTrue(dialog.attributes('-topmost'))
        app._begin_loading('nested')
        app.update()
        self.assertEqual(str(panel.popup.transient()), str(dialog))
        app._end_loading('nested')
        self.assertFalse(panel.popup.winfo_viewable())
        self.assertIsNone(bar.timer)
        dialog.destroy()
        app._set_fullscreen(False)

    def test_picker_checkboxes_click_keyboard_and_accept(self):
        app = self.app
        app.deiconify()
        records = [dict(name=f'Mod {i}', path=str(core.MODS_DIR/f'{i}.zip'),
                        selected={'Optional': False}) for i in range(3)]
        picker = lab_storage.StoragePicker(app, records)
        app.update()
        x, y, width, height = picker.tree.bbox('0')
        picker.click(SimpleNamespace(x=x+10, y=y+height//2))
        self.assertEqual(picker.checked, {'0'})
        picker.tree.focus('2')
        picker.toggle_focused()
        self.assertEqual(picker.checked, {'0', '2'})
        self.assertNotEqual(picker.tree.item('0', 'image'), picker.tree.item('1', 'image'))
        picker.select_all()
        self.assertEqual(len(picker.checked), 3)
        picker.set_checked(())
        self.assertIn('disabled', picker.add.state())
        picker.set_checked(('2', '0'))
        with patch.object(app, 'refresh_mods'), patch.object(app, 'refresh_status'):
            picker.accept()
        self.assertEqual([m['name'] for m in app.cfg['mods']], ['Mod 0', 'Mod 2'])
        self.assertFalse(app.cfg['mods'][0]['selected']['Optional'])
        self.assertIsNot(app.cfg['mods'][0], records[0])

    def test_stock_capture_keeps_ui_responsive(self):
        app = self.app
        worker_threads, ticks = [], []
        def capture(*args):
            worker_threads.append(threading.get_ident())
            time.sleep(.12)
            return 5
        with patch.object(core, 'capture_stock', side_effect=capture):
            app.capture_stock()
            self.assertTrue(app.busy)
            app.after(10, lambda: ticks.append(True))
            deadline = time.monotonic()+3
            while app.busy and time.monotonic()<deadline:
                app.update()
                time.sleep(.005)
        self.assertFalse(app.busy)
        self.assertTrue(ticks)
        self.assertNotEqual(worker_threads[0], threading.get_ident())


class StorageCacheTests(unittest.TestCase):
    def test_cache_reuses_summary_and_detects_nested_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            nested = path/'data'
            nested.mkdir()
            item = nested/'mod.patch_0'
            item.write_bytes(b'old')
            parsed = dict(path=str(path), name='Example', type='data', targets=['mod.patch_0'],
                          options=[dict(name='Part', default=False)])
            with patch.object(core, 'parse_mod', return_value=parsed) as parse:
                first = lab_storage.package_summary(path)
                first['selected']['Part'] = True
                self.assertFalse(lab_storage.package_summary(path)['selected']['Part'])
                self.assertEqual(parse.call_count, 1)
                item.write_bytes(b'changed')
                lab_storage.package_summary(path)
                self.assertEqual(parse.call_count, 2)
                item.unlink()
                lab_storage.package_summary(path)
                self.assertEqual(parse.call_count, 3)
