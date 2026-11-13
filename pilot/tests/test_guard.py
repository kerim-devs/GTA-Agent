"""The guard: what each rule answers, in what order, and what it never does."""

import json
from concurrent.futures import Future
from dataclasses import replace

import numpy as np
import pytest

from pilot.conductor import Conductor, guard_row
from pilot.contract import NEUTRAL_PAD, Blip, Detection, Hud, Observation, Reading
from pilot.guard import Guard
from pilot.head import HeadRequest, parse_response
from pilot.mission import MissionHead

TICK = 1 / 30
RGB = np.zeros((720, 1280, 3), dtype=np.uint8)
AHEAD = Blip("red", 0.0, 20.0)  # inside the map, straight ahead
BEHIND = Blip("red", 0.0, -20.0)
EDGE = Blip("red", 60.0, 86.0, border=True)  # pinned to the map's edge, ahead and to the right


def see(t, *, blips=(), wanted=0, health=0.9, screen="game", minimap="flat", corrupt=False, mode=None):
    reading = Reading(minimap, "none", None, None, 0.0, corrupt, 1.0, blips=tuple(blips))
    return Observation(reading, None, t, hud=Hud(wanted=wanted, health=health, screen=screen), mode=mode)


def calm(guard, until=1.2, start=0.0):
    """Ticks of an ordinary picture, long enough for the HUD to count as back."""
    t = start
    while t < until:
        assert guard.tick(see(t)).pad is None
        t += TICK
    return t


def run(guard, t, seconds, **picture):
    verdicts = []
    for _ in range(round(seconds / TICK)):
        verdicts.append(guard.tick(see(t, **picture)))
        t += TICK
    return t, verdicts


def fired(verdicts):
    return any(verdict.pad.r2 or verdict.pad.l2 for verdict in verdicts if verdict.pad is not None)


def kinds(verdicts):
    return [event["kind"] for verdict in verdicts for event in verdict.events]


def test_the_highest_rank_that_counts_holds_the_pad():
    guard = Guard()
    t = calm(guard)
    # Red ahead, two stars and a third of health at once: the stars count after 0.1 s and flee, low
    # health takes over after half a second, and the red is never fought while stars are lit.
    t, verdicts = run(guard, t, 0.8, blips=(AHEAD,), wanted=2, health=0.2)
    holders = [verdict.rule for verdict in verdicts]
    assert holders[:3] == [None, None, None]
    assert holders[4] == "stars"
    assert holders[-1] == "low_health"
    starts = [event for verdict in verdicts for event in verdict.events]
    assert [(e["rule"], e.get("after")) for e in starts] == [("stars", None), ("low_health", "stars")]
    assert not fired(verdicts)
    # The flight is a sprint away from the marker ahead, which is backwards on the stick.
    assert any("cross" in verdict.pad.buttons and verdict.pad.left[1] > 0.5 for verdict in verdicts[5:])

    # Inside the map outranks the edge: a marker inside is fought, one on the edge is only turned to.
    guard = Guard()
    t = calm(guard)
    t, verdicts = run(guard, t, 0.2, blips=(EDGE,))
    assert verdicts[-1].rule == "red_edge"
    assert verdicts[-1].pad.right[0] > 0 and verdicts[-1].pad.l2 == 0 and verdicts[-1].pad.r2 == 0
    t, verdicts = run(guard, t, 0.6, blips=(EDGE, AHEAD))
    assert verdicts[-1].rule == "red"
    assert [e.get("after") for v in verdicts for e in v.events] == ["red_edge"]
    assert verdicts[-1].pad.l2 == 1.0


def test_one_odd_tick_decides_nothing():
    guard = Guard()
    t = calm(guard)
    for picture in ({"blips": (AHEAD,)}, {"blips": (EDGE,)}, {"wanted": 1}, {"minimap": "none"}):
        assert guard.tick(see(t, **picture)).pad is None
        t += TICK
        t = calm(guard, t + 0.2, t)
    # Health under a third for less than half a second, and a red marker on every other tick.
    t, verdicts = run(guard, t, 0.4, health=0.1)
    assert all(verdict.pad is None for verdict in verdicts)
    for index in range(10):
        assert guard.tick(see(t, blips=(AHEAD,) if index % 3 == 0 else ())).pad is None
        t += TICK
    assert guard.episodes == []

    # A damaged picture stands out: it neither confirms a marker nor breaks a fight.
    t, verdicts = run(guard, t, 0.1, blips=(AHEAD,))
    assert verdicts[-1].rule == "red"
    damaged = guard.tick(see(t, corrupt=True))
    assert damaged.rule == "red" and not damaged.events


