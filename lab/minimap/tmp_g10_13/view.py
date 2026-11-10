"""Viewing helpers for labelling: zooms with a clock overlay. Reads sheets only."""
import math
import sys
from PIL import Image, ImageDraw, ImageFont

BASE = 'data/sheets/%s.jpg'
OUT = 'tmp_g10_13/'


def tile(sheet, n):
    im = Image.open(BASE % sheet).convert('RGB')
    W, H = im.size
    tw, th = W // 4, H // 3
    r, c = divmod(n - 1, 4)
    return im.crop((c * tw, r * th, (c + 1) * tw, (r + 1) * th))


def font(sz):
    for p in ('/System/Library/Fonts/Helvetica.ttc', '/System/Library/Fonts/Supplemental/Arial.ttf'):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def clock(sheet, n, cx=370, cy=350, z=2, rad=None):
    t = tile(sheet, n)
    tw = t.size[0]
    R = rad if rad else 90.0
    x0, y0, x1, y1 = cx - 230, cy - 225, cx + 230, cy + 125
    x0 = max(0, x0); y0 = max(0, y0); x1 = min(t.size[0], x1); y1 = min(t.size[1], y1)
    c = t.crop((x0, y0, x1, y1)).resize(((x1 - x0) * z, (y1 - y0) * z), Image.LANCZOS)
    raw = c.copy()
    d = ImageDraw.Draw(c)
    ox, oy = (cx - x0) * z, (cy - y0) * z
    for k, col in ((1, (0, 255, 255)), (2, (0, 255, 0))):
        rr = R * k * z
        d.ellipse((ox - rr, oy - rr, ox + rr, oy + rr), outline=col, width=1)
    f = font(16)
    for h2 in range(24):
        hr = h2 / 2.0
        a = math.radians(hr * 30)
        dx, dy = math.sin(a), -math.cos(a)
        for k in (1, 2):
            rr = R * k * z
            l = 14 if h2 % 2 == 0 else 7
            d.line((ox + dx * (rr - l), oy + dy * (rr - l), ox + dx * (rr + l), oy + dy * (rr + l)),
                   fill=(255, 0, 0), width=2)
            if h2 % 2 == 0:
                lab = str(int(hr) if hr else 12)
                d.text((ox + dx * (rr + 30) - 8, oy + dy * (rr + 30) - 11), lab, fill=(255, 0, 0), font=f,
                       stroke_width=2, stroke_fill=(255, 255, 255))
    d.line((ox - 6, oy, ox + 6, oy), fill=(255, 0, 0), width=1)
    d.line((ox, oy - 6, ox, oy + 6), fill=(255, 0, 0), width=1)
    out = Image.new('RGB', (raw.size[0] * 2 + 10, raw.size[1]), (255, 0, 255))
    out.paste(raw, (0, 0))
    out.paste(c, (raw.size[0] + 10, 0))
    p = OUT + 'clock_%s_%02d.jpg' % (sheet, n)
    out.save(p, quality=92)
    return p


def arrows(sheet, cx=370, cy=350, half=45, z=5):
    cell = half * 2 * z
    out = Image.new('RGB', (cell * 4 + 30, cell * 3 + 20), (255, 0, 255))
    f = font(28)
    for n in range(1, 13):
        t = tile(sheet, n)
        c = t.crop((cx - half, cy - half, cx + half, cy + half)).resize((cell, cell), Image.LANCZOS)
        d = ImageDraw.Draw(c)
        d.text((6, 4), str(n), fill=(255, 255, 0), font=f, stroke_width=3, stroke_fill=(0, 0, 0))
        r, col = divmod(n - 1, 4)
        out.paste(c, (col * (cell + 10), r * (cell + 10)))
    p = OUT + 'arrows_%s.jpg' % sheet
    out.save(p, quality=92)
    return p


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'arrows':
        for s in sys.argv[2:]:
            print(arrows(s))
    elif cmd == 'clock':
        s = sys.argv[2]
        for spec in sys.argv[3:]:
            parts = spec.split(':')
            n = int(parts[0])
            cx = int(parts[1]) if len(parts) > 1 else 370
            cy = int(parts[2]) if len(parts) > 2 else 350
            print(clock(s, n, cx, cy))
