import sys, json
import numpy as np
from PIL import Image, ImageDraw
out='work_G00_G04'
crops=np.load('data/crops.npy', mmap_mode='r')
g={e['id']:e for e in json.load(open('data/golden.json'))}
# usage: one.py name R Z id[:cx:cy] ...
name=sys.argv[1]; R=int(sys.argv[2]); Z=int(sys.argv[3])
ids=sys.argv[4:]
P=2*R*Z
sheet=Image.new('RGB',(len(ids)*(P+6),P+6),(255,0,255))
for i,a in enumerate(ids):
    parts=a.split(':'); id_=parts[0]
    cx,cy=(int(parts[1]),int(parts[2])) if len(parts)>1 else (123,117)
    c=Image.fromarray(np.asarray(crops[g[id_]['k']]))
    c=c.crop((cx-R,cy-R,cx+R,cy+R)).resize((P,P),Image.BICUBIC)
    d=ImageDraw.Draw(c)
    d.rectangle((0,0,90,24),fill=(0,0,0)); d.text((4,2),id_,fill=(255,255,0),font_size=18)
    sheet.paste(c,(i*(P+6)+3,3))
sheet.save(f'{out}/{name}.png')
