"""Replay P73's 14 windows with reconstructed, timestamped local detections."""

import hashlib
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from time import monotonic

import cv2
import numpy as np
import replay
from pilot.avoid import STALE, passing_side, waits_behind
from pilot.cli import drive_config
from pilot.contract import Reading
from pilot.drive import Driver
from pilot.objects import MODEL, Detector

HERE = Path(__file__).resolve().parent


def main():
    detector = Detector()
    for old in (*HERE.glob("p80-starts-*.jpg"), *HERE.glob("p80-context-*.jpg")):
        old.unlink()
    output = {"evidence": "recorded replay with reconstructed object detections",
        "model_sha256": hashlib.sha256(MODEL.read_bytes()).hexdigest(),
        "confidence": 0.4, "detection_interval": 0.25,
        "note": "The source has no object boxes. Detections come from the recorded full frames, not historical detector output.",
        "windows": [], "starts": [], "reverse_entries": []}
    thumbs = []
    started = monotonic()
    for suffix, windows in replay.WINDOWS.items():
        folder = replay.ROOT / f"20261112-{suffix}"
        play = replay.lines(folder / "play.jsonl")
        motion = replay.motion_for(folder, play)
        selected = {}
        contexts = []
        for start, end in windows:
            context = {"driver": Driver(drive_config(["style=bold"])),
                "objects": (), "objects_time": None, "last_phase": None,
                "row": {"session": folder.name, "start": start, "end": end,
                    "ticks": 0, "detections": 0, "starts": 0, "reverse_entries": 0,
                    "damaged_start_violations": 0, "stale_start_violations": 0,
                    "states": Counter()}}
            contexts.append(context)
            for row in play:
                if (start - 0.0005 <= row["t"] <= end + 0.0005
                    and (row.get("skill") or {}).get("name") == "drive_route"
                    and row.get("reading") and row.get("fresh")):
                    selected.setdefault(row["frame_id"], []).append((context, row))
        cap = cv2.VideoCapture(str(folder / "video.mp4"))
        for ordinal, frame in enumerate(replay.lines(folder / "frames.jsonl")):
            assert frame["i"] == ordinal
            if not cap.grab():
                raise RuntimeError(f"Missing video frame {folder.name}:{ordinal}")
            rows = selected.get(frame["frame_id"])
            if rows is None:
                continue
            ok, bgr = cap.retrieve()
            if not ok:
                raise RuntimeError(f"Cannot retrieve {folder.name}:{ordinal}")
            for context, row in rows:
                now = row["t"]
                report = context["row"]
                if context["objects_time"] is None or now - context["objects_time"] >= 0.25:
                    context["objects"] = detector.detect(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                    context["objects_time"] = now
                    report["detections"] += 1
                objects, objects_time = context["objects"], context["objects_time"]
                reading = replace(Reading(**{k: v for k, v in row["reading"].items()
                    if k in Reading.__dataclass_fields__}), blips=())
                driver = context["driver"]
                previous = driver._phase
                command = driver.step(reading, now, motion.get(row["frame_id"]),
                    speed=reading.gps_speed,
                    ahead=waits_behind(objects, objects_time, now),
                    bypass_side=passing_side(objects, objects_time, now),
                    boxes_fresh=0 <= now - objects_time <= STALE)
                report["ticks"] += 1
                report["states"][command.state] += 1
                entry = (driver._phase in ("bypass-reverse", "turn-reverse")
                    and previous != driver._phase)
                if entry:
                    event = {"session": folder.name, "window_start": report["start"],
                        "t": now, "frame_id": frame["frame_id"], "i": ordinal,
                        "capture_t": frame["t"], "phase": driver._phase,
                        "moving": motion.get(row["frame_id"]), "gps_speed": reading.gps_speed,
                        "corrupt": reading.corrupt, "box_age": now - objects_time,
                        "bearing": reading.bearing, "arrow": reading.arrow,
                        "objects": [{"kind": obj.kind, "box": obj.box,
                            "confidence": obj.confidence} for obj in objects]}
                    report["reverse_entries"] += 1
                    output["reverse_entries"].append(event)
                    if previous is None or not previous.startswith(("bypass-", "turn-")):
                        report["starts"] += 1
                        report["damaged_start_violations"] += reading.corrupt is not False
                        report["stale_start_violations"] += now - objects_time > STALE
                        output["starts"].append(event)
                        thumb = cv2.resize(bgr, (480, 270))
                        for obj in objects:
                            x0, y0, x1, y1 = (round(v * 0.375) for v in obj.box)
                            cv2.rectangle(thumb, (x0, y0), (x1, y1), (0, 220, 255), 1)
                        title = f"{len(thumbs)+1} {suffix} {now:.2f}s {driver._phase}"
                        cv2.rectangle(thumb, (0, 0), (480, 24), (0, 0, 0), -1)
                        cv2.putText(thumb, title, (5, 17), cv2.FONT_HERSHEY_SIMPLEX, .43, (255, 255, 255), 1)
                        thumbs.append(thumb)
        cap.release()
        for context in contexts:
            output["windows"].append(context["row"])
        print(json.dumps({"session": folder.name, "ticks": sum(c["row"]["ticks"] for c in contexts),
            "starts": sum(c["row"]["starts"] for c in contexts), "seconds": monotonic()-started}), flush=True)
        (HERE / "p80-replay.json").write_text(json.dumps(output, indent=2) + "\n")
    for offset in range(0, len(thumbs), 8):
        group = thumbs[offset:offset+8]
        sheet = np.zeros((((len(group)+1)//2)*270, 960, 3), dtype=np.uint8)
        for index, thumb in enumerate(group):
            row, column = divmod(index, 2)
            sheet[row*270:(row+1)*270, column*480:(column+1)*480] = thumb
        cv2.imwrite(str(HERE / f"p80-starts-{offset//8+1}.jpg"), sheet,
            [cv2.IMWRITE_JPEG_QUALITY, 75])
    contexts = []
    for index, event in enumerate(output["starts"], 1):
        folder = replay.ROOT / event["session"]
        frames = replay.lines(folder / "frames.jsonl")
        cap = cv2.VideoCapture(str(folder / "video.mp4"))
        strip = []
        for delta in (-0.6, 0.0, 0.6):
            frame = min(frames, key=lambda f: abs(f["t"] - event["capture_t"] - delta))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame["i"])
            ok, bgr = cap.read()
            if not ok:
                raise RuntimeError(f"Missing context frame {folder.name}:{frame['i']}")
            thumb = cv2.resize(bgr, (480, 270))
            cv2.rectangle(thumb, (0, 0), (480, 24), (0, 0, 0), -1)
            cv2.putText(thumb, f"{index} {folder.name[-6:]} {frame['t']:.2f}s ({delta:+.1f})",
                (5, 17), cv2.FONT_HERSHEY_SIMPLEX, .43, (255, 255, 255), 1)
            strip.append(thumb)
        cap.release()
        contexts.append(np.concatenate(strip, axis=1))
    for offset in range(0, len(contexts), 4):
        cv2.imwrite(str(HERE / f"p80-context-{offset//4+1}.jpg"),
            np.concatenate(contexts[offset:offset+4], axis=0), [cv2.IMWRITE_JPEG_QUALITY, 75])
    print(json.dumps({"windows": len(output["windows"]),
        "ticks": sum(r["ticks"] for r in output["windows"]),
        "starts": len(output["starts"]), "reverse_entries": len(output["reverse_entries"]),
        "sheets": (len(thumbs)+7)//8}), flush=True)


if __name__ == "__main__":
    main()
