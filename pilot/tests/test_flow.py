from dataclasses import replace

import pytest

from pilot.contract import NEUTRAL_PAD, Hud, Reading
from pilot.flow import Flow
from pilot.skills import Observation

READING = Reading("tilted", "purple", 0.0, 0.0, 0.0, False, 1.0)


def observation(time, screen="game"):
    return Observation(READING, True, time, hud=Hud(screen=screen))


def enter(flow, screen, start=0.0, text=None):
    first = flow.tick(observation(start, screen), text)
    assert first.pad == NEUTRAL_PAD
    return flow.tick(observation(start + 0.1, screen), text)


def test_ordinary_play_and_missing_reader():
    flow = Flow()
    assert flow.tick(observation(0)) is None
    assert flow.tick(replace(observation(0.1), hud=None)) is None


@pytest.mark.parametrize("screen", ["failed", "pause", "map", "phone", "weapon_wheel", "passed", "loading"])
def test_one_tick_bad_screen_does_not_press(screen):
    flow = Flow()
    assert flow.tick(observation(0)) is None
    result = flow.tick(observation(0.1, screen), "X Retry | Circle Back")
    assert result.pad == NEUTRAL_PAD
    assert not result.events
    assert flow.tick(observation(0.2)).action == "confirm"
    assert flow.tick(observation(0.3)) is None


def test_the_retry_is_pressed_twice_at_most_and_then_the_screen_is_stuck():
    flow = Flow(response_timeout=0.5)
    text = "Erneut versuchen"
    result = enter(flow, "failed", text=text)
    assert result.pad.buttons == ("cross",)
    assert result.action == "retry"
    assert result.events == ({"kind": "failure", "screen": "failed", "count": 1},)
    for t in (0.2, 0.3, 0.5):
        assert flow.tick(observation(t, "failed"), text).pad == NEUTRAL_PAD
    # The picture did not change: the footer may not have been ready, so once more.
    assert flow.tick(observation(0.7, "failed"), text).pad.buttons == ("cross",)
    assert flow.tick(observation(1.0, "failed"), text).pad == NEUTRAL_PAD
    result = flow.tick(observation(1.3, "failed"), text)
    assert result.action == "stuck"
    assert result.events == ({"kind": "stuck", "screen": "failed"},)
    result = flow.tick(observation(10, "failed"), text)
    assert result.action == "stuck" and not result.events and result.pad == NEUTRAL_PAD
    for t in (10.1, 10.2, 10.3):
        assert flow.tick(observation(t)).pad == NEUTRAL_PAD
    assert flow.tick(observation(10.45)) is None


def test_a_press_lasts_three_ticks_of_the_loop_and_is_not_repeated():
    flow = Flow()
    flow.tick(observation(0.0, "pause"))
    pressed = [flow.tick(observation(0.1 + i / 30, "pause")).pad.buttons for i in range(9)]
    assert pressed == [("circle",)] * 3 + [()] * 6


def test_a_press_is_let_go_when_the_hud_reading_is_lost():
    flow = Flow()
    assert enter(flow, "pause").pad.buttons == ("circle",)
    assert flow.tick(replace(observation(0.13, "pause"), hud=None)).pad == NEUTRAL_PAD


@pytest.mark.parametrize("screen", ["pause", "map", "phone"])
def test_accidental_menus_back_out(screen):
    flow = Flow()
    result = enter(flow, screen, text="Circle Back")
    assert result.pad.buttons == ("circle",)
    assert result.action == "back"
    for t in (0.2, 0.3, 0.4):
        assert flow.tick(observation(t)).pad == NEUTRAL_PAD
    assert flow.tick(observation(0.55)) is None


def test_wheel_releases_held_controls():
    assert enter(Flow(), "weapon_wheel").action == "release"


