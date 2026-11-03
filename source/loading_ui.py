"""Shared themed loading indicator; no guessed percentages for unmeasured work."""
import tkinter as tk
import math


class LoadingBrand(tk.Frame):
    """Shared themed text title followed by the flask icon."""
    def __init__(self, parent, background, secondary):
        super().__init__(parent, bg=background)
        self.label = tk.Label(self, text='MODDIVER LABORATORY', bd=0,
                              font=('Segoe UI Semibold', 16))
        self.label.pack(side='left')
        self.flask = tk.Label(self, bd=0)
        self.flask.pack(side='left', padx=(8, 0))
        self.set_theme(background, secondary)

    def set_theme(self, background, secondary):
        import nav_icons
        self.configure(bg=background)
        self.label.configure(bg=background, fg=secondary)
        self.icon = nav_icons.make_icon(self, 'flask', secondary)
        self.flask.configure(bg=background, image=self.icon)


def blend(a, b, amount):
    return '#' + ''.join(f'{round(int(a[i:i+2],16)*(1-amount)+int(b[i:i+2],16)*amount):02x}' for i in (1,3,5))


def luminance(color):
    channels = [int(color[i:i+2],16)/255 for i in (1,3,5)]
    linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in channels]
    return sum(a*b for a,b in zip(linear,(.2126,.7152,.0722)))


def contrast(a, b):
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light+.05)/(dark+.05)


def visible(color, background, minimum=3):
    if contrast(color, background) >= minimum:
        return color
    target = '#ffffff' if luminance(background) < .179 else '#000000'
    for step in range(1,21):
        candidate = blend(color, target, step/20)
        if contrast(candidate, background) >= minimum:
            return candidate
    return target


class LoadingBar(tk.Canvas):
    """Theme-coloured gradient rail with bounded animation and readable status."""
    def __init__(self, parent, background='#080808', **kw):
        self.value = None
        self.phase = 0
        self.caption = 'Working'
        self.timer = None
        self.accent = kw.pop('accent', None)
        kw.setdefault('height', 56)
        kw.setdefault('width', 300)
        super().__init__(parent, bg=background, highlightthickness=0, bd=0, **kw)
        self.bind('<Configure>', lambda event: self.draw())
        self.bind('<Destroy>', self._destroyed, add='+')

    def configure(self, cnf=None, **kw):
        if 'value' in kw:
            value = kw.pop('value')
            self.value = None if value is None else max(0, min(100, float(value)))
        if 'caption' in kw:
            self.caption = kw.pop('caption')
        if 'accent' in kw:
            self.accent = kw.pop('accent')
        kw.pop('maximum', None)
        result = super().configure(cnf, **kw)
        self.draw()
        return result

    config = configure

    def __getitem__(self, key):
        return self.value if key == 'value' else super().__getitem__(key)

    def draw(self):
        w, h = max(30, self.winfo_width()), max(48, self.winfo_height())
        raw_bg = self.winfo_rgb(self.cget('bg'))
        background = '#' + ''.join(f'{channel//256:02x}' for channel in raw_bg)
        theme = getattr(self.winfo_toplevel(), 'theme', {})
        accent = visible(self.accent or theme.get('accent', '#ffd400'), background)
        ink = visible(theme.get('text', '#ffffff'), background, 4.5)
        muted = visible(theme.get('muted', '#aab3c2'), background, 4.5)
        track_color = blend(background, ink, .18)
        if not hasattr(self, '_items'):
            track = self.create_line(0,0,0,0,width=14,capstyle='round')
            glow = self.create_line(0,0,0,0,width=14,capstyle='round')
            segments = [self.create_line(0,0,0,0,width=8,capstyle='round') for _ in range(48)]
            caption = self.create_text(0,0,anchor='w',font=('Segoe UI',10))
            value = self.create_text(0,0,anchor='e',font=('Segoe UI Semibold',10))
            self._items = track, glow, segments, caption, value
        track, glow, segments, caption, value = self._items
        left, right, y = 8, w-8, h-13
        self.coords(track,left,y,right,y)
        self.itemconfigure(track,fill=track_color)
        if self.value is None:
            span = max(10,(right-left)*.24)
            position = (1-math.cos(self.phase*math.tau/100))/2
            start = left + position*max(0,right-left-span)
            finish = min(right,start+span)
            detail = 'IN PROGRESS'
        else:
            start, finish = left, left+(right-left)*self.value/100
            detail = f'{self.value:.0f}%'
        shown = self.value != 0
        self.coords(glow,start,y,finish,y)
        self.itemconfigure(glow,fill=blend(track_color,accent,.35),state='normal' if shown else 'hidden')
        for i,item in enumerate(segments):
            a,b = i/48,(i+1)/48
            self.coords(item,start+(finish-start)*a,y,start+(finish-start)*b,y)
            self.itemconfigure(item,fill=blend(accent,ink,.25*a),state='normal' if shown else 'hidden')
        # Reserve the right-hand status column, ellipsizing long phase names.
        from tkinter import font
        if not hasattr(self, '_caption_font'):
            self._caption_font = font.Font(root=self, font=self.itemcget(caption,'font'))
            self._value_font = font.Font(root=self, font=self.itemcget(value,'font'))
        available = max(0,w-24-self._value_font.measure(detail)-20)
        caption_font = self._caption_font
        text = str(self.caption)
        if caption_font.measure(text) > available:
            while text and caption_font.measure(text+'…') > available:
                text = text[:-1]
            text = text+'…' if text else ''
        self.coords(caption,8,13)
        self.coords(value,w-8,13)
        self.itemconfigure(caption,text=text,fill=muted)
        self.itemconfigure(value,text=detail,fill=ink)

    def start(self, interval=40):
        if self.timer is None:
            self.value = None
            self._tick(interval)

    def _tick(self, interval):
        self.phase = (self.phase + 1) % 100
        self.draw()
        self.timer = self._root().after(max(16,interval),self._tick,interval)

    def stop(self):
        if self.timer is not None:
            self._root().after_cancel(self.timer)
            self.timer = None

    def _destroyed(self, event):
        if event.widget is self:
            self.stop()


