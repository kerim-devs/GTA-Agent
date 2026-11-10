import sys, json
import numpy as np
from PIL import Image, ImageDraw
out='work_G00_G04'
crops=np.load('data/crops.npy', mmap_mode='r')
g={e['id']:e for e in json.load(open('data/golden.json'))}
# usage: pair.py name id1 id2  -> two full crops at 6x (nearest-ish via LANCZOS) side by side 1560x1020 each -> scaled 0.5 => use 5x: 1300x850 each
name=sys.argv[1]; ids=sys.argv[2:]
Z=6
W,H=260*Z,170*Z
sheet=Image.new('RGB',(len(ids)*(W+6),H),(255,0,255))
for i,a in enumerate(ids):
    if a.startswith('k'):
        k=int(a[1:])
    else:
        k=g[a]['k']
    c=Image.fromarray(np.asarray(crops[k])).resize((W,H),Image.LANCZOS)
    d=ImageDraw.Draw(c)
    d.rectangle((0,0,110,26),fill=(0,0,0)); d.text((4,2),a,fill=(255,255,0),font_size=20)
    sheet.paste(c,(i*(W+6),0))
sheet.save(f'{out}/{name}.png')
