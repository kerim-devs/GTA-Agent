"""Tests of the bench on small logs written here, on pictures drawn here, and on a model of the bridge
and the pilot. Nothing in this file talks to a console: `bench_run.bridge` and `bench_run.pilot` are the
only two doors to it, and every test starts with both replaced by functions that fail."""

import ast
import functools
import json
import re
import signal
import subprocess
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import cv2
import numpy as np
import pytest

from pilot import bench, bench_run
from pilot import bench_proofs as proofs
from pilot.bench import CATALOGUE, Capability, P, step
from pilot.contract import Detection

REPO = Path(__file__).resolve().parents[2]
OFFSET = 4000.0  # head rows carry the monotonic clock, the play rows the session's own
REAL_BRIDGE, REAL_PILOT = bench_run.bridge, bench_run.pilot  # the doors, before any test replaces them


@pytest.fixture(autouse=True)
def no_console(monkeypatch):
    """Whatever a test forgets to replace must fail, never reach a console."""

    def refuse(*args, **kwargs):
        raise AssertionError("a test reached for the console")

    monkeypatch.setattr(bench_run, "bridge", refuse)
    monkeypatch.setattr(bench_run, "pilot", refuse)
    monkeypatch.setattr(bench_run, "BRIDGE_URL", "http://127.0.0.1:1")
    monkeypatch.delenv("PS5_HOST", raising=False)
    monkeypatch.setattr(bench, "version", lambda: {"commit": "abc123", "dirty": False})


# ---------------------------------------------------------------- small logs
def at(value):
    """A value that may depend on the second."""
    return value if callable(value) else (lambda t: value)


def running(name, until, status="done", reason="done", first=0.0):
    """A skill that runs from `first` to `until` and then ends with `status`."""

    def skill(t):
        if t < first:
            return None
        if t < until:
            return {"name": name, "status": "running", "reason": None}
        return {"name": name, "status": status, "reason": reason}

    return skill


