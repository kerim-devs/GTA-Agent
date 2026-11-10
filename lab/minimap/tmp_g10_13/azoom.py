"""usage: azoom.py out_name SHEET:N[:cx:cy] ... -> strip of 14x arrow zooms (64px window)"""
import sys
sys.path.insert(0, 'tmp_g10_13')
from view import tile, font
from PIL import Image, ImageDraw
name = sys.argv[1]
specs = sys.argv[2:]
half = 30; z = 14; cell = half * 2 * z
cols = min(len(specs), 2)
rows = (len(specs) + cols - 1) // cols
out = Image.new('RGB', (cols * (cell + 10), rows * (cell + 10)), (255, 0, 255))
f = font(30)
for i, sp in enumerate(specs):
    p = sp.split(':'); s = p[0]; n = int(p[1])
    cx = int(p[2]) if len(p) > 2 else 370
    cy = int(p[3]) if len(p) > 3 else 350
    c = tile(s, n).crop((cx - half, cy - half, cx + half, cy + half)).resize((cell, cell), Image.BICUBIC)
    d = ImageDraw.Draw(c)
    d.text((6, 4), '%s-%02d' % (s, n), fill=(255, 255, 0), font=f, stroke_width=3, stroke_fill=(0, 0, 0))
    r, col = divmod(i, cols)
    out.paste(c, (col * (cell + 10), r * (cell + 10)))
p = 'tmp_g10_13/az_%s.jpg' % name
out.save(p, quality=93)
print(p, out.size)
