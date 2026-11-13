from dataclasses import replace

import pytest

from pilot.contract import NEUTRAL_PAD, Hud, Observation, Reading
from pilot.flow import Flow
from pilot.scene import SceneText, TextLine

READING = Reading("tilted", "none", None, None, None, False, 1)


def obs(t, screen="game"):
    return Observation(READING, True, t, hud=Hud(screen=screen))


def failure(flow, start, footer="Erneut versuchen Überspringen"):
    flow.tick(obs(start, "failed"), footer)
    return flow.tick(obs(start + 0.1, "failed"), footer)


def recover(flow, start):
    flow.tick(obs(start))
    flow.tick(obs(start + 0.4))


def mission(flow, start, name):
    text = SceneText(banner=name, objective="Drive to the warehouse")
    flow.tick(obs(start), text)
    flow.tick(obs(start + 0.4), text)


def test_third_failure_skips_only_when_offered_and_emits_once():
    flow = Flow()
    mission(flow, 0, "The long stretch")
    assert failure(flow, 1).action == "retry"
    recover(flow, 2)
    assert failure(flow, 3).action == "retry"
    recover(flow, 4)
    result = failure(flow, 5)
    assert result.action == "skip"
    assert result.pad.buttons == ("square",)
    assert [e["kind"] for e in result.events] == ["failure", "mission_skip"]
    assert flow.tick(obs(5.15, "failed"), "Überspringen").events == ()
    assert flow.tick(obs(5.25, "failed"), "Überspringen").pad == NEUTRAL_PAD


@pytest.mark.parametrize(
    "skip,footer", [(False, "Erneut versuchen Überspringen"), (True, "Erneut versuchen")]
)
def test_skip_requires_option_and_enabled_policy(skip, footer):
    flow = Flow(skip=skip)
    mission(flow, 0, "The long stretch")
    for t in (1, 3, 5, 7):
        result = failure(flow, t, footer)
        assert result.action == "retry"
        assert result.pad.buttons == ("cross",)
        recover(flow, t + 1)


@pytest.mark.parametrize("reset", ["passed", "mission", "play"])
def test_failure_streak_reset(reset):
    flow = Flow()
    mission(flow, 0, "The long stretch")
    failure(flow, 1)
    recover(flow, 2)
    failure(flow, 3)
    recover(flow, 4)
    if reset == "passed":
        flow.tick(obs(5, "passed"))
        flow.tick(obs(5.1, "passed"))
        recover(flow, 6)
    elif reset == "mission":
        mission(flow, 5, "Complications")
    else:
        flow.tick(obs(605))
    result = failure(flow, 607)
    assert result.action == "retry"
    assert flow.failures_in_row == 1


def alert(footer="Weiter X", body="Die Verbindung zu den Spieldiensten wurde unterbrochen."):
    return SceneText(
        lines=(
            TextLine("ALARM", 0.99, (540, 180, 160, 40), "banner"),
            TextLine(body, 0.99, (300, 320, 680, 40), "banner"),
            TextLine(footer, 0.99, (1070, 665, 140, 20), "bottom"),
        )
    )


def test_single_continue_alert_is_detected_from_lines_and_pressed_once_after_two_seconds():
    flow = Flow()
    text = alert()
    for t in (0, 0.1, 1, 2):
        assert flow.tick(obs(t), text).pad == NEUTRAL_PAD
    assert flow.tick(obs(2.11), text).pad.buttons == ("cross",)
    assert flow.tick(obs(2.14), text).pad.buttons == ("cross",)
    assert flow.tick(obs(2.25), text).pad == NEUTRAL_PAD
    result = flow.tick(obs(4.2), text)
    assert result.action == "stuck"
    assert result.pad == NEUTRAL_PAD
    assert flow.tick(obs(5), text).pad == NEUTRAL_PAD


