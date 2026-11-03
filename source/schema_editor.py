"""Searchable native editor for the installed game-data schema and file catalog."""
from pathlib import Path
import hashlib
import threading
import tkinter as tk
from localization import tr
from tkinter import ttk,filedialog,messagebox,simpledialog

import core
from game_schema import Library,friendly
from schema_document import Document


class Editor(tk.Toplevel):
    _standalone_window = True
    PAGE=300
    def __init__(self,app):
        super().__init__(app)
        self.app=app;self.library=None;self.document=None;self.busy=False;self.current=None
        self.filtered=[];self.page=0;self.props=[];self.paths={}
        self.title(tr('Native Game Data Editor'))
        # A normal resizable window retains native minimize/maximize controls.
        self.configure(bg=app.theme['bg']);self.resizable(True, True)
        w,h=min(1420,self.winfo_screenwidth()-80),min(850,self.winfo_screenheight()-100)
        self.geometry(f'{w}x{h}+{(self.winfo_screenwidth()-w)//2}+{(self.winfo_screenheight()-h)//2}')
        self.state('zoomed')
        self.columnconfigure(0,weight=1);self.rowconfigure(2,weight=1)
        bar=ttk.Frame(self,padding=10);bar.grid(row=0,column=0,sticky='ew')
        for title,command in (('Open Game Database',self.open_database),('Open Data File',self.open_file),('Load Type Library',self.open_library),('Export Edited File',self.export),('Rename Entry',self.rename),('Coverage Report',self.coverage)):
            ttk.Button(bar,text=tr(title),command=command).pack(side='left',padx=4)
        self.footer=tk.BooleanVar(value=False)
        extra=ttk.Frame(self);extra.grid(row=1,column=0,sticky='ew',padx=14,pady=(0,8))
        ttk.Checkbutton(extra,text=tr('Schema footer export (experimental)'),variable=self.footer).pack(side='right',padx=6)
        self.status=ttk.Label(extra,text=tr('Load the game database to browse files, entries and verified named properties.'),style='Muted.TLabel',wraplength=900)
        self.status.pack(side='left',fill='x',expand=True)
        split=ttk.Panedwindow(self,orient='horizontal');split.grid(row=2,column=0,sticky='nsew',padx=10)
        self.files=self.tree_panel(split,('name',),(('name','GAME DATA FILES',230),))
        self.files.bind('<<TreeviewSelect>>',self.choose_file)
        middle=ttk.Frame(split);middle.columnconfigure(0,weight=1);middle.rowconfigure(1,weight=1)
        self.search=tk.StringVar()
        search=ttk.Entry(middle,textvariable=self.search);search.grid(row=0,column=0,sticky='ew',pady=(0,6))
        self.search.trace_add('write',lambda *_:self.filter_entries())
        self.entries=self.tree_panel(middle,('entry',),(('entry','ENTRIES / SEARCH ABOVE',400),),grid=True)
        self.entries.bind('<<TreeviewSelect>>',self.choose_entry)
        nav=ttk.Frame(middle);nav.grid(row=2,column=0,sticky='ew',pady=6)
        ttk.Button(nav,text=tr('Previous'),command=lambda:self.change_page(-1)).pack(side='left')
        self.page_label=ttk.Label(nav,text=tr(''));self.page_label.pack(side='left',padx=8)
        ttk.Button(nav,text=tr('Next'),command=lambda:self.change_page(1)).pack(side='left')
        split.add(middle,weight=2)
        self.values=self.tree_panel(split,('property','value','status'),(('property','PROPERTY',340),('value','VALUE',140),('status','MEANING / STATUS',220)))
        self.values.bind('<Double-1>',self.edit)
        ttk.Label(self,text=tr('Double-click a verified property to edit. Unresolved names, references and unsupported layouts are read-only. '
                  'Custom entry names change display labels only. Export saves a new verified file, not the installed game.'),
                  style='Muted.TLabel',wraplength=1300).grid(row=3,column=0,sticky='w',padx=14,pady=10)
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.update_idletasks();app._dark_titlebar(self)
        default=core.game_dir(app.cfg)/'data/game'
        if default.is_dir():self.after(50,lambda:self.load_database(default))

    def tree_panel(self,parent,columns,spec,grid=False):
        frame=ttk.Frame(parent);frame.columnconfigure(0,weight=1);frame.rowconfigure(0,weight=1)
        tree=ttk.Treeview(frame,columns=columns,show='headings',selectmode='browse')
        for key,title,width in spec:tree.heading(key,text=tr(title));tree.column(key,width=width,minwidth=80)
        tree.grid(row=0,column=0,sticky='nsew');scroll=ttk.Scrollbar(frame,command=tree.yview);scroll.grid(row=0,column=1,sticky='ns');tree.configure(yscrollcommand=scroll.set)
        horizontal=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview);horizontal.grid(row=1,column=0,sticky='ew');tree.configure(xscrollcommand=horizontal.set)
        if grid:frame.grid(row=1,column=0,sticky='nsew')
        else:parent.add(frame,weight=1 if columns==('name',) else 3)
        return tree

    def run(self,work,done):
        if self.busy:return
        self.busy=True;self.status.configure(text=tr('Loading / verifying…'))
        self.app._begin_loading(self, self.winfo_toplevel())
        def worker():
            try:result,error=work(),None
            except Exception as exc:result,error=None,str(exc)
            self.after(0,lambda:finish(result,error))
        def finish(result,error):
            self.busy=False
            self.app._end_loading(self)
            try:
                if error:raise ValueError(error)
                done(result)
            except Exception as exc:self.status.configure(text=tr(str(exc)));messagebox.showerror(tr('Native Editor'),tr(str(exc)),parent=self)
        threading.Thread(target=worker,daemon=True).start()

    def discard(self):
        return not self.document or not self.document.data.replacements or messagebox.askyesno(tr('Staged changes'),tr('Discard the current staged changes?'),parent=self)

    def open_database(self):
        if self.busy:return
        path=filedialog.askdirectory(parent=self,title=tr('Choose the data/game folder'))
        if path:self.load_database(Path(path))

    def load_database(self,path):
        if self.busy or not self.discard():return
        def loaded(library):
            self.library=library;self.library_path=path/'dl_library.dl_typelib'
            self.document=None;self.current=None;self.entries.delete(*self.entries.get_children());self.values.delete(*self.values.get_children());self.files.delete(*self.files.get_children())
            self.paths={str(i):p for i,p in enumerate(sorted(path.glob('generated_*.dl_bin')))}
            for key,p in self.paths.items():self.files.insert('','end',iid=key,values=(friendly(p.name.removeprefix('generated_').removesuffix('.dl_bin')),))
            self.status.configure(text=tr(f'{len(self.paths)} data files · schema loaded from {self.library_path}. Select a file.'))
        self.run(lambda:Library.open(path/'dl_library.dl_typelib'),loaded)

    def open_library(self):
        if self.busy:return
        path=filedialog.askopenfilename(parent=self,title=tr('Choose the matching dl_library.dl_typelib'))
        if path:
            if not self.discard():return
            def loaded(lib):
                self.library=lib;self.library_path=Path(path);self.document=None;self.current=None
                self.entries.delete(*self.entries.get_children());self.values.delete(*self.values.get_children())
                self.status.configure(text=tr('Type library loaded. Open a data file from the same game version.'))
            self.run(lambda:Library.open(path),loaded)

    def open_file(self):
        if self.busy:return
        path=filedialog.askopenfilename(parent=self,title=tr('Open generated data'),filetypes=[('Sealed data','*.dl_bin'),('All files','*')])
        if path:self.load(Path(path))

    def choose_file(self,event=None):
        selected=self.files.selection()
        if selected and not self.busy:self.load(self.paths[selected[0]])

    def load(self,path):
        if self.busy or not self.discard():return
        if not self.library:
            candidate=Path(path).parent/'dl_library.dl_typelib'
            if not candidate.is_file():messagebox.showinfo(tr('Schema required'),tr('Load the matching dl_library.dl_typelib first.'),parent=self);return
        else:candidate=None
        def work():
            library=self.library or Library.open(candidate)
            return library,Document(path,library)
        def loaded(result):
            self.library,self.document=result
            if candidate:self.library_path=candidate
            self.current=None;self.values.delete(*self.values.get_children());self.filter_entries()
            count=sum(e.named for e in self.document.entries)
            mapped=sum(e.mapped and not e.named for e in self.document.entries)
            self.status.configure(text=tr(f'{Path(path).name} · {len(self.document.entries):,} entries · {count:,} resolved names · {mapped:,} mapped records. Unknown names remain explicit.'))
        self.run(work,loaded)

    def alias_key(self,entry):
        if not hasattr(self.document,'alias_id'):
            self.document.alias_id=hashlib.sha256(self.document.data.plain).hexdigest()[:24]
        return f'{self.document.data.path.name}:{self.document.alias_id}:{entry.block}:{entry.offset}:{entry.type_id}'

    def label(self,entry):
        aliases=self.app.cfg.get('native_entry_aliases',{})
        return aliases.get(self.alias_key(entry),entry.label)

    def filter_entries(self):
        if not self.document:return
        query=self.search.get().casefold()
        self.filtered=[i for i,e in enumerate(self.document.entries) if query in self.label(e).casefold()]
        self.page=0;self.show_page()

    def show_page(self):
        self.current=None;self.props=[];self.values.delete(*self.values.get_children())
        self.entries.delete(*self.entries.get_children())
        start=self.page*self.PAGE
        for index in self.filtered[start:start+self.PAGE]:self.entries.insert('','end',iid=str(index),values=(self.label(self.document.entries[index]),))
        self.page_label.configure(text=tr(f'{start+1 if self.filtered else 0}–{min(start+self.PAGE,len(self.filtered))} / {len(self.filtered):,}'))

    def change_page(self,delta):
        if self.filtered:self.page=max(0,min((len(self.filtered)-1)//self.PAGE,self.page+delta));self.show_page()

    def choose_entry(self,event=None):
        selected=self.entries.selection()
        if not selected or self.busy:return
        self.current=int(selected[0]);self.refresh_properties()

    def refresh_properties(self):
        entry=self.document.entries[self.current]
        self.props=self.document.properties(entry);self.values.delete(*self.values.get_children())
        for i,prop in enumerate(self.props):
            value=format(prop.value,'.9g') if isinstance(prop.value,float) else str(prop.value)
            self.values.insert('','end',iid=str(i),values=(prop.label,value,prop.note or ('Editable' if prop.editable else 'Read-only')))
        self.status.configure(text=tr(f'{self.label(entry)} · {sum(p.editable for p in self.props)} verified editable properties / {len(self.props)} displayed'))

    def edit(self,event=None):
        if self.busy or not self.document or not self.values.selection():return
        prop=self.props[int(self.values.selection()[0])]
        if not prop.editable:messagebox.showinfo(tr('Read-only property'),tr(prop.note or 'This property cannot be edited safely by name.'),parent=self);return
        self.property_dialog(prop)

    def property_dialog(self,prop):
        win=tk.Toplevel(self);win.title(tr('Edit property'));win.transient(self);win.configure(bg=self.app.theme['bg'])
        panel=ttk.Frame(win,padding=18);panel.pack(fill='both',expand=True)
        ttk.Label(panel,text=tr(prop.label),wraplength=530,font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(0,12))
        options=self.library.enum_values.get(prop.enum_type)
        choice=tk.StringVar(value=str(prop.value));lookup={}
        if options is not None:
            names=self.library.enums.get(prop.enum_type,{})
            lookup={f'{names.get(value,"Name unresolved")}  ({value})':str(value) for value in sorted(options)}
            control=ttk.Combobox(panel,textvariable=choice,values=list(lookup),state='readonly',width=65)
            choice.set(next((label for label,value in lookup.items() if value==str(prop.value)),str(prop.value)))
        else:control=ttk.Entry(panel,textvariable=choice,width=65)
        control.pack(fill='x',pady=(0,10));control.focus_set()
        ttk.Label(panel,text=tr(prop.note or 'Changes are staged until you export a file.'),wraplength=530,style='Muted.TLabel').pack(anchor='w')
        buttons=ttk.Frame(panel);buttons.pack(fill='x',pady=(16,0))
        def save():
            value=lookup.get(choice.get(),choice.get())
            try:self.document.edit(prop,value);self.refresh_properties()
            except Exception as exc:messagebox.showerror(tr('Invalid value'),tr(str(exc)),parent=win);return
            win.destroy()
        ttk.Button(buttons,text=tr('Save change'),command=save,style='Accent.TButton').pack(side='right')
        ttk.Button(buttons,text=tr('Cancel'),command=win.destroy).pack(side='right',padx=8)
        win.bind('<Return>',lambda _:save());win.bind('<Escape>',lambda _:win.destroy())
        win.update_idletasks();w=max(560,win.winfo_reqwidth());h=win.winfo_reqheight()
        win.geometry(f'{w}x{h}+{(win.winfo_screenwidth()-w)//2}+{(win.winfo_screenheight()-h)//2}')
        self.app._dark_titlebar(win);win.grab_set()
        return win

    def rename(self):
        if self.busy or self.current is None:return
        entry=self.document.entries[self.current]
        value=simpledialog.askstring(tr('Custom entry name'),tr('Display label (does not alter game IDs):'),initialvalue=self.label(entry),parent=self)
        if value and value.strip():
            self.app.cfg.setdefault('native_entry_aliases',{})[self.alias_key(entry)]=value.strip();core.save_config(self.app.cfg);self.filter_entries()

    def coverage(self):
        if not self.library:return
        lib=self.library;total=sum(len(t.members) for t in lib.types.values());named=sum(m.trusted for t in lib.types.values() for m in t.members)
        text=f'Type library: {len(lib.types):,} types\nVerified property labels: {named:,} / {total:,}\n\nThe game library has stripped field-name strings. Unresolved properties remain read-only; labels are not invented.'
        if self.document:text+=f'\n\nCurrent file: {len(self.document.entries):,} records, {sum(e.named for e in self.document.entries):,} resolved names, {sum(e.mapped and not e.named for e in self.document.entries):,} mapped records.\nMappings include resource IDs, enum identities, collection containers and empty slots. They do not resolve unknown field meanings.\n'+ '\n'.join(self.document.issues[:8])
        messagebox.showinfo(tr('Schema coverage'),tr(text),parent=self)

    def export(self):
        if self.busy or not self.document:return
        path=filedialog.asksaveasfilename(parent=self,title=tr('Export a verified mod copy'),initialfile=self.document.data.path.name,defaultextension='.dl_bin')
        if not path:return
        if Path(path).resolve()==self.document.data.path.resolve():messagebox.showerror(tr('Export'),tr('Choose a new folder to preserve the original.'),parent=self);return
        game=self.app.cfg.get('game')
        if game and Path(path).resolve().is_relative_to(Path(game).resolve()):
            messagebox.showerror(tr('Export'),tr('Export outside the game folder, then import the mod through Mod Library.'),parent=self);return
        def saved(result):
            sealed,adjustments=result
            if adjustments and not messagebox.askyesno(tr('Hash correction adjustments'),tr('An edited float requires a small adjustment:\n'+'\n'.join(adjustments)+'\n\nSave this result?'),parent=self):return
            self.document.data.save(path,sealed);self.status.configure(text=tr('Verified export saved: '+path))
        allow_footer=self.footer.get()
        if allow_footer and not messagebox.askyesno(tr('Experimental schema footer'),
            tr('This export may append hash-correction padding to a validated variable-sized final block. Edited values remain exact, but this method has not been tested in-game for every file type. Continue?'),parent=self):return
        self.run(lambda:self.document.prepare(allow_footer=allow_footer),saved)

    def close(self):
        if self.busy:messagebox.showinfo(tr('Working'),tr('Wait for the current operation to finish.'),parent=self);return
        if self.discard():self.destroy()
