"""Centered choices inside the app, without a native popup window."""
import tkinter as tk


def active(app):
    screen = getattr(app, '_choice_screen', None)
    if screen is not None and screen.winfo_exists():
        screen.lift()
        return screen
    return None


class ChoiceScreen(tk.Frame):
    def __init__(self, app, size=None):
        super().__init__(app, bg=app.theme['bg'], bd=0)
        self.app = app
        self.previous_focus = app.focus_get()
        self.previous_screen = active(app)
        self.previous_grab = app.grab_current()
        self.size = size
        self.card = tk.Frame(self, bg=app.theme['panel'], bd=0,
                             highlightthickness=1, highlightbackground=app.theme['accent'])
        self.card.place(relx=.5, rely=.5, anchor='center')
        self.error = tk.StringVar(master=self)
        app._choice_screen = self
        self.place(x=0, y=0, relwidth=1, relheight=1)
        self.lift()
        self.bind('<Configure>', self._layout)
        self.card.bind('<Configure>', self._layout)
        self.bind('<Escape>', self.close)

    def _layout(self, event=None):
        width, height = self.size or (self.card.winfo_reqwidth(), self.card.winfo_reqheight())
        available_width = max(1, self.winfo_width()-40)
        available_height = max(1, self.winfo_height()-40)
        # Natural-size cards can grow when an inline error appears. Storage
        # uses an explicit size so its scrollable table fills the available area.
        self.card.place_configure(
            width=min(width, available_width) if self.size or width > available_width else '',
            height=min(height, available_height) if self.size or height > available_height else '')

    def activate(self, focus):
        # Route Escape from any option or tree row to this screen, before the
        # root's fullscreen Escape handler. Never enter a nested Tk wait.
        def bind_children(widget):
            for child in widget.winfo_children():
                child.bindtags((str(self), *child.bindtags()))
                bind_children(child)
        bind_children(self)
        self._layout()
        self.grab_set()
        focus.focus_set()

    def close(self, event=None):
        self.destroy()
        return 'break'

    def destroy(self):
        if not self.winfo_exists():
            return
        if self.grab_current() is self:
            self.grab_release()
        if getattr(self.app, '_choice_screen', None) is self:
            self.app._choice_screen = (self.previous_screen if self.previous_screen is not None
                                       and self.previous_screen.winfo_exists() else None)
        super().destroy()
        if self.previous_grab is not None and self.previous_grab.winfo_exists():
            self.previous_grab.grab_set()
        if self.previous_focus is not None and self.previous_focus.winfo_exists():
            self.previous_focus.focus_set()