@pytest.mark.parametrize(
    "body", ["GTA Online", "Im Store kaufen", "Spiel speichern?", "$100", "Save game", "Ja Nein"]
)
def test_risky_alert_never_confirms(body):
    flow = Flow()
    text = alert(body=body)
    flow.tick(obs(0), text)
    result = flow.tick(obs(0.1), text)
    assert result.action == "stuck"
    for t in (0.2, 3, 8):
        assert flow.tick(obs(t), text).pad == NEUTRAL_PAD


def test_choice_alert_and_plain_game_subtitle_are_not_confirmed():
    flow = Flow()
    text = alert("Weiter X Zurück O")
    flow.tick(obs(0), text)
    assert flow.tick(obs(0.1), text).action == "stuck"
    ordinary = replace(text, lines=text.lines[1:])
    flow = Flow()
    for t in (0, 0.1, 3):
        assert flow.tick(obs(t), ordinary) is None


def test_skip_is_not_repeated_when_its_outcome_is_unknown():
    flow = Flow()
    mission(flow, 0, "The long stretch")
    for t in (1, 3):
        failure(flow, t)
        recover(flow, t + 1)
    assert failure(flow, 5).action == "skip"
    result = flow.tick(obs(7.2, "failed"), "Überspringen")
    assert result.action == "stuck"
    assert result.pad == NEUTRAL_PAD


@pytest.mark.parametrize(
    "text", ["Continue retry", "Continue select", "Weiter Optionen", "Weiter X Zurück O"]
)
def test_unstructured_alert_does_not_guess_a_single_choice(text):
    flow = Flow()
    flow.tick(obs(0, "alert"), text)
    result = flow.tick(obs(0.1, "alert"), text)
    assert result.action == "stuck"
    assert result.pad == NEUTRAL_PAD


def test_damaged_alert_frame_cannot_confirm_or_count_toward_dwell():
    flow = Flow()
    text = alert()
    flow.tick(obs(0), text)
    flow.tick(obs(0.1), text)
    damaged = replace(obs(2.1), reading=replace(READING, corrupt=True))
    assert flow.tick(damaged, text).pad == NEUTRAL_PAD
    for t in (2.2, 2.3, 3):
        assert flow.tick(obs(t), text).pad == NEUTRAL_PAD


def test_skip_word_in_a_help_banner_is_not_a_footer_offer():
    flow = Flow()
    mission(flow, 0, "The long stretch")
    for t in (1, 3):
        failure(flow, t)
        recover(flow, t + 1)
    text = SceneText(
        help="Überspringen",
        subtitle="Erneut versuchen",
        lines=(
            TextLine("Überspringen", 0.99, (30, 30, 150, 20), "help"),
            TextLine("Erneut versuchen", 0.99, (900, 665, 250, 20), "bottom"),
        ),
    )
    flow.tick(obs(5, "failed"), text)
    result = flow.tick(obs(5.1, "failed"), text)
    assert result.action == "retry"
    assert result.pad.buttons == ("cross",)


def test_recorded_low_confidence_skip_spelling_is_recognized():
    flow = Flow()
    mission(flow, 0, "Nervous Ron")
    for t in (1, 3):
        failure(flow, t)
        recover(flow, t + 1)
    # 20261112-130333, OCR frame 102382 at source t=1764.5934.
    text = SceneText(lines=(TextLine("Uberspringèn", 0.5, (887, 667, 74, 12), "bottom"),))
    flow.tick(obs(5, "failed"), text)
    result = flow.tick(obs(5.1, "failed"), text)
    assert result.action == "skip"
    assert result.pad.buttons == ("square",)


def test_single_low_confidence_skip_read_is_not_pressed():
    flow = Flow()
    flow.failures_in_row = 3
    flow.tick(
        obs(0, "failed"), SceneText(lines=(TextLine("Uberspringèn", 0.5, (887, 667, 74, 12), "bottom"),))
    )
    result = flow.tick(obs(0.1, "failed"), SceneText())
    assert result.pad == NEUTRAL_PAD
