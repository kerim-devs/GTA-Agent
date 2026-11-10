import sys
from PIL import Image, ImageEnhance
# usage: az.py SHEET NN[,NN...] [cx cy half zoom contrast]
s=sys.argv[1]; ns=[int(x) for x in sys.argv[2].split(',')]
cx=int(sys.argv[3]) if len(sys.argv)>3 else 370; cy=int(sys.argv[4]) if len(sys.argv)>4 else 350
h=int(sys.argv[5]) if len(sys.argv)>5 else 30; z=int(sys.argv[6]) if len(sys.argv)>6 else 12
con=float(sys.argv[7]) if len(sys.argv)>7 else 1.0
im=Image.open('data/sheets/%s.jpg'%s).convert('RGB')
W,H=im.size; tw,th=W//4,H//3
out=Image.new('RGB',(len(ns)*(2*h*z+6),2*h*z+6),(255,0,255))
for i,n in enumerate(ns):
    r,c=divmod(n-1,4); t=im.crop((c*tw,r*th,(c+1)*tw,(r+1)*th)).crop((cx-h,cy-h,cx+h,cy+h)).resize((2*h*z,2*h*z),Image.BICUBIC)
    if con!=1.0: t=ImageEnhance.Contrast(t).enhance(con)
    out.paste(t,(i*(2*h*z+6)+3,3))
out.save('work_g05_g09/%s_az_%s.jpg'%(s,'_'.join(map(str,ns))),quality=92)
