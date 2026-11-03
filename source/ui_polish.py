"""Theme-aware page surfaces and consistent action icons for native Tk widgets."""
from localization import tr
import tkinter as tk
from tkinter import ttk
import nav_icons


def creator_layout(body):
    """Wrap related actions within cards instead of clipping at small sizes."""
    def visit(frame):
        children = frame.winfo_children()
        if (len(children) > 1 or getattr(frame, '_flow_single', False)) and all(isinstance(child, ttk.Button) for child in children):
            for child in children:
                child.pack_forget()
            if frame.winfo_manager() == 'pack':
                frame.pack_configure(fill='x')
            def arrange(event=None):
                if not frame.winfo_exists(): return
                width = max(1, frame.winfo_width())
                preferred = max(child.winfo_reqwidth() for child in children) + 12
                columns = max(1, min(len(children), width // preferred))
                if getattr(frame, '_flow_columns', None) == columns:
                    return
                frame._flow_columns = columns
                for index, child in enumerate(children):
                    child.grid(row=index // columns, column=index % columns, sticky='w' if len(children) == 1 else 'ew', padx=(0, 8), pady=(0, 8))
                for index in range(len(children)):
                    frame.columnconfigure(index, weight=1 if index < columns else 0)
            frame.bind('<Configure>', arrange, add='+')
            frame._root().after_idle(arrange)
        for child in children:
            visit(child)
    visit(body)


def mix(a, b, fraction):
    a = tuple(int(a[i:i+2], 16) for i in (1, 3, 5))
    b = tuple(int(b[i:i+2], 16) for i in (1, 3, 5))
    return '#' + ''.join(f'{round(x+(y-x)*fraction):02x}' for x, y in zip(a, b))


ACTION_STYLES = {'primary': 'Action.Primary.TButton', 'export': 'Action.Export.TButton',
                 'danger': 'Action.Danger.TButton', 'secondary': 'Action.Secondary.TButton'}


def action_styles(app):
    t, style = app.theme, app.style
    palettes = {'primary': ('#ffd400', '#000000', '#111111'),
                'export': ('#247848', '#30935c', '#ffffff'),
                'danger': ('#b83242', '#d24858', '#ffffff'),
                'secondary': (t['panel2'], t['panel'], t['text'])}
    for role, (base, hover, text) in palettes.items():
        style.configure(ACTION_STYLES[role], background=base, foreground=text, borderwidth=0,
                        bordercolor=base, lightcolor=base, darkcolor=base,
                        padding=(12, 8), font=('Segoe UI Semibold', int(t.get('font', 10))))
        style.map(ACTION_STYLES[role], background=[('disabled', t['panel2']), ('pressed', hover), ('active', hover)],
                  foreground=[('disabled', t['muted'])] + ([('active', '#ffd400'), ('pressed', '#ffd400')] if role == 'primary' else []), bordercolor=[('disabled', t['panel2']), ('active', hover)])
    style.configure('Studio.Card.TFrame', background=t['panel'])
    style.configure('Studio.Card.TLabel', background=t['panel'], foreground=t['text'])
    style.configure('Studio.Muted.TLabel', background=t['panel'], foreground=t['muted'])


def action_button(app, parent, text, command, role='secondary', icon=None, **kwargs):
    button = ttk.Button(parent, text=tr(text), command=command, style=ACTION_STYLES[role], **kwargs)
    button._semantic_role = role
    if icon:
        button._action_icon_name = icon
        update_icon(app, button)
    return button


def decorate(app, widget):
    if not isinstance(widget, ttk.Button):
        return
    label = str(widget.cget('text')).lower()
    command = str(widget.cget('command')).lower()
    role = getattr(widget, '_semantic_role', None)
    if role is None:
        if any(word in label for word in ('delete', 'purge', 'remove mod', 'mute sound', 'uninstall')):
            role = 'danger'
        elif any(word in label for word in ('export', 'build mod', 'capture game')):
            role = 'export'
        elif any(word in label for word in ('import', 'play original', 'play edited', 'open native', 'open visual', 'open audio', 'open shodan', 'open ccm', 'replace from donor', 'open mod zip', 'use selected replacement')):
            role = 'primary'
    if role:
        widget.configure(style=ACTION_STYLES[role])
    if hasattr(widget, '_action_icon_name'):
        update_icon(app, widget)
        return
    if widget.cget('image') or getattr(widget, '_no_action_icon', False):
        return
    name = None
    for keywords, icon in ((('play ',), 'play'), (('stop',), 'stop'), (('undo',), 'undo'), (('redo',), 'redo'),
                           (('trim',), 'scissors'), (('volume', 'gain'), 'volume'), (('new project', 'new audio'), 'plus'),
                           (('select all',), 'check_all'), (('clear all',), 'clear_all'),
                           (('save',), 'save'), (('find', 'search', 'scan'), 'search'),
                           (('export', 'build mod'), 'export'), (('import', 'add_'), 'import'),
                           (('folder', 'archive'), 'folder'), (('install', 'deploy', 'capture'), 'deploy'),
                           (('purge', 'delete', 'remove'), 'trash'), (('update', 'repair', 'restart', 'refresh'), 'about'),
                           (('audio', 'sound'), 'waveform'), (('editor', 'preset'), 'tools'),
                           (('log', 'copy', 'report'), 'log'), (('back',), 'back'),
                           (('help', 'guide'), 'info'), (('configure', 'settings'), 'settings'),
                           (('support', 'browser', 'download'), 'globe')):
        if any(word in command + ' ' + label for word in keywords):
            name = icon
            break
    if name:
        widget._action_icon_name = name
        update_icon(app, widget)


def update_icon(app, widget):
    style = widget.cget('style') or 'TButton'
    color = app.style.lookup(style, 'foreground') or app.theme['text']
    if getattr(widget, '_icon_hover', False) and style in ('Yellow.TButton', 'Action.Primary.TButton', 'Accent.TButton', 'Options.TButton'):
        color = app.style.lookup(style, 'foreground', ('active',)) or color
    if not getattr(widget, '_icon_hover_bound', False):
        widget._icon_hover_bound = True
        def hover(active):
            widget._icon_hover = active
            update_icon(app, widget)
        widget.bind('<Enter>', lambda e: hover(True), add='+')
        widget.bind('<Leave>', lambda e: hover(False), add='+')
    key = (widget._action_icon_name, color)
    if getattr(widget, '_action_icon_key', None) == key:
        return
    widget._action_icon_key = key
    widget._action_icon = nav_icons.make_icon(app, widget._action_icon_name, color)
    widget.configure(image=widget._action_icon, compound='left')


def schedule(app):
    if getattr(app, '_polish_pending', None):
        app.after_cancel(app._polish_pending)
    app._polish_pending = app.after(80, lambda: refresh(app))


def refresh(app):
    """Native surfaces avoid allocating full-window images on every layout event.

    Visit controls once per theme, and newly opened pages once per theme.
    No geometry-dependent repaint jobs are installed.
    """
    app._polish_pending = None
    if not hasattr(app, 'pages'):
        return
    theme = tuple(sorted(app.theme.items()))
    changed = getattr(app, '_polish_theme', None) != theme
    app._polish_theme = theme
    page = app.pages.get(app.current)
    target = app if changed else page
    if target is None:
        return
    def visit(widget):
        if not changed and getattr(widget, '_polish_seen', None) == theme:
            return
        if isinstance(widget, ttk.Button):
            decorate(app, widget)
            if hasattr(widget, '_action_icon_name'):
                update_icon(app, widget)
        if getattr(widget, '_theme_background', False):
            widget.configure(bg=app.theme['bg'])
        for child in widget.winfo_children():
            visit(child)
        widget._polish_seen = theme
    visit(target)
    if hasattr(app, 'mod_canvas'):
        paint_library(app)
        paint_library_chrome(app)


def paint_library_chrome(app):
    """Carry the library surface through the title and toolbar to the top edge."""
    top, bottom = app.mod_canvas._library_palette
    surface = app.main_surface
    height = max(1, surface.winfo_height())
    widgets = [surface, app.content, app.title_label.master, app.title_label,
               app.subtitle_label, app.status]
    page = app.pages['mods']
    widgets += [page]
    def collect(frame):
        if isinstance(frame, ttk.Frame):
            for child in frame.winfo_children():
                if isinstance(child, (ttk.Frame, ttk.Label)):
                    widgets.append(child)
                    collect(child)
    collect(page)
    for widget in dict.fromkeys(widgets):
        if not widget.winfo_exists():
            continue
        base = getattr(widget, '_library_original_style', None)
        if base is None:
            base = widget.cget('style') or widget.winfo_class()
            widget._library_original_style = base
        if app.current != 'mods':
            widget.configure(style=base)
            background = getattr(widget, '_library_surface_canvas', None)
            if background is not None:
                background.place_forget()
            continue
        offset = widget.winfo_rooty() - surface.winfo_rooty()
        fraction = offset / height
        color = mix(top, bottom, max(0, min(1, fraction)))
        style = f'LibrarySurface{str(widget).replace(".", "_")}.{base}'
        app.style.configure(style, background=color)
        widget.configure(style=style)
        if isinstance(widget, ttk.Frame):
            # A placed canvas paints behind the controls without participating
            # in requested sizes. Image-backed ttk elements can feed their
            # rendered dimensions back into geometry and stall the event loop.
            background = getattr(widget, '_library_surface_canvas', None)
            if background is None:
                background = tk.Canvas(widget, width=1, height=1, bd=0, highlightthickness=0, background=color)
                background._bands = [background.create_rectangle(0, 0, 0, 0, outline='')
                                     for _ in range(96)]
                widget._library_surface_canvas = background
            background.place(x=0, y=0, relwidth=1, relheight=1)
            widget.tk.call('lower', str(background))
            width, size = max(1, widget.winfo_width()), max(1, widget.winfo_height())
            key = (top, bottom, offset, height, width, size)
            if getattr(background, '_paint_key', None) != key:
                for index, item in enumerate(background._bands):
                    y = size * index / 96
                    background.coords(item, 0, y, width, size * (index+1) / 96 + 1)
                    background.itemconfigure(item, fill=mix(top, bottom, max(0, min(1, (offset+y)/height))))
                background._paint_key = key


def position_canvas(canvas):
    bands = getattr(canvas, '_gradient_bands', ())
    if not bands:
        return
    width, height = canvas.winfo_width(), canvas.winfo_height()
    y = canvas.canvasy(0)
    for index, item in enumerate(bands):
        canvas.coords(item, 0, y+height*index/len(bands), width, y+height*(index+1)/len(bands)+1)
        canvas.tag_lower(item)
    if hasattr(canvas, '_gradient_colors'):
        top, bottom = canvas._gradient_colors
        for header in getattr(canvas, '_gradient_headers', ()):
            if not header.winfo_exists():
                continue
            fraction = min(1, max(0, (header.winfo_rooty()-canvas.winfo_rooty()+header.winfo_height()/2)/max(1, height)))
            color = mix(top, bottom, fraction)
            if header.cget('bg') != color:
                header.configure(bg=color)


def paint_library(app):
    """A fixed viewport gradient made from reusable bands, with no raster copies."""
    canvas = app.mod_canvas
    if not hasattr(canvas, '_gradient_bands'):
        canvas._gradient_bands = [canvas.create_rectangle(0, 0, 0, 0, outline='', tags='library-gradient') for _ in range(96)]
    base = app.theme['bg']
    canvas._gradient_headers = list(getattr(app, '_category_headers', {}).values())
    top = '#1a1d23' if base == '#080808' else mix(base, '#000000', .09)
    bottom = mix(base, '#ffffff', .14)
    canvas._library_palette = (top, bottom)
    # Sample the same full-height gradient below the title and actions.
    height = max(1, app.main_surface.winfo_height())
    offset = max(0, canvas.winfo_rooty() - app.main_surface.winfo_rooty())
    start = min(1, offset / height)
    stop = min(1, (offset + canvas.winfo_height()) / height)
    key = (top, bottom, start, stop)
    if getattr(canvas, '_gradient_paint_key', None) != key:
        for index, item in enumerate(canvas._gradient_bands):
            canvas.itemconfigure(item, fill=mix(top, bottom, start + (stop-start)*index/95))
        canvas._gradient_paint_key = key
    canvas._gradient_colors = (mix(top, bottom, start), mix(top, bottom, stop))
    position_canvas(canvas)