@pytest.mark.parametrize("screen", ["passed", "loading", "wasted", "busted"])
def test_wait_screens_never_accept_a_prompt(screen):
    flow = Flow(wait_timeout=3)
    assert enter(flow, screen, text="X Retry").pad == NEUTRAL_PAD
    assert flow.tick(observation(1, screen), "Circle Back").action == "wait"
    assert flow.tick(observation(3.2, screen)).action == "stuck"
    for t in (3.3, 3.4, 3.5):
        assert flow.tick(observation(t)).pad == NEUTRAL_PAD
    assert flow.tick(observation(3.65)) is None


def test_expected_menu_expires_and_is_confirmed_again():
    flow = Flow()
    flow.expect("map", until=1)
    for t in (0, 0.1, 0.9):
        assert flow.tick(observation(t, "map"), "Circle Back") is None
    assert flow.tick(observation(1, "map"), "Circle Back").pad == NEUTRAL_PAD
    assert flow.tick(observation(1.1, "map"), "Circle Back").pad.buttons == ("circle",)
    with pytest.raises(ValueError):
        flow.expect("failed", until=3)


def test_expected_menu_does_not_hide_failure():
    flow = Flow()
    flow.expect("map", until=20)
    assert enter(flow, "failed", text="X Retry").action == "retry"


def test_failures_count_once_and_pass_resets():
    flow = Flow()
    enter(flow, "failed")
    assert not flow.tick(observation(0.2, "failed")).events
    flow.tick(observation(0.3))
    flow.tick(observation(0.4))
    assert flow.tick(observation(0.7)) is None
    result = enter(flow, "failed", 1)
    assert result.events[0]["count"] == 2
    result = enter(flow, "passed", 2)
    assert result.events == ({"kind": "pass", "time": 2.1},)
    assert flow.failures_in_row == 0
    assert flow.last_pass == 2.1
    assert not flow.tick(observation(2.2, "passed")).events


def test_missing_hud_and_wrong_game_cannot_release_active_plan():
    flow = Flow()
    enter(flow, "failed", text="X Retry")
    assert flow.tick(replace(observation(0.2), hud=None)).pad == NEUTRAL_PAD
    assert flow.tick(observation(0.3)).pad == NEUTRAL_PAD
    assert flow.tick(observation(0.4, "failed"), "X Retry").pad == NEUTRAL_PAD
    assert flow.tick(observation(0.5, "failed"), "X Retry").pad == NEUTRAL_PAD


def test_duplicate_timestamps_do_not_confirm():
    flow = Flow()
    assert flow.tick(observation(0, "failed"), "X Retry").pad == NEUTRAL_PAD
    assert flow.tick(observation(0, "failed"), "X Retry").pad == NEUTRAL_PAD
    assert flow.tick(observation(0.1, "failed"), "X Retry").pad.buttons == ("cross",)


@pytest.mark.parametrize(
    "text", ["R1 Back", "X Skip", "Circle Delete", "Verlassen O", "MISSION FEHLGESCHLAGEN"]
)
def test_nothing_is_pressed_on_a_failure_before_the_retry_is_offered(text):
    flow = Flow()
    assert enter(flow, "failed", text=text).pad == NEUTRAL_PAD
    assert flow.tick(observation(31, "failed"), text).action == "stuck"


@pytest.mark.parametrize(
    "text",
    [
        # As the text reader returned it at t=36.43 of recording 093238: the cross is not read.
        "Franklin ist tot. Verlassen O Erneut versuchen",
        "Verlassen ○ Erneut versuchen",
        "Erneut versuchen ○ Verlassen",
        "Erneut versuchen",
        "Circle Retry",
    ],
)
def test_the_retry_is_cross_whatever_glyph_the_reader_puts_next_to_it(text):
    flow = Flow()
    pads = [enter(flow, "failed", text=text)] + [
        flow.tick(observation(0.1 + tick / 30, "failed"), text) for tick in range(1, 90)
    ]
    assert pads[0].pad.buttons == ("cross",)
    assert all(set(result.pad.buttons) <= {"cross"} for result in pads)


