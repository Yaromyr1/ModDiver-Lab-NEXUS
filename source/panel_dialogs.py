"""Main-app dialog APIs backed by centered choice screens.

Editor modules continue importing tkinter's dialogs directly.
"""
import re
import tkinter as tk
from tkinter import ttk

from choice_screen import ChoiceScreen
from native_file_dialogs import filedialog
from localization import tr


def app_for(parent):
    while parent is not None:
        if hasattr(parent, 'theme') and hasattr(parent, 'cfg'):
            return parent
        parent = parent.master
    raise ValueError('A main-app dialog requires its parent widget.')


class ResultScreen(ChoiceScreen):
    def __init__(self, app, title, message='', size=None, default=None):
        super().__init__(app, size=size)
        self.result = default
        self.finished = tk.BooleanVar(master=app, value=False)
        self.content = ttk.Frame(self.card, padding=24)
        self.content.pack(fill='both', expand=True, padx=1, pady=1)
        ttk.Label(self.content, text=tr(title), style='Title.TLabel', wraplength=660).pack(fill='x', pady=(0, 12))
        if message:
            ttk.Label(self.content, text=tr(message), wraplength=660, justify='left').pack(fill='x', pady=(0, 16))
        self.actions = ttk.Frame(self.content)

    def buttons(self, choices):
        self.actions.pack(side='bottom', fill='x', pady=(16, 0))
        self.option_buttons = []
        for label, result in choices:
            button = ttk.Button(self.actions, text=tr(label), command=lambda value=result: self.finish(value))
            button.pack(side='right', padx=4)
            self.option_buttons.append(button)
        self.cancel_button = self.option_buttons[0]
        self.activate(self.cancel_button)
        for button in self.option_buttons:
            button.bind('<Return>', lambda event, item=button: item.invoke())

    def finish(self, value):
        self.result = value
        self.destroy()

    def destroy(self):
        super().destroy()
        self.finished.set(True)

    def wait(self):
        # Legacy callers need a return value. Tk still services timers and I/O
        # completions while waiting on this visible in-app panel.
        if not self.finished.get():
            self.app.wait_variable(self.finished)
        return self.result


class Messages:
    def showinfo(self, title, message, parent=None, **kwargs):
        screen = ResultScreen(app_for(parent), title, message)
        screen.buttons([('OK', None)])
        return screen.wait()

    showerror = showwarning = showinfo

    def askyesno(self, title, message, parent=None, cancel_label='No', **kwargs):
        screen = ResultScreen(app_for(parent), title, message, default=False)
        screen.buttons([(cancel_label, False), ('Yes', True)])
        return screen.wait()

    def askyesnocancel(self, title, message, parent=None, **kwargs):
        screen = ResultScreen(app_for(parent), title, message)
        screen.buttons([('Cancel', None), ('No', False), ('Yes', True)])
        return screen.wait()


messagebox = Messages()


class Strings:
    def askstring(self, title, prompt, initialvalue='', parent=None, **kwargs):
        screen = ResultScreen(app_for(parent), title, prompt)
        screen.value = tk.StringVar(master=screen, value=initialvalue)
        screen.entry = ttk.Entry(screen.content, textvariable=screen.value, width=60)
        screen.entry.pack(fill='x')
        screen.buttons([('Cancel', None), ('OK', None)])
        screen.option_buttons[1].configure(command=lambda: screen.finish(screen.value.get()))
        screen.entry.bind('<Return>', lambda event: screen.finish(screen.value.get()))
        screen.entry.selection_range(0, 'end')
        screen.entry.focus_set()
        return screen.wait()


simpledialog = Strings()


class Colors:
    def askcolor(self, color='#ffffff', title='Pick color', parent=None, **kwargs):
        app = app_for(parent)
        screen = ResultScreen(app, title, 'Choose a color or enter a hex color such as #1266d8.', default=(None, None))
        value = tk.StringVar(master=screen, value=color or '#ffffff')
        preview = tk.Label(screen.content, bg=color or '#ffffff', height=3)
        preview.pack(fill='x', pady=8)
        palette = ttk.Frame(screen.content)
        palette.pack(fill='x')
        for index, swatch in enumerate(('#000000', '#ffffff', '#ffd400', '#1266d8', '#ff6b35', '#ff4d4d',
                                         '#38d996', '#b06bff', '#008b8b', '#ff82b2', '#c8102e', '#8a93b0')):
            tk.Button(palette, bg=swatch, width=5, height=2, command=lambda c=swatch: value.set(c)).grid(row=index//6, column=index%6, padx=3, pady=3)
        entry = ttk.Entry(screen.content, textvariable=value)
        entry.pack(fill='x', pady=8)
        ttk.Label(screen.content, textvariable=screen.error, wraplength=500).pack(fill='x')
        def changed(*args):
            if re.fullmatch(r'#[0-9a-fA-F]{6}', value.get()):
                preview.configure(bg=value.get())
                screen.error.set('')
        value.trace_add('write', changed)
        def accept():
            text = value.get().strip()
            if not re.fullmatch(r'#[0-9a-fA-F]{6}', text):
                screen.error.set(tr('Enter a hex color such as #1266d8.'))
                return
            screen.finish((tuple(int(text[i:i+2], 16) for i in (1, 3, 5)), text))
        screen.buttons([('Cancel', (None, None)), ('OK', None)])
        screen.option_buttons[1].configure(command=accept)
        entry.bind('<Return>', lambda event: accept())
        return screen.wait()


colorchooser = Colors()

