"""Compare driving styles on P55's recorded ticks using its existing motion caches."""

import json
from dataclasses import replace
from pathlib import Path

import replay
from pilot.cli import drive_config
from pilot.contract import Reading
from pilot.drive import Driver


def main():
    results = []
    for suffix, windows in replay.WINDOWS.items():
        folder = replay.ROOT / f"20261112-{suffix}"
        play = replay.lines(folder / "play.jsonl")
        motion = replay.motion_for(folder, play)
        for start, end in windows:
            drivers = {
                style: Driver(drive_config([f"style={style}"]))
                for style in ("careful", "bold")
            }
            ticks = unreadable = arrival_braking = 0
            violations = []
            distances = []
            stationary = flagged_stationary = brake_stationary = 0.0
            previous = None
            for row in play:
                if not start - 0.0005 <= row["t"] <= end + 0.0005:
                    continue
                if (row.get("skill") or {}).get("name") != "drive_route":
                    continue
                raw = row.get("reading")
                if not raw or not row.get("fresh"):
                    continue
                if raw.get("gps_distance") is not None:
                    distances.append(raw["gps_distance"])
                if previous is not None:
                    old_time, was_still, was_flagged, was_braking = previous
                    elapsed = min(0.5, max(0, row["t"] - old_time))
                    if was_still:
                        stationary += elapsed
                        flagged_stationary += elapsed * was_flagged
                        brake_stationary += elapsed * was_braking
                previous = (
                    row["t"],
                    motion.get(row["frame_id"]) is False,
                    raw.get("corrupt") is True,
                    (row.get("sent_pad") or {}).get("l2", 0) > 0,
                )
                reading = replace(
                    Reading(
                        **{
                            k: v
                            for k, v in raw.items()
                            if k in Reading.__dataclass_fields__
                        }
                    ),
                    blips=(),
                )
                commands = {
                    style: driver.step(
                        reading,
                        row["t"],
                        motion.get(row["frame_id"]),
                        speed=reading.gps_speed,
                    )
                    for style, driver in drivers.items()
                }
                ticks += 1
                careful, bold = commands["careful"], commands["bold"]
                clean_absence = (
                    reading.route == "none"
                    and reading.corrupt is False
                    and reading.confidence >= drivers["careful"].config.confidence_min
                )
                neutral_coast = (
                    careful.state == "coast"
                    and not careful.throttle
                    and not careful.brake
                )
                # A legible map with no route is arrival evidence, not an unreadable
                # picture. Retain earlier braking as a separate audited difference.
                arrival_braking += bool(neutral_coast and clean_absence and bold.brake)
                abstained = careful.state in ("idle", "map-unreadable") or (
                    neutral_coast and not clean_absence
                )
                unreadable += abstained
                if abstained and (bold.throttle or bold.brake):
                    violations.append(
                        {"t": row["t"], "careful": careful.state, "bold": bold.state}
                    )
            results.append(
                {
                    "session": folder.name,
                    "start": start,
                    "end": end,
                    "ticks": ticks,
                    "unreadable_ticks": unreadable,
                    "clean_absence_braking_ticks": arrival_braking,
                    "recorded_net_route_progress": distances[0] - distances[-1]
                    if distances
                    else None,
                    "recorded_seconds": end - start,
                    "map_stationary_seconds": stationary,
                    "flagged_while_map_stationary_seconds": flagged_stationary,
                    "braking_while_map_stationary_seconds": brake_stationary,
                    "violations": violations,
                }
            )
    output = {"evidence": "recorded replay", "windows": results}
    Path(__file__).with_name("p73-replay.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "windows": len(results),
                "ticks": sum(r["ticks"] for r in results),
                "unreadable_ticks": sum(r["unreadable_ticks"] for r in results),
                "clean_absence_braking_ticks": sum(
                    r["clean_absence_braking_ticks"] for r in results
                ),
                "violations": sum(len(r["violations"]) for r in results),
            }
        )
    )


if __name__ == "__main__":
    main()
