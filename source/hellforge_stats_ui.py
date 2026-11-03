"""Small native workspace for HellForge's named, checked gameplay edits."""
import json
import threading
import tkinter as tk
from tkinter import ttk

import core
import hellforge_stats as stats
from localization import tr
from panel_dialogs import filedialog


class Editor(tk.Toplevel):
    _standalone_window = True

    def __init__(self, app):
        super().__init__(app)
        self.app, self.doc, self.busy = app, {'format': 1}, False
        self.title(tr('HellForge Stats Editor'))
        self.configure(bg=app.theme['bg'])
        self.geometry('1050x700')
        self.minsize(780, 580)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        bar = ttk.Frame(self, padding=14); bar.grid(row=0, column=0, sticky='ew')
        ttk.Label(bar, text=tr('Mod name')).pack(side='left')
        self.name = tk.StringVar(value='My HellForge Stats')
        ttk.Entry(bar, textvariable=self.name, width=20).pack(side='left', padx=8)
        self.buttons = []
        for title, action in (('Import stats', self.open), ('Read F8 changes', self.local),
                              ('Export + add to library', self.export)):
            button = ttk.Button(bar, text=tr(title), command=action)
            button.pack(side='left', padx=4); self.buttons.append(button)
        ttk.Label(self, text=tr('Choose a category, target and stat. HellForge checks every edit before export. '
                  'Import an existing stats file or read the changes saved by HellForge’s F8 editor to start from known names. '
                  'Local Stats applies last: reset conflicting in-game edits when testing your exported mod.'),
                  wraplength=980, padding=(14, 0, 14, 12)).grid(row=1, column=0, sticky='ew')
        table = ttk.Frame(self, padding=(14, 0)); table.grid(row=2, column=0, sticky='nsew')
        table.columnconfigure(0, weight=1); table.rowconfigure(1, weight=1)
        search = ttk.Frame(table); search.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 8))
        ttk.Label(search, text=tr('Search changes')).pack(side='left', padx=(0, 8))
        self.search = tk.StringVar()
        ttk.Entry(search, textvariable=self.search).pack(side='left', fill='x', expand=True)
        self.search.trace_add('write', lambda *_: self.populate())
        self.tree = ttk.Treeview(table, columns=('category', 'target', 'field', 'value'), show='headings', selectmode='browse')
        for key, width in (('category', 100), ('target', 230), ('field', 300), ('value', 120)):
            self.tree.heading(key, text=tr(key.title())); self.tree.column(key, width=width)
        self.tree.grid(row=1, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(table, command=self.tree.yview); scroll.grid(row=1, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>', self.select)
        form = ttk.Frame(self, padding=14); form.grid(row=3, column=0, sticky='ew')
        self.category = tk.StringVar(value='weapons')
        self.target, self.field, self.value = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for index, (label, variable) in enumerate((('Category', self.category), ('Target name / ID', self.target),
                                                  ('Stat name', self.field), ('Value', self.value))):
            form.columnconfigure(index, weight=1)
            ttk.Label(form, text=tr(label)).grid(row=0, column=index, sticky='w')
            widget = (ttk.Combobox(form, textvariable=variable, values=stats.CATEGORIES, state='readonly', width=15)
                      if index == 0 else ttk.Combobox(form, textvariable=variable, width=22)
                      if index in (1, 2) else ttk.Entry(form, textvariable=variable, width=16))
            widget.grid(row=1, column=index, sticky='ew', padx=(0, 8), pady=6)
            if index == 1: self.target_box = widget
            if index == 2: self.field_box = widget
        self.category.trace_add('write', lambda *_: self.suggestions())
        self.target.trace_add('write', lambda *_: self.suggestions())
        row = ttk.Frame(self, padding=(14, 0, 14, 10)); row.grid(row=4, column=0, sticky='ew')
        for title, action in (('Add / update stat', self.add), ('Remove selected stat', self.remove)):
            button = ttk.Button(row, text=tr(title), command=action); button.pack(side='left', padx=(0, 8)); self.buttons.append(button)
        ttk.Label(row, text=tr('Example: weapons · AR-23 Liberator · rpm · 900')).pack(side='left', padx=12)
        self.status = tk.StringVar(value=tr('Changes stay in this workspace until you export. Existing HellForge mods are preserved.'))
        ttk.Label(self, textvariable=self.status, wraplength=980, padding=14).grid(row=5, column=0, sticky='ew')
        self.protocol('WM_DELETE_WINDOW', lambda: None if self.busy else self.destroy())
        app._dark_titlebar(self)

    def populate(self):
        self.tree.delete(*self.tree.get_children())
        self.keys = {}
        for category in stats.CATEGORIES:
            for target, fields in self.doc.get(category, {}).items():
                for field, value in fields.items():
                    if not all(word in f'{category} {target} {field} {value}'.casefold()
                               for word in self.search.get().casefold().split()): continue
                    key = str(len(self.keys)); self.keys[key] = (category, target, field)
                    self.tree.insert('', 'end', iid=key, values=(category, target, field, json.dumps(value)))
        self.status.set(tr('{count} stat changes loaded.').format(count=len(self.keys)) +
                        (tr(' Imported raw edits are preserved and checked on export.') if self.doc.get('raw') else ''))
        self.suggestions()

    def suggestions(self):
        rows = self.doc.get(self.category.get(), {})
        self.target_box.configure(values=sorted(rows))
        fields = rows.get(self.target.get(), {})
        self.field_box.configure(values=sorted(fields))

    def select(self, event=None):
        selected = self.tree.selection()
        if not selected: return
        category, target, field = self.keys[selected[0]]
        for var, value in ((self.category, category), (self.target, target), (self.field, field),
                           (self.value, json.dumps(self.doc[category][target][field]))):
            var.set(value)

    def add(self):
        if self.busy: return
        try:
            category, target, field = self.category.get(), self.target.get().strip(), self.field.get().strip()
            if not target or not field: raise ValueError('Enter the target and stat name.')
            item = stats.value(self.value.get())
            self.doc.setdefault(category, {}).setdefault(target, {})[field] = item
            self.populate()
        except ValueError as exc: self.status.set(str(exc))

    def remove(self):
        if self.busy or not self.tree.selection(): return
        category, target, field = self.keys[self.tree.selection()[0]]
        del self.doc[category][target][field]
        if not self.doc[category][target]: del self.doc[category][target]
        self.populate()

    def load(self, path):
        try:
            self.doc = stats.read(path); self.populate()
        except (OSError, ValueError) as exc: self.status.set(str(exc))

    def open(self):
        if self.busy: return
        path = filedialog.askopenfilename(parent=self, title=tr('Import HellForge stats'), filetypes=[('Stats JSON', '*.json')])
        if path: self.load(path)

    def local(self):
        if self.busy: return
        root = core.hellforge_root(self.app.cfg)
        if root is None: self.status.set(tr('Select the HellForge installation in Merge and Deploy first.')); return
        self.load(root / 'mods/zz.local.stats/hellforge-stats.json')

    def export(self):
        if self.busy: return
        root = core.hellforge_root(self.app.cfg)
        if root is None: self.status.set(tr('Select the HellForge installation in Merge and Deploy first.')); return
        path = filedialog.asksaveasfilename(parent=self, title=tr('Export HellForge stats mod'),
                                           initialfile='HellForge Stats.zip', defaultextension='.zip', filetypes=[('ZIP', '*.zip')])
        if not path: return
        doc, name = json.loads(json.dumps(self.doc)), self.name.get()
        self.busy = True
        for button in self.buttons: button.state(['disabled'])
        self.status.set(tr('HellForge is checking the changes…'))
        results = []
        def work():
            try: results.append((stats.export(root, doc, name, path), None))
            except Exception as exc: results.append((None, str(exc)))
        threading.Thread(target=work, daemon=True).start()
        def poll():
            if not results: self.after(80, poll); return
            self.busy = False
            for button in self.buttons: button.state(['!disabled'])
            report, error = results[0]
            if error: self.status.set(error); return
            self.app._add_paths([path])
            self.status.set(tr('Checked ZIP added to the library. Use Merge and Install All, then PLAY in HellForge.'))
        self.after(80, poll)
