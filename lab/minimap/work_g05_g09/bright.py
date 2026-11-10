import sys
from PIL import Image
import numpy as np
s=sys.argv[1]; n=int(sys.argv[2]); g=float(sys.argv[3]) if len(sys.argv)>3 else 4.0
im=Image.open('work_g05_g09/%s_%02d.jpg'%(s,n)).convert('RGB')
a=np.asarray(im).astype(float)*g
Image.fromarray(np.clip(a,0,255).astype('uint8')).save('work_g05_g09/%s_%02d_bright.jpg'%(s,n),quality=92)
