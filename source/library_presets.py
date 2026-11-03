"""Persistent library compositions and an embedded native preset toolbar."""
import copy
import tkinter as tk
from tkinter import ttk
import nav_icons
from localization import tr

SETTINGS = ('loaders_deploy_first', 'nomofomo', 'stratagem_bounce_removed',
            'consistent_vaulting', 'unlock_groups', 'unlock_padding')


def snapshot(cfg):
    return copy.deepcopy({'mods': cfg.get('mods', []),
                          'settings': {key: cfg[key] for key in SETTINGS if key in cfg}})


def sync_active(cfg):
    """Explicitly replace the active preset with the current working library."""
    name = cfg.get('active_mod_preset')
    if name and name in cfg.get('mod_presets', {}):
        cfg['mod_presets'][name] = snapshot(cfg)


def save_as(cfg, name):
    name = name.strip()
    if not name:
        raise ValueError('Enter a preset name.')
    if len(name) > 80:
        raise ValueError('Preset names can contain up to 80 characters.')
    presets = cfg.setdefault('mod_presets', {})
    if name in presets:
        raise ValueError('That preset already exists. Choose it to continue editing.')
    presets[name] = snapshot(cfg)
    cfg['active_mod_preset'] = name
    return name


def activate(cfg, name):
    if name not in cfg.get('mod_presets', {}):
        raise ValueError('Choose a saved preset.')
    state = copy.deepcopy(cfg['mod_presets'][name])
    cfg['mods'] = state['mods']
    for key in SETTINGS:
        cfg.pop(key, None)
    cfg.update(state.get('settings', {}))
    cfg['active_mod_preset'] = name


