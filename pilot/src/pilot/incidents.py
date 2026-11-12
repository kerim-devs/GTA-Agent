"""What went wrong while Kerim played: incidents found offline from the readers, the texts and his pad.

Every function here works on sequences that the tools have already written, never on video:
`samples` are the HUD and minimap readings of `pilot/tools/incidents.py` at ten a second (screen,
wanted, health, minimap kind, map travel under the arrow, red blips, brightness, the printed
distance and a colour signature of the vehicle under the chase camera), `texts` and `readings` come
from `texts.py`, `sections` from P38 and `pads` from the recording's `pad.jsonl`.

The classes are closed. Each incident has one cause from the list of its class, and `unknown` where
the evidence does not decide.
"""

from __future__ import annotations

import itertools
import json
import re
from bisect import bisect_left, bisect_right
from collections import Counter
from pathlib import Path
from statistics import median

from .notes import best_reading, ending, same_objective

CLASSES = {
    "death": ("police", "crash", "explosion", "fight", "fall", "drowning", "unknown"),
    "arrest": ("police",),
    "mission_failed": (
        "player_died",
        "player_arrested",
        "target_escaped",
        "vehicle_destroyed",
        "ally_died",
        "seen",
        "left_area",
        "time_out",
        "other",
        "unknown",
    ),
    "mission_passed": ("passed",),
    "retry": ("checkpoint", "mission_start", "unknown"),
    "wanted": ("lost", "death", "arrest", "mission_end", "recording_end"),
    "collision": ("carried_on", "reversed", "left_car", "car_dead", "unknown"),
    "car_change": ("after_crash", "mission", "other"),
    "standstill": ("stuck_vehicle", "stuck_foot", "fight", "camera", "waiting"),
    "reverse": ("reverse",),
    "turn": ("turn",),
}

# How far each class can be trusted, from the contact sheets of docs/reports/P43-what-went-wrong.md.
SURE = {
    "death": "high",
    "arrest": "low",
    "mission_failed": "high",
    "mission_passed": "high",
    "retry": "high",
    "wanted": "medium",
    "collision": "low",
    "car_change": "low",
    "standstill": "medium",
    "reverse": "medium",
    "turn": "low",
}

# Kerim's controller leads the picture over Wi-Fi: the pad's clock is the Mac's, the frame's is the
# time it arrived. docs/tasks/README.md measured 0.6 to 1.1 s on recording 093238; the middle is used.
PAD_LEAD = 0.8
# Map travel under the player arrow in crop pixels a second (`move` of the samples). Measured on
# 164039: driving in a car park reads 10 to 30, a street drive 20 to 60, a standing car under 1.
# Over Wi-Fi single samples repeat a frame (0) or lose the flow (over 150), so only medians over two
# seconds are used.
FAST = 12.0
STILL = 1.5
STOPPED = 5.0
PLAYERS = ("franklin", "michael", "trevor")


# ----------------------------------------------------------------------------------------------- pad


class Pad:
    """Kerim's controller as a step function of picture time. `pad.jsonl` holds one line per change."""

    def __init__(self, rows, lead=PAD_LEAD):
        rows = sorted((row for row in rows if row.get("src", "human") == "human"), key=lambda r: r["t"])
        self.rows = rows
        self.times = [row["t"] + lead for row in rows]

    def __bool__(self):
        return len(self.rows) > 1

    def at(self, t):
        index = bisect_right(self.times, t) - 1
        return self.rows[index] if index >= 0 else None

    def share(self, start, end, test):
        """Share of [start, end] during which `test(row)` held."""
        if end <= start or not self:
            return 0.0
        index = max(0, bisect_right(self.times, start) - 1)
        total = 0.0
        while index < len(self.rows) and self.times[index] < end:
            left = max(start, self.times[index])
            right = min(end, self.times[index + 1] if index + 1 < len(self.rows) else end)
            if right > left and test(self.rows[index]):
                total += right - left
            index += 1
        return total / (end - start)

    def presses(self, start, end, button):
        """Times at which `button` went down in [start, end]."""
        found = []
        index = max(0, bisect_right(self.times, start) - 1)
        before = index > 0 and button in self.rows[index - 1].get("buttons", [])
        for i in range(index, len(self.rows)):
            if self.times[i] > end:
                break
            down = button in self.rows[i].get("buttons", [])
            if down and not before and self.times[i] >= start:
                found.append(self.times[i])
            before = down
        return found


def throttle(row):
    return row.get("r2", 0) > 0.5


def brake(row):
    return row.get("l2", 0) > 0.5


def steering(row):
    return abs(row.get("left", [0, 0])[0]) > 0.7


def walking(row):
    return max(abs(v) for v in row.get("left", [0, 0])) > 0.4


def looking(row):
    return max(abs(v) for v in row.get("right", [0, 0])) > 0.4


def active(row):
    return (
        max(abs(v) for v in (*row.get("left", [0, 0]), *row.get("right", [0, 0]))) > 0.25
        or row.get("l2", 0) > 0.1
        or row.get("r2", 0) > 0.1
        or bool(row.get("buttons"))
    )