def write_session(
    folder,
    *,
    seconds=30.0,
    rate=5,
    minimap="flat",
    route="none",
    distance=None,
    skill=None,
    screen="game",
    objective="",
    objects=(),
    judged=None,
    overlay=False,
    opening_failed=(),
    fresh=True,
    health=1.0,
    wanted=0,
    status=200,
):
    """play.jsonl, head.jsonl and judge.jsonl of a session; every field may depend on the second."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    minimap, route, distance, skill = at(minimap), at(route), at(distance), at(skill)
    screen, objective, objects, judged, fresh = at(screen), at(objective), at(objects), at(judged), at(fresh)
    health, wanted, status, overlay = at(health), at(wanted), at(status), at(overlay)
    ticks = [i / rate for i in range(int(seconds * rate) + 1)]
    play = [
        {
            "t": t,
            "fresh": fresh(t),
            "status": status(t),
            "reading": {
                "minimap": minimap(t),
                "route": route(t),
                "gps_distance": distance(t),
                "corrupt": False,
                "blips": [],
            },
            "skill": skill(t),
        }
        for t in ticks
    ]
    head = [
        {
            "id": second,
            "t": OFFSET + second,
            "type": "request",
            "request": {
                "objective": objective(second),
                "hud": {"screen": screen(second), "wanted": wanted(second), "health": health(second)},
                "objects": list(objects(second)),
                "last_skill": skill(second) or {},
            },
        }
        for second in range(int(seconds) + 1)
    ]
    for t, name, reason in opening_failed:
        head.append({"t": OFFSET + t, "type": "opening_failed", "name": name, "reason": reason})
    answers = [
        {"capture": OFFSET + t, "answers": {"mode": {"value": judged(t)}, "overlay": {"value": overlay(t)}}}
        for t in ticks
        if judged(t) is not None
    ]
    for name, rows in (("play", play), ("head", head), ("judge", answers)):
        (folder / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return folder


# ---------------------------------------------------------------- pictures drawn here
NOISE = np.full((720, 1280, 3), 30, np.uint8)
# A map with texture, so that a turn of the camera can be told: values too dim for any purple mask.
NOISE[530:700, 30:290] = np.random.default_rng(7).integers(40, 90, size=(170, 260, 3)).astype(np.uint8)
PURPLE = (160, 60, 220)


def picture(blip=None):
    """A frame whose minimap shows one purple waypoint blip at `blip` = (x right, y up) from the arrow."""
    frame = NOISE.copy()
    if blip is not None:
        x = proofs.HUD_RECT[0] + proofs.ARROW_XY[0] + blip[0]
        y = proofs.HUD_RECT[1] + proofs.ARROW_XY[1] - blip[1]
        cv2.circle(frame, (int(x), int(y)), 5, PURPLE, -1)
    return frame


class Pictured(proofs.Session):
    """A session with pictures drawn by a function of the second and a HUD screen that is one too."""

    def __init__(self, folder, frames, screen=lambda t: "game", detect=None):
        super().__init__(folder, frames=frames, detect=detect)
        self._screen = screen

    def hud_at(self, t):
        return SimpleNamespace(screen=self._screen(t))


def map_open(t):
    return 5 <= t <= 12.5


def foot_waypoint(tmp_path, before, after, *, mode="flat", route="none"):
    """A try on foot that has the map open from 5 s to 12.5 s. The picture before shows a waypoint blip
    at `before`, the picture after at `after` (None for none); no route line is ever drawn."""
    folder = write_session(
        tmp_path / "waypoint",
        minimap=lambda t: "none" if 5 <= t <= 12 else mode,
        route=route,
        skill=running("set_waypoint", 13, reason="waypoint set"),
        screen=lambda t: "map" if map_open(t) else "game",
    )
    shown = {"before": picture(before), "after": picture(after), "map": picture()}
    session = Pictured(
        folder,
        lambda t: shown["before"] if t < 5 else shown["after"] if t > 12.5 else shown["map"],
        screen=lambda t: "map" if map_open(t) else "game",
    )
    return session, proofs.Try(session, ("set_waypoint",), ("set_waypoint",))


def waypoint_try(folder, **kwargs):
    session = proofs.Session(write_session(folder, rate=10, **kwargs))
    return proofs.Try(session, ("set_waypoint",), ("set_waypoint",))


# ---------------------------------------------------------------- the outcome table
@pytest.mark.parametrize(
    "skill,proof,expected",
    [
        (True, True, ("ok", None)),
        (True, False, ("failed", "proof")),
        (False, True, ("failed", "proof")),
        (False, False, ("failed", None)),
        (None, True, ("not_counted", None)),
        (True, None, ("not_counted", None)),
        (False, None, ("not_counted", None)),
    ],
)
def test_outcome_table(skill, proof, expected):
    assert bench.outcome(skill, proof) == expected


def leave_session(tmp_path, *, name="leave", skill_ok=True, reason="done", ends="flat", **extra):
    return write_session(
        tmp_path / name,
        seconds=16,
        minimap=lambda t: "tilted" if t < 2 or ends == "tilted" else "flat",
        skill=running("press", 1.5, status="done" if skill_ok else "failed", reason=reason),
        **extra,
    )


def test_judge_reads_the_proof_apart_from_the_skills_word(tmp_path):
    ok = bench.judge(leave_session(tmp_path, name="a"), "car.leave")
    assert (ok["outcome"], ok["cause"]) == ("ok", None)
    # the skill says done and the figure still sits in the vehicle: its word is not taken
    liar = bench.judge(leave_session(tmp_path, name="b", ends="tilted"), "car.leave")
    assert (liar["outcome"], liar["cause"]) == ("failed", "proof")
    assert liar["moment"]["how"].startswith("proof:")
    # the skill says failed and the figure stands on foot
    modest = bench.judge(leave_session(tmp_path, name="c", skill_ok=False, reason="blocked"), "car.leave")
    assert (modest["outcome"], modest["cause"]) == ("failed", "proof")
    both = bench.judge(
        leave_session(tmp_path, name="d", skill_ok=False, reason="blocked", ends="tilted"), "car.leave"
    )
    assert (both["outcome"], both["cause"]) == ("failed", "act")


def test_a_try_that_did_not_start_in_its_state_is_not_counted(tmp_path):
    # on foot all along: car.leave needs a vehicle
    folder = write_session(tmp_path / "wrong", seconds=16, minimap="flat", skill=running("press", 1.5))
    row = bench.judge(folder, "car.leave")
    assert row["outcome"] == "not_counted"
    assert "start state not established" in row["exclusion"] and "vehicle no" in row["exclusion"]


def test_a_start_the_minimap_and_the_judge_disagree_on_is_not_counted_and_says_why(tmp_path):
    folder = write_session(
        tmp_path / "split",
        seconds=16,
        minimap=lambda t: "tilted" if t < 2 else "flat",
        judged="foot",
        skill=running("press", 1.5),
    )
    row = bench.judge(folder, "car.leave")
    assert row["outcome"] == "not_counted"
    assert "vehicle unclear" in row["exclusion"] and "do not agree" in row["exclusion"]


def test_a_session_without_ticks_is_not_counted(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    row = bench.judge(folder, "car.leave")
    assert row["outcome"] == "not_counted" and row["exclusion"] == "no ticks in play.jsonl"


# ---------------------------------------------------------------- the mode of the figure
def seated_share(tenths):
    """The minimap says tilted on `tenths` of every ten ticks."""
    return lambda t: "tilted" if round(t * 5) % 10 < tenths else "flat"


def test_mode_is_a_majority_of_a_stretch_and_a_mixed_stretch_says_nothing(tmp_path):
    nine = proofs.Session(write_session(tmp_path / "nine", minimap=seated_share(9)))
    assert nine.mode_over(10, 20).mode == "vehicle"
    seven = proofs.Session(write_session(tmp_path / "seven", minimap=seated_share(7)))
    mode = seven.mode_over(10, 20)
    assert (mode.mode, mode.why) == (None, "mixed")
    thin = proofs.Session(write_session(tmp_path / "thin", minimap="tilted"))
    assert thin.mode_over(10, 10.5).why == "too-few"  # three ticks


def test_mode_needs_the_judge_to_agree_where_the_judge_answered(tmp_path):
    conflict = proofs.Session(write_session(tmp_path / "c", minimap="tilted", judged="foot"))
    mode = conflict.mode_over(10, 20)
    assert (mode.mode, mode.why) == (None, "conflict")
    agree = proofs.Session(write_session(tmp_path / "a", minimap="tilted", judged="vehicle"))
    assert (agree.mode_over(10, 20).mode, agree.mode_over(10, 20).why) == ("vehicle", "agree")


def test_a_flat_minimap_that_reads_tilted_for_seconds_is_not_taken_for_a_vehicle(tmp_path):
    # bright ground made the reader say tilted for a few seconds; the judge saw the figure on foot
    folder = write_session(
        tmp_path / "bright", minimap=lambda t: "tilted" if 10 <= t < 14 else "flat", judged="foot"
    )
    session = proofs.Session(folder)
    assert session.mode_over(10, 14).mode is None
    assert session.mode_over(16, 20).mode == "foot"


# ---------------------------------------------------------------- a waypoint is proved by its blip
BLIP_A, BLIP_B = (40, 30), (-55, 25)


def test_a_waypoint_on_foot_is_a_new_blip_and_no_route_line_is_asked_for(tmp_path):
    session, run = foot_waypoint(tmp_path, None, BLIP_A)
    found = proofs.waypoint_changed(run)
    assert found.ok is True
    assert found.numbers["blip_before_share"] == 0.0 and found.numbers["blip_after_share"] == 1.0
    assert all(r["reading"]["route"] == "none" for r in session.play)  # nothing a route proof could use


def test_a_waypoint_on_foot_that_stands_elsewhere_counts_and_the_same_place_does_not(tmp_path):
    _, run = foot_waypoint(tmp_path / "moved", BLIP_A, BLIP_B)
    assert proofs.waypoint_changed(run).ok is True
    _, run = foot_waypoint(tmp_path / "same", BLIP_A, BLIP_A)
    found = proofs.waypoint_changed(run)
    assert found.ok is None and "stands where it stood" in found.missing


def test_a_waypoint_on_foot_that_vanished_is_a_no_at_the_second_of_the_last_look(tmp_path):
    _, run = foot_waypoint(tmp_path, BLIP_A, None)
    found = proofs.waypoint_changed(run)
    assert found.ok is False
    assert found.moment[0] > 13 and "no waypoint blip" in found.moment[1]


def test_a_waypoint_where_no_map_or_menu_opened_is_a_no(tmp_path):
    folder = write_session(tmp_path / "never", skill=running("set_waypoint", 13))
    session = Pictured(folder, lambda t: picture())
    found = proofs.waypoint_changed(proofs.Try(session, ("set_waypoint",), ("set_waypoint",)))
    assert found.ok is False and "no map or menu opened" in found.moment[1]


def test_a_waypoint_on_foot_without_video_is_not_measurable(tmp_path):
    found = proofs.waypoint_changed(waypoint_try(tmp_path / "bare", skill=running("set_waypoint", 13)))
    assert found.ok is None and "no video" in found.missing


def test_a_waypoint_seated_is_proved_by_the_route_line(tmp_path):
    new = waypoint_try(
        tmp_path / "new",
        minimap="tilted",
        route=lambda t: "purple" if t > 15 else "none",
        skill=running("set_waypoint", 18),
    )
    assert proofs.waypoint_changed(new).ok is True
    none = waypoint_try(tmp_path / "none", minimap="tilted", skill=running("set_waypoint", 18))
    found = proofs.waypoint_changed(none)
    assert found.ok is False and found.moment[1] == "no route on the minimap at the end, seated"
    same = waypoint_try(
        tmp_path / "same", minimap="tilted", route="purple", distance=400, skill=running("set_waypoint", 18)
    )
    assert proofs.waypoint_changed(same).ok is None  # a route stood already at the same distance
    other = waypoint_try(
        tmp_path / "other",
        minimap="tilted",
        route="purple",
        distance=lambda t: 400 if t < 8 else 900,
        skill=running("set_waypoint", 18),
    )
    assert proofs.waypoint_changed(other).ok is True
    thin = waypoint_try(
        tmp_path / "thin",
        minimap=lambda t: "none" if t < 3 else "tilted",
        route=lambda t: "purple" if t > 15 else "none",
        skill=running("set_waypoint", 18),
    )
    assert proofs.waypoint_changed(thin).ok is None  # the minimap was hidden at the start: no "before"


def test_a_waypoint_in_a_mixed_mode_is_not_measurable(tmp_path):
    folder = write_session(
        tmp_path / "mixed",
        minimap=lambda t: "none" if 5 <= t <= 12 else seated_share(5)(t),
        skill=running("set_waypoint", 13),
    )
    session = Pictured(folder, lambda t: picture(), screen=lambda t: "map" if map_open(t) else "game")
    found = proofs.waypoint_changed(proofs.Try(session, ("set_waypoint",), ("set_waypoint",)))
    assert found.ok is None and "not clear" in found.missing


def test_a_blip_that_a_turn_of_the_camera_explains_is_no_change(tmp_path):
    # the same place after the minimap turned by 10 degrees: the rim blip moved by about 12 px
    center = (proofs.HUD_RECT[0] + proofs.ARROW_XY[0], proofs.HUD_RECT[1] + proofs.ARROW_XY[1])
    turned = cv2.warpAffine(NOISE, cv2.getRotationMatrix2D(center, 10, 1.0), (1280, 720))
    cv2.circle(turned, (center[0] + 64, center[1] - 10), 5, PURPLE, -1)
    before = picture((60, 0))
    folder = write_session(
        tmp_path / "turn",
        minimap=lambda t: "none" if 5 <= t <= 12 else "flat",
        skill=running("set_waypoint", 13),
    )
    session = Pictured(
        folder, lambda t: before if t < 5 else turned, screen=lambda t: "map" if map_open(t) else "game"
    )
    found = proofs.waypoint_changed(proofs.Try(session, ("set_waypoint",), ("set_waypoint",)))
    assert found.ok is None and "turn of the camera" in found.missing


def test_a_false_success_of_the_skill_is_a_failed_proof_and_a_true_one_is_ok(tmp_path):
    # the known case: the skill said done, a second press had removed the waypoint again
    session, _ = foot_waypoint(tmp_path / "lost", BLIP_A, None)
    row = bench.judge(session.folder, "map.place", session=session)
    assert (row["outcome"], row["cause"]) == ("failed", "proof")
    assert row["moment"]["how"].startswith("proof:")
    session, _ = foot_waypoint(tmp_path / "set", None, BLIP_A)
    assert bench.judge(session.folder, "map.place", session=session)["outcome"] == "ok"


def test_the_purple_reader_finds_a_blip_and_leaves_a_route_line_alone():
    found = proofs.purple_blips(picture(BLIP_A))
    assert len(found) == 1 and found[0] == pytest.approx(BLIP_A, abs=0.6)
    line = picture()
    cv2.line(line, (100, 640), (250, 600), PURPLE, 3)  # long and thin: a route
    assert proofs.purple_blips(line) == []


# ---------------------------------------------------------------- the far view
FAR_BOX, MIDDLE_BOX = (590, 400, 650, 600), (570, 360, 670, 670)


def view_session(tmp_path, *, name="view", at_end="far", skill=None, opening_failed=(), video=True):
    folder = write_session(tmp_path / name, seconds=45, skill=skill, opening_failed=opening_failed)
    marks = {"far": np.zeros((720, 1280, 3), np.uint8), "middle": np.ones((720, 1280, 3), np.uint8)}

    def detect(frame):
        return (), Detection("person", FAR_BOX if frame[0, 0, 0] == 0 else MIDDLE_BOX, 0.95), None

    return Pictured(folder, (lambda t: marks[at_end]) if video else None, detect=detect)


def test_foot_view_is_ok_when_the_figure_stands_in_the_far_band(tmp_path):
    session = view_session(tmp_path, skill=running("set_far_view", 20))
    row = bench.judge(session.folder, "foot.view", session=session)
    assert (row["outcome"], row["cause"]) == ("ok", None)


def test_foot_view_done_by_the_skill_and_middle_in_the_picture_is_a_failed_proof(tmp_path):
    session = view_session(tmp_path, at_end="middle", skill=running("set_far_view", 20))
    row = bench.judge(session.folder, "foot.view", session=session)
    assert (row["outcome"], row["cause"]) == ("failed", "proof")
    assert "middle" in row["moment"]["how"]


def test_foot_view_failed_in_the_opening_is_read_from_head_jsonl_and_is_see_where_it_was_far(tmp_path):
    # the owner's reading: the skill could not tell the view although the figure stood in the far one
    session = view_session(
        tmp_path, opening_failed=[(30.0, "set_far_view", "view-unknown; last=unknown; presses=5")]
    )
    assert [f["name"] for f in session.opening_failures] == ["set_far_view"]
    row = bench.judge(session.folder, "foot.view", session=session)
    assert (row["outcome"], row["cause"]) == ("failed", "see")
    assert row["skill_reason"].startswith("view-unknown")
    assert "far view stood from here" in row["moment"]["how"] and row["moment"]["t"] < 30


def test_foot_view_failed_in_the_opening_and_not_far_is_the_reasons_own_cause(tmp_path):
    session = view_session(
        tmp_path,
        at_end="middle",
        opening_failed=[(30.0, "set_far_view", "five-presses; last=middle; presses=5")],
    )
    row = bench.judge(session.folder, "foot.view", session=session)
    assert (row["outcome"], row["cause"]) == ("failed", "act")


def test_foot_view_without_video_is_not_counted_and_says_what_is_missing(tmp_path):
    session = view_session(tmp_path, skill=running("set_far_view", 20), video=False)
    row = bench.judge(session.folder, "foot.view", session=session)
    assert row["outcome"] == "not_counted" and "no video" in row["proof"]["missing"]


# ---------------------------------------------------------------- the causes
@pytest.mark.parametrize(
    "reason,cause",
    [
        ("view-unknown; last=unknown; presses=5", "see"),
        ("no-figure; last=none; presses=2", "see"),
        ("hud-unread; last=far; presses=1", "see"),
        ("place-not-in-legend:ANDY", "see"),
        ("not-on-foot; last=far; presses=0", "decide"),
        ("rider; last=far; presses=0", "decide"),
        ("replaced", "decide"),
        ("existing-waypoint-at-target", "decide"),
        ("five-presses; last=middle; presses=5", "act"),
        ("map-did-not-open", "act"),
        ("cursor-move-limit", "act"),
        ("screen-menu; last=far; presses=1", "world"),
        ("death_or_arrest", "world"),
        ("invalid-clock; last=far; presses=1", "tech"),
        ("no-detections; last=unknown; presses=3", "tech"),
        ("skill-error:ValueError", "tech"),
    ],
)
def test_reason_to_cause(reason, cause):
    assert bench.reason_rule(reason) == (True, cause)


def test_reasons_that_do_not_say_whose_fault_are_known_and_left_to_the_log():
    for reason in ("time-limit; last=far; presses=5", "route-gone", "arrived", "entered vehicle"):
        assert bench.reason_rule(reason) == (True, None)
    assert bench.reason_rule("a reason nobody wrote") == (False, None)


NOT_TERMINAL = {
    "flow",  # conductor: the flow reader's pad, no end
    "carry-on",  # conductor: the carry-on touch, no end
    "guard",  # conductor: the guard's pad, no end
    "vehicle found",  # vehicle_entry: stops its walk along the road, not itself
    "touching the camera for the game's own view",  # walk_to_point: its first half second, no end
    "stepping off the carriageway",  # walk_to_point: its last steps, no end
    "turning the camera to the target",  # walk_to_point: before its first step, no end
}
# camera.read_view's reasons name one look at one detection; a skill ends on the view it last had
READINGS = {
    "between-bands",
    "figure-off-place",
    "invalid-box",
    "invalid-frame",
    "second-person",
    "uncalibrated-mode:",
    "uncertain-figure",
}


def reasons_in_the_code(only=None):
    """Every string a skill of the pilot ends or stops on: `reason=` of any call, the first argument of
    `fail`, `_fail` and `stop`, the second of `_finish`; for an f-string its fixed beginning."""
    found = {}
    for path in sorted((REPO / "pilot" / "src" / "pilot").glob("*.py")):
        if path.stem.startswith("bench") or path.stem == "calibrate" or (only and path.name != only):
            continue  # calibrate's "reasons" are the status of a measurement, not the end of a skill
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            candidates = [kw.value for kw in node.keywords if kw.arg == "reason"]
            if name in ("fail", "_fail", "stop") and node.args:
                candidates.append(node.args[0])
            if name == "_finish" and len(node.args) > 1:
                candidates.append(node.args[1])
            for candidate in candidates:
                text = None
                if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
                    text = candidate.value
                elif isinstance(candidate, ast.JoinedStr) and candidate.values:
                    first = candidate.values[0]
                    text = first.value if isinstance(first, ast.Constant) else None
                if text:
                    found.setdefault(text, []).append(f"{path.name}:{node.lineno}")
    return found


def test_every_reason_a_skill_can_end_on_has_a_rule():
    found = reasons_in_the_code()
    assert len(found) > 50  # the scan does find the skills' reasons
    unknown = {
        reason: where
        for reason, where in found.items()
        if reason not in NOT_TERMINAL | READINGS and not bench.reason_rule(reason)[0]
    }
    assert not unknown, f"add a rule to bench.CAUSE_RULES for: {unknown}"


def test_every_reason_of_set_far_view_is_mapped_where_the_code_ends_on_it():
    source = ast.parse((REPO / "pilot" / "src" / "pilot" / "camera.py").read_text())
    unsafe = next(n for n in ast.walk(source) if isinstance(n, ast.FunctionDef) and n.name == "_unsafe")
    whys = {"time-limit", "no-detections", "no-figure", "view-unknown", "five-presses"}
    for node in ast.walk(unsafe):  # `_fail(unsafe)` ends on what `_unsafe` returns
        if isinstance(node, ast.Return) and isinstance(node.value, (ast.Constant, ast.JoinedStr)):
            value = node.value
            text = value.value if isinstance(value, ast.Constant) else value.values[0].value
            if text:
                whys.add(text)
    assert {"hud-unread", "screen-", "not-on-foot", "rider"} <= whys
    assert whys >= set(reasons_in_the_code("camera.py")) - READINGS - {"invalid-clock", "far; presses="}
    for why in whys | {"invalid-clock"}:
        assert bench.reason_rule(f"{why}; last=far; presses=3")[0], why
    assert bench.reason_rule("invalid-clock")[0]


def failed_press(tmp_path, name, **extra):
    return write_session(
        tmp_path / name,
        seconds=16,
        minimap="tilted",
        skill=running("press", 1.5, status="failed", reason="blocked"),
        **extra,
    )


def test_a_failure_is_tech_for_stale_frames_and_errors_and_world_for_health_and_stars(tmp_path):
    stale = failed_press(tmp_path, "stale", fresh=lambda t: not 4 <= t < 7)
    assert bench.judge(stale, "car.leave")["cause"] == "tech"
    errors = failed_press(tmp_path, "errors", status=lambda t: 503 if t > 5 else 200)
    assert bench.judge(errors, "car.leave")["cause"] == "tech"
    hurt = failed_press(tmp_path, "hurt", health=lambda t: 1.0 if t < 3 else 0.5)
    assert bench.judge(hurt, "car.leave")["cause"] == "world"
    stars = failed_press(tmp_path, "stars", wanted=lambda t: 2 if t > 3 else 0)
    assert bench.judge(stars, "car.leave")["cause"] == "world"
    plain = failed_press(tmp_path, "plain")
    assert bench.judge(plain, "car.leave")["cause"] == "act"  # the reason's own: it was blocked


def test_a_time_limit_is_told_by_the_log_and_a_log_that_says_nothing_is_unclear(tmp_path):
    def entering(name, objects):
        folder = write_session(
            tmp_path / name,
            seconds=40,
            skill=running("enter_vehicle", 30, status="failed", reason="time-limit"),
            objects=objects,
        )
        return bench.judge(folder, "foot.enter")

    assert entering("blind", [])["cause"] == "see"  # no vehicle was ever detected
    assert entering("seen", [{"kind": "car", "box": [0, 0, 1, 1]}])["cause"] == "act"

    def following(name, distance):
        folder = write_session(
            tmp_path / name,
            seconds=40,
            minimap="tilted",
            route="purple",
            distance=distance,
            skill=running("drive_route", 35, status="failed", reason="time-limit"),
        )
        return bench.judge(folder, "car.follow")

    assert following("nearer", lambda t: 500 - 2 * t)["cause"] == "act"  # approached, not there
    assert following("still", 500)["cause"] == "decide"  # never moved
    unread = write_session(
        tmp_path / "unread",
        seconds=40,
        minimap="tilted",
        route="purple",
        skill=running("drive_route", 35, status="failed", reason="time-limit"),
    )
    assert bench.judge(unread, "car.follow")["outcome"] == "not_counted"  # no distance, no proof


# ---------------------------------------------------------------- the ledger, the marks, the board
def row(capability="car.leave", outcome="ok", cause=None, reason="done", session="/s/1", **extra):
    base = {
        "capability": capability,
        "time": "2026-11-12T12:00:00+00:00",
        "commit": "abc",
        "dirty": False,
        "session": session,
        "start_state": {"held": True, "observed": {}},
        "outcome": outcome,
        "cause": cause,
        "skill_reason": reason,
        "skill_ok": outcome == "ok",
        "seconds": 5.0,
        "proof": {"ok": outcome == "ok", "numbers": {}, "missing": "", "parts": {}, "partial": False},
        "objective": {"on_screen": None, "text": ""},
        "exclusion": "",
    }
    return {**base, **extra}


def test_the_board_counts_the_last_ten_and_ranks_what_to_repair_by_count():
    rows = [row(session=f"/s/{i}") for i in range(7)]
    rows += [
        row(outcome="failed", cause="see", reason="view-unknown; last=x", session=f"/f/{i}") for i in range(3)
    ]
    rows += [row("car.follow", "failed", "act", "blocked", session="/c/1")]
    rows += [row("car.follow", "not_counted", None, "done", session="/c/2")]
    data = bench.board_data(rows)
    leave = next(c for c in data["capabilities"] if c["id"] == "car.leave")
    assert leave["last10"] == [7, 10] and leave["state"] == "red"  # 7 of 10 is under the mark of 9
    assert leave["causes"] == {"see": 3}
    follow = next(c for c in data["capabilities"] if c["id"] == "car.follow")
    assert follow["excluded"] == 1 and follow["all"] == [0, 1]
    assert data["ranking"][0] == {
        "capability": "car.leave",
        "cause": "see",
        "reason": "view-unknown",
        "count": 3,
    }
    assert data["ranking"][1]["count"] == 1
    assert data["unclear"] == 0 and data["failures"] == 4


def test_the_board_names_what_is_not_built_not_measurable_and_too_few():
    states = {
        c["id"]: c["state"]
        for c in bench.board_data([row(session=f"/s/{i}") for i in range(3)])["capabilities"]
    }
    assert states["foot.roadside"] == "not built"
    assert states["foot.enter"] == "not measurable"  # a part of its card that no log can show
    assert states["car.leave"] == "too few tries"


def test_a_mark_overrules_on_the_board_and_never_touches_the_ledger(tmp_path):
    ledger = tmp_path / "bench.jsonl"
    session = str((tmp_path / "s1").resolve())
    bench.append(ledger, row(outcome="failed", cause="proof", session=session))
    before = ledger.read_bytes()
    arguments = [
        "--ledger",
        str(ledger),
        "mark",
        session,
        "--outcome",
        "ok",
        "--note",
        "the picture shows it",
    ]
    assert bench.main(arguments) == 0
    assert ledger.read_bytes() == before
    rows = bench.apply_marks(bench.read_jsonl(ledger), bench.read_jsonl(bench.marks_path(ledger)))
    assert rows[0]["outcome"] == "ok" and rows[0]["marked"] and rows[0]["mark_note"] == "the picture shows it"
    with pytest.raises(SystemExit):  # a failed mark needs its cause
        bench.main(["--ledger", str(ledger), "mark", "x", "--outcome", "failed", "--note", "n"])


def test_a_rejudged_try_counts_once_with_its_newest_row(tmp_path):
    folder = leave_session(tmp_path)
    ledger = tmp_path / "bench.jsonl"
    bench.append(ledger, bench.judge(folder, "car.leave"))
    assert bench.rejudge(ledger) == 1
    lines = bench.read_jsonl(ledger)
    assert len(lines) == 2 and lines[1]["revision"] is True
    assert len(bench.apply_marks(lines, [])) == 1


def test_import_takes_a_list_once_and_a_rebuild_gives_the_same_ledger(tmp_path):
    first = leave_session(tmp_path, name="20261112-100000")
    second = leave_session(tmp_path, name="20261112-100100", ends="tilted")
    source = tmp_path / "basics.tsv"
    source.write_text(f"1\tleave\t{first}\n1\tleave\t{second}\n2\tunknown-step\t{first}\n")
    ledger = tmp_path / "bench.jsonl"
    added = bench.import_basics(source, ledger, harvest_too=False)
    assert [r["outcome"] for r in added] == ["ok", "failed"]
    assert bench.import_basics(source, ledger, harvest_too=False) == []
    again = tmp_path / "again.jsonl"
    bench.import_basics(source, again, harvest_too=False)

    def key(r):
        return (r["capability"], r["session"], r["outcome"], r["cause"])

    assert sorted(map(key, bench.read_jsonl(ledger))) == sorted(map(key, bench.read_jsonl(again)))


def test_harvest_finds_the_moments_of_capabilities_that_cannot_be_staged(tmp_path):
    folder = write_session(
        tmp_path / "drive",
        seconds=20,
        screen=lambda t: "pause" if t == 4 else "wasted" if t == 9 else "game",
        wanted=lambda t: 2 if t == 14 else 0,
    )
    rows = bench.harvest(folder)
    assert {r["capability"] for r in rows} == {"incident.menu", "incident.down", "incident.wanted"}
    assert all(r["outcome"] == "not_counted" and r["event_start"] is not None for r in rows)


def test_the_head_contract_accepts_every_plan_of_the_catalogue():
    from pilot.head import parse_response

    for capability in CATALOGUE.values():
        for number in range(6):
            plan = bench.plan_for(capability, number)
            if plan:
                assert len(parse_response({"plan": list(plan), "sentence": "Bench."}).plan) == len(plan)


# ---------------------------------------------------------------- one entry extends the catalogue
def lights_on_at_end(run, seconds: float = 2.0) -> proofs.Evidence:
    """The test's own piece: the minimap read flat over the last readings."""
    rows = run.session.ticks(run.session.end - seconds, run.session.end)
    flat = sum(r["reading"]["minimap"] == "flat" for r in rows) / max(len(rows), 1)
    moment = None if flat > 0.9 else (run.session.end, "not flat")
    return proofs.Evidence(flat > 0.9, {"flat": flat}, "", moment)


