"""Kerim's escapes: stretches with stars lit, from the first star to the last gone, with what he did.

escapes.py > escapes.json; escapes_kept.json in ../labels is its selection; reads derived/kerim/<rec>/hud.jsonl, kerim/<rec>/pad.jsonl and the key frame
crops in keys/<rec>.npz (one about every 4 s) for the road reading."""
import bisect, json, sys
from pathlib import Path
from common import KEYS, LABELS, WORK
import numpy as np
from pilot import terrain

KERIM = Path("/Users/kerim/recordings/kerim")
DERIVED = Path("/Users/kerim/recordings/derived/kerim")
CLEAR = 3.0  # the star row reads zero this long: the last star is gone
BANNER = 0.5

out = []
for folder in sorted(DERIVED.iterdir()):
    hudp = folder / "hud.jsonl"
    if not hudp.exists() or not (KERIM / folder.name / "pad.jsonl").exists():
        continue
    rows = [json.loads(l) for l in hudp.open()]
    pad = [json.loads(l) for l in (KERIM / folder.name / "pad.jsonl").open()]
    pad_t = [p["t"] for p in pad]
    keys = np.load(KEYS / f"{folder.name}.npz") if (KEYS / f"{folder.name}.npz").exists() else None
    i = 0
    while i < len(rows):
        w = rows[i].get("wanted")
        if not (isinstance(w, int) and w > 0):
            i += 1
            continue
        start = rows[i]["t"]
        peak, end, why = w, None, None
        zero_since = None
        banner_since, banner = None, None
        j = i
        while j < len(rows):
            r = rows[j]
            wj, screen = r.get("wanted"), r.get("screen")
            if isinstance(wj, int) and wj > 0:
                peak = max(peak, wj)
                zero_since = None
            elif wj == 0:
                zero_since = r["t"] if zero_since is None else zero_since
                if r["t"] - zero_since >= CLEAR:
                    end, why = zero_since, "gone"
                    break
            if screen in ("wasted", "busted", "failed"):
                if banner != screen:
                    banner, banner_since = screen, r["t"]
                if r["t"] - banner_since >= BANNER:
                    end, why = banner_since, screen
                    break
            else:
                banner = None
            j += 1
        if end is None:
            end, why = rows[-1]["t"], "recording ends"
        span = [r for r in rows if start <= r["t"] <= end]
        game = [r for r in span if r.get("screen") == "game"]
        tilted = sum(r.get("map") == "tilted" for r in game)
        flat = sum(r.get("map") == "flat" for r in game)
        # Screens he opened: a run of map or pause rows.
        opened, last = [], None
        for r in span:
            s = r.get("screen")
            if s in ("map", "pause") and last not in ("map", "pause"):
                opened.append((round(r["t"], 1), s))
            last = s
        # The pad while the map is a vehicle's: a step function of the controller.
        k0 = bisect.bisect_right(pad_t, start) - 1
        k1 = bisect.bisect_right(pad_t, end)
        steps = pad[max(0, k0):k1]
        veh_t = [r["t"] for r in span if r.get("map") == "tilted" and r.get("screen") == "game"]
        def in_vehicle(t):
            k = bisect.bisect_left(veh_t, t)
            return any(0 <= kk < len(veh_t) and abs(veh_t[kk] - t) <= 0.15 for kk in (k - 1, k))
        dur = steer_hard = steer_sum = r2_down = r2_sum = l2_on = 0.0
        flips, side = 0, 0
        presses = {"options": 0, "touchpad": 0, "r1": 0}
        held = set()
        for a, b in zip(steps, steps[1:] + [{"t": end}]):
            t0, t1 = max(a["t"], start), min(b["t"], end)
            for name in presses:
                if name in a.get("buttons", []) and name not in held:
                    presses[name] += 1
            held = set(a.get("buttons", []))
            if t1 <= t0 or not in_vehicle((t0 + t1) / 2):
                continue
            dt = t1 - t0
            x = a["left"][0]
            dur += dt
            steer_sum += abs(x) * dt
            steer_hard += (abs(x) >= 0.5) * dt
            r2_sum += a["r2"] * dt
            r2_down += (a["r2"] >= 0.9) * dt
            l2_on += (a["l2"] >= 0.3) * dt
            s = 1 if x >= 0.3 else -1 if x <= -0.3 else 0
            if s and side and s != side:
                flips += 1
            if s:
                side = s
        # Road or across country on the key frames in a vehicle.
        on = off = unk = 0
        if keys is not None:
            for t, m, sc, crop in zip(keys["t"], keys["map"], keys["screen"], keys["crops"]):
                if not (start <= t <= end) or m != "tilted" or sc != "game":
                    continue
                r = terrain.read(crop)
                if r is None:
                    unk += 1
                elif r.on_road:
                    on += 1
                else:
                    off += 1
        out.append(dict(
            recording=folder.name, start=round(start, 1), end=round(end, 1), seconds=round(end - start, 1),
            ends=why, peak=peak, vehicle=round(tilted / max(1, len(game)), 2), foot=round(flat / max(1, len(game)), 2),
            driven=round(dur, 1),
            steer_mean=round(steer_sum / dur, 2) if dur else None, steer_hard=round(steer_hard / dur, 2) if dur else None,
            steer_changes_per_min=round(flips / dur * 60, 1) if dur else None,
            r2_mean=round(r2_sum / dur, 2) if dur else None, r2_down=round(r2_down / dur, 2) if dur else None,
            l2_share=round(l2_on / dur, 2) if dur else None,
            opened=opened, presses=presses, road=on, country=off, unread=unk,
        ))
        i = max(j, i + 1)
        while i < len(rows) and rows[i]["t"] <= end:
            i += 1
json.dump(out, sys.stdout, indent=1)