# ------------------------------------------------------------------------------------------ context


class Context:
    """The sequences of one recording with lookups by picture time."""

    def __init__(self, samples, sections, pads, seconds):
        self.samples = sorted(samples, key=lambda s: s["t"])
        self.times = [s["t"] for s in self.samples]
        self.sections = sorted(sections["sections"], key=lambda s: s["start"])
        self.starts = [s["start"] for s in self.sections]
        self.pad = Pad(pads)
        self.seconds = seconds

    def window(self, start, end):
        return self.samples[bisect_left(self.times, start) : bisect_right(self.times, end)]

    def frame(self, t):
        if not self.samples:
            return None
        index = min(len(self.samples) - 1, bisect_left(self.times, t))
        if index and abs(self.times[index - 1] - t) < abs(self.times[index] - t):
            index -= 1
        return self.samples[index]["i"]

    def kind(self, t):
        index = bisect_right(self.starts, t) - 1
        if index < 0:
            return "unknown"
        section = self.sections[index]
        return section["kind"] if t <= section["end"] else "unknown"

    def driving(self, t):
        return self.kind(t) == "drive"

    def speed(self, start, end):
        """Median map travel of [start, end] in crop pixels a second, or None when fewer than three
        samples or less than 40 % of them can be read."""
        rows = self.window(start, end)
        values = [s["move"] for s in rows if s.get("move") is not None]
        if len(values) < 3 or len(values) < 0.4 * len(rows):
            return None
        return median(values)

    def gps_speed(self, start, end):
        """Metres a second from the printed distance where the game prints one, or None."""
        fixes = [(s["t"], s["gps"]) for s in self.window(start, end) if s.get("gps") is not None]
        if len(fixes) < 3 or fixes[-1][0] - fixes[0][0] < 1.0:
            return None
        slopes = [
            abs(b[1] - a[1]) / (b[0] - a[0]) for a, b in itertools.pairwise(fixes) if b[0] - a[0] >= 0.3
        ]
        return round(median(slopes), 1) if slopes else None


def evidence_at(ctx, t):
    """What the readers say in the second before t, for every incident."""
    near = ctx.window(t - 1, t)
    health = [s["health"] for s in near if s.get("health") is not None]
    wanted = [s["wanted"] for s in near if s.get("wanted") is not None]
    return {
        "section": ctx.kind(t),
        "health": health[-1] if health else None,
        "wanted": max(wanted) if wanted else None,
    }


def incident(ctx, t, klass, cause, sure=None, evidence=None, **fields):
    if cause not in CLASSES[klass]:
        raise ValueError(f"{cause} is not a cause of {klass}")
    row = {
        "t": round(t, 3),
        "frame": ctx.frame(t),
        "class": klass,
        "cause": cause,
        "sure": sure or SURE[klass],
    }
    row.update(fields)
    row["evidence"] = {**evidence_at(ctx, t), **(evidence or {})}
    return row


def runs(samples, test, gap=0.6, least=0.3):
    """Stretches in which `test(sample)` holds, bridging gaps up to `gap` seconds: (start, end, rows)."""
    found = []
    current = []
    for sample in samples:
        if test(sample):
            if current and sample["t"] - current[-1]["t"] > gap:
                found.append(current)
                current = []
            current.append(sample)
    if current:
        found.append(current)
    return [(rows[0]["t"], rows[-1]["t"], rows) for rows in found if rows[-1]["t"] - rows[0]["t"] >= least]


# ------------------------------------------------------------------------------------------ banners


FAILURE_REASONS = (
    ("player_arrested", r"verhaftet|festgenommen|busted|arrested"),
    ("vehicle_destroyed", r"zerst[öo]rt|kaputt|fahrunt[üu]chtig|wrack|destroyed"),
    (
        "target_escaped",
        r"entkommen|entwischt|geflohen|abgeh[äa]ngt|aus den augen|verloren|escaped|got away|\blost\b",
    ),
    ("seen", r"entdeckt|gesehen|bemerkt|aufgeflogen|spotted|\bseen\b"),
    ("left_area", r"verlassen|zur[üu]ckgelassen|zu weit|im stich|abandoned|\bleft\b"),
    ("time_out", r"\bzeit\b|zu sp[äa]t|abgelaufen|\btime\b"),
)


def failure_reason(text):
    """The class of the line the game prints under "Mission fehlgeschlagen"; the text stays as read."""
    if not text:
        return "unknown"
    lowered = text.casefold()
    if re.search(r"\b(tot|gestorben|get[öo]tet|died|dead)\b", lowered):
        if any(name in lowered for name in PLAYERS) or "du bist" in lowered:
            return "player_died"
        return "ally_died"
    for reason, pattern in FAILURE_REASONS:
        if re.search(pattern, lowered):
            return reason
    return "other"