def test_a_catalogue_entry_with_named_proofs_is_all_it_takes(tmp_path, monkeypatch):
    monkeypatch.setitem(proofs.PIECES, "lights_on_at_end", None)  # put back by the monkeypatch
    proofs.piece(lights_on_at_end)  # a new piece is one function with a decorator
    entry = Capability(
        "test.stand",
        "foot",
        "Stand still",
        "Stehen bleiben",
        ("foot",),
        (step("wait", duration=5),),
        10,
        (P("on_foot_at_end"), P("lights_on_at_end", seconds=1.0)),
    )
    monkeypatch.setitem(CATALOGUE, "test.stand", entry)  # and an entry is one line of the catalogue
    row = bench.judge(write_session(tmp_path / "s", seconds=12, skill=running("wait", 5)), "test.stand")
    assert row["outcome"] == "ok"
    assert set(row["proof"]["parts"]) == {"on_foot_at_end", "lights_on_at_end"}
    assert "test's own piece" in entry.describe_proof()
    # the loop, the dry run, the board and the catalogue listing know it without another line
    assert bench_run.resolve(["test.stand"]) == ["test.stand"]
    assert any("test.stand" in line for line in bench_run.plan_lines(["test.stand"], 2, None))
    assert "test.stand" in {c["id"] for c in bench.board_data([row])["capabilities"]}
    assert "test.stand" in bench.catalogue_text()


