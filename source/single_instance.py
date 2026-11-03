"""A process-owned lock shared by all launchers and application versions."""
import ctypes
import errno
import os
from pathlib import Path


class InstanceLock:
    def __init__(self, data, filename='instance.lock'):
        self.path = Path(data) / filename
        self.handle = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open('a+b')
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b'\0'); handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            self.activate_existing()
            return False
        self.handle = handle
        handle.seek(1); handle.truncate(); handle.write(str(os.getpid()).encode('ascii')); handle.flush()
        return True

    def activate_existing(self):
        if os.name != 'nt':
            return
        try:
            # Windows denies reads that overlap another process's locked byte.
            # Read just the PID metadata after it so focus still works.
            pid = self.owner_pid()
            from ctypes import wintypes
            user = ctypes.WinDLL('user32', use_last_error=True)
            user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            user.IsWindowVisible.argtypes = [wintypes.HWND]
            user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            user.SetForegroundWindow.argtypes = [wintypes.HWND]
            callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def visit(hwnd, _):
                owner = wintypes.DWORD()
                user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
                if owner.value == pid and user.IsWindowVisible(hwnd):
                    user.ShowWindow(hwnd, 9)  # restore a minimized window
                    user.SetForegroundWindow(hwnd)
                    return False
                return True
            user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
            user.EnumWindows(callback_type(visit), 0)
        except (OSError, ValueError):
            pass

    def owner_pid(self):
        with self.path.open('rb') as handle:
            handle.seek(1)
            return int(handle.read())

    def release(self):
        if self.handle is None:
            return
        if os.name == 'nt':
            import msvcrt
            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        self.handle.close()
        self.handle = None
