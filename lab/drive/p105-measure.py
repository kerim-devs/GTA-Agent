"""Measure tracked junction displacement against GPS differences, without an end offset."""
import json
from collections import Counter, defaultdict
from math import atan2, degrees, hypot
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'lab/drive'
RUNS = Path('/Users/kerim/recordings/pilot')
ARRIVALS = ['024431', '024817', '025007', '025345', '025645']


def angle(a):
    return (a + 180) % 360 - 180


def corner(path):
    """Intersect straight fitted incoming/outgoing chords; reject curved or ambiguous paths."""
    p = np.asarray(path, dtype=float)
    if len(p) < 5:
        return None
    best = None
    for i in range(2, len(p) - 1):
        left, right = p[:i], p[i:i+5]
        if np.linalg.norm(left[-1] - left[0]) < 5 or np.linalg.norm(right[-1] - right[0]) < 8:
            continue
        means = [a.mean(axis=0) for a in (left, right)]
        dirs = [np.linalg.svd(a - m, full_matrices=False)[2][0] for a, m in zip((left, right), means)]
        for j, a in enumerate((left, right)):
            if dirs[j] @ (a[-1] - a[0]) < 0:
                dirs[j] *= -1
        turn = angle(degrees(atan2(*dirs[1]) - atan2(*dirs[0])))
        if not 60 <= abs(turn) <= 125:
            continue
        residual = sum(np.sum((a - m) ** 2) - np.sum(((a - m) @ d) ** 2) for a, m, d in zip((left, right), means, dirs)) / len(p)
        if residual > 2**2:
            continue
        try:
            lengths = np.linalg.solve(np.column_stack((dirs[0], -dirs[1])), means[1] - means[0])
        except np.linalg.LinAlgError:
            continue
        xy = means[0] + lengths[0] * dirs[0]
        if min(np.linalg.norm(xy - p[i-1]), np.linalg.norm(xy - p[i])) > 10:
            continue
        # The approach must pass the arrow: route correction is not driven route distance.
        cross = abs(dirs[0][0] * means[0][1] - dirs[0][1] * means[0][0])
        if cross > 9 or xy[1] < 0:
            continue
        result = dict(x=float(xy[0]), y=float(xy[1]), turn=turn,
                      residual=float(max(0, residual)**0.5), direction=degrees(atan2(*dirs[0])),
                      index=i, path=path)
        if best is None or residual < best[0]:
            best = residual, result
    return best[1] if best else None


