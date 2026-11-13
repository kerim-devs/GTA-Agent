"""The heading get_away would take on the key frames of Kerim's escapes, beside his stick in the 0.2 to 1.5 s and
0.2 to 3 s after the frame (signed, in seconds of full lock). Corrupt key frames are left out."""
import bisect, json, sys
from collections import Counter
from common import KEYS, LABELS, WORK
import numpy as np
from pilot import minimap, terrain
from pilot.getaway import GetAway

keep = json.load(open(LABELS / 'escapes_kept.json'))
rows = []
def integral(pad, pt, a, b):
    k0 = max(0, bisect.bisect_right(pt, a) - 1)
    tot = 0.0
    for k in range(k0, len(pad)):
        lo = max(pad[k]['t'], a)
        hi = min(pad[k + 1]['t'] if k + 1 < len(pad) else b, b)
        if pad[k]['t'] >= b:
            break
        if hi > lo:
            tot += pad[k]['left'][0] * (hi - lo)
    return tot
for e in keep:
    d = np.load(KEYS / f"{e['recording']}.npz")
    pad = [json.loads(l) for l in open(f"/Users/kerim/recordings/kerim/{e['recording']}/pad.jsonl")]
    pt = [p['t'] for p in pad]
    for t, m, sc, bad, crop in zip(d['t'], d['map'], d['screen'], d['corrupt'], d['crops']):
        if not (e['start'] <= t <= e['end']) or m != 'tilted' or sc != 'game' or bad:
            continue
        reading = minimap.read(crop)
        skill = GetAway({})
        skill.arrow = reading.arrow if reading.arrow is not None else 0.0
        skill.terrain = terrain.read(crop)
        police = terrain.police(reading)
        skill.police = tuple(((p - skill.arrow + 180) % 360) - 180 for p in police)
        heading, why = skill.choose()
        rel = ((heading - skill.arrow + 180) % 360) - 180
        roads = None if skill.terrain is None else [((r - skill.arrow + 180) % 360) - 180 for r, _ in skill.terrain.roads]
        rows.append(dict(rec=e['recording'], t=round(float(t), 1), why=why, rel=round(rel, 1), police=len(police),
                         roads=roads, s1=integral(pad, pt, t + 0.2, t + 1.5), s2=integral(pad, pt, t + 0.2, t + 3.0)))
json.dump(rows, open(WORK / 'beside.json', 'w'))
print('frames', len(rows), Counter(r['why'] for r in rows), 'police seen', sum(1 for r in rows if r['police']))
def sgn(v, lim):
    return 0 if abs(v) < lim else (1 if v > 0 else -1)
for win in ('s1', 's2'):
    for lim in (30, 45):
        for label, sel in (('all', rows), ('road, no police', [r for r in rows if r['why'] == 'road' and not r['police']]),
                           ('police seen', [r for r in rows if r['police']])):
            turn = [r for r in sel if abs(r['rel']) >= lim]
            same = sum(1 for r in turn if sgn(r[win], 0.15) == sgn(r['rel'], lim))
            opp = sum(1 for r in turn if sgn(r[win], 0.15) == -sgn(r['rel'], lim))
            rho = np.corrcoef(np.argsort(np.argsort([r['rel'] for r in sel])), np.argsort(np.argsort([r[win] for r in sel])))[0, 1] if len(sel) > 2 else float('nan')
            print(f"{win} |rel|>={lim} {label}: frames {len(sel)}, turns {len(turn)}, same {same}, opposite {opp}, none {len(turn)-same-opp}, rank corr {rho:.2f}")
straight = [r for r in rows if abs(r['rel']) < 15]
print('straight', len(straight), 'Kerim |s2|<0.15', sum(1 for r in straight if abs(r['s2']) < 0.15))
big = [r for r in rows if abs(r['s2']) >= 0.6]
print('Kerim turned hard (|s2|>=0.6 s of lock)', len(big), 'skill same', sum(1 for r in big if sgn(r['rel'], 15) == sgn(r['s2'], 0.6)), 'skill straight', sum(1 for r in big if abs(r['rel']) < 15))