def test_a_piece_that_does_not_exist_names_the_ones_that_do(tmp_path, monkeypatch):
    entry = Capability(
        "test.bad", "foot", "Bad", "Schlecht", ("foot",), (step("wait", duration=1),), 5, (P("nope"),)
    )
    monkeypatch.setitem(CATALOGUE, "test.bad", entry)
    with pytest.raises(KeyError, match=r"known: .*waypoint_changed"):
        bench.judge(write_session(tmp_path / "s", seconds=6, skill=running("wait", 2)), "test.bad")


def test_pieces_combine_all_yes_any_no_else_not_measurable():
    yes = proofs.Evidence(True)
    no = proofs.Evidence(False, moment=(3.0, "x"))
    unknown = proofs.Evidence(None, missing="m")
    assert proofs.combine([("a", yes), ("b", yes)]).ok is True
    assert proofs.combine([("a", yes), ("b", no), ("c", unknown)]).ok is False
    assert proofs.combine([("a", yes), ("b", unknown)]).ok is None
    assert proofs.combine([("a", yes), ("b", no)]).moment == (3.0, "x")


def test_the_time_to_sit_is_counted_from_the_skills_first_tick_and_not_from_the_sessions(tmp_path):
    # the opening (far view, levelling) takes 25 s before the plan's skill begins; seated 15 s after that
    def entering(name, seats_at):
        return write_session(
            tmp_path / name,
            seconds=60,
            minimap=lambda t: "tilted" if t >= seats_at else "flat",
            skill=running("enter_vehicle", seats_at + 1, reason="entered vehicle", first=25.0),
        )

    quick = proofs.Try(proofs.Session(entering("quick", 40)), ("enter_vehicle",), ("enter_vehicle",))
    found = proofs.seated_within(quick, seconds=20)
    assert found.ok is True and found.numbers["seated_from"] == pytest.approx(15, abs=0.5)
    slow = proofs.Try(proofs.Session(entering("slow", 50)), ("enter_vehicle",), ("enter_vehicle",))
    found = proofs.seated_within(slow, seconds=20)
    assert found.ok is False and found.moment[0] == pytest.approx(45, abs=0.5)  # 20 s after the skill began


