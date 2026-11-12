"""Walking that gets nowhere: found after about two seconds, never on one tick, freed in bounded,
alternating turns, and released at every end."""

import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from pilot.contract import NEUTRAL_PAD, Answer, Judgment, Observation, Reading
from pilot.foot import FootGuard, WalkRoad, find_road, map_shift
from pilot.head import SkillCall
from pilot.minimap import ACX, ACY
from pilot.motion import map_motion
from pilot.skills import REGISTRY, Skill, SkillRunner

FIXTURES = Path(__file__).parent / "fixtures"
FLAT = Reading("flat", "none", None, None, 0.0, False, 0.9)
DT = 1 / 30
FORWARD = (0.0, -1.0)


def crop(name):
    return cv2.cvtColor(cv2.imread(str(FIXTURES / f"{name}.png")), cv2.COLOR_BGR2RGB)


def frame_with(hud):
    frame = np.zeros((720, 1280, 3), np.uint8)
    frame[530:700, 30:290] = hud
    return frame


def obs(t, *, moving=False, corrupt=False, judgment=None, frame=None, mode=None):
    reading = Reading("flat", "none", None, None, 0.0, corrupt, 0.9)
    return Observation(reading, moving, t, frame=frame, judgment=judgment, mode=mode)


def judged(capture, path):
    return Judgment(capture, {"mode": Answer("foot", 1.0), "path": Answer(path, 0.9)}, {}, 0.25, "test")


def angle_of(stick):
    return math.degrees(math.atan2(stick[0], -stick[1]))


# ------------------------------------------------------------------ the ground under the arrow
def test_the_ground_under_a_walking_figure_moves_and_under_one_at_the_railing_it_does_not():
    still = map_shift(crop("foot_pier_still_a"), crop("foot_pier_still_b"))
    walking = map_shift(crop("foot_pier_walk_a"), crop("foot_pier_walk_b"))
    road = map_shift(crop("foot_road_a"), crop("foot_road_b"))
    assert still is not None and still < FootGuard.STILL_SHIFT
    assert walking is not None and walking > FootGuard.GOING_SHIFT
    assert road is not None and road > FootGuard.GOING_SHIFT


def test_a_camera_turn_is_not_a_step():
    # The map turns about the arrow when the camera turns; the figure has not moved.
    before = crop("foot_pier_walk_a")
    after = before.copy()
    turn = cv2.getRotationMatrix2D((ACX, ACY), 6, 1.0)
    turned = cv2.warpAffine(before, turn, (260, 170), borderMode=cv2.BORDER_REPLICATE)
    after[32:138, 39:209] = turned[32:138, 39:209]
    assert map_motion(before, after) > 1.0  # the plain map motion calls it moving
    shift = map_shift(before, after)
    assert shift is not None and shift < FootGuard.STILL_SHIFT


def test_no_map_says_nothing():
    assert map_shift(np.zeros((170, 260, 3), np.uint8), crop("foot_pier_still_a")) is None
    assert map_shift(None, None) is None


# ------------------------------------------------------------------ roads on the map
def test_a_road_is_found_on_the_map_and_open_water_is_none():
    road = find_road(crop("foot_road_a"))
    assert road is not None and 20 < road.distance < 80
    assert find_road(crop("foot_pier_still_a")) is None
    assert find_road(crop("foot_pier_walk_a")) is None
    assert find_road(np.zeros((170, 260, 3), np.uint8)) is None


# ------------------------------------------------------------------ stuck
def run(guard, seconds, *, start=0.0, want=FORWARD, **kwargs):
    steers = []
    t = start
    while t < start + seconds:
        steers.append((t, guard.step(obs(t, **kwargs), want)))
        t += DT
    return steers


def test_stuck_is_found_after_about_two_seconds():
    guard = FootGuard()
    steers = run(guard, 3.0, moving=False)
    first = next(t for t, steer in steers if steer.state == "escape")
    assert 1.95 <= first <= 2.3
    assert all(steer.left == FORWARD for t, steer in steers if t < first)


def test_walking_is_never_called_stuck_while_the_map_moves_or_cannot_be_read():
    for moving in (True, None):
        guard = FootGuard()
        assert all(steer.state == "go" for _, steer in run(guard, 8.0, moving=moving))


def test_one_odd_tick_decides_nothing():
    guard = FootGuard()
    steers = []
    for i in range(240):
        t = i * DT
        # Nothing readable but one still tick a second.
        steers.append(guard.step(obs(t, moving=False if i % 30 == 0 else None), FORWARD))
    assert all(steer.state == "go" for steer in steers)


