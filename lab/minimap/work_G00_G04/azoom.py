import sys, json
import numpy as np
from PIL import Image, ImageDraw
out='work_G00_G04'
crops=np.load('data/crops.npy', mmap_mode='r')
g=json.load(open('data/golden.json'))
def arrows(s, R=13, Z=15, cx=123, cy=117):
    P=2*R*Z
    sheet=Image.new('RGB',(4*(P+6),3*(P+6)),(255,0,255))
    for e in g:
        if e['sheet']!=s+'.jpg': continue
        n=e['tile']
        c=Image.fromarray(np.asarray(crops[e['k']]))
        c=c.crop((cx-R,cy-R,cx+R,cy+R)).resize((P,P),Image.BICUBIC)
        d=ImageDraw.Draw(c)
        d.rectangle((0,0,60,34),fill=(0,0,0)); d.text((6,4),str(n),fill=(255,255,0),font_size=24)
        r,cc=(n-1)//4,(n-1)%4
        sheet.paste(c,(cc*(P+6)+3,r*(P+6)+3))
    sheet.save(f'{out}/{s}_az.png')
for s in sys.argv[1:]: arrows(s)