def reason_lines(readings, start, end):
    """Readings of the line under the banner: centred, its middle between y 355 and 420 of the frame.
    Wrapped reasons are two lines and are joined top to bottom."""
    variants = Counter()
    for row in readings:
        if not start <= row["t"] <= end:
            continue
        lines = sorted(
            (line for line in row["text"]["lines"] if line["region"] != "banner"),
            key=lambda line: (line["box"][1], line["box"][0]),
        )
        parts = []
        for line in lines:
            x, y, w, h = line["box"]
            if 355 <= y + h / 2 <= 420 and abs(x + w / 2 - 640) < 160 and w > 30:
                parts.append(line["text"].strip())
        text = " ".join(part for part in parts if part)
        if sum(char.isalpha() for char in text) >= 6:
            variants[text] += 1
    return variants


def reason_at(readings, item):
    """The reason as read, and when it was first on screen: the banner is often read later than the
    reason under it, while the scene behind it still fades."""
    variants = reason_lines(readings, item["first"] - 6, item["last"] + 1)
    if not variants:
        return "", item["first"]
    best = best_reading(dict(variants))
    first = min(
        (
            t
            for t, text in reason_times(readings, item["first"] - 6, item["last"] + 1)
            if same_objective(text, best)
        ),
        default=item["first"],
    )
    return best, min(first, item["first"])


def reason_times(readings, start, end):
    for row in readings:
        if start <= row["t"] <= end:
            for text in reason_lines([row], start, end):
                yield row["t"], text


def endings(ctx, texts):
    """Failed and passed banners: the texts' banner lines joined with the HUD reader's banner screens."""
    found = [
        {"outcome": ending(row["text"]), "first": row["first"], "last": row["last"], "text": row["text"]}
        for row in texts
        if row["kind"] == "banner" and ending(row["text"]) in ("failed", "passed")
    ]
    for screen in ("failed", "passed"):
        for start, end, _ in runs(
            ctx.samples, lambda s, screen=screen: s["screen"] == screen, gap=1.5, least=0.2
        ):
            found.append({"outcome": screen, "first": start, "last": end, "text": None})
    found.sort(key=lambda item: item["first"])
    merged = []
    for item in found:
        if merged and merged[-1]["outcome"] == item["outcome"] and item["first"] - merged[-1]["last"] <= 6:
            merged[-1]["last"] = max(merged[-1]["last"], item["last"])
            merged[-1]["text"] = merged[-1]["text"] or item["text"]
        else:
            merged.append(dict(item))
    return merged


def last_hud(ctx, before, within=10.0):
    """The last time the health bar was read before `before`: where play ended before a banner."""
    seen = [s["t"] for s in ctx.window(before - within, before) if s.get("health") is not None]
    return seen[-1] if seen else before - 3.0


def resumed(ctx, after, within=40.0):
    """The first time play is back after a banner: a health bar read after a black or loading screen."""
    dark = False
    for sample in ctx.window(after, after + within):
        if sample["screen"] == "loading" or sample.get("lum", 99) < 3:
            dark = True
        elif dark and sample.get("health") is not None and sample["screen"] == "game":
            return sample["t"]
    return None


# ------------------------------------------------------------------------------------------- deaths


