"""Compare recorded controller input with the current live route driver, offline."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import cv2

from pilot.cli import LIVE, MEASURED_DELAY_S
from pilot.drive import DriveConfig
from pilot.gps import Speedometer, recognize
from pilot.humandrive import (
    analyze,
    controller_lines,
    durations,
    estimate_lead,
    gps_reading,
    has_hand,
    json_lines,
    metrics_for,
    sample_frames,
)
from pilot.minimap import read
from pilot.replay import hud_crop


def readings(recording, destination, config, refresh=False):
    cache = destination / "readings-v3.jsonl"
    if cache.exists() and not refresh:
        return json_lines(cache)
    frames = json_lines(recording / "frames.jsonl")
    selected = {row["i"] for row in sample_frames(frames)}
    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    speedometer = Speedometer(
        window=config.gps_window,
        stale=config.gps_stale,
        max_speed=config.gps_max_speed,
        tolerance=config.gps_tolerance,
        acceleration=config.gps_acceleration,
    )
    last_ocr = None
    rows = []
    temporary = cache.with_suffix(".tmp")
    try:
        with temporary.open("w") as output:
            for index, frame in enumerate(frames):
                if frame["i"] != index:
                    raise ValueError("frames.jsonl indices must match sequential video frames")
                if not capture.grab():
                    raise ValueError(f"video ended before frame {index}")
                if index not in selected:
                    continue
                ok, bgr = capture.retrieve()
                if not ok:
                    raise ValueError(f"cannot decode frame {index}")
                crop = hud_crop(bgr)
                reading = read(crop)
                t = float(frame["t"])
                fix = None
                if reading.minimap == "tilted" and (last_ocr is None or t - last_ocr >= config.gps_interval):
                    fix = recognize(crop)
                    last_ocr = t
                reading = gps_reading(reading, speedometer, t, fix)
                row = {"t": t, "i": index, "frame_id": frame["frame_id"], "reading": asdict(reading)}
                rows.append(row)
                output.write(json.dumps(row) + "\n")
                if len(rows) % 3000 == 0:
                    print(f"{recording.name}: {t:.1f}s, {len(rows)} readings", flush=True)
        temporary.replace(cache)
    finally:
        capture.release()
    return rows


def load_sections(root, recording):
    if root is None:
        return None
    candidates = [
        root / recording.name / "sections.json",
        root / f"{recording.name}.json",
        root / "sections.json",
    ]
    for path in candidates:
        if path.exists():
            data = json.loads(path.read_text())
            if Path(data["recording"]).name == recording.name:
                return data["sections"]
    raise ValueError(f"no matching P38 sections for {recording}")


def contact_sheets(results, output):
    import numpy as np

    candidates = []
    for result in results:
        if result.get("source") != "human":
            continue
        for row in result.get("rows", []):
            if row["clear"]:
                hand = row["hand"]
                score = abs(hand["left"][0] - row["command"]["steer"])
                candidates.append((score, result["recording"], row))
    chosen = []
    for score, recording, row in sorted(candidates, key=lambda item: item[0], reverse=True):
        if any(rec == recording and abs(other["t"] - row["t"]) < 3 for _, rec, other in chosen):
            continue
        chosen.append((score, recording, row))
        if len(chosen) == 20:
            break
    records = []
    for group in range(0, len(chosen), 4):
        tiles = []
        for index, (score, recording, row) in enumerate(chosen[group : group + 4], group + 1):
            capture = cv2.VideoCapture(str(Path(recording) / "video.mp4"))
            capture.set(cv2.CAP_PROP_POS_FRAMES, row["i"])
            ok, bgr = capture.read()
            capture.release()
            if not ok:
                raise ValueError(f"cannot decode contact frame {recording}:{row['i']}")
            tile = np.zeros((460, 800, 3), dtype=np.uint8)
            tile[:360, :640] = cv2.resize(bgr, (640, 360))
            hud = cv2.cvtColor(hud_crop(bgr), cv2.COLOR_RGB2BGR)
            tile[:340, 640:] = cv2.resize(hud, (160, 340))
            h, c = row["hand"], row["command"]
            labels = [
                f"#{index} {Path(recording).name} t={row['t']:.3f}s frame={row['i']} gap={score:.3f}",
                f"Hand: stick {h['left'][0]:+.2f} R2 {h.get('r2', 0):.2f} L2 {h.get('l2', 0):.2f}",
                f"Driver: stick {c['steer']:+.2f} R2 {c['throttle']:.2f} L2 {c['brake']:.2f} {c['state']}",
                f"Speed {row['reading'].get('gps_speed')} limit {row['limit']}",
            ]
            for line, text in enumerate(labels):
                cv2.putText(
                    tile, text[:110], (8, 380 + 22 * line), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 1
                )
            tiles.append(tile)
            records.append(
                {
                    "rank": index,
                    "recording": recording,
                    "t": row["t"],
                    "frame": row["i"],
                    "difference": score,
                    "hand": h,
                    "command": c,
                    "reading": row["reading"],
                    "sheet": f"contact-{group // 4 + 1:02d}.jpg",
                }
            )
        while len(tiles) < 4:
            tiles.append(np.zeros_like(tiles[0]))
        sheet = np.vstack([np.hstack(tiles[:2]), np.hstack(tiles[2:])])
        cv2.imwrite(str(output / f"contact-{group // 4 + 1:02d}.jpg"), sheet)
    (output / "divergences.json").write_text(json.dumps(records, indent=2) + "\n")
    return records


def fmt(value):
    return "n/a" if value is None else f"{value:.3f}"


def write_summary(results, output, config):
    pooled = []
    weights = []
    for result in results:
        if result.get("source") == "human" and result["status"] == "analyzed":
            pooled.extend(result["rows"])
            weights.extend(durations(result["rows"]))
    metrics = metrics_for(pooled, weights, config)
    moments = [m for r in results if r.get("source") == "human" for m in r.get("clear_moments", [])]
    metrics["clear_moments"] = len(moments)
    metrics["moment_direction_share"] = (
        sum(m["same_direction_share"] > 0.5 for m in moments) / len(moments) if moments else None
    )
    (output / "summary.json").write_text(json.dumps(metrics, indent=2) + "\n")
    text = [
        "# Recorded driving against the live driver",
        "",
        "Capture-clock samples at 30 Hz; no interpolation across missing frames. Controller "
        "states are held until the next event. Pilot self-check is excluded from human totals.",
        "",
        "The lead is fitted to changes in route-relative visual heading, independently of "
        "driver commands. All response-lag fits are provisional; geometry changes can confound them. GPS "
        "speed is a causal distance slope, not a ground-truth speedometer. Lateral "
        "acceleration is an ahead-path proxy using the driver's 0.7 metres/pixel scale, not "
        "measured vehicle acceleration.",
        "",
        "| Recording | Source | Route seconds | Lead seconds | Resolved | Clear moments | "
        "Direction seconds share |",
        "|---|---|---:|---:|---|---:|---:|",
    ]
    for result in results:
        m = result.get("metrics") or {}
        a = result.get("alignment") or {}
        text.append(
            f"| {Path(result['recording']).name} | {result['source']} | {fmt(result['route_seconds'])} | "
            f"{fmt(a.get('seconds'))} | {a.get('resolved', False)} | {m.get('clear_moments', 0)} | "
            f"{fmt(m.get('direction_seconds_share'))} |"
        )
        if result["status"] != "analyzed":
            text.extend(
                ["", f"{Path(result['recording']).name}: {result['status']}: {result['reason']}.", ""]
            )
    text.extend(
        [
            "",
            f"Human route driving with controller: {metrics['route_seconds']:.3f} seconds. "
            "All shares are time-weighted with explicit subsets below.",
            "",
            "| Metric | Value |",
            "|---|---:|",
        ]
    )
    for key, value in metrics.items():
        if not isinstance(value, list):
            text.append(f"| {key} | {fmt(value)} |")
    text.extend(
        [
            "",
            "Clear moments require a same-sign stick of at least 0.3 for at least 0.3 s. Moment "
            "agreement means the same direction for more than half the moment; the "
            "seconds-weighted share is reported separately. Curvature bins are >=0.01 inverse "
            "pixels for bends and <0.005 for straights. Lift timing is measured before crossing "
            "the ahead-path bend threshold, not before physical entry to a bend.",
            "",
            "Pedal shares use raw recorded controls: full R2 >=0.95, lifted R2 <=0.05, braking L2 "
            ">0.05. Pilot pedal output has a hardware profile and is not equated with Driver "
            "throttle.",
            "",
            "## Driving without a route",
            "",
        ]
    )
    for result in results:
        check = result.get("self_check")
        if check:
            fit = check["visual_response_fit"]
            text.extend(
                [
                    f"Pilot self-check uses the configured {MEASURED_DELAY_S:.3f}s reference. "
                    f"Independent visual-response fit: {fmt(fit.get('seconds'))}s. "
                    "Independent command-delay remeasurement FAILED: vehicle response and route geometry "
                    "cannot be separated from transport delay in these observations.",
                    "",
                ]
            )
    for result in results:
        stretches = result.get("no_route_stretches", [])
        text.append(
            f"{Path(result['recording']).name}: "
            + (", ".join(f"{s['start']:.3f}-{s['end']:.3f}s" for s in stretches) or "none observed")
            + "."
        )
        text.append("")
    (output / "summary.md").write_text("\n".join(text) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", nargs="*", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sections", type=Path)
    parser.add_argument("--refresh", action="store_true", help="rebuild derived reader cache from video")
    parser.add_argument("--summarize", action="store_true", help="combine existing drive.json files")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    config = DriveConfig(command_delay=MEASURED_DELAY_S, **LIVE)
    results = []
    for recording in args.recording:
        destination = args.out / recording.name
        destination.mkdir(parents=True, exist_ok=True)
        source = "agent" if recording.name == "20261111-134217" else "human"
        pads = controller_lines(json_lines(recording / "pad.jsonl"), source)
        if not has_hand(pads):
            result = analyze([], pads, config)
        else:
            rows = readings(recording, destination, config, args.refresh)
            if source == "agent":
                result = analyze(
                    rows, pads, config, load_sections(args.sections, recording), lead=MEASURED_DELAY_S
                )
                response_lag = estimate_lead(rows, pads)
                result["self_check"] = {
                    "reference_lead_seconds": MEASURED_DELAY_S,
                    "visual_response_fit": response_lag,
                    "independent_delay_check_passed": False,
                    "reason": "Visual heading response includes vehicle dynamics and route geometry; "
                    "it does not independently identify command-to-picture delay.",
                }
                result["alignment"]["reason"] = (
                    "known MEASURED_DELAY_S reference, not independently remeasured"
                )
                result["alignment"]["physical_delay_validated"] = False
            else:
                result = analyze(rows, pads, config, load_sections(args.sections, recording))
        result.update(
            recording=str(recording.resolve()),
            source=source,
            config=asdict(config),
            sections=str(args.sections) if args.sections else None,
        )
        (destination / "drive.json").write_text(json.dumps(result, separators=(",", ":")) + "\n")
        print(
            f"{recording.name}: {result['status']}, route={result['route_seconds']:.3f}s, "
            f"alignment={result.get('alignment', {}).get('seconds')}",
            flush=True,
        )
        results.append(result)
    if args.summarize:
        results = [json.loads(path.read_text()) for path in sorted(args.out.glob("*/drive.json"))]
    if not results:
        parser.error("provide recordings or --summarize with existing outputs")
    write_summary(results, args.out, config)
    if args.summarize or len(results) > 1:
        contact_sheets(results, args.out)


if __name__ == "__main__":
    main()
