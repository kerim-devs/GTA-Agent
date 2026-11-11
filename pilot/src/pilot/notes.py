"""Offline text intervals and mission summaries, using recording time throughout."""

from __future__ import annotations

import json
import re
from bisect import bisect_right
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

from .scene import _normal, _similar

KINDS = ("objective", "help", "subtitle", "banner")

# Readings of one objective that are this close in time, and the same up to recognition errors or
# truncation, are one line. Over Wi-Fi a misread objective drops out of its box for one to two
# seconds (the fragment is then read as a subtitle); a cutscene that hides an objective lasts longer.
MERGE_SECONDS = 4.0
MERGE_RATIO = 0.7


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
                previous["variants"][text] += 1
            else:
                active[kind] = {
                    "kind": kind,
                    "text": text,
                    "first": timestamp,
                    "last": timestamp,
                    "variants": Counter({text: 1}),
                }
    intervals.extend(active.values())
    for row in intervals:
        row["variants"] = dict(row["variants"])
    intervals = merge_objectives(intervals)
    return sorted(intervals, key=lambda item: (item["first"], item["kind"]))


def same_objective(a, b):
    """Equal up to recognition errors, or one is the cut-off start of the other."""
    a, b = _normal(a), _normal(b)
    if not a or not b:
        return False
    short, long = sorted((a, b), key=len)
    return (
        SequenceMatcher(None, a, b).ratio() >= MERGE_RATIO
        or SequenceMatcher(None, short, long[: len(short) + 2]).ratio() >= 0.85
    )


def best_reading(variants):
    """The reading a head should be given for one objective.

    Every reading is supported by the samples of all readings it matches, and a cut-off reading counts
    for the longer one it begins, but never wins against it. Among the supported ones the winner is the
    reading with the most letters in ordinary words (misreads put digits and symbols into words), then
    the longest. The most frequent exact text is useless here: over Wi-Fi nearly every sample reads
    differently.
    """

    def support(text):
        return sum(
            count * (1.0 if text == other else SequenceMatcher(None, _normal(text), _normal(other)).ratio())
            for other, count in variants.items()
            if same_objective(text, other)
        )

    def truncated(text):
        n = _normal(text)
        return any(
            len(_normal(other)) > len(n) + 3
            and SequenceMatcher(None, n, _normal(other)[: len(n)]).ratio() > 0.85
            for other in variants
        )

    def clean(text):
        letters = sum(char.isalpha() for char in text)
        words = sum(1 for word in re.findall(r"[^\W\d_]+", text) if len(word) > 2)
        return (letters / max(len(text), 1), words)

    pool = [text for text in variants if not truncated(text)] or list(variants)
    return max(pool, key=lambda text: (round(support(text), 1), clean(text), len(text)))


def merge_banners(rows):
    """One banner read as several texts ("besianden", "bestsandeTr.") is one ending."""
    banners = []
    for row in sorted((r for r in rows if r["kind"] == "banner"), key=lambda r: r["first"]):
        before = banners[-1] if banners else None
        outcome = ending(row["text"])
        if (
            before
            and outcome
            and ending(before["text"]) == outcome
            and row["first"] - before["last"] <= MERGE_SECONDS
        ):
            before["last"] = max(before["last"], row["last"])
        else:
            banners.append(dict(row))
    return [r for r in rows if r["kind"] != "banner"] + banners


def merge_objectives(intervals):
    """One objective is one line: close, similar objective intervals become one."""
    others = merge_banners([row for row in intervals if row["kind"] != "objective"])
    groups = []
    for row in sorted((row for row in intervals if row["kind"] == "objective"), key=lambda r: r["first"]):
        group = groups[-1] if groups else None
        if (
            group
            and row["first"] - group[-1]["last"] <= MERGE_SECONDS
            and any(same_objective(row["text"], member["text"]) for member in group)
        ):
            group.append(row)
        else:
            groups.append([row])
    merged = []
    for group in groups:
        variants = Counter()
        for row in group:
            variants.update(row.get("variants") or {row["text"]: 1})
        merged.append(
            {
                "kind": "objective",
                "text": best_reading(dict(variants)),
                "first": group[0]["first"],
                "last": max(row["last"] for row in group),
                "variants": dict(variants),
            }
        )
    return others + merged


