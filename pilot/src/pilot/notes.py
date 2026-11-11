"""Offline text intervals and mission summaries, using recording time throughout."""

from __future__ import annotations

import json
import re
from bisect import bisect_right
from pathlib import Path

from .scene import _similar

KINDS = ("objective", "help", "subtitle", "banner")


def consolidate(readings, gap=1.25):
    """Close on observed absence; tolerate irregular spacing of visible samples."""
    active = {}
    intervals = []
    for reading in readings:
        timestamp = float(reading["t"])
        scene = reading["text"]
        for kind in KINDS:
            text = (scene.get(kind) or "").strip()
            previous = active.get(kind)
            if previous and (
                timestamp - previous["last"] > gap or (text and not _similar(previous["text"], text))
            ):
                intervals.append(active.pop(kind))
                previous = None
            if not text:
                if previous:
                    intervals.append(active.pop(kind))
                continue
            if previous:
                previous["last"] = timestamp
            else:
                active[kind] = {
                    "kind": kind,
                    "text": text,
                    "first": timestamp,
                    "last": timestamp,
                }
    intervals.extend(active.values())
    return sorted(intervals, key=lambda item: (item["first"], item["kind"]))


def read_sections(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Missing sections.json: {path}; run P38 first.")
    data = json.loads(path.read_text())
    required = {"recording", "seconds", "sample_hz", "has_pad", "sections"}
    if not required <= data.keys():
        raise ValueError(f"Invalid P38 sections contract: {path}")
    for section in data["sections"]:
        if not {"start", "end", "kind", "wanted", "route", "human"} <= section.keys():
            raise ValueError(f"Invalid P38 section: {path}")
    return data


def ending(text):
    if any(
        _similar(text, phrase) for phrase in ("mission fehlgeschlagen", "fehlgeschlagen", "mission failed")
    ):
        return "failed"
    if re.search(r"\b(bestanden|geschafft|passed)\b", text, re.I):
        return "passed"
    if re.search(r"\b(gescheitert|fehlgeschlagen|failed)\b", text, re.I):
        return "failed"
    if re.search(r"\b(tot|gestorben|wasted|dead)\b", text, re.I):
        return "dead"
    return None


def observed_actions(pads, sections, start, end):
    """Integrate held human inputs, disambiguating triggers by section kind."""
    rows = sorted((row for row in pads if row.get("src") == "human"), key=lambda row: row["t"])
    if not rows or end <= start:
        return None
    index = max(0, bisect_right([row["t"] for row in rows], start) - 1)
    actions = {
        key: 0.0
        for key in (
            "driving",
            "walking",
            "running",
            "aiming",
            "firing",
            "looking",
            "map_input",
            "vehicle_input",
            "neutral",
        )
    }
    covered = 0.0
    for i in range(index, len(rows)):
        row = rows[i]
        if row["t"] >= end:
            break
        left = max(start, row["t"])
        right = min(end, rows[i + 1]["t"] if i + 1 < len(rows) else end)
        for section in sections:
            duration = min(right, section["end"]) - max(left, section["start"])
            if duration <= 0:
                continue
            kind = section["kind"]
            covered += duration
            moving = max(abs(value) for value in row.get("left", [0, 0])) > 0.4
            looking = max(abs(value) for value in row.get("right", [0, 0])) > 0.4
            l2, r2 = row.get("l2", 0), row.get("r2", 0)
            buttons = row.get("buttons", [])
            flags = {
                "driving": kind == "drive" and (moving or l2 > 0.5 or r2 > 0.5),
                "walking": kind in ("foot", "combat") and moving,
                "running": kind in ("foot", "combat") and moving and "cross" in row.get("buttons", []),
                "aiming": kind in ("foot", "combat") and l2 > 0.5,
                "firing": kind in ("foot", "combat") and r2 > 0.5,
                "looking": kind in ("foot", "combat", "drive") and looking,
                "map_input": "options" in buttons,
                "vehicle_input": kind in ("foot", "combat") and "triangle" in buttons,
                "neutral": not moving and not looking and not buttons and l2 <= 0.5 and r2 <= 0.5,
            }
            for action, active in flags.items():
                if active:
                    actions[action] += duration
    if not covered:
        return None
    return {
        "observed_seconds": round(covered, 3),
        "seconds": {key: round(value, 3) for key, value in actions.items()},
    }


def build_missions(intervals, sections, pads=()):
    objectives = sorted(
        (row for row in intervals if row["kind"] == "objective"),
        key=lambda row: row["first"],
    )
    banners = [row for row in intervals if row["kind"] == "banner" and ending(row["text"])]
    missions = []
    used_banners = set()
    current = None
    for index, objective in enumerate(objectives):
        start = objective["first"]
        next_start = objectives[index + 1]["first"] if index + 1 < len(objectives) else float("inf")
        silence = objective["last"] + 60
        limit = min(next_start, silence, sections["seconds"])
        banner = next(
            (row for row in sorted(banners, key=lambda x: x["first"]) if start <= row["first"] <= limit),
            None,
        )
        stop = banner["first"] if banner else limit
        if banner:
            used_banners.add(banner["first"])
        outcome = (
            ending(banner["text"])
            if banner
            else ("next objective" if next_start <= min(silence, sections["seconds"]) else "unknown")
        )
        overlapping = [row for row in sections["sections"] if row["start"] < stop and row["end"] > start]
        if current is None:
            current = {"start": start, "end": stop, "steps": []}
            missions.append(current)
        current["steps"].append(
            {
                "objective": objective["text"],
                "start": start,
                "end": stop,
                "last": objective["last"],
                "duration": round(objective["last"] - start, 3),
                "step_duration": round(stop - start, 3),
                "section_kinds": sorted({row["kind"] for row in overlapping}),
                "route": sorted({colour for row in overlapping for colour in row["route"]}),
                "blips": sorted({colour for row in overlapping for colour in row.get("blips", [])}),
                "blips_known": all("blips" in row for row in overlapping) and bool(overlapping),
                "wanted": max((row["wanted"] or 0 for row in overlapping), default=0),
                "human": observed_actions(pads, overlapping, start, stop) if sections["has_pad"] else None,
                "ending": outcome,
            }
        )
        current["end"] = stop
        current["ending"] = outcome
        if outcome != "next objective":
            current["end_reason"] = (
                "banner" if banner else "silence" if silence <= sections["seconds"] else "recording ended"
            )
            current = None
    for mission in missions:
        wording = " Then ".join(step["objective"] for step in mission["steps"])
        mission["notes"] = ("The game asks: " + wording + ". Outcome: " + mission["ending"] + ".")[:600]
    return {
        "recording": sections["recording"],
        "missions": missions,
        "unassigned_endings": [row for row in banners if row["first"] not in used_banners],
    }
