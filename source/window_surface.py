"""Keep the native Windows surface opaque during Tk frame changes."""
import ctypes
import os
from ctypes import wintypes


def install(window):
    if os.name != 'nt':
        return
    user = ctypes.windll.user32
    gdi = ctypes.windll.gdi32
    user.GetParent.argtypes = [wintypes.HWND]
    user.GetParent.restype = wintypes.HWND
    user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    hwnd = user.GetParent(window.winfo_id())
    if hwnd == getattr(window, '_surface_hwnd', None):
        return
    proc_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM)
    set_proc = user.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user.SetWindowLongW
    set_proc.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    set_proc.restype = ctypes.c_void_p
    get_proc = user.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user.GetWindowLongW
    get_proc.argtypes = [wintypes.HWND, ctypes.c_int]
    get_proc.restype = ctypes.c_void_p
    user.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                    wintypes.WPARAM, wintypes.LPARAM]
    user.CallWindowProcW.restype = ctypes.c_ssize_t
    gdi.CreateSolidBrush.argtypes = [wintypes.COLORREF]
    gdi.CreateSolidBrush.restype = wintypes.HBRUSH
    user.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
    gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]

    @proc_type
    def paint(handle, message, wparam, lparam):
        if message == 0x14:  # WM_ERASEBKGND: Tk's native frame otherwise erases white.
            rect = wintypes.RECT()
            user.GetClientRect(handle, ctypes.byref(rect))
            brush = gdi.CreateSolidBrush(window._bgr(window.theme['bg']))
            try:
                user.FillRect(wparam, ctypes.byref(rect), brush)
            finally:
                gdi.DeleteObject(brush)
            return 1
        return user.CallWindowProcW(previous, handle, message, wparam, lparam)

    previous = set_proc(hwnd, -4, ctypes.cast(paint, ctypes.c_void_p))
    # Tk replaces its native wrapper on fullscreen changes. Keep each callback
    # alive through native destruction, and hook every replacement wrapper.
    if not hasattr(window, '_surface_procs'):
        window._surface_procs = []
    window._surface_procs.append(paint)
    window._surface_hwnd = hwnd
    disabled = ctypes.c_int(1)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 3, ctypes.byref(disabled), 4)

    def restore(event):
        if event.widget == window:
            if user.IsWindow(hwnd) and get_proc(hwnd, -4) == ctypes.cast(paint, ctypes.c_void_p).value:
                set_proc(hwnd, -4, previous)
    window.bind('<Destroy>', restore, add='+')


def repaint(window):
    if os.name == 'nt' and hasattr(window, '_surface_hwnd'):
        # Invalidate the frame and every child, and finish painting before returning.
        redraw = ctypes.windll.user32.RedrawWindow
        redraw.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.HRGN, wintypes.UINT]
        redraw(window._surface_hwnd, None, None, 0x581)
        ctypes.windll.dwmapi.DwmFlush()