def test_no_shot_while_stars_are_lit():
    guard = Guard()
    t = calm(guard)
    t, verdicts = run(guard, t, 1.0, blips=(AHEAD,))
    assert any(verdict.pad.r2 for verdict in verdicts if verdict.pad)  # fired at the marker ahead
    # The first reading of a star holds the trigger at once, before the stars count.
    t, verdicts = run(guard, t, 1.5, blips=(AHEAD,), wanted=1)
    assert not fired(verdicts)
    assert verdicts[0].pad == NEUTRAL_PAD
    assert verdicts[-1].rule == "stars"

    # With stars lit from the start a marker is never fought, however long it stays.
    guard = Guard()
    t = calm(guard)
    t, verdicts = run(guard, t, 6.0, blips=(AHEAD,), wanted=1)
    assert not fired(verdicts)
    assert "red" not in {episode["rule"] for episode in guard.episodes}


@pytest.mark.parametrize("picture", [{"screen": "map"}, {"mode": "none"}, {"minimap": "none"}])
def test_silent_on_a_screen_and_in_mode_none(picture):
    guard = Guard()
    t = calm(guard)
    t, verdicts = run(guard, t, 0.5, blips=(AHEAD,))
    assert verdicts[-1].rule == "red"
    # The first tick of the screen decides nothing, the second lets go with the neutral pad.
    t, verdicts = run(guard, t, 3.0, blips=(AHEAD,), **picture)
    assert verdicts[1].pad == NEUTRAL_PAD
    assert verdicts[1].events[0]["kind"] == "guard_end" and verdicts[1].events[0]["reason"] == "screen"
    assert all(verdict.pad is None and not verdict.events for verdict in verdicts[2:])
    # Nor does anything start while the screen lasts, whatever the map shows.
    t, verdicts = run(guard, t, 1.0, blips=(EDGE,), wanted=1, health=0.1, **picture)
    assert all(verdict.pad is None and not verdict.events for verdict in verdicts)


def test_nothing_on_the_pad_in_a_vehicle():
    guard = Guard()
    t = calm(guard)
    t, _ = run(guard, t, 1.0, minimap="tilted")
    t, verdicts = run(guard, t, 3.0, minimap="tilted", blips=(AHEAD, EDGE), health=0.1, wanted=0)
    assert all(verdict.pad is None for verdict in verdicts)
    news = [event for verdict in verdicts for event in verdict.events]
    assert {event["kind"] for event in news} == {"guard_news"}
    assert {event["rule"] for event in news} == {"red", "low_health"}
    assert all(event["where"] == "vehicle" for event in news)
    assert all(verdict.abandon for verdict in verdicts if verdict.events)

    # On foot the map tilts when stars light up (docs/LOG.md, 11 November): that is no vehicle.
    guard = Guard()
    t = calm(guard)
    t, verdicts = run(guard, t, 0.5, minimap="tilted", wanted=1)
    # The sprint is tapped (0.11 s down in every 0.21 s), so one of the last ticks holds the press.
    taps = [button for verdict in verdicts[-7:] if verdict.pad is not None for button in verdict.pad.buttons]
    assert verdicts[-1].rule == "stars" and "cross" in taps


def test_neutral_pad_on_the_tick_it_lets_go():
    guard = Guard()
    t = calm(guard)
    t, verdicts = run(guard, t, 1.0, blips=(AHEAD,))
    assert verdicts[-1].rule == "red"
    # Fight ends by itself after two seconds without red; that tick is neutral, the next is the plan's.
    t, verdicts = run(guard, t, 2.5)
    end = next(index for index, verdict in enumerate(verdicts) if verdict.events)
    assert verdicts[end].pad == NEUTRAL_PAD
    assert verdicts[end].events[0] == {
        "kind": "guard_end",
        "rule": "red",
        "reason": "no-red-blips",
        "seconds": pytest.approx(verdicts[end].events[0]["seconds"]),
    }
    assert 1.9 <= end * TICK <= 2.2
    assert all(verdict.pad is None for verdict in verdicts[end + 1 :])
    # A rule that let go waits for its signal to be gone before it answers again: the stars a head
    # already flees from do not take the pad back.
    guard = Guard()
    t = calm(guard)
    t, verdicts = run(guard, t, 5.0, wanted=1)
    assert kinds(verdicts) == ["guard_start", "guard_end"]
    assert verdicts[-1].pad is None


