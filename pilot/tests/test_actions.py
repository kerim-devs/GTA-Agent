"""Action labels from controller lines and reader output, never from video."""

import json
import math

import pytest

from pilot.actions import (
    Controller,
    Look,
    Sample,
    attach_hands,
    estimate_lead,
    label,
    load_controller,
    sample_indices,
    write_index,
)
from pilot.contract import Pad

FOOT = Look(minimap="flat", wanted=0)
CAR = Look(minimap="tilted", wanted=0)
STARRED = Look(minimap="tilted", wanted=2)


def samples(looks, step=0.1, times=None):
    times = times or [round(k * step, 6) for k in range(len(looks))]
    return [
        Sample(index=k, time=t, end=times[k + 1] if k + 1 < len(times) else t + step, last=k, look=look)
        for k, (t, look) in enumerate(zip(times, looks, strict=True))
    ]


def run(looks, events, *, lead=0.0, times=None, **kwargs):
    controller = None if events is None else Controller(sorted(events, key=lambda e: e[0]))
    return label(
        attach_hands(samples(looks, times=times), controller, lead),
        has_pad=controller is not None,
        lead=lead,
        **kwargs,
    )


def at(stretches, t):
    for stretch in stretches:
        if stretch["start"] <= t < stretch["end"]:
            return stretch["action"]
    raise AssertionError(f"no stretch at {t}")


def hold(start, end, pad, step=0.05):
    """A held state written as the controller writes it: a line whenever it changes, here a little noise."""
    lines, t = [], start
    while t < end:
        lines.append((round(t, 4), pad))
        t += step
    lines.append((round(end, 4), Pad()))
    return lines


def taps(start, end, button, every=0.25, length=0.05, left=(0.0, -1.0)):
    lines, t = [], start
    while t < end:
        lines += [(round(t, 4), Pad(buttons=(button,), left=left)), (round(t + length, 4), Pad(left=left))]
        t += every
    return lines


def test_a_press_shorter_than_a_sample_is_kept():
    events = [(0.0, Pad()), (1.53, Pad(buttons=("circle",))), (1.56, Pad())]
    stretches = run([FOOT] * 30, events)
    assert at(stretches, 1.5) == "melee"
    assert [s["action"] for s in stretches] == ["idle", "melee", "idle"]
    assert stretches[1]["evidence"]["hand"]["pressed"] == {"circle": 1}


def test_the_lead_puts_the_hand_on_the_clock_of_the_frames():
    events = [(0.0, Pad()), (1.03, Pad(buttons=("circle",))), (1.06, Pad())]
    stretches = run([FOOT] * 30, events, lead=0.5)
    melee = [s for s in stretches if s["action"] == "melee"]
    assert len(melee) == 1 and melee[0]["start"] == pytest.approx(1.5)
    assert melee[0]["first_frame"] == 15 and melee[0]["evidence"]["lead"] == 0.5


def test_what_the_hand_does_on_foot():
    events = [
        (0.0, Pad()),
        *hold(1.0, 2.0, Pad(left=(0.0, -0.6))),
        *taps(3.0, 4.0, "cross"),
        (4.0, Pad()),
        *hold(5.0, 6.0, Pad(right=(0.8, 0.0))),
        *hold(7.0, 8.0, Pad(l2=1.0)),
        *hold(9.0, 9.4, Pad(l2=1.0, r2=1.0)),
    ]
    stretches = run([FOOT] * 110, events)
    assert at(stretches, 0.5) == "idle"
    assert at(stretches, 1.5) == "walk"
    assert at(stretches, 3.5) == "sprint"
    assert at(stretches, 5.5) == "look"
    assert at(stretches, 7.5) == "aim"
    assert at(stretches, 9.2) == "fire"


def test_a_tilted_map_on_foot_without_a_press_changes_nothing():
    # Under bridges and in alleys the reader calls the map tilted for seconds with the figure on foot.
    events = [(0.0, Pad()), *hold(1.0, 8.0, Pad(left=(0.0, -1.0)))]
    stretches = run([FOOT] * 20 + [CAR] * 50, events)
    assert {s["action"] for s in stretches if s["start"] >= 1.0} == {"walk"}


def test_getting_in_and_driving_along_a_route_or_without():
    for route, expected in (("yellow", "follow_route"), ("none", "drive_free")):
        events = [
            (0.0, Pad()),
            (1.0, Pad(buttons=("triangle",))),
            (1.05, Pad()),
            *hold(3.5, 8.0, Pad(r2=1.0)),
        ]
        looks = [FOOT] * 30 + [Look(minimap="tilted", route=route, wanted=0)] * 60
        stretches = run(looks, events)
        assert at(stretches, 0.5) == "idle"
        assert at(stretches, 1.0) == at(stretches, 2.9) == "enter_vehicle"
        assert at(stretches, 4.0) == at(stretches, 7.5) == expected


