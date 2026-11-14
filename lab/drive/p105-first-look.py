"""scale.py <run>...: metres of route per pixel of path to a corner that is tracked until the car is at it."""
import json, sys, collections, statistics
from math import atan2, degrees, hypot
def corner(path):
    """Path length in px to the first bend of 60 degrees or more between chords two points long."""
    if len(path) < 6: return None
    s = hypot(*path[0]); out = None
    acc = [s]
    for a, b in zip(path, path[1:]): acc.append(acc[-1] + hypot(b[0]-a[0], b[1]-a[1]))
    for i in range(2, len(path) - 2):
        a, b, c = path[i-2], path[i], path[i+2]
        h1 = degrees(atan2(b[0]-a[0], b[1]-a[1])); h2 = degrees(atan2(c[0]-b[0], c[1]-b[1]))
        d = abs((h2 - h1 + 180) % 360 - 180)
        if d >= 60: return acc[i], (1 if ((h2 - h1 + 180) % 360 - 180) > 0 else -1)
    return None
pairs = []
for run in sys.argv[1:]:
    rows = [json.loads(l) for l in open(run + "/play.jsonl")]
    track = []
    def close():
        global track
        if len(track) >= 20 and track[0][1] - track[-1][1] >= 25 and track[-1][1] <= 30:
            t1, s1, d1, v1 = track[-1]
            for t, s, d, v in track[:-1]:
                if s - s1 >= 5 and 0 < d - d1 < 600: pairs.append((s, s1, d - d1 + 1.4 * s1, v, run[-6:], t))
        track = []
    for r in rows:
        rd = r.get("reading") or {}
        if not (isinstance(r.get("skill"), dict) and r["skill"].get("name") == "drive_route"): close(); continue
        p = rd.get("path") or (); d = rd.get("gps_distance"); v = rd.get("gps_speed")
        c = corner([tuple(x) for x in p]) if p else None
        if c is None or d is None or v is None:
            if track and r["t"] - track[-1][0] > 1.5: close()
            continue
        s = c[0]
        if track and (r["t"] - track[-1][0] > 1.5 or s > track[-1][1] + 12): close()
        track.append((r["t"], s, d, v))
    close()
print("pairs", len(pairs), "tracks", len({(p[4], p[1]) for p in pairs}))
bins = collections.defaultdict(list)
for s_, s1, m, v, run, t in pairs:
    vb = "v<8" if v < 8 else "v 8-16" if v < 16 else "v>=16"
    bins[(vb, int(s_ // 10) * 10)].append(m)
for vb in ("v<8", "v 8-16", "v>=16"):
    print(vb, " assumed scale", {"v<8": "0.7-1.0", "v 8-16": "1.0-2.1", "v>=16": "2.1-3.7"}[vb])
    for sb in range(20, 120, 10):
        b = sorted(bins.get((vb, sb), []))
        if len(b) >= 12: print(f"   corner {sb:3d}-{sb+10:3d} px along the path: n {len(b):4d}  metres p10 {b[len(b)//10]:5.0f} p25 {b[len(b)//4]:5.0f} median {b[len(b)//2]:5.0f}  = m/px p10 {b[len(b)//10]/(sb+5):.1f} p25 {b[len(b)//4]/(sb+5):.1f} median {b[len(b)//2]/(sb+5):.1f}")
