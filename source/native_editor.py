"""Native Tk armour-kit and passive-effect editor for Windows and Linux.

Schema-derived armour fields use the supplied HD REMIX source; passive layouts
come from the bundled SHODAN bridge. Export uses portable hash correction.
"""
from dataclasses import dataclass
from pathlib import Path
import math
import struct
import threading
import tkinter as tk
from localization import tr
from tkinter import ttk, filedialog, simpledialog, messagebox

import core
import editor_names
import hdremix
from dlbin_codec import DLBin
from portable_hash import correct_reserved, finish_armor, content_hash


@dataclass(frozen=True)
class Field:
    block: int
    offset: int
    code: str
    record: str
    label: str


class Document:
    def __init__(self, path):
        self.data = DLBin.open(path)
        self.fields = []
        types = {r.type_hash for r in self.data.resources}
        self.armor = types == {hdremix.KIT}
        if self.armor:
            hdremix.armor_headers(self.data.plain)
            names = {e['definition']: e['name'] for e in hdremix.SCHEMA['changes']}
            for r in self.data.resources:
                payload = self.data.payload(r.index,0)
                definition = struct.unpack_from('<I',payload)[0]
                name = names.get(definition, f'Armor kit {definition}')
                self.fields.extend([Field(r.index,4,'I',name,'Availability tag'), Field(r.index,28,'I',name,'Passive ID')])
        elif types == {0x63CE0FEB}:
            for r in self.data.resources:
                payload = self.data.payload(r.index,0)
                if len(payload)<56:
                    raise ValueError('Unsupported passive record size.')
                identity = struct.unpack_from('<I',payload)[0]
                record = editor_names.PASSIVE_NAMES.get(identity,f'Passive {identity}')
                for descriptor,stride,value_offset,label in ((16,16,8,'Modifier'),(32,12,4,'Stat')):
                    pointer,count = struct.unpack_from('<QQ',payload,descriptor)
                    if count>4096 or (count and (pointer<56 or pointer+count*stride>len(payload))):
                        raise ValueError('Passive array lies outside its block.')
                    for row in range(count):
                        offset = pointer+row*stride
                        field_id = struct.unpack_from('<I',payload,offset)[0]
                        title = editor_names.MOD_NAMES.get(field_id,f'{label} {field_id:#010x}')
                        self.fields.append(Field(r.index,offset+value_offset,'f',record,title))
        else:
            raise ValueError('This native editor supports armour kits and passive bonuses. Use Data Decoder for other data types.')

    def value(self, field):
        return struct.unpack_from('<'+field.code,self.data.payload(field.block,0),field.offset)[0]

    def edit(self, field, value):
        value = float(value) if field.code=='f' else int(value,16) if str(value).lower().startswith('0x') else int(value)
        if field.code=='f' and not math.isfinite(value):
            raise ValueError('Value must be finite.')
        payload = bytearray(self.data.payload(field.block,0))
        struct.pack_into('<'+field.code,payload,field.offset,value)
        self.data.replace(field.block,0,bytes(payload),float_offsets=[field.offset] if field.code=='f' else [])

    def prepare(self):
        if not self.data.replacements:
            return self.data.sealed
        candidate = bytearray(self.data.plain)
        for (index,_),payload in self.data.replacements.items():
            offset = self.data.resources[index].offsets[0]
            candidate[offset:offset+len(payload)] = payload
        if self.armor:
            corrected = finish_armor(self.data.plain,candidate,self.data.headers)
            hdremix.armor_headers(corrected)
        else:
            corrected = correct_reserved(self.data.plain,candidate,self.data.headers)
            if corrected is None:
                raise ValueError('No portable correction is available for this passive layout. Original file preserved.')
        if content_hash(corrected)!=content_hash(self.data.plain):
            raise ValueError('Content hash check failed.')
        # Armour padding may extend the final block; all edited gameplay bytes
        # and every other original payload byte must remain exact.
        for pos,_,size in self.data.headers:
            if corrected[pos+24:pos+24+size] != candidate[pos+24:pos+24+size]:
                raise ValueError('Correction changed gameplay payload bytes.')
        sealed = core.seal(corrected)
        if core.unseal(sealed)!=corrected:
            raise ValueError('Reseal verification failed.')
        return sealed


