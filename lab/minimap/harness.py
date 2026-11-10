"""Score a minimap reader:  .venv/bin/python harness.py impl_x/minimap.py [--split dev|held] [--json out.json]

Against the labels of the split: minimap class, route presence and colour, bearings, arrow heading, corrupt flag.
Against all crops, without labels: speed, agreement with the human's steering, frame-to-frame jitter.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from tools import load, load_impl  # noqa: E402


def clock_to_deg(clock) -> float | None:
    if clock is None:
        return None
    deg = (float(clock) % 12) * 30
    return deg - 360 if deg > 180 else deg


def angdiff(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def labels(split: str) -> list[dict]:
    _, _, golden = load()
    by_id = {g["id"]: g for g in golden}
    out = []
    for path in sorted((ROOT / "data" / "labels").glob("*.json")):
        for label in json.loads(path.read_text()):
            g = by_id.get(label.get("id"))
            if g is not None and g["split"] == split:
                out.append({**label, "k": g["k"]})
    return out


def ranks(v: np.ndarray) -> np.ndarray:
    order = np.argsort(v, kind="stable")
    r = np.empty(len(v))
    r[order] = np.arange(len(v))
    return r


def angle_stats(errors: list[float]) -> dict:
    if not errors:
        return {"n": 0}
    e = np.array(errors)
    return {"n": len(e), "median_err": round(float(np.median(e)), 1), "within_45": round(float((e <= 45).mean()), 3)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("impl")
    ap.add_argument("--split", default="dev", choices=["dev", "held"])
    ap.add_argument("--json")
    args = ap.parse_args()
    read = load_impl(args.impl).read
    crops, meta, _ = load()
    result: dict = {"impl": args.impl, "split": args.split}

    # --- labelled part
    labs = labels(args.split)
    ok_map = tp = fp = fn = colour_ok = 0
    near, far, arrow, missing_bearing = [], [], [], 0
    c_tp = c_fp = c_fn = 0
    disagreements = []
    for lab in labs:
        r = read(np.asarray(crops[lab["k"]]))
        diff = []
        if r.minimap == lab["minimap"]:
            ok_map += 1
        else:
            diff.append(f"minimap {r.minimap} != {lab['minimap']}")
        has, want = r.route != "none", lab["route"] != "none"
        if has and want:
            tp += 1
            if r.route == lab["route"]:
                colour_ok += 1
            else:
                diff.append(f"colour {r.route} != {lab['route']}")
            for got, clock, errors, name in (
                (r.bearing, lab.get("near_clock"), near, "near"),
                (r.far_bearing, lab.get("far_clock"), far, "far"),
            ):
                want_deg = clock_to_deg(clock)
                if want_deg is None:
                    continue
                if got is None:
                    missing_bearing += 1
                    diff.append(f"{name} bearing missing, label {want_deg:.0f}")
                    continue
                errors.append(angdiff(got, want_deg))
                if errors[-1] > 45:
                    diff.append(f"{name} bearing {got:.0f} vs label {want_deg:.0f}")
        elif has:
            fp += 1
            diff.append(f"route {r.route} but label none")
        elif want:
            fn += 1
            diff.append(f"no route but label {lab['route']}")
        want_arrow = clock_to_deg(lab.get("arrow_clock"))
        if want_arrow is not None and r.arrow is not None:
            arrow.append(angdiff(r.arrow, want_arrow))
            if arrow[-1] > 45:
                diff.append(f"arrow {r.arrow:.0f} vs label {want_arrow:.0f}")
        if r.corrupt and lab.get("corrupt"):
            c_tp += 1
        elif r.corrupt:
            c_fp += 1
        elif lab.get("corrupt"):
            c_fn += 1
        if diff:
            disagreements.append({"id": lab["id"], "k": lab["k"], "diff": diff})
    n = len(labs)
    result["labelled"] = {
        "n": n,
        "minimap_acc": round(ok_map / n, 3) if n else None,
        "route": {"tp": tp, "fp": fp, "fn": fn,
                  "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                  "recall": round(tp / (tp + fn), 3) if tp + fn else None,
                  "colour_acc": round(colour_ok / tp, 3) if tp else None},
        "near_bearing": angle_stats(near),
        "far_bearing": angle_stats(far),
        "bearing_missing": missing_bearing,
        "arrow": angle_stats(arrow),
        "corrupt": {"tp": c_tp, "fp": c_fp, "fn": c_fn},
    }
    result["disagreements"] = disagreements

    # --- all crops, no labels
    n_all = len(meta)
    for k in range(0, n_all, 97):  # warm-up
        read(np.asarray(crops[k]))
    readings, times = [], []
    for k in range(n_all):
        crop = np.asarray(crops[k])
        t0 = time.perf_counter()
        r = read(crop)
        times.append(time.perf_counter() - t0)
        readings.append(r)
    t = np.array(times) * 1000
    result["speed_ms"] = {"mean": round(float(t.mean()), 2), "p95": round(float(np.percentile(t, 95)), 2),
                          "max": round(float(t.max()), 2)}
    result["rates"] = {
        "minimap": {c: sum(r.minimap == c for r in readings) for c in ("none", "flat", "tilted")},
        "route": {c: sum(r.route == c for r in readings) for c in ("none", "yellow", "purple")},
        "corrupt": sum(r.corrupt for r in readings),
    }
    b, s = [], []
    for r, m in zip(readings, meta, strict=True):
        if r.minimap == "tilted" and r.route != "none" and r.bearing is not None and m["r2"] > 0.2:
            b.append(r.bearing)
            s.append(m["steer"])
    b, s = np.array(b), np.array(s)
    strong = (np.abs(s) > 0.3) & (np.abs(b) > 10) if len(b) else np.array([], bool)
    result["steering"] = {
        "n": int(len(b)),
        "spearman": round(float(np.corrcoef(ranks(b), ranks(s))[0, 1]), 3) if len(b) > 10 else None,
        "strong_n": int(strong.sum()),
        "sign_agreement": round(float((np.sign(b[strong]) == np.sign(s[strong])).mean()), 3) if strong.any() else None,
    }
    jumps = []
    for k in range(n_all - 1):
        a, c = readings[k], readings[k + 1]
        same = meta[k]["rec"] == meta[k + 1]["rec"] and meta[k + 1]["i"] - meta[k]["i"] == 6
        if same and a.bearing is not None and c.bearing is not None:
            jumps.append(angdiff(a.bearing, c.bearing))
    result["jitter_deg"] = (
        {"n": len(jumps), "median": round(float(np.median(jumps)), 1), "p90": round(float(np.percentile(jumps, 90)), 1),
         "over_60": int((np.array(jumps) > 60).sum())} if jumps else {"n": 0}
    )
    text = json.dumps(result, indent=1)
    if args.json:
        Path(args.json).write_text(text)
    short = {k: v for k, v in result.items() if k != "disagreements"}
    print(json.dumps(short, indent=1))
    print(f"{len(disagreements)} labelled tiles disagree" + (f" (details in {args.json})" if args.json else ""))
    for d in disagreements[:40]:
        print(" ", d["id"], "k=%d" % d["k"], "; ".join(d["diff"]))


if __name__ == "__main__":
    main()
