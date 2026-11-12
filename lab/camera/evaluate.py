"""The view reading against the labelled frames, from stored detections; nothing here touches a console.

    pilot/.venv/bin/python lab/camera/evaluate.py             the confusion table
    pilot/.venv/bin/python lab/camera/evaluate.py --refit     the bands the labels give, and how they hold
                                                              when each recording is left out in turn
    pilot/.venv/bin/python lab/camera/evaluate.py --detect F  run the detector again on the sample's frames
                                                              (reads the recordings, writes only F)

The frames are those of lab/camera/sample (90 of Kerim's recordings and 50 of the pilot's own sessions of
12 November) and the eight of lab/camera/views.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from pilot.camera import FOOT_BANDS, ViewBand, read_view
from pilot.contract import Detection
from pilot.objects import split_player

HERE = Path(__file__).resolve().parent
RECORDINGS = {"": Path("/Users/kerim/recordings/kerim"), "pilot": Path("/Users/kerim/recordings/pilot")}
SHAPE = (720, 1280)
COLUMNS = ("far", "middle", "near", "none", "unknown", "rider")
NAMED = ("far", "middle", "near")


def detections(rows):
    return tuple(Detection(r["kind"], tuple(r["box"]), r["confidence"]) for r in rows)


def detections_of(rows):
    """The compact rows of lab/camera/sessions: kind, x0, y0, x1, y1, confidence."""
    return tuple(Detection(r[0], tuple(r[1:5]), r[5]) for r in rows)


def load():
    """(group, label, raw detections) for every labelled frame; the group is the recording."""
    sample = json.loads((HERE / "sample/labels.json").read_text())["frames"]
    stored = json.loads((HERE / "sample/detections.json").read_text())
    found = [(item["session"], item["label"], detections(stored[str(item["n"])])) for item in sample]
    views = json.loads((HERE / "views/detections.json").read_text())
    found += [("lab", name.split("-")[-1][:-4], detections(rows)) for name, rows in views.items()]
    return found


def read(raw, calibrations=None):
    kept, figure, vehicle = split_player(raw)
    vehicles = tuple(d for d in kept if d.kind != "person") + ((vehicle,) if vehicle else ())
    others = tuple(d for d in kept if d.kind == "person")
    return read_view(figure, SHAPE, vehicles=vehicles, others=others, calibrations=calibrations)


def table(found, calibrations=None):
    return Counter((label, read(raw, calibrations).view) for _group, label, raw in found)


def show(counts, labels=("far", "middle", "near", "first", "unnamed")):
    print(f"{'':10}" + "".join(f"{c:>9}" for c in COLUMNS) + f"{'total':>9}")
    for label in labels:
        row = [counts[label, c] for c in COLUMNS]
        print(f"{label:10}" + "".join(f"{v:9d}" for v in row) + f"{sum(row):9d}")
    named = sum(counts[v, v] for v in NAMED)
    wrong = sum(counts[v, c] for v in NAMED for c in NAMED if c != v)
    wrong += sum(counts["first", c] for c in NAMED)
    total = sum(counts[v, c] for v in NAMED for c in COLUMNS)
    print(f"far, middle and near frames named right: {named} of {total}; named wrong: {wrong}")


def fit(found, margin_height=0.015, margin_feet=0.03):
    """Bands from the labelled figures: the range each view's figures reach, a margin beyond it."""
    seen = {view: [] for view in NAMED}
    for _group, label, raw in found:
        figure = split_player(raw)[1]
        if label not in seen or figure is None or figure.confidence < 0.8 or read(raw).view == "rider":
            continue
        x0, y0, x1, y1 = figure.box
        if 0.3 <= (x0 + x1) / 2560 <= 0.56:
            seen[label].append(((y1 - y0) / SHAPE[0], y1 / SHAPE[0]))
    bands = []
    for view, items in seen.items():
        heights, feet = zip(*items, strict=True)
        bands.append(
            ViewBand(
                view,
                (round(min(heights) - margin_height, 3), round(max(heights) + margin_height, 3)),
                (round(min(feet) - margin_feet, 3), round(min(1.0, max(feet) + margin_feet), 3)),
            )
        )
    return tuple(bands)


def refit():
    found = load()
    print("bands in use:", [(b.view, b.height, b.feet) for b in FOOT_BANDS])
    print("bands fitted on every frame:", [(b.view, b.height, b.feet) for b in fit(found)])
    print("\nevery frame, bands in use:")
    show(table(found))
    print("\nevery recording left out in turn, bands fitted on the others and read on the one left out:")
    held = Counter()
    for group in sorted({g for g, _, _ in found}):
        bands = {"foot": fit([item for item in found if item[0] != group])}
        held += table([item for item in found if item[0] == group], bands)
    show(held)


def detect(out: Path):
    import cv2

    from pilot.objects import Detector

    detector = Detector()
    rows = {}
    for item in json.loads((HERE / "sample/labels.json").read_text())["frames"]:
        cap = cv2.VideoCapture(str(RECORDINGS[item.get("source", "")] / item["session"] / "video.mp4"))
        cap.set(cv2.CAP_PROP_POS_FRAMES, item["frame"])
        ok, frame = cap.read()
        cap.release()
        if not ok:
            # A recording trimmed since the sample was taken has fewer frames, and moved ones.
            print(f"cannot decode frame {item['frame']} of {item['session']}; skipped")
            continue
        found = detector.detect(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), exclude_player=False)
        rows[str(item["n"])] = [
            {"kind": d.kind, "box": list(d.box), "confidence": d.confidence} for d in found
        ]
    with out.open("x") as stream:
        json.dump(rows, stream, separators=(",", ":"))
    print(f"wrote raw detections for {len(rows)} frames to {out}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--refit", action="store_true")
    parser.add_argument("--detect", type=Path)
    args = parser.parse_args()
    if args.detect:
        detect(args.detect)
    elif args.refit:
        refit()
    else:
        show(table(load()))


if __name__ == "__main__":
    main()