def test_low_health_waits_for_the_hud_to_settle():
    # P64, enemy-13: after a black screen the bar fades in and reads empty for about 0.35 s.
    guard = Guard()
    t = calm(guard)
    t, _ = run(guard, t, 1.0, minimap="none", screen="loading", health=None)
    t, verdicts = run(guard, t, 0.6, health=0.0)
    t, more = run(guard, t, 2.0)
    assert all(verdict.pad is None for verdict in verdicts + more)
    assert guard.episodes == []
    # Once the HUD has been back a second, a real fall flees: straight ahead, with no marker.
    t, verdicts = run(guard, t, 0.7, health=0.2)
    assert verdicts[-1].rule == "low_health"
    assert verdicts[-1].pad.left == (0.0, -1.0)


def test_a_fight_is_not_ended_by_a_bar_fading_in():
    # enemy-19 and enemy-20 of the bench: the HUD comes back after a black screen with red on the map,
    # and the bar reads empty while it fades in. Fight must not take that for a figure without health.
    guard = Guard()
    t = calm(guard)
    t, _ = run(guard, t, 1.0, minimap="none", screen="loading", health=None)
    t, verdicts = run(guard, t, 0.5, blips=(AHEAD,), health=0.0)
    assert verdicts[-1].rule == "red"
    assert kinds(verdicts) == ["guard_start"]


def test_a_turn_waits_while_a_skill_moves_the_figure():
    guard = Guard()
    t = calm(guard)
    verdicts = []
    for _ in range(10):
        verdicts.append(guard.tick(see(t, blips=(EDGE,)), moving=True))
        t += TICK
    assert all(verdict.pad is None for verdict in verdicts)
    assert kinds(verdicts) == ["guard_news"] and verdicts[-1].rule == "red_edge"
    verdict = guard.tick(see(t, blips=(EDGE,)), moving=False)
    assert verdict.events[0]["kind"] == "guard_start" and verdict.pad.right[0] > 0


def test_an_escape_objective_flees_from_red_instead_of_fighting():
    guard = Guard()
    t = calm(guard)
    verdicts = []
    for _ in range(6):
        verdicts.append(guard.tick(see(t, blips=(BEHIND,)), objective="Entkomme den Feinden."))
        t += TICK
    start = next(event for verdict in verdicts for event in verdict.events)
    assert start["answer"] == "flee"
    assert verdicts[-1].pad.left[1] < -0.5 and not verdicts[-1].pad.r2


class Pending:
    def __init__(self):
        self.jobs = []

    def __call__(self, function, *args):
        # Running, as a head on its thread is: it cannot be cancelled and answers when it answers.
        future = Future()
        future.set_running_or_notify_cancel()
        self.jobs.append((future, function, args))
        return future


class NoEvents:
    def update(self, *args, **kwargs):
        return ()


def walk_reply():
    return parse_response(
        {"plan": [{"name": "walk", "args": {"duration": 5, "x": 0, "y": -1}}], "sentence": "Weiter."}
    )


def test_the_guard_voids_a_head_answer_that_arrives_after_it_started(tmp_path):
    pending = Pending()
    conductor = Conductor(tmp_path, submit=pending, detector=NoEvents(), guard=Guard())
    try:
        t = 0.0
        while t < 1.2:
            conductor.tick(see(t), RGB)
            t += TICK
        assert len(pending.jobs) == 1  # the startup request, still on its way
        results = []
        for _ in range(3):
            results.append(conductor.tick(see(t, blips=(AHEAD,)), RGB))
            t += TICK
        assert results[1].reason == "guard"
        assert len(pending.jobs) == 2
        assert pending.jobs[1][2][0].events[0]["kind"] == "guard_start"
        # The answer to the request from before arrives now: it is void.
        pending.jobs[0][0].set_result(walk_reply())
        for _ in range(5):
            result = conductor.tick(see(t, blips=(AHEAD,)), RGB)
            t += TICK
            assert result.reason == "guard"
        assert conductor.runner.active is None and not conductor.runner.queue
        responses = [json.loads(line) for line in (tmp_path / "head.jsonl").read_text().splitlines()]
        first = [row for row in responses if row["type"] == "response" and row["id"] == 1]
        assert first and all(not row["applied"] for row in first)
        # The answer to the guard's own request is kept for when the guard lets go.
        pending.jobs[1][0].set_result(walk_reply())
        conductor.tick(see(t, blips=(AHEAD,)), RGB)
        t += TICK
        assert conductor.runner.active is None and [s.name for s in conductor.runner.queue] == ["walk"]
        # Two seconds without red: the fight ends, that tick is neutral, and the plan runs after it.
        results, ends = [], []
        for _ in range(80):
            results.append(conductor.tick(see(t), RGB))
            ends.append(any(event["kind"] == "guard_end" for event in conductor.guard_events))
            t += TICK
        end = ends.index(True)
        assert results[end].reason == "guard" and results[end].pad == NEUTRAL_PAD
        assert results[end + 1].reason != "guard"
        assert any(r.pad.left == (0, -1) for r in results[end + 1 :])
        assert conductor.pending == [] or conductor.pending[0]["kind"] == "guard_end"
        assert pending.jobs[2][2][0].events[0]["kind"] == "guard_end"
    finally:
        conductor.close()