def collect():
    tracks = []
    flat = Counter()
    for run in sorted(RUNS.glob('20261114-*')):
        if run.name > '20261114-025645' or not (run / 'play.jsonl').exists():
            continue
        track = []
        last_sample = -1
        def close():
            if len(track) >= 5 and track[-1]['t'] - track[0]['t'] >= 1:
                tracks.append(dict(run=run.name, rows=track.copy()))
            track.clear()
        with (run / 'play.jsonl').open() as f:
            for line in f:
                row = json.loads(line)
                rd, sk = row.get('reading') or {}, row.get('skill') or {}
                if sk.get('name') != 'drive_route':
                    close()
                    continue
                if rd.get('minimap') == 'flat':
                    flat['ticks'] += 1
                    flat['with_path'] += bool(rd.get('path'))
                if row['t'] - last_sample < .3:
                    continue
                last_sample = row['t']
                p, d, v = rd.get('path') or [], rd.get('gps_distance'), rd.get('gps_speed')
                age = sk.get('distance_age')
                c = corner(p) if not rd.get('corrupt') and d is not None and v is not None and age is not None and age <= .5 else None
                if c is None:
                    if track and row['t'] - track[-1]['t'] > .8:
                        close()
                    continue
                c.update(t=row['t'], distance=d, speed=v, age=age, arrow=rd.get('arrow'),
                         attempt=sk.get('attempt_id'), quantum=10 if d >= 1000 else 1)
                if track:
                    prev = track[-1]
                    if (c['t'] - prev['t'] > .8 or c['turn'] * prev['turn'] < 0
                            or hypot(c['x']-prev['x'],c['y']-prev['y']) > 12
                            or c['attempt'] != prev['attempt'] or c['distance'] > prev['distance'] + 2):
                        close()
                track.append(c)
        close()
    pairs = []
    for tid, track in enumerate(tracks):
        rows = track['rows']
        # Nonoverlapping endpoints: do not count 26 repeated GPS ticks as independent samples.
        i = 0
        while i < len(rows) - 1:
            a = rows[i]
            found = None
            for j in range(i+1, len(rows)):
                b = rows[j]
                dm = a['distance'] - b['distance']
                dp = hypot(a['x'], a['y']) - hypot(b['x'], b['y'])
                if dm < max(8, 2*a['quantum']) or dp < 6:
                    continue
                vs = [r['speed'] for r in rows[i:j+1]]
                directions = [r['direction'] for r in rows[i:j+1]]
                if max(vs)-min(vs) > 6 or max(directions)-min(directions) > 20:
                    break
                if a['t']+8 < b['t'] or dm/(b['t']-a['t']) > 40:
                    break
                found = j
                speed = float(np.median(vs))
                pairs.append(dict(track=tid, run=track['run'], t0=a['t'], t1=b['t'],
                                  a=[a['x'],a['y']], b=[b['x'],b['y']], metres=dm,
                                  pixel=dp, speed=speed, band=0 if speed<8 else 1 if speed<16 else 2,
                                  quantum=a['quantum'], residual=max(a['residual'],b['residual']),
                                  age_delta=a['age']-b['age']))
                break
            i = found + 1 if found is not None else i+1
    return tracks, pairs, flat


def fit(pairs):
    a, b = [np.asarray([r[key] for r in pairs]) for key in ('a', 'b')]
    dm = np.asarray([r['metres'] for r in pairs])
    bands = np.asarray([r['band'] for r in pairs])
    best = None
    for tilt in np.arange(0, .00801, .00025):
        for ratio in np.arange(.4, 1.21, .05):
            delta = np.hypot(a[:,0]*ratio,a[:,1])/(1-tilt*a[:,1]) - np.hypot(b[:,0]*ratio,b[:,1])/(1-tilt*b[:,1])
            good = delta>1
            scales = dm / np.maximum(delta,.01)
            medians = [np.median(scales[(bands==band)&good]) for band in range(3)]
            score = np.median(np.abs(np.log(scales[good]/np.take(medians,bands[good]))))
            if best is None or score < best[0]:
                best = score, tilt, ratio, medians, scales
    score, tilt, ratio, medians, scales = best
    return dict(tilt=float(tilt), horizontal_ratio=float(ratio), score=float(score),
                bands=[dict(n=int(sum(bands==band)), p10=float(np.percentile(scales[bands==band],10)),
                            median=float(medians[band]), p90=float(np.percentile(scales[bands==band],90))) for band in range(3)])


def main():
    tracks, pairs, flat = collect()
    (OUT/'p105-tracks.json').write_text(json.dumps(tracks,separators=(',',':'))+'\n')
    (OUT/'p105-pairs.json').write_text(json.dumps(pairs,indent=2)+'\n')
    result = dict(tracks=len(tracks), pairs=len(pairs), flat=dict(flat), fit=fit(pairs))
    bins=defaultdict(list)
    for p in pairs:
        y=(p['a'][1]+p['b'][1])/2
        x=(abs(p['a'][0])+abs(p['b'][0]))/2
        zone='side' if x>25 else 'near' if y<35 else 'middle' if y<60 else 'far'
        bins[f"{p['band']}/{zone}"].append(p)
    result['zones']={key:dict(n=len(val),tracks=len({v['track'] for v in val}),
                             p10=float(np.percentile([v['metres']/v['pixel'] for v in val],10)),
                             median=float(np.median([v['metres']/v['pixel'] for v in val])),
                             p90=float(np.percentile([v['metres']/v['pixel'] for v in val],90)))
                     for key,val in sorted(bins.items())}
    (OUT/'p105-measurements.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__ == '__main__':
    main()
