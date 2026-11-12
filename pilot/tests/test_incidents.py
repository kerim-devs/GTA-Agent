"""Incidents from sequences of readings, texts and controller lines; no video is decoded."""

import pytest

from pilot.incidents import PAD_LEAD, Pad, attach_to_missions, failure_reason, find_incidents


def sample(t, **values):
    row = {
        "t": round(t, 3),
        "i": int(t * 60),
        "screen": "game",
        "wanted": 0,
        "health": 0.9,
        "map": "flat",
        "route": "none",
        "corrupt": False,
        "move": 0.0,
        "red": 0,
        "lum": 80.0,
        "change": 5.0,
    }
    row.update(values)
    return row


def samples(start, end, **values):
    return [sample(start + k / 10, **values) for k in range(round((end - start) * 10))]


def sections(*spans, seconds=200):
    return {
        "recording": "example",
        "seconds": seconds,
        "sample_hz": 10,
        "has_pad": True,
        "sections": [
            {"start": a, "end": b, "kind": kind, "wanted": 0, "route": [], "human": 0.5}
            for a, b, kind in spans
        ],
    }


def pad(t, buttons=(), left=(0.0, 0.0), right=(0.0, 0.0), l2=0.0, r2=0.0):
    """A controller line at picture time t; pad.jsonl times lead the picture by PAD_LEAD."""
    return {
        "t": round(t - PAD_LEAD, 3),
        "src": "human",
        "buttons": list(buttons),
        "left": list(left),
        "right": list(right),
        "l2": l2,
        "r2": r2,
    }


def reading(t, *lines):
    return {
        "t": t,
        "i": int(t * 60),
        "text": {
            "lines": [
                {"text": text, "confidence": 0.5, "box": box, "region": region} for text, box, region in lines
            ]
        },
    }


def run(rows, spans, pads=(), texts=(), readings=(), missions=None, seconds=200):
    return find_incidents(
        samples=rows,
        texts=list(texts),
        readings=list(readings),
        sections=sections(*spans, seconds=seconds),
        pads=list(pads),
        missions=missions or {"missions": []},
        seconds=seconds,
    )


def classes(found):
    return [(row["class"], row["cause"]) for row in found]


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("Franklin ist tot.", "player_died"),
        ("Lamar ist tot.", "ally_died"),
        ("Das Ziel ist entkommen.", "target_escaped"),
        ("Das Fahrzeug wurde zerstört.", "vehicle_destroyed"),
        ("Du wurdest entdeckt.", "seen"),
        ("Du hast das Gebiet verlassen.", "left_area"),
        ("Die Zeit ist abgelaufen.", "time_out"),
        ("Franklin hatte nicht genug Geld, um die Pump-Action-Schrotflinte zu kaufen.", "other"),
        ("", "unknown"),
    ],
)
def test_the_line_under_a_failure_banner_falls_into_a_closed_class(text, reason):
    assert failure_reason(text) == reason


def failed_mission(cross=True):
    """Play, the HUD gone at 50 s, the banner with "Franklin ist tot." from 52 to 57 s, loading, play."""
    rows = (
        samples(30, 50, red=2)
        + samples(50, 52, health=None, map="none", wanted=None)
        + samples(52, 57, screen="failed", health=None, map="none", wanted=None, lum=3.0)
        + samples(57, 59, screen="loading", health=None, map="none", wanted=None, lum=0.0)
        + samples(59, 80)
    )
    readings = [
        reading(
            t,
            ("mission FehLgeschLagen", [307, 299, 665, 62], "banner"),
            ("Franklin ist tot.", [581, 384, 118, 13], "menu"),
            ("Vèrlassen", [999, 667, 53, 9], "phone"),
        )
        for t in (52.5, 53.0, 53.5, 54.0)
    ]
    texts = [{"kind": "banner", "text": "mission FehLgeschLagen", "first": 52.5, "last": 56.5}]
    missions = {
        "missions": [
            {
                "start": 31,
                "end": 52.5,
                "ending": "failed",
                "steps": [
                    {"objective": "Sammle eine Waffe auf.", "start": 31, "end": 40},
                    {"objective": "Schalte die Vagos aus.", "start": 40, "end": 52.5},
                ],
            },
            {
                "start": 60,
                "end": 80,
                "ending": "unknown",
                "steps": [{"objective": "Schalte die Vagos aus.", "start": 60, "end": 80}],
            },
        ]
    }
    button = "cross" if cross else "circle"
    pads = [pad(30, r2=1.0), pad(31), pad(54.5, buttons=[button]), pad(54.7)]
    return run(
        rows, [(30, 50, "foot"), (50, 59, "banner"), (59, 80, "foot")], pads, texts, readings, missions
    )


def test_a_failure_naming_the_player_is_a_death_a_failure_and_a_retry_from_the_checkpoint():
    found = failed_mission()
    assert classes(found) == [
        ("death", "fight"),
        ("mission_failed", "player_died"),
        ("retry", "checkpoint"),
    ]
    death, failure, retry = found
    assert death["t"] == pytest.approx(49.9)
    assert failure["evidence"]["reason"] == "Franklin ist tot."
    assert failure["then"] == "retry"
    assert (failure["mission"], failure["step"]) == (1, 2)
    assert retry["t"] == pytest.approx(59.0)


