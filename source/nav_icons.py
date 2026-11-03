"""Small theme-coloured sidebar icons, drawn without platform font dependencies."""
import math
import tkinter as tk


def make_icon(master, name, color, secondary=None):
    root = master._root()
    cache = getattr(root, '_nav_icon_cache', None)
    if cache is None:
        cache = root._nav_icon_cache = {}
    key = (name, color, secondary)
    if key in cache:
        return cache[key]
    image = tk.PhotoImage(master=root, width=24, height=24)
    cache[key] = image

    def line(*points):
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            steps = max(abs(x2-x1), abs(y2-y1), 1)
            for step in range(steps+1):
                x = round(x1+(x2-x1)*step/steps)
                y = round(y1+(y2-y1)*step/steps)
                image.put(color, to=(x, y, min(x+2, 24), min(y+2, 24)))

    def box(x1, y1, x2, y2):
        line((x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1))

    def arc(cx, cy, radius, start, end):
        line(*[(round(cx+radius*math.cos(math.radians(a))),
                round(cy+radius*math.sin(math.radians(a))))
               for a in range(start, end+1, 5)])

    if name == 'play':
        line((7, 3), (20, 11), (7, 20), (7, 3))
        for x in range(8, 17):
            extent = min(x-6, 19-x)
            image.put(color, to=(x, 11-extent//2, x+1, 13+extent//2))
    elif name == 'stop':
        image.put(color, to=(5, 5, 19, 19))
    elif name in ('waveform', 'audio'):
        for x, height in ((2, 3), (6, 7), (10, 10), (14, 5), (18, 8), (22, 3)):
            line((x, 12-height), (x, 12+height))
    elif name == 'creator':
        line((8, 1), (15, 1), (15, 4), (14, 4), (14, 9), (21, 20), (20, 22), (3, 22), (2, 20), (9, 9), (9, 4), (8, 4), (8, 1))
        line((5, 17), (8, 17), (10, 13), (12, 20), (15, 15), (17, 17))
    elif name == 'scissors':
        arc(5, 17, 3, 0, 360); arc(17, 17, 3, 0, 360)
        line((7, 14), (20, 2)); line((15, 14), (3, 2))
    elif name in ('undo', 'redo'):
        if name == 'undo':
            line((9, 3), (3, 8), (9, 13)); line((3, 8), (15, 8), (20, 12), (20, 17), (16, 21))
        else:
            line((14, 3), (20, 8), (14, 13)); line((20, 8), (8, 8), (3, 12), (3, 17), (7, 21))
    elif name == 'plus':
        box(3, 3, 20, 20); line((7, 11), (16, 11)); line((11, 7), (11, 16))
    elif name == 'info':
        arc(11, 11, 10, 0, 360); line((11, 10), (11, 17)); line((11, 5), (11, 6))
    elif name == 'volume':
        line((2, 9), (6, 9), (12, 4), (12, 20), (6, 15), (2, 15), (2, 9))
        arc(12, 12, 6, -50, 50); arc(12, 12, 10, -45, 45)
    elif name == 'sliders':
        for y, x in ((5, 7), (12, 16), (20, 10)):
            line((2, y), (21, y)); box(x-2, y-2, x+2, y+2)
    elif name in ('checkbox_empty', 'checkbox_checked'):
        box(3, 3, 20, 20)
        if name == 'checkbox_checked':
            line((6, 11), (10, 15), (17, 7))
    elif name == 'save':
        line((3, 2), (17, 2), (21, 6), (21, 21), (3, 21), (3, 2))
        box(7, 2, 16, 9)
        box(7, 14, 17, 21)
        line((13, 4), (13, 7))
    elif name in ('loader', 'loader_up', 'loaders'):
        # Shared layers; the arrow indicates the selected deployment order.
        line((2, 6), (11, 2), (20, 6), (11, 10), (2, 6))
        line((2, 11), (11, 15), (20, 11))
        line((2, 16), (11, 20), (20 if name == 'loaders' else 16, 16 if name == 'loaders' else 18))
        if name != 'loaders':
            line((20, 15), (20, 22))
        if name == 'loader_up':
            line((17, 18), (20, 15), (23, 18))
        elif name == 'loader':
            line((17, 19), (20, 22), (23, 19))
    elif name == 'gameplay':
        line((7, 6), (16, 6), (20, 9), (22, 18), (19, 20), (15, 15),
             (8, 15), (4, 20), (1, 18), (3, 9), (7, 6))
        line((5, 10), (9, 10))
        line((7, 8), (7, 12))
        line((16, 9), (16, 10))
        line((19, 12), (19, 13))
    elif name == 'visual':
        # A picture frame and sound wave remain legible at category-header size.
        box(1, 3, 15, 19)
        line((2, 16), (6, 11), (10, 15), (13, 12), (15, 14))
        arc(10, 7, 1, 0, 360)
        line((18, 8), (18, 15))
        arc(17, 11, 5, -50, 50)
    elif name == 'globe':
        arc(11, 11, 10, 0, 360)
        line((1, 11), (21, 11))
        line((11, 1), (7, 5), (6, 11), (7, 17), (11, 21),
             (15, 17), (16, 11), (15, 5), (11, 1))
    elif name == 'flask':
        line((8, 1), (15, 1))
        line((9, 2), (9, 9), (2, 20), (3, 22), (20, 22), (21, 20),
             (14, 9), (14, 2))
        line((6, 15), (17, 15))
        line((9, 18), (10, 18))
        line((15, 20), (16, 20))
    elif name == 'trash':
        line((6, 8), (7, 21), (17, 21), (18, 8))
        line((3, 5), (20, 5))
        line((8, 5), (8, 2), (15, 2), (15, 5))
        color = secondary or color
        line((10, 10), (10, 17))
        line((14, 10), (14, 17))
    elif name == 'exit_fullscreen':
        for x, y, dx, dy in ((2, 2, 1, 1), (20, 2, -1, 1),
                             (2, 20, 1, -1), (20, 20, -1, -1)):
            tip = (x + 6*dx, y + 6*dy)
            line((x, y), tip)
            line((tip[0]-4*dx, tip[1]), tip, (tip[0], tip[1]-4*dy))
    elif name == 'mods':
        line((2, 4), (7, 4), (11, 6), (15, 4), (20, 4), (20, 19),
             (15, 19), (11, 21), (7, 19), (2, 19), (2, 4))
        line((11, 6), (11, 20))
    elif name == 'log':
        line((4, 2), (14, 2), (20, 8), (20, 21), (4, 21), (4, 2))
        line((14, 2), (14, 8), (20, 8))
        for y in (11, 15, 18):
            line((8, y), (16, y))
    elif name == 'deploy':
        line((2, 3), (7, 3), (12, 11), (21, 11))
        line((2, 20), (7, 20), (12, 11))
        line((17, 7), (21, 11), (17, 15))
    elif name == 'tools':
        box(7, 2, 16, 10)
        box(1, 13, 10, 21)
        box(13, 13, 22, 21)
    elif name == 'about':
        arc(11, 11, 8, 200, 355)
        arc(11, 11, 8, 20, 175)
        line((15, 8), (19, 11), (21, 6))
        line((7, 14), (3, 11), (1, 16))
    elif name == 'editor':
        box(4, 7, 19, 20)
        line((11, 7), (11, 3), (14, 3))
        line((1, 11), (1, 16))
        line((22, 11), (22, 16))
        box(7, 10, 8, 12)
        box(15, 10, 16, 12)
        line((8, 17), (15, 17))
    elif name == 'folder':
        line((2, 19), (2, 4), (9, 4), (12, 7), (21, 7), (21, 19), (2, 19))
    elif name == 'import':
        line((2, 14), (2, 21), (21, 21), (21, 14))
        line((11, 2), (11, 16), (6, 11))
        line((11, 16), (16, 11))
    elif name == 'export':
        line((2, 14), (2, 21), (21, 21), (21, 14))
        line((11, 16), (11, 2), (6, 7))
        line((11, 2), (16, 7))
    elif name == 'search':
        arc(9, 9, 7, 0, 360)
        line((14, 14), (21, 21))
    elif name == 'check_all':
        box(2, 2, 21, 21)
        line((6, 11), (10, 15), (17, 7))
    elif name == 'clear_all':
        box(2, 2, 21, 21)
        line((7, 11), (16, 11))
    elif name == 'back':
        line((20, 11), (3, 11), (9, 5))
        line((3, 11), (9, 17))
    elif name == 'settings':
        arc(11, 11, 7, 0, 360)
        arc(11, 11, 3, 0, 360)
        for angle in range(0, 360, 45):
            r = math.radians(angle)
            line((round(11+7*math.cos(r)), round(11+7*math.sin(r))),
                 (round(11+10*math.cos(r)), round(11+10*math.sin(r))))
    else:
        raise ValueError(name)
    return image