def test_getting_in_with_stars_needs_the_hand_to_confirm():
    # With stars the map is tilted on foot as well; R2 there is a shot unless the enter button came first.
    looks = [Look(minimap="flat", wanted=2)] * 20 + [STARRED] * 80
    shot = run(looks, [(0.0, Pad()), *hold(4.0, 6.0, Pad(r2=1.0))])
    assert at(shot, 5.0) == "fire"
    events = [(0.0, Pad()), (2.5, Pad(buttons=("triangle",))), (2.55, Pad()), *hold(5.0, 9.0, Pad(r2=1.0))]
    entered = run(looks, events)
    assert at(entered, 3.0) == "enter_vehicle"
    assert at(entered, 7.0) == "drive_free"


def test_a_press_that_changes_nothing_is_no_entry():
    events = [(0.0, Pad()), (1.0, Pad(buttons=("triangle",))), (1.05, Pad())]
    stretches = run([FOOT] * 120, events)
    assert "enter_vehicle" not in {s["action"] for s in stretches}


def test_getting_out():
    events = [
        *hold(0.0, 2.0, Pad(r2=1.0)),
        (2.5, Pad(buttons=("triangle",))),
        (2.55, Pad()),
        *hold(4.5, 7.0, Pad(left=(0.0, -0.7))),
    ]
    looks = [CAR] * 40 + [FOOT] * 40
    stretches = run(looks, events)
    assert at(stretches, 1.0) == "drive_free"
    assert at(stretches, 3.0) == "leave_vehicle"
    assert at(stretches, 5.0) == "walk"


def test_a_long_l2_is_reversing_and_a_short_one_a_brake():
    events = [
        *hold(0.0, 2.0, Pad(r2=1.0)),
        *hold(2.0, 2.3, Pad(l2=1.0)),
        *hold(2.3, 4.0, Pad(r2=1.0)),
        *hold(4.0, 6.0, Pad(l2=1.0)),
    ]
    stretches = run([CAR] * 70, events)
    assert at(stretches, 2.1) == "drive_free"
    assert at(stretches, 5.0) == "reverse_or_turn"


def test_a_standing_car_is_idle_and_unreadable_motion_is_not():
    standing = Look(minimap="tilted", wanted=0, moving=False)
    events = [*hold(0.0, 1.0, Pad(r2=1.0)), (1.0, Pad())]
    stretches = run([CAR] * 20 + [standing] * 20 + [CAR] * 40, events)
    # Let off R2 a moment ago the car rolls on, whether or not its motion is read.
    assert at(stretches, 1.5) == "drive_free"
    assert at(stretches, 3.0) == "idle"
    # Long after, with no motion read, nobody can tell a standing car from a rolling one.
    assert at(stretches, 6.0) == "unknown"


def test_the_screen_decides_before_the_hand():
    looks = [
        Look(screen="map"),
        Look(screen="pause"),
        Look(screen="phone"),
        Look(screen="loading"),
        Look(screen="wasted"),
    ]
    events = [*hold(0.0, 1.0, Pad(left=(1.0, 0.0), r2=1.0))]
    for events_or_none in (events, None):
        stretches = run([look for look in looks for _ in range(5)], events_or_none)
        assert [s["action"] for s in stretches] == ["map", "menu", "use_phone", "wait"]


def test_without_a_controller_only_the_screen_decides():
    stretches = run([FOOT] * 10 + [CAR] * 10, None)
    assert {s["action"] for s in stretches} == {"unknown"}
    assert stretches[0]["evidence"]["hand"] is None


def test_a_recording_with_the_controller_on_the_console_has_no_hand(tmp_path):
    (tmp_path / "pad.jsonl").write_text(json.dumps({"t": 0.1, "src": "human", "buttons": []}) + "\n")
    assert load_controller(tmp_path) is None


def test_damaged_readings_decide_nothing():
    damaged = Look(minimap="tilted", route="yellow", corrupt=True, wanted=0)
    events = [(0.0, Pad()), *hold(0.5, 6.0, Pad(left=(0.0, -1.0)))]
    looks = [FOOT, FOOT, damaged, damaged] * 15
    stretches = run(looks, events)
    assert {s["action"] for s in stretches if s["start"] >= 0.5} == {"walk"}
    # In a car whose every reading is damaged the route cannot be told.
    car = run([Look(minimap="tilted", wanted=0)] * 20 + [damaged] * 40, [*hold(0.0, 6.0, Pad(r2=1.0))])
    assert at(car, 4.0) == "unknown"


def test_no_minimap_on_the_game_screen_is_a_cutscene_while_the_hand_is_quiet():
    events = [(0.0, Pad()), *hold(3.0, 4.0, Pad(left=(1.0, 0.0)))]
    stretches = run([FOOT] * 10 + [Look(minimap="none")] * 40, events)
    assert at(stretches, 2.0) == "wait"
    assert at(stretches, 3.5) == "unknown"


def test_a_controller_lying_on_its_sticks_is_not_a_walk():
    events = [(0.0, Pad(left=(1.0, 1.0)))]
    stretches = run([FOOT] * 300, events)
    assert at(stretches, 5.0) == "walk"
    assert at(stretches, 25.0) == "unknown"


