import ctypes
from ctypes import wintypes
import os
import unittest
from unittest.mock import Mock, patch

import native_file_dialogs
import panel_dialogs


class NativeFileDialogTests(unittest.TestCase):
    def test_main_file_api_delegates_to_original_dialogs_with_options(self):
        self.assertIs(panel_dialogs.filedialog, native_file_dialogs.filedialog)
        owner = Mock()
        owner.grab_current.return_value = None
        parent = Mock()
        parent.winfo_toplevel.return_value = owner
        for method, result in (('askopenfilename', 'mod.zip'), ('askopenfilenames', ('a.zip', 'b.zip')),
                               ('askdirectory', 'game-folder'), ('asksaveasfilename', 'export.zip')):
            options = dict(title='Pick a package', initialdir='C:/Downloads', filetypes=[('ZIP', '*.zip')])
            with self.subTest(method=method), patch.object(native_file_dialogs.native, method, return_value=result) as dialog, \
                 patch.object(native_file_dialogs, 'CenterOnce') as center:
                self.assertEqual(getattr(panel_dialogs.filedialog, method)(parent=parent, **options), result)
                dialog.assert_called_once_with(parent=owner, **options)
                center.assert_called_once_with(owner)
                center.return_value.close.assert_called_once()

    def test_native_cancel_and_error_restore_panel_grab_and_remove_hook(self):
        owner, panel = Mock(), Mock()
        owner.winfo_toplevel.return_value = owner
        owner.grab_current.return_value = panel
        panel.winfo_exists.return_value = True
        for failed in (False, True):
            with patch.object(native_file_dialogs.native, 'askopenfilename', return_value='',
                              side_effect=OSError('dialog failed') if failed else None), \
                 patch.object(native_file_dialogs, 'CenterOnce') as center:
                if failed:
                    with self.assertRaises(OSError):
                        panel_dialogs.filedialog.askopenfilename(parent=owner)
                else:
                    self.assertEqual(panel_dialogs.filedialog.askopenfilename(parent=owner), '')
                center.return_value.close.assert_called_once()
        self.assertEqual(panel.grab_set.call_count, 2)

    def test_position_centers_over_owner_and_stays_inside_monitor(self):
        position = native_file_dialogs.center_position
        self.assertEqual(position((100, 100, 1300, 900), (800, 600), (0, 0, 1920, 1040)), (300, 200))
        self.assertEqual(position((-1700, 200, -500, 1000), (800, 600), (-1920, 0, 0, 1080)), (-1500, 300))
        self.assertEqual(position((1800, 900, 2200, 1300), (800, 600), (0, 0, 1920, 1040)), (1120, 440))

    @unittest.skipUnless(os.name == 'nt', 'Windows dialog activation hook')
    def test_activation_hook_centers_once_then_allows_user_moves(self):
        parent = Mock()
        parent.winfo_rootx.return_value = 100
        parent.winfo_rooty.return_value = 100
        parent.winfo_width.return_value = 1200
        parent.winfo_height.return_value = 800
        parent.winfo_screenwidth.return_value = 1920
        parent.winfo_screenheight.return_value = 1080
        parent.winfo_id.return_value = 0
        hook = native_file_dialogs.CenterOnce(parent)
        hook.close()
        user = Mock()
        def classname(handle, buffer, length):
            buffer.value = '#32770'
        def rect(handle, output):
            value = ctypes.cast(output, ctypes.POINTER(wintypes.RECT)).contents
            value.left, value.top, value.right, value.bottom = 10, 10, 810, 610
            return 1
        user.GetClassNameW.side_effect = classname
        user.GetWindowRect.side_effect = rect
        user.CallNextHookEx.return_value = 0
        hook.user = user
        hook.callback(5, 123, 0)
        user.SetWindowPos.assert_not_called()
        hook.timer_callback(None, 0, 1, 0)
        self.assertTrue(hook.centered)
        user.SetWindowPos.assert_called_once()
        initial = user.SetWindowPos.call_args
        self.assertEqual(initial.args[2:4], (300, 200))
        # Moving/resizing or reactivating the dialog never snaps it back.
        for event in (3, 4, 5, 5):
            hook.callback(event, 123, 0)
        user.SetWindowPos.assert_called_once()
