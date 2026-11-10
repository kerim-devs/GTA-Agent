import sys
from PIL import Image
out='work_G00_G04'
for s in ['G00','G01','G02','G03','G04']:
    im=Image.open(f'data/sheets/{s}.jpg')
    W,H=im.size
    tw,th=W//4,H//3
    for r in range(3):
        for half in range(2):
            box=(half*2*tw, r*th, (half*2+2)*tw, (r+1)*th)
            c=im.crop(box)
            c.save(f'{out}/{s}_r{r}_h{half}.png')
print(tw,th)