def test_a_map_is_left_with_circle_although_its_footer_reads_x_before_back():
    # As read at t=388.49 of recording 093238; cross here would set a waypoint.
    text = "Stripclub A Unterschlupf 9 Wegpunkt X Zurück l O"
    flow = Flow()
    pads = [enter(flow, "map", text=text)] + [
        flow.tick(observation(0.1 + tick / 30, "map"), text) for tick in range(1, 90)
    ]
    assert pads[0].pad.buttons == ("circle",)
    assert all(set(result.pad.buttons) <= {"circle"} for result in pads)


def test_a_confirmed_screen_is_not_gone_after_two_frames_of_game():
    flow = Flow()
    assert enter(flow, "phone").pad.buttons == ("circle",)
    # The reader called the visible phone "game" twice at t=153.70 of recording 093238.
    assert flow.tick(observation(0.20)).pad == NEUTRAL_PAD
    assert flow.tick(observation(0.23)).pad == NEUTRAL_PAD
    assert flow.tick(observation(0.26, "phone")) is not None
    assert flow.tick(observation(0.30)).pad == NEUTRAL_PAD
    assert flow.tick(observation(0.45)).pad == NEUTRAL_PAD
    assert flow.tick(observation(0.61)) is None


def test_one_tick_wrong_text_does_not_press():
    flow = Flow()
    enter(flow, "failed")
    assert flow.tick(observation(0.2, "failed"), "X Retry").pad == NEUTRAL_PAD
    assert flow.tick(observation(0.3, "failed")).pad == NEUTRAL_PAD


@pytest.mark.parametrize(
    "screen",
    [
        "game",
        "failed",
        "passed",
        "loading",
        "pause",
        "map",
        "phone",
        "weapon_wheel",
        "wasted",
        "busted",
        "unknown",
    ],
)
def test_every_result_has_no_sticks_triggers_or_shoulders(screen):
    flow = Flow()
    for tick in range(50):
        result = flow.tick(observation(tick / 10, screen), "X Retry | Circle Back | L1 Close")
        if result:
            assert result.pad.left == result.pad.right == (0.0, 0.0)
            assert result.pad.l2 == result.pad.r2 == 0
            assert set(result.pad.buttons) <= {"cross", "circle"}


def test_scene_text_fields():
    from pilot.scene import SceneText

    result = enter(Flow(), "phone", text=SceneText(phone_menu="Schließen ○"))
    assert result.pad.buttons == ("circle",)


def test_banner_before_retry_footer_waits_for_choices():
    flow = Flow()
    enter(flow, "failed", text="MISSION FAILED")
    assert flow.tick(observation(3.0, "failed"), "MISSION FAILED").pad == NEUTRAL_PAD
    assert flow.tick(observation(3.1, "failed"), "Retry X").pad == NEUTRAL_PAD
    assert flow.tick(observation(3.2, "failed"), "Retry X").pad.buttons == ("cross",)


def test_recorded_nested_map_then_pause_each_gets_one_back():
    flow = Flow()
    assert enter(flow, "map").pad.buttons == ("circle",)
    assert flow.tick(observation(0.2, "map")).pad == NEUTRAL_PAD
    assert flow.tick(observation(0.3, "pause")).pad == NEUTRAL_PAD
    assert flow.tick(observation(0.4, "pause")).pad.buttons == ("circle",)


def test_repeated_ordinary_timestamp_stays_ordinary():
    flow = Flow()
    assert flow.tick(observation(0)) is None
    assert flow.tick(observation(0)) is None


def test_missing_reader_after_first_warning_keeps_controls_neutral():
    flow = Flow()
    flow.tick(observation(0, "failed"), "X Retry")
    for time in (0.1, 0.2):
        assert flow.tick(replace(observation(time), hud=None)).pad == NEUTRAL_PAD
    assert flow.tick(observation(0.3, "failed"), "X Retry").pad == NEUTRAL_PAD
    assert flow.tick(observation(0.4, "failed"), "X Retry").pad.buttons == ("cross",)