def test_an_unmeasured_part_keeps_the_cards_wording_and_a_success_does_not_count(tmp_path):
    entered = write_session(
        tmp_path / "in",
        seconds=40,
        minimap=lambda t: "tilted" if t >= 8 else "flat",
        skill=running("enter_vehicle", 9, reason="entered vehicle"),
    )
    row = bench.judge(entered, "foot.enter")
    assert row["outcome"] == "not_counted" and row["proof"]["partial"] is True
    assert "speed and occupancy of the vehicle" in CATALOGUE["foot.enter"].unmeasured()[0]
    stayed = write_session(
        tmp_path / "out",
        seconds=40,
        skill=running("enter_vehicle", 9, status="failed", reason="time-limit"),
    )
    assert bench.judge(stayed, "foot.enter")["outcome"] == "failed"  # a no of another piece still counts


# ---------------------------------------------------------------- a model of the bridge and the pilot
class Console:
    """The bridge and the pilot, on a clock that moves only when the loop pauses.

    Every try the loop starts becomes a session folder, written when the pilot ends: its minimap follows
    the figure (`mode`), and the plan's first skill says what changes it. `outcomes` lists what happens in
    the tries of a capability, in order: ok, tech (the skill fails on a clock reason), none (a pilot that
    leaves no session behind)."""

    def __init__(self, tmp_path, mode="foot"):
        self.t = 0.0
        self.mode = mode
        self.record_dir = tmp_path / "recordings"
        self.record_dir.mkdir()
        self.human = lambda t: False
        self.down = lambda t: False
        self.recording = lambda t: False
        self.objective = lambda t: ""
        self.outcomes = {}
        self.dies_after = None
        self.starts = []  # (time, command, status at that moment)
        self.pads = []  # (time, path, payload)
        self.interrupted = []
        self.runs = 0
        self.live = None

    def clock(self):
        return self.t

    def pause(self, seconds):
        self.t += seconds

    def now(self):
        return datetime(2026, 11, 12, 12, 0, tzinfo=UTC) + timedelta(seconds=self.t)

    def status(self):
        return {
            "session_up": True,
            "human_input": bool(self.human(self.t)),
            "recording": bool(self.live) or bool(self.recording(self.t)),
        }

    def bridge(self, path="/status", payload=None):
        if self.down(self.t):
            raise OSError("connection refused")
        if payload is not None:
            self.pads.append((self.t, path, payload))
            return {}
        return self.status()

    def pilot(self, action, *, handle=None, command=None, log=None):
        if action == "start":
            self.starts.append((self.t, command, self.status()))
            self.runs += 1
            plan = json.loads(command[command.index("--plan") + 1])
            kind = {"wait": "probe", "press": "leave", "enter_vehicle": "enter"}.get(plan[0]["name"], "other")
            queue = self.outcomes.get({"leave": "car.leave", "enter": "foot.enter"}.get(kind, kind), [])
            self.live = SimpleNamespace(
                began=self.t,
                seconds=float(command[command.index("--seconds") + 1]),
                kind=kind,
                outcome=queue.pop(0) if queue else "ok",
                code=None,
                folder=Path(command[command.index("--record-dir") + 1]),
            )
            Path(log).write_text("pilot output\n")
            return self.live
        if action == "poll":
            if handle.code is not None:
                return handle.code
            if self.dies_after is not None and self.t - handle.began >= self.dies_after:
                return self.finish(handle, 1, self.dies_after)
            if self.t - handle.began >= handle.seconds:
                return self.finish(handle, 0, handle.seconds)
            return None
        if action == "interrupt":
            self.interrupted.append(self.t)
            return self.finish(handle, 0, self.t - handle.began)
        raise AssertionError(action)

    def finish(self, handle, code, lasted):
        handle.code, self.live = code, None
        if handle.outcome != "none":
            write_session(handle.folder / f"20261112-{self.runs:06d}", **self.session_for(handle, lasted))
        if handle.kind == "leave" and handle.outcome == "ok" and lasted >= 1.5:
            self.mode = "foot"
        if handle.kind == "enter" and lasted >= 9:
            self.mode = "vehicle"
        return code

    def session_for(self, handle, lasted):
        begin, tech, began, objective = self.mode, handle.outcome == "tech", handle.began, self.objective
        base = {"seconds": max(lasted, 3.0), "objective": lambda t: objective(began + t)}
        shown = {"foot": "flat", "vehicle": "tilted"}
        if handle.kind == "leave":
            return {
                **base,
                "minimap": lambda t: shown[begin] if t < 2 or tech else "flat",
                "skill": running(
                    "press",
                    1.5,
                    status="failed" if tech else "done",
                    reason="clock-invalid" if tech else "done",
                ),
            }
        if handle.kind == "enter":
            return {
                **base,
                "minimap": lambda t: "flat" if t < 8 else "tilted",
                "skill": running("enter_vehicle", 9, reason="entered vehicle"),
            }
        return {**base, "minimap": shown[begin], "skill": running("wait", 99)}