# First words of the game's German and English instructions, with the ones scene.py leaves out
# ("Schlepp den Wagen ...", "Mach das Fahrzeug ... los"). A misread first word ("Beglb", "Stelg")
# still counts when it is a close match.
INSTRUCTION_VERBS = (
    "begib folge sammle schalte fahr fahre geh gehe erreiche steig steige verlasse bring bringe töte "
    "beschaffe kehre kehr rette rett verliere finde find hole hol warte triff schlepp schleppe mach mache "
    "verfolge verfolg zerstöre zerstör fliehe flieh töt lauf such sprich benutz "
    "entkomme versteck nimm ruf rufe wähle spring springe klettere benutze lösche besorge hilf folgt "
    "go follow collect take kill drive find reach enter leave return lose meet wait steal tow"
).split()


def pale_target(frame, box):
    """Coloured target word in a line of objective text.

    scene.py asks for saturated cyan, yellow, red or green. In the Wi-Fi recordings the target word of an
    objective is pale after video compression (cyan from 160,233,233 down to 126,170,184, yellow near
    236,232,155), so only the first test fails there. White text, even with coloured edges from
    compression, does not pass these.
    """
    x, y, w, h = box
    pixels = frame[max(y, 0) : y + h, max(x, 0) : x + w].astype(np.int16)
    if not pixels.size:
        return False
    r, g, b = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    cyan = (g > 120) & (b > 120) & (g - r > 30) & (b - r > 30)
    yellow = (r > 160) & (g > 140) & (r - b > 60) & (g - b > 50)
    red = (r > 140) & (r - g > 60) & (r - b > 60)
    green = (g > 120) & (g - r > 30) & (g - b > 30)
    return float(np.mean(cyan | yellow | red | green)) > 0.012


def instruction_like(text):
    """An instruction by its first word: a listed verb, or a listed verb of five letters or more with
    one letter misread ("Beglb", "Stelg"). Dialogue starts with words one letter off a verb too
    ("Machen wir", "Nach dem", "war"), so other fuzzy matches and long lines are refused."""
    words = text.split()
    if not words or sum(char.isalpha() for char in text) < 8 or len(text) > 80:
        return False
    first = re.sub(r"[^\wäöüß]", "", words[0].casefold())
    if first in INSTRUCTION_VERBS:
        return True
    return len(first) >= 5 and any(
        len(verb) == len(first) and sum(a != b for a, b in zip(verb, first, strict=True)) <= 1
        for verb in INSTRUCTION_VERBS
    )


def promote_objectives(scene, frame):
    """Lines scene.py read as subtitle that are objectives by their words and a coloured target.

    Returns the scene with those lines labelled objective and its joined texts rebuilt.
    """
    from dataclasses import replace

    lines = tuple(
        replace(line, region="objective")
        if line.region == "subtitle"
        and line.confidence >= 0.3
        and instruction_like(line.text)
        and pale_target(frame, line.box)
        else line
        for line in scene.lines
    )
    if lines == scene.lines:
        return scene

    def joined(*labels):
        return " ".join(line.text for line in lines if line.region in labels and line.confidence >= 0.3)

    return replace(scene, lines=lines, objective=joined("objective"), subtitle=joined("subtitle"))


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
    """What a banner says, tolerating the recognition errors of Wi-Fi frames ("besianden")."""
    normal = _normal(text)
    if any(
        _similar(text, phrase) for phrase in ("mission fehlgeschlagen", "fehlgeschlagen", "mission failed")
    ):
        return "failed"
    if len(normal) >= 9 and normal.startswith("mission f"):
        return "failed"
    words = normal.split()
    if re.search(r"\b(bestanden|geschafft|passed)\b", text, re.I) or any(
        SequenceMatcher(None, word[:9], "bestanden").ratio() >= 0.75 for word in words
    ):
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
