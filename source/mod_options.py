"""In-app mod component selection with immediate persistence."""
import tkinter as tk
from tkinter import ttk
import core
from localization import tr


class OptionsPage(ttk.Frame):
    def __init__(self, parent, app, mod):
        super().__init__(parent)
        self.app, self.mod = app, mod
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky='ew', pady=(0, 14))
        ttk.Button(top, text=tr('Back to Library'), command=lambda: app._show('mods')).pack(side='left')
        self.summary = ttk.Label(top, style='Muted.TLabel')
        self.summary.pack(side='right')
        title = ttk.Label(self, text=mod['name'], style='SettingsTitle.TLabel', wraplength=700)
        title.grid(row=1, column=0, sticky='w', pady=(0, 6))
        actions = ttk.Frame(self)
        actions.grid(row=2, column=0, sticky='ew', pady=(0, 12))
        ttk.Button(actions, text=tr('Select all'), command=lambda: self.set_all(True)).pack(side='left')
        ttk.Button(actions, text=tr('Clear all'), command=lambda: self.set_all(False)).pack(side='left', padx=8)
        ttk.Label(actions, text=tr('Changes save automatically. Deploy to apply them.'), style='Muted.TLabel').pack(side='left', padx=8)
        self.canvas = tk.Canvas(self, bg=app.theme['bg'], bd=0, highlightthickness=0)
        self.canvas._theme_background = True
        self.canvas.grid(row=3, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(self, command=self.canvas.yview)
        scroll.grid(row=3, column=1, sticky='ns')
        self.canvas.configure(yscrollcommand=scroll.set)
        body = ttk.Frame(self.canvas)
        item = self.canvas.create_window(0, 0, window=body, anchor='nw')
        body.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(item, width=e.width))
        self.variables = {}
        self.buttons = {}
        for name in dict.fromkeys(mod['options']):
            var = tk.BooleanVar(self, value=mod.get('selected', {}).get(name, True))
            self.variables[name] = var
            row = ttk.Frame(body, style='Panel.TFrame', padding=12)
            row.pack(fill='x', pady=(0, 8))
            row.columnconfigure(0, weight=1)
            label = ttk.Label(row, text=tr(name), style='Panel.TLabel', width=1, justify='left')
            label.grid(row=0, column=0, sticky='ew', padx=(0, 14))
            label.bind('<Configure>', lambda e, w=label: w.configure(wraplength=max(1, e.width)))
            button = ttk.Button(row, command=lambda n=name: self.toggle(n), width=13)
            button.grid(row=0, column=1)
            self.buttons[name] = button
        def wheel(event):
            delta = -1 if getattr(event, 'num', None) == 4 or getattr(event, 'delta', 0) > 0 else 1
            self.canvas.yview_scroll(delta * 3, 'units')
            return 'break'
        def bind_wheel(widget):
            for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                widget.bind(sequence, wheel)
            for child in widget.winfo_children():
                bind_wheel(child)
        bind_wheel(body)
        self.canvas.bind('<MouseWheel>', wheel)
        self.paint()

    def paint(self):
        count = sum(var.get() for var in self.variables.values())
        self.summary.configure(text=tr(f'{count} / {len(self.variables)} enabled') + '  •  ' + tr('Saved automatically'))
        for name, button in self.buttons.items():
            enabled = self.variables[name].get()
            button.configure(text=tr('✓  Included' if enabled else '—  Excluded'),
                             style='Accent.TButton' if enabled else 'TButton')

    def save(self):
        self.mod['selected'] = {name: bool(var.get()) for name, var in self.variables.items()}
        core.save_config(self.app.cfg)
        self.paint()

    def toggle(self, name):
        self.variables[name].set(not self.variables[name].get())
        self.save()

    def set_all(self, enabled):
        for var in self.variables.values():
            var.set(enabled)
        self.save()
