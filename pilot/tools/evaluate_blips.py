"""Score manually labeled circles and save enlarged overlays for review."""

import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from pilot.minimap import read


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    output = root / "lab/blips"
    crops = np.load(root / "lab/minimap/data/crops.npy", mmap_mode="r")
    labels = []
    for path in sorted(output.glob("*-labels.json")):
        labels.extend(json.loads(path.read_text()))
    np.savez_compressed(
        output / "crops.npz",
        crops=np.array([crops[row["id"]] for row in labels]),
        ids=np.array([row["id"] for row in labels]),
    )
    rows = []
    totals = {c: {"found": 0, "missed": 0, "invented": 0, "errors": []} for c in ("yellow", "blue", "red")}
    tiles = []
    times = []
    for label in labels:
        crop = crops[label["id"]]
        start = perf_counter()
        reading = read(crop)
        times.append(perf_counter() - start)
        got = [(b.color, b.x + 123, 117 - b.y) for b in reading.blips]
        unmatched = set(range(len(got)))
        matches, misses = [], []
        for color, x, y in label["blips"]:
            candidates = [
                (float(np.hypot(x - got[i][1], y - got[i][2])), i) for i in unmatched if got[i][0] == color
            ]
            if candidates and min(candidates)[0] <= 5:
                error, index = min(candidates)
                unmatched.remove(index)
                totals[color]["found"] += 1
                totals[color]["errors"].append(error)
                matches.append([color, x, y, error])
            else:
                totals[color]["missed"] += 1
                misses.append([color, x, y])
        invented = [got[i] for i in unmatched]
        for color, _, _ in invented:
            totals[color]["invented"] += 1
        rows.append(
            {
                "id": label["id"],
                "map": label["map"],
                "reading": asdict(reading),
                "found": matches,
                "missed": misses,
                "invented": invented,
            }
        )
        tile = np.zeros((370, 520, 3), np.uint8)
        tile[:340] = cv2.resize(
            cv2.cvtColor(crop, cv2.COLOR_RGB2BGR), (520, 340), interpolation=cv2.INTER_NEAREST
        )
        for _, x, y in label["blips"]:
            cv2.drawMarker(tile, (round(x * 2), round(y * 2)), (255, 255, 255), cv2.MARKER_CROSS, 8, 1)
        for color, x, y in got:
            cv2.circle(tile, (round(x * 2), round(y * 2)), 11, (0, 255, 0), 1)
            cv2.putText(
                tile, color, (round(x * 2) + 10, round(y * 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1
            )
        cv2.putText(
            tile,
            f"{label['id']} {label['map']}: found {len(matches)} "
            f"missed {len(misses)} invented {len(invented)}",
            (5, 360),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 255, 255),
            1,
        )
        tiles.append(tile)
    for offset in range(0, len(tiles), 4):
        group = tiles[offset : offset + 4]
        sheet = np.concatenate([np.concatenate(group[:2], axis=1), np.concatenate(group[2:], axis=1)])
        cv2.imwrite(str(output / f"overlay-{offset // 4:02}.jpg"), sheet)
    for metrics in totals.values():
        found, missed, invented = metrics["found"], metrics["missed"], metrics["invented"]
        metrics["recall"] = found / (found + missed) if found + missed else None
        metrics["invented_fraction"] = invented / (found + invented) if found + invented else 0
        metrics["median_error_px"] = float(np.median(metrics["errors"])) if metrics["errors"] else None
        metrics["max_error_px"] = max(metrics["errors"]) if metrics["errors"] else None
    summary = {
        "crops": len(labels),
        "flat": sum(r["map"] == "flat" for r in labels),
        "vehicle": sum(r["map"] == "tilted" for r in labels),
        "with_blips": sum(bool(r["blips"]) for r in labels),
        "mean_ms": 1000 * float(np.mean(times)),
        "colors": totals,
    }
    (output / "scores.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "scored-crops.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(
        json.dumps(
            {
                **summary,
                "colors": {c: {k: v for k, v in m.items() if k != "errors"} for c, m in totals.items()},
            },
            indent=2,
        )
    )
    print(
        "Disagreements:",
        [(r["id"], r["missed"], r["invented"]) for r in rows if r["missed"] or r["invented"]],
    )


if __name__ == "__main__":
    main()
