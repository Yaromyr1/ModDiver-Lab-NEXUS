"""A focused entry page for the native ModDiver creation workspaces."""
from localization import tr
import tkinter as tk
from tkinter import ttk
import asset_editor
import nav_icons
import ui_polish
import core
import nexus_mode


class CreatorPage(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.rowconfigure(0, weight=1); self.columnconfigure(0, weight=1)
        canvas = tk.Canvas(self, bg=app.theme['bg'], highlightthickness=0, bd=0)
        app.creator_canvas = canvas
        canvas.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(self, command=canvas.yview); scroll.grid(row=0, column=1, sticky='ns')
        canvas.configure(yscrollcommand=scroll.set)
        body = ttk.Frame(canvas, padding=(0, 4, 12, 20)); body.columnconfigure(0, weight=1)
        window = canvas.create_window(0, 0, window=body, anchor='nw')
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
        def layout(event=None):
            canvas.configure(scrollregion=canvas.bbox('all'))
            width = max(180, body.winfo_width()-60)
            def wrap(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Label) and child.cget('wraplength'):
                        original = getattr(child, '_preferred_wrap', int(float(child.cget('wraplength'))))
                        child._preferred_wrap = original
                        limit = max(150, (width-40)//3) if original == 220 else width
                        value = min(original, limit)
                        if int(float(child.cget('wraplength'))) != value: child.configure(wraplength=value)
                    wrap(child)
            wrap(body)
        body.bind('<Configure>', layout)
        hero = ttk.Frame(body, style='Panel.TFrame', padding=22); hero.grid(row=0, column=0, sticky='ew', pady=(0, 16))
        self.heading(hero, 'Choose your creative workspace', 'creator', 21)
        ttk.Label(hero, text=tr('Edit gameplay, create audio mods, or work directly with game data.'),
                  style='PanelMuted.TLabel', wraplength=740).pack(anchor='w', pady=(9, 16))
        path = ttk.Frame(hero, style='Panel.TFrame'); path.pack(fill='x')
        for i, (title, caption) in enumerate((('01  CHOOSE', 'Pick a workspace'), ('02  CREATE', 'Preview your changes'), ('03  EXPORT', 'Add your mod to the library'))):
            part = ttk.Frame(path, style='Panel.TFrame', padding=(0, 0, 20, 0)); part.grid(row=0, column=i, sticky='nw')
            path.columnconfigure(i, weight=1)
            ttk.Label(part, text=tr(title), style='Panel.TLabel', font=('Segoe UI Semibold', 10)).pack(anchor='w')
            ttk.Label(part, text=tr(caption), style='PanelMuted.TLabel', wraplength=220).pack(anchor='w', pady=(4, 0))
        border = tk.Frame(body, bg=app.theme['panel'], highlightthickness=1, highlightbackground='#ffd400', bd=0)
        app.advanced_creator = app.creator_audio_card = border
        border.grid(row=1, column=0, sticky='ew', pady=(0, 16))
        main = ttk.Frame(border, style='Panel.TFrame', padding=22); main.pack(fill='both', expand=True, padx=1, pady=1)
        ttk.Label(main, text=tr('SOUND & VISUAL MODS'), style='PanelMuted.TLabel', font=('Segoe UI Semibold', 9)).pack(anchor='w', pady=(0, 8))
        self.heading(main, 'Audio Studio', 'waveform', 19, ('windows', 'linux'))
        ttk.Label(main, text=tr('Give your favourite weapon a new sound. Replace a voice line, adjust volume, or work with native visual assets.'),
                  style='PanelMuted.TLabel', wraplength=740).pack(anchor='w', pady=(8, 14))
        ui_polish.action_button(app, main, 'Open Audio Studio', lambda: asset_editor.Editor(app),
                               role='primary', icon='play').pack(anchor='w')
        ttk.Label(main, text=tr('Game audio loads from your installation. Listen first, make an edit, then export a mod ZIP.'),
                  style='PanelMuted.TLabel', wraplength=740).pack(anchor='w', pady=(12, 0))
        data = ttk.Frame(body, style='Panel.TFrame', padding=22); data.grid(row=2, column=0, sticky='ew', pady=(0, 16))
        app.creator_native_card = data
        ttk.Label(data, text=tr('GAMEPLAY & STATS'), style='PanelMuted.TLabel', font=('Segoe UI Semibold', 9)).pack(anchor='w', pady=(0, 8))
        self.heading(data, 'Native Game Data Editor', 'sliders', 16, ('windows', 'linux'))
        ttk.Label(data, text=tr('Browse supported game records and edit named properties. Use this workspace for weapons, equipment and other supported stat changes.'),
                  style='PanelMuted.TLabel', wraplength=740).pack(anchor='w', pady=(8, 14))
        ui_polish.action_button(app, data, 'Open Native Data Editor', app.open_native_editor, role='primary', icon='sliders').pack(anchor='w')
        ui_polish.action_button(app, data, 'Open HellForge Stats Editor', app.open_hellforge_stats, icon='sliders').pack(anchor='w', pady=(8, 0))
        ttk.Label(data, text=tr('Advanced workspace · Windows & Linux · Unresolved properties stay read-only.'),
                  style='PanelMuted.TLabel', wraplength=740).pack(anchor='w', pady=(12, 0))
        help_card = ttk.Frame(body, style='Panel.TFrame', padding=20); help_card.grid(row=3, column=0, sticky='ew')
        self.heading(help_card, 'Need another tool?', 'info', 12)
        ttk.Label(help_card, text=tr('Manage loaders and tool updates in Tools. Use Data Bot for raw decoding and mod repair.'),
                  style='PanelMuted.TLabel', wraplength=740).pack(anchor='w', pady=(8, 12))
        buttons = ttk.Frame(help_card, style='Panel.TFrame'); buttons.pack(fill='x')
        ui_polish.action_button(app, buttons, 'Open Tools', lambda: app._show('tools'), icon='tools').pack(side='left')
        ui_polish.action_button(app, buttons, 'Open Data Bot', lambda: app._show('editor'), icon='editor').pack(side='left', padx=8)
        ui_polish.action_button(app, buttons, 'Open Mod Library', lambda: app._show('mods'), icon='mods').pack(side='left')

    def heading(self, parent, text, icon, size, platforms=()):
        image = nav_icons.make_icon(self.app, icon, self.app.theme['accent'])
        if platforms:
            row = ttk.Frame(parent, style='Panel.TFrame')
            row.pack(fill='x', anchor='w')
            label = ttk.Label(row, text='  ' + tr(text), image=image, compound='left',
                              style='Panel.TLabel', font=('Segoe UI Semibold', size))
            label.pack(side='left', anchor='w')
            import platform_icons
            badges = platform_icons.make(self.app, platforms)
            badge = ttk.Label(row, image=badges, style='Panel.TLabel')
            badge.pack(side='right', anchor='e', padx=(12, 2))
            row._platform_badges = badges
        else:
            label = ttk.Label(parent, text='  ' + tr(text), image=image, compound='left',
                              style='Panel.TLabel', font=('Segoe UI Semibold', size))
            label.pack(anchor='w')
        label._heading_icon = image
