"""A shop's menu nobody asked for: the reflex leaves it by the way back, and never by anything else."""

from itertools import pairwise

from pilot.contract import NEUTRAL_PAD, Hud, Observation, Pad, Reading
from pilot.flow import MENU_LEVELS, Flow
from pilot.scene import SceneText, TextLine

NO_MAP = Reading("none", "none", None, None, None, False, 1)
MAP = Reading("flat", "none", None, None, 0.0, False, 1)
# The footers as the reader gave them on Kerim's recordings of 11 November.
AMMU = SceneText(
    lines=(
        TextLine("ZurÖck O Kaufen", 0.5, (1071, 663, 114, 18), "phone"),
        TextLine("Zth)men IFJ Ansehèn", 0.5, (666, 665, 131, 14), "subtitle"),
    )
)
WARDROBE = SceneText(lines=(TextLine("ZurÖek O Auswahlen", 0.5, (1051, 663, 135, 18), "phone"),))
SCENE = SceneText(
    lines=(TextLine("Komm zurück, du Idiot!", 0.5, (480, 640, 320, 21), "subtitle"),),
    subtitle="Komm zurück, du Idiot!",
)
PLAIN = SceneText()


def obs(t, reading=NO_MAP, screen="game"):
    return Observation(reading, True, t, hud=Hud(screen=screen))


def run(flow, start, end, text, reading=NO_MAP, step=1 / 30):
    """Every result between two times, with the times a button went down."""
    results, presses, down = [], [], False
    t = start
    while t < end:
        result = flow.tick(obs(t, reading), text)
        results.append(result)
        pressed = result is not None and bool(result.pad.buttons)
        if pressed and not down:
            presses.append((round(t, 2), result.pad.buttons))
        down = pressed
        t += step
    return results, presses


def test_a_menu_left_open_is_backed_out_of_after_its_seconds():
    flow = Flow()
    results, presses = run(flow, 0.0, 3.9, AMMU)
    assert presses == []
    assert {result.action for result in results} <= {"confirm", "observe"}
    results, presses = run(flow, 3.9, 4.5, AMMU)
    assert [buttons for _, buttons in presses] == [("circle",)]
    held = [result for result in results if result.pad.buttons]
    assert 2 <= len(held) <= 4  # a press the console can see, and no longer


def test_each_level_gets_one_press_and_then_the_head_is_told():
    flow = Flow()
    results, presses = run(flow, 0.0, 14.0, AMMU)
    assert [buttons for _, buttons in presses] == [("circle",)] * MENU_LEVELS
    times = [t for t, _ in presses]
    assert all(later - earlier >= 0.99 for earlier, later in pairwise(times))
    stuck = [event for result in results for event in result.events if event["kind"] == "stuck"]
    assert stuck == [{"kind": "stuck", "screen": "shop_menu"}]
    assert results[-1].action == "stuck" and results[-1].pad == NEUTRAL_PAD


def test_the_reflex_lets_go_when_the_map_is_back():
    flow = Flow()
    run(flow, 0.0, 4.3, WARDROBE)
    results, presses = run(flow, 4.3, 6.0, PLAIN, MAP)
    assert presses == []
    assert results[-1] is None
    assert flow.screen in {None, "game"}


def test_a_scene_that_says_zurueck_is_no_menu():
    flow = Flow()
    results, presses = run(flow, 0.0, 12.0, SCENE)
    assert presses == [] and all(result is None for result in results)


def test_a_failed_mission_read_as_the_game_is_never_left_by_the_circle():
    text = SceneText(
        lines=(
            TextLine("Zurück O Erneut versuchen", 0.5, (1010, 663, 190, 18), "phone"),
            TextLine("Mission fehlgeschlagen", 0.5, (400, 300, 480, 60), "banner"),
        ),
        banner="Mission fehlgeschlagen",
    )
    results, presses = run(Flow(), 0.0, 12.0, text)
    assert presses == [] and all(result is None for result in results)


def test_a_menu_with_the_map_on_screen_is_not_this_one():
    results, presses = run(Flow(), 0.0, 8.0, AMMU, MAP)
    assert presses == [] and all(result is None for result in results)


def test_a_skill_that_expects_the_menu_is_left_alone():
    flow = Flow()
    flow.expect("interaction_menu", "shop_menu", until=60.0)
    results, presses = run(flow, 0.0, 20.0, AMMU)
    assert presses == [] and all(result is None for result in results)
    # Its time is up with the menu still open: the reflex takes over.
    results, presses = run(flow, 60.0, 66.0, AMMU)
    assert presses and presses[0][1] == ("circle",)


def test_one_reading_without_the_footer_does_not_end_it_and_a_long_gap_does():
    flow = Flow()
    run(flow, 0.0, 3.0, AMMU)
    results, _ = run(flow, 3.0, 3.6, PLAIN)
    assert all(result is not None for result in results)
    results, presses = run(flow, 3.6, 4.6, AMMU)
    assert [buttons for _, buttons in presses] == [("circle",)]
    # No footer for two seconds and still no map: a scene, not the menu. Nothing more is pressed.
    results, presses = run(flow, 4.6, 12.0, PLAIN)
    assert presses == []
    assert results[-1] is None


def test_in_a_mission_the_head_is_told_first_and_nothing_is_pressed_in_its_seconds():
    flow = Flow()
    objective = SceneText(objective="Kauf dir einen Anzug")
    run(flow, 0.0, 1.0, objective, MAP)
    results, presses = run(flow, 1.0, 20.0, AMMU)
    assert presses == []
    stuck = [event for result in results for event in result.events if event["kind"] == "stuck"]
    assert stuck == [{"kind": "stuck", "screen": "shop_menu"}]
    first = next(index for index, result in enumerate(results) if result.action == "stuck")
    assert 1.2 <= first / 30 <= 1.5
    assert all(result.action == "stuck" for result in results[first:])
    # The head did nothing with it: after its seconds the menu is left after all.
    results, presses = run(flow, 20.0, 23.0, AMMU)
    assert presses and presses[0][1] == ("circle",)


def test_in_a_mission_a_menu_the_head_was_told_of_is_left_the_second_time():
    flow = Flow()
    run(flow, 0.0, 1.0, SceneText(objective="Kauf dir einen Anzug"), MAP)
    run(flow, 1.0, 3.0, AMMU)
    # The head's skill takes the menu, and ends with it still open.
    flow.expect("shop_menu", until=30.0)
    run(flow, 3.0, 10.0, AMMU)
    flow.end_expectation()
    results, presses = run(flow, 10.0, 15.0, AMMU)
    assert [event for result in results for event in result.events] == []
    assert presses and presses[0][1] == ("circle",) and presses[0][0] >= 13.9


def test_only_the_way_back_is_ever_pressed():
    for text in (AMMU, WARDROBE):
        for prepare in (False, True):
            flow = Flow()
            if prepare:
                run(flow, 0.0, 1.0, SceneText(objective="Geh zu Ammu-Nation"), MAP)
            results, _ = run(flow, 1.0, 60.0, text)
            assert {button for result in results for button in result.pad.buttons} <= {"circle"}
            assert all(result.pad in (NEUTRAL_PAD, Pad(buttons=("circle",))) for result in results)
