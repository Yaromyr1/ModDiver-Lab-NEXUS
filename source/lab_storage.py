"""Browse managed packages without copying them or forgetting saved options."""
import copy
import os
import re
import shutil
from collections import OrderedDict
from pathlib import Path
import tkinter as tk
from tkinter import ttk

import core
import nav_icons
from choice_screen import ChoiceScreen
from localization import tr


_summaries = OrderedDict()


def package_summary(path):
    """Cache only picker metadata, never decompressed mod contents.

    Folder signatures include every file, so edits inside extracted packages
    invalidate the summary even when the top directory timestamp is unchanged.
    """
    files = sorted((p for p in path.rglob('*') if p.is_file()), key=str) if path.is_dir() else [path]
    signature = tuple((str(p), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
                      for p in files for stat in [p.stat()])
    key = str(path.resolve())
    cached = _summaries.get(key)
    if cached is not None and cached[0] == signature:
        _summaries.move_to_end(key)
        return copy.deepcopy(cached[1])
    parsed = core.parse_mod(path)
    options = parsed.get('options', [])
    record = {'path': parsed['path'], 'name': parsed['name'], 'type': parsed['type'],
              'targets': parsed['targets'], 'runtime': bool(parsed.get('runtime')),
              'options': [o['name'] for o in options],
              'selected': {o['name']: bool(o.get('default', True)) for o in options}, 'enabled': True}
    _summaries[key] = (signature, copy.deepcopy(record))
    _summaries.move_to_end(key)
    while len(_summaries) > 256:
        _summaries.popitem(last=False)
    return record


def candidates(cfg):
    root = core.MODS_DIR.resolve()
    active = {os.path.normcase(str(Path(m['path']).resolve())) for m in cfg.get('mods', []) if m.get('path')}
    saved = {}
    for preset in cfg.get('mod_presets', {}).values():
        for mod in preset.get('mods', []):
            if mod.get('path'):
                saved[os.path.normcase(str(Path(mod['path']).resolve()))] = mod
    paths = []
    if not root.is_dir():
        return []
    for folder, directories, files in os.walk(root, followlinks=False):
        parent = Path(folder)
        directories[:] = [d for d in directories if not (parent / d).is_symlink()]
        manifests = {'manifest.json', 'mod.json', 'hellforge-mod.json'}
        if parent != root and manifests.intersection(f.casefold() for f in files):
            paths.append(parent)
            directories[:] = []
        else:
            paths.extend(parent / f for f in files if Path(f).suffix.lower() in ('.zip', '.7z'))
            # An unmanifested, extracted mod is one package, including its data subtree.
            if parent != root and (any(f.lower().endswith('.dl_bin') or re.search(r'\.patch_\d+(?:\.stream|\.gpu_resources)?$', f, re.I) for f in files)
                                   or 'data' in directories):
                paths.append(parent)
                directories[:] = []
    records = []
    for path in sorted(set(paths), key=lambda p: str(p).casefold()):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            continue
        identity = os.path.normcase(str(path.resolve()))
        if identity in active:
            continue
        try:
            record = package_summary(path)
            if not record.get('targets') and not record.get('runtime'):
                continue
            previous = saved.get(identity, {})
            record['selected'].update(copy.deepcopy(previous.get('selected', {})))
            if previous.get('category') in core.LIBRARY_CATEGORIES:
                record['category'] = previous['category']
            records.append(record)
        except (OSError, ValueError, RuntimeError):
            continue
    return records


def delete_packages(cfg, records):
    """Delete only selected managed packages; remove saved references to them."""
    root = core.MODS_DIR.resolve()
    paths = []
    active = {Path(m['path']).resolve() for m in cfg.get('mods', [])}
    for record in records:
        original = Path(record['path'])
        path = original.resolve()
        if (original.is_symlink() or path == root or not path.is_relative_to(root)
                or path in active or any(p.is_relative_to(path) for p in active)):
            raise ValueError('Only unused packages inside Lab Storage can be deleted.')
        paths.append(path)
    deleted, failures = [], []
    for path in paths:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            deleted.append(path)
        except OSError as exc:
            failures.append(str(exc))
    removed = set(deleted)
    for preset in cfg.get('mod_presets', {}).values():
        preset['mods'] = [m for m in preset.get('mods', []) if Path(m['path']).resolve() not in removed]
    if deleted:
        core.save_config(cfg)
    return removed, failures


class StoragePicker(ChoiceScreen):
    def __init__(self, app, records):
        super().__init__(app, size=(940, 560))
        self.records = records
        self.checked = set()
        content = self.card
        content.columnconfigure(0, weight=1)
        content.rowconfigure(2, weight=1)
        ttk.Label(content, text=tr('Your stored mods'), style='SettingsTitle.TLabel').grid(row=0, column=0, sticky='w', padx=20, pady=(20, 6))
        ttk.Label(content, text=tr('Select mods to add to this setup. Already added mods are hidden.'), style='Muted.TLabel', wraplength=700).grid(row=1, column=0, sticky='w', padx=20, pady=(0, 12))
        body = ttk.Frame(content)
        body.grid(row=2, column=0, sticky='nsew', padx=20)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(body, columns=('folder',), show='tree headings', selectmode='browse')
        self.tree.heading('#0', text=tr('Mod'))
        self.tree.heading('folder', text=tr('Stored package'))
        self.tree.column('#0', width=320)
        self.tree.column('folder', width=320)
        self.tree.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(body, command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=scroll.set)
        self.unchecked_icon = nav_icons.make_icon(app, 'checkbox_empty', app.theme['muted'])
        self.checked_icon = nav_icons.make_icon(app, 'checkbox_checked', app.theme['accent'])
        for index, record in enumerate(records):
            self.tree.insert('', 'end', iid=str(index), text=' ' + record['name'], image=self.unchecked_icon,
                             values=(str(Path(record['path']).relative_to(core.MODS_DIR)),))
        self.message = ttk.Label(content, text=tr('Click a mod to check it. Space toggles the focused row.') if records else tr('No other mods in lab storage. Add a ZIP or folder to store a new mod.'), style='Muted.TLabel', wraplength=700)
        self.message.grid(row=3, column=0, sticky='w', padx=20, pady=12)
        actions = ttk.Frame(content)
        actions.grid(row=4, column=0, sticky='ew', padx=20, pady=(0, 20))
        ttk.Button(actions, text=tr('Select all'), command=lambda: self.set_checked(self.tree.get_children())).pack(side='left')
        ttk.Button(actions, text=tr('Clear all'), command=lambda: self.set_checked(())).pack(side='left', padx=8)
        self.delete = ttk.Button(actions, text=tr('Delete selected'), style='Danger.TButton', command=self.delete_selected, state='disabled')
        self.delete.pack(side='left', padx=(4, 8))
        self.count = ttk.Label(actions, text='0 / ' + str(len(records)), style='Muted.TLabel')
        self.count.pack(side='left', padx=8)
        self.cancel_button = ttk.Button(actions, text=tr('Cancel'), command=self.close)
        self.cancel_button.pack(side='right')
        self.add = ttk.Button(actions, text=tr('Add selected mods'), style='Accent.TButton', command=self.accept, state='disabled')
        self.add._action_icon_name = 'import'
        import ui_polish
        ui_polish.update_icon(app, self.add)
        self.add.pack(side='right', padx=8)
        self.tree.bind('<Button-1>', self.click)
        self.tree.bind('<space>', self.toggle_focused)
        self.tree.bind('<Control-a>', lambda event: self.select_all())
        self.tree.bind('<Return>', lambda event: self.accept())
        self.add.bind('<Return>', lambda event: self.accept())
        self.cancel_button.bind('<Return>', self.close)
        self.activate(self.tree)

    def set_checked(self, rows):
        rows = set(rows)
        for row in self.checked.symmetric_difference(rows):
            self.tree.item(row, image=self.checked_icon if row in rows else self.unchecked_icon)
        self.checked = rows
        self.add.configure(state='normal' if rows else 'disabled')
        self.delete.configure(state='normal' if rows else 'disabled')
        self.count.configure(text=f'{len(rows)} / {len(self.tree.get_children())}')

    def click(self, event):
        if self.tree.identify_region(event.x, event.y) not in ('tree', 'cell'):
            return
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.focus(row)
            self.tree.selection_set(row)
            self.set_checked(self.checked.symmetric_difference({row}))
            self.tree.focus_set()
        return 'break'

    def toggle_focused(self, event=None):
        row = self.tree.focus()
        if row:
            self.set_checked(self.checked.symmetric_difference({row}))
        return 'break'

    def select_all(self):
        self.set_checked(self.tree.get_children())
        return 'break'

    def delete_selected(self):
        if self.app.busy or not self.checked:
            return
        from panel_dialogs import ResultScreen
        rows = sorted(self.checked, key=int)
        records = [self.records[int(row)] for row in rows]
        screen = ResultScreen(self.app, tr('Delete selected stored mods'),
            tr('Permanently delete these stored packages? Saved presets will also lose their references.') +
            '\n\n' + '\n'.join(record['name'] for record in records))
        def confirm():
            screen.close()
            self.app._set_buttons(False)
            def work():
                return delete_packages(self.app.cfg, records)
            def finished(result, error):
                self.app._set_buttons(True)
                if not self.winfo_exists():
                    return
                deleted, failures = result or (set(), [])
                for row in rows:
                    if Path(self.records[int(row)]['path']).resolve() in deleted:
                        self.checked.discard(row)
                        self.tree.delete(row)
                self.set_checked(self.checked)
                self.message.configure(text=str(error) if error else '\n'.join(failures) if failures else
                    tr(f'Deleted {len(deleted)} stored package(s).'))
                self.app.log(f'Deleted {len(deleted)} selected package(s) from Lab Storage.')
            self.app._background_update(work, finished, 'Delete stored mods')
        screen.buttons([('Cancel', None), ('Delete selected', None)])
        screen.option_buttons[1].configure(command=confirm, style='Danger.TButton')
        return screen

    def accept(self):
        if self.app.busy or not self.checked:
            return
        entries = [copy.deepcopy(self.records[int(row)]) for row in sorted(self.checked, key=int)]
        self.app.cfg.setdefault('mods', []).extend(entries)
        core.save_config(self.app.cfg)
        self.app.refresh_mods()
        self.app.refresh_status()
        self.app.log(f'Added {len(entries)} mod(s) from lab storage. Deploy to install this setup.')
        self.destroy()