def test_leaving_the_failed_mission_is_no_retry():
    found = failed_mission(cross=False)
    assert ("retry", "checkpoint") not in classes(found)
    assert next(row for row in found if row["class"] == "mission_failed")["then"] == "quit"


def driving(start, end, speed):
    return samples(start, end, map="tilted", move=speed)


def test_a_sudden_stop_with_the_throttle_held_is_a_collision_and_braking_is_not():
    rows = driving(0, 10, 40.0) + driving(10, 12, 0.5) + driving(12, 20, 40.0)
    spans = [(0, 20, "drive")]
    throttle = [pad(0, r2=1.0)]
    found = run(rows, spans, throttle)
    assert classes(found) == [("collision", "carried_on")]
    assert found[0]["t"] == pytest.approx(10.0)
    assert found[0]["kind"] == "standstill"

    braking = [pad(0, r2=1.0), pad(8.5, l2=1.0), pad(10.2, r2=1.0)]
    assert run(rows, spans, braking) == []


def test_single_repeated_frames_at_speed_are_no_collision():
    rows = driving(0, 20, 40.0)
    for row in rows[::7]:
        row["move"] = 0.0
    assert run(rows, [(0, 20, "drive")], [pad(0, r2=1.0)]) == []


def test_after_a_collision_he_leaves_the_car():
    rows = driving(0, 10, 40.0) + driving(10, 14, 0.2) + samples(14, 20, move=5.0)
    found = run(
        rows, [(0, 14, "drive"), (14, 20, "foot")], [pad(0, r2=1.0), pad(10.5), pad(13, buttons=["triangle"])]
    )
    assert classes(found)[0] == ("collision", "left_car")


def test_a_wanted_level_lasts_from_the_first_lasting_star_to_the_first_lasting_zero():
    rows = samples(0, 10) + samples(10, 40, wanted=2) + samples(40, 60)
    rows[50]["wanted"] = 3  # one odd reading does not raise the level
    found = run(rows, [(0, 60, "foot")])
    assert classes(found) == [("wanted", "lost")]
    assert found[0]["seconds"] == pytest.approx(30.0, abs=0.2)
    assert found[0]["level"] == 2


def test_a_single_star_reading_is_no_wanted_level():
    rows = samples(0, 30)
    rows[100]["wanted"] = 1
    assert run(rows, [(0, 30, "foot")]) == []


def test_stars_that_end_with_a_cutscene_were_cleared_by_the_mission():
    rows = samples(0, 20, wanted=1) + samples(20, 30, wanted=None, map="none") + samples(30, 40)
    found = run(rows, [(0, 20, "foot"), (20, 30, "cutscene"), (30, 40, "foot")])
    assert classes(found) == [("wanted", "mission_end")]


def test_ten_seconds_still_with_the_stick_pushed_is_a_standstill_and_without_the_hand_it_is_not():
    rows = samples(0, 5, move=8.0) + samples(5, 18, move=0.2) + samples(18, 25, move=8.0)
    pushed = [pad(0, left=(0.0, -0.9)), pad(0.5, left=(0.0, -1.0))]
    found = run(rows, [(0, 25, "foot")], pushed)
    assert classes(found) == [("standstill", "stuck_foot")]
    assert found[0]["seconds"] >= 10
    assert run(rows, [(0, 25, "foot")], [pad(0), pad(0.5)]) == []


def test_a_long_reverse_is_counted_and_a_short_one_is_not():
    rows = driving(0, 20, 10.0)
    long = [pad(0), pad(5, l2=1.0), pad(9)]
    short = [pad(0), pad(5, l2=1.0), pad(6)]
    assert classes(run(rows, [(0, 20, "drive")], long)) == [("reverse", "reverse")]
    assert run(rows, [(0, 20, "drive")], short) == []


def test_the_pad_is_read_on_the_picture_clock():
    controller = Pad([{"t": 1.0, "src": "human", "buttons": ["cross"]}])
    assert controller.at(1.0 + PAD_LEAD - 0.01) is None
    assert controller.at(1.0 + PAD_LEAD)["buttons"] == ["cross"]


def test_incidents_are_added_to_their_steps_and_nothing_else_changes():
    missions = {
        "missions": [{"start": 0, "end": 20, "steps": [{"objective": "Folge Lamar.", "start": 0, "end": 20}]}]
    }
    found = [{"t": 5.0, "class": "collision", "cause": "carried_on", "mission": 1, "step": 1}]
    result = attach_to_missions(missions, found)
    step = result["missions"][0]["steps"][0]
    assert step["incidents"] == [{"t": 5.0, "class": "collision", "cause": "carried_on"}]
    assert step["objective"] == "Folge Lamar." and step["end"] == 20


def test_a_recording_without_controller_lines_is_read_from_the_picture_alone():
    rows = driving(0, 10, 40.0) + driving(10, 12, 0.5) + driving(12, 30, 40.0) + samples(30, 50, wanted=1)
    rows += samples(50, 55)
    found = run(rows, [(0, 30, "drive"), (30, 55, "foot")], [pad(0)])
    assert classes(found) == [("collision", "carried_on"), ("wanted", "lost")]
