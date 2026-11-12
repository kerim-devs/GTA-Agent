"""Where `pilot.foot.find_road` puts the nearest road, on minimap crops of a recording.

    pilot/.venv/bin/python lab/foot/roads.py RECORDING OUT.jpg [STEP_SECONDS]

Every STEP seconds (default 4) the crop is drawn at twice its size with the road pixel the reader
chose (green dot and line from the arrow), its direction along the road (red), or "no road". It also
prints on how many sampled frames a road was found and how far it was.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pilot" / "src"))

from pilot.foot import find_road, hud_crop
from pilot.minimap import ACX, ACY


def main(recording: Path, out: Path, step: float):
    frames = [json.loads(line) for line in (recording / "frames.jsonl").open()]
    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    tiles, found, sampled, distances, nxt = [], 0, 0, [], frames[0]["t"]
    for item in frames:
        ok, bgr = capture.read()
        if not ok:
            break
        if item["t"] < nxt:
            continue
        nxt += step
        crop = hud_crop(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        road = find_road(crop)
        sampled += 1
        tile = cv2.resize(
            cv2.cvtColor(crop, cv2.COLOR_RGB2BGR),
            (520, 340),
            interpolation=cv2.INTER_NEAREST,
        )
        cx, cy = int(ACX * 2), int(ACY * 2)
        if road is None:
            cv2.putText(
                tile,
                "no road",
                (200, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
            )
        else:
            found += 1
            distances.append(road.distance)
            r = np.radians(road.bearing)
            px, py = (
                cx + int(2 * road.distance * np.sin(r)),
                cy - int(2 * road.distance * np.cos(r)),
            )
            cv2.line(tile, (cx, cy), (px, py), (0, 200, 0), 2)
            cv2.circle(tile, (px, py), 6, (0, 200, 0), -1)
            if road.along is not None:
                a = np.radians(road.along)
                cv2.line(
                    tile,
                    (px - int(30 * np.sin(a)), py + int(30 * np.cos(a))),
                    (px + int(30 * np.sin(a)), py - int(30 * np.cos(a))),
                    (0, 0, 255),
                    2,
                )
        cv2.putText(
            tile,
            f"{item['t']:.0f}s",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
        )
        tiles.append(tile)
    capture.release()
    while len(tiles) % 6:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i : i + 6]) for i in range(0, len(tiles), 6)]
    sheet = np.vstack(rows)
    sheet = cv2.resize(
        sheet, (sheet.shape[1] // 2, sheet.shape[0] // 2), interpolation=cv2.INTER_AREA
    )
    cv2.imwrite(str(out), sheet, [cv2.IMWRITE_JPEG_QUALITY, 75])
    median = float(np.median(distances)) if distances else None
    print(
        f"{recording.name}: road on {found} of {sampled} sampled frames, median distance {median}"
    )


if __name__ == "__main__":
    main(
        Path(sys.argv[1]),
        Path(sys.argv[2]),
        float(sys.argv[3]) if len(sys.argv) > 3 else 4.0,
    )