class PresetsPage(ttk.Frame):
    """A library subpage, following the Mod Options navigation pattern."""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky='ew', pady=(0, 16))
        ttk.Button(top, text=tr('Back to Library'), command=lambda: app._show('mods')).pack(side='left')
        self.active_label = ttk.Label(top, style='Chip.TLabel')
        self.active_label.pack(side='right')
        ttk.Label(self, text=tr('Your mod setups'), style='SettingsTitle.TLabel').grid(row=1, column=0, sticky='w')
        create = ttk.Frame(self, style='Panel.TFrame', padding=14)
        create.grid(row=2, column=0, sticky='ew', pady=(12, 16))
        create.columnconfigure(1, weight=1)
        ttk.Label(create, text=tr('New preset name'), style='Panel.TLabel').grid(row=0, column=0, padx=(0, 12))
        self.name = ttk.Entry(create)
        self.name.grid(row=0, column=1, sticky='ew', padx=(0, 12))
        save = ttk.Button(create, text=tr('Save current setup'), style='Accent.TButton', command=self.create)
        save.grid(row=0, column=2)
        self.name.bind('<Return>', lambda event: self.create())
        body = ttk.Frame(self)
        body.grid(row=3, column=0, sticky='nsew')
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.list = ttk.Treeview(body, columns=('mods', 'enabled'), show='tree headings', selectmode='browse', height=8)
        self.list.heading('#0', text=tr('Saved preset'))
        self.list.heading('mods', text=tr('Mods'))
        self.list.heading('enabled', text=tr('Enabled'))
        self.list.column('#0', width=300)
        for column in ('mods', 'enabled'):
            self.list.column(column, width=85, minwidth=65, stretch=False, anchor='center')
        self.list.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(body, command=self.list.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.list.configure(yscrollcommand=scrollbar.set)
        self.choice = tk.StringVar(master=self)
        self.list.bind('<<TreeviewSelect>>', self.selected)
        self.list.bind('<Double-1>', lambda event: self.apply())
        self.detail = ttk.Label(self, style='Muted.TLabel', wraplength=760, justify='left')
        self.detail.grid(row=4, column=0, sticky='ew', pady=(12, 8))
        actions = ttk.Frame(self)
        actions.grid(row=5, column=0, sticky='ew', pady=(0, 12))
        apply = ttk.Button(actions, text=tr('Apply preset and return'), style='Accent.TButton', command=self.apply)
        apply.pack(side='left')
        delete = ttk.Button(actions, text=tr('Delete preset'), style='Danger.TButton', command=self.delete)
        delete.pack(side='left', padx=8)
        update = ttk.Button(actions, text=tr('Update selected preset'), command=self.update_selected)
        update.pack(side='left')
        app.mod_action_buttons.extend((save, apply, delete, update))
        ttk.Label(self, text=tr('Presets keep their saved mods, order, groups, ON/OFF and components. Use Update selected preset to replace a saved setup with the current library. Deploy from the library to install.'), style='Muted.TLabel', wraplength=760).grid(row=6, column=0, sticky='w')
        self.refresh()

    def refresh(self, message=None):
        active = self.app.cfg.get('active_mod_preset', '')
        selected = self.choice.get() or active
        self.list.delete(*self.list.get_children())
        self.records = {}
        self.preset_icon = nav_icons.make_icon(self.app, 'tools', self.app.theme['accent'])
        for index, (name, preset) in enumerate(self.app.cfg.get('mod_presets', {}).items()):
            key = str(index)
            self.records[key] = name
            mods = preset.get('mods', [])
            self.list.insert('', 'end', iid=key, text=name, image=self.preset_icon,
                             values=(len(mods), sum(m.get('enabled', True) for m in mods)))
            if name == selected:
                self.list.selection_set(key)
        self.active_label.configure(text=tr('Active: ') + (active or tr('Current library')))
        self.detail.configure(text=message or tr('Select a preset to inspect it. Save your current library to create a new preset.'))

    def selected(self, event=None):
        rows = self.list.selection()
        if not rows or rows[0] not in self.records:
            return
        name = self.records[rows[0]]
        self.choice.set(name)
        mods = self.app.cfg['mod_presets'][name].get('mods', [])
        names = ', '.join(m.get('name', '?') for m in mods[:8])
        self.detail.configure(text=tr('Saved order: ') + (names or tr('Empty library')) + (' …' if len(mods)>8 else ''))

    def persist(self):
        import core
        core.save_config(self.app.cfg)
        self.refresh()

    def create(self):
        if self.app.busy:
            return
        try:
            save_as(self.app.cfg, self.name.get())
        except ValueError as exc:
            self.refresh(str(exc))
            return
        self.choice.set(self.app.cfg['active_mod_preset'])
        self.name.delete(0, 'end')
        self.persist()

    def apply(self):
        if self.app.busy:
            return
        # Read the widget now: <<TreeviewSelect>> may still be queued when the
        # user double-clicks or immediately presses Apply.
        self.selected()
        try:
            activate(self.app.cfg, self.choice.get())
        except ValueError as exc:
            self.refresh(str(exc))
            return
        self.app.selected_mod_index = None
        self.persist()
        self.app.refresh_mods()
        self.app._paint_loader_order()
        self.app.nomofomo_var.set(self.app.cfg.get('nomofomo', True))
        for key, variable in self.app.gameplay_vars.items():
            variable.set(self.app.cfg.get(key, True))
        self.app.refresh_status()
        self.app._show('mods')
        self.app.mod_detail.configure(text=tr('Preset applied: ') + self.choice.get() + tr('. Use Merge and Install All to deploy this setup.'))
        self.app.log('Preset applied: ' + self.choice.get() + '. Deploy from Merge and Install All to update the game.')

    def delete(self):
        if self.app.busy:
            return
        name = self.choice.get()
        if name not in self.app.cfg.get('mod_presets', {}):
            return
        if not self.app._ask_themed(tr('Delete preset'), tr('Delete preset "') + name + tr('"? The current library and mod files are kept.')):
            return
        del self.app.cfg['mod_presets'][name]
        if self.app.cfg.get('active_mod_preset') == name:
            self.app.cfg.pop('active_mod_preset', None)
        self.persist()

    def update_selected(self):
        if self.app.busy:
            return
        self.selected()
        name = self.choice.get()
        if name not in self.app.cfg.get('mod_presets', {}):
            self.refresh(tr('Choose a saved preset.'))
            return
        self.app.cfg['mod_presets'][name] = snapshot(self.app.cfg)
        self.app.cfg['active_mod_preset'] = name
        self.persist()