def test_a_damaged_tick_is_stood_out_and_decides_nothing():
    guard = FootGuard()
    steers = run(guard, 1.0, moving=None)
    damaged = guard.step(obs(1.0, moving=False, corrupt=True), FORWARD)
    assert damaged.left == (0.0, 0.0) and damaged.state == "odd"
    # A run of damaged ticks reporting a stationary map does not make the figure stuck either.
    for i in range(1, 90):
        assert guard.step(obs(1.0 + i * DT, moving=False, corrupt=True), FORWARD).state == "odd"
    assert all(steer.state == "go" for _, steer in steers)


def test_a_short_push_is_not_stuck():
    guard = FootGuard()
    assert all(steer.state == "go" for _, steer in run(guard, 1.9, moving=False))
    # A released stick starts the clock again.
    guard.step(obs(1.95, moving=False), (0.0, 0.0))
    assert all(steer.state == "go" for _, steer in run(guard, 1.9, start=2.0, moving=False))


def test_ways_round_alternate_grow_and_end_in_a_failure_with_its_reason():
    guard = FootGuard()
    steers = run(guard, 30.0, moving=False)
    escapes = []
    for t, steer in steers:
        if steer.state == "escape" and (not escapes or escapes[-1][0] < t - 2 * DT - 0.0001):
            if not escapes or abs(angle_of(steer.left) - escapes[-1][1]) > 1:
                escapes.append((t, angle_of(steer.left)))
        if steer.failed:
            break
    assert [round(a) for _, a in escapes] == [70, -70, 120, -120]
    failed = [(t, steer) for t, steer in steers if steer.failed]
    assert failed and failed[0][1].failed == "stuck" and failed[0][1].left == (0.0, 0.0)
    # Every way round is a stretch of at most 1.6 s, and the whole of it is bounded.
    assert failed[0][0] < 2.0 + 4 * (FootGuard.ESCAPE_SECONDS + 0.1)


def test_after_a_way_round_the_old_direction_is_tried_again(monkeypatch):
    guard = FootGuard()
    monkeypatch.setattr(guard, "_evidence", lambda observation: "still" if guard.state == "go" else "going")
    # Stuck for two seconds, then the way round walks (the map moves), then the old direction.
    t = 0.0
    states = []
    while t < 6.0:
        state = guard.state
        steer = guard.step(obs(t, moving=False if state == "go" else None), FORWARD)
        states.append((t, steer.state, steer.left))
        t += DT
    back = [left for t, state, left in states if t > 4.0 and state == "go"]
    assert back and all(left == FORWARD for left in back)


def test_small_motion_spikes_do_not_restart_four_failed_turns(monkeypatch):
    guard = FootGuard()
    # Most map samples remain still even though turning creates occasional flow.
    monkeypatch.setattr(
        guard, "_evidence", lambda observation: "going" if round(observation.time / DT) % 10 == 0 else "still"
    )
    steers = run(guard, 10)
    failed = [(t, steer) for t, steer in steers if steer.failed]
    assert failed and failed[0][0] < 9
    assert failed[0][1].failed == "stuck"
    assert [state for t, state in guard.events if t < failed[0][0]].count("escape") == 4


def test_uncertain_escape_needs_progress_before_retrying_original_direction(monkeypatch):
    guard = FootGuard()
    monkeypatch.setattr(guard, "_evidence", lambda observation: "still" if observation.time < 2.1 else None)
    steers = run(guard, 10)
    assert any(steer.failed == "stuck" and t < 9 for t, steer in steers)


def test_walking_diagnostic_reaches_the_logged_skill_description():
    runner = SkillRunner()
    runner.replace((SkillCall("walk", {"duration": 10, "y": -1}),))
    runner.tick(obs(0))
    result = runner.tick(obs(DT))
    assert result.reason == runner.describe()["reason"]
    assert "state=go;attempts=0;motion=still" in result.reason
    for i in range(2, 300):
        result = runner.tick(obs(i * DT))
        if result.status == "failed":
            break
    assert result.reason == "stuck"
    assert runner.describe()["reason"] == "stuck"


def test_standalone_vehicle_skill_description_does_not_require_a_foot_guard():
    runner = SkillRunner()
    runner.replace((SkillCall("enter_vehicle", {"duration": 25, "kind": "any"}),))
    runner.active = runner.queue.popleft()
    assert runner.describe() == {"name": "enter_vehicle", "status": "running", "reason": None, "queue": []}


def test_progress_clears_the_count_of_failures():
    guard = FootGuard()
    run(guard, 2.2, moving=False)
    assert guard.failures == 1
    walking = [frame_with(crop("foot_road_a")), frame_with(crop("foot_road_b"))]
    t = 2.2
    while t < 9.0:
        # The ground moves under the arrow: each shift is measured across the pair.
        guard.step(obs(t, moving=None, frame=walking[int(t / 0.5) % 2]), FORWARD)
        t += DT
    assert guard.state == "go" and guard.failures == 0


