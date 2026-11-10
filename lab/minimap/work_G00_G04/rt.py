# full crop at 6x with near/far circles overlay (thin dotted), from original crops
import sys, json, math
import numpy as np
from PIL import Image, ImageDraw
out='work_G00_G04'
crops=np.load('data/crops.npy', mmap_mode='r')
g={e['id']:e for e in json.load(open('data/golden.json'))}
Z=6
def render(a):
    parts=a.split(':'); id_=parts[0]
    cx,cy=(float(parts[1]),float(parts[2])) if len(parts)>1 else (123,117)
    k=int(id_[1:]) if id_.startswith('k') else g[id_]['k']
    x0,y0,x1,y1=20,10,230,160
    c=Image.fromarray(np.asarray(crops[k])).crop((x0,y0,x1,y1)).resize(((x1-x0)*Z,(y1-y0)*Z),Image.LANCZOS)
    d=ImageDraw.Draw(c)
    ox,oy=(cx-x0)*Z,(cy-y0)*Z
    for rad,col in ((30,(0,255,255)),(60,(0,255,0))):
        rr=rad*Z
        for kk in range(0,720):
            if (kk//4)%3==0:
                a0=math.radians(kk/2)
                d.point((ox+rr*math.cos(a0),oy+rr*math.sin(a0)),fill=col)
        for h in range(0,24):
            ang=math.radians(h*15-90)
            l=12 if h%2==0 else 6
            d.line((ox+rr*math.cos(ang),oy+rr*math.sin(ang),ox+(rr+l)*math.cos(ang),oy+(rr+l)*math.sin(ang)),fill=col,width=2)
            if h%2==0:
                hh=(h//2) or 12
                d.text((ox+(rr+24)*math.cos(ang)-6,oy+(rr+24)*math.sin(ang)-8),str(hh),fill=(255,255,255),stroke_width=2,stroke_fill=(0,0,0),font_size=16)
    d.rectangle((0,0,110,26),fill=(0,0,0)); d.text((4,2),id_,fill=(255,255,0),font_size=20)
    return c
name=sys.argv[1]
ims=[render(a) for a in sys.argv[2:]]
W=sum(i.size[0]+6 for i in ims); H=ims[0].size[1]
o=Image.new('RGB',(W,H),(255,0,255)); x=0
for i in ims:
    o.paste(i,(x,0)); x+=i.size[0]+6
o.save(f'{out}/{name}.png')