@pytest.fixture
def console(tmp_path, monkeypatch):
    world = Console(tmp_path)
    monkeypatch.setattr(bench_run, "bridge", world.bridge)
    monkeypatch.setattr(bench_run, "pilot", world.pilot)
    return world


def make_loop(console, base, ids, **kwargs):
    return bench_run.Loop(
        ids,
        base / "ledger" / "bench.jsonl",
        record_dir=console.record_dir,
        clock=console.clock,
        pause=console.pause,
        now=console.now,
        **kwargs,
    )


def ledger_rows(base):
    return [r for r in bench.read_jsonl(base / "ledger" / "bench.jsonl") if r.get("event_start") is None]


def plan_names(console):
    return [json.loads(c[1][c[1].index("--plan") + 1])[0]["name"] for c in console.starts]


# ---------------------------------------------------------------- the loop against the model
def test_a_missing_start_state_is_made_by_the_capability_that_produces_it(console, tmp_path):
    loop = make_loop(console, tmp_path, ["car.leave"], tries=1)
    loop.run()
    assert plan_names(console) == ["wait", "enter_vehicle", "press"]  # the probe, the producer, the try
    rows = ledger_rows(tmp_path)
    assert [(r["capability"], r.get("setup_for")) for r in rows] == [
        ("foot.enter", "car.leave"),
        ("car.leave", None),
    ]
    assert rows[1]["outcome"] == "ok"
    assert loop.stopped_because == "every capability had its tries"


def test_a_person_on_the_controller_ends_the_try_and_it_is_not_counted(console, tmp_path):
    console.mode = "vehicle"
    console.human = lambda t: 12 <= t < 40
    loop = make_loop(console, tmp_path, ["car.leave"], tries=1)
    loop.run()
    assert console.interrupted, "the running pilot was ended"
    cut = next(r for r in ledger_rows(tmp_path) if r.get("interruption"))
    assert cut["interruption"] == "human input" and cut["outcome"] == "not_counted"
    assert "took the controller" in cut["exclusion"]
    assert console.starts[-1][0] >= 40  # started again once the person was gone
    last = [r for r in ledger_rows(tmp_path) if r["capability"] == "car.leave"][-1]
    assert last["outcome"] == "ok" and not last.get("interruption")
    assert loop.done["car.leave"] == 1  # the cut try did not count toward the tries


@pytest.mark.parametrize(
    "status,waiting",
    [
        ({"session_up": False, "recording": False, "human_input": False}, "the session is not up"),
        ({"session_up": True, "recording": True, "human_input": False}, "a recording runs"),
        ({"session_up": True, "recording": False, "human_input": True}, "a person is on the controller"),
        ({"session_up": True, "human_input": False}, "recording is not reported"),
        ({"session_up": True, "recording": False}, "human_input is not reported"),
        ([], "the bridge's answer is not a status"),
    ],
)
def test_a_try_starts_only_when_the_bridge_says_it_may(status, waiting):
    assert bench_run.clear(status) is False
    assert bench_run.waiting_for(status) == waiting
    assert bench_run.clear({"session_up": True, "human_input": False, "recording": False}) is True


def test_the_pilot_is_never_started_while_the_bridge_is_unclear(console, tmp_path):
    console.mode = "vehicle"
    console.recording = lambda t: t < 30
    console.human = lambda t: 30 <= t < 45
    loop = make_loop(console, tmp_path, ["car.leave"], tries=1)
    loop.run()
    assert console.starts and all(bench_run.clear(status) for _, _, status in console.starts)
    assert console.starts[0][0] >= 45 and console.pads[0][0] >= 45  # not even the small push before


def test_a_bridge_that_does_not_answer_is_waited_out_and_reported_apart(console, tmp_path):
    console.mode = "vehicle"
    console.down = lambda t: t < 60
    loop = make_loop(console, tmp_path, ["car.leave"], tries=1)
    loop.run()
    assert console.starts[0][0] >= 60
    assert [e["where"] for e in loop.errors] == ["bridge"]  # once, not once per poll
    assert [r["outcome"] for r in ledger_rows(tmp_path)] == ["ok"]
    report = (loop.run_dir / "report.md").read_text()
    assert "Problems of the loop itself" in report and "connection refused" in report


def test_a_bridge_that_goes_silent_during_a_try_ends_the_try_and_the_loop_goes_on(console, tmp_path):
    console.down = lambda t: 20 <= t < 80  # foot.enter runs for 53 s, so the bridge is gone for ten of them
    loop = make_loop(console, tmp_path, ["foot.enter"], tries=1)
    loop.run()
    rows = ledger_rows(tmp_path)
    cut = [r for r in rows if r.get("interruption") == "bridge not answering"]
    assert cut and cut[0]["outcome"] == "not_counted" and console.interrupted
    assert "bridge stopped answering" in cut[0]["exclusion"]
    assert console.starts[-1][0] >= 80 and len(rows) >= 2  # went on once the bridge answered again


