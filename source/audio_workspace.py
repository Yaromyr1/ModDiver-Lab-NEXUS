"""Full-page, native ModDiver sound workstation. No browser or local API server."""
from localization import tr
import os
import queue
import shutil
import subprocess
import threading
import time
import ui_polish
import nav_icons
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import core
from audio_backend import AudioBackend
from panel_dialogs import filedialog


class AudioWorkspace(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=(14, 12))
        self.app = app
        self.backend = getattr(app, '_audio_backend', None)
        self.busy = False
        self.results = queue.Queue()
        self.scan_updates = queue.Queue()
        self.rows, self.items, self.categories = [], {}, []
        self.player, self.peaks = None, None
        self.active_side = 'original'
        self.search_timer, self.pending_navigation = None, None
        self.state = {'assignments': {}, 'gains': {}}
        self.controls, self.timer_ids = [], set()
        self.play_started, self.playback_timer = None, None
        self.preview_request = 0
        self.play_duration, self.play_position = 0.0, 0.0
        self.columnconfigure(0, weight=1); self.rowconfigure(3, weight=1)
        self.heading = tk.StringVar(value=tr('Your next sound starts here'))
        self.status = tk.StringVar(value=tr('Finding your game. Audio is read from your own installation.'))
        self.game_label = tk.StringVar(value=tr('Connecting to your game…'))
        self.source_path = tk.StringVar()
        self.project_label = tk.StringVar(value=tr('No project · You can listen before creating a mod.'))
        self.next_step = tk.StringVar(value=tr('Choose a collection on the left, then select a sound to listen.'))
        self.crumb = tk.StringVar(value=tr('Browse weapons, voices, music and more'))
        self.search, self.sound_search = tk.StringVar(), tk.StringVar()
        self.name, self.label = tk.StringVar(value=tr('My Audio Mod')), tk.StringVar()
        self.gain, self.timing = tk.StringVar(value='0'), tk.BooleanVar(value=True)
        self.volume_slider = tk.DoubleVar(value=0)
        self.start, self.end = tk.StringVar(value='0'), tk.StringVar()
        self.edited_only = tk.BooleanVar(value=False)
        self.detail = tk.StringVar(value=tr('Technical details appear here after you choose a sound.'))
        self.selection_note = tk.StringVar(value=tr('Listen to the original. Replace it with your own audio. Export when you’re ready.'))
        self.file_label = tk.StringVar(value=tr('Choose a sound to begin'))
        self.elapsed = tk.StringVar(value='0:00.00 / 0:00.00')

        intro = ttk.Frame(self); intro.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        ttk.Label(intro, text=tr('01  CHOOSE A SOUND     →     02  MAKE IT YOURS     →     03  EXPORT YOUR MOD'),
                  font=('Segoe UI Semibold', 10)).pack(side='left')
        self.button(intro, tr('Quick guide'), self.toggle_guide, icon='info').pack(side='right')
        self.guide = ttk.Frame(self, style='Panel.TFrame', padding=14)
        self.guide_text = ttk.Label(self.guide, style='PanelMuted.TLabel', wraplength=950,
            text=tr('1. Browse a category and choose a sound. Play original lets you hear what the game uses.\n'
                 '2. Create a project, then Import replacement audio or change Volume. Play edited compares your saved changes.\n'
                 '3. Export mod ZIP saves your mod. Add it to the library, then use Merge and Install All to use it in game.\n'
                 'Edits save automatically. Undo reverses an edit. More options contains trimming, mute and custom names.'))
        self.guide_text.pack(fill='x')

        project = ttk.Frame(self, style='Panel.TFrame', padding=(12, 10)); project.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        self.new_button = self.button(project, tr('New audio mod'), self.new_project, role='primary', icon='plus')
        self.new_button.pack(side='left')
        self.button(project, tr('Open project'), self.open_project, icon='folder').pack(side='left', padx=(6, 14))
        name_label = ttk.Label(project, text=tr('Mod name'), style='PanelMuted.TLabel')
        name_label.pack(side='left')
        name_entry = ttk.Entry(project, textvariable=self.name, width=22)
        name_entry.pack(side='left', padx=8)
        self.build_button = self.button(project, tr('Finish & export'), self.build, role='export', icon='export')
        self.build_button.pack(side='right')
        self.redo_button = self.button(project, tr('Redo'), lambda: self.edit('redo'), icon='redo')
        self.redo_button.pack(side='right', padx=(0, 10))
        self.undo_button = self.button(project, tr('Undo'), lambda: self.edit('undo'), icon='undo')
        self.undo_button.pack(side='right', padx=6)
        project_children = project.winfo_children()
        for child in project_children: child.pack_forget()
        def toolbar_layout(event=None):
            compact = project.winfo_width() < max(1050, sum(c.winfo_reqwidth() for c in project_children)+100)
            if getattr(project, '_compact', None) == compact: return
            project._compact = compact
            for child in project_children: child.grid_forget()
            for column in range(7): project.columnconfigure(column, weight=1 if column == 3 else 0)
            self.new_button.grid(row=0, column=0, sticky='w', padx=(0, 6))
            project_children[1].grid(row=0, column=1, sticky='w', padx=(0, 10))
            self.build_button.grid(row=0, column=6, sticky='e')
            name_label.grid(row=1 if compact else 0, column=0 if compact else 2, sticky='w', pady=(6, 0) if compact else 0)
            name_entry.grid(row=1 if compact else 0, column=1 if compact else 3, columnspan=3 if compact else 1, sticky='ew', padx=(6, 12), pady=(6, 0) if compact else 0)
            self.undo_button.grid(row=1 if compact else 0, column=4, padx=(0, 6), pady=(6, 0) if compact else 0)
            self.redo_button.grid(row=1 if compact else 0, column=5, padx=(0, 10), pady=(6, 0) if compact else 0)
        project.bind('<Configure>', toolbar_layout)
        connection = ttk.Frame(self); connection.grid(row=2, column=0, sticky='ew', pady=(0, 10))
        ttk.Label(connection, textvariable=self.game_label, style='Muted.TLabel').pack(side='left')
        ttk.Label(connection, textvariable=self.project_label, style='Muted.TLabel', wraplength=290).pack(side='left', padx=16)
        self.button(connection, tr('Change game folder'), self.choose_game, icon='folder').pack(side='right')
        self.button(connection, tr('Refresh sounds'), lambda: self.connect(rescan=True), icon='about').pack(side='right', padx=6)

        app.style.configure('Studio.TPanedwindow', background=app.theme['panel2'])
        panes = ttk.Panedwindow(self, orient='horizontal', style='Studio.TPanedwindow'); panes.grid(row=3, column=0, sticky='nsew')
        library = ttk.Frame(panes, width=340, padding=(0, 0, 14, 0)); panes.add(library, weight=2)
        library.columnconfigure(0, weight=1); library.rowconfigure(2, weight=2); library.rowconfigure(6, weight=3)
        self.section(library, tr('Find a collection'), 'search').grid(row=0, column=0, sticky='w', pady=(0, 8))
        self.collection_search_entry = ttk.Entry(library, textvariable=self.search)
        self.collection_search_entry.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        self.search.trace_add('write', lambda *_: self.defer_search())
        collections = ttk.Frame(library); collections.grid(row=2, column=0, sticky='nsew')
        collections.columnconfigure(0, weight=1); collections.rowconfigure(0, weight=1)
        self.browser = ttk.Treeview(collections, show='tree', selectmode='browse', height=6)
        self.browser.column('#0', width=300, minwidth=180); self.browser.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(collections, command=self.browser.yview); scrollbar.grid(row=0, column=1, sticky='ns')
        self.browser.configure(yscrollcommand=scrollbar.set); self.browser.bind('<<TreeviewSelect>>', self.select_item)
        self.section(library, tr('Choose a sound'), 'waveform').grid(row=3, column=0, sticky='w', pady=(14, 6))
        ttk.Label(library, textvariable=self.crumb, style='Muted.TLabel', wraplength=310).grid(row=4, column=0, sticky='w', pady=(0, 6))
        filters = ttk.Frame(library); filters.grid(row=5, column=0, sticky='ew', pady=(0, 8))
        ttk.Label(filters, text=tr('Search')).pack(side='left', padx=(0, 6))
        self.sound_search_entry = ttk.Entry(filters, textvariable=self.sound_search, width=14)
        self.sound_search_entry.pack(side='left', fill='x', expand=True)
        ttk.Checkbutton(filters, text=tr('Edited'), variable=self.edited_only, command=self.populate_sounds).pack(side='right', padx=(8, 0))
        self.sound_search.trace_add('write', lambda *_: self.populate_sounds())
        table = ttk.Frame(library); table.grid(row=6, column=0, sticky='nsew')
        table.rowconfigure(0, weight=1); table.columnconfigure(0, weight=1)
        self.sounds = ttk.Treeview(table, columns=('name', 'duration', 'status'), show='headings', selectmode='extended', height=8)
        for col, title, width in [('name', 'Sound', 196), ('duration', 'Length', 54), ('status', 'State', 65)]:
            self.sounds.heading(col, text=tr(title)); self.sounds.column(col, width=width, minwidth=45, stretch=col=='name')
        self.sounds.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(table, command=self.sounds.yview); scrollbar.grid(row=0, column=1, sticky='ns')
        self.sounds.configure(yscrollcommand=scrollbar.set); self.sounds.bind('<<TreeviewSelect>>', self.select_sound)
        self.count_label = ttk.Label(library, text=tr('Choose a collection above'), style='Muted.TLabel')
        self.count_label.grid(row=7, column=0, sticky='w', pady=(8, 0))
        ttk.Label(library, text=tr('Ctrl-click or Shift-click to select sounds for a volume change.'),
                  style='Muted.TLabel', wraplength=320).grid(row=8, column=0, sticky='w', pady=(4, 0))
        self.empty = ttk.Label(table, text=tr('Choose a collection above.\nIts sounds will appear here.'), justify='center', style='Muted.TLabel')
        self.empty.place(relx=.5, rely=.45, anchor='center')

        work = ttk.Frame(panes, width=690); panes.add(work, weight=5)
        work.rowconfigure(0, weight=1); work.columnconfigure(0, weight=1)
        canvas = tk.Canvas(work, bg=app.theme['panel'], highlightthickness=0)
        canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(work, command=canvas.yview); scrollbar.grid(row=0, column=1, sticky='ns')
        canvas.configure(yscrollcommand=scrollbar.set)
        detail = ttk.Frame(canvas, style='Panel.TFrame', padding=20)
        window = canvas.create_window(0, 0, anchor='nw', window=detail)
        detail.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        def resize(e):
            canvas.itemconfigure(window, width=e.width)
            for label in detail.winfo_children():
                if isinstance(label, ttk.Label): label.configure(wraplength=max(180, e.width-48))
        canvas.bind('<Configure>', resize)
        self.section(detail, tr('SOUND WORKSPACE'), 'waveform', panel=True).pack(anchor='w', pady=(0, 8))
        ttk.Label(detail, textvariable=self.heading, style='Panel.TLabel', font=('Segoe UI Semibold', 19)).pack(anchor='w')
        ttk.Label(detail, textvariable=self.selection_note, style='PanelMuted.TLabel', wraplength=620).pack(anchor='w', pady=(6, 14))
        self.wave = tk.Canvas(detail, height=145, bg=app.theme['bg'], highlightthickness=1, highlightbackground=app.theme['panel2'])
        self.wave.pack(fill='x'); self.wave.bind('<Configure>', lambda e: self.draw_wave())
        wave_info = ttk.Frame(detail, style='Panel.TFrame'); wave_info.pack(fill='x', pady=(7, 8))
        self.wave_label = ttk.Label(wave_info, text=tr('Waveform appears when you choose a sound'), style='PanelMuted.TLabel')
        self.wave_label.pack(side='left')
        ttk.Label(wave_info, textvariable=self.elapsed, style='Panel.TLabel', font=('Consolas', 10)).pack(side='right')
        transport = ttk.Frame(detail, style='Panel.TFrame'); transport.pack(fill='x', pady=(0, 14))
        self.original_button = self.button(transport, tr('Play original'), lambda: self.preview('original', True), role='primary', icon='play')
        self.original_button.pack(side='left')
        self.edited_button = self.button(transport, tr('Play edited'), lambda: self.preview('edited', True), role='primary', icon='play')
        self.edited_button.pack(side='left', padx=8)
        self.stop_button = ui_polish.action_button(app, transport, 'Stop', self.stop, icon='stop')
        self.stop_button.pack(side='left')
        ui_polish.creator_layout(transport)
        ttk.Separator(detail).pack(fill='x', pady=(0, 14))
        self.section(detail, tr('Make it yours'), 'import', panel=True).pack(anchor='w')
        ttk.Label(detail, textvariable=self.file_label, style='PanelMuted.TLabel', wraplength=620).pack(anchor='w', pady=(6, 9))
        self.import_button = self.button(detail, tr('Import replacement audio'), self.assign, role='primary', icon='import')
        self.import_button.pack(anchor='w')
        ttk.Label(detail, text=tr('WAV, MP3, FLAC & more. Game conversion is automatic.'),
                  style='PanelMuted.TLabel', wraplength=620).pack(anchor='w', pady=(7, 12))
        volume = ttk.Frame(detail, style='Panel.TFrame'); volume.pack(fill='x')
        ttk.Label(volume, text=tr('Volume'), style='Panel.TLabel', font=('Segoe UI Semibold', 10)).pack(side='left')
        ttk.Scale(volume, from_=-24, to=12, variable=self.volume_slider, orient='horizontal',
                  command=lambda v: self.gain.set(f'{round(float(v)*2)/2:g}')).pack(side='left', fill='x', expand=True, padx=12)
        ttk.Spinbox(volume, from_=-96, to=96, increment=.5, textvariable=self.gain, width=6).pack(side='left')
        ttk.Label(volume, text=tr(' dB'), style='PanelMuted.TLabel').pack(side='left', padx=(0, 10))
        self.volume_button = self.button(volume, tr('Apply volume'), self.apply_gain, icon='volume'); self.volume_button.pack(side='left')
        ttk.Label(detail, text=tr('0 dB is unchanged. Negative values are quieter; positive values are louder.'),
                  style='PanelMuted.TLabel', wraplength=620).pack(anchor='w', pady=(6, 10))
        self.more_button = self.button(detail, tr('More options: trim, mute & sound names'), self.toggle_more, icon='sliders')
        self.more_button.pack(anchor='w', pady=(6, 0))
        self.more = ttk.Frame(detail, style='Panel.TFrame', padding=(0, 16, 0, 0))
        self.more_open = False
        ttk.Checkbutton(self.more, text=tr('Use the replacement’s length in game'), variable=self.timing).pack(anchor='w')
        ttk.Label(self.more, text=tr('Saved with Apply volume. Leave this on for most replacements.'), style='PanelMuted.TLabel', wraplength=620).pack(anchor='w', pady=(5, 14))
        self.section(self.more, tr('Trim replacement audio'), 'scissors', panel=True).pack(anchor='w')
        trim = ttk.Frame(self.more, style='Panel.TFrame'); trim.pack(fill='x', pady=8)
        for text, variable in [('Start (seconds)', self.start), ('End (seconds)', self.end)]:
            ttk.Label(trim, text=tr(text), style='Panel.TLabel').pack(side='left')
            ttk.Entry(trim, textvariable=variable, width=8).pack(side='left', padx=(6, 14))
        self.trim_button = self.button(self.more, tr('Save trimmed copy'), self.trim, icon='scissors'); self.trim_button.pack(anchor='w')
        ttk.Label(self.more, text=tr('Keeps your input file intact. Undo restores the previous assignment.'), style='PanelMuted.TLabel', wraplength=620).pack(anchor='w', pady=(6, 14))
        actions = ttk.Frame(self.more, style='Panel.TFrame'); actions.pack(fill='x')
        self.mute_button = self.button(actions, tr('Mute sound'), lambda: self.sound_edit('silence'), role='danger', icon='volume'); self.mute_button.pack(side='left')
        self.restore_button = self.button(actions, tr('Restore original'), self.restore, icon='undo'); self.restore_button.pack(side='left', padx=8)
        self.wav_button = self.button(self.more, tr('Export original WAV'), self.export_wav, role='export', icon='export'); self.wav_button.pack(anchor='w', pady=(12, 16))
        ttk.Label(self.more, text=tr('Sound display name'), style='Panel.TLabel').pack(anchor='w')
        ttk.Entry(self.more, textvariable=self.label).pack(fill='x', pady=(6, 8))
        self.rename_button = self.button(self.more, tr('Save display name'), self.rename, icon='save'); self.rename_button.pack(anchor='w')
        ttk.Label(self.more, text=tr('Local labels help you recognize sounds. They do not change game IDs.'), style='PanelMuted.TLabel', wraplength=620).pack(anchor='w', pady=(6, 14))
        ttk.Label(self.more, textvariable=self.detail, style='PanelMuted.TLabel', wraplength=620).pack(anchor='w')
        ttk.Label(self.more, textvariable=self.source_path, style='PanelMuted.TLabel', wraplength=620).pack(anchor='w', pady=(8, 0))

        footer = ttk.Frame(self); footer.grid(row=4, column=0, sticky='ew', pady=(10, 0))
        ttk.Label(footer, textvariable=self.next_step, font=('Segoe UI Semibold', 10), wraplength=900).pack(anchor='w', pady=(0, 6))
        info = ttk.Frame(footer); info.pack(fill='x')
        self.progress = ttk.Progressbar(info, mode='indeterminate', length=75); self.progress.pack(side='left', padx=(0, 10))
        self.status_label = ttk.Label(info, textvariable=self.status, style='Muted.TLabel', wraplength=700)
        self.status_label.pack(side='left', fill='x', expand=True)
        self.library_button = ui_polish.action_button(app, info, 'Add export to library', self.add_to_library, role='export', icon='mods', state='disabled')
        self.library_button.pack(side='right', padx=(8, 0))
        self.controls.append(self.library_button)
        info.bind('<Configure>', lambda e: self.status_label.configure(wraplength=max(120, e.width-320)))
        self.create_scan_overlay()
        def scroll(event):
            canvas.yview_scroll(-1 if getattr(event, 'num', None) == 4 else 1 if getattr(event, 'num', None) == 5 else (-1 if event.delta > 0 else 1), 'units')
            return 'break'
        def wire(widget):
            for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'): widget.bind(sequence, scroll)
            for child in widget.winfo_children(): wire(child)
        wire(detail)
        self.stop_button.state(['disabled'])
        self.sync_controls()
        self.after(80, self.poll); self.after(200, self.connect)

    def section(self, parent, text, icon, panel=False):
        image = nav_icons.make_icon(self.app, icon, self.app.theme['accent'])
        label = ttk.Label(parent, text='  ' + tr(text), image=image, compound='left',
                          style='Panel.TLabel' if panel else 'TLabel', font=('Segoe UI Semibold', 10))
        label._heading_icon = image
        return label

    def toggle_guide(self):
        if hasattr(self, 'show_guide'):
            self.show_guide(); return
        if self.guide.winfo_manager(): self.guide.grid_remove()
        else: self.guide.grid(row=5, column=0, sticky='ew', pady=(10, 0))

    def toggle_more(self):
        self.more_open = not self.more_open
        if self.more_open: self.more.pack(fill='x')
        else: self.more.pack_forget()

    def sync_controls(self):
        if self.busy: return
        ready = bool(self.backend and self.backend.session.stage == 'ready')
        project = bool(self.backend and self.backend.session.project)
        selected = self.sounds.selection()
        sid = selected[0] if selected else None
        row = next((r for r in self.rows if r['source'] == sid), None)
        available = ready and bool(row) and not row.get('absent')
        assigned = self.state['assignments'].get(sid)
        changed = bool(assigned or sid in self.state['gains'])
        states = [(self.original_button, available), (self.edited_button, available and changed),
                  (self.import_button, available and project), (self.volume_button, available and project and all(
                      not r.get('absent') for r in self.rows if r['source'] in selected)),
                  (self.mute_button, available and project), (self.restore_button, available and project and changed),
                  (self.trim_button, available and project and assigned and not assigned['silence']),
                  (self.wav_button, available), (self.rename_button, available),
                  (self.undo_button, self.state.get('can_undo')), (self.redo_button, self.state.get('can_redo')),
                  (self.build_button, project and bool(self.state['assignments'] or self.state['gains'])),
                  (self.library_button, bool(getattr(self, 'last_output', None)))]
        for button, enabled in states: button.state(['!disabled'] if enabled else ['disabled'])
        if not ready: self.next_step.set(tr('Getting your sound library ready. You can choose a game folder if automatic discovery fails.'))
        elif not available: self.next_step.set(tr('1 · Choose a collection, then click a sound to listen.'))
        elif not project: self.next_step.set(tr('2 · Like this sound? Click New audio mod to replace it or adjust its volume.'))
        elif not changed: self.next_step.set(tr('2 · Import replacement audio, or adjust Volume and click Apply volume.'))
        else: self.next_step.set(tr('3 · Play edited to check your change. Export mod ZIP when you’re ready.'))

    def after(self, ms, func=None, *args):
        if func is None: return super().after(ms)
        token = None
        def call():
            self.timer_ids.discard(token)
            func(*args)
        token = super().after(ms, call)
        self.timer_ids.add(token)
        return token

    def button(self, parent, text, command, style=None, role='secondary', icon=None):
        b = ui_polish.action_button(self.app, parent, text, command, role=role, icon=icon)
        if text not in ('Quick guide', 'More options: trim, mute & sound names'): self.controls.append(b)
        return b

    def create_scan_overlay(self):
        theme = self.app.theme
        style = self.app.style
        style.configure('AudioScan.Card.TFrame', background=theme['panel'], relief='flat')
        style.configure('AudioScan.Title.TLabel', background=theme['panel'], foreground=theme['text'],
                        font=('Segoe UI Semibold', 17))
        style.configure('AudioScan.Body.TLabel', background=theme['panel'], foreground=theme['muted'],
                        font=('Segoe UI', 10))
        style.configure('AudioScan.Value.TLabel', background=theme['panel'], foreground=theme['accent'],
                        font=('Segoe UI Semibold', 11))
        style.configure('AudioScan.Horizontal.TProgressbar', troughcolor=theme['panel2'],
                        background=theme['accent'], bordercolor=theme['panel2'], lightcolor=theme['accent'],
                        darkcolor=theme['accent'], thickness=10)
        self.scan_overlay = tk.Frame(self, bg=theme['bg'])
        self.scan_overlay.place_forget()
        card = ttk.Frame(self.scan_overlay, style='AudioScan.Card.TFrame', padding=(36, 30))
        card.place(relx=.5, rely=.5, anchor='center', relwidth=.68)
        ttk.Label(card, text=tr('AUDIO LIBRARY'), style='AudioScan.Value.TLabel').pack(anchor='w')
        ttk.Label(card, text=tr('Scanning your game data'), style='AudioScan.Title.TLabel').pack(anchor='w', pady=(9, 6))
        ttk.Label(card, text=tr('Reading audio archives and building your sound library. This may take a little while.'),
                  style='AudioScan.Body.TLabel', wraplength=540, justify='left').pack(anchor='w', pady=(0, 22))
        self.scan_bar = ttk.Progressbar(card, style='AudioScan.Horizontal.TProgressbar', mode='determinate', maximum=100)
        self.scan_bar.pack(fill='x')
        stats = ttk.Frame(card, style='AudioScan.Card.TFrame'); stats.pack(fill='x', pady=(10, 0))
        self.scan_detail = tk.StringVar(value=tr('Preparing archive scan…'))
        self.scan_percent = tk.StringVar(value='0%')
        ttk.Label(stats, textvariable=self.scan_detail, style='AudioScan.Body.TLabel').pack(side='left')
        ttk.Label(stats, textvariable=self.scan_percent, style='AudioScan.Value.TLabel').pack(side='right')

    def update_scan(self, current, total, detail):
        if total:
            percent = min(100, max(0, round(current * 100 / total)))
            display = f'{current:,} of {total:,} game archives'
        else:
            percent, display = (100 if current else 0), detail
        self.scan_bar.configure(maximum=100, value=percent)
        self.scan_percent.set(f'{percent}%')
        self.scan_detail.set(display)

    def perform(self, title, work, done=None, scan=False):
        if self.busy:
            return
        self.busy = True
        self.status.set(title)
        self.progress.start(15)
        if scan:
            theme = self.app.theme
            self.scan_overlay.configure(bg=theme['bg'])
            self.app.style.configure('AudioScan.Card.TFrame', background=theme['panel'])
            self.app.style.configure('AudioScan.Title.TLabel', background=theme['panel'], foreground=theme['text'])
            self.app.style.configure('AudioScan.Body.TLabel', background=theme['panel'], foreground=theme['muted'])
            self.app.style.configure('AudioScan.Value.TLabel', background=theme['panel'], foreground=theme['accent'])
            self.app.style.configure('AudioScan.Horizontal.TProgressbar', troughcolor=theme['panel2'],
                                     background=theme['accent'], bordercolor=theme['panel2'],
                                     lightcolor=theme['accent'], darkcolor=theme['accent'])
            self.scan_bar.configure(value=0)
            self.scan_percent.set('0%')
            self.scan_detail.set(tr('Preparing archive scan…'))
            self.scan_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.scan_overlay.lift()
        for button in self.controls:
            button.state(['disabled'])
        def worker():
            try:
                result, error = work(), None
            except Exception as exc:
                result, error = None, str(exc)
                if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
                    error += ': ' + exc.stderr.decode(errors='replace')[-350:]
            self.results.put((result, error, done))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        while True:
            try:
                update = self.scan_updates.get_nowait()
            except queue.Empty:
                break
            self.update_scan(*update)
        try:
            result, error, done = self.results.get_nowait()
        except queue.Empty:
            if self.busy and self.backend and self.backend.session.stage not in ('ready', 'failed', 'starting'):
                self.status.set(self.backend.session.stage)
        else:
            self.busy = False
            self.progress.stop()
            self.scan_overlay.place_forget()
            for button in self.controls:
                button.state(['!disabled'])
            if error:
                self.status.set(tr('Could not complete operation: ') + error)
            else:
                self.status.set(tr('Ready. Audio project edits save automatically.') if self.backend and self.backend.session.project else tr('Ready. Create a project to save audio edits.'))
                if done:
                    try:
                        done(result)
                    except Exception as exc:
                        self.status.set(str(exc))
        if not self.busy and self.pending_navigation:
            navigation, self.pending_navigation = self.pending_navigation, None
            if navigation == 'item': self.select_item()
            else: self.select_sound()
        if not self.busy:
            self.stop_button.state(['disabled'])
        self.sync_controls()
        self.after(80, self.poll)

    def connect(self, folder=None, rescan=False):
        if self.busy: return
        # The deployment target is the default audio source. Do not silently build
        # Steam banks for a HellForge deployment (or retain a previously scanned copy).
        configured = core.game_dir(self.app.cfg) if self.app.cfg.get('game') else None
        if folder is None and configured is not None and (configured / 'data').is_dir():
            loaded = getattr(getattr(self.backend, 'session', None), 'ix', None)
            if loaded is None or loaded.game.data.resolve() != (configured / 'data').resolve():
                folder = str(configured)
        def work():
            if self.backend is None:
                self.backend = AudioBackend(core.APP_DATA / 'audio-workspace')
                self.app._audio_backend = self.backend
            if folder or rescan or self.backend.session.stage != 'ready':
                return self.backend.load(folder or None, progress=lambda current, total, detail: self.scan_updates.put((current, total, detail)))
            return self.backend.categories()
        def done(categories):
            self.categories = categories
            s = self.backend.session
            self.game_label.set(tr('Game connected · Sound library ready'))
            self.source_path.set(tr('Game files: ') + str(s.ix.game.data))
            self.populate_library()
            self.refresh_state()
            self.status.set(tr('Your game audio is ready. Start with a category on the left.'))
        self.perform(tr('Discovering installed game and indexing audio…'), work, done, scan=True)

    def choose_game(self):
        if self.busy: return
        folder = filedialog.askdirectory(parent=self, title=tr('Choose Helldivers 2 or HellForge installation folder'))
        if folder: self.connect(folder)

    def defer_search(self):
        if self.search_timer: self.after_cancel(self.search_timer)
        self.search_timer = self.after(160, self.populate_library)

    def populate_library(self):
        self.search_timer = None
        previous = self.browser.selection()
        self.browser.delete(*self.browser.get_children())
        self.items = {}
        words = self.search.get().casefold().split()
        for c in self.categories:
            for sec in c['sections']:
                for item in sec['items']:
                    path = f"{c['name']} {sec['name']} {item['name']} {item['id']}".casefold()
                    if not all(w in path for w in words): continue
                    cid, section = 'c:' + c['id'], 'g:' + sec['id']
                    if not self.browser.exists(cid): self.browser.insert('', 'end', iid=cid, text=c['name'], open=bool(words))
                    if not self.browser.exists(section): self.browser.insert(cid, 'end', iid=section, text=sec['name'], open=bool(words))
                    iid = item['id']
                    self.items[iid] = (item, f"{c['name']}  ›  {sec['name']}  ›  {item['name']}")
                    self.browser.insert(section, 'end', iid=iid, text=item['name'])
        if previous and self.browser.exists(previous[0]): self.browser.selection_set(previous[0])

    def select_item(self, event=None):
        selected = self.browser.selection()
        if self.busy:
            self.pending_navigation = 'item'
            return
        if not selected or selected[0] not in self.items: return
        iid = selected[0]
        self.stop()
        self.crumb.set(self.items[iid][1])
        self.perform(tr('Reading sounds in ') + self.items[iid][0]['name'] + '…', lambda: self.backend.sounds(iid), self.loaded_sounds)

    def loaded_sounds(self, rows):
        self.rows = rows
        self.refresh_state()
        self.populate_sounds()
        self.heading.set(tr('Choose a sound'))
        self.detail.set(tr('Select a row to preview or replace it. Shared sounds may affect more than one collection.'))
        self.wave.delete('all')
        self.peaks = None

    def populate_sounds(self):
        previous = self.sounds.selection()
        self.sounds.delete(*self.sounds.get_children())
        words = self.sound_search.get().casefold().split()
        assignments, gains = self.state['assignments'], self.state['gains']
        for row in self.rows:
            sid = row['source']
            changed = sid in assignments or sid in gains
            if self.edited_only.get() and not changed: continue
            name = self.backend.labels.get(sid) or row['name']
            if not all(w in f"{name} {row['group']} {sid}".casefold() for w in words): continue
            assignment = assignments.get(sid)
            status = 'Unavailable' if row.get('absent') else 'Muted' if assignment and assignment['silence'] else 'Replaced' if assignment else 'Gain' if sid in gains else 'Original'
            ms = row.get('duration_ms')
            self.sounds.insert('', 'end', iid=sid, values=(name, f'{ms/1000:.2f} s' if ms else '—', tr(status)))
        count = len(self.sounds.get_children())
        self.count_label.configure(text=tr('{count} sounds shown · {edited} edited').format(count=count, edited=sum(r['source'] in assignments or r['source'] in gains for r in self.rows)))
        if count: self.empty.place_forget()
        else:
            self.empty.configure(text=tr('No sounds match these filters.') if self.rows else tr('Choose a collection above.\nIts sounds will appear here.'))
            self.empty.place(relx=.5, rely=.45, anchor='center')
        remaining = [sid for sid in previous if self.sounds.exists(sid)]
        if remaining: self.sounds.selection_set(remaining)

    def current(self, project=False):
        if self.busy: return None
        if not self.backend or self.backend.session.stage != 'ready':
            self.status.set(tr('Connect your installed game first.')); return None
        if project and not self.backend.session.project:
            self.status.set(tr('Create or open an audio project before editing.')); return None
        selected = self.sounds.selection()
        if not selected:
            self.status.set(tr('Select a sound first.')); return None
        row = next((r for r in self.rows if r['source'] == selected[0]), None)
        if row and row.get('absent'):
            self.status.set(tr('This sound is named by the game but its audio is not installed.')); return None
        return row

    def select_sound(self, event=None):
        if self.busy:
            if self.pending_navigation != 'item': self.pending_navigation = 'sound'
            return
        row = self.current()
        if not row: return
        self.stop()
        sid = row['source']
        name = self.backend.labels.get(sid) or row['name']
        self.heading.set(name); self.label.set(name)
        shared = row.get('banks', 0)
        self.selection_note.set(tr('Shared sound · Changes may also be heard in other collections.') if shared else tr('Listen to the original, then import your own audio or adjust its volume.'))
        count = len(self.sounds.selection())
        if count > 1:
            self.selection_note.set(tr('{count} sounds selected · Apply volume sets the same dB value on all selected sounds. Other actions use the first selected sound.').format(count=count))
        self.detail.set(f"{row['group']}\nSound ID: {sid}\nShared with {row.get('banks', 0)} other sound banks." + ('\n' + row['note'] if row.get('note') else ''))
        a = self.state['assignments'].get(sid)
        self.file_label.set(tr('Replacement: ') + a['name'] if a else tr('Using the original game sound. Import a file to replace it.'))
        self.gain.set(str(a['gain_db'] if a else self.state['gains'].get(sid, 0)))
        self.volume_slider.set(max(-24, min(12, float(self.gain.get()))))
        self.timing.set(a['fit_timing'] if a else True)
        self.start.set('0'); self.end.set(str(round(a['duration_ms']/1000, 3)) if a and a.get('duration_ms') else '')
        self.sync_controls()
        self.preview('original', False)

    @staticmethod
    def clock_text(seconds):
        minutes, rest = divmod(max(0, seconds), 60)
        return f'{int(minutes)}:{rest:05.2f}'

    def draw_wave(self):
        self.wave.delete('all')
        w, h = self.wave.winfo_width(), self.wave.winfo_height()
        for fraction in (.25, .5, .75):
            self.wave.create_line(w*fraction, 10, w*fraction, h-10, fill=self.app.theme['panel2'], dash=(2, 5))
        self.wave.create_line(0, h/2, w, h/2, fill=self.app.theme['panel2'])
        if not self.peaks:
            self.wave.create_text(w/2, h/2, text=tr('Select a sound to see its waveform'), fill=self.app.theme['muted'], font=('Segoe UI', 11))
            return
        values = self.peaks['peaks']; full = self.peaks.get('full', 255)
        display_full = max(full*.125, min(full, max(values, default=0)*1.3))
        for i, value in enumerate(values):
            x, y = 8+i*(w-16)/max(1, len(values)), max(1, value/display_full*(h/2-16))
            self.wave.create_line(x, h/2-y, x, h/2+y, fill=self.app.theme['accent'])
        self.draw_playhead()

    def draw_playhead(self):
        w, h = self.wave.winfo_width(), self.wave.winfo_height()
        fraction = min(1.0, self.play_position/self.play_duration) if self.play_duration else 0
        x = 8+fraction*max(0, w-16)
        self.wave.delete('playhead')
        if self.peaks:
            self.wave.create_line(x, 0, x, h, fill=self.app.theme['bg'], width=5, tags='playhead')
            self.wave.create_line(x, 0, x, h, fill='#73d8ff', width=2, tags='playhead')
            self.wave.create_polygon(x-5, 1, x+5, 1, x, 8, fill='#73d8ff', tags='playhead')
        self.elapsed.set(self.clock_text(self.play_position) + ' / ' + self.clock_text(self.play_duration))

    def start_playback_clock(self, duration):
        if self.playback_timer:
            self.after_cancel(self.playback_timer)
            self.timer_ids.discard(self.playback_timer)
        self.play_duration = max(0, duration)
        self.play_position = 0.0
        self.play_started = time.monotonic()
        self.stop_button.state(['!disabled'])
        self.tick_playback()

    def tick_playback(self):
        self.playback_timer = None
        if self.play_started is None: return
        self.play_position = min(self.play_duration, max(0, time.monotonic()-self.play_started))
        self.draw_playhead()
        if self.play_position >= self.play_duration:
            self.play_started = None
            self.stop_button.state(['disabled'])
        else:
            self.playback_timer = self.after(30, self.tick_playback)

    def preview(self, side, play):
        row = self.current()
        if not row: return
        sid = row['source']
        self.stop()
        request = self.preview_request
        def done(result):
            if request != self.preview_request: return
            path, self.peaks = result
            self.active_side = side
            self.play_duration = self.peaks['duration_ms']/1000
            self.play_position = 0
            self.draw_wave()
            self.wave_label.configure(text=tr('{side} audio · {seconds} seconds').format(side=tr(side.title()), seconds=f'{self.play_duration:.2f}'))
            if play:
                if os.name == 'nt':
                    import winsound
                    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
                else:
                    player = shutil.which('ffplay')
                    if not player: raise ValueError('Install ffplay for audio playback on Linux. WAV export is available.')
                    self.player = subprocess.Popen([player, '-nodisp', '-autoexit', '-loglevel', 'error', str(path)])
                self.start_playback_clock(self.play_duration)
        self.perform(tr('Preparing ') + side + tr(' audio…'), lambda: self.backend.preview(sid, side), done)

    def stop(self):
        self.preview_request += 1
        if os.name == 'nt':
            import winsound
            winsound.PlaySound(None, 0)
        if self.player and self.player.poll() is None: self.player.terminate()
        self.player = None
        if self.playback_timer:
            self.after_cancel(self.playback_timer)
            self.timer_ids.discard(self.playback_timer)
            self.playback_timer = None
        self.play_started = None
        self.play_position = 0
        if hasattr(self, 'stop_button'): self.stop_button.state(['disabled'])
        if hasattr(self, 'wave'): self.draw_playhead()

    def refresh_state(self, state=None):
        self.state = state or self.backend.state()
        if 'name' in self.state:
            self.name.set(self.state['name'])
            count = len(self.state['assignments']) + len(self.state['gains'])
            self.project_label.set(f"{self.state['name']}  ·  {count} edits  ·  Saved automatically")
        self.populate_sounds()
        self.sync_controls()

    def new_project(self):
        if self.busy or not self.backend: return
        path = filedialog.asksaveasfilename(parent=self, title=tr('Save new audio project'), defaultextension='.audi', filetypes=[('Audio project', '*.audi')], initialfile='My Audio Mod.audi')
        if not path: return
        name = self.name.get().strip() or Path(path).stem
        def work():
            s = self.backend.session
            self.backend.check_destination(path)
            s.new_project(str(Path(path).resolve()), name)
            # Package ModDiver's own badge with the project for portable exports.
            from PIL import Image
            target = s.project.path.parent / (s.project.path.stem + '-icon.png')
            Image.open(Path(__file__).parent / 'branding' / 'icon_256.png').convert('RGBA').resize((540, 540)).save(target)
            s.set_icon(str(target.resolve()))
            return s.project_state()
        self.perform(tr('Creating project…'), work, self.refresh_state)

    def open_project(self):
        if self.busy or not self.backend: return
        path = filedialog.askopenfilename(parent=self, title=tr('Open audio project'), filetypes=[('Audio project', '*.audi')])
        if path:
            def work():
                self.backend.check_destination(path)
                return self.backend.session.open_project(path)
            self.perform(tr('Opening project…'), work, self.refresh_state)

    def edit(self, method):
        if not self.backend or not self.backend.session.project: return
        self.perform(tr('Saving edit…'), lambda: getattr(self.backend.session, method)(), self.refresh_state)

    def assign(self):
        row = self.current(True)
        if not row: return
        path = filedialog.askopenfilename(parent=self, title=tr('Choose replacement audio'), filetypes=[('Audio files', '*.wav *.mp3 *.flac *.ogg *.opus *.m4a *.aac *.aif *.aiff *.wma *.wem'), ('All files', '*.*')])
        if not path: return
        sid, label = row['source'], self.label.get()
        self.perform(tr('Importing replacement audio…'), lambda: self.backend.assign(sid, path, label), self.edit_done)

    def edit_done(self, state):
        self.refresh_state(state)
        self.select_sound()

    def apply_gain(self):
        row = self.current(True)
        if not row: return
        selected = list(self.sounds.selection())
        if any(r.get('absent') for r in self.rows if r['source'] in selected):
            self.status.set(tr('Some selected sounds are not installed. Deselect them before applying volume.'))
            return
        if len(selected) > 1:
            gain = self.gain.get()
            self.perform(tr('Saving volume for selected sounds…'),
                         lambda: self.backend.edit_volume_many(selected, gain), self.refresh_state)
            return
        sid, gain, timing = row['source'], self.gain.get(), self.timing.get()
        self.perform(tr('Saving gain and timing…'), lambda: self.backend.edit_settings(sid, gain, timing), self.refresh_state)

    def sound_edit(self, method):
        row = self.current(True)
        if row: self.perform(tr('Saving sound edit…'), lambda: getattr(self.backend.session, method)([row['source']]), self.edit_done)

    def restore(self):
        row = self.current(True)
        if row: self.perform(tr('Restoring original…'), lambda: self.backend.restore(row['source']), self.edit_done)

    def rename(self):
        row = self.current()
        if not row: return
        sid, label = row['source'], self.label.get().strip()
        if not label: self.status.set(tr('Enter a display name first.')); return
        def done(_):
            self.heading.set(label); self.populate_sounds()
            self.status.set(tr('Sound name saved locally. Names are shared across your projects.'))
        self.perform(tr('Saving sound name…'), lambda: self.backend.rename(sid, label), done)

    def trim(self):
        row = self.current(True)
        if not row: return
        sid, start, end = row['source'], self.start.get(), self.end.get()
        self.perform(tr('Saving trimmed audio copy…'), lambda: self.backend.trim(sid, start, end), self.edit_done)

    def export_wav(self):
        row = self.current()
        if not row: return
        path = filedialog.asksaveasfilename(parent=self, title=tr('Export original sound'), defaultextension='.wav', initialfile='original-sound.wav', filetypes=[('WAV audio', '*.wav')])
        if not path: return
        def work():
            self.backend.check_destination(path)
            return shutil.copyfile(self.backend.session.vanilla_wav(int(row['source'])), path)
        self.perform(tr('Extracting original sound…'), work, lambda _: self.status.set(tr('Original WAV exported: ') + path))

    def build(self):
        if hasattr(self, 'finish_export'):
            self.finish_export(); return
        if self.busy or not self.backend or not self.backend.session.project:
            self.status.set(tr('Create or open a project and edit a sound first.')); return
        folder = filedialog.askdirectory(parent=self, title=tr('Choose folder for exported mod ZIP'))
        if not folder: return
        name = self.name.get().strip()
        def work():
            s = self.backend.session
            s.settings(name=name, build_folder=folder)
            return s.build()
        def started(job):
            self.build_job = job['id']
            self.busy = True
            for button in self.controls: button.state(['disabled'])
            self.progress.start(15)
            self.after(150, self.poll_build)
        self.perform(tr('Preparing verified audio mod…'), work, started)

    def poll_build(self):
        job = self.backend.session.job(self.build_job)
        self.status.set(job.get('doing') or tr('Building and verifying audio archives…'))
        if job['state'] == 'running':
            self.after(150, self.poll_build); return
        self.busy = False; self.progress.stop()
        for button in self.controls: button.state(['!disabled'])
        self.refresh_state()
        if job['state'] == 'done':
            output = job['result']['zip']
            self.status.set(tr('Verified mod ZIP saved: ') + output)
            self.last_output = output
            self.library_button.state(['!disabled'])
        else:
            self.status.set(tr('Build failed: ') + str(job.get('error') or job['state']))

    def add_to_library(self):
        if self.busy or not getattr(self, 'last_output', None): return
        self.app._add_paths([self.last_output])
        self.status.set(tr('Audio mod imported into the Mod Library. Use Merge and Install All to deploy.'))

    def destroy(self):
        self.stop()
        for token in list(self.timer_ids):
            self.after_cancel(token)
        self.timer_ids.clear()
        # Cancel Tcl callbacks explicitly; workers only write to a Python queue.
        super().destroy()
