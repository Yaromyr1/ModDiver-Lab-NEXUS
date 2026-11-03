"""Dedicated visual/audio creator UI; native resource metadata stays with payloads."""
import threading
import queue
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from panel_dialogs import filedialog, messagebox
from choice_screen import ChoiceScreen

from asset_mods import Project, kind
from localization import tr


class NativeEditor(ttk.Frame):
    def __init__(self, app, parent):
        super().__init__(parent)
        self.app, self.project = app, None
        self.results = queue.Queue()
        self.poll_token = self.after(80, self._poll_results)
        self.busy = False
        self.saved_revision = -1
        self.columnconfigure(0, weight=1); self.rowconfigure(3, weight=1)
        bar = ttk.Frame(self, padding=12); bar.grid(row=0, column=0, sticky='ew')
        for label, command in [('Open mod ZIP / archive', self.open), ('Replace from donor mod', self.donor),
                               ('Export mod ZIP', self.export)]:
            ttk.Button(bar, text=tr(label), command=command).pack(side='left', padx=(0, 8))
        ttk.Label(self, text=tr('Replace textures and sounds using native game resources. Open a source mod, select a resource, then copy a matching resource from a donor mod or import an edited native bundle.'),
                  wraplength=950).grid(row=1, column=0, sticky='ew', padx=16)
        controls = ttk.Frame(self, padding=12); controls.grid(row=2, column=0, sticky='ew')
        self.name = tk.StringVar(value='My Visual & Audio Mod')
        ttk.Label(controls, text=tr('Mod name')).pack(side='left')
        ttk.Entry(controls, textvariable=self.name, width=34).pack(side='left', padx=8)
        self.filter = tk.StringVar()
        ttk.Label(controls, text=tr('Search hash / type')).pack(side='left', padx=(16, 4))
        ttk.Entry(controls, textvariable=self.filter).pack(side='left', fill='x', expand=True)
        self.filter.trace_add('write', lambda *_: self.populate())
        pane = ttk.Frame(self, padding=(12, 0)); pane.grid(row=3, column=0, sticky='nsew')
        pane.columnconfigure(0, weight=1); pane.rowconfigure(0, weight=1)
        self.tree = self.make_tree(pane)
        self.tree.bind('<<TreeviewSelect>>', self.selected)
        self.detail = ttk.Label(self, text=tr('Open a mod ZIP or main archive. Keep .stream and .gpu_resources beside a loose archive.'), wraplength=950)
        self.detail.grid(row=4, column=0, sticky='ew', padx=16, pady=10)
        buttons = ttk.Frame(self, padding=12); buttons.grid(row=5, column=0, sticky='ew')
        for label, command in [('Export native asset bundle', self.export_bundle),
                               ('Import native asset bundle', self.import_bundle), ('Restore selected', self.restore)]:
            ttk.Button(buttons, text=tr(label), command=command).pack(side='left', padx=(0, 8))
        ttk.Label(self, text=tr('Native bundles contain main.bin, stream.bin, gpu.bin and resource.json. Keep metadata and encoded payloads compatible. Use Audio studio for WAV/MP3 imports. PNG/JPG/DDS textures require conversion with texture authoring tools before native import.'),
                  style='Muted.TLabel', wraplength=950).grid(row=6, column=0, sticky='ew', padx=16, pady=(0, 12))
        self.status = ttk.Label(self, text='', style='Muted.TLabel')
        self.status.grid(row=7, column=0, sticky='w', padx=16, pady=(0, 12))
    @staticmethod
    def make_tree(parent):
        tree = ttk.Treeview(parent, columns=('archive', 'kind', 'hash', 'size', 'edited'), show='headings', selectmode='browse')
        for column, title, width in [('archive','Archive',210), ('kind','Resource type',150), ('hash','Resource hash',155),
                                     ('size','Main / stream / GPU bytes',220), ('edited','Edited',60)]:
            tree.heading(column, text=tr(title)); tree.column(column, width=width)
        tree.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(parent, command=tree.yview); scroll.grid(row=0, column=1, sticky='ns')
        tree.configure(yscrollcommand=scroll.set)
        return tree

    def attempt(self, work):
        if self.busy: return
        try:
            return work()
        except Exception as exc:
            messagebox.showerror(tr('Visual & Audio Mod Creator'), str(exc), parent=self)

    def run(self, work, done):
        if self.busy: return
        self.busy = True
        self.app._begin_loading(self, self)
        def worker():
            try: result, error = work(), None
            except Exception as exc: result, error = None, str(exc)
            self.results.put((done, result, error))
        threading.Thread(target=worker, daemon=True).start()

    def _poll_results(self):
        try:
            done, result, error = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.app._end_loading(self)
            if error:
                messagebox.showerror('Visual assets', error, parent=self)
            else:
                self.attempt(lambda: done(result))
        self.poll_token = self.after(80, self._poll_results)

    def confirm_discard(self):
        return not self.has_unsaved_changes() or messagebox.askyesno(
            tr('Unsaved replacements'), tr('Discard staged replacements?'), parent=self)

    def has_unsaved_changes(self):
        return bool(self.project and self.project.changed and self.project.revision != self.saved_revision)

    def close(self):
        if self.busy: return
        if self.confirm_discard(): self.destroy()

    def open(self):
        if self.busy or not self.confirm_discard(): return
        filename = filedialog.askopenfilename(parent=self, title=tr('Open mod ZIP or main archive'),
                                             filetypes=[('Mod ZIP / archive','*')])
        if filename:
            def done(project):
                self.project = project
                self.saved_revision = -1
                self.populate()
                self.status.configure(text=f'{project.source.name} — {len(project.archives)} archive groups')
            self.run(lambda: Project.open(filename), done)

    def populate(self):
        previous = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        if not self.project: return
        for a, archive in enumerate(self.project.archives):
            for r in archive.resources:
                values = (archive.path.name, kind(r), f'{r.name_hash:016x}',
                          ' / '.join(str(len(archive.payload(r.index, s))) for s in range(3)),
                          tr('Yes') if any(i == r.index for i, _ in archive.replacements) else '')
                if self.filter.get().casefold() in ' '.join(values).casefold():
                    self.tree.insert('', 'end', iid=f'{a}:{r.index}', values=values)
        if previous and self.tree.exists(previous[0]): self.tree.selection_set(previous[0])

    def current(self):
        selected = self.tree.selection()
        if not self.project or not selected:
            raise ValueError(tr('Select a resource first.'))
        return tuple(map(int, selected[0].split(':')))

    def selected(self, event=None):
        if not self.tree.selection(): return
        a, r = self.current()
        resource = self.project.archives[a].resources[r]
        self.detail.configure(text=f'{kind(resource)} • ID {resource.name_hash:016x} • Type {resource.type_hash:016x}\n' +
                              tr('Copy a donor resource to replace all three sections while keeping this target ID.'))

    def donor(self):
        def work():
            a, r = self.current()
            filename = filedialog.askopenfilename(parent=self, title=tr('Choose donor mod ZIP / archive'))
            if not filename: return
            def done(donor):
                win = ChoiceScreen(self.app, size=(1080, 650))
                body = ttk.Frame(win.card, padding=16); body.pack(fill='both', expand=True)
                ttk.Label(body, text='Choose replacement resource', style='Title.TLabel').pack(anchor='w', pady=(0, 12))
                table = ttk.Frame(body); table.pack(fill='both', expand=True)
                table.columnconfigure(0, weight=1); table.rowconfigure(0, weight=1)
                tree = self.make_tree(table)
                target_type = self.project.archives[a].resources[r].type_hash
                for i, archive in enumerate(donor.archives):
                    for resource in archive.resources:
                        if resource.type_hash == target_type:
                            tree.insert('', 'end', iid=f'{i}:{resource.index}', values=(archive.path.name, kind(resource),
                                f'{resource.name_hash:016x}', ' / '.join(map(str, resource.sizes)), ''))
                def choose():
                    if not tree.selection(): return
                    i, j = map(int, tree.selection()[0].split(':'))
                    self.project.copy_resource(a, r, donor.archives[i], j)
                    win.destroy(); self.populate()
                    self.status.configure(text=tr('Replacement staged. Export mod ZIP to save.'))
                ttk.Button(body, text='Use selected replacement', command=lambda: self.attempt(choose)).pack(side='right', pady=12)
                ttk.Button(body, text='Cancel', command=win.close).pack(side='left', pady=12)
                if not tree.get_children():
                    win.destroy(); raise ValueError('Donor has no resources of the selected type.')
                win.activate(tree)
            self.run(lambda: Project.open(filename), done)
        self.attempt(work)

    def export_bundle(self):
        def work():
            a, r = self.current()
            filename = filedialog.asksaveasfilename(parent=self, defaultextension='.zip', initialfile='native-asset.zip')
            if filename:
                if self.project.source.resolve() == Path(filename).resolve():
                    raise ValueError('Choose a separate output file.')
                self.run(lambda: self.project.export_bundle(a, r, filename),
                         lambda _: self.status.configure(text=tr('Native asset bundle exported.')))
        self.attempt(work)

    def import_bundle(self):
        def work():
            a, r = self.current()
            filename = filedialog.askopenfilename(parent=self, filetypes=[('Native asset bundle','*.zip')])
            if filename:
                def done(_):
                    self.populate()
                    self.status.configure(text=tr('Replacement staged. Export mod ZIP to save.'))
                self.run(lambda: self.project.import_bundle(a, r, filename), done)
        self.attempt(work)

    def restore(self):
        def work():
            self.project.restore(*self.current()); self.populate()
        self.attempt(work)

    def export(self):
        if hasattr(self, 'finish_export'):
            self.finish_export(); return
        def work():
            if not self.project: raise ValueError(tr('Open a source mod first.'))
            filename = filedialog.asksaveasfilename(parent=self, defaultextension='.zip', initialfile='visual-audio-mod.zip')
            if not filename: return
            name = self.name.get()
            def done(output):
                self.saved_revision = self.project.revision
                self.status.configure(text=tr('Exported: ') + str(output))
                self.app.log('Visual/audio mod exported: '+str(output))
                if messagebox.askyesno(tr('Mod exported'), tr('Add this mod ZIP to the library?'), parent=self):
                    self.app._add_paths([str(output)])
            self.run(lambda: self.project.export_mod(filename, name), done)
        self.attempt(work)

    def destroy(self):
        self.after_cancel(self.poll_token)
        super().destroy()
