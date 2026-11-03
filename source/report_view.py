"""Selectable, scrollable read-only report with a transparent watermark.

Tk Text cannot draw an image behind its text. Keep a native Text model for
content/tags and render only visible report lines over a Canvas watermark.
"""
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont


class ReportView(tk.Canvas):
    def __init__(self, parent, **kw):
        self.background_folder = kw.pop('background_folder', 'bot_background')
        super().__init__(parent, bd=0, highlightthickness=0, takefocus=True, cursor='xterm')
        self.model = tk.Text(self, **kw)
        self._lines = []
        self._selection = (0, 0)
        self._pending = None
        self._background_size = None
        self._background_item = self.create_image(0, 0, anchor='center')
        self.bind('<Configure>', lambda e: self._schedule())
        self.bind('<MouseWheel>', self._wheel)
        self.bind('<Button-4>', lambda e: self.yview_scroll(-3, 'units'))
        self.bind('<Button-5>', lambda e: self.yview_scroll(3, 'units'))
        self.bind('<Button-1>', self._press)
        self.bind('<B1-Motion>', self._drag)
        self.bind('<Control-a>', self._select_all)
        self.bind('<Control-c>', self._copy)
        self.bind('<Control-Insert>', self._copy)
        self.bind('<Prior>', lambda e: self.yview_scroll(-1, 'pages'))
        self.bind('<Next>', lambda e: self.yview_scroll(1, 'pages'))
        self.bind('<Up>', lambda e: self.yview_scroll(-1, 'units'))
        self.bind('<Down>', lambda e: self.yview_scroll(1, 'units'))
        self.bind('<Home>', lambda e: self.yview_moveto(0))
        self.bind('<End>', lambda e: self.yview_moveto(1))
        self.bind('<Destroy>', self._destroyed, add='+')
        self.configure(bg=self.model.cget('bg'))

    def _destroyed(self, event):
        if event.widget is self and self._pending is not None:
            self._root().after_cancel(self._pending)
            self._pending = None

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        if not kw:
            return self.model.configure()
        canvas = {key: kw.pop(key) for key in ('yscrollcommand',) if key in kw}
        self.model.configure(**kw)
        canvas['bg'] = self.model.cget('bg')
        super().configure(**canvas)
        self._schedule()

    config = configure

    def cget(self, key):
        return self.model.cget(key)

    def insert(self, *args):
        self.model.insert(*args)
        self._schedule()

    def delete(self, *args):
        self.model.delete(*args)
        self._selection = (0, 0)
        super().yview_moveto(0)
        self._schedule()

    def get(self, *args):
        return self.model.get(*args)

    def tag_configure(self, *args, **kw):
        result = self.model.tag_configure(*args, **kw)
        self._schedule()
        return result

    tag_config = tag_configure

    def tag_names(self, *args):
        return self.model.tag_names(*args)

    def tag_cget(self, *args):
        return self.model.tag_cget(*args)

    def tag_ranges(self, *args):
        return self.model.tag_ranges(*args)

    def index(self, *args):
        return self.model.index(*args)

    def search(self, *args, **kw):
        return self.model.search(*args, **kw)

    def see(self, index):
        self._scroll_to_end = self.model.compare(index, '>=', 'end-1c')
        self._schedule()

    def _schedule(self):
        if self._pending is None:
            self._pending = self._root().after_idle(self._layout)

    def _layout(self):
        self._pending = None
        self._font = tkfont.Font(self, font=self.model.cget('font'))
        self._line_height = self._font.metrics('linespace') + 3
        self._text = self.model.get('1.0', 'end-1c')
        available = max(20, self.winfo_width()-24)
        self._lines = []
        offset = 0
        for physical in self._text.split('\n'):
            start = 0
            while start < len(physical) or start == 0:
                low, high = 1, len(physical)-start
                while low < high:
                    middle = (low+high+1)//2
                    if self._font.measure(physical[start:start+middle]) <= available:
                        low = middle
                    else:
                        high = middle-1
                end = min(len(physical), start+low)
                if end < len(physical):
                    space = physical.rfind(' ', start, end)
                    if space > start:
                        end = space+1
                self._lines.append((offset+start, offset+end, physical[start:end]))
                if end >= len(physical):
                    break
                start = end
            offset += len(physical)+1
        height = max(self.winfo_height(), 20+len(self._lines)*self._line_height)
        super().configure(scrollregion=(0, 0, self.winfo_width(), height),
                          yscrollincrement=self._line_height)
        if getattr(self, '_scroll_to_end', False):
            super().yview_moveto(1)
            self._scroll_to_end = False
        self._paint()

    def _paint(self):
        if not self._lines:
            return
        width, height = self.winfo_width(), self.winfo_height()
        sizes = (320, 480, 640, 800, 960, 1280, 1600, 1920)
        desired = min(width, height*1920/1080)
        size = min(sizes, key=lambda n: abs(n-desired))
        if size != self._background_size:
            self._background_size = size
            self._background = tk.PhotoImage(master=self, file=str(
                Path(__file__).parent/self.background_folder/f'{size}.png'))
            self.itemconfigure(self._background_item, image=self._background)
        top = self.canvasy(0)
        self.coords(self._background_item, width/2, top+height/2)
        self.tag_lower(self._background_item)
        super().delete('report-line')
        first = max(0, int((top-10)//self._line_height))
        last = min(len(self._lines), int((top+height)//self._line_height)+1)
        a, b = sorted(self._selection)
        for number in range(first, last):
            start, end, text = self._lines[number]
            y = 10+number*self._line_height
            color = self.model.cget('fg')
            for tag in self.model.tag_names(f'1.0 + {start} chars'):
                color = self.model.tag_cget(tag, 'foreground') or color
            self.create_text(12, y, text=text, fill=color, font=self._font, anchor='nw', tags='report-line')
            left, right = max(start, a), min(end, b)
            if left < right:
                x = 12+self._font.measure(text[:left-start])
                selected = text[left-start:right-start]
                self.create_rectangle(x, y, x+self._font.measure(selected), y+self._line_height,
                                      fill=self.model.cget('selectbackground'), outline='', tags='report-line')
                self.create_text(x, y, text=selected, fill=self.model.cget('selectforeground'),
                                 font=self._font, anchor='nw', tags='report-line')

    def yview(self, *args):
        result = super().yview(*args)
        if args:
            self._paint()
        return result

    def yview_scroll(self, *args):
        super().yview_scroll(*args)
        self._paint()

    def yview_moveto(self, *args):
        super().yview_moveto(*args)
        self._paint()

    def _wheel(self, event):
        direction = -1 if event.delta > 0 else 1
        self.yview_scroll(direction*max(1, abs(event.delta)//120)*3, 'units')
        return 'break'

    def _offset(self, event):
        if not self._lines:
            return 0
        line = max(0, min(len(self._lines)-1, int((self.canvasy(event.y)-10)//self._line_height)))
        start, end, text = self._lines[line]
        x = max(0, event.x-12)
        count = min(range(len(text)+1), key=lambda n: abs(self._font.measure(text[:n])-x))
        return start+count

    def _press(self, event):
        self.focus_set()
        self._anchor = self._offset(event)
        self._selection = (self._anchor, self._anchor)
        self._paint()

    def _drag(self, event):
        if event.y < 0 or event.y > self.winfo_height():
            self.yview_scroll(-1 if event.y < 0 else 1, 'units')
        self._selection = (self._anchor, self._offset(event))
        self._paint()

    def _select_all(self, event=None):
        self._selection = (0, len(self._text))
        self._paint()
        return 'break'

    def _copy(self, event=None):
        a, b = sorted(self._selection)
        if a != b:
            self.clipboard_clear()
            self.clipboard_append(self._text[a:b])
        return 'break'
