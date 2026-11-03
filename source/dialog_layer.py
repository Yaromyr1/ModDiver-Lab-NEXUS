"""Owned foreground windows, including over the fullscreen application."""
import tkinter as tk


def foreground(window, owner):
    if not window.winfo_exists():
        return
    if str(window.transient()) != str(owner):
        window.transient(owner)
    window.attributes('-topmost', True)
    window.lift()


def install(app):
    def mapped(event):
        window = event.widget
        if (isinstance(window, tk.Toplevel) and not getattr(window, '_standalone_window', False)
                and not getattr(window, '_foreground_ready', False)):
            # Changing a Windows owner can recreate its native wrapper and
            # emit Map again. Mark first to avoid an unbounded remap loop.
            window._foreground_ready = True
            current = window.transient()
            owner = window.nametowidget(str(current)) if current else window.master.winfo_toplevel()
            foreground(window, owner)
            # The creator owns sizing and placement. Repositioning from Map or
            # Configure can fight Windows/DPI layout and keep Tk in a resize loop.
    app.bind_all('<Map>', mapped, add='+')


def center(window, owner, width, height):
    owner.update_idletasks()
    x = owner.winfo_rootx() + (owner.winfo_width() - width) // 2
    y = owner.winfo_rooty() + (owner.winfo_height() - height) // 2
    window.geometry(f'{width}x{height}+{max(0, x)}+{max(0, y)}')