def test_on_real_frames_the_railing_is_stuck_and_walking_is_not():
    still = [frame_with(crop("foot_pier_still_a")), frame_with(crop("foot_pier_still_b"))]
    walking = [frame_with(crop("foot_road_a")), frame_with(crop("foot_road_b"))]
    for frames, stuck in ((still, True), (walking, False)):
        guard = FootGuard()
        states = []
        for i in range(90):
            t = i * DT
            # Alternate the pair every half second, so each shift is measured across it.
            frame = frames[int(t / 0.5) % 2] if not stuck else frames[0]
            states.append(guard.step(obs(t, moving=None, frame=frame), FORWARD).state)
        assert ("escape" in states) == stuck


def test_nothing_is_guarded_off_foot():
    guard = FootGuard()
    steers = run(guard, 5.0, moving=False, mode="vehicle")
    assert all(steer.state == "idle" and steer.left == FORWARD for _, steer in steers)


# ------------------------------------------------------------------ the judge
def feed(guard, judgments, seconds, *, start=0.0, moving=None):
    steers, t, pending = [], start, list(judgments)
    current = None
    while t < start + seconds:
        while pending and pending[0][0] <= t:
            current = pending.pop(0)[1]
        steers.append((t, guard.step(obs(t, moving=moving, judgment=current), FORWARD)))
        t += DT
    return steers


def test_blocked_for_a_second_turns_the_camera_and_is_bounded():
    guard = FootGuard()
    # Judgments arrive 0.27 s after their frame, one every 0.3 s.
    judgments = [(c + 0.27, judged(c, "blocked")) for c in np.arange(0.0, 6.0, 0.3)]
    steers = feed(guard, judgments, 6.0)
    looks = [(t, steer) for t, steer in steers if steer.state == "look"]
    assert looks
    first = looks[0][0]
    assert 0.9 + 0.27 <= first <= 1.6
    assert all(steer.left == (0.0, 0.0) and abs(steer.right[0]) >= 0.3 for _, steer in looks)
    # The turn ends at the bound: 100 deg at 15 + 133 * 0.4 deg/s.
    first_look = [t for t, _ in looks if t < first + 3.0]
    turn = first_look[-1] - first + DT
    assert turn * FootGuard.LOOK_RATE <= FootGuard.LOOK_BOUND + FootGuard.LOOK_RATE * 2 * DT


def test_the_turn_ends_on_a_fresh_free():
    guard = FootGuard()
    judgments = [(c + 0.27, judged(c, "blocked")) for c in np.arange(0.0, 1.3, 0.3)]
    judgments += [(c + 0.27, judged(c, "free")) for c in np.arange(1.5, 4.0, 0.3)]
    steers = feed(guard, judgments, 4.0)
    looks = [t for t, steer in steers if steer.state == "look"]
    assert looks and looks[-1] - looks[0] < 0.6
    after = [steer for t, steer in steers if t > looks[-1]]
    assert after[0].state == "ahead" and after[0].left[1] < 0 and after[0].right == (0.0, 0.0)


def test_successive_judge_turns_alternate_sides():
    guard = FootGuard()
    judgments = [(c + 0.27, judged(c, "blocked")) for c in np.arange(0.0, 12.0, 0.3)]
    steers = feed(guard, judgments, 12.0)
    sides = []
    for _, steer in steers:
        if steer.state == "look" and (not sides or sides[-1] != math.copysign(1, steer.right[0])):
            sides.append(math.copysign(1, steer.right[0]))
    assert sides[:2] == [1, -1]


@pytest.mark.parametrize(
    "judgments",
    [
        # One blocked judgment among free ones.
        [(0.57, judged(0.3, "free")), (0.87, judged(0.6, "blocked")), (1.17, judged(0.9, "free"))],
        # Blocked for a second, but every one of them arrives too old to count.
        [(c + 2.0, judged(c, "blocked")) for c in np.arange(0.0, 1.3, 0.3)],
        # Blocked twice, a cannot-tell between: not a second of blocked in a row.
        [(0.27, judged(0.0, "blocked")), (0.57, judged(0.3, "unknown")), (0.87, judged(0.6, "blocked"))],
    ],
)
def test_a_single_or_stale_judgment_does_not_turn(judgments):
    guard = FootGuard()
    steers = feed(guard, judgments, 4.0)
    assert all(steer.state == "go" for _, steer in steers)


