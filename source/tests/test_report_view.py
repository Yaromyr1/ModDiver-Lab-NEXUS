import tkinter as tk
import unittest
from unittest.mock import patch

from report_view import ReportView


class ReportViewTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.root.geometry('640x420')
        self.view = ReportView(self.root, wrap='word', font=('Consolas', 10))
        self.view.pack(fill='both', expand=True)

    def test_long_report_scrolls_over_fixed_watermark_and_keeps_tags(self):
        report = 'SUCCESS\n' + '\n'.join(f'Line {n}: '+('verified game data '*12) for n in range(150))
        self.view.insert('1.0', report)
        self.view.model.tag_add('success', '1.0', '1.end')
        self.view.tag_configure('success', foreground='#65df92')
        self.root.update()
        self.assertEqual(self.view.get('1.0', 'end-1c'), report)
        self.assertIn('success', self.view.tag_names('1.0'))
        self.assertLess(len(self.view.find_withtag('report-line')), 40)
        self.view.yview_moveto(.7)
        self.root.update()
        self.assertGreater(self.view.yview()[0], .5)
        x, y = self.view.coords(self.view._background_item)
        self.assertAlmostEqual(x, self.view.winfo_width()/2)
        self.assertAlmostEqual(y, self.view.canvasy(0)+self.view.winfo_height()/2)
        self.view.configure(bg='#fefefe', fg='#111111')
        self.root.update()
        self.assertEqual(self.view.cget('bg'), '#fefefe')
        self.assertEqual(self.view.get('1.0', 'end-1c'), report)

    def test_wrapped_report_can_be_selected_and_copied_without_losing_text(self):
        report = 'Selected report text across wrapped lines. '*40
        self.view.insert('1.0', report)
        self.view.configure(state='disabled')
        self.root.update()
        self.view._select_all()
        with patch.object(self.view, 'clipboard_clear'), patch.object(self.view, 'clipboard_append') as copy:
            self.view._copy()
            copy.assert_called_once_with(report)
        self.view.configure(state='normal')
        self.view.delete('1.0', 'end')
        self.view.insert('1.0', 'New report')
        self.root.update()
        self.assertEqual(self.view.get('1.0', 'end-1c'), 'New report')
        self.assertEqual(self.view._selection, (0, 0))
