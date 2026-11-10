import sys, math
from PIL import Image, ImageDraw
out='work_G00_G04'
TW,TH=780,510
def tile(s,n):
    im=Image.open(f'data/sheets/{s}.jpg')
    r,c=(n-1)//4,(n-1)%4
    return im.crop((c*TW,r*TH,(c+1)*TW,(r+1)*TH))
def arrows(s):
    # grid of arrow zooms, 4x3, each 110x110 region at 4x
    R=55; Z=4
    sheet=Image.new('RGB',(4*(2*R*Z+6),3*(2*R*Z+6)),(255,0,255))
    for n in range(1,13):
        t=tile(s,n)
        cx,cy=369,351
        c=t.crop((cx-R,cy-R,cx+R,cy+R)).resize((2*R*Z,2*R*Z),Image.LANCZOS)
        d=ImageDraw.Draw(c)
        d.rectangle((0,0,40,22),fill=(0,0,0)); d.text((4,4),str(n),fill=(255,255,0))
        r,cc=(n-1)//4,(n-1)%4
        sheet.paste(c,(cc*(2*R*Z+6)+3,r*(2*R*Z+6)+3))
    sheet.save(f'{out}/{s}_arrows.png')
def route(s,n,cx=369,cy=351):
    t=tile(s,n)
    x0,y0,x1,y1=cx-200,cy-200,cx+200,min(TH,cy+160)
    x0=max(0,x0)
    Z=2
    a=t.crop((x0,y0,x1,y1)).resize(((x1-x0)*Z,(y1-y0)*Z),Image.LANCZOS)
    b=a.copy()
    d=ImageDraw.Draw(b)
    ox,oy=(cx-x0)*Z,(cy-y0)*Z
    for rad,col in ((90,(0,255,255)),(180,(0,255,0))):
        rr=rad*Z
        # dotted circle
        for k in range(0,360,3):
            if (k//3)%2==0:
                a0=math.radians(k);
                d.point((ox+rr*math.cos(a0),oy+rr*math.sin(a0)),fill=col)
                d.point((ox+rr*math.cos(a0)+1,oy+rr*math.sin(a0)),fill=col)
        for h in range(0,24):
            ang=math.radians(h*15-90)
            l=10 if h%2==0 else 5
            d.line((ox+(rr)*math.cos(ang),oy+(rr)*math.sin(ang),ox+(rr+l)*math.cos(ang),oy+(rr+l)*math.sin(ang)),fill=col,width=1)
            if h%2==0:
                hh=(h//2) or 12
                d.text((ox+(rr+18)*math.cos(ang)-4,oy+(rr+18)*math.sin(ang)-5),str(hh),fill=(255,255,255),stroke_width=1,stroke_fill=(0,0,0))
    W=a.size[0]*2+6
    o=Image.new('RGB',(W,a.size[1]),(255,0,255))
    o.paste(a,(0,0)); o.paste(b,(a.size[0]+6,0))
    o.save(f'{out}/{s}_{n:02d}_route.png')
if __name__=='__main__':
    cmd=sys.argv[1]
    if cmd=='arrows':
        for s in sys.argv[2:]: arrows(s)
    elif cmd=='route':
        s=sys.argv[2]
        for a in sys.argv[3:]:
            if ':' in a:
                n,cx,cy=a.split(':'); route(s,int(n),int(cx),int(cy))
            else: route(s,int(a))
