"""Tests of the bench's proofs, outcome table, causes, ledger and board on small logs written here and on
pictures drawn here. Nothing in this file talks to a console."""

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from pilot import bench
from pilot import bench_proofs as proofs
from pilot.bench import CATALOGUE, Capability, P, step
from pilot.contract import Detection

REPO = Path(__file__).resolve().parents[2]
OFFSET = 4000.0  # head rows carry the monotonic clock, the play rows the session's own


@pytest.fixture(autouse=True)
def fixed_version(monkeypatch):
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
    "vehicle found",  # vehicle_entry: stops its walk along the road, not itself
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
    # the board and the catalogue listing know it without another line
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