def test_a_pilot_that_dies_is_a_problem_of_the_loop_and_the_run_ends_on_its_own_account(console, tmp_path):
    console.mode = "vehicle"
    console.dies_after = 4.0
    loop = make_loop(console, tmp_path, ["car.leave"], tries=2)
    loop.run()
    assert any(e["where"] == "pilot" and "exit code 1" in e["error"] for e in loop.errors)
    # the producer dies every time, so the capability that needs its state is left be, not retried forever
    assert loop.stopped_because.startswith("what was left could not be tried: car.leave")
    assert (loop.run_dir / "report.md").exists()


def test_a_pilot_that_leaves_no_session_is_reported_and_three_in_a_row_stop_the_loop(console, tmp_path):
    console.mode = "vehicle"
    console.outcomes = {"car.leave": ["none", "ok"]}
    loop = make_loop(console, tmp_path, ["car.leave"], tries=1)
    loop.run()
    assert [e["where"] for e in loop.errors] == ["session"]
    assert [r["outcome"] for r in ledger_rows(tmp_path)] == ["ok"]
    console.outcomes = {"car.leave": ["none"] * 9}
    other = make_loop(console, tmp_path / "other", ["car.leave"], tries=5)
    other.run()
    assert other.stopped_because == "3 tries in a row left no session folder; the loop stops."


def test_a_capability_whose_start_state_cannot_be_made_is_left_be_after_three_skips(console, tmp_path):
    console.mode = "vehicle"
    # foot.walk_to needs a yellow blip, which nothing in the catalogue makes
    loop = make_loop(console, tmp_path, ["foot.walk_to", "car.leave"], tries=4)
    loop.run()
    assert "foot.walk_to" in loop.given_up and loop.done["car.leave"] == 4
    assert loop.stopped_because.startswith("what was left could not be tried: foot.walk_to")
    assert [
        (s["capability"], s["times"])
        for s in json.loads((loop.run_dir / "report.json").read_text())["skipped"]
    ] == [("foot.walk_to", 3)]


def test_three_technical_failures_in_a_row_stop_the_loop(console, tmp_path):
    console.mode = "vehicle"
    console.outcomes = {"car.leave": ["tech"] * 5}
    loop = make_loop(console, tmp_path, ["car.leave"], tries=10)
    summary = loop.run()
    rows = ledger_rows(tmp_path)
    assert [(r["outcome"], r["cause"]) for r in rows] == [("failed", "tech")] * 3
    assert loop.stopped_because.startswith("car.leave: three tries in a row failed for a technical cause")
    assert "worst capability car.leave" in summary and "most frequent cause `tech`" in summary


