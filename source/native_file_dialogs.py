"""Original OS file dialogs, centered once when they open on Windows."""
import ctypes
from ctypes import wintypes
import os
from tkinter import filedialog as native


def center_position(owner, dialog, work):
    left, top, right, bottom = owner
    width, height = dialog
    x, y = left + (right-left-width)//2, top + (bottom-top-height)//2
    return (max(work[0], min(x, work[2]-width)),
            max(work[1], min(y, work[3]-height)))


class CenterOnce:
    def __init__(self, parent):
        self.hook = None
        self.timer = None
        if os.name != 'nt':
            return
        parent.update_idletasks()
        self.owner = (parent.winfo_rootx(), parent.winfo_rooty(),
                      parent.winfo_rootx()+parent.winfo_width(), parent.winfo_rooty()+parent.winfo_height())
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentThreadId.restype = wintypes.DWORD
        self.user.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
        self.user.SetWindowsHookExW.restype = wintypes.HANDLE
        self.user.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        self.user.CallNextHookEx.restype = ctypes.c_ssize_t
        self.user.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        self.user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                          ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self.user.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        self.user.MonitorFromWindow.restype = wintypes.HANDLE

        class MonitorInfo(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT),
                        ('work', wintypes.RECT), ('flags', wintypes.DWORD)]

        self.user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        self.user.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
        self.user.SetTimer.restype = ctypes.c_size_t
        self.user.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
        work = (0, 0, parent.winfo_screenwidth(), parent.winfo_screenheight())
        info = MonitorInfo(size=ctypes.sizeof(MonitorInfo))
        monitor = self.user.MonitorFromWindow(parent.winfo_id(), 2)
        if self.user.GetMonitorInfoW(monitor, ctypes.byref(info)):
            work = (info.work.left, info.work.top, info.work.right, info.work.bottom)
        self.work = work
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        timer_type = ctypes.WINFUNCTYPE(None, wintypes.HWND, wintypes.UINT, ctypes.c_size_t, wintypes.DWORD)
        self.centered = False

        @timer_type
        def center(handle, message, timer, timestamp):
            self.user.KillTimer(None, timer)
            self.timer = None
            if self.centered:
                return
            rect = wintypes.RECT()
            if self.user.GetWindowRect(self.dialog, ctypes.byref(rect)):
                self.centered = True
                x, y = center_position(self.owner, (rect.right-rect.left, rect.bottom-rect.top), work)
                self.user.SetWindowPos(self.dialog, None, x, y, 0, 0, 0x15)

        self.timer_callback = center

        @callback_type
        def callback(code, handle, detail):
            # WH_CBT / HCBT_ACTIVATE. No move/resize handler is installed:
            # later activation, dragging and resizing preserve the user's position.
            if code == 5 and not self.centered and self.timer is None:
                name = ctypes.create_unicode_buffer(256)
                self.user.GetClassNameW(handle, name, len(name))
                if name.value == '#32770':
                    self.dialog = handle
                    # Explorer finalizes the remembered dialog size just after
                    # activation. Center once after that native initialization.
                    self.timer = self.user.SetTimer(None, 0, 300, ctypes.cast(center, ctypes.c_void_p)) or None
            return self.user.CallNextHookEx(self.hook, code, handle, detail)

        self.callback = callback  # Keep the native function pointer alive until unhooked.
        self.hook = self.user.SetWindowsHookExW(5, ctypes.cast(callback, ctypes.c_void_p), None, kernel.GetCurrentThreadId())

    def close(self):
        if self.timer:
            self.user.KillTimer(None, self.timer)
            self.timer = None
        if self.hook:
            self.user.UnhookWindowsHookEx(self.hook)
            self.hook = None


class Files:
    def _show(self, method, parent, **options):
        owner = parent.winfo_toplevel()
        grabbed = owner.grab_current()
        centering = CenterOnce(owner)
        try:
            return getattr(native, method)(parent=owner, **options)
        finally:
            centering.close()
            if grabbed is not None and grabbed.winfo_exists():
                grabbed.grab_set()

    def askopenfilename(self, parent=None, **options):
        return self._show('askopenfilename', parent, **options)

    def askopenfilenames(self, parent=None, **options):
        return self._show('askopenfilenames', parent, **options)

    def askdirectory(self, parent=None, **options):
        return self._show('askdirectory', parent, **options)

    def asksaveasfilename(self, parent=None, **options):
        return self._show('asksaveasfilename', parent, **options)


filedialog = Files()