class Editor(tk.Toplevel):
    _standalone_window = True
    def __init__(self, app):
        super().__init__(app)
        self.app,self.document,self.busy = app,None,False
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.title(tr('Native Armor & Passive Editor — Windows / Linux'))
        self.configure(bg=app.theme['bg'])
        self.resizable(True, True)
        w,h=min(1050,self.winfo_screenwidth()-100),min(720,self.winfo_screenheight()-120)
        self.geometry(f'{w}x{h}+{(self.winfo_screenwidth()-w)//2}+{(self.winfo_screenheight()-h)//2}')
        self.state('zoomed')
        self.columnconfigure(0,weight=1);self.rowconfigure(2,weight=1)
        bar=ttk.Frame(self,padding=12);bar.grid(row=0,column=0,sticky='ew')
        ttk.Button(bar,text=tr('Open Data File'),command=self.open_file,style='Accent.TButton').pack(side='left',padx=4)
        ttk.Button(bar,text=tr('Open Game Armor'),command=lambda:self.load(core.game_dir(app.cfg)/'data/game'/hdremix.ARMOR)).pack(side='left',padx=4)
        ttk.Button(bar,text=tr('Open Game Passives'),command=lambda:self.load(core.game_dir(app.cfg)/'data/game/generated_customization_passive_bonuses.dl_bin')).pack(side='left',padx=4)
        ttk.Button(bar,text=tr('Export Edited File'),command=self.export,style='Install.TButton').pack(side='left',padx=4)
        self.status=ttk.Label(self,text=tr('Named armour-kit availability/passive fields and passive effect values. Double-click a field to edit.'),style='Muted.TLabel',wraplength=950)
        self.status.grid(row=1,column=0,sticky='w',padx=16,pady=6)
        frame=ttk.Frame(self,padding=12);frame.grid(row=2,column=0,sticky='nsew');frame.columnconfigure(0,weight=1);frame.rowconfigure(0,weight=1)
        self.tree=ttk.Treeview(frame,columns=('record','field','value'),show='headings')
        for key,title,width in (('record','ARMOR / PASSIVE',340),('field','PROPERTY',300),('value','VALUE',150)):
            self.tree.heading(key,text=tr(title));self.tree.column(key,width=width)
        self.tree.grid(row=0,column=0,sticky='nsew');sb=ttk.Scrollbar(frame,command=self.tree.yview);sb.grid(row=0,column=1,sticky='ns');self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind('<Double-1>',self.edit)
        ttk.Label(self,text=tr('Export preserves the input and verifies the content hash. Add the exported file folder to Mod Library to deploy. '
                  'This native editor covers armour kits and passive effects; it is not the full SHODAN/CCM feature set.'),style='Muted.TLabel',wraplength=950).grid(row=3,column=0,padx=16,pady=12,sticky='w')
        self.update_idletasks();app._dark_titlebar(self)

    def close(self):
        if self.busy:
            messagebox.showinfo(tr('Export running'),tr('Wait for the export to finish before closing this editor.'),parent=self)
            return
        if self.document and self.document.data.replacements and not messagebox.askyesno(tr('Close editor'),tr('Discard staged edits and close?'),parent=self):
            return
        self.destroy()

    def open_file(self):
        if self.busy:return
        path=filedialog.askopenfilename(parent=self,title=tr('Open armor sets or passive bonuses'),filetypes=[('Sealed data','*.dl_bin')])
        if path:self.load(path)

    def load(self,path):
        if self.busy:return
        if self.document and self.document.data.replacements and not messagebox.askyesno(tr('Discard edits'),tr('Discard staged edits?'),parent=self):return
        try:
            document=Document(path)
            self.document=document;self.refresh()
            self.status.configure(text=tr(f'{document.data.path} — {len(document.fields)} editable properties'))
        except Exception as exc:messagebox.showerror(tr('Native Editor'),tr(str(exc)),parent=self)

    def refresh(self):
        selected=self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for index,field in enumerate(self.document.fields):
            value=self.document.value(field)
            self.tree.insert('','end',iid=str(index),values=(field.record,field.label,format(value,'.9g') if field.code=='f' else value))
        if selected and self.tree.exists(selected[0]):self.tree.selection_set(selected[0]);self.tree.see(selected[0])

    def edit(self,event=None):
        if self.busy or not self.document or not self.tree.selection():return
        field=self.document.fields[int(self.tree.selection()[0])]
        value=simpledialog.askstring(tr(field.label),tr(f'{field.record}\n{field.label}'),initialvalue=str(self.document.value(field)),parent=self)
        if value is not None:
            try:self.document.edit(field,value);self.refresh();self.status.configure(text=tr('Changes staged. Export Edited File to save a mod copy.'))
            except Exception as exc:messagebox.showerror(tr('Invalid value'),tr(str(exc)),parent=self)

    def export(self):
        if self.busy or not self.document:return
        path=filedialog.asksaveasfilename(parent=self,title=tr('Export into a new mod folder'),initialfile=self.document.data.path.name,defaultextension='.dl_bin')
        if not path:return
        if Path(path).resolve()==self.document.data.path.resolve():
            messagebox.showerror(tr('Export'),tr('Choose another folder to preserve the original.'),parent=self);return
        self.busy=True;self.status.configure(text=tr('Correcting hash and resealing with the portable engine…'))
        def work():
            try:
                sealed=self.document.prepare();self.document.data.save(path,sealed);error=None
            except Exception as exc:error=str(exc)
            self.after(0,lambda:finish(error))
        def finish(error):
            self.busy=False
            if error:messagebox.showerror(tr('Export failed'),tr(error),parent=self)
            self.status.configure(text=tr(error or 'Verified export saved: '+path))
        threading.Thread(target=work,daemon=True).start()
