"""Replay real drive ticks through Reader and Speedometer; OCR only at live cadence.

The offline join is outside the reader and charges the measured job duration,
with a 150 ms completion floor matching the simulator's live OCR delay. The
reader itself retains its one-job, no-wait contract. Recorded map classifications
are reused, so the minimap reader, steering and trip logic are not reevaluated.
"""

import json
from collections import Counter
from dataclasses import asdict
from time import perf_counter

import cv2
import numpy as np

import p104


def replay(session):
    directory = p104.RECORDINGS / ("20261114-" + session)
    frames = p104.load(directory / "frames.jsonl")
    frame_by_id = {r["frame_id"]: r for r in frames}
    ticks = p104.load(directory / "play.jsonl")
    driving = [r for r in ticks if (r.get("skill") or {}).get("name") == "drive_route"]
    ticks = [r for r in ticks if driving[0]["t"] - 3 <= r["t"] <= driving[-1]["t"]]
    modules = {"before": p104.original(), "after": p104.gps}
    meters = {name: module.Speedometer() for name, module in modules.items()}
    # Isolate the meter's contribution with the same improved OCR captures.
    meters["reader_only"] = modules["before"].Speedometer()
    captures = {name: [] for name in modules}
    readers = {}
    for name, module in modules.items():
        def recognize(crop, name=name, module=module):
            result = p104.trace(module, crop)
            captures[name].append(result)
            return None if result["value"] is None else module.Fix(result["value"], quantum=result["quantum"])
        readers[name] = module.Reader(recognizer=recognize)
    ready = {name: -float("inf") for name in modules}
    latest = {name: None for name in meters}
    metrics = {name: Counter() for name in meters}
    samples, observed = [], []
    poll_ms = {name: [] for name in modules}
    cap = cv2.VideoCapture(str(directory / "video.mp4"))
    last_frame, crop = None, None
    for tick_index, row in enumerate(ticks):
        frame = frame_by_id.get(row.get("frame_id"))
        reading = row.get("reading")
        if frame is None or reading is None:
            continue
        at = frame["t"]
        is_drive = (row.get("skill") or {}).get("name") == "drive_route"
        if row.get("fresh") and frame["i"] != last_frame:
            needed = any(at >= ready[name] and (reader._started is None or at - reader._started >= reader.interval)
                         for name, reader in readers.items())
            if needed:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame["i"])
                ok, bgr = cap.read()
                if not ok:
                    raise RuntimeError((session, frame["i"]))
                crop = p104.hud_crop(bgr)
            for name, reader in readers.items():
                result = None
                if at >= ready[name]:
                    previous = reader._started
                    start = perf_counter()
                    result = reader.poll(crop, at)
                    poll_ms[name].append(1000 * (perf_counter() - start))
                    if reader._started != previous:
                        reader._thread.join()  # Offline only: charge completion on the replay clock.
                        capture = dict(captures[name][-1], sampled_at=at, frame=frame["i"], version=name)
                        samples.append(capture)
                        ready[name] = at + max(.15, capture["ms"] / 1000)
                sampled_at, fix = result if result is not None else (at, None)
                for meter_name in ([name, "reader_only"] if name == "after" else [name]):
                    meter = meters[meter_name]
                    if reading["minimap"] != "tilted":
                        meter.reset()
                        fix = None
                    speed = meter.update(at, fix, sampled_at=sampled_at)
                    fresh = meter.time is not None and 0 <= at - meter.time <= meter.stale
                    latest[meter_name] = dict(speed=speed, distance=meter.fix.distance if fresh else None)
                    if result is not None and meter_name != "reader_only":
                        samples.append(dict(version=name, delivered_at=at, sampled_at=sampled_at,
                                            accepted_at=meter.time, speed=speed, segment=meter.segment,
                                            fix=None if fix is None else asdict(fix)))
            last_frame = frame["i"]
        if is_drive:
            result = dict(t=row["t"], frame_time=at)
            for name, value in latest.items():
                metrics[name]["ticks"] += 1
                for key in ("speed", "distance"):
                    present = value is not None and value[key] is not None
                    metrics[name][key] += present
                    result[name + "_" + key] = value[key] if value else None
            result["recorded_speed"] = reading.get("gps_speed")
            result["recorded_distance"] = reading.get("gps_distance")
            observed.append(result)
        if tick_index % 1000 == 0:
            print(session, round(row["t"], 1), "s", flush=True)
    cap.release()
    for reader in readers.values():
        reader.close()
    p104.dump(p104.OUT / f"p104-replay-{session}.jsonl", samples)
    p104.dump(p104.OUT / f"p104-ticks-{session}.jsonl", observed)
    result = dict(session=session, completion_floor=.15, interval=.25, metrics=metrics,
                  poll_ms={n: np.percentile(v,[50,95,99]).tolist() for n,v in poll_ms.items()},
                  ocr_ms={n: np.percentile([r['ms'] for r in v],[50,95,99]).tolist() for n,v in captures.items()},
                  calls={n:len(v) for n,v in captures.items()})
    (p104.OUT / f"p104-replay-{session}-summary.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    for session in p104.SESSIONS:
        replay(session)
