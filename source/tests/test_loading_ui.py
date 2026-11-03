import tkinter as tk
import unittest
from loading_ui import LoadingBar, contrast, visible

class LoadingTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def test_theme_contrast_and_live_changes(self):
        bar = LoadingBar(self.root)
        for background, accent in (('#080808','#ffd400'),('#ffffff','#ffff00'),('#112233','#112233')):
            self.root.theme = {'accent':accent,'text':background,'muted':background}
            bar.configure(bg=background,value=42)
            track,glow,segments,caption,status = bar._items
            self.assertGreaterEqual(contrast(bar.itemcget(segments[0],'fill'),background),3)
            for item in (caption,status):
                self.assertGreaterEqual(contrast(bar.itemcget(item,'fill'),background),4.5)
            self.assertEqual(bar.itemcget(status,'text'),'42%')

    def test_animation_reuses_items_and_stops_on_destroy(self):
        bar = LoadingBar(self.root)
        bar.start()
        items = bar.find_all()
        for phase in range(100):
            bar.phase=phase
            bar.draw()
            self.assertEqual(bar.find_all(),items)
        bar.destroy()
        self.assertIsNone(bar.timer)

    def test_zero_full_and_long_caption(self):
        bar = LoadingBar(self.root,width=320)
        bar.pack()
        self.root.deiconify()
        self.root.update()
        for value in (0,100):
            bar.configure(value=value,caption='A very long phase description '*20)
            track,glow,segments,caption,status = bar._items
            self.assertEqual(bar.itemcget(segments[0],'state'),'hidden' if value==0 else 'normal')
            self.assertLess(bar.bbox(caption)[2],bar.bbox(status)[0])
            self.assertEqual(bar.itemcget(status,'text'),str(value)+'%')