def test_neighbours_and_short_flickers():
    # A sprint between taps does not break into walk-sprint-walk; an event is never smoothed away.
    events = [(0.0, Pad()), *taps(1.0, 4.0, "cross", every=0.45)]
    stretches = run([FOOT] * 50, events)
    assert [s["action"] for s in stretches] == ["idle", "sprint", "walk"]
    fire = run([FOOT] * 30, [(0.0, Pad()), (1.21, Pad(r2=1.0)), (1.24, Pad())])
    assert [s["action"] for s in fire] == ["idle", "fire", "idle"]


def test_a_short_rest_between_two_inputs_is_no_idle():
    # Between two punches the fight goes on in the picture while the hand rests for half a second.
    events = [
        (0.0, Pad()),
        (1.0, Pad(buttons=("circle",))),
        (1.05, Pad()),
        (1.6, Pad(buttons=("circle",))),
        (1.65, Pad()),
        (4.0, Pad(buttons=("circle",))),
        (4.05, Pad()),
    ]
    actions = [s["action"] for s in run([FOOT] * 60, events)]
    assert actions == ["idle", "melee", "unknown", "melee", "idle", "melee", "idle"]


def test_times_and_frames_come_from_frames_jsonl_with_gaps():
    rows = [{"i": i, "t": t} for i, t in enumerate([0.0, 0.016, 0.05, 0.1, 0.12, 1.7, 1.71, 1.8, 1.9])]
    assert sample_indices(rows, 10) == [0, 3, 5, 7, 8]
    times = [rows[i]["t"] for i in sample_indices(rows, 10)]
    events = [(0.0, Pad()), (0.5, Pad(buttons=("circle",))), (0.52, Pad())]
    stretches = run([FOOT] * 5, events, times=times)
    # The press fell into the gap after 0.1 s, so the sample at 0.1 holds it until the next frame at 1.7.
    assert at(stretches, 0.1) == "melee"
    assert [s["start"] for s in stretches] == [0.0, 0.1, 1.7]
    assert stretches[1]["end"] == 1.7


def test_the_decision_can_be_replaced():
    stretches = run([FOOT] * 10, [(0.0, Pad())], decision=lambda sample, context, layout: ("wait", "judge"))
    assert stretches == [stretches[0]] and stretches[0]["action"] == "wait"
    assert stretches[0]["evidence"]["rule"] == "judge"


def test_a_known_lead_is_found_again():
    events, t, value = [(0.0, Pad())], 0.0, 0.0
    for k in range(400):
        t = 0.3 + k * 0.37
        value = [0.0, 0.8, -0.8, 0.5][(k * 7) % 4]
        events.append((round(t, 3), Pad(right=(value, 0.0))))
    controller = Controller(events)
    looks = []
    for k in range(1500):
        t = k * 0.1
        stick = controller.state_at(t - 0.05 - 0.4).right[0]
        looks.append(Look(minimap="flat", wanted=0, pan=-300 * stick))
    lead, correlation = estimate_lead(samples(looks), controller)
    assert lead == pytest.approx(0.4, abs=0.03) and correlation > 0.9


def test_the_index_samples_twice_a_second_with_the_hand_that_caused_the_frame(tmp_path):
    recording = tmp_path / "rec"
    recording.mkdir()
    frames = [{"i": i, "frame_id": i, "t": i / 30} for i in range(300)]
    (recording / "frames.jsonl").write_text("".join(json.dumps(f) + "\n" for f in frames))
    pad = [
        {"t": 0.0, "src": "human", "buttons": [], "left": [0, 0], "right": [0, 0], "l2": 0, "r2": 0},
        {"t": 4.0, "src": "human", "buttons": [], "left": [0, -1], "right": [0, 0], "l2": 0, "r2": 0},
    ]
    (recording / "pad.jsonl").write_text("".join(json.dumps(p) + "\n" for p in pad))
    out = tmp_path / "out" / "rec"
    out.mkdir(parents=True)
    stretches = [
        {"start": 0.0, "end": 4.5, "first_frame": 0, "last_frame": 134, "action": "idle"},
        {"start": 4.5, "end": 10.0, "first_frame": 135, "last_frame": 299, "action": "walk"},
    ]
    (out / "actions.jsonl").write_text("".join(json.dumps(s) + "\n" for s in stretches))
    (out / "labels.json").write_text(
        json.dumps({"recording": str(recording), "has_pad": True, "lead": 0.5, "lead_source": "given"})
    )
    result = write_index(tmp_path / "out")
    rows = [json.loads(line) for line in (tmp_path / "out" / "index.jsonl").read_text().splitlines()]
    assert result == {"recordings": 1, "samples": 20} and len(rows) == 20
    by_time = {row["time"]: row for row in rows}
    assert by_time[4.0]["action"] == "idle" and by_time[4.0]["pad"]["left"] == [0, 0]
    assert by_time[4.5]["action"] == "walk" and by_time[4.5]["pad"]["left"] == [0, -1]
    assert all(not math.isnan(row["time"]) and "pixels" not in row for row in rows)
    summary = (tmp_path / "out" / "summary.md").read_text()
    assert "| walk | 0.1 |" in summary and "| rec | 0.2 | 0.50 (given) | 2 | 0.0% |" in summary