def test_a_turn_that_never_hears_free_gives_the_judge_up_after_two():
    guard = FootGuard()
    judgments = [(c + 0.27, judged(c, "blocked")) for c in np.arange(0.0, 20.0, 0.3)]
    steers = feed(guard, judgments, 20.0)
    starts = [
        t
        for (t, steer), (_, before) in zip(steers[1:], steers, strict=False)
        if steer.state == "look" != before.state
    ]
    assert len(starts) + (steers[0][1].state == "look") <= FootGuard.JUDGE_TURNS


# ------------------------------------------------------------------ the skills
def walk(args=None):
    return Skill(SkillCall("walk", {"duration": 10, "y": -1, **(args or {})}))


def test_walk_fails_stuck_with_a_neutral_pad_and_holds_it():
    skill = walk()
    result = None
    for i in range(301):
        result = skill.step(obs(i * DT, moving=False))
        if result.status != "running":
            break
    assert result.status == "failed" and result.reason == "stuck" and result.pad == NEUTRAL_PAD
    assert skill.step(obs(11.0, moving=False)) == result


def test_walk_to_reports_blocked_after_its_ways_round():
    from pilot.contract import Blip

    skill = Skill(SkillCall("walk_to", {"color": "blue", "duration": 10}))
    reading = Reading("flat", "none", None, None, 0.0, False, 0.9, blips=(Blip("blue", 0, 50),))
    result = None
    for i in range(301):
        result = skill.step(Observation(reading, False, i * DT))
        if result.status != "running":
            break
    assert result.status == "failed" and result.reason == "blocked" and result.pad == NEUTRAL_PAD


def test_sprint_is_not_held_on_a_way_round():
    skill = walk({"sprint": True})
    pads = [skill.step(obs(i * DT, moving=False)) for i in range(120)]
    assert any(p.pad.buttons for p in pads[:30])
    escaping = [p for p in pads if p.pad.left != (0, -1) and p.pad.left != (0.0, 0.0)]
    assert escaping and not any(p.pad.buttons for p in escaping)


@pytest.mark.parametrize("ending", ["time", "stop", "replace"])
def test_walk_releases_the_pad_at_every_end(ending):
    runner = SkillRunner()
    runner.replace((SkillCall("walk", {"duration": 3, "y": -1}),))
    runner.tick(obs(0.0, moving=False))
    for i in range(1, 70):
        result = runner.tick(obs(i * DT, moving=False))
    assert result.pad != NEUTRAL_PAD  # in the middle of a way round
    if ending == "time":
        result = runner.tick(obs(3.1, moving=False))
        assert result.status == "done" and result.pad == NEUTRAL_PAD
    elif ending == "stop":
        assert runner.stop() == NEUTRAL_PAD
    else:
        assert runner.replace((SkillCall("wait", {}),)) == NEUTRAL_PAD
        assert runner.tick(obs(3.2)).pad == NEUTRAL_PAD


def test_walk_road_is_registered_and_validates():
    assert REGISTRY["walk_road"] is WalkRoad
    assert len(WalkRoad.prompt) <= 400
    with pytest.raises(ValueError):
        WalkRoad({"duration": float("nan")})
    with pytest.raises(ValueError):
        WalkRoad({"speed": 1})
    assert WalkRoad({"duration": 999}).limit == 30.0


def test_walk_road_walks_toward_the_road_and_ends_neutral():
    skill = WalkRoad({"duration": 3})
    frame = frame_with(crop("foot_road_a"))
    road = find_road(crop("foot_road_a"))
    first = skill.step(Observation(FLAT, None, 0.0, frame=frame))
    assert first.status == "running"
    assert abs(angle_of(first.pad.left) - road.bearing) < 1
    final = None
    for i in range(1, 100):
        final = skill.step(Observation(FLAT, None, i * DT, frame=frame))
        if final.status != "running":
            break
    assert final.status == "done" and final.reason == "time-limit" and final.pad == NEUTRAL_PAD


def test_walk_road_keeps_going_when_north_is_temporarily_hidden(monkeypatch):
    monkeypatch.setattr("pilot.foot.north_bearing", lambda _: None)
    skill = WalkRoad({})
    frame = frame_with(crop("foot_pier_still_a"))
    results = [skill.step(Observation(FLAT, None, i * DT, frame=frame)) for i in range(40)]
    assert all(r.status == "running" for r in results)
    assert all(r.pad.left == (0.0, -skill.STICK) for r in results)
    assert skill.compass_heading is None
    blind = WalkRoad({}).step(Observation(FLAT, None, 0.0))
    assert blind.status == "failed" and blind.reason == "no-frame" and blind.pad == NEUTRAL_PAD
