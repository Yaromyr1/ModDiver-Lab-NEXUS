"""A guided finishing step shared by the audio and visual workspaces."""
import copy
from pathlib import Path
import queue
import tempfile
import threading
import tkinter as tk
from tkinter import ttk
import uuid

import core
from localization import tr
from panel_dialogs import filedialog
import studio_export
import ui_polish


class Finish(ttk.Frame):
    def __init__(self, parent, studio):
        super().__init__(parent)
        self.studio, self.app, self.busy = studio, studio.app, False
        self.files, self.available = [], (False, False)
        self.results = queue.Queue()
        self.columnconfigure(0, weight=1); self.rowconfigure(0, weight=1)
        canvas = tk.Canvas(self, background=self.app.theme['bg'], highlightthickness=0)
        self.canvas = canvas
        canvas.configure(yscrollincrement=24)
        canvas.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(self, command=canvas.yview); scroll.grid(row=0, column=1, sticky='ns')
        canvas.configure(yscrollcommand=scroll.set)
        body = ttk.Frame(canvas, padding=22); body.columnconfigure(0, weight=1)
        window = canvas.create_window(0, 0, anchor='nw', window=body)
        body.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        def resize(event):
            canvas.itemconfigure(window, width=event.width)
            for widget in self.winfo_children():
                if isinstance(widget, ttk.Label): widget.configure(wraplength=max(200,event.width-44))
            for widget in body.winfo_children():
                if isinstance(widget, ttk.Label): widget.configure(wraplength=max(200,event.width-44))
        canvas.bind('<Configure>', resize)
        self.app.style.configure('Studio.Panel.TCheckbutton', background=self.app.theme['panel'], foreground=self.app.theme['text'])
        self.app.style.map('Studio.Panel.TCheckbutton', background=[('active',self.app.theme['panel'])],
                           foreground=[('disabled',self.app.theme['muted'])])
        self.name = tk.StringVar(value='My finished mod')
        self.description = tk.StringVar()
        self.audio, self.visual = tk.BooleanVar(), tk.BooleanVar()
        self.add_library = tk.BooleanVar(value=True)
        self.summary, self.status = tk.StringVar(), tk.StringVar(value=tr('Choose your content, name the mod, then export.'))
        ttk.Label(body, text=tr('Finish your mod'), style='Title.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(body, text=tr('Audio, visuals, or both. One ZIP to import and enable in a compatible HD2 mod manager.'),
                  style='Muted.TLabel', wraplength=900).grid(row=1, column=0, sticky='ew', pady=(7, 18))
        content = ttk.Frame(body, style='Panel.TFrame', padding=16)
        content.grid(row=2, column=0, sticky='ew')
        ttk.Label(content, text=tr('01  INCLUDE YOUR CONTENT'), style='Panel.TLabel', font=('Segoe UI Semibold',10)).pack(anchor='w',pady=(0,12))
        self.audio_choice = ttk.Checkbutton(content, text=tr('Current audio project'), variable=self.audio, style='Studio.Panel.TCheckbutton')
        self.audio_choice.pack(anchor='w')
        self.visual_choice = ttk.Checkbutton(content, text=tr('Current visual replacements'), variable=self.visual, style='Studio.Panel.TCheckbutton')
        self.visual_choice.pack(anchor='w', pady=(6, 8))
        ttk.Label(content, textvariable=self.summary, style='PanelMuted.TLabel', wraplength=880).pack(anchor='w', pady=(0, 8))
        row = ttk.Frame(content, style='Panel.TFrame'); row.pack(fill='x')
        self.files_label = ttk.Label(row, text=tr('No extra ZIPs added'), style='PanelMuted.TLabel',wraplength=350)
        self.files_label.pack(side='left', fill='x', expand=True)
        ttk.Button(row, text=tr('Add finished ZIPs…'), command=self.add_files).pack(side='right')
        ttk.Button(row, text=tr('Clear extra ZIPs'), command=self.clear_files).pack(side='right', padx=8)
        meta = ttk.Frame(body, style='Panel.TFrame', padding=16)
        meta.grid(row=3, column=0, sticky='ew', pady=14); meta.columnconfigure(1, weight=1)
        ttk.Label(meta,text=tr('02  NAME AND REVIEW'),style='Panel.TLabel',font=('Segoe UI Semibold',10)).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,12))
        ttk.Label(meta, text=tr('Mod name'),style='Panel.TLabel').grid(row=1, column=0, sticky='w', padx=(0, 14))
        ttk.Entry(meta, textvariable=self.name).grid(row=1, column=1, sticky='ew')
        ttk.Label(meta, text=tr('Description'),style='Panel.TLabel').grid(row=2, column=0, sticky='w', pady=10)
        ttk.Entry(meta, textvariable=self.description).grid(row=2, column=1, sticky='ew', pady=10)
        self.target = tk.StringVar()
        ttk.Label(meta, textvariable=self.target, style='PanelMuted.TLabel', wraplength=880).grid(row=3, column=0, columnspan=2, sticky='w')
        ttk.Checkbutton(body, text=tr('Add the finished ZIP to Mod Library after export'), variable=self.add_library).grid(row=4, column=0, sticky='w')
        row = ttk.Frame(self, padding=(22,12)); row.grid(row=1, column=0, sticky='ew')
        self.export_button = ui_polish.action_button(self.app, row, 'Export finished mod ZIP', self.export, role='export', icon='export')
        self.export_button.pack(side='left')
        self.progress = ttk.Progressbar(row, mode='indeterminate', length=130)
        ttk.Label(self, textvariable=self.status, wraplength=900,padding=(22,0,22,14)).grid(row=2, column=0, sticky='ew')
        ttk.Label(body, text=tr('The ZIP includes installable patches, matching sidecars and a manager manifest. '
                  'No loader is needed for these resource replacements. Existing game files are never edited by export. '
                  'Extra ZIPs use their default options; export one variant first if you need another.'),
                  style='Muted.TLabel', wraplength=900).grid(row=7, column=0, sticky='ew', pady=(12, 0))
        for variable in (self.audio, self.visual, self.name):
            variable.trace_add('write', lambda *_: self.update_export_state())
        self.update_export_state()

    def update_export_state(self):
        enabled = not self.busy and self.name.get().strip() and (self.audio.get() or self.visual.get() or self.files)
        self.export_button.state(['!disabled'] if enabled else ['disabled'])

    def refresh(self):
        if self.busy: return
        audio = self.studio.audio
        has_audio = bool(audio.backend and audio.backend.session.stage == 'ready' and audio.backend.session.project and
                         (audio.state.get('assignments') or audio.state.get('gains')))
        has_visual = bool(self.studio.native.project and self.studio.native.project.changed)
        for i, (present, variable, widget) in enumerate(((has_audio, self.audio, self.audio_choice),
                                                        (has_visual, self.visual, self.visual_choice))):
            if present and not self.available[i]: variable.set(True)
            if not present: variable.set(False)
            widget.state(['!disabled'] if present else ['disabled'])
        self.available = has_audio, has_visual
        self.summary.set(tr('Audio edits: {audio}  ·  Visual replacements: {visual}').format(
            audio=len(audio.state.get('assignments', {}))+len(audio.state.get('gains', {})),
            visual=sum(len({i for i, _ in a.replacements}) for a in self.studio.native.project.archives) if has_visual else 0))
        self.target.set(tr('Target: ') + ('HellForge' if core.hellforge_root(self.app.cfg) else 'Steam / regular HD2') +
                        '  ·  ' + str(core.game_dir(self.app.cfg)))
        if self.name.get() == 'My finished mod' and has_audio: self.name.set(audio.name.get())
        self.update_export_state()

    def add_files(self):
        if self.busy: return
        paths = filedialog.askopenfilenames(parent=self, title=tr('Add completed audio / visual exports'), filetypes=[('Finished mod ZIPs', '*.zip')])
        self.files = list(dict.fromkeys([*self.files, *(str(Path(p).resolve()) for p in paths)]))
        self.files_label.configure(text=tr('{count} extra ZIPs · ').format(count=len(self.files)) + ', '.join(Path(p).name for p in self.files))
        self.update_export_state()

    def clear_files(self):
        if self.busy: return
        self.files.clear(); self.files_label.configure(text=tr('No extra ZIPs added'))
        self.update_export_state()

    def export(self):
        if self.busy or self.studio.audio.busy or self.studio.native.busy: return
        if not self.audio.get() and not self.visual.get() and not self.files:
            self.status.set(tr('Include an edited project or add a completed audio/visual ZIP first.')); return
        if not self.name.get().strip(): self.status.set(tr('Enter a mod name.')); return
        filename = filedialog.asksaveasfilename(parent=self, title=tr('Export finished mod'),
            initialfile=self.name.get()+'.zip', defaultextension='.zip', filetypes=[('Manager-ready mod ZIP', '*.zip')])
        if not filename: return
        destination = Path(filename).resolve()
        if destination.suffix.lower() != '.zip':
            self.status.set(tr('Use a .zip filename for a manager-ready mod.')); return
        game = core.game_dir(self.app.cfg).resolve()
        if destination.is_relative_to(game) or destination in {Path(p).resolve() for p in self.files}:
            self.status.set(tr('Export outside the game folder and keep source ZIPs intact.')); return
        audio, visual = self.studio.audio, self.studio.native
        try:
            if self.audio.get():
                audio.backend.check_destination(filename)
                if audio.backend.session.ix.game.data.resolve() != (game/'data').resolve():
                    raise ValueError('Audio is loaded from another game copy. Change its game folder to match the export target first.')
            if self.visual.get(): visual.project.check_output(filename)
        except (OSError, ValueError) as exc: self.status.set(str(exc)); return
        include_audio = self.audio.get()
        native = copy.deepcopy(visual.project) if self.visual.get() else None
        inputs, name, description, add = list(self.files), self.name.get(), self.description.get(), self.add_library.get()
        target = 'HellForge' if core.hellforge_root(self.app.cfg) else 'Steam / regular HD2'
        identity = (audio.backend.session.project.guid if include_audio else
                    str(native.source.resolve()) if native else '|'.join(sorted(inputs)))
        guid = str(uuid.uuid5(uuid.NAMESPACE_URL, 'moddiver-studio:'+identity+'\0'+name.strip()))
        self.busy = audio.busy = visual.busy = True
        for button in audio.controls: button.state(['disabled'])
        self.export_button.state(['disabled']); self.progress.pack(side='left',padx=16); self.progress.start(15)
        self.status.set(tr('Building and checking your finished mod…'))
        def work():
            try:
                sources = []
                with tempfile.TemporaryDirectory(prefix='moddiver-finished-') as temp:
                    if include_audio:
                        from audioStudio.project import Project
                        from audioStudio.build import build
                        session = audio.backend.session
                        with session.lock:
                            session.flush()
                            snapshot = Project.from_json(session.project.to_json(), session.project.path)
                        output = build(snapshot, session.ix, out_dir=Path(temp)/'audio', log=lambda *_: None)
                        sources.append(('Audio project', studio_export.zip_patches(output)))
                    if native: sources.append(('Visual project', studio_export.visual_patches(native)))
                    for path in inputs: sources.append((Path(path).name, studio_export.zip_patches(path)))
                    output = studio_export.export(destination, name, sources, description=description,
                        target=target, guid=guid, icon=core.ROOT/'branding/icon_256.png')
                self.results.put((output, None))
            except Exception as exc: self.results.put((None, str(exc)))
        threading.Thread(target=work, daemon=True).start()
        def poll():
            try: output, error = self.results.get_nowait()
            except queue.Empty: self.after(80, poll); return
            self.busy = audio.busy = visual.busy = False
            self.progress.stop(); self.progress.pack_forget(); self.update_export_state(); audio.sync_controls()
            if error: self.status.set(error); return
            audio.last_output = str(output); audio.sync_controls()
            if native: visual.saved_revision = native.revision
            self.status.set(tr('Finished mod saved: ') + str(output) + tr(' · Import and enable this ZIP in your mod manager.'))
            if add: self.app._add_paths([str(output)])
        self.after(80, poll)
