"""Automatic mod repair and export workflow for DATA BOT."""
import threading
import tkinter as tk
from tkinter import ttk
from panel_dialogs import filedialog, simpledialog

from localization import tr
from report_view import ReportView


class EasyRepair(ttk.Frame):
    def show_report(self, text):
        self.report.configure(state='normal')
        self.report.delete('1.0', 'end')
        heading = text.split('\n', 1)[0]
        tag = {'REPAIRED AND UPDATED SUCCESFULLY': 'success',
               'FAILED TO REPAIR OR UPDATE': 'error'}.get(heading)
        if tag:
            self.report.insert('1.0', heading, tag)
            self.report.insert('end', text[len(heading):])
        else:
            self.report.insert('1.0', text)
        self.report.configure(state='disabled')

    def run(self, work, done, failure=None):
        if self.busy:
            return
        if getattr(self.app, 'busy', False):
            self.status.configure(text=tr('Wait for the current app operation to finish.'))
            return
        self.busy = True
        if hasattr(self.app, '_set_buttons'):
            self.app._set_buttons(False)
        self.analyse_button.configure(state='disabled')
        self.folder_button.configure(state='disabled')
        self.export_button.configure(state='disabled')
        self.purge_button.configure(state='disabled')
        self.status.configure(text=tr('Working…'))
        def worker():
            try:
                result, error = work(), None
            except Exception as exc:
                result, error = None, str(exc)
            self.after(0, lambda: finish(result, error))
        def finish(result, error):
            self.busy = False
            if hasattr(self.app, '_set_buttons'):
                self.app._set_buttons(True)
            self.analyse_button.configure(state='normal')
            self.folder_button.configure(state='normal')
            self.purge_button.configure(state='normal')
            if error:
                if failure:
                    failure(error)
                else:
                    self.status.configure(text=tr('Operation failed; review the report.'))
                    self.show_report(error)
            else:
                done(result)
            self.export_button.configure(state='normal' if self.repaired_folder else 'disabled')
        threading.Thread(target=worker, daemon=True).start()


    def __init__(self, parent, app):
        super().__init__(parent)
        self.app, self.busy = app, False
        self.repaired_folder = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        ttk.Label(self, text=tr('Select your mod. Laboratory finds its archived build, repairs supported '
            'changes against your current Steam files, and saves a new mod folder.'), wraplength=950).grid(
                row=0, column=0, columnspan=2, sticky='ew', pady=12)
        toolbar = ttk.Frame(self)
        toolbar.grid(row=1, column=0, columnspan=2, sticky='ew', pady=8)
        toolbar.columnconfigure(0, weight=1)
        canvas = tk.Canvas(toolbar, height=42, highlightthickness=0, borderwidth=0,
                           background=ttk.Style(self).lookup('TFrame', 'background') or '#222222')
        self.toolbar_canvas = canvas
        canvas._theme_background = True
        canvas.grid(row=0, column=0, sticky='ew')
        buttons = ttk.Frame(canvas)
        canvas.create_window(0, 0, window=buttons, anchor='nw')
        scroll_buttons = ttk.Scrollbar(toolbar, orient='horizontal', command=canvas.xview)
        canvas.configure(xscrollcommand=scroll_buttons.set)
        def size_toolbar(event=None):
            canvas.configure(scrollregion=canvas.bbox('all'), height=buttons.winfo_reqheight())
            if buttons.winfo_reqwidth() > canvas.winfo_width():
                scroll_buttons.grid(row=1, column=0, sticky='ew')
            else:
                scroll_buttons.grid_remove()
        buttons.bind('<Configure>', size_toolbar)
        canvas.bind('<Configure>', size_toolbar)
        self.analyse_button = ttk.Button(buttons, text=tr('Import zip/file mod'), style='Accent.TButton', command=self.file)
        self.analyse_button.pack(side='left', padx=(0, 8))
        self.folder_button = ttk.Button(buttons, text=tr('Import mod folder'), style='Accent.TButton', command=self.folder)
        self.folder_button.pack(side='left', padx=(0, 8))
        self.export_button = ttk.Button(buttons, text=tr('EXPORT REPAIRED MOD…'), style='Install.TButton', command=self.export, state='disabled')
        self.export_button.pack(side='left', padx=(0, 8))
        self.purge_button = ttk.Button(buttons, text=tr('PURGE REPAIRED MOD STORAGE'),
                                       style='Danger.TButton', command=self.purge)
        self.purge_button.pack(side='left', padx=(0, 8))
        self.clear_button = ttk.Button(buttons, text=tr('Clear Log'),
                                       style='Shortcut.TButton', command=self.clear_log)
        self.clear_button.pack(side='left')
        ttk.Button(buttons, text=tr('Archive'), command=self.library).pack(side='left', padx=8)
        ttk.Button(buttons, text=tr('Archive current Steam build'), command=self.capture).pack(side='left')
        self.status = ttk.Label(self, text=tr('Steam builds are archived automatically at startup when mods are purged. '
            'Older repair baselines stay in Archive. Only files used by mod repair are stored. Use verified clean game files.'),
            wraplength=950, style='Muted.TLabel')
        self.status.grid(row=2, column=0, columnspan=2, sticky='ew', pady=8)
        advanced = ttk.Frame(self)
        advanced.grid(row=4, column=0, columnspan=2, sticky='ew', pady=(12, 4))
        self.reference_button = ttk.Button(advanced, text=tr('INSPECT REPAIRED REFERENCE'), command=self.reference)
        self.reference_button.pack(side='left', padx=(0, 8))
        self.baseline_button = ttk.Button(advanced, text=tr('IMPORT OLD DATA BASELINE'), command=self.import_baseline)
        self.baseline_button.pack(side='left')
        for label in (child for child in self.winfo_children() if isinstance(child, ttk.Label)):
            label.bind('<Configure>', lambda event, label=label: label.configure(wraplength=max(1, event.width-12)))
        self.report = ReportView(self, wrap='word', state='disabled', font=('Consolas', 10))
        self.report.grid(row=3, column=0, sticky='nsew')
        self.report.tag_configure('success', foreground='#16752b')
        self.report.tag_configure('error', foreground='#b5161c')
        app.texts.append(self.report)
        scroll = ttk.Scrollbar(self, command=self.report.yview)
        scroll.grid(row=3, column=1, sticky='ns')
        self.report.configure(yscrollcommand=scroll.set)

    def reference(self):
        if self.busy:
            return
        reference = filedialog.askopenfilename(parent=self, title=tr('Select repaired reference ZIP'))
        if not reference:
            return
        original = filedialog.askopenfilename(parent=self, title=tr('Select original mod ZIP to compare (Cancel to inspect only)'))
        import repair_reference
        import json
        def work():
            return repair_reference.compare(reference, original) if original else repair_reference.inspect(reference)
        def done(rows):
            self.show_report('Reference inspection only. No installer or package code was executed.\n\n'
                             + json.dumps(rows, indent=2, ensure_ascii=False))
            self.status.configure(text=tr('Reference inspected. A packaging change is not proof of a binary repair.'))
        self.run(work, done)

    def import_baseline(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(parent=self, title=tr('Select old game-data ZIP'))
        if not path:
            return
        import re
        from pathlib import Path
        import build_archive
        guesses = re.findall(r'\d{6,}', Path(path).stem)
        build = simpledialog.askstring(tr('Baseline Steam build'), tr('Steam build ID for these old data files:'),
                                       initialvalue=guesses[-1] if guesses else '', parent=self)
        if not build:
            return
        def done(folder):
            self.show_report('Imported data-only baseline:\n' + str(folder)
                             + '\n\nThe supplied build label is recorded; this is not a complete Steam build archive.')
            self.status.configure(text=tr('Baseline imported and available for automatic matching.'))
        self.run(lambda: build_archive.import_data_baseline(path, build.strip()), done)

    def game(self):
        import core
        return core.game_dir(self.app.cfg)

    def file(self):
        if not self.busy:
            path = filedialog.askopenfilename(parent=self, title=tr('Import zip/file mod'),
                filetypes=[('Mod ZIP or data/archive file', '*.zip *.dl_bin *.patch_*'), ('All files', '*.*')])
            if path:
                self.repair(path)

    def folder(self):
        if not self.busy:
            path = filedialog.askdirectory(parent=self, title=tr('Select extracted mod folder'))
            if path:
                self.repair(path)

    def repair(self, path):
        import build_archive
        if self.busy or getattr(self.app, 'busy', False):
            return
        import core
        root = core.hellforge_root(self.app.cfg)
        if root is not None:
            import hellforge
            self.repaired_folder = None
            self.export_button.configure(state='disabled')
            self.run(lambda: hellforge.validate_package(path, root),
                     lambda report: self.outcome('HELLFORGE PACKAGE CHECKED', '\n\n'.join(report)),
                     lambda error: self.outcome('HELLFORGE PACKAGE NEEDS ATTENTION', error))
            return
        if getattr(self.app, '_stock_verify_started', False):
            if not self.app._confirm_steam_verify_complete():
                return
            self.app._capture_for_repair = True
            self.app._capture_stock_then(lambda: self._repair_after_stock(path, capture_current=False))
            return
        self._repair_after_stock(path)

    def _repair_after_stock(self, path, capture_current=True):
        import core
        import build_archive
        if self.busy or getattr(self.app, 'busy', False):
            return
        self.repaired_folder = None
        self.export_button.configure(state='disabled')
        def work():
            game = self.game()
            if core.stock_file_count() != core.REQUIRED_STOCK_FILES:
                raise ValueError('DATA BOT CAN NOT UPDATE/REPAIR THIS MOD BECAUSE IT IS EITHER INCOMPATIBLE OR THE BOT DOESN\'T HAVE THE DATA IT NEEDS')
            if core.load_deployed():
                raise ValueError('Purge ModDiver-deployed mods before repairing. Your library copies remain available for redeployment.')
            def repair_with_baselines(roots):
                try:
                    build = build_archive.steam_build(game)
                except (OSError, ValueError, KeyError):
                    build = None
                known = bool(build) and any(meta.get('build_id') == build and meta.get('scope') in ('repair-data', 'data-only')
                                            for _, meta in build_archive.builds())
                if capture_current and build and not known and core.stock_file_count() == core.REQUIRED_STOCK_FILES:
                    build_archive.capture_stock_folder(game, core.STOCK)
                return build_archive.repair(path, game, root=roots, progress=lambda message: self.app.log(message))
            if capture_current:
                try:
                    with build_archive.baseline_session(progress=lambda message: self.app.log(message)) as roots:
                        return repair_with_baselines(roots)
                except Exception as exc:
                    if build_archive.archive_root().exists():
                        raise
                    self.app.log('Shared repair data unavailable; using saved local baselines: ' + str(exc))
                    return repair_with_baselines(build_archive.archive_root())
            return repair_with_baselines(build_archive.archive_root())
        def done(result):
            folder, report = result
            self.repaired_folder = folder
            self.outcome('REPAIRED AND UPDATED SUCCESFULLY', 'Repaired mod saved to:\n' + str(folder) + '\n\n' + '\n'.join(report))
        def failed(error):
            self.outcome('FAILED TO REPAIR OR UPDATE', error)
            if hasattr(self.app, 'log'):
                self.app.log('DATA BOT CAN NOT UPDATE/REPAIR THIS MOD BECAUSE IT IS EITHER INCOMPATIBLE OR THE BOT DOESN\'T HAVE THE DATA IT NEEDS', 'error')
        self.run(work, done, failed)

    def outcome(self, message, details):
        self.status.configure(text=message)
        self.show_report(message + '\n\n' + details)
        if hasattr(self.app, 'log'):
            self.app.log(message)

    def export(self):
        if self.busy or getattr(self.app, 'busy', False) or self.repaired_folder is None:
            return
        import core
        import zipfile
        from pathlib import Path
        source = Path(self.repaired_folder)
        try:
            if not source.is_dir():
                raise ValueError('The repaired mod folder no longer exists. Import and repair the mod again.')
            destination = filedialog.asksaveasfilename(parent=self, title=tr('Export repaired mod ZIP'),
                initialfile=source.name + '.zip', defaultextension='.zip',
                filetypes=[('ZIP archive', '*.zip')])
            if not destination:
                return
            destination = Path(destination)
            with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for path in sorted(source.rglob('*')):
                    if path.is_file():
                        archive.write(path, path.relative_to(source).as_posix())
            self.status.configure(text=tr('Repaired mod ZIP exported. Import it in any mod manager.'))
            self.show_report('Portable repaired mod ZIP exported to:\n' + str(destination))
        except (OSError, ValueError) as exc:
            self.show_report(str(exc))

    def purge(self):
        if self.busy or getattr(self.app, 'busy', False):
            return
        import build_archive
        def done(_):
            self.repaired_folder = None
            self.show_report('Repaired mod storage purged.')
            self.status.configure(text=tr('Repaired mod storage purged.'))
        self.run(build_archive.purge_repaired, done)

    def clear_log(self):
        self.show_report('')

    def capture(self):
        import build_archive
        game = self.game()
        def done(path):
            self.show_report('Archived Steam build data:\n' + str(path))
            self.status.configure(text=tr('Archive ready. Older captured builds are retained.'))
        self.run(lambda: build_archive.capture(game), done)

    def library(self):
        import build_archive
        if self.busy:
            return
        root = build_archive.archive_root()
        root.mkdir(parents=True, exist_ok=True)
        entries = build_archive.builds()
        self.show_report('Archive folder:\n' + str(root) + '\n\n' + ('\n'.join(
            f"Steam build {meta['build_id']} — {meta['created_utc']} — {meta['bytes'] / 1024**3:.2f} GiB\n{path}"
            for path, meta in entries) or 'No builds captured yet. Archive your clean Steam build before updating.'))
        import core
        if core.os.name == 'nt':
            core.os.startfile(str(root))
        else:
            core.linux_open(str(root))



class RepairMode(EasyRepair):
    """The automatic updater is the sole repair mode."""
