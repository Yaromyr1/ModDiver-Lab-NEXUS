import tkinter as tk
import unittest
import core
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from decoder_ui import Decoder


class RepairUITests(unittest.TestCase):
    def test_modes_and_close_guards(self):
        root = tk.Tk()
        root.withdraw()
        try:
            decoder = Decoder(root, SimpleNamespace(texts=[]))
            decoder.pack(fill='both', expand=True)
            root.update_idletasks()
            tabs = decoder.winfo_children()[0]
            self.assertEqual(len(tabs.tabs()), 2)
            self.assertEqual(tabs.tab(0, 'text'), 'Update Repair')
            self.assertEqual(tabs.select(), str(decoder.repair))
            self.assertEqual(decoder.repair.analyse_button.cget('text'), 'Import zip/file mod')
            self.assertEqual(decoder.repair.folder_button.cget('text'), 'Import mod folder')
            self.assertEqual(decoder.repair.reference_button.cget('text'), 'INSPECT REPAIRED REFERENCE')
            self.assertEqual(decoder.repair.baseline_button.cget('text'), 'IMPORT OLD DATA BASELINE')
            self.assertEqual(decoder.repair.reference_button.master, decoder.repair.baseline_button.master)
            self.assertEqual(decoder.repair.reference_button.master.grid_info()['row'], 4)
            with patch('repair_ui.filedialog.askopenfilename', return_value='mod.zip') as file_picker, patch('repair_ui.filedialog.askdirectory', return_value='mod-folder') as folder_picker, patch.object(decoder.repair, 'repair') as repair:
                decoder.repair.analyse_button.invoke()
                repair.assert_called_with('mod.zip')
                file_picker.assert_called_once()
                folder_picker.assert_not_called()
                decoder.repair.folder_button.invoke()
                repair.assert_called_with('mod-folder')
                folder_picker.assert_called_once()
            self.assertIsNone(decoder.current)
            self.assertFalse(decoder.busy)
            decoder.repair.busy = True
            self.assertTrue(decoder.busy)
            decoder.repair.busy = False
            decoder.payload.busy = True
            self.assertTrue(decoder.busy)
            decoder.payload.busy = False
            self.assertFalse(any(isinstance(child, __import__('tkinter').ttk.Notebook)
                                 for child in decoder.repair.winfo_children()))
            self.assertEqual(decoder.repair.analyse_button.cget('style'), 'Accent.TButton')
            self.assertEqual(decoder.repair.export_button.cget('style'), 'Install.TButton')
            self.assertIn('disabled', decoder.repair.export_button.state())
        finally:
            root.destroy()



    def test_repair_outcomes_and_export(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = SimpleNamespace(texts=[], log=Mock())
            repair = Decoder(root, app).repair
            # Run the worker synchronously, then process its queued Tk completion.
            def immediate_thread(target, **kwargs):
                return SimpleNamespace(start=target)
            from contextlib import nullcontext
            with TemporaryDirectory() as tmp, patch('repair_ui.threading.Thread', side_effect=immediate_thread), patch.object(repair, 'game', return_value=tmp), patch('core.stock_file_count', return_value=core.REQUIRED_STOCK_FILES), patch('core.load_deployed', return_value={}), patch('build_archive.baseline_session', return_value=nullcontext(Path(tmp))), patch('build_archive.capture'), patch('build_archive.repair') as worker:
                output = Path(tmp) / 'repaired'
                output.mkdir()
                (output / 'mod.patch_0').write_bytes(b'verified mod')
                worker.return_value = output, ['Verified output']
                repair.repair('broken.zip')
                root.update()
                self.assertEqual(repair.status.cget('text'), 'REPAIRED AND UPDATED SUCCESFULLY')
                self.assertIn('success', repair.report.tag_names('1.0'))
                app.log.assert_called_with('REPAIRED AND UPDATED SUCCESFULLY')
                self.assertNotIn('disabled', repair.export_button.state())
                with patch('repair_ui.filedialog.asksaveasfilename', return_value=str(Path(tmp) / 'portable.zip')):
                    repair.export()
                import zipfile
                with zipfile.ZipFile(Path(tmp) / 'portable.zip') as package:
                    self.assertIn('mod.patch_0', package.namelist())
                repair.clear_button.invoke()
                self.assertEqual(repair.report.get('1.0', 'end').strip(), '')
                with patch('build_archive.purge_repaired') as purge:
                    repair.purge_button.invoke()
                    root.update()
                    purge.assert_called_once()
                self.assertIsNone(repair.repaired_folder)
                self.assertIn('disabled', repair.export_button.state())
                self.assertEqual(repair.purge_button.cget('style'), 'Danger.TButton')
                self.assertEqual(repair.clear_button.cget('style'), 'Shortcut.TButton')
                worker.side_effect = ValueError('No matching archived build')
                repair.repair('broken.zip')
                root.update()
                self.assertEqual(repair.status.cget('text'), 'FAILED TO REPAIR OR UPDATE')
                self.assertIn('No matching archived build', repair.report.get('1.0', 'end'))
                self.assertIn('error', repair.report.tag_names('1.0'))
                app.log.assert_called_with("DATA BOT CAN NOT UPDATE/REPAIR THIS MOD BECAUSE IT IS EITHER INCOMPATIBLE OR THE BOT DOESN'T HAVE THE DATA IT NEEDS", 'error')
                self.assertIn('disabled', repair.export_button.state())
                self.assertIsNone(repair.repaired_folder)
        finally:
            root.destroy()

if __name__ == '__main__':
    unittest.main()
