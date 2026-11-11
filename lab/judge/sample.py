"""Pick the frames the judge is measured on and say what the readers make of each.

    pilot/.venv/bin/python lab/judge/sample.py

Writes lab/judge/sample/<name>.jpg (rebuilt, not in git) and lab/judge/sample.json. The expected
situation is what the pilot's own readers say, with the hand-labelled menu intervals of
lab/screens/labels.json on top; it is a reference to compare against, not ground truth.
"""

import json
from pathlib import Path

import cv2

from pilot.conductor import minimap_crop
from pilot.hud import read as read_hud
from pilot.minimap import read as read_map

HERE = Path(__file__).resolve().parent
CABLE = Path("/Users/kerim/recordings")
WIFI = HERE.parent.parent / "recordings" / "20261110-093238"
MENUS = ("pause", "map", "phone", "weapon_wheel", "interaction_menu")


def evenly(count, total, first=0):
    step = (total - first) / count
    return [int(first + step * (i + 0.5)) for i in range(count)]


def at_times(folder, seconds):
    times = [json.loads(line)["t"] for line in (folder / "frames.jsonl").open()]
    return [min(range(len(times)), key=lambda i: abs(times[i] - t)) for t in seconds]


def spread(first, last, count):
    return [first + (last - first) * (i + 1) / (count + 1) for i in range(count)]


labels = json.loads((HERE.parent / "screens" / "labels.json").read_text())["sources"]
tour = labels["tour"]["intervals"]
picks = {
    # Kerim playing over the cable: stealing cars, one and two stars, fist fights.
    "kerim": (CABLE / "kerim/20261111-065022", evenly(110, 22479)),
    # Every menu of the game, opened one after the other, and the play between them.
    "tour": (
        CABLE / "screen-tour/20261111-070239",
        sorted(
            [int(i) for item in tour for i in spread(item["first"], item["last"], 5)]
            + [30, 60, 600, 650, 900, 950, 1200, 1250, 1600, 1700]
        ),
    ),
    # The pilot walking in free roam.
    "pilot": (CABLE / "pilot/20261110-231512", evenly(20, 14312)),
    # Wi-Fi, a third of it damaged: a failed mission, stars while driving, and the death.
    "wifi": (
        WIFI,
        sorted(
            set(
                at_times(
                    WIFI,
                    spread(30, 40, 10) + spread(536, 626, 14) + spread(629, 640, 6) + spread(230, 310, 10),
                )
            )
        ),
    ),
}


def situation(source, index, hud, reading):
    if source == "tour":
        for item in tour:
            if item["first"] <= index <= item["last"]:
                return "menu"
    if hud.screen in MENUS:
        return "menu"
    if hud.screen in ("failed", "wasted", "busted"):
        return "dead_or_failed"
    if hud.screen == "loading" or reading.minimap == "none":
        return "cutscene"
    return "vehicle" if reading.minimap == "tilted" else "foot"


rows = []
(HERE / "sample").mkdir(exist_ok=True)
for source, (folder, wanted_frames) in picks.items():
    video = cv2.VideoCapture(str(folder / "video.mp4"))
    wanted, index = set(wanted_frames), 0
    while wanted:
        ok, bgr = video.read()
        if not ok:
            break
        if index in wanted:
            wanted.discard(index)
            bgr = cv2.resize(bgr, (1280, 720)) if bgr.shape[:2] != (720, 1280) else bgr
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            hud, reading = read_hud(rgb), read_map(minimap_crop(rgb))
            name = f"{source}-{index:05d}"
            cv2.imwrite(str(HERE / "sample" / f"{name}.jpg"), bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
            rows.append(
                {
                    "name": name,
                    "source": source,
                    "frame": index,
                    "screen": hud.screen,
                    "minimap": reading.minimap,
                    "corrupt": reading.corrupt,
                    "wanted": hud.wanted,
                    "situation": situation(source, index, hud, reading),
                }
            )
        index += 1
(HERE / "sample.json").write_text(json.dumps(rows, indent=1) + "\n")
counts = {}
for row in rows:
    counts[row["situation"]] = counts.get(row["situation"], 0) + 1
print(len(rows), "frames", counts)
