import sys, json
import numpy as np
from PIL import Image, ImageOps
out='work_G00_G04'
crops=np.load('data/crops.npy', mmap_mode='r')
g={e['id']:e for e in json.load(open('data/golden.json'))}
name=sys.argv[1]; a=sys.argv[2]
k=int(a[1:]) if a.startswith('k') else g[a]['k']
c=np.asarray(crops[k]).astype(np.float32)
lo=float(sys.argv[3]) if len(sys.argv)>3 else 180
hi=float(sys.argv[4]) if len(sys.argv)>4 else 255
c=np.clip((c-lo)/(hi-lo),0,1)**1.5*255
im=Image.fromarray(c.astype(np.uint8)).resize((260*6,170*6),Image.LANCZOS)
im.save(f'{out}/{name}.png')