def death_cause(ctx, t, collisions):
    """What preceded a death in the fifteen seconds before it, as (cause, why).

    Stars before the death say police; a collision says crash; a white flash, an explosion; red
    blips, health lost in several hits, or aim and fire on foot, a fight; a vehicle under him
    without any of these, a crash; a health bar over half that vanishes at once on foot, a fall.
    Drowning shows nothing these readers see and stays unknown.
    """
    window = ctx.window(t - 15, t)
    stars = sum((s.get("wanted") or 0) >= 1 for s in window)
    in_vehicle = sum(ctx.driving(s["t"]) for s in window) > max(5, len(window) // 3)
    red = sum((s.get("red") or 0) >= 1 for s in window)
    shooting = 0.0 if in_vehicle else ctx.pad.share(t - 15, t, lambda r: brake(r) or throttle(r))
    bars = [s["health"] for s in window if s.get("health") is not None]
    hits = sum(a - b > 0.04 for a, b in itertools.pairwise(bars))
    fighting = red >= 10 or shooting > 0.1 or hits >= 3
    flash = any(
        b.get("lum", 0) - a.get("lum", 0) > 60 for a, b in itertools.pairwise(window) if b["t"] < t - 0.3
    )
    health = [s for s in ctx.window(t - 3, t) if s.get("health") is not None]
    crash = [c for c in collisions if t - 10 <= c["t"] <= t]
    if stars >= 10:
        return "police", f"{stars} samples with stars in the 15 s before"
    if crash:
        return "crash", "collision in the 10 s before"
    if flash:
        return "explosion", "white flash before the death"
    if fighting:
        return "fight", f"{red} samples with red blips, {hits} hits, aim or fire {shooting:.0%} of the time"
    if in_vehicle:
        return "crash", "in a vehicle, no fight seen"
    if health and health[0]["health"] >= 0.5:
        return "fall", "on foot, health over half 3 s before, no fight"
    return "unknown", ""


def find_deaths(ctx, readings, banners, collisions):
    """Deaths: a failed mission whose reason names the player ("Franklin ist tot."), and the death
    screen the HUD reader knows. In a mission the game shows the failure instead of the death screen."""
    found = []
    for item in banners:
        if item["outcome"] != "failed":
            continue
        if failure_reason(item["reason"]) == "player_died":
            t = last_hud(ctx, item["first"])
            found.append((t, "failed banner", item["reason"], *death_cause(ctx, t, collisions)))
    for start, _end, _rows in runs(ctx.samples, lambda s: s["screen"] == "wasted", gap=1.5, least=0.2):
        if any(abs(start - other[0]) < 15 for other in found):
            continue
        t = last_hud(ctx, start)
        found.append((t, "death screen", None, *death_cause(ctx, t, collisions)))
    return [
        incident(ctx, t, "death", cause, evidence={"seen_by": by, "reason": reason, "why": why})
        for t, by, reason, cause, why in found
    ]


def find_arrests(ctx, readings):
    """The arrest screen ("Verhaftet") read by the text recognition. The HUD reader has no template
    for it, so an arrest whose text is not read is not found."""
    found = []
    for row in readings:
        for line in row["text"]["lines"]:
            if re.search(r"\b(verhaftet|festgenommen|busted)\b", line["text"], re.I):
                if not found or row["t"] - found[-1][0] >= 15:
                    found.append((row["t"], line["text"]))
    return [
        incident(ctx, last_hud(ctx, t), "arrest", "police", evidence={"text": text, "screen_at": t})
        for t, text in found
    ]


# ------------------------------------------------------------------------------------- missions


def find_mission_endings(ctx, readings, banners):
    """Passed and failed missions. A failure carries its reason as read and what Kerim did next:
    the footer offers "Erneut versuchen" on cross and "Verlassen" on circle."""
    found = []
    for item in banners:
        if item["outcome"] == "passed":
            found.append(
                incident(ctx, item["first"], "mission_passed", "passed", evidence={"text": item["text"]})
            )
            continue
        reason = item["reason"]
        cross = ctx.pad.presses(item["first"], item["last"] + 15, "cross")
        circle = ctx.pad.presses(item["first"], item["last"] + 15, "circle")
        back = resumed(ctx, item["last"])
        if cross and (not circle or cross[0] < circle[0]):
            then = "retry"
        elif circle:
            then = "quit"
        else:
            then = "retry" if back is not None and back - item["last"] < 15 else "unknown"
        found.append(
            incident(
                ctx,
                item["first"],
                "mission_failed",
                failure_reason(reason),
                then=then,
                resumed=back,
                evidence={"banner": item["text"], "reason": reason, "banner_end": round(item["last"], 3)},
            )
        )
    return found


def find_retries(ctx, failures, missions):
    """A retry is a failure, the retry chosen, and play back. Its cause says where the game put him:
    the objective he is given then is a later step of the failed try (a checkpoint) or its first."""
    found = []
    for failure in failures:
        if failure["then"] != "retry" or failure["resumed"] is None:
            continue
        t = failure["resumed"]
        failed = mission_at(missions, failure["t"]) or banner_mission(missions, failure["t"])
        following = next(
            (
                step["objective"]
                for mission in missions.get("missions", [])
                for step in mission["steps"]
                if t - 2 <= step["start"] <= t + 40
            ),
            None,
        )
        cause = "unknown"
        if failed is not None and following:
            steps = [step["objective"] for step in missions["missions"][failed[0] - 1]["steps"]]
            if any(same_objective(text, following) for text in steps[1:]):
                cause = "checkpoint"
            elif same_objective(steps[0], following):
                cause = "mission_start"
        found.append(
            incident(
                ctx, t, "retry", cause, evidence={"failed_at": failure["t"], "objective_after": following}
            )
        )
    return found


BANNER_CLASSES = ("death", "mission_failed", "mission_passed")


def banner_mission(missions, t, within=180.0):
    """The mission a banner ends when it comes after the last objective was read for a while: the
    latest mission that began before it and ended at most `within` seconds earlier. missions.json
    closes a mission after a minute without an objective, which a long chase or fight outlasts."""
    candidates = [
        (number, len(mission["steps"]))
        for number, mission in enumerate(missions.get("missions", []), 1)
        if mission["start"] <= t and t - mission["end"] <= within
    ]
    return candidates[-1] if candidates else None


def mission_at(missions, t, slack=3.0):
    """(mission number, step number) of the step at t; a banner just after the last step counts."""
    for number, mission in enumerate(missions.get("missions", []), 1):
        if mission["start"] - 0.5 <= t <= mission["end"] + slack:
            for index, step in enumerate(mission["steps"], 1):
                last = index == len(mission["steps"])
                if step["start"] - 0.5 <= t <= step["end"] + (slack if last else 0):
                    return number, index
            return number, None
    return None


# -------------------------------------------------------------------------------------- wanted level


def find_wanted(ctx, ends):
    """Episodes with stars, from the first lasting star to the first lasting zero.

    A star counts when three readings within a second agree; a zero ends an episode when it is read
    for two seconds without a star. Cutscenes and menus, where the reader says nothing, do not end
    one. The end is a death, an arrest or a mission banner inside the episode, a cutscene or loading
    screen between the last star and the zero (the game clears the stars), or lost.
    """
    samples = [s for s in ctx.samples if s.get("wanted") is not None]
    found = []
    i = 0
    while i < len(samples):
        s = samples[i]
        lasting = [x for x in samples[i : i + 8] if x["t"] - s["t"] <= 1.0 and x["wanted"] >= 1]
        if s["wanted"] < 1 or len(lasting) < 3:
            i += 1
            continue
        start, level, last_star, end = s["t"], 0, s["t"], None
        j = i
        while j < len(samples):
            x = samples[j]
            if x["wanted"] >= 1:
                last_star = x["t"]
                agree = [
                    y for y in samples[j : j + 8] if y["t"] - x["t"] <= 1.0 and y["wanted"] == x["wanted"]
                ]
                if len(agree) >= 3:
                    level = max(level, x["wanted"])
                j += 1
                continue
            zeros = [y for y in samples[j : j + 60] if y["t"] - x["t"] <= 2.5]
            if zeros[-1]["t"] - x["t"] >= 2.0 and all(y["wanted"] == 0 for y in zeros):
                end = x["t"]
                break
            j += 1
        stop = end if end is not None else ctx.seconds
        cause = "lost" if end is not None else "recording_end"
        ended_by = next(((t, klass) for t, klass in ends if start <= t <= stop + 3), None)
        if ended_by:
            cause = {"death": "death", "arrest": "arrest"}.get(ended_by[1], "mission_end")
            stop = min(stop, ended_by[0])
            last_star = min(last_star, stop)
        elif end is not None and any(
            ctx.kind(last_star + k * 0.5) in ("cutscene", "loading", "banner")
            for k in range(int((end - last_star) * 2) + 1)
        ):
            cause = "mission_end"
        found.append(
            incident(
                ctx,
                start,
                "wanted",
                cause,
                end=round(stop, 3),
                seconds=round(stop - start, 1),
                level=level or s["wanted"],
                evidence={"last_star": round(last_star, 3)},
            )
        )
        j = i
        while j < len(samples) and samples[j]["t"] <= stop:
            j += 1
        if ended_by:
            # The stars stay on screen through the death or the banner; they are over once a zero is
            # read or play comes back from a black or loading screen (a retry may bring its own).
            dark = next(
                (
                    x["t"]
                    for x in ctx.window(stop, stop + 60)
                    if x["screen"] == "loading" or x.get("lum", 99) < 3
                ),
                None,
            )
            while (
                j < len(samples) and samples[j]["wanted"] >= 1 and (dark is None or samples[j]["t"] <= dark)
            ):
                j += 1
        i = max(j, i + 1)
    return found


# ------------------------------------------------------------------------------------------ driving


def find_collisions(ctx):
    """A sudden loss of speed in a vehicle with the throttle held and the brake not.

    Speed is the median map travel over two seconds before (2.5 to 0.3 s ahead of the moment) and
    two after (0.3 to 2.3 s), so that one repeated frame or one turn of the camera decides nothing.
    A collision is a drive of 12 or more that falls to 5 or less and to a quarter: a stop out of
    speed, or nearly one. A crash that only slows the car and drives on is not found. Braking or a
    released throttle explains a drop, so it is not counted. The printed distance, where the game
    shows one, gives metres a second as evidence.
    """
    found = []
    last = -1e9
    for sample in ctx.samples:
        t = sample["t"]
        if t - last < 4 or sample.get("move") is None or sample["move"] > 3 or not ctx.driving(t):
            continue
        before = ctx.speed(t - 2.5, t - 0.3)
        after = ctx.speed(t + 0.3, t + 2.3)
        if before is None or after is None or before < FAST or after > min(STOPPED, before / 4):
            continue
        if any(s["map"] != "tilted" or s["screen"] != "game" for s in ctx.window(t, t + 2.3)):
            continue
        if ctx.pad and (ctx.pad.share(t - 2, t, brake) > 0.2 or ctx.pad.share(t - 2, t, throttle) < 0.4):
            continue
        then, why = after_collision(ctx, t, before)
        if then in ("left_car", "car_dead") and ctx.pad and ctx.pad.share(t - 0.5, t + 0.5, throttle) < 0.2:
            # Throttle off at the stop and out of the car: he parked. On the sheets of 11 November
            # every such stop was a parking, never a crash.
            continue
        found.append(
            incident(
                ctx,
                t,
                "collision",
                then,
                kind="standstill" if after <= STILL else "slowed",
                evidence={
                    "speed_before": round(before, 1),
                    "speed_after": round(after, 1),
                    "gps_before_ms": ctx.gps_speed(t - 4, t),
                    "gps_after_ms": ctx.gps_speed(t, t + 3),
                    "why": why,
                },
            )
        )
        last = t
    return found


def after_collision(ctx, t, before):
    """What followed a collision in the next ten seconds, as (cause, why)."""
    horizon = t + 10
    left = next((s["t"] for s in ctx.window(t, horizon) if ctx.kind(s["t"]) == "foot"), None)
    if left is not None:
        tried = ctx.pad.share(t + 0.5, left, lambda r: throttle(r) or brake(r))
        moving = ctx.speed(t + 0.5, left)
        if left - t >= 2.5 and tried > 0.5 and (moving is None or moving < 3.0):
            return "car_dead", f"pedals held {tried:.0%} without moving, out {left - t:.1f} s later"
        return "left_car", f"on foot {left - t:.1f} s later"
    for sample in ctx.window(t + 0.6, horizon):
        u = sample["t"]
        speed = ctx.speed(u - 0.5, u + 0.5)
        if ctx.pad.share(u - 1, u, brake) > 0.8 and (speed or 0) > 3.0:
            return "reversed", f"brake held and moving {u - t:.1f} s later"
        if speed is not None and speed >= max(FAST * 0.8, before * 0.5):
            return "carried_on", f"speed back {u - t:.1f} s later"
    return "unknown", ""


def find_manoeuvres(ctx):
    """Long reverses (brake held without throttle while the map moves, three seconds or more) and
    long turns (steering at full lock while the map moves, four seconds or more)."""
    found = []
    for klass, test, least in (
        ("reverse", lambda r: brake(r) and not throttle(r), 3.0),
        ("turn", steering, 4.0),
    ):
        held = [
            s
            for s in ctx.samples
            if ctx.driving(s["t"]) and ctx.pad.at(s["t"]) is not None and test(ctx.pad.at(s["t"]))
        ]
        for start, end, _rows in runs(held, lambda s: True, gap=0.3, least=least):
            moving = ctx.speed(start, end)
            if moving is None or moving < 3.0:
                continue
            found.append(
                incident(
                    ctx,
                    start,
                    klass,
                    klass,
                    end=round(end, 3),
                    seconds=round(end - start, 1),
                    evidence={"speed": round(moving, 1)},
                )
            )
    return found


# L1 distance of two colour signatures (car_signature in tools/incidents.py) above which the vehicle
# under the camera is taken for another one.
CAR_DISTANCE = 0.4


def signature(rows):
    cars = [row["car"] for row in rows if row.get("car")]
    if len(cars) < 5:
        return None
    return [median(values) for values in zip(*cars, strict=True)]


def find_car_changes(ctx, collisions, missions):
    """A drive, at least two seconds on foot, and another drive, with the colours under the chase
    camera different before and after. The detector is not run, so the vehicles themselves are not
    seen; the same car driven on looks the same under the camera and is not counted, and a change
    whose colours cannot be read on both sides (a damaged or untilted map) is not counted either."""
    drives = [s for s in ctx.sections if s["kind"] == "drive" and s["end"] - s["start"] >= 2]
    found = []
    for a, b in itertools.pairwise(drives):
        between = [s for s in ctx.sections if a["end"] <= s["start"] and s["end"] <= b["start"]]
        if b["start"] - a["end"] > 180 or any(
            s["kind"] in ("cutscene", "loading", "banner") for s in between
        ):
            continue
        if not any(s["kind"] == "foot" and s["end"] - s["start"] >= 2 for s in between):
            continue
        old = signature(ctx.window(a["end"] - 4, a["end"] - 0.5))
        new = signature(ctx.window(b["start"] + 1, b["start"] + 5))
        distance = (
            None if old is None or new is None else sum(abs(x - y) for x, y in zip(old, new, strict=True))
        )
        if distance is None or distance < CAR_DISTANCE:
            continue
        cause = "other"
        if any(
            a["end"] - 15 <= c["t"] <= a["end"] + 1 and c["cause"] in ("left_car", "car_dead")
            for c in collisions
        ):
            cause = "after_crash"
        elif any(
            re.match(r"^\s*(steig|stelg|hol|nimm|klau|stiehl)", step["objective"], re.I)
            and a["end"] - 10 <= step["start"] <= b["start"] + 5
            for mission in missions.get("missions", [])
            for step in mission["steps"]
        ):
            cause = "mission"
        found.append(
            incident(
                ctx,
                a["end"],
                "car_change",
                cause,
                entered=round(b["start"], 3),
                evidence={"colour_distance": None if distance is None else round(distance, 2)},
            )
        )
    return found


# ------------------------------------------------------------------------------------- standstills


def find_standstills(ctx, least=10.0):
    """Ten seconds or more in play, the hand on the controller half the time, and the map not moving.

    Samples the minimap cannot give (damage, no map) are bridged for up to 1.5 s and the stretch
    has to average under the stationary band. On foot the map moves slowly when he walks, so a
    figure that walks in small steps on one spot can be counted as standing.
    """
    in_play = [
        s
        for s in ctx.samples
        if s["screen"] == "game" and s.get("move") is not None and ctx.kind(s["t"]) in ("foot", "drive")
    ]
    found = []
    for start, end, rows in runs(in_play, lambda s: s["move"] <= 3.0, gap=1.5, least=least):
        mean = ctx.speed(start, end)
        if mean is None or mean > STILL:
            continue
        hand = ctx.pad.share(start, end, active)
        if hand < 0.5:
            continue
        vehicle = sum(ctx.driving(s["t"]) for s in rows) > len(rows) / 2
        pedals = ctx.pad.share(start, end, lambda r: throttle(r) or brake(r))
        if vehicle and pedals > 0.3:
            cause = "stuck_vehicle"
        elif not vehicle and pedals > 0.2:
            cause = "fight"
        elif not vehicle and ctx.pad.share(start, end, walking) > 0.3:
            cause = "stuck_foot"
        elif ctx.pad.share(start, end, looking) > 0.3:
            cause = "camera"
        else:
            cause = "waiting"
        found.append(
            incident(
                ctx,
                start,
                "standstill",
                cause,
                end=round(end, 3),
                seconds=round(end - start, 1),
                evidence={"hand": round(hand, 2), "vehicle": vehicle},
            )
        )
    return found


# ------------------------------------------------------------------------------------------- all


def find_incidents(*, samples, texts, readings, sections, pads, missions, seconds):
    """Analyze uninterrupted footage separately, including wanted and controller history."""
    samples = sorted(samples, key=lambda row: row["t"])
    boundaries = [0, *(i for i in range(1, len(samples)) if samples[i]["t"] - samples[i - 1]["t"] > 1)]
    if len(boundaries) == 1:
        return _find_incidents(
            samples=samples,
            texts=texts,
            readings=readings,
            sections=sections,
            pads=pads,
            missions=missions,
            seconds=seconds,
        )
    boundaries.append(len(samples))
    found = []
    for first, stop in itertools.pairwise(boundaries):
        chunk = samples[first:stop]
        start, end = chunk[0]["t"], chunk[-1]["t"]
        local_sections = dict(
            sections,
            sections=[
                dict(row, start=max(start, row["start"]), end=min(end, row["end"]))
                for row in sections["sections"]
                if row["start"] <= end and row["end"] >= start
            ],
        )
        run = _find_incidents(
            samples=chunk,
            texts=[row for row in texts if start <= row["first"] <= end],
            readings=[row for row in readings if start <= row["t"] <= end],
            sections=local_sections,
            pads=pads if first == 0 else [row for row in pads if start <= row["t"] <= end],
            missions=missions,
            seconds=end,
        )
        for row in run:
            if row["cause"] == "recording_end" and stop < len(samples):
                row["evidence"]["clock_gap"] = True
        found.extend(row for row in run if start <= row["t"] <= end)
    return sorted(found, key=lambda row: (row["t"], row["class"]))


def _find_incidents(*, samples, texts, readings, sections, pads, missions, seconds):
    """Every incident of one recording in time order, each with its mission and step."""
    ctx = Context(samples, sections, pads, seconds)
    readings = sorted(readings, key=lambda r: r["t"])
    banners = endings(ctx, texts)
    for item in banners:
        if item["outcome"] == "failed":
            item["reason"], item["first"] = reason_at(readings, item)
    collisions = find_collisions(ctx)
    deaths = find_deaths(ctx, readings, banners, collisions)
    arrests = find_arrests(ctx, readings)
    finished = find_mission_endings(ctx, readings, banners)
    failures = [row for row in finished if row["class"] == "mission_failed"]
    ends = sorted(
        [(row["t"], "death") for row in deaths]
        + [(row["t"], "arrest") for row in arrests]
        + [(row["t"], row["class"]) for row in finished]
    )
    found = (
        deaths
        + arrests
        + finished
        + find_retries(ctx, failures, missions)
        + find_wanted(ctx, ends)
        + collisions
        + find_car_changes(ctx, collisions, missions)
        + find_standstills(ctx)
        + find_manoeuvres(ctx)
    )
    for row in found:
        where = mission_at(missions, row["t"])
        if where is None and row["class"] in BANNER_CLASSES:
            where = banner_mission(missions, row["t"])
            if where:
                row["evidence"]["mission_by"] = "last objective before the banner"
        row["mission"], row["step"] = where if where else (None, None)
        if where and where[1]:
            row["objective"] = missions["missions"][where[0] - 1]["steps"][where[1] - 1]["objective"]
    return sorted(found, key=lambda row: (row["t"], row["class"]))


def attach_to_missions(missions, incidents):
    """missions.json with an `incidents` list on every step; nothing else changes."""
    for number, mission in enumerate(missions.get("missions", []), 1):
        for index, step in enumerate(mission["steps"], 1):
            step["incidents"] = [
                {key: row[key] for key in ("t", "class", "cause")}
                for row in incidents
                if row["mission"] == number and row["step"] == index
            ]
    return missions


# ------------------------------------------------------------------------------------------ summary


def mission_tries(missions, incidents):
    """Missions as Kerim played them: a try that begins after a retry continues the mission retried."""
    retries = [row for row in incidents if row["class"] == "retry"]
    groups = []
    for number, mission in enumerate(missions.get("missions", []), 1):
        failure = next(
            (r for r in incidents if r["class"] == "mission_failed" and r["mission"] == number), None
        )
        death = next((r for r in incidents if r["class"] == "death" and r["mission"] == number), None)
        passed = any(r["class"] == "mission_passed" and r["mission"] == number for r in incidents)
        if failure:
            outcome = f"failed, {failure['cause']}"
            reason = failure["evidence"].get("reason")
            outcome += f' ("{reason}")' if reason else ""
            outcome += f", then {failure['then']}"
        elif death:
            outcome = f"in a death ({death['cause']})"
        elif passed:
            outcome = "passed"
        else:
            outcome = f"without a banner ({mission.get('end_reason', 'next objective')})"
        entry = {
            "start": mission["start"],
            "end": mission["end"],
            "first": mission["steps"][0]["objective"],
            "outcome": outcome,
            "incidents": Counter(r["class"] for r in incidents if r["mission"] == number),
        }
        if groups and any(groups[-1][-1]["end"] - 1 <= r["t"] <= mission["start"] + 1 for r in retries):
            groups[-1].append(entry)
        else:
            groups.append([entry])
    return groups


def write_summary(directory):
    """DIR/incidents.md over every DIR/<name>/incidents.jsonl."""
    directory = Path(directory)
    folders = sorted(path.parent for path in directory.glob("*/incidents.jsonl"))
    classes = list(CLASSES)
    totals, causes = Counter(), Counter()
    recordings = []
    play_total = 0.0
    for folder in folders:
        rows = [
            json.loads(line) for line in (folder / "incidents.jsonl").read_text().splitlines() if line.strip()
        ]
        meta_path = folder / "incidents-meta.json"
        play = json.loads(meta_path.read_text())["play_seconds"] if meta_path.is_file() else 0.0
        play_total += play
        counts = Counter(row["class"] for row in rows)
        totals.update(counts)
        causes.update((row["class"], row["cause"]) for row in rows)
        recordings.append((folder, rows, counts, play))
    hours = play_total / 3600 or 1.0
    lines = [
        "Incidents of the recordings below, as written by pilot/tools/incidents.py. Times are seconds on the "
        "clock of each recording's frames.jsonl, play is the time of its foot and drive sections. A death in "
        "a mission is counted twice, as the death and as the failed mission.",
        "",
        "## Counts per recording",
        "",
        "| Recording | Play min | " + " | ".join(classes) + " |",
        "| --- | --- | " + " | ".join("---" for _ in classes) + " |",
    ]
    for folder, _rows, counts, play in recordings:
        lines.append(
            f"| {folder.name} | {play / 60:.1f} | " + " | ".join(str(counts[k]) for k in classes) + " |"
        )
    lines.append(f"| all | {play_total / 60:.1f} | " + " | ".join(str(totals[k]) for k in classes) + " |")
    lines.append("| per hour of play | | " + " | ".join(f"{totals[k] / hours:.1f}" for k in classes) + " |")
    lines += [
        "",
        "## Counts per cause",
        "",
        "| Class | Cause | Count | Per hour of play |",
        "| --- | --- | --- | --- |",
    ]
    for klass in classes:
        for cause in CLASSES[klass]:
            count = causes[(klass, cause)]
            if count:
                lines.append(f"| {klass} | {cause} | {count} | {count / hours:.1f} |")
    lines += ["", "## Missions", ""]
    for folder, rows, _counts, _play in recordings:
        path = folder / "missions.json"
        missions = json.loads(path.read_text()) if path.is_file() else {"missions": []}
        lines += [f"### {folder.name}", ""]
        if not missions.get("missions"):
            lines += ["No objective was read in this recording.", ""]
        for group in mission_tries(missions, rows):
            tries = []
            for number, entry in enumerate(group, 1):
                found = ", ".join(f"{n} {k}" for k, n in sorted(entry["incidents"].items())) or "none"
                tries.append(
                    f"try {number}, {entry['start']:.0f} to {entry['end']:.0f} s, ended {entry['outcome']}; "
                    f"incidents {found}"
                )
            plural = "try" if len(group) == 1 else "tries"
            lines += [f'"{group[0]["first"]}", {len(group)} {plural}: ' + "; ".join(tries) + ".", ""]
        outside = Counter(row["class"] for row in rows if row["mission"] is None)
        if outside:
            lines += [
                "Outside any mission: " + ", ".join(f"{n} {k}" for k, n in sorted(outside.items())) + ".",
                "",
            ]
    lines += [
        "## Deaths, arrests and failures",
        "",
        "| Recording | Time | Frame | Class | Cause | Text as read |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for folder, rows, _counts, _play in recordings:
        for row in rows:
            if row["class"] in ("death", "arrest", "mission_failed"):
                text = row["evidence"].get("reason") or row["evidence"].get("text") or ""
                cells = (folder.name, f"{row['t']:.1f}", row["frame"], row["class"], row["cause"], text)
                lines.append("| " + " | ".join(str(cell) for cell in cells) + " |")
    lines.append("")
    (directory / "incidents.md").write_text("\n".join(lines))