def test_an_error_of_the_loop_is_reported_with_its_traceback_and_does_not_end_the_run(
    console, tmp_path, monkeypatch
):
    console.mode = "vehicle"
    real, calls = bench.judge, []

    def broken(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("judging broke")
        return real(*args, **kwargs)

    monkeypatch.setattr(bench, "judge", broken)
    loop = make_loop(console, tmp_path, ["car.leave"], tries=1)
    loop.run()
    assert len(loop.errors) == 1 and "RuntimeError: judging broke" in loop.errors[0]["error"]
    assert "Traceback" in loop.errors[0]["traceback"] and "in broken" in loop.errors[0]["traceback"]
    assert ledger_rows(tmp_path)[-1]["outcome"] == "ok"
    assert "judging broke" in (loop.run_dir / "report.md").read_text().split("## Failures")[0]


def test_an_error_of_the_loop_five_times_in_a_row_stops_it(console, tmp_path, monkeypatch):
    console.mode = "vehicle"

    def broken(*args, **kwargs):
        raise RuntimeError("always")

    monkeypatch.setattr(bench, "judge", broken)
    loop = make_loop(console, tmp_path, ["car.leave"], tries=10)
    loop.run()
    assert loop.stopped_because == "the loop itself failed 5 times in a row; it stops."
    assert len(loop.errors) == 5


def test_the_mission_guard_is_off_by_default_and_waits_for_the_objective_when_asked(console, tmp_path):
    console.mode = "vehicle"
    console.objective = lambda t: "Follow Franklin" if t < 100 else ""
    free = make_loop(console, tmp_path / "free", ["car.leave"], tries=1)
    assert free.guard_mission is False
    free.run()
    assert console.starts[1][0] < 100  # it played inside the mission
    row = ledger_rows(tmp_path / "free")[0]
    assert row["objective"]["on_screen"] is True and row["objective"]["text"] == "Follow Franklin"
    console.t, console.mode, console.starts = 0.0, "vehicle", []
    guarded = make_loop(console, tmp_path / "guard", ["car.leave"], tries=1, guard_mission=True)
    guarded.run()
    assert console.starts[-1][0] >= 100  # it waited for the objective to go
    assert ledger_rows(tmp_path / "guard")[0]["objective"]["on_screen"] is False


def test_the_minutes_bound_the_run_and_no_try_starts_that_cannot_end_in_them(console, tmp_path):
    console.mode = "vehicle"
    loop = make_loop(console, tmp_path, ["car.leave", "foot.enter"], tries=10, minutes=2)
    loop.run()
    assert loop.stopped_because.startswith("the minutes were used up")
    assert console.t <= 2 * 60 + 1
    assert not loop.errors  # running out of minutes is no problem of the loop


def test_a_small_push_of_the_right_stick_comes_before_every_try(console, tmp_path):
    console.mode = "vehicle"
    loop = make_loop(console, tmp_path, ["car.leave"], tries=1)
    loop.run()
    for began, _, _ in console.starts:
        before = [p for p in console.pads if p[0] <= began]
        assert before and before[-1][2]["right"] == [0, 0]  # the stick was let go again
        push = next(p for p in reversed(before) if p[2]["right"] == [0.5, 0.0])
        assert push[1] == "/pad" and push[2]["ttl_ms"] <= 500 and push[0] < began


def test_the_status_file_says_what_the_loop_does_and_lies_beside_the_ledger(console, tmp_path):
    console.mode = "vehicle"
    loop = make_loop(console, tmp_path, ["car.leave"], tries=1)
    loop.run()
    status = json.loads((tmp_path / "ledger" / "bench.status.json").read_text())
    assert status["state"].startswith("finished") and status["run"] == loop.run_id
    assert status["tries_done"] == 1 and status["report"].endswith("report.md")
    assert {"since", "updated", "capability", "minutes_left", "last_line", "pid"} <= set(status)


def test_the_report_has_every_section_a_pointer_per_failure_and_ends_on_the_summary(console, tmp_path):
    console.mode = "vehicle"
    console.outcomes = {"car.leave": ["tech", "ok"]}
    loop = make_loop(console, tmp_path, ["car.leave", "foot.enter"], tries=2)
    loop.run()
    text = (loop.run_dir / "report.md").read_text()
    for heading in (
        "## What was planned",
        "## What ran",
        "## What was skipped, and why",
        "## Problems of the loop itself (not failures of the pilot)",
        "## The board before and after",
        "## Failures, each with where to look",
    ):
        assert heading in text
    data = json.loads((loop.run_dir / "report.json").read_text())
    assert data["summary"] == text.rstrip().splitlines()[-1]
    assert data["board_before"] != data["board_after"]
    failure = data["failures"][0]
    wanted = {"capability", "cause", "skill_reason", "session", "second", "how_found", "readers_said"}
    assert wanted | {"proof_saw", "picture", "look_first"} <= set(failure)
    assert failure["capability"] == "car.leave" and failure["cause"] == "tech"
    assert failure["look_first"].startswith("Look first at ") and "video.mp4" in failure["look_first"]
    assert failure["readers_said"]["skill"]["reason"] == "clock-invalid"


def test_a_failure_with_a_video_gets_the_picture_of_its_second(console, tmp_path, monkeypatch):
    console.mode = "vehicle"
    console.outcomes = {"car.leave": ["tech"]}
    monkeypatch.setattr(proofs.Session, "frame", lambda self, t: picture(BLIP_A))
    loop = make_loop(console, tmp_path, ["car.leave"], tries=1)
    loop.run()
    pointer = loop.pointers[0]
    assert pointer["picture"] and (loop.run_dir / pointer["picture"]).stat().st_size > 1000


def test_the_command_runs_the_loop_with_its_flags_and_names_the_report(
    console, tmp_path, monkeypatch, capsys
):
    console.mode = "vehicle"
    monkeypatch.setattr(
        bench_run,
        "Loop",
        functools.partial(bench_run.Loop, clock=console.clock, pause=console.pause, now=console.now),
    )
    ledger = tmp_path / "ledger" / "bench.jsonl"
    arguments = ["--ledger", str(ledger), "run", "car.leave", "--tries", "1", "--guard-mission"]
    arguments += ["--record-dir", str(console.record_dir), "--judge", "http://judge.test=model"]
    assert bench.main(arguments) == 0
    out = capsys.readouterr().out
    assert "Report: " in out and out.rstrip().endswith("report.md")
    command = console.starts[-1][1]
    assert command[command.index("--judge") + 1] == "http://judge.test=model"
    assert command[command.index("--record-dir") + 1] == str(console.record_dir)
    assert "mission guard on" in next(Path(ledger.parent / "runs").glob("*/report.md")).read_text()


# ---------------------------------------------------------------- the dry run
def test_the_dry_run_prints_the_plan_and_touches_nothing(tmp_path, capsys):
    ledger = tmp_path / "unwritten" / "bench.jsonl"
    assert bench.main(["--ledger", str(ledger), "run", "all", "--minutes", "30", "--dry"]) == 0
    out = capsys.readouterr().out
    assert "Nothing is touched" in out and "foot.view" in out and "car.arrive" in out
    assert "foot.walk_to is skipped" in out and "made for" in out
    assert not (tmp_path / "unwritten").exists()  # not even the folder
    assert bench.main(["--ledger", str(ledger), "run", "no.such", "--dry"]) == 2
    assert bench.main(["--ledger", str(ledger), "run", "car.free", "--dry"]) == 2  # harvested: no try to run


def test_the_dry_run_follows_the_states_the_entries_leave():
    lines = bench_run.plan_lines(["car.follow"], 1, None, assume="foot")
    steps = [line.split()[1] for line in lines if re.match(r"\s*\d+\.", line)]
    assert steps == ["foot.enter", "map.place", "car.follow"]  # a vehicle, a route, then the try itself
    body = "\n".join(lines[4:])
    assert "made for car.follow" in body
    assert "foot.enter" in "\n".join(bench_run.plan_lines(["car.leave"], 1, None, assume="foot")[4:])
    assert "foot.enter" not in "\n".join(bench_run.plan_lines(["car.leave"], 1, None, assume="vehicle")[4:])


def test_all_means_every_runnable_capability_in_the_order_of_the_chain():
    ids = bench_run.resolve(["all"])
    assert ids.index("foot.view") < ids.index("foot.enter") < ids.index("map.place") < ids.index("car.arrive")
    assert all(CATALOGUE[i].runnable for i in ids)
    assert "foot.roadside" not in ids and "car.free" not in ids  # not built, harvested


# ---------------------------------------------------------------- the command line and the two doors
def test_the_try_command_line_is_the_one_basics_sh_runs(tmp_path):
    text = (REPO / "lab" / "live" / "basics.sh").read_text()
    begin = text.index("env -u PS5_HOST")
    command_text = text[begin : text.index(">/dev/null", begin)]
    script_flags = re.findall(r"--[a-z-]+", command_text)
    assert script_flags == ["--head"] + ["--plan"] * 5 + ["--seconds", "--judge", "--record-dir"]
    assert "-m pilot.cli play $level" in command_text
    judge = re.search(r"^judge=(.*)$", text, re.M).group(1)
    still = re.search(r"^still='(.*)'$", text, re.M).group(1)
    assert judge == bench_run.JUDGE and still == json.dumps(bench_run.STILL)
    command = bench_run.pilot_command(CATALOGUE["map.place"], 0, record_dir=tmp_path)
    assert command[1:4] == ["-m", "pilot.cli", "play"]
    assert [t for t in command if t.startswith("--")] == ["--no-level", *script_flags]
    assert command[command.index("--judge") + 1] == judge
    assert command[command.index("--record-dir") + 1] == str(tmp_path)
    plans = [command[i + 1] for i, token in enumerate(command) if token == "--plan"]
    assert plans[1:] == [still] * 4 and json.loads(plans[0])[0]["name"] == "set_waypoint"
    # `--no-level` only where the map is the subject: basics.sh does it for place and waypoint
    assert re.search(r"\[\[ \$name == place \|\| \$name == waypoint \]\] && level=\(--no-level\)", text)
    assert "--no-level" not in bench_run.pilot_command(CATALOGUE["foot.walk"], 0, record_dir=tmp_path)
    assert "--no-level" not in bench_run.pilot_command(
        CATALOGUE["map.open_close"], 0, record_dir=tmp_path
    ) or (not CATALOGUE["map.open_close"].level)


def test_the_places_vary_from_try_to_try_so_that_no_waypoint_is_set_twice_on_one_place():
    places = [bench.plan_for(CATALOGUE["map.place"], n)[0]["args"]["place"] for n in range(8)]
    assert len(set(places[:4])) == 4 and places[:4] == places[4:]
    instances = [bench.plan_for(CATALOGUE["map.mission"], n)[0]["args"]["instance"] for n in range(3)]
    assert len(set(instances)) == 3


def test_the_pilot_door_starts_without_ps5_host_in_the_pilot_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("PS5_HOST", "10.0.0.5")
    seen = {}

    def popen(command, **kwargs):
        seen.update(command=command, **kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(subprocess, "Popen", popen)
    REAL_PILOT("start", command=["python", "-m", "pilot.cli", "play"], log=tmp_path / "log.txt")
    assert "PS5_HOST" not in seen["env"] and seen["cwd"] == bench_run.PILOT_DIR
    assert seen["command"] == ["python", "-m", "pilot.cli", "play"]


class Process:
    """A process that dies after `survives` signals."""

    def __init__(self, survives):
        self.signals, self.survives = [], survives

    def poll(self):
        return None if len(self.signals) < self.survives else -9

    def send_signal(self, sig):
        self.signals.append(sig)

    def wait(self, timeout):
        if len(self.signals) < self.survives:
            raise subprocess.TimeoutExpired("x", timeout)
        return -self.signals[-1]


def test_the_pilot_door_ends_a_try_with_sigint_and_only_then_with_more():
    polite = Process(survives=1)
    REAL_PILOT("interrupt", handle=polite)
    assert polite.signals == [signal.SIGINT]
    stubborn = Process(survives=3)
    REAL_PILOT("interrupt", handle=stubborn)
    assert stubborn.signals == [signal.SIGINT, signal.SIGTERM, signal.SIGKILL]


class Bridge(BaseHTTPRequestHandler):
    posted: ClassVar[list] = []

    def do_GET(self):
        body = json.dumps({"session_up": True, "human_input": False, "recording": False}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        Bridge.posted.append((self.path, self.headers["Content-Type"], json.loads(self.rfile.read(length))))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


def test_the_bridge_door_reads_the_status_and_posts_pad_states(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), Bridge)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(bench_run, "BRIDGE_URL", f"http://127.0.0.1:{server.server_address[1]}")
        assert bench_run.clear(REAL_BRIDGE()) is True
        REAL_BRIDGE("/pad", {"buttons": ["touchpad"], "ttl_ms": 250})
        assert Bridge.posted == [("/pad", "application/json", {"buttons": ["touchpad"], "ttl_ms": 250})]
    finally:
        server.shutdown()
