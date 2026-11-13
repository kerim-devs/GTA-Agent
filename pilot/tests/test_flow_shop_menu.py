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
    results, presses = run(flow, 0.0, 4.1, AMMU)
    assert presses == []
    # For its first second and more the footer is not a menu yet, and no skill is disturbed by it.
    assert all(result is None for result in results[:30])
    assert {result.action for result in results if result is not None} <= {"confirm", "observe"}
    results, presses = run(flow, 4.1, 4.8, AMMU)
    assert [buttons for _, buttons in presses] == [("circle",)]
    held = [result for result in results if result.pad.buttons]
    assert 2 <= len(held) <= 4  # a press the console can see, and no longer


def test_each_level_gets_one_press_and_then_the_head_is_told():
    flow = Flow()
    results, presses = run(flow, 0.0, 16.0, AMMU)
    assert [buttons for _, buttons in presses] == [("circle",)] * MENU_LEVELS
    times = [t for t, _ in presses]
    assert all(later - earlier >= 0.99 for earlier, later in pairwise(times))
    results = [result for result in results if result is not None]
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
    results, presses = run(flow, 1.0, 21.0, AMMU)
    assert presses == []
    stuck = [
        event
        for result in results
        if result is not None
        for event in result.events
        if event["kind"] == "stuck"
    ]
    assert stuck == [{"kind": "stuck", "screen": "shop_menu"}]
    first = next(i for i, result in enumerate(results) if result is not None and result.action == "stuck")
    assert 1.2 <= first / 30 <= 1.5
    assert all(result.action == "stuck" for result in results[first:])
    # The head did nothing with it: after its seconds the menu is left after all.
    results, presses = run(flow, 21.0, 25.0, AMMU)
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
    assert [event for result in results if result is not None for event in result.events] == []
    assert presses and presses[0][1] == ("circle",) and presses[0][0] >= 13.0


def test_only_the_way_back_is_ever_pressed():
    for text in (AMMU, WARDROBE):
        for prepare in (False, True):
            flow = Flow()
            if prepare:
                run(flow, 0.0, 1.0, SceneText(objective="Geh zu Ammu-Nation"), MAP)
            results, _ = run(flow, 1.0, 60.0, text)
            results = [result for result in results if result is not None]
            assert {button for result in results for button in result.pad.buttons} <= {"circle"}
            assert all(result.pad in (NEUTRAL_PAD, Pad(buttons=("circle",))) for result in results)


def test_the_footer_of_a_map_just_closed_is_not_a_menu():
    # The text is read half a second behind the picture: a skill has closed the map, the screen is
    # the game's, the minimap is not back yet and the map's footer still stands in the text.
    footer = SceneText(lines=(TextLine("Wegpunkt X Zurück O", 0.5, (1010, 663, 190, 18), "phone"),))
    flow = Flow()
    results, presses = run(flow, 0.0, 1.0, footer)
    assert presses == [] and all(result is None for result in results)
    results, presses = run(flow, 1.0, 3.0, PLAIN, MAP)
    assert presses == [] and all(result is None for result in results)


def test_while_a_skill_has_its_own_screen_open_nothing_is_a_menu_left_open():
    flow = Flow()
    flow.expect("pause", "map", until=30.0)
    results, presses = run(flow, 0.0, 8.0, AMMU)
    assert presses == [] and all(result is None for result in results)


def test_a_footer_read_before_the_last_press_proves_nothing():
    """The first press closed the menu; the reader is slow and the old text is all there is."""
    flow = Flow()
    t, first = 0.0, None
    while first is None and t < 6.0:  # the footer, read from pictures as they come
        result = flow.tick(obs(t), AMMU, text_time=t - 0.1)
        if result is not None and result.pad.buttons:
            first = t
        t += 1 / 30
    assert first is not None
    presses = []
    while t < first + 1.45:  # no map yet, and no text newer than the one from before the press
        result = flow.tick(obs(t), AMMU, text_time=first - 0.1)
        if result is not None and result.pad.buttons and t - first > 0.2:
            presses.append(round(t, 2))
        t += 1 / 30
    assert presses == []
    # A reading taken after the press still shows the footer: the menu has another level.
    again = None
    while again is None and t < first + 4.0:
        result = flow.tick(obs(t), AMMU, text_time=t - 0.1)
        if result is not None and result.pad.buttons:
            again = t
        t += 1 / 30
    assert again is not None


def test_a_reset_forgets_what_was_pressed_into_a_pad_that_was_not_the_pilots():
    flow = Flow()
    _, presses = run(flow, 0.0, 16.0, AMMU)
    assert len(presses) == MENU_LEVELS  # and stuck from here
    flow.reset()
    _, presses = run(flow, 16.0, 22.0, AMMU)
    assert presses and presses[0][1] == ("circle",)
