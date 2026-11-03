"""Full-screen Visual & Audio editor hosted in the existing application surface."""
from localization import tr
from tkinter import ttk
from choice_screen import ChoiceScreen
from panel_dialogs import filedialog, messagebox
from native_asset_editor import NativeEditor
from audio_workspace import AudioWorkspace
from studio_finish import Finish
from studio_guide import Guide


class Editor(ChoiceScreen):
    def __new__(cls, app):
        current = getattr(app, '_asset_workspace', None)
        if current is not None and current.winfo_exists():
            return current
        return super().__new__(cls)

    def __init__(self, app):
        current = getattr(app, '_asset_workspace', None)
        if current is not None and current.winfo_exists():
            current.lift()
            return
        super().__init__(app)
        app._asset_workspace = self
        self.card.place_configure(x=0, y=0, relx=0, rely=0, relwidth=1, relheight=1, anchor='nw')
        body = ttk.Frame(self.card, padding=16); body.pack(fill='both', expand=True, padx=1, pady=1)
        header = ttk.Frame(body); header.pack(fill='x', pady=(0, 12))
        ttk.Label(header, text=tr('AUDIO STUDIO'), style='Title.TLabel').pack(side='left')
        ttk.Button(header, text=tr('Back to Mod Creator'), command=self.close).pack(side='right')
        ttk.Button(header, text=tr('Guide & shortcuts  ·  F1'), command=self.show_guide).pack(side='right', padx=8)
        ttk.Button(header, text=tr('Finish & export  ·  Ctrl+E'), command=self.show_finish).pack(side='right')
        self.tabs = ttk.Notebook(body); self.tabs.pack(fill='both', expand=True)
        self.audio = AudioWorkspace(self.tabs, app)
        self.native = NativeEditor(app, self.tabs)
        self.tabs.add(self.audio, text=tr('  Audio studio  '))
        self.tabs.add(self.native, text=tr('  Visual assets · Advanced  '))
        self.finish = Finish(self.tabs, self)
        self.guide = Guide(self.tabs, app)
        self.tabs.add(self.finish, text=tr('  Finish & export  '))
        self.tabs.add(self.guide, text=tr('  Guide & shortcuts  '))
        self.audio.finish_export = self.native.finish_export = self.show_finish
        self.audio.show_guide = self.show_guide
        self.tabs.bind('<<NotebookTabChanged>>', self.tab_changed)
        self.activate(self.audio.browser)
        for sequence, action in (('<F1>', self.show_guide), ('<Control-e>', self.show_finish),
             ('<Control-n>', self.audio.new_project), ('<Control-o>', self.open_current),
             ('<Control-i>', self.audio.assign), ('<Control-f>', lambda: self.search_sounds(False)),
             ('<Control-Shift-F>', lambda: self.search_sounds(True)), ('<Control-z>', lambda: self.audio.edit('undo')),
             ('<Control-y>', lambda: self.audio.edit('redo')), ('<Control-Shift-Z>', lambda: self.audio.edit('redo')),
             ('<Control-a>', self.select_all), ('<space>', self.play_stop), ('<Escape>', self.audio.stop),
             ('<Control-w>', self.close)):
            self.bind(sequence, lambda event, action=action, sequence=sequence: self.shortcut(event, action, sequence))
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.bind(sequence, self.scroll_finish)

    def scroll_finish(self, event):
        if self.tabs.select() != str(self.finish): return
        amount = -1 if getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0 else 1
        self.finish.canvas.yview_scroll(amount*3, 'units')
        return 'break'

    def tab_changed(self, event=None):
        if self.tabs.select() != str(self.audio): self.audio.stop()
        if self.tabs.select() == str(self.finish): self.finish.refresh()

    def show_finish(self):
        self.finish.refresh(); self.tabs.select(self.finish)

    def show_guide(self):
        self.tabs.select(self.guide)

    def open_current(self):
        if self.tabs.select() == str(self.native): self.native.open()
        else: self.audio.open_project()

    def search_sounds(self, collections=False):
        self.tabs.select(self.audio)
        field = self.audio.collection_search_entry if collections else self.audio.sound_search_entry
        field.focus_set(); field.selection_range(0, 'end')

    def select_all(self):
        if self.focus_get() is not self.audio.sounds: return
        self.audio.sounds.selection_set(self.audio.sounds.get_children())

    def play_stop(self):
        if self.focus_get() is not self.audio.sounds: return
        if self.audio.play_started is not None: self.audio.stop(); return
        row = self.audio.current()
        if row:
            sid = row['source']
            edited = sid in self.audio.state['assignments'] or sid in self.audio.state['gains']
            self.audio.preview('edited' if edited else 'original', True)

    def shortcut(self, event, action, sequence):
        if self.app._choice_screen is not self: return
        text = event.widget.winfo_class() in ('Entry', 'TEntry', 'Text', 'TSpinbox', 'Spinbox', 'TCombobox')
        if text and sequence in ('<space>', '<Control-a>', '<Control-z>', '<Control-y>', '<Control-Shift-Z>'): return
        if sequence in ('<space>', '<Control-a>') and event.widget is not self.audio.sounds: return
        if self.busy and sequence not in ('<F1>', '<Escape>'): return 'break'
        action()
        return 'break'

    def _layout(self, event=None):
        # This workspace uses the whole main-window surface, including fullscreen.
        self.card.place_configure(x=0, y=0, relx=0, rely=0, relwidth=1, relheight=1, anchor='nw', width=0, height=0)

    @property
    def busy(self):
        return self.audio.busy or self.native.busy or getattr(getattr(self, 'finish', None), 'busy', False)

    def has_unsaved_changes(self):
        return self.native.has_unsaved_changes()

    def close(self, event=None):
        if self.busy:
            self.audio.status.set('Wait for the current operation to finish before leaving the studio.')
            return 'break'
        if self.native.confirm_discard():
            self.destroy()
        return 'break'

    def destroy(self):
        if getattr(self.app, '_asset_workspace', None) is self:
            self.app._asset_workspace = None
        super().destroy()
