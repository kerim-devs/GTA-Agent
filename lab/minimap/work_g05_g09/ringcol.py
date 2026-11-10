import sys, math, colorsys
import numpy as np
from PIL import Image
# usage: ringcol.py SHEET NN color [ax ay R]
s=sys.argv[1]; n=int(sys.argv[2]); col=sys.argv[3]
ax=int(sys.argv[4]) if len(sys.argv)>4 else 370; ay=int(sys.argv[5]) if len(sys.argv)>5 else 350
R=float(sys.argv[6]) if len(sys.argv)>6 else 95
im=np.asarray(Image.open('work_g05_g09/%s_%02d.jpg'%(s,n)).convert('RGB')).astype(float)/255
r,g,b=im[...,0],im[...,1],im[...,2]
mx=im.max(-1); mn=im.min(-1); sat=(mx-mn)/(mx+1e-6)
if col=='purple':
    m=(b>g+0.10)&(r>g+0.05)&(mx>0.45)
else:
    m=(r>0.6)&(g>0.6)&(b<0.76*np.minimum(r,g))&(abs(r-g)<0.12)
H,W=m.shape
yy,xx=np.mgrid[0:H,0:W]
d=np.hypot(xx-ax,yy-ay)
for rr,name in ((R,'near'),(2*R,'far')):
    ring=m&(abs(d-rr)<5)&(yy<435)&(xx>100)&(xx<645)
    ang=(np.degrees(np.arctan2(xx-ax,-(yy-ay)))%360)[ring]
    if len(ang)==0: print(name,'no pixels'); continue
    hist=np.histogram(ang,bins=72,range=(0,360))[0]
    out=[]
    for i,h in enumerate(hist):
        if h>0: out.append('%.1fh:%d'%(((i*5+2.5)/30) or 12,h))
    print(name,' '.join(out))
# max distance of colored pixels inside map
inm=m&(yy<435)&(xx>100)&(xx<645)&(yy>70)
print('colored px',inm.sum(),'max dist',d[inm].max() if inm.sum() else None)
Image.fromarray((m*255).astype('uint8')).save('work_g05_g09/%s_%02d_mask.png'%(s,n))
