"""Small raster platform marks independent of installed symbol fonts."""
import tkinter as tk

def make(master, platforms):
    image = tk.PhotoImage(master=master, width=len(platforms)*28+8, height=24)
    for index, platform in enumerate(platforms):
        offset = index*28+8
        def fill(color, x1, y1, x2, y2):
            image.put(color, to=(offset+x1,y1,offset+x2,y2))
        if platform == 'windows':
            for x in (2,12):
                for y in (3,13):
                    fill('#00a4ef',x,y,x+8,y+8)
        else:
            # Tux silhouette, white belly/eyes and yellow beak/feet.
            for y in range(2,22):
                half = 5 if y < 9 else min(9,5+(y-8)//2)
                fill('#161616',11-half,y,12+half,y+1)
            for y in range(10,21):
                half = 4 if y < 13 else 6
                fill('#f5f5f5',11-half,y,12+half,y+1)
            fill('#ffffff',7,5,10,9); fill('#ffffff',13,5,16,9)
            fill('#161616',8,6,9,8); fill('#161616',14,6,15,8)
            fill('#f5c542',9,9,14,12)
            fill('#f5c542',2,21,10,24); fill('#f5c542',14,21,22,24)
    cache = getattr(master, '_platform_images', [])
    cache.append(image)
    master._platform_images = cache
    return image
