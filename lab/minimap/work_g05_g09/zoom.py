import sys, math
from PIL import Image, ImageDraw
# usage: zoom.py arrows SHEET  -> 12 arrow zooms (4x) in a grid
#        zoom.py ring SHEET NN [ax ay] -> tile 2x with near/far circles
mode=sys.argv[1]; s=sys.argv[2]
im=Image.open('data/sheets/%s.jpg'%s).convert('RGB')
W,H=im.size; tw,th=W//4,H//3
def tile(n):
    r,c=divmod(n-1,4); return im.crop((c*tw,r*th,(c+1)*tw,(r+1)*th))
if mode=='arrows':
    cx,cy,h=370,350,60
    z=5
    out=Image.new('RGB',(4*(2*h*z+6),3*(2*h*z+6)),(255,0,255))
    for n in range(1,13):
        t=tile(n).crop((cx-h,cy-h,cx+h,cy+h)).resize((2*h*z,2*h*z),Image.LANCZOS)
        d=ImageDraw.Draw(t); d.text((4,4),str(n),fill=(255,255,0))
        r,c=divmod(n-1,4); out.paste(t,(c*(2*h*z+6)+3,r*(2*h*z+6)+3))
    out.save('work_g05_g09/%s_arrows.jpg'%s,quality=92)
elif mode=='ring':
    n=int(sys.argv[3]); ax=int(sys.argv[4]) if len(sys.argv)>4 else 370; ay=int(sys.argv[5]) if len(sys.argv)>5 else 350
    R=float(sys.argv[6]) if len(sys.argv)>6 else 95
    z=2
    t=tile(n).resize((tw*z,th*z),Image.LANCZOS)
    d=ImageDraw.Draw(t)
    for rr in (R,2*R):
        d.ellipse((ax*z-rr*z,ay*z-rr*z,ax*z+rr*z,ay*z+rr*z),outline=(0,255,255),width=1)
        for hh in range(12):
            a=math.radians(hh*30)
            x1=ax*z+math.sin(a)*(rr*z-6); y1=ay*z-math.cos(a)*(rr*z-6)
            x2=ax*z+math.sin(a)*(rr*z+6); y2=ay*z-math.cos(a)*(rr*z+6)
            d.line((x1,y1,x2,y2),fill=(0,255,0),width=2)
            xt=ax*z+math.sin(a)*(rr*z+16); yt=ay*z-math.cos(a)*(rr*z+16)
            d.text((xt-5,yt-5),str(hh if hh else 12),fill=(0,255,0))
    t.save('work_g05_g09/%s_%02d_ring.jpg'%(s,n),quality=92)
