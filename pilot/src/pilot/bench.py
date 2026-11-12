"""Offline capability evidence, an append-only bench, and an injectable runner.

Nothing connects to the console on import. Only bridge() and pilot() can do so.
Historical sessions are inputs, never output directories.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any
from urllib.request import urlopen

DEFAULT_LEDGER = Path("/Users/kerim/recordings/pilot/bench.jsonl")
CAUSES = ("see", "decide", "act", "proof", "world", "tech", "unclear")


@dataclass(frozen=True)
class Capability:
    id: str
    group: str
    title: str
    german: str
    start: tuple[str, ...]
    plan: tuple[dict, ...]
    seconds: int
    proof: str
    missing: str = ""
    built: bool = True
    mark: int = 9
    harvested: bool = False


def step(name: str, **args: Any) -> dict:
    return {"name": name, "args": args}


CATALOGUE = {
    c.id: c
    for c in (
        Capability(
            "foot.view",
            "foot",
            "Set the view",
            "Sicht einstellen",
            ("foot",),
            (step("level_camera"),),
            15,
            "Final independent camera pose and follow distance.",
            "Camera pose/distance missing: perception reader and cli play logger.",
        ),
        Capability(
            "foot.walk",
            "foot",
            "Walk",
            "Laufen",
            ("foot",),
            (step("walk_road", duration=20),),
            28,
            "Independent moving observations over 20 seconds; >50% moving, no 3-second hold.",
            "Independent moving field missing: flow reader and conductor play logger.",
        ),
        Capability(
            "foot.walk_to",
            "foot",
            "Walk to a point",
            "Zu einem Punkt laufen",
            ("foot", "yellow_target"),
            (step("walk_to", duration=10, color="yellow", sprint=False),),
            18,
            "Independent distance to the selected yellow blip <=10m.",
            "Blip distance in metres missing: minimap reader and cli play logger.",
        ),
        Capability(
            "foot.roadside",
            "foot",
            "Stay roadside",
            "Am Straßenrand bleiben",
            ("foot",),
            (),
            28,
            "Every sampled foot position is outside the carriageway.",
            "Roadside position missing: road reader and cli play logger; no roadside skill.",
            built=False,
        ),
        Capability(
            "foot.enter",
            "foot",
            "Enter a vehicle",
            "Einsteigen",
            ("foot",),
            (step("enter_vehicle", duration=20, kind="any"),),
            28,
            "Stable vehicle mode within 20s; target was stationary and unoccupied.",
            "Target speed and driver occupancy missing: vehicle detector and cli/head logger.",
        ),
        Capability(
            "car.leave",
            "car",
            "Leave a vehicle",
            "Aussteigen",
            ("vehicle",),
            (step("press", button="triangle", duration=1),),
            8,
            "Final stable flat minimap, initially tilted; independent of press result.",
        ),
        Capability(
            "car.follow",
            "car",
            "Follow the route",
            "Der Route folgen",
            ("vehicle", "route"),
            (step("drive_route", duration=30),),
            38,
            "GPS distance drops >=100m within 30s; speed never held for 5s.",
        ),
        Capability(
            "car.arrive",
            "car",
            "Arrive",
            "Ankommen",
            ("vehicle", "route"),
            (step("drive_route", duration=60),),
            66,
            "Final GPS <=30m, speed stopped, arrival sentence in head response.",
        ),
        Capability(
            "car.free",
            "car",
            "Get unstuck",
            "Sich befreien",
            ("vehicle",),
            (),
            10,
            "Held vehicle moves again within 10s.",
            "Recovery attempt identity/start missing: driver and cli play logger.",
            harvested=True,
        ),
        Capability(
            "car.turn",
            "car",
            "Turn around",
            "Wenden",
            ("vehicle", "route", "behind"),
            (),
            15,
            "Route-relative heading aligned within 15s.",
            "No standalone turn skill; route-relative heading missing from play logger.",
            built=False,
        ),
        Capability(
            "map.open_close",
            "map",
            "Open and close the map",
            "Karte auf und zu",
            ("game",),
            (
                step("press", button="options", duration=0.2),
                step("wait", duration=2),
                step("press", button="circle", duration=0.2),
            ),
            8,
            "Independent HUD screen visits map and returns to game.",
        ),
        Capability(
            "map.place",
            "map",
            "Choose a listed place",
            "Ort aus der Liste wählen",
            ("game",),
            (step("set_waypoint", kind="shop"),),
            52,
            "Real legend entry selected and purple route persists in final minimap.",
            "Selected legend entry identity/type missing: legend reader and conductor head/play logger.",
        ),
        Capability(
            "map.mission",
            "map",
            "Choose a mission",
            "Missionsziel wählen",
            ("game",),
            (step("set_waypoint", kind="mission"),),
            52,
            "Mission legend entry and resulting route.",
            (
                "Independent selected legend identity/type missing: legend reader and conductor "
                "head/play logger."
            ),
        ),
        Capability(
            "goal.keep",
            "goal",
            "Keep a goal",
            "Ein Ziel halten",
            ("game",),
            (),
            60,
            "Stable goal id through completion or listed interrupt, no plan replacement.",
            "Goal lifecycle/id/end condition missing from head/play logger; no fixed goal plan.",
        ),
        Capability(
            "incident.menu",
            "incident",
            "Close an unexpected menu",
            "Fremdes Menü schließen",
            (),
            (),
            5,
            "HUD menu onset to game <=5s.",
            "Recovery handler result/attempt id missing: conductor play/head logger.",
            harvested=True,
        ),
        Capability(
            "incident.down",
            "incident",
            "Resume after death or arrest",
            "Nach Tod oder Verhaftung weiter",
            (),
            (),
            30,
            "Death/arrest, respawn, then playing within 30s.",
            "Explicit respawn timestamp and resumed control missing: HUD reader and cli logger.",
            harvested=True,
        ),
        Capability(
            "incident.wanted",
            "incident",
            "Lose wanted stars",
            "Sterne loswerden",
            (),
            (),
            180,
            "HUD wanted rises above zero and reaches zero within 180s.",
            "Recovery handler result/attempt id missing: conductor play/head logger.",
            harvested=True,
        ),
        Capability(
            "chain.basic",
            "chain",
            "Basic chain",
            "Grundkette",
            ("foot",),
            (
                step("enter_vehicle", duration=20, kind="any"),
                step("set_waypoint", kind="shop"),
                step("drive_route", duration=60),
                step("press", button="triangle", duration=1),
            ),
            150,
            "Ordered entry, real place route, stopped arrival, exit in one session.",
            "Real legend selection and arrival declaration missing; depends on map.place proof.",
        ),
    )
}

# Exact terminal reasons, plus documented dynamic prefixes below. Success reasons
# have no cause unless evidence contradicts them; do not call a timeout a cause.
REASONS: dict[str, str | None] = {
    "interrupted": "decide",
    "replaced": "decide",
    "clock-reversed": "tech",
    "clock-invalid": "tech",
    "invalid observation": "tech",
    "invalid observation time": "tech",
    "invalid-observation-time": "tech",
    "time-limit": None,
    "route-gone": None,
    "failed-recovery": "act",
    "arrived": None,
    "blocked": "act",
    "stuck": "act",
    "no-frame": "tech",
    "map-unreadable": "see",
    "minimap-unreadable": "see",
    "entered vehicle": None,
    "already in a vehicle": "decide",
    "no detections delivered at all": "tech",
    "vehicle out of reach": "act",
    "nothing found": "see",
    "detections lost after entry press": "see",
    "vehicle drove away or was lost": None,
    "door locked or blocked": "act",
    "entry press had no effect": "act",
    "could not reach it": "act",
    "not on foot": "decide",
    "levelled": None,
    "combat-timeout": None,
    "wrong-screen-while-exiting; gameplay observed": "decide",
    "waypoint set; route on the minimap": None,
    "waypoint set; no route yet": None,
    "gameplay returned without a waypoint": "act",
    "picture-unchanged-after-input; check the video feed": "tech",
    "start-screen-unverified; start from visible gameplay": "decide",
    "map-picture-missing-or-damaged": "see",
    "interactive-map-or-cursor-unverified": "see",
    "player-marker-unreadable; centre the map manually": "see",
    "target-not-uniquely-trackable; inspect the map manually": "see",
    "target-tracking-unverified; inspect the selected marker": "see",
    "waypoint-not-visible-after-cross": "act",
    "existing-waypoint-at-target; avoid toggling it off": "decide",
    "cursor-did-not-approach-target; check stick direction and map scale": "act",
    "cursor-move-limit": "act",
    "map-texture-unverified; need a clean detailed map": "see",
    "map-shift-unverified; damaged or ambiguous map pair": "see",
    "map-unmoved-after-alternate; check map edge or video feed": "act",
    "map-shift-wrong-direction; check stick mapping": "act",
    "sea-or-distance-unverified-after-inland-look": "see",
    "map-move-limit": "act",
    "death_or_arrest": "world",
    "objective": "world",
    "low_health": "world",
    "stars": "world",
    "limit": None,
    "invalid observation; check detector and HUD readings": "tech",
    "punch time limit reached; move closer or choose another person": None,
    "minimap unreadable; restore an on-foot game view": "see",
    "player is in a vehicle; exit before punching": "decide",
    "gameplay interrupted; restore the game screen": "world",
    "target person lost; restore visibility before retrying": "see",
    "no person found; face a visible person before retrying": "see",
    "target person remained on the ground": None,
    "blip-gone": "see",
    "blip-bearing-undefined": "see",
    "aligned": None,
    "health-depleted": "world",
    "no-red-blips": None,
    "health-still-low": "world",
    "melee-target-too-far": "act",
    "health below 30%; retreat and recover": "world",
    "person detector unavailable or stale; check detector delivery": "tech",
    "person already on the ground; face a standing person": "decide",
    "selection-changed-before-waypoint": "decide",
    "waypoint-unproven-on-a-later-page": "see",
    "legend-selection-did-not-move": "act",
    "legend-selection-skips-the-place": "act",
    "return-unverified": "see",
}

REASON_PREFIXES = {
    "skill-error:": "tech",
    "wrong-screen:": "decide",
    "map-check-failed:": "see",
    "no-visible-": "see",
    "legend-selection-skips-the-place:": "act",
    "place-not-in-legend:": "see",
    "nothing found; road search unavailable:": "see",
    "goal_": "decide",
    "waypoint set:": None,
    "time-limit:": None,
}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open() as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{number}: invalid JSON") from exc
    return rows


def load_session(folder: Path) -> dict:
    return {name: read_jsonl(folder / f"{name}.jsonl") for name in ("play", "head", "judge", "frames")}


def requests(log: dict) -> list[dict]:
    rows = [row for row in log["head"] if row.get("request")]
    if not rows:
        return []
    first = min(row.get("t", 0) for row in rows)
    play_start = log["play"][0]["t"] if log["play"] else 0
    # Head records use absolute monotonic time; play records are relative.
    offset = first - play_start
    result = []
    seen = set()
    for row in rows:
        key = row.get("id", (row.get("t"), row.get("type")))
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(row["request"], t=row.get("t", 0) - offset))
    return result


def mode(row: dict) -> str | None:
    reading = row.get("reading") or row.get("minimap") or {}
    if reading.get("corrupt"):
        return None
    return {"flat": "foot", "tilted": "vehicle"}.get(reading.get("minimap"))


def state(log: dict, *, end: bool = False) -> dict:
    play = log["play"]
    if not play:
        return {"known": False}
    anchor = play[-1 if end else 0]["t"]
    rows = [r for r in play if abs(r["t"] - anchor) <= 1]
    modes = [mode(r) for r in rows]
    known = [m for m in modes if m]
    dominant = Counter(known).most_common(1)
    current_mode = dominant[0][0] if dominant and dominant[0][1] / len(rows) >= 0.8 else None
    req = [r for r in requests(log) if r["t"] <= anchor + 0.1 and (end or abs(r["t"] - anchor) <= 1)]
    reading = rows[-1 if end else 0].get("reading") or {}
    hud = next((r.get("hud") for r in reversed(req) if r.get("hud")), {})
    objective = next((r.get("objective") for r in reversed(req) if r.get("objective")), "")
    return {
        "known": current_mode is not None,
        "mode": current_mode,
        "route": reading.get("route") in ("yellow", "purple"),
        "target": bool(reading.get("blips")) or reading.get("route") in ("yellow", "purple"),
        "yellow_target": any(b.get("color") == "yellow" for b in reading.get("blips", [])),
        "game": hud.get("screen") == "game" if hud else None,
        "mission": bool(str(objective).strip()) or reading.get("route") == "yellow",
        "mission_known": bool(req) and "objective" in req[-1] and anchor - req[-1]["t"] <= 5,
        "behind": None,
    }


def meets(current: dict, needed: tuple[str, ...]) -> bool:
    return all(
        current.get("mode") == item if item in ("foot", "vehicle") else current.get(item) is True
        for item in needed
    )


def terminal(log: dict, cap: Capability) -> tuple[bool | None, str]:
    names = {s["name"] for s in cap.plan}
    candidates = []
    for row in log["play"]:
        skill = row.get("skill") or {}
        if skill.get("name") in names and skill.get("status") in ("done", "failed"):
            candidates.append((row["t"], skill))
    for req in requests(log):
        skills = [req.get("last_skill") or {}]
        skills += [e.get("skill") or {} for e in req.get("events", [])]
        for skill in skills:
            if skill.get("name") in names and skill.get("status") in ("done", "failed"):
                candidates.append((req["t"], skill))
    if not candidates:
        return None, "terminal skill result missing"
    _, result = max(candidates, key=lambda pair: pair[0])
    return result["status"] == "done", result.get("reason") or "done"


def hold_seconds(samples: list[tuple[float, bool]], end: float) -> float:
    longest = 0.0
    start = None
    for t, moving in samples:
        if not moving and start is None:
            start = t
        if moving and start is not None:
            longest = max(longest, t - start)
            start = None
    return max(longest, end - start if start is not None else 0.0)


def prove(log: dict, capability: str) -> dict:
    cap = CATALOGUE[capability]
    rows = log["play"]
    numbers: dict = {}
    result = None
    missing = cap.missing
    if not rows:
        return {"ok": None, "numbers": {}, "missing": "play.jsonl: cli play logger"}
    end_state = state(log, end=True)
    numbers["end_mode"] = end_state.get("mode")
    if capability == "car.leave":
        result = end_state.get("mode") == "foot" if end_state.get("known") else None
    elif capability == "foot.enter":
        entered = next((r["t"] for r in rows if mode(r) == "vehicle"), None)
        numbers["entered_seconds"] = entered
        if entered is None or entered > 20 or end_state.get("mode") != "vehicle":
            result = False
    elif capability == "foot.walk":
        # Only a measured movement field qualifies. Skill reason motion=going
        # and stick commands are deliberately not independent evidence.
        samples = [(r["t"], r["moving"]) for r in rows if isinstance(r.get("moving"), bool)]
        if not samples:
            samples = [(r["t"], r["moving"]) for r in requests(log) if isinstance(r.get("moving"), bool)]
        samples = [(t, m) for t, m in samples if t <= 20.5]
        if len(samples) >= 2 and samples[-1][0] - samples[0][0] >= 19:
            duration = samples[-1][0] - samples[0][0]
            fraction = sum((b[0] - a[0]) for a, b in pairwise(samples) if a[1]) / duration
            hold = hold_seconds(samples, samples[-1][0])
            gap = max(b[0] - a[0] for a, b in pairwise(samples))
            numbers.update(
                moving_fraction=round(fraction, 4),
                longest_hold=round(hold, 3),
                observed_seconds=duration,
                max_sample_gap=gap,
            )
            result = fraction > 0.5 and hold < 3 if gap < 3 else None
        if result is None:
            missing = "Independent moving field at <3s intervals for 20s: flow reader and cli play logger."
    elif capability == "foot.walk_to":
        reading = rows[-1].get("reading") or {}
        distance = reading.get("target_distance_metres")
        if isinstance(distance, (int, float)) and reading.get("target_color") == "yellow":
            numbers["target_metres"] = distance
            result = distance <= 10
    elif capability in ("car.follow", "car.arrive"):
        gps = [
            (r["t"], r.get("reading", {}).get("gps_distance"), r.get("reading", {}).get("gps_speed"))
            for r in rows
        ]
        gps = [(t, d, s) for t, d, s in gps if isinstance(d, (int, float))]
        if gps:
            numbers.update(first_metres=gps[0][1], final_metres=gps[-1][1], final_speed=gps[-1][2])
            if capability == "car.arrive":
                said = any(
                    str(r.get("sentence", "")).strip().casefold().rstrip(".!")
                    in {"arrived", "arrived at destination", "arrived at the destination"}
                    for r in log["head"]
                )
                numbers["arrival_declared"] = said
                if gps[-1][2] is not None:
                    result = gps[-1][1] <= 30 and gps[-1][2] <= 1 and said
            else:
                window = [p for p in gps if p[0] <= gps[0][0] + 30]
                progress = window[0][1] - min(p[1] for p in window)
                speeds = [(t, s > 1) for t, _, s in window if s is not None]
                numbers["progress_metres"] = progress
                if len(speeds) >= 2:
                    hold = hold_seconds(speeds, window[-1][0])
                    gap = max(b[0] - a[0] for a, b in pairwise(speeds))
                    numbers.update(longest_hold=hold, max_sample_gap=gap)
                    result = progress >= 100 and hold < 5 if gap < 5 else None
        if result is None:
            missing = (
                "GPS distance/speed in metres at sufficient cadence: minimap/OCR reader and cli play logger."
            )
    elif capability in ("map.place", "map.mission"):
        final = [r for r in rows if r["t"] >= rows[-1]["t"] - 1]
        routes = [r.get("reading", {}).get("route") for r in final]
        numbers.update(
            final_route_samples=len(routes),
            final_route_fraction=sum(r == "purple" for r in routes) / len(routes),
        )
        if all(r == "none" for r in routes):
            result = False
    elif capability == "map.open_close":
        screens = [r.get("hud", {}).get("screen") for r in requests(log)]
        numbers["screens"] = screens
        if screens:
            hud_requests = requests(log)
            recent = rows[-1]["t"] - hud_requests[-1]["t"] <= 1
            gap = max((b["t"] - a["t"] for a, b in pairwise(hud_requests)), default=float("inf"))
            if recent and ("map" in screens or gap <= 1):
                result = "map" in screens and screens[-1] == "game"
            else:
                missing = "Continuous HUD screen transitions/final screen: conductor head/play logger."
        else:
            missing = "HUD screen transitions: HUD reader and head logger."
    return {
        "ok": result,
        "numbers": numbers,
        "missing": missing if result is None else "",
        "limitation": cap.missing,
    }


def cause(reason: str, log: dict) -> str:
    stale = [(r["t"], r.get("fresh") is not False) for r in log["play"]]
    if stale and hold_seconds(stale, stale[-1][0]) >= 2:
        return "tech"
    reqs = requests(log)
    huds = [r.get("hud") or {} for r in reqs]
    health = [h["health"] for h in huds if isinstance(h.get("health"), (int, float))]
    if any(
        h.get("screen") in ("wasted", "busted", "failed") or (h.get("wanted") or 0) > 0 for h in huds
    ) or any(b < a - 0.02 for a, b in pairwise(health)):
        return "world"
    if any(
        e.get("kind") in ("death", "arrest", "wasted", "busted", "failure", "mission_ended")
        for r in reqs
        for e in r.get("events", [])
    ):
        return "world"
    if any((r.get("status") or 200) >= 400 for r in log["play"]):
        return "tech"
    if reason.startswith("nothing found; road search unavailable:"):
        return "see"
    if reason.startswith("goal_") or "plan replaced" in reason:
        return "decide"
    mapped = REASONS.get(reason)
    if mapped:
        return mapped
    for known, mapped in sorted(REASONS.items(), key=lambda item: -len(item[0])):
        if mapped and reason.startswith(known + ";"):
            return mapped
    stem = reason.split(";", 1)[0]
    if REASONS.get(stem):
        return REASONS[stem]
    for prefix, mapped in REASON_PREFIXES.items():
        if reason.startswith(prefix) and mapped:
            return mapped
    if reason.startswith("time-limit:"):
        detail = reason.split(":", 1)[1].split(";", 1)[0].strip()
        matches = [value for key, value in REASONS.items() if key.split(";", 1)[0] == detail and value]
        if matches:
            return matches[0]
    if "time" in reason or reason == "vehicle drove away or was lost":
        objects = [
            o
            for r in reqs
            for o in r.get("objects", [])
            if o.get("kind") in {"car", "truck", "bus", "motorcycle"}
        ]
        entry = any((r.get("last_skill") or {}).get("name") == "enter_vehicle" for r in reqs)
        if entry and reqs and all("objects" in r for r in reqs) and not objects:
            return "see"
        distances = [r.get("reading", {}).get("gps_distance") for r in log["play"]]
        distances = [d for d in distances if isinstance(d, (int, float))]
        if len(distances) > 1 and min(distances) < distances[0] - 1:
            return "act"
    return "unclear"


def outcome(skill: bool | None, proof: bool | None) -> tuple[str, str | None]:
    if skill is None or proof is None:
        return "not_counted", None
    if skill and proof:
        return "ok", None
    return "failed", "proof" if skill != proof else None


def version() -> dict:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()

    try:
        return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": "unknown", "dirty": None}


def judge(folder: Path, capability: str, *, code: dict | None = None) -> dict:
    cap = CATALOGUE[capability]
    log = load_session(folder)
    start = state(log)
    proof = prove(log, capability)
    skill, reason = terminal(log, cap)
    status, why = outcome(skill, proof["ok"])
    valid_start = meets(start, cap.start)
    exclusion = ""
    if not cap.built:
        status, why, exclusion = "not_counted", None, "not built"
    elif not valid_start:
        status, why, exclusion = "not_counted", "decide", "start state not established in first second"
    elif skill is None or proof["ok"] is None:
        exclusion = proof["missing"] or "terminal skill result missing: cli/head logger"
    if status == "failed" and why is None:
        why = cause(reason, log)
    rows = log["play"]
    stamp = datetime.now(UTC).isoformat()
    meta_path = folder / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return {
        "capability": capability,
        "time": meta.get("started", stamp),
        "judged_at": stamp,
        **(code or {"commit": "unknown", "dirty": None}),
        "judged_with": version(),
        "session": str(folder.resolve()),
        "start_state": {"held": valid_start, "observed": start},
        "outcome": status,
        "cause": why,
        "skill_reason": reason,
        "skill_ok": skill,
        "seconds": round(rows[-1]["t"] - rows[0]["t"], 3) if rows else 0,
        "proof": proof,
        "exclusion": exclusion,
    }


def append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def marks_path(ledger: Path) -> Path:
    return ledger.with_name(ledger.stem + ".marks.jsonl")


def apply_marks(rows: list[dict], marks: list[dict]) -> list[dict]:
    # Rejudging appends a revision; rates count each attempt exactly once.
    latest = {}
    for row in rows:
        latest[(row["session"], row["capability"], row.get("event_start"))] = row
    rows = list(latest.values())
    result = []
    for original in rows:
        row = dict(original)
        for mark in marks:
            if mark["session"] == row["session"] and (
                not mark.get("capability") or mark["capability"] == row["capability"]
            ):
                row.update(outcome=mark["outcome"], cause=mark["cause"], marked=True, mark_note=mark["note"])
        result.append(row)
    return result


def import_basics(source: Path, ledger: Path) -> list[dict]:
    mapping = {
        "leave": "car.leave",
        "walk": "foot.walk",
        "enter": "foot.enter",
        "place": "map.place",
        "waypoint": "map.place",
        "drive": "car.follow",
    }
    seen = {(r["session"], r["capability"]) for r in read_jsonl(ledger)}
    added = []
    for line in source.read_text().splitlines():
        fields = line.split("\t")
        if len(fields) < 3 or fields[1] not in mapping:
            continue
        folder = Path(fields[2])
        if not folder.is_absolute():
            folder = source.parent / folder
        cap = mapping[fields[1]]
        key = (str(folder.resolve()), cap)
        if key in seen:
            continue
        row = judge(folder, cap)
        row["source"] = {"file": str(source), "cycle": fields[0], "step": fields[1]}
        append(ledger, row)
        added.append(row)
        seen.add(key)
    return added


def harvest(folder: Path, *, code: dict | None = None) -> list[dict]:
    """Discover incident edges once, retaining unmeasurable attempts explicitly."""
    log = load_session(folder)
    reqs = requests(log)
    events: list[tuple[str, float, int]] = []
    previous = {}
    for index, req in enumerate(reqs):
        hud = req.get("hud") or {}
        screen = hud.get("screen")
        if screen in ("pause", "map", "menu") and previous.get("screen") == "game":
            # A map intentionally opened by set_waypoint is not an incident.
            if (req.get("last_skill") or {}).get("name") != "set_waypoint":
                events.append(("incident.menu", req["t"], index))
        if screen in ("wasted", "busted") and previous.get("screen") not in ("wasted", "busted"):
            events.append(("incident.down", req["t"], index))
        if (hud.get("wanted") or 0) > 0 and previous.get("wanted") == 0:
            events.append(("incident.wanted", req["t"], index))
        previous = hud
    held_since = None
    harvested_hold = False
    for row in log["play"]:
        if mode(row) == "vehicle" and row.get("moving") is False:
            if held_since is None:
                held_since = row["t"]
            if row["t"] - held_since >= 3 and not harvested_hold:
                events.append(("car.free", held_since, -1))
                harvested_hold = True
        else:
            held_since, harvested_hold = None, False
    records = []
    for cap, onset, index in events:
        deadline = onset + CATALOGUE[cap].seconds
        tail = [r for r in reqs[index + 1 :] if r["t"] <= deadline] if index >= 0 else []
        resolved = None
        if cap == "incident.menu":
            resolved = next((r["t"] for r in tail if (r.get("hud") or {}).get("screen") == "game"), None)
        elif cap == "incident.wanted":
            resolved = next((r["t"] for r in tail if (r.get("hud") or {}).get("wanted") == 0), None)
        elif cap == "car.free":
            resolved = next(
                (r["t"] for r in log["play"] if onset < r["t"] <= deadline and r.get("moving") is True), None
            )
        observed_end = log["play"][-1]["t"] if log["play"] else onset
        proof = (
            True
            if resolved is not None
            else False
            if observed_end >= deadline and cap != "incident.down"
            else None
        )
        # Existing logs lack a recovery-handler result tied to this event. Do
        # not fabricate skill success from the same HUD transition as the proof.
        records.append(
            {
                "capability": cap,
                "time": datetime.now(UTC).isoformat(),
                **(code or {"commit": "unknown", "dirty": None}),
                "session": str(folder.resolve()),
                "event_start": onset,
                "start_state": {"held": True, "observed": {"harvested": True}},
                "outcome": "not_counted",
                "cause": None,
                "skill_reason": "recovery handler terminal result missing",
                "skill_ok": None,
                "seconds": round((resolved or min(deadline, observed_end)) - onset, 3),
                "proof": {
                    "ok": proof,
                    "numbers": {"onset": onset, "resolved": resolved},
                    "missing": CATALOGUE[cap].missing,
                },
                "exclusion": "Recovery handler result/attempt id missing: conductor play/head logger.",
            }
        )
    return records


def bridge() -> dict:
    """The sole bridge boundary. Never called by offline commands or tests."""
    with urlopen("http://127.0.0.1:9395/status", timeout=2) as response:
        return json.load(response)


def pilot(
    action: str,
    *,
    handle: Any = None,
    plan: tuple[dict, ...] = (),
    seconds: int = 0,
    folder: Path | None = None,
) -> Any:
    """The sole pilot boundary; start/poll/stop are replaced as one test seam."""
    if action == "start":
        assert folder is not None
        folder.mkdir(parents=True, exist_ok=False)
        args = [
            sys.executable,
            "-m",
            "pilot.cli",
            "play",
            "--head",
            "scripted",
            "--seconds",
            str(seconds),
            "--no-level",
            "--record-dir",
            str(folder),
            "--plan",
            json.dumps(plan),
        ]
        for _ in range(4):
            args += ["--plan", json.dumps([step("wait", duration=120)])]
        stream = (folder / "bench-process.log").open("w")
        try:
            process = subprocess.Popen(args, stdout=stream, stderr=subprocess.STDOUT)
        finally:
            stream.close()
        return process
    if action == "poll":
        return handle.poll()
    if action == "stop":
        handle.terminate()
        try:
            handle.wait(timeout=3)
        except subprocess.TimeoutExpired:
            handle.kill()
            handle.wait(timeout=3)
        return handle.returncode
    raise ValueError(f"Unknown pilot action: {action}")


class BenchStoppedError(RuntimeError):
    pass


def run(
    capabilities: list[str], tries: int, ledger: Path, *, allow_mission: bool = False, pause=time.sleep
) -> list[dict]:
    if tries < 1:
        raise ValueError("tries must be positive")
    for name in capabilities:
        cap = CATALOGUE[name]
        if not cap.built or not cap.plan or cap.harvested:
            raise ValueError(
                f"{name}: no runnable standalone plan; {cap.missing or 'harvested from other sessions'}"
            )
    results = []
    current: dict = {"known": False}
    streak: Counter = Counter()
    serial = 0
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")

    def execute(cap: Capability | None) -> tuple[Path, str | None]:
        nonlocal serial
        status = bridge()
        if status.get("human_input") is True:
            raise BenchStoppedError("Controller input: no try started.")
        if (
            status.get("session_up") is not True
            or status.get("recording") is not False
            or status.get("human_input") is not False
        ):
            raise BenchStoppedError(
                "Bridge must explicitly report session_up, no human input and no recording."
            )
        serial += 1
        folder = ledger.parent / "sessions" / f"{run_id}-{serial:04d}"
        handle = pilot(
            "start",
            plan=cap.plan if cap else (step("wait", duration=2),),
            seconds=cap.seconds if cap else 3,
            folder=folder,
        )
        interruption = None
        try:
            deadline = time.monotonic() + (cap.seconds if cap else 3) + 30
            while (exit_code := pilot("poll", handle=handle)) is None:
                status = bridge()
                if status.get("human_input") is True:
                    interruption = "human input"
                    pilot("stop", handle=handle)
                    break
                if status.get("session_up") is not True:
                    interruption = "bridge session lost"
                    pilot("stop", handle=handle)
                    break
                if time.monotonic() > deadline:
                    interruption = "pilot process timeout"
                    pilot("stop", handle=handle)
                    break
                pause(0.25)
        except OSError as exc:
            pilot("stop", handle=handle)
            interruption = f"bridge or pilot error: {type(exc).__name__}"
        except BaseException:
            pilot("stop", handle=handle)
            raise
        if interruption is None and exit_code not in (None, 0):
            interruption = f"pilot exited with status {exit_code}"
        # --record-dir is a parent; the recorder creates its own session child.
        # Fake pilots may write directly to the supplied root.
        sessions = sorted(folder.glob("*/play.jsonl"))
        if len(sessions) == 1:
            folder = sessions[0].parent
        elif len(sessions) > 1:
            raise BenchStoppedError(f"Multiple recording sessions under {folder}; cannot identify this try.")
        return folder, interruption

    def mission_guard() -> None:
        nonlocal current
        if not allow_mission and not current.get("mission_known"):
            observed, interrupted = execute(None)
            if interrupted:
                raise BenchStoppedError(f"State probe stopped: {interrupted}")
            current = state(load_session(observed), end=True)
        if not allow_mission:
            if current.get("mission"):
                raise BenchStoppedError(
                    "Mission guard: objective text or yellow route is active; --allow-mission lifts it."
                )
            if not current.get("mission_known"):
                raise BenchStoppedError(
                    "Mission guard: objective reading missing from head log; --allow-mission lifts it."
                )

    def trial(name: str) -> None:
        nonlocal current
        mission_guard()
        trial_code = version()
        folder, interruption = execute(CATALOGUE[name])
        row = judge(folder, name, code=trial_code)
        if interruption:
            row.update(
                outcome="not_counted" if interruption == "human input" else "failed",
                cause="decide" if interruption == "human input" else "tech",
                exclusion=interruption,
                skill_reason=interruption,
            )
        append(ledger, row)
        results.append(row)
        for incident in harvest(folder, code=trial_code):
            append(ledger, incident)
            results.append(incident)
        current = state(load_session(folder), end=True)
        streak[name] = streak[name] + 1 if row["outcome"] == "failed" and row["cause"] == "tech" else 0
        if interruption == "human input":
            raise BenchStoppedError("Controller input: stopped the pilot and excluded the try.")
        if streak[name] >= 3:
            raise BenchStoppedError(f"{name}: three consecutive tech failures; loop stopped.")

    def prepare(name: str, visiting: tuple[str, ...] = ()) -> None:
        nonlocal current
        if name in visiting:
            raise BenchStoppedError(f"Cannot establish start state for {name}.")
        for needed in CATALOGUE[name].start:
            if meets(current, (needed,)):
                continue
            producer = {
                "foot": "car.leave",
                "vehicle": "foot.enter",
                "route": "map.place",
            }.get(needed)
            if not producer:
                raise BenchStoppedError(f"{name}: missing start state {needed}; no safe producer.")
            prepare(producer, (*visiting, name))
            trial(producer)
            if not meets(current, (needed,)):
                raise BenchStoppedError(f"{producer} did not establish {needed} for {name}.")

    folder, interrupted = execute(None)
    if interrupted:
        raise BenchStoppedError(f"State probe stopped: {interrupted}")
    current = state(load_session(folder), end=True)
    for _ in range(tries):
        for name in capabilities:
            mission_guard()
            prepare(name)
            trial(name)
    return results


def board_data(rows: list[dict]) -> dict:
    capabilities = []
    ranking: Counter = Counter()
    by_commit: dict = defaultdict(list)
    failures = [r for r in rows if r["outcome"] == "failed"]
    for cap in CATALOGUE.values():
        selected = [r for r in rows if r["capability"] == cap.id]
        counted = [r for r in selected if r["outcome"] != "not_counted"]
        recent = counted[-10:]
        failed = [r for r in counted if r["outcome"] == "failed"]
        wins = sum(r["outcome"] == "ok" for r in recent)
        missing = next(
            (
                r["proof"].get("missing")
                for r in reversed(selected)
                if r["proof"].get("ok") is None and r["proof"].get("missing")
            ),
            cap.missing,
        )
        label = (
            "not built"
            if not cap.built
            else "not measurable"
            if missing
            else "too few tries"
            if len(recent) < 10
            else "green"
            if wins >= cap.mark
            else "red"
        )
        capabilities.append(
            {
                "id": cap.id,
                "title": cap.title,
                "german": cap.german,
                "state": label,
                "reason": missing or cap.missing,
                "last10": [wins, len(recent)],
                "all": [sum(r["outcome"] == "ok" for r in counted), len(counted)],
                "excluded": len(selected) - len(counted),
                "median_seconds": statistics.median(r["seconds"] for r in counted) if counted else None,
                "causes": dict(Counter(r["cause"] for r in failed)),
                "top_reasons": Counter(r["skill_reason"] for r in failed).most_common(3),
                "newest_failures": [r["session"] for r in failed[-3:][::-1]],
                "marked": sum(bool(r.get("marked")) for r in selected),
            }
        )
        for row in failed:
            ranking[(cap.id, row["cause"], row["skill_reason"])] += 1
        for row in counted:
            by_commit[(cap.id, row["commit"], row["dirty"])].append(row)
    return {
        "capabilities": capabilities,
        "ranking": [
            {"capability": key[0], "cause": key[1], "reason": key[2], "count": count}
            for key, count in sorted(ranking.items(), key=lambda pair: (-pair[1], str(pair[0])))
        ],
        "commits": [
            {
                "capability": key[0],
                "commit": key[1],
                "dirty": key[2],
                "ok": sum(r["outcome"] == "ok" for r in value),
                "counted": len(value),
            }
            for key, value in by_commit.items()
        ],
        "unclear": sum(r["cause"] == "unclear" for r in failures),
        "failures": len(failures),
        "total": len(rows),
    }


def framesheet(session: Path, output: Path) -> str | None:
    """Four frames, including the final decodable video frame, written locally."""
    video = session / "video.mp4"
    if not video.exists():
        return None
    import hashlib

    target = output / (hashlib.sha256(str(session).encode()).hexdigest()[:16] + ".jpg")
    output.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        try:
            data = json.loads(
                subprocess.check_output(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-select_streams",
                        "v:0",
                        "-count_frames",
                        "-show_entries",
                        "stream=nb_read_frames",
                        "-of",
                        "json",
                        str(video),
                    ],
                    text=True,
                )
            )
            count = int(data["streams"][0]["nb_read_frames"])
            indices = sorted({0, (count - 1) // 3, 2 * (count - 1) // 3, count - 1})
            select = "+".join(f"eq(n\\,{i})" for i in indices)
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(video),
                    "-vf",
                    f"select='{select}',scale=320:-2,tile=2x2",
                    "-frames:v",
                    "1",
                    "-q:v",
                    "6",
                    "-y",
                    str(target),
                ],
                check=True,
                capture_output=True,
            )
        except (OSError, ValueError, KeyError, IndexError, subprocess.CalledProcessError):
            return None
    return base64.b64encode(target.read_bytes()).decode()


def write_board(ledger: Path, *, sheets: bool = True) -> dict:
    rows = apply_marks(read_jsonl(ledger), read_jsonl(marks_path(ledger)))
    data = board_data(rows)
    lines = [
        "# Capability bench",
        "",
        f"{data['total']} tries; {data['failures']} counted failures; unclear "
        f"{data['unclear']}/{data['failures']} ({data['unclear'] / data['failures']:.1%})."
        if data["failures"]
        else f"{data['total']} tries; no counted failures; unclear share undefined.",
        "",
        (
            "Historical code versions are unknown unless recorded at execution. Missing evidence "
            "is excluded, never converted into a pass."
        ),
        "",
        "| Capability | State | Last ten | All | Median s | Excluded | Causes | Top reasons |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for cap in data["capabilities"]:
        lines.append(
            f"| {cap['id']} | {cap['state']} | {cap['last10'][0]}/{cap['last10'][1]} | "
            f"{cap['all'][0]}/{cap['all'][1]} | {cap['median_seconds']} | {cap['excluded']} | "
            f"{cap['causes']} | {str(cap['top_reasons']).replace('|', '/')} |"
        )
    lines += ["", "## Evidence and newest failures", ""]
    for cap in data["capabilities"]:
        lines.append(
            f"{cap['id']}: {cap['reason'] or CATALOGUE[cap['id']].proof} Marked: {cap['marked']}. "
            f"Newest failures: {', '.join(cap['newest_failures']) or 'none'}."
        )
        lines.append("")
    lines += ["## Repair ranking", "", "| Capability | Cause | Reason | Count |", "| --- | --- | --- | --- |"]
    for rank in data["ranking"]:
        lines.append(
            f"| {rank['capability']} | {rank['cause']} | {rank['reason'].replace('|', '/')} | "
            f"{rank['count']} |"
        )
    lines += ["", "## Rates by commit", ""]
    for commit in data["commits"]:
        lines.append(
            f"{commit['capability']}: {commit['commit']} (dirty={commit['dirty']}), "
            f"{commit['ok']}/{commit['counted']}."
        )
        lines.append("")
    markdown = "\n".join(lines) + "\n"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.with_suffix(".md").write_text(markdown)
    page = [
        (
            '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" '
            'content="width=device-width"><title>Capability bench</title><style>'
            "body{font:15px system-ui;background:#111821;color:#e4eaf0;margin:2rem;max-width:1400px}"
            "table{border-collapse:collapse;width:100%}"
            "td,th{padding:.6rem;border-bottom:1px solid #344252;text-align:left;vertical-align:top}"
            "pre{white-space:pre-wrap;overflow-wrap:anywhere}"
            ".green{color:#78db93}"
            ".red{color:#ff8b87}"
            "img{max-width:640px;width:100%}"
            "article{border-top:1px solid #344252;margin-top:2rem}"
            "small{display:block;color:#adbace}"
            "</style><h1>Capability bench</h1>"
        ),
        (
            f"<p>{html.escape(lines[2])}</p><table><tr><th>Capability</th><th>State</th><th>Last "
            f"ten / all</th><th>Median seconds</th><th>Failures</th></tr>"
        ),
    ]
    for cap in data["capabilities"]:
        page.append(
            f"<tr><td>{html.escape(cap['id'])}<small>{html.escape(cap['german'])}</small></td><td "
            f"class='{cap['state']}'>{cap['state']}<small>{html.escape(cap['reason'])}</small></td>"
            f"<td>{cap['last10'][0]}/{cap['last10'][1]} / {cap['all'][0]}/{cap['all'][1]}<small>"
            f"excluded {cap['excluded']}; marked {cap['marked']}</small></td><td>"
            f"{cap['median_seconds']}</td><td>{html.escape(str(cap['causes']))}<small>"
            f"{html.escape(str(cap['top_reasons']))}</small></td></tr>"
        )
    page += [
        "</table><h2>Repair ranking and rates by commit</h2><pre>",
        html.escape(markdown[markdown.index("## Evidence and newest failures") :]),
        "</pre><h2>Failure evidence</h2>",
    ]
    cache = {}
    for row in rows:
        if row["outcome"] != "failed":
            continue
        session = row["session"]
        if session not in cache:
            cache[session] = framesheet(Path(session), ledger.parent / "frames") if sheets else None
        page.append(
            f"<article><h3>{html.escape(row['capability'])}: {html.escape(str(row['cause']))}</h3>"
            f"<p>{html.escape(session)}</p><p>{html.escape(row['skill_reason'])}</p><pre>"
            f"{html.escape(json.dumps(row['proof'], ensure_ascii=False, indent=2))}</pre>"
        )
        if row.get("marked"):
            page.append(f"<p>Marked: {html.escape(row['mark_note'])}</p>")
        page.append(
            f'<img alt="Four session frames including the last video frame" '
            f'src="data:image/jpeg;base64,{cache[session]}">'
            if cache[session]
            else "<p>Frames unavailable: missing video or ffmpeg/ffprobe extraction failed.</p>"
        )
        page.append("</article>")
    page.append("</html>")
    ledger.with_suffix(".html").write_text("\n".join(page))
    print(markdown)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("judge")
    command.add_argument("session", type=Path)
    command.add_argument("--capability", choices=CATALOGUE, required=True)
    command = commands.add_parser("import")
    command.add_argument("source", type=Path)
    command = commands.add_parser("mark")
    command.add_argument("session", type=Path)
    command.add_argument("--capability", choices=CATALOGUE)
    command.add_argument("--outcome", choices=("ok", "failed", "not_counted"), required=True)
    command.add_argument("--cause", choices=CAUSES)
    command.add_argument("--note", required=True)
    command = commands.add_parser("run")
    command.add_argument("capabilities", nargs="+", choices=CATALOGUE)
    command.add_argument("--tries", type=int, default=10)
    command.add_argument("--allow-mission", action="store_true")
    command = commands.add_parser("board")
    command.add_argument("--no-sheets", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "judge":
        row = judge(args.session, args.capability)
        append(args.ledger, row)
        print(json.dumps(row, indent=2))
    elif args.command == "import":
        rows = import_basics(args.source, args.ledger)
        for session in dict.fromkeys(r["session"] for r in rows):
            for incident in harvest(Path(session)):
                append(args.ledger, incident)
        print(f"Imported {len(rows)} trials.")
    elif args.command == "mark":
        if args.outcome == "failed" and args.cause is None:
            parser.error("failed marks require --cause")
        if not args.note.strip():
            parser.error("marks require a nonempty note")
        append(
            marks_path(args.ledger),
            {
                "time": datetime.now(UTC).isoformat(),
                "session": str(args.session.resolve()),
                "capability": args.capability,
                "outcome": args.outcome,
                "cause": args.cause,
                "note": args.note,
            },
        )
    elif args.command == "run":
        try:
            run(args.capabilities, args.tries, args.ledger, allow_mission=args.allow_mission)
        except (BenchStoppedError, ValueError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
    else:
        write_board(args.ledger, sheets=not args.no_sheets)
    return 0
