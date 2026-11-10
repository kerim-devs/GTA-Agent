import sys
from PIL import Image
s=sys.argv[1]; n=int(sys.argv[2]); z=float(sys.argv[3]) if len(sys.argv)>3 else 2
im=Image.open('work_g05_g09/%s_%02d.jpg'%(s,n)).convert('RGB')
box=[int(v) for v in sys.argv[4:8]] if len(sys.argv)>7 else None
if box: im=im.crop(box)
im.resize((int(im.width*z),int(im.height*z)),Image.BICUBIC).save('work_g05_g09/%s_%02d_big.jpg'%(s,n),quality=92)