def test_a_conductor_without_a_guard_keeps_its_plan_through_threats(tmp_path):
    """No guard: the plan's pad is the tick's whatever the map shows, and the head hears stars and low
    health as it always did, a bar that fades in included."""
    pending = Pending()
    conductor = Conductor(tmp_path, submit=pending, detector=NoEvents())
    try:
        conductor.tick(see(0.0), RGB)
        pending.jobs[0][0].set_result(walk_reply())
        t = TICK
        results = []
        for index in range(60):
            picture = {"blips": (AHEAD, EDGE), "wanted": 2 if index > 20 else 0}
            results.append(conductor.tick(see(t, **picture), RGB))
            t += TICK
        assert all(result.reason != "guard" for result in results)
        assert not any(result.pad.r2 or result.pad.l2 for result in results)
        assert conductor.runner.active.name == "walk"
        assert conductor.guard_events == [] and conductor.guard_verdict is None
        # A bar that reads empty right after a black screen is low health after half a second.
        events = []
        for _ in range(10):
            events += conductor._hud_events(see(t, minimap="none", screen="loading", health=None))
            t += TICK
        for _ in range(20):
            events += conductor._hud_events(see(t, health=0.0))
            t += TICK
        assert {"kind": "low_health", "health": 0.0} in events
        hud = conductor._hud_for_head(see(t, health=0.0))
        assert hud["health"] == 0.0
    finally:
        conductor.close()


def test_with_a_guard_the_head_does_not_see_a_bar_fading_in(tmp_path):
    conductor = Conductor(tmp_path, submit=Pending(), detector=NoEvents(), guard=Guard())
    try:
        t = 0.0
        for _ in range(10):
            conductor.tick(see(t, minimap="none", screen="loading", health=None), RGB)
            t += TICK
        events = []
        for _ in range(20):
            conductor.tick(see(t, health=0.0), RGB)
            events += conductor._hud_events(see(t, health=0.0))
            t += TICK
        assert conductor._hud_for_head(see(t, health=0.0))["health"] is None
        assert not any(event["kind"] == "low_health" for event in events)
    finally:
        conductor.close()


def test_the_head_rules_take_the_guards_events_as_no_failure():
    def plan(reason):
        request = HeadRequest(
            [
                {"kind": "guard_start", "rule": "stars", "rank": 3, "answer": "flee", "bearing": None},
                {"kind": "guard_end", "rule": "stars", "reason": "time", "seconds": 4.0},
            ],
            "",
            "",
            "",
            "",
            {"minimap": "flat", "route": "none", "corrupt": False, "blips": []},
            {"name": "walk", "status": "failed", "reason": reason, "queue": []},
            "",
            "",
            hud={"screen": "game", "health": 0.9, "wanted": 1},
        )
        return [call.name for call in MissionHead().decide(request).plan]

    # A walk that failed is not walked again at once: the goal looks round first. One the guard stopped
    # did not fail, and the escape goes on as it was.
    assert plan("stuck") == ["look", "walk"]
    assert plan("guard_stars") == ["walk"]


def test_the_play_log_rows_time_a_live_run_without_the_bench():
    start = {"kind": "guard_start", "rule": "red_edge", "rank": 5, "answer": "turn", "bearing": 34.9}
    row = guard_row({**start, "seen": 100.25}, 0.31, 100.0)
    assert row == {
        "type": "guard_start",
        "t": 0.31,
        "rule": "red_edge",
        "seen": 0.25,
        "bearing": 34.9,
        "answer": "turn",
    }
    end = {"kind": "guard_end", "rule": "red_edge", "reason": "no red left", "seconds": 2.4}
    assert guard_row(end, 2.71, 100.0) == {
        "type": "guard_end",
        "t": 2.71,
        "rule": "red_edge",
        "reason": "no red left",
    }
    # The start event the guard gives carries the first tick its signal was read on.
    guard = Guard()
    t = calm(guard)
    seen = t
    t, verdicts = run(guard, t, 0.2, blips=(AHEAD,))
    event = next(e for v in verdicts for e in v.events)
    assert event["seen"] == pytest.approx(seen) and event["bearing"] == 0.0