def style_titlebar(window, background, foreground=None):
    """Style a standalone helper's native Windows caption after frame creation."""
    import ctypes
    try:
        rgb = [value // 256 for value in window.winfo_rgb(background)]
        if foreground is None:
            foreground = '#ffffff' if sum(rgb) < 384 else '#000000'
        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetAncestor.restype = ctypes.c_void_p
        hwnd = user32.GetAncestor(window.winfo_id(), 2)
        dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
        dwm.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        dark = ctypes.c_int(int(sum(rgb) < 384))
        dwm(hwnd, 20, ctypes.byref(dark), 4)
        for attribute, color in ((35, background), (34, background), (36, foreground)):
            r, g, b = (value // 256 for value in window.winfo_rgb(color))
            value = ctypes.c_int(r | g << 8 | b << 16)
            dwm(hwnd, attribute, ctypes.byref(value), 4)
    except (AttributeError, OSError, tk.TclError):
        pass


def run_splash(work, background='#080808', caption=None, caption_text=None, secondary='#ffd400'):
    """Keep a standalone helper responsive while filesystem work runs."""
    import threading
    root = tk.Tk()
    root.title('ModDiver Laboratory')
    root.configure(bg=background)
    root.resizable(False, False)
    root.attributes('-topmost', True)
    root.geometry('480x172+%d+%d' % ((root.winfo_screenwidth()-480)//2, (root.winfo_screenheight()-172)//2))
    from pathlib import Path
    icon = tk.PhotoImage(master=root, file=str(Path(__file__).parent / 'branding/icon_64.png'))
    root.iconphoto(True, icon)
    root.protocol('WM_DELETE_WINDOW', lambda: None)
    def mapped(event):
        if event.widget is root:
            root.after_idle(lambda: style_titlebar(root, caption or background, caption_text))
    root.bind('<Map>', mapped, add='+')
    LoadingBrand(root, background, secondary).pack(pady=(22, 8))
    bar = LoadingBar(root, background, accent=secondary)
    bar.pack(fill='x', padx=30, pady=(0, 22))
    bar.start()
    result = []
    def worker():
        try: result.append((work(), None))
        except BaseException as exc: result.append((None, exc))
    def poll():
        if result: root.destroy()
        else: root.after(40, poll)
    threading.Thread(target=worker, daemon=True).start()
    root.after(40, poll)
    root.mainloop()
    if result[0][1]: raise result[0][1]
    return result[0][0]

