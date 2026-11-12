"""Conservative offline trimming. Video position changes; recording time does not."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path

ALLOWED = {"foot", "drive", "menu", "unknown"}
PROTECTED_TEXT = {"subtitle", "objective", "banner", "dialogue"}
GAP_SECONDS = 1.0


def read_lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def frame_runs(rows):
    """Half-open ordinal ranges with no missing stretch of recording time."""
    start = 0
    for i in range(1, len(rows)):
        if rows[i]["t"] - rows[i - 1]["t"] > GAP_SECONDS:
            yield start, i
            start = i
    if rows:
        yield start, len(rows)


def resting(state):
    return (
        not state.get("buttons")
        and all(float(state.get(k, 0)) < 0.1 for k in ("l2", "r2"))
        and all(math.hypot(*state.get(k, [0, 0])) < 0.25 for k in ("left", "right"))
    )


def _frames(recording):
    rows = read_lines(recording / "frames.jsonl")
    if not rows or any(row["i"] != i for i, row in enumerate(rows)):
        raise ValueError("Frame indices must be contiguous video positions")
    if len({r["frame_id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate frame_id")
    if any(b["t"] < a["t"] for a, b in itertools.pairwise(rows)):
        raise ValueError("Recording clock goes backwards")
    return rows


def plan(recording, derived):
    recording, derived = Path(recording), Path(derived)
    rows = _frames(recording)
    human = [p for p in read_lines(recording / "pad.jsonl") if p.get("src") == "human"]
    result = {
        "version": 1,
        "recording": str(recording.resolve()),
        "index_meaning": "position in this video",
        "no_human_input": not human,
        "whole_recording_would_be_cut": False,
        "stretches": [],
    }
    if not human:
        result["reason"] = "No human input; controller inactivity cannot judge this recording"
        return result
    sections = json.loads((derived / "sections.json").read_text())["sections"]
    texts = read_lines(derived / "texts.jsonl")
    protections = [
        (float(s["start"]), float(s["end"]), f"section: {s['kind']}")
        for s in sections
        if s["kind"] not in ALLOWED
    ]
    protections += [
        (float(t["first"]) - 5, float(t["last"]) + 5, f"text: {t['kind']}")
        for t in texts
        if t["kind"] in PROTECTED_TEXT
    ]
    # Missing section coverage is not evidence of an unknown game screen.
    covered = sorted((float(s["start"]), float(s["end"])) for s in sections)
    cursor = rows[0]["t"]
    for lo, hi in covered:
        if lo > cursor + 1:
            protections.append((cursor, lo, "sections unavailable"))
        cursor = max(cursor, hi)
    if cursor < rows[-1]["t"] - 1:
        protections.append((cursor, rows[-1]["t"], "sections unavailable"))
    quiet = []
    for j, pad in enumerate(human):
        lo = max(float(pad["t"]), rows[0]["t"])
        hi = min(float(human[j + 1]["t"]) if j + 1 < len(human) else rows[-1]["t"], rows[-1]["t"])
        if resting(pad) and hi > lo:
            if quiet and abs(quiet[-1][1] - lo) < 1e-6:
                quiet[-1] = (quiet[-1][0], hi)
            else:
                quiet.append((lo, hi))
    for first, stop in frame_runs(rows):
        for lo, hi in quiet:
            lo, hi = max(lo, rows[first]["t"]), min(hi, rows[stop - 1]["t"])
            if hi - lo < 60:
                continue
            bounds = sorted({lo, hi} | {max(lo, min(hi, x)) for a, b, _ in protections for x in (a, b)})
            segments = []
            for a, b in itertools.pairwise(bounds):
                reasons = sorted({why for p, q, why in protections if p < b and q > a})
                if segments and segments[-1][2] == reasons:
                    segments[-1] = (segments[-1][0], b, reasons)
                else:
                    segments.append((a, b, reasons))
            for a, b, reasons in segments:
                eligible = not reasons and b - a >= 60
                item = {
                    "start": a + 5 if eligible else a,
                    "end": b - 5 if eligible else b,
                    "rest_start": a,
                    "rest_end": b,
                    "decision": "cut" if eligible else "keep",
                    "reason": "; ".join(reasons)
                    if reasons
                    else (
                        "Human controller rests for at least 60 seconds; keep five seconds at each end"
                        if eligible
                        else "Unprotected rest is shorter than 60 seconds"
                    ),
                }
                result["stretches"].append(item)
                if eligible and a <= rows[0]["t"] + 1 and b >= rows[-1]["t"] - 1:
                    result["whole_recording_would_be_cut"] = True
    return result


def _av():
    try:
        import av

        return av
    except ImportError as exc:
        raise ImportError("PyAV is required: uv pip install --python .venv/bin/python 'av>=12'") from exc


def _packets(recording, rows):
    av = _av()
    with av.open(str(recording / "video.mp4")) as container:
        if len(container.streams) != 1 or len(container.streams.video) != 1:
            raise ValueError("Only single-video-stream recordings are supported")
        stream = container.streams.video[0]
        packets = [
            {"pts": p.pts, "dts": p.dts, "key": p.is_keyframe, "duration": p.duration}
            for p in container.demux(stream)
            if p.size
        ]
        base = stream.time_base
    if len(packets) != len(rows) or any(p["pts"] is None or p["dts"] is None for p in packets):
        raise ValueError("Video packets do not map one-to-one to frame rows")
    positions = {pts: i for i, pts in enumerate(sorted(p["pts"] for p in packets))}
    if len(positions) != len(rows):
        raise ValueError("Duplicate presentation timestamp")
    for p in packets:
        p["i"] = positions[p["pts"]]
    keys = [i for i, p in enumerate(packets) if p["key"]]
    if not keys or keys[0] != 0:
        raise ValueError("Video does not start with a keyframe")
    return packets, keys, base


def cut(recording, plan_path, destination):
    recording, destination = Path(recording), Path(destination)
    if destination.exists() or destination.resolve().is_relative_to(recording.resolve()):
        raise ValueError("Output must be a new folder outside the source recording")
    rows = _frames(recording)
    specification = json.loads(Path(plan_path).read_text())
    if Path(specification["recording"]).resolve() != recording.resolve():
        raise ValueError("Plan belongs to another recording")
    ranges = [
        (float(s["start"]), float(s["end"])) for s in specification["stretches"] if s["decision"] == "cut"
    ]
    if any(not math.isfinite(a + b) or a >= b or a < rows[0]["t"] or b > rows[-1]["t"] for a, b in ranges):
        raise ValueError("Invalid cut interval")
    packets, keys, time_base = _packets(recording, rows)
    omitted, cuts = set(), []
    for first, stop in itertools.pairwise(keys):
        group = packets[first:stop]
        a, b = packets[first]["i"], packets[stop]["i"]
        # Open GOPs that straddle the next keyframe are retained conservatively.
        closed = sorted(p["i"] for p in group) == list(range(a, b))
        if closed and any(lo <= rows[a]["t"] and rows[b]["t"] <= hi for lo, hi in ranges):
            omitted.update(range(first, stop))
            item = {
                "start": rows[a]["t"],
                "end": rows[b]["t"],
                "first_frame": a,
                "stop_frame": b,
                "video_seconds": float((packets[stop]["pts"] - packets[first]["pts"]) * time_base),
            }
            if cuts and cuts[-1]["stop_frame"] == a:
                cuts[-1].update(
                    end=item["end"],
                    stop_frame=b,
                    video_seconds=cuts[-1]["video_seconds"] + item["video_seconds"],
                )
            else:
                cuts.append(item)
    removed_frames = {packets[i]["i"] for i in omitted}
    kept = [dict(row, i=i) for i, row in enumerate(r for j, r in enumerate(rows) if j not in removed_frames)]
    meta = json.loads((recording / "meta.json").read_text())
    trim = {
        "source": str(recording.resolve()),
        "index_meaning": "position in this video",
        "cuts": cuts,
        "frames_before": len(rows),
        "frames_after": len(kept),
        "seconds_before": float(sum(p["duration"] for p in packets) * time_base),
        "seconds_after": float(
            sum(p["duration"] for i, p in enumerate(packets) if i not in omitted) * time_base
        ),
        "recording_clock_start": rows[0]["t"],
        "recording_clock_end": rows[-1]["t"],
        "derived_data": "Rebuild for the new video indices with lab/process-recordings.sh",
    }
    av = _av()
    destination.mkdir(parents=True)
    with (
        av.open(str(recording / "video.mp4")) as source,
        av.open(str(destination / "video.mp4"), "w") as output,
    ):
        stream = source.streams.video[0]
        target = output.add_stream_from_template(stream)
        offset, ordinal = 0, 0
        for packet in source.demux(stream):
            if not packet.size:
                continue
            if ordinal in omitted:
                offset += packet.duration
            else:
                packet.pts -= offset
                packet.dts -= offset
                packet.stream = target
                output.mux(packet)
            ordinal += 1
    (destination / "frames.jsonl").write_text("".join(json.dumps(r) + "\n" for r in kept))
    pad_lines = (recording / "pad.jsonl").read_text().splitlines(keepends=True)
    retained_pads = [
        line
        for line in pad_lines
        if line.strip() and not any(c["start"] <= json.loads(line)["t"] < c["end"] for c in cuts)
    ]
    (destination / "pad.jsonl").write_text("".join(retained_pads))
    meta.update(frames=len(kept), pad_events=len(retained_pads), trim=trim)
    (destination / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return trim


def _decode(recording, rows, samples):
    av = _av()
    hashes, count = {}, 0
    with av.open(str(recording / "video.mp4")) as container:
        container.streams.video[0].thread_type = "AUTO"
        for i, frame in enumerate(container.decode(video=0)):
            if i >= len(rows):
                raise ValueError(f"Extra decoded frame in {recording}")
            if rows[i]["frame_id"] in samples:
                hashes[rows[i]["frame_id"]] = hashlib.sha256(
                    frame.to_ndarray(format="rgb24").tobytes()
                ).hexdigest()
            count += 1
        duration = float(container.streams.video[0].duration * container.streams.video[0].time_base)
    if count != len(rows):
        raise ValueError(f"Decoded {count} frames but frames.jsonl has {len(rows)} in {recording}")
    return hashes, duration


def check(source, trimmed):
    source, trimmed = Path(source), Path(trimmed)
    original, kept = _frames(source), _frames(trimmed)
    trim = json.loads((trimmed / "meta.json").read_text())["trim"]
    cuts = trim["cuts"]
    removed = {i for c in cuts for i in range(c["first_frame"], c["stop_frame"])}
    expected = [dict(row, i=i) for i, row in enumerate(r for j, r in enumerate(original) if j not in removed)]
    if kept != expected:
        raise ValueError("Kept frame metadata differs from source or a frame is missing")
    lines = (source / "pad.jsonl").read_text().splitlines(keepends=True)
    expected_pads = "".join(
        line
        for line in lines
        if line.strip() and not any(c["start"] <= json.loads(line)["t"] < c["end"] for c in cuts)
    )
    if (trimmed / "pad.jsonl").read_text() != expected_pads:
        raise ValueError("A kept pad line is missing or changed")
    if len(kept) < 50:
        raise ValueError("At least fifty kept frames are required for a verified cut")
    samples = {kept[round(i * (len(kept) - 1) / 49)]["frame_id"] for i in range(50)}
    # Include the pictures directly on both sides of every splice as well.
    for a, b in itertools.pairwise(kept):
        if b["t"] - a["t"] > GAP_SECONDS:
            samples.update((a["frame_id"], b["frame_id"]))
    before, seconds_before = _decode(source, original, samples)
    after, seconds_after = _decode(trimmed, kept, samples)
    if before != after or len(after) < 50:
        raise ValueError("Kept pictures do not match source frame_id pixels")
    if trim["frames_before"] != len(original) or trim["frames_after"] != len(kept):
        raise ValueError("Frame counts in meta.json are incorrect")
    if (
        abs(trim["seconds_before"] - seconds_before) > 0.05
        or abs(trim["seconds_after"] - seconds_after) > 0.05
    ):
        raise ValueError("Video lengths disagree with meta.json")
    return {
        "ok": True,
        "sampled_frames": len(after),
        "frames_before": len(original),
        "frames_after": len(kept),
        "seconds_before": seconds_before,
        "seconds_after": seconds_after,
        "bytes_before": sum(p.stat().st_size for p in source.iterdir() if p.is_file()),
        "bytes_after": sum(p.stat().st_size for p in trimmed.iterdir() if p.is_file()),
        "pad_lines_kept": len(expected_pads.splitlines()),
    }
