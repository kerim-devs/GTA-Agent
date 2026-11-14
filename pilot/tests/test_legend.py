import json
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pilot.contract import NEUTRAL_PAD, Hud, Observation, Reading
from pilot.head import parse_response, response_schema
from pilot.legend import Entry, Legend, kind_of, read_legend
from pilot.waypoint import SetWaypoint


def line(text, y, x=1050):
    return {"text": text, "box": [x, y, 160, 14], "confidence": 1.0}


def lines(names, selected=0, offset=0, distance=None, total=None, instance=1):
    rows = []
    for i, name in enumerate(names):
        text = name
        if i + offset == selected and name != "Spieler":
            text += f" < {instance}/7 > q"
        rows.append(line(text, 42 + i * 26))
    if distance is not None:
        rows.insert(0, line(f"Wegpunkt ({distance}m)", 28))
    rows += [line(f"{selected + 1}/{total or len(names)}", 556)]
    rows += [line("Markierung wählen", 666, 520), line("Wegpunkt", 666)]
    return rows


class Model:
    """The legend as the recording by hand shows it: a waypoint adds a row under the player's."""

    def __init__(self, names, *, lost=(), stuck=False, confirm=True, wrong_menu=False, moves=True, double=()):
        self.names = names
        self.screen = "game"
        self.selected = 0  # among rows()
        self.instance = 1
        self.distance = None  # of the waypoint that stands
        self.moves = moves  # a cross on another place moves a waypoint; otherwise it only takes it away
        self.double = set(double)  # presses that the game takes for two
        self.lingering = None  # the old waypoint's row, which the legend shows on beside the new one
        self.linger = 0
        self.previous = ()
        self.presses = []
        self.lost = set(lost)
        self.stuck = stuck
        self.confirm = confirm
        self.wrong_menu = wrong_menu
        self.scroll_seen = False
        self.house = False  # whether the map opens on the plan of a house

    def picture(self, frame):
        if self.screen == "pause":
            return read_legend([line("KARTE", 100, 100)])
        if self.screen == "interior":
            rooms = lines(["Spieler", "Kleidung", "Persönliches Fahrzeug", "Yoga"], 0, 0, None, 4, 1)
            return replace(read_legend(rooms), screen="interior")
        if self.screen == "wrong":
            return read_legend([line("STATISTIKEN", 100, 100)])
        if self.lingering is not None:
            self.linger -= 1
            if self.linger <= 0:
                self.lingering = None
                self.selected -= 1
        rows = self.rows()
        offset = (self.selected // 5) * 5
        self.scroll_seen |= offset > 0
        legend = read_legend(
            lines(rows[offset : offset + 5], self.selected, offset, None, len(rows), self.instance)
        )
        if legend.selected is None and self.selected - offset < len(legend.entries):
            # The white bar, for which the model has no picture.
            legend = replace(legend, selected=legend.entries[self.selected - offset])
        return legend

    def rows(self):
        waypoints = [f"Wegpunkt ({value}m)" for value in (self.distance, self.lingering) if value is not None]
        return [self.names[0], *waypoints, *self.names[1:]]

    def observation(self, tick, *, corrupt=False):
        game = self.screen == "game"
        frame = np.full((4, 4, 3), tick % 255, dtype=np.uint8)
        reading = Reading("tilted" if game else "none", "none", None, None, None, corrupt, 1.0)
        return Observation(reading, False, tick * 0.05, frame, hud=Hud(screen="game" if game else "pause"))

    def apply(self, result):
        buttons = result.pad.buttons
        if buttons and buttons != self.previous:
            button = buttons[0]
            self.presses.append(button)
            if len(self.presses) not in self.lost:
                if button == "options" and self.screen == "game":
                    self.screen = "wrong" if self.wrong_menu else "pause"
                elif button == "cross" and self.screen == "pause":
                    self.screen = "interior" if self.house else "map"
                elif button == "touchpad" and self.screen == "interior":
                    self.screen = "map"
                elif button == "circle":
                    self.screen = "pause" if self.screen in {"map", "interior"} else "game"
                elif self.screen == "map":
                    rows = self.rows()
                    if button in {"up", "down"} and not self.stuck:
                        step = 2 if len(self.presses) in self.double else 1
                        self.selected = (self.selected + (step if button == "down" else -step)) % len(rows)
                    elif button in {"left", "right"} and not self.stuck:
                        self.instance += 1 if button == "right" else -1
                    elif (
                        button == "cross" and self.confirm and not rows[self.selected].startswith("Wegpunkt")
                    ):
                        if self.distance is None:
                            self.distance = 532
                            self.selected += 1  # the new row pushes the selected one down
                        elif self.moves and self.distance != 532:
                            self.lingering, self.linger = self.distance, 25
                            self.distance = 532
                            self.selected += 1
                        else:
                            self.distance = None
                            self.selected -= 1
        self.previous = buttons


def run(args, model, corrupt=()):
    skill = SetWaypoint(args)
    skill.legend._picture = model.picture
    outputs = []
    for tick in range(1000):
        result = skill.step(model.observation(tick, corrupt=tick in corrupt))
        outputs.append(result)
        model.apply(result)
        if result.status != "running":
            assert result.pad == NEUTRAL_PAD
            return skill, result, outputs
    pytest.fail("skill did not terminate")


@pytest.mark.parametrize(
    "args, expected",
    [
        ({"place": "Friseursalon"}, "Friseursalon"),
        ({"kind": "shop"}, "Ammu-Nation"),
        ({"kind": "mission"}, "Fremde und Freaks"),
        ({"kind": "pastime"}, "Golf"),
        ({"place": "Unlisted place"}, "Unlisted place"),
    ],
)
def test_reaches_destination_with_scrolling_and_lost_presses(args, expected):
    model = Model(
        [
            "Spieler",
            "Ammu-Nation",
            "Chinesen",
            "Golf",
            "Kino",
            "Fremde und Freaks",
            "Friseursalon",
            "Unlisted place",
        ],
        lost=(1, 3, 6),
    )
    skill, result, _ = run(args, model)
    assert result.status == "done", result.reason
    # On the model's second page the waypoint's row is out of sight and the counter is the proof.
    later = expected in {"Friseursalon", "Unlisted place", "Fremde und Freaks"}
    assert f"{expected} ({'distance not read' if later else '532m'})" in result.reason
    assert model.screen == "game"
    assert "Chinesen" in skill.legend.observed_places
    if expected in {"Friseursalon", "Unlisted place", "Fremde und Freaks"}:
        assert model.scroll_seen


@pytest.mark.parametrize(
    "args, model, reason",
    [
        ({"place": "Missing"}, Model(["Spieler", "Golf"]), "place-not-in-legend"),
        ({"kind": "shop"}, Model(["Spieler", "Chinesen"]), "place-not-in-legend"),
        ({"place": "Golf"}, Model(["Spieler", "Golf"], stuck=True), "legend-selection-did-not-move"),
        ({"place": "Golf"}, Model(["Spieler", "Golf"], confirm=False), "waypoint-not-visible-after-cross"),
        ({"place": "Golf", "instance": 9}, Model(["Spieler", "Golf"]), "place-instance-not-present"),
        (
            {"place": "Missing", "duration": 6},
            Model(["Spieler"] + [f"Place {i}" for i in range(40)]),
            "time-limit",
        ),
    ],
)
def test_failures_close_the_map(args, model, reason):
    _, result, _ = run(args, model)
    assert result.status == "failed"
    assert reason in result.reason
    assert "gameplay observed" in result.reason
    assert model.screen == "game"


def test_explicit_instance_and_interruption():
    model = Model(["Spieler", "Golf"], lost=(4,))
    skill, result, _ = run({"place": "Golf", "instance": 3}, model)
    assert result.status == "done", result.reason
    assert model.instance == 3
    assert skill.stop().pad == NEUTRAL_PAD


def test_in_a_house_the_view_is_changed_to_the_city_before_the_legend_is_read():
    # 20261114-043707: Michael in his house after a switch, the map on its rooms, 45 s of nothing.
    model = Model(["Spieler", "Golf", "Kino"])
    model.house = True
    _, result, _ = run({"place": "Kino"}, model)
    assert result.status == "done" and "Kino" in result.reason
    assert model.presses.count("touchpad") == 1


def test_unknown_menu_never_gets_a_button():
    model = Model(["Spieler", "Golf"], wrong_menu=True)
    _, result, _ = run({"place": "Golf"}, model)
    assert result.status == "failed"
    assert "menu-not-map" in result.reason
    assert model.presses == ["options"]


def test_recognised_wrong_pause_tab_is_closed_without_confirming():
    model = Model(["Spieler", "Golf"], wrong_menu=True)
    model.picture = lambda frame: Legend(screen="menu")
    _, result, _ = run({"place": "Golf"}, model)
    assert result.status == "failed"
    assert "menu-not-map" in result.reason
    assert model.screen == "game"
    assert model.presses == ["options", "circle"]


def test_native_picture_requires_the_selected_map_tab():
    skill = SetWaypoint({"place": "Golf"}).legend
    text = SimpleNamespace(
        lines=tuple(
            SimpleNamespace(text=name, box=(100, 100, 50, 14), confidence=1.0)
            for name in ("KARTE", "STATISTIKEN", "EINSTELLUNGEN", "SPIEL")
        )
    )
    skill.reader = SimpleNamespace(read=lambda frame: text)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[123:145, 355:490] = 255
    assert skill._picture(frame).screen == "menu"
    frame[123:145, 215:345] = 255
    assert skill._picture(frame).screen == "pause"


def test_lost_map_opening_is_retried_then_closed():
    model = Model(["Spieler", "Golf"], lost=(2, 3, 4))
    _, result, _ = run({"place": "Golf"}, model)
    assert result.status == "failed"
    assert "map-did-not-open" in result.reason
    assert model.screen == "game"
    assert model.presses == ["options", "cross", "cross", "cross", "circle"]


@pytest.mark.parametrize("lost", [(4,), (5, 6)])
def test_lost_confirmation_or_exit_press_is_retried_until_gameplay(lost):
    model = Model(["Spieler", "Golf"], lost=lost)
    _, result, _ = run({"place": "Golf"}, model)
    assert result.status == "done"
    assert model.screen == "game"


def test_ocr_failure_never_authorises_another_press():
    model = Model(["Spieler", "Golf"])

    def unreadable(frame):
        raise RuntimeError("native OCR unavailable")

    model.picture = unreadable
    _, result, _ = run({"place": "Golf", "duration": 6}, model)
    assert result.status == "failed"
    assert result.pad == NEUTRAL_PAD
    assert model.presses == ["options"]
    assert "gameplay not verified" in result.reason


def test_unverified_start_and_backward_clock_are_neutral():
    model = Model(["Spieler", "Golf"])
    model.screen = "map"
    _, result, _ = run({"place": "Golf"}, model)
    assert "start-screen-unverified" in result.reason
    assert not model.presses
    model.screen = "game"
    skill = SetWaypoint({"place": "Golf"})
    skill.step(model.observation(10))
    result = skill.step(model.observation(1))
    assert result.status == "failed"
    assert result.reason.startswith("clock-invalid")
    assert result.pad == NEUTRAL_PAD


@pytest.mark.parametrize("moves, crosses", [(True, 2), (False, 3)])
def test_a_waypoint_that_stands_elsewhere_is_replaced(moves, crosses):
    model = Model(["Spieler", "Golf"], moves=moves)
    model.distance = 99
    _, result, _ = run({"place": "Golf"}, model)
    assert result.status == "done", result.reason
    assert "Golf (532m)" in result.reason
    assert model.presses.count("cross") == crosses  # one opens the map
    assert model.distance == 532
    assert model.screen == "game"


def test_a_press_that_counts_twice_does_not_lose_the_place():
    # The third press is the first direction; it steps over Ammu-Nation, and the way back is up.
    model = Model(["Spieler", "Ammu-Nation", "Golf", "Kino"], double=(3,))
    _, result, _ = run({"place": "Ammu-Nation"}, model)
    assert result.status == "done", result.reason
    assert "Ammu-Nation (532m)" in result.reason
    assert model.presses.count("up") == 1


def test_a_waypoint_that_stands_on_the_place_itself_comes_back():
    model = Model(["Spieler", "Golf"])
    model.distance = 532
    _, result, _ = run({"place": "Golf"}, model)
    assert result.status == "done", result.reason
    assert model.presses.count("cross") == 3  # the map, the cross that took it away, the cross that set it
    assert model.distance == 532


def test_offered_instance_is_kept_by_default():
    model = Model(["Spieler", "Friseursalon"])
    model.instance = 6
    _, result, _ = run({"place": "Friseursalon"}, model)
    assert result.status == "done"
    assert model.instance == 6
    assert "left" not in model.presses and "right" not in model.presses


def test_frozen_frames_never_authorise_further_input():
    model = Model(["Spieler", "Golf"])
    skill = SetWaypoint({"place": "Golf", "duration": 6})
    skill.legend._picture = model.picture
    frozen = None
    for tick in range(200):
        observation = model.observation(tick)
        if frozen is not None:
            observation.frame[:] = frozen
        result = skill.step(observation)
        if result.pad.buttons and frozen is None:
            frozen = observation.frame.copy()
        model.apply(result)
        if result.status != "running":
            break
    assert result.status == "failed"
    assert result.pad == NEUTRAL_PAD
    assert model.presses == ["options"]
    assert "gameplay not verified" in result.reason


def test_a_waypoint_that_stood_on_a_later_pages_place_is_set_again_after_the_cross_took_it():
    # 20261114-064206: after a death on the way the waypoint still stood on the cinema, on the
    # legend's fourth page. The cross took it away, the counter fell by one, and the try ended unproven.
    names = ["Spieler", "Ammu-Nation", "Chinesen", "Golf", "Kino", "Fremde und Freaks", "Friseursalon"]
    model = Model(names)
    model.distance = 532  # the waypoint the game takes away at a cross on its own place
    _, result, _ = run({"place": "Friseursalon"}, model)
    assert result.status == "done", result.reason
    assert "Friseursalon" in result.reason and model.distance == 532 and model.screen == "game"


def test_missing_or_ambiguous_arrows_on_a_scrolled_page_are_unknown():
    rows = lines(["Golf", "Kino"], selected=6, offset=5, total=28)
    rows[1]["text"] = "Kino"
    assert read_legend(rows).selected is None
    rows[0]["text"] = "Golf < 1/2 >"
    rows[1]["text"] = "Kino < 1/3 >"
    assert read_legend(rows).selected is None


def test_a_direction_is_let_go_on_the_tick_after_its_press():
    model = Model(["Spieler", "Ammu-Nation", "Golf", "Kino"])
    observe = model.observation
    model.observation = lambda tick, corrupt=False: replace(observe(tick, corrupt=corrupt), time=tick * 0.12)
    _, result, outputs = run({"place": "Kino"}, model)
    assert result.status == "done", result.reason
    held = ["down" in output.pad.buttons for output in outputs]
    assert sum(held) == 3  # with the text reader in it a tick takes 0.08 to 0.17 s
    assert not any(a and b for a, b in pairwise(held))


def test_a_button_is_one_press_where_the_tick_after_it_is_slower_than_the_bridge_holds_a_pad():
    # 13 November, 01:12 and 01:28: the tick after the cross took 0.37 s, the bridge let go of a pad
    # it had not been sent again within its 250 ms, and the cross, sent a second time, was a second
    # press: it took away the waypoint the first had set, after the skill had read its distance.
    model = Model(["Spieler", "Ammu-Nation", "Golf", "Kino"])
    observe, apply = model.observation, model.apply
    times = [0.0]
    for tick in range(1000):
        times.append(times[-1] + (0.2 if tick % 2 else 0.37))
    model.observation = lambda tick, corrupt=False: replace(observe(tick, corrupt=corrupt), time=times[tick])
    sent = []

    def bridge(result):
        # The pad of a tick goes out as the next tick begins.
        tick = len(sent)
        sent.append(result.pad.buttons)
        if result.pad.buttons and times[tick + 1] - times[tick] > 0.25:
            model.previous = ()
        apply(result)

    model.apply = bridge
    _, result, outputs = run({"place": "Kino"}, model)
    assert result.status == "done" and "Kino (532m)" in result.reason
    assert model.distance == 532 and model.screen == "game"
    assert model.presses.count("cross") == 2  # one opens the map
    for button in ("options", "cross", "circle", "down"):
        held = [button in output.pad.buttons for output in outputs]
        assert any(held) and not any(a and b for a, b in pairwise(held))


def test_writing_behind_the_map_and_misread_arrows_make_no_place():
    rows = lines(["Spieler", "Golf", "Los Santos Customs"], selected=0)
    rows[2]["text"] = "Los Santos Customs < 114> i"
    rows.insert(1, {"text": "ANDY", "box": [968, 60, 89, 32], "confidence": 1.0})
    assert [entry.name for entry in read_legend(rows).entries] == ["Spieler", "Golf", "Los Santos Customs"]


def test_the_white_bar_names_the_selection_where_no_arrows_stand():
    rows = lines(["Golf", "Kino", "Seilbahn"], selected=6, offset=5, total=28)
    rows[1]["text"] = "Kino"  # the one place of its kind: the game prints no arrows
    frame = np.full((720, 1280, 3), 20, dtype=np.uint8)
    x, y, w, h = rows[1]["box"]
    frame[y : y + h, x : x + w] = 250
    assert read_legend(rows).selected is None
    assert read_legend(rows, frame).selected.name == "Kino"
    x, y, w, h = rows[2]["box"]
    frame[y : y + h, x : x + w] = 250
    assert read_legend(rows, frame).selected is None  # two bars prove nothing


def test_missing_first_page_row_cannot_shift_counter_selection():
    rows = lines(["Spieler", "Golf", "Kino"], selected=2)
    rows[2]["text"] = "Kino"
    del rows[1]
    assert read_legend(rows).selected is None


def test_a_single_false_waypoint_reading_does_not_complete():
    model = Model(["Spieler", "Golf"], confirm=False)
    original = model.picture
    calls = 0

    def picture(frame):
        nonlocal calls
        calls += 1
        if calls == 30:
            model.distance = 532
            reading = original(frame)
            model.distance = None
            return reading
        return original(frame)

    model.picture = picture
    _, result, _ = run({"place": "Golf"}, model)
    assert result.status == "failed"
    assert "waypoint-not-visible-after-cross" in result.reason


def test_a_single_false_name_does_not_enter_the_inventory():
    model = Model(["Spieler", "Golf"])
    original = model.picture
    injected = False

    def picture(frame):
        nonlocal injected
        reading = original(frame)
        if model.screen == "map" and not injected:
            injected = True
            return replace(reading, entries=(*reading.entries, Entry("OCR phantom", "other")))
        return reading

    model.picture = picture
    skill, result, _ = run({"place": "Golf"}, model)
    assert result.status == "done"
    assert "Golf" in skill.legend.observed_places
    assert "OCR phantom" not in skill.legend.observed_places


def test_brief_damage_and_bad_selection_do_not_decide():
    model = Model(["Spieler", "Golf"])
    _, result, outputs = run({"place": "Golf"}, model, corrupt={25, 26, 27})
    assert result.status == "done", result.reason
    assert all(outputs[t].pad == NEUTRAL_PAD for t in (25, 26, 27))


def test_distance_is_only_read_from_legend_and_arrows_override_counter():
    reading = read_legend(lines(["Spieler", "Friseursalon"], 1))
    assert reading.distance is None
    rows = lines(["Spieler", "Friseursalon"], 1, distance=532)
    rows[-3] = line("3/29", 556)
    reading = read_legend(rows)
    assert reading.selected.name == "Friseursalon"
    assert reading.distance == 532
    assert kind_of("Chinesen") == "other"
    assert kind_of("New mission maybe") == "other"
    assert kind_of("Spieler") == "none"


def test_recording_every_reading():
    path = Path(__file__).parents[2] / "lab/legend/readings.json"
    readings = json.loads(path.read_text())["readings"]
    counters = selected = distances = 0
    for sample in readings:
        reading = read_legend(sample["lines"])
        t = sample["t"]
        if reading.position is not None:
            counters += 1
            expected = {
                1: "Spieler",
                2: "Ammu-Nation",
                3: "Ammu-Nation mit Schießstand",
                4: "Autowaschanlage",
                5: "Beekers Garage",
                6: "Binco Bekleidung",
                8: "Discount Store",
                9: "Fahrgeschäft",
                10: "Fremde und Freaks",
                11: "Friseursalon",
                12: "Friseursalon",
            }
            assert reading.selected is not None, (t, reading)
            assert reading.selected.name == expected[reading.position], (t, reading)
            assert reading.total == (29 if reading.position == 12 else 28)
        if reading.selected is not None:
            selected += 1
        if reading.distance is not None:
            distances += 1
            assert reading.distance == 532
            assert 74 <= t <= 77
    assert len(readings) == 185
    assert counters == 102
    assert selected == 103
    assert distances == 5


@pytest.mark.parametrize(
    "args",
    [
        {"place": 3},
        {"place": " "},
        {"kind": "whatever"},
        {"kind": "other"},
        {"place": "Golf", "kind": "shop"},
        {"instance": True},
        {"instance": 1.2},
        {"duration": float("nan")},
    ],
)
def test_invalid_arguments(args):
    with pytest.raises(ValueError):
        SetWaypoint(args)


def test_head_accepts_printed_names_and_exposes_string_schema():
    decision = parse_response(
        {
            "plan": [{"name": "set_waypoint", "args": {"place": "Friseursalon"}}],
            "sentence": "Go to the barber.",
        }
    )
    assert decision.plan[0].args["place"] == "Friseursalon"
    variants = response_schema()["properties"]["plan"]["items"]["anyOf"]
    schema = next(v for v in variants if v["properties"]["name"]["enum"] == ["set_waypoint"])
    assert schema["properties"]["args"]["properties"]["place"] == {"type": "string"}
    for argument in ("place", "kind"):
        assert any(
            v["properties"]["name"]["enum"] == ["set_waypoint"]
            and v["properties"]["args"]["required"] == [argument]
            and set(v["properties"]["args"]["properties"]) == {argument}
            for v in variants
        )
    assert len(SetWaypoint.prompt) <= 400


def test_a_long_row_that_begins_far_to_the_left_is_still_the_selection():
    rows = lines(["Spieler", "Ammu-Nation", "Autowaschanlage"], selected=5, total=31)
    rows.insert(
        1,
        {
            "text": "Immobilie: McKenzie-Feldhangar: 150.000 $ < 1/4 >",
            "box": [877, 96, 338, 14],
            "confidence": 1.0,
        },
    )
    legend = read_legend(rows)
    assert legend.selected is not None and legend.selected.name.startswith("Immobilie")
    assert legend.selected.instance == 1 and legend.selected.count == 4


def test_a_selected_row_that_is_not_read_is_stepped_past():
    # 20261114-025903 at 16 s: the white bar on "Kfz-Abschleppplatz", one above the place, was not
    # read for the 28 s the try had left, and nothing was pressed.
    model = Model(["Spieler", "Ammu-Nation", "Chinesen", "Golf", "Kino", "Friseursalon"])
    seen = model.picture

    def unread(frame):
        legend = seen(frame)
        if model.screen == "map" and legend.selected is not None and legend.selected.name == "Golf":
            rest = tuple(entry for entry in legend.entries if entry.name != "Golf")
            return replace(legend, selected=None, entries=rest)
        return legend

    model.picture = unread
    _skill, result, _ = run({"place": "Kino"}, model)
    assert result.status == "done", result.reason
    assert "Kino" in result.reason
    assert model.distance == 532