def test_a_rule_is_one_entry_in_the_table():
    from pilot.guard import RULES, Rule

    assert [rule.rank for rule in RULES] == [1, 2, 3, 4, 5, 6]
    quick = tuple(
        Rule(rule.rank, rule.name, rule.signal, ("ticks", 1, 1), rule.answer, rule.lets_go)
        if rule.name == "red"
        else rule
        for rule in RULES
    )
    guard = Guard(quick)
    t = calm(guard)
    assert guard.tick(see(t, blips=(AHEAD,))).rule == "red"


# ---------------------------------------------------------------- a hit without a marker


def person(t, health, *, objective_people=True, **picture):
    """The picture with a man standing before the figure, as the detector reports him."""
    seen = see(t, health=health, **picture)
    man = Detection("person", (560.0, 250.0, 700.0, 620.0), 0.9)
    own = Detection("person", (590.0, 330.0, 690.0, 640.0), 0.9)
    return replace(seen, objects=(man,) if objective_people else (), objects_time=t, figure=own)


def hit(guard, t, *, before=0.9, after=0.7, seconds=2.0, objective="", people=True, **picture):
    """A level held, then a step down that stays: what hits.py confirms on its third frame."""
    verdicts = []
    for _ in range(round(seconds / TICK)):
        guard.tick(person(t, before, objective_people=people, **picture), objective=objective)
        t += TICK
    for _ in range(round(1.0 / TICK)):
        verdicts.append(guard.tick(person(t, after, objective_people=people, **picture), objective=objective))
        t += TICK
    return t, verdicts


def test_a_hit_without_a_marker_is_answered_with_the_fists_in_free_roam():
    guard = Guard()
    _, verdicts = hit(guard, 0.0)
    starts = [event for verdict in verdicts for event in verdict.events if event["kind"] == "guard_start"]
    assert [event["rule"] for event in starts] == ["hit"]
    assert starts[0]["answer"] == "strike" and starts[0]["drop"] == pytest.approx(0.2, abs=0.01)
    held = [verdict for verdict in verdicts if verdict.rule == "hit" and verdict.pad is not None]
    assert held and not any(verdict.pad.r2 for verdict in held)  # the fists, never the trigger


def test_a_hit_is_no_signal_with_a_marker_on_the_map_or_stars_lit():
    guard = Guard()
    _, verdicts = hit(guard, 0.0, blips=(AHEAD,))
    assert "hit" not in {verdict.rule for verdict in verdicts}
    guard = Guard()
    _, verdicts = hit(guard, 0.0, wanted=1)
    assert "hit" not in {verdict.rule for verdict in verdicts}


def test_a_hit_in_a_mission_is_told_to_the_head_and_nothing_is_struck():
    guard = Guard()
    _, verdicts = hit(guard, 0.0, objective="Folge Lamar.")
    assert all(verdict.pad is None for verdict in verdicts)
    news = [event for verdict in verdicts for event in verdict.events]
    assert [(event["kind"], event["rule"], event["where"]) for event in news] == [
        ("guard_news", "hit", "mission")
    ]


def test_a_hit_with_nobody_in_view_lets_go_by_itself():
    guard = Guard()
    t, verdicts = hit(guard, 0.0, people=False)
    _, more = run(guard, t, 6.0, health=0.7)
    ends = [event for verdict in verdicts + more for event in verdict.events if event["kind"] == "guard_end"]
    assert [event["rule"] for event in ends] == ["hit"]
    assert more[-1].pad is None


def test_a_lower_bar_after_a_screen_without_the_hud_is_no_hit():
    guard = Guard()
    t = calm(guard)
    t, _ = run(guard, t, 2.0, health=0.9)
    for _ in range(45):  # a scene: no bars at all, and no map
        guard.tick(replace(see(t, minimap="none"), hud=Hud(wanted=None, health=None, screen="game")))
        t += TICK
    verdicts = []
    for _ in range(90):  # the game is back with less health than before the scene
        verdicts.append(guard.tick(person(t, 0.5)))
        t += TICK
    assert "hit" not in {verdict.rule for verdict in verdicts}
