"""Native resource browser, payload editor and Stingray archive exporter."""
from pathlib import Path
import struct
import math
import threading
import tkinter as tk
from localization import tr
from tkinter import ttk, filedialog, messagebox

from archive_codec import Archive, LUA_TYPE, SECTIONS, SUFFIXES, MAX_BYTES, lua_source
from merge_engine import atomic_write
from dlbin_codec import DLBin


class Decoder(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, style="TFrame")
        from repair_ui import RepairMode
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)
        self.payload = PayloadDecoder(tabs, app)
        self.repair = RepairMode(tabs, app)
        tabs.add(self.repair, text=tr("Update Repair"))
        tabs.add(self.payload, text=tr("Decode / Edit"))
        tabs.select(self.repair)

    # Preserve the application's close/restart guards for the nested editor.
    busy = property(lambda self: self.payload.busy or self.repair.busy)
    archive = property(lambda self: self.payload.archive)
    current = property(lambda self: self.payload.current)
    editor = property(lambda self: self.payload.editor)
    rendered = property(lambda self: self.payload.rendered)


class PayloadDecoder(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, style="TFrame")
        self.app = app
        self.archive = None
        self.current = None
        self.rendered = ""
        self.busy = False
        self.section = tk.StringVar(value="main")
        self.mode = tk.StringVar(value="Hex")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        for title, command, style in (("OPEN FILE / ARCHIVE", self.open_archive, "Accent.TButton"),
                                      ("EXPORT REPACKED FILE", self.repack, "Install.TButton"),
                                      ("GUIDE", self.show_guide, "Update.TButton")):
            ttk.Button(toolbar, text=tr(title), command=command, style=style).pack(side="left", padx=(0, 8))
        self.info = ttk.Label(self, text=tr("Open a sealed .dl_bin data file or a Stingray archive / .patch_N file."),
                              style="Muted.TLabel", wraplength=900)
        self.info.grid(row=1, column=0, sticky="w", pady=(0, 8))
        split = ttk.Panedwindow(self, orient="horizontal")
        split.grid(row=2, column=0, sticky="nsew")
        left = ttk.Frame(split)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(left, columns=("id", "type", "size"), show="headings", selectmode="browse")
        for key, title, width in (("id", "RESOURCE HASH", 150), ("type", "TYPE HASH", 150), ("size", "BYTES", 75)):
            self.tree.heading(key, text=tr(title))
            self.tree.column(key, width=width)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(left, command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.select_resource)
        split.add(left, weight=2)
        right = ttk.Frame(split)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        controls = ttk.Frame(right)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.section_box = ttk.Combobox(controls, textvariable=self.section, values=SECTIONS, state="readonly", width=9)
        self.section_box.pack(side="left", padx=(0, 6))
        self.section_box.bind("<<ComboboxSelected>>", self.switch_view)
        self.mode_box = ttk.Combobox(controls, textvariable=self.mode, values=("Hex", "Lua source", "UInt32 values", "Float32 values"), state="readonly", width=15)
        self.mode_box.pack(side="left", padx=(0, 6))
        self.mode_box.bind("<<ComboboxSelected>>", self.switch_view)
        ttk.Button(controls, text=tr("Apply Edit"), command=self.apply_edit).pack(side="left")
        self.detail = ttk.Label(right, text=tr("Select a resource."), style="Muted.TLabel", wraplength=600)
        self.detail.grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.editor = tk.Text(right, wrap="none", undo=True, font=("Consolas", 10), bd=0)
        self.editor.grid(row=2, column=0, sticky="nsew")
        editor_scroll = ttk.Scrollbar(right, command=self.editor.yview)
        editor_scroll.grid(row=2, column=1, sticky="ns")
        self.editor.configure(yscrollcommand=editor_scroll.set)
        app.texts.append(self.editor)
        buttons = ttk.Frame(right)
        buttons.grid(row=3, column=0, sticky="ew", pady=8)
        ttk.Button(buttons, text=tr("Export Payload"), command=self.export_payload).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text=tr("Import Replacement"), command=self.import_payload).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text=tr("Restore Original"), command=self.restore).pack(side="left")
        split.add(right, weight=3)
        ttk.Label(self, text=tr(".dl_bin files decode to LDLD blocks. Numeric views show 4-byte values at block-relative offsets; field names are not inferred. "
                  "Keep block lengths unchanged. Export verifies and reseals data files; archive exports include sidecars."),
                  style="Muted.TLabel", wraplength=1000).grid(row=3, column=0, sticky="w", pady=8)

    def show_guide(self):
        from choice_screen import active
        from panel_dialogs import ResultScreen
        existing = active(self.app)
        if existing is not None:
            return existing
        screen = ResultScreen(self.app, tr('DATA BOT — Complete Guide'), size=(860, 720))
        screen.buttons([('Close Guide', None)])
        body = ttk.Frame(screen.content)
        body.pack(fill='both', expand=True)
        text = tk.Text(body, wrap='word', font=('Segoe UI', 11), padx=12, pady=10, bd=0,
                       bg=self.app.theme['bg'], fg=self.app.theme['text'], spacing3=8)
        text.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(body, command=text.yview)
        scroll.pack(side='right', fill='y')
        text.configure(yscrollcommand=scroll.set)
        text.insert('1.0', (Path(__file__).parent/'decoder_guide.txt').read_text(encoding='utf-8'))
        text.configure(state='disabled')
        # Guide widgets were added after buttons; include them in Escape routing.
        text.bind('<Escape>', screen.close)
        screen.guide_text = text
        return screen

    def run(self, work, done):
        if self.busy:
            return
        self.busy = True
        self.app._begin_loading(self, self.winfo_toplevel())
        self.info.configure(text=tr("Working…"))
        def worker():
            try:
                result, error = work(), None
            except Exception as exc:
                result, error = None, str(exc)
            self.after(0, lambda: finish(result, error))
        def finish(result, error):
            self.busy = False
            self.app._end_loading(self)
            if error:
                self.info.configure(text=tr(error))
                messagebox.showerror(tr("DATA BOT"), tr(error), parent=self)
            else:
                try:
                    done(result)
                except Exception as exc:
                    messagebox.showerror(tr("DATA BOT"), tr(str(exc)), parent=self)
        threading.Thread(target=worker, daemon=True).start()

    def pending(self):
        if self.current is None or self.editor.cget("state") == "disabled":
            return True
        if self.editor.get("1.0", "end-1c") != self.rendered:
            answer = messagebox.askyesnocancel(tr("Unapplied edit"), tr("Apply this edit before continuing?"), parent=self)
            if answer is None:
                return False
            if answer:
                return self.apply_edit()
        return True

    def open_archive(self):
        if self.busy or not self.pending():
            return
        if self.archive and self.archive.replacements and not messagebox.askyesno(
                tr("Open archive"), tr("Discard the staged changes and open another archive?"), parent=self):
            return
        path = filedialog.askopenfilename(parent=self, title=tr("Open data file or archive"),
                                          filetypes=[("Data files and archives", "*"), ("Sealed data files", "*.dl_bin")])
        if not path:
            return
        def opened(archive):
            self.archive, self.current = archive, None
            data_file = isinstance(archive, DLBin)
            self.section.set("main")
            self.section_box.configure(state="disabled" if data_file else "readonly")
            self.tree.heading("id", text=tr("BLOCK OFFSET" if data_file else "RESOURCE HASH"))
            self.tree.heading("type", text=tr("BLOCK TYPE" if data_file else "TYPE HASH"))
            self.tree.delete(*self.tree.get_children())
            for resource in archive.resources:
                self.tree.insert("", "end", iid=str(resource.index), values=(f"{resource.name_hash:016x}",
                    "Lua" if resource.type_hash == LUA_TYPE else f"{resource.type_hash:016x}", sum(resource.sizes)))
            self.info.configure(text=tr(f"{archive.path}  •  {len(archive.resources)} " +
                                ("decoded LDLD blocks" if data_file else f"resources / {archive.type_count} types")))
            self.editor.configure(state="normal")
            self.editor.delete("1.0", "end")
            self.rendered = ""
        self.run(lambda: DLBin.open(path) if path.lower().endswith(".dl_bin") else Archive.open(path), opened)

    def select_resource(self, _event=None):
        if self.busy:
            return
        selected = self.tree.selection()
        if selected and self.current is not None and selected[0] == str(self.current[0]):
            return
        if selected and self.pending():
            index = int(selected[0])
            self.current = (index, SECTIONS.index(self.section.get()))
            payload = self.archive.payload(*self.current)
            self.mode.set("UInt32 values" if isinstance(self.archive, DLBin) else
                          "Lua source" if self.archive.resources[index].type_hash == LUA_TYPE and lua_source(payload) is not None else "Hex")
            self.show()
        elif self.current is not None:
            self.tree.selection_set(str(self.current[0]))

    def switch_view(self, _event=None):
        if self.current is None or self.busy:
            return
        if not self.pending():
            self.section.set(SECTIONS[self.current[1]])
            self.mode.set(self.view_mode)
            return
        self.current = (self.current[0], SECTIONS.index(self.section.get()))
        self.show()

    def show(self):
        payload = self.archive.payload(*self.current)
        self.view_mode = self.mode.get()
        self.editor.configure(state="normal")
        self.editor.delete("1.0", "end")
        if len(payload) > 2 * 1024 ** 2:
            text = "Payload is too large for inline editing. Use Export Payload and Import Replacement."
            self.editor.insert("1.0", text)
            self.editor.configure(state="disabled")
        else:
            resource = self.archive.resources[self.current[0]]
            text = lua_source(payload) if self.view_mode == "Lua source" and resource.type_hash == LUA_TYPE else None
            if self.view_mode in ("UInt32 values", "Float32 values"):
                code = "I" if self.view_mode == "UInt32 values" else "f"
                self.scalar_rendered = {pos: (str(struct.unpack_from("<I", payload, pos)[0]) if code == "I"
                    else format(struct.unpack_from("<f", payload, pos)[0], ".9g"))
                    for pos in range(0, len(payload) - 3, 4)}
                text = "\n".join(f"{pos:08X}: {value}" for pos, value in self.scalar_rendered.items())
            elif text is None:
                self.mode.set("Hex")
                self.view_mode = "Hex"
                text = "\n".join(payload[pos:pos+16].hex(" ") for pos in range(0, len(payload), 16))
            self.editor.insert("1.0", text)
        self.rendered = text
        self.editor.edit_reset()
        self.detail.configure(text=tr(f"Resource {self.current[0]} · {SECTIONS[self.current[1]]} · {len(payload):,} bytes · "
                                  f"{len(self.archive.replacements)} staged replacements"))

    def apply_edit(self):
        if self.current is None or self.busy or self.editor.cget("state") == "disabled":
            return True
        try:
            text = self.editor.get("1.0", "end-1c")
            if self.view_mode == "Lua source":
                source = text.encode("utf-8")
                payload = struct.pack("<II", len(source), 2) + source
            elif self.view_mode in ("UInt32 values", "Float32 values"):
                payload = bytearray(self.archive.payload(*self.current))
                seen = set()
                for line in text.splitlines():
                    if not line.strip():
                        continue
                    address, value = line.split(":", 1)
                    offset, value = int(address.strip(), 16), value.strip()
                    if offset % 4 or offset < 0 or offset + 4 > len(payload) or offset in seen:
                        raise ValueError("Numeric offsets must be unique aligned positions within this payload.")
                    seen.add(offset)
                    if value != self.scalar_rendered.get(offset):
                        if self.view_mode == "UInt32 values":
                            struct.pack_into("<I", payload, offset, int(value, 0))
                        else:
                            number = float(value)
                            if not math.isfinite(number):
                                raise ValueError("New decimal values must be finite.")
                            struct.pack_into("<f", payload, offset, number)
                payload = bytes(payload)
            else:
                payload = bytes.fromhex(text)
            if isinstance(self.archive, DLBin) and self.view_mode == "Float32 values":
                previous = self.archive.payload(*self.current)
                changed = [pos for pos in range(0, len(payload) - 3, 4) if payload[pos:pos+4] != previous[pos:pos+4]]
                self.archive.replace(*self.current, payload, float_offsets=changed)
            else:
                self.archive.replace(*self.current, payload)
            if self.view_mode in ("UInt32 values", "Float32 values"):
                self.scalar_rendered.update({int(line.split(":", 1)[0].strip(), 16): line.split(":", 1)[1].strip()
                                             for line in text.splitlines() if line.strip()})
            self.rendered = text
            self.detail.configure(text=tr(f"Edit staged · {len(payload):,} bytes · {len(self.archive.replacements)} replacements"))
            return True
        except Exception as exc:
            messagebox.showerror(tr("Invalid edit"), tr(str(exc)), parent=self)
            return False

    def export_payload(self):
        if self.current is None or self.busy or not self.pending():
            return
        path = filedialog.asksaveasfilename(parent=self, initialfile=f"resource_{self.current[0]}_{SECTIONS[self.current[1]]}.bin")
        if path:
            try:
                if Path(path).resolve() in {Path(str(self.archive.path) + suffix).resolve() for suffix in SUFFIXES}:
                    raise ValueError("Choose a payload filename outside the original archive triplet.")
                atomic_write(path, self.archive.payload(*self.current))
            except Exception as exc:
                messagebox.showerror(tr("Export failed"), tr(str(exc)), parent=self)

    def import_payload(self):
        if self.current is None or self.busy or not self.pending():
            return
        path = filedialog.askopenfilename(parent=self, title=tr("Import raw resource payload"))
        if path:
            try:
                if Path(path).stat().st_size > MAX_BYTES:
                    raise ValueError("Replacement exceeds the 2 GiB editor limit.")
                self.archive.replace(*self.current, Path(path).read_bytes())
                self.show()
            except Exception as exc:
                messagebox.showerror(tr("Import failed"), tr(str(exc)), parent=self)

    def restore(self):
        if self.current is not None and not self.busy:
            self.archive.replacements.pop(self.current, None)
            if isinstance(self.archive, DLBin):
                self.archive.float_edits.pop(self.current[0], None)
            self.show()

    def repack(self):
        if self.archive is None or self.busy or not self.pending():
            return
        data_file = isinstance(self.archive, DLBin)
        path = filedialog.asksaveasfilename(parent=self, title=tr("Export repacked file to a new folder"),
                                          initialfile=(self.archive.path.name if data_file or ".patch_" in self.archive.path.name
                                                       else self.archive.path.name + ".patch_0"))
        if path:
            if data_file:
                if Path(path).resolve() == self.archive.path.resolve():
                    messagebox.showerror(tr("DATA BOT"), tr("Choose a new folder to preserve the input file."), parent=self)
                    return
                def save_data(result):
                    sealed, adjustments = result
                    if adjustments and not messagebox.askyesno(tr("Hash correction adjusted decimal values"),
                        tr("Preserving the game's content hash requires these small adjustments to edited values:\n\n" +
                        "\n".join(adjustments[:20]) + "\n\nSave this corrected file?"), parent=self):
                        self.info.configure(text=tr("Export cancelled; staged edits are still available."))
                        return
                    self.archive.save(path, sealed)
                    self.info.configure(text=tr("Decoded, hash-verified and resealed: " + path))
                self.run(self.archive.prepare, save_data)
                return
            if any(Path(str(path) + suffix).exists() for suffix in SUFFIXES):
                if not messagebox.askyesno(tr("Replace exported files"), tr("Replace the archive and matching sidecars at this destination?"), parent=self):
                    return
            self.run(lambda: self.archive.export(path), lambda paths: self.info.configure(
                text=tr("Exported and checked: " + ", ".join(str(p) for p in paths))))
