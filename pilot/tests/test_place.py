import threading
from dataclasses import replace

import numpy as np
import pytest

from pilot.contract import NEUTRAL_PAD, Hud, Observation, Reading
from pilot.place import DoPrompt, Picture, UsePlace, _TextStream, menu_entries
from pilot.scene import SceneText, TextLine

FRAME = np.full((720, 1280, 3), 20, np.uint8)
PROMPT = "Drücke die Taste, um dir die Kleidung anzusehen."


def observation(time, screen="game", minimap="flat", frame=FRAME):
    return Observation(
        Reading(minimap, "none", None, None, None, False, 1.0), False, time, frame, hud=Hud(screen=screen)
    )


def lines(*labels):
    return SceneText(
        lines=tuple(
            TextLine(label, 1.0, (30, 164 + i * 30, 300, 20), "help") for i, label in enumerate(labels)
        )
    )


class Text:
    def __init__(self, scene):
        self.scene, self.latest, self.closed = scene, None, False

    def submit(self, frame, now):
        self.latest = Picture(now, self.scene)

    def read(self):
        return self.latest

    def close(self):
        self.closed = True


def attach(skill, scene):
    skill.text = Text(scene)
    return skill.text


@pytest.mark.parametrize("tick", [0.03, 0.3])
def test_single_press_observed_effect(tick):
    skill = DoPrompt({})
    text = attach(skill, SceneText(help=PROMPT))
    assert skill.step(observation(0)).pad.buttons == ("right",)
    assert skill.step(observation(tick)).pad == NEUTRAL_PAD
    text.scene = SceneText()
    result = skill.step(observation(tick * 2))
    assert (result.status, result.reason, result.pad) == ("done", "pressed: right", NEUTRAL_PAD)
    assert text.closed


def test_no_effect_and_no_prompt():
    skill = DoPrompt({})
    attach(skill, SceneText(help=PROMPT))
    skill.step(observation(0))
    assert skill.step(observation(0.3)).pad == NEUTRAL_PAD
    assert skill.step(observation(2.1)).reason == "no-effect"
    skill = DoPrompt({})
    attach(skill, SceneText())
    assert skill.step(observation(0)).reason == "no-prompt"


@pytest.mark.parametrize(
    "wording",
    [
        "Telefon",
        "Internet",
        "Spiel speichern",
        "Aktien",
        "Immobilie kaufen",
        "GTA Online",
        "PlayStation",
        "PS-Taste",
        "GTA+",
    ],
)
@pytest.mark.parametrize("cls", [DoPrompt, UsePlace])
def test_forbidden_never_pressed(wording, cls):
    skill = cls({})
    attach(skill, SceneText(help=f"Drücke X für {wording}."))
    results = [skill.step(observation(t)) for t in (0, 0.3, 0.6)]
    assert all(result.pad == NEUTRAL_PAD for result in results)
    assert results[-1].reason.startswith("refused:")


def test_invalid_frames_and_clock_abstain():
    skill = DoPrompt({})
    text = attach(skill, SceneText(help=PROMPT))
    assert skill.step(observation(float("nan"))).pad == NEUTRAL_PAD
    assert skill.step(observation(0, frame=None)).pad == NEUTRAL_PAD
    obs = observation(0.1)
    assert skill.step(replace(obs, reading=replace(obs.reading, corrupt=True))).pad == NEUTRAL_PAD
    assert skill.step(observation(0.2)).pad.buttons == ("right",)
    assert skill.step(observation(0.2)).pad == NEUTRAL_PAD
    assert skill.step(observation(0.1)).pad == NEUTRAL_PAD
    text.submit = lambda frame, now: None
    assert skill.step(observation(2)).pad == NEUTRAL_PAD
    assert skill.stop().pad == NEUTRAL_PAD


class Shop:
    def __init__(
        self, rows=("Buzz cut $75",), nested=False, unread=False, receipt=True, menu_screen="interaction_menu"
    ):
        self.rows, self.nested, self.unread = rows, nested, unread
        self.receipt, self.menu_screen = receipt, menu_screen
        self.level, self.purchased, self.buttons = 0, False, []

    def scene(self):
        if not self.level:
            return SceneText(help=PROMPT)
        if self.unread:
            return SceneText()
        if self.nested and self.level == 1:
            return lines("Haare", "Bärte")
        return lines(*self.rows, *(["Gekauft"] if self.purchased and self.receipt else []))

    def apply(self, pad):
        self.buttons.extend(pad.buttons)
        if "right" in pad.buttons:
            self.level = 1
        if "circle" in pad.buttons:
            self.level = max(0, self.level - 1)
        if "cross" in pad.buttons:
            if self.nested and self.level == 1:
                self.level = 2
            else:
                self.purchased = True

    def run(self, skill, closed=True):
        text = attach(skill, self.scene())
        for i in range(400):
            text.scene = self.scene()
            result = skill.step(
                observation(
                    i * 0.3, self.menu_screen if self.level else "game", "none" if self.level else "flat"
                )
            )
            self.apply(result.pad)
            if result.status != "running":
                assert result.pad == NEUTRAL_PAD
                assert not closed or self.level == 0
                return result
        pytest.fail("skill did not terminate")


@pytest.mark.parametrize("nested", [False, True])
def test_spend_no_never_confirms(nested):
    shop = Shop(nested=nested)
    result = shop.run(UsePlace({"spend": "no", "choice": "first"}))
    assert result.status == "done" and result.reason.endswith("bought nothing")
    assert "cross" not in shop.buttons and shop.buttons.count("right") == 1


def test_above_limit_never_bought():
    shop = Shop(rows=("Expensive cut $151",))
    assert shop.run(UsePlace({"choice": "first"})).status == "done"
    assert "cross" not in shop.buttons


@pytest.mark.parametrize("nested", [False, True])
def test_buy_once_close_all_levels(nested):
    shop = Shop(nested=nested)
    result = shop.run(UsePlace({"choice": "first"}))
    assert result.reason.endswith("bought Buzz cut for 75")
    assert shop.buttons.count("cross") == (2 if nested else 1)
    assert shop.buttons.count("circle") == (2 if nested else 1)


@pytest.mark.parametrize("unread,receipt", [(True, True), (False, False)])
def test_unread_backs_out(unread, receipt):
    shop = Shop(unread=unread, receipt=receipt)
    assert shop.run(UsePlace({"choice": "first"})).reason == "menu-unread"
    assert shop.buttons.count("cross") <= 1


def test_missing_price_does_not_confirm():
    shop = Shop(rows=("Buzz cut unreadable price",))
    assert shop.run(UsePlace({"choice": "first"})).reason == "menu-unread"
    assert "cross" not in shop.buttons


def test_random_repeatable():
    shops = [Shop(rows=("One $10", "Two $20", "Three $30")) for _ in range(2)]
    assert all(shop.run(UsePlace({"spend": "no"})).status == "done" for shop in shops)
    assert shops[0].buttons == shops[1].buttons


def test_welcome_waits_search_bounded():
    skill = UsePlace({})
    attach(skill, SceneText())
    for i in range(5):
        assert skill.step(observation(i * 0.3, minimap="none")).pad == NEUTRAL_PAD
    for i in range(5, 200):
        result = skill.step(observation(i * 0.3))
        if result.status != "running":
            break
    assert result.reason == "no-prompt" and result.pad == NEUTRAL_PAD


def test_an_unread_menu_is_backed_out_of():
    assert Shop(unread=True).run(UsePlace({"duration": 5})).reason in ("menu-unread", "time-limit")


@pytest.mark.parametrize("screen", ["pause", "failed", "map", "alert"])
def test_another_screen_is_left_to_the_reflex_with_nothing_pressed_into_it(screen):
    # On a failed mission the circle gives the mission up: the skill ends, and the reflex has the screen.
    shop = Shop(menu_screen=screen)
    result = shop.run(UsePlace({}), closed=False)
    assert result.status == "failed" and result.reason == f"wrong-screen: {screen}"
    assert shop.buttons == ["right"]


def test_the_way_out_presses_nothing_into_a_scene_without_a_menu():
    # The game's screen, no map and no menu: a scene. On foot the circle is a punch.
    skill = UsePlace({"duration": 12})
    text = attach(skill, SceneText(help=PROMPT))
    pressed = []
    for index in range(200):
        text.scene = SceneText(help=PROMPT) if index < 2 else SceneText()
        result = skill.step(observation(index * 0.1, "game", "flat" if index < 2 else "none"))
        pressed.extend(result.pad.buttons)
        if result.status != "running":
            break
    assert result.status == "failed" and result.pad == NEUTRAL_PAD
    assert "circle" not in pressed and "cross" not in pressed


@pytest.mark.parametrize(
    "row,price,name",
    [
        ("Jacke 2 $500", 500, "Jacke 2"),
        ("Hose 1 $450", 450, "Hose 1"),
        ("Weißes Hemd $115", 115, "Weißes Hemd"),
        ("Schalldämpfer $1,823", 1823, "Schalldämpfer"),
        ("Schalldämpfer $1.823", 1823, "Schalldämpfer"),
        ("T-Shirt 39 $", 39, "T-Shirt"),
        ("Angebot $20 statt $400", 400, "Angebot statt"),
        ("Buzz cut", None, "Buzz cut"),
    ],
)
def test_the_price_of_a_row_is_the_one_behind_the_sign_and_the_highest_of_several(row, price, name):
    from pilot.place import menu_entries

    entries = menu_entries(lines(row))
    assert [(entry.price, entry.name) for entry in entries] == [(price, name)]


def test_a_number_before_the_price_never_makes_a_dear_row_cheap():
    for rows in (("Jacke 2 $500",), ("Hose 1 $450",)):
        shop = Shop(rows=rows)
        result = shop.run(UsePlace({"spend": "yes", "choice": "first"}))
        assert "cross" not in shop.buttons and result.reason.endswith("bought nothing")


def test_nothing_is_bought_where_any_row_on_screen_is_dear_or_unread():
    for rows in (("Cap $75", "Anzug $900"), ("Cap $75", "Hut")):
        shop = Shop(rows=rows)
        result = shop.run(UsePlace({"spend": "yes", "choice": "first"}))
        assert "cross" not in shop.buttons and result.status == "done"
        assert result.reason.endswith("bought nothing")


def test_a_row_that_says_bought_of_something_else_is_no_receipt():
    shop = Shop(rows=("Cap $75", "Alter Hut $20 Gekauft"), receipt=False)
    result = shop.run(UsePlace({"spend": "yes", "choice": "first"}))
    assert "bought Cap" not in result.reason


@pytest.mark.parametrize(
    "help_text,why",
    [
        ("Drücke [X], um im Bett zu schlafen.", "bed"),
        ("Drücke [X], um zu schlafen.", "bed"),
        ("Drücke [X], um Online beizutreten.", "GTA Online"),
        ("Drücke [X], um das Haus zu kaufen.", "purchase"),
        ("Drücke [X], um die Wohnung zu kaufen", "purchase"),
        ("Drücke [X], um das Fahrzeug für $500000 zu erwerben.", "purchase"),
        ("Drücke [X], um das Angebot für $90 anzunehmen.", "purchase"),
        ("Drücke [X], um die Mission abzubrechen.", "leaving the game or the mission"),
    ],
)
def test_a_help_text_is_never_the_way_to_a_bed_a_purchase_or_online(help_text, why):
    from pilot.prompts import offer, refusal

    assert refusal(help_text) == why and offer(help_text) is None
    skill = DoPrompt({})
    attach(skill, SceneText(help=help_text))
    result = skill.step(observation(0.0))
    for index in range(1, 6):
        if result.status != "running":
            break
        result = skill.step(observation(index * 0.1))
    assert result.status == "failed" and result.reason == f"refused: {why}" and result.pad == NEUTRAL_PAD


def test_the_same_help_text_read_with_a_letter_wrong_is_not_a_press_that_worked():
    from pilot.place import _changed
    from pilot.prompts import normalize

    before = normalize("Drücke [glyph], um dir Kleidung anzusehen")
    assert not _changed(before, normalize("Drücke [glyph], um dir Kleidurg anzusehen"))
    assert _changed(before, normalize(""))
    assert _changed(before, normalize("Drücke [glyph], um in Deckung zu gehen"))


def test_async_reader_does_not_block_tick(monkeypatch):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    ids = []

    class Reader:
        def read(self, frame):
            ids.append(threading.get_ident())
            entered.set()
            release.wait(1)
            finished.set()
            return SceneText(help=PROMPT)

    monkeypatch.setattr("pilot.place.TextReader", Reader)
    stream = _TextStream()
    try:
        stream.submit(FRAME, 0)
        assert entered.wait(1) and stream.read() is None
        stream.submit(FRAME, 0.1)
        stream.submit(FRAME, 0.2)
        assert stream.pending[1] == 0.2
        release.set()
        assert finished.wait(1) and ids[0] != threading.get_ident()
    finally:
        release.set()
        stream.close()


def test_split_price_boxes():
    text = SceneText(
        lines=(
            TextLine("Jacket", 1, (30, 150, 100, 20), "help"),
            TextLine("$1,500", 1, (400, 151, 100, 20), "help"),
        )
    )
    assert menu_entries(text)[0].price == 1500


@pytest.mark.parametrize("cls", [DoPrompt, UsePlace])
@pytest.mark.parametrize(
    "args", [{"duration": float("nan")}, {"duration": True}, {"duration": "5"}, {"seed": 3}]
)
def test_invalid_arguments(cls, args):
    with pytest.raises(ValueError):
        cls(args)


def test_hold_duration_and_hard_limit(monkeypatch):
    from pilot.prompts import Offer

    monkeypatch.setattr("pilot.place.offer", lambda *args: Offer("r1", "hold", 0.7, "cover", True))
    skill = DoPrompt({})
    text = attach(skill, SceneText(help="Halte die Taste für Deckung."))
    for now in (0, 0.1, 0.2, 0.4, 0.6):
        assert skill.step(observation(now)).pad.buttons == ("r1",)
    assert skill.step(observation(0.8)).pad == NEUTRAL_PAD
    text.scene = SceneText()
    assert skill.step(observation(0.9)).status == "done"
    skill = DoPrompt({"duration": 0.2})
    attach(skill, SceneText(help="Halte die Taste für Deckung."))
    skill.step(observation(0))
    result = skill.step(observation(0.3))
    assert result.reason == "time-limit" and result.pad == NEUTRAL_PAD


def test_native_reader_failure_abstains(monkeypatch):
    failed = threading.Event()

    def broken():
        failed.set()
        raise RuntimeError("OCR unavailable")

    monkeypatch.setattr("pilot.place.TextReader", broken)
    stream = _TextStream()
    stream.submit(FRAME, 0)
    assert failed.wait(1)
    assert stream.read() is None
    stream.close()


@pytest.mark.parametrize("kind", ["ammu", "suburban", "wardrobe"])
def test_recorded_shop_menu_replay(kind):
    import json
    from pathlib import Path

    import cv2

    folder = Path(__file__).resolve().parents[2] / "lab/prompts"
    visit = json.loads((folder / "p71-menu-readings.json").read_text())[kind]
    sample = next(
        row
        for row in visit["samples"]
        if any(
            line["box"][1] > 600 and ("Kaufen" in line["text"] or "Ausw" in line["text"])
            for line in row["lines"]
        )
    )
    scene = SceneText(lines=tuple(TextLine(**line) for line in sample["lines"]), help=sample["help"])
    menu_frame = cv2.cvtColor(cv2.imread(str(folder / "frames" / f"{kind}.jpg")), cv2.COLOR_BGR2RGB)
    assert menu_frame.shape == FRAME.shape
    shop = Shop(menu_screen="game")
    entry = SceneText(help=PROMPT)
    skill = UsePlace({"spend": "no", "choice": "first"})
    text = attach(skill, entry)
    for i in range(100):
        text.scene = scene if shop.level else entry
        result = skill.step(observation(i * 0.3, "game", "none" if shop.level else "flat", menu_frame))
        shop.apply(result.pad)
        if result.status != "running":
            break
    assert result.status == "done" and result.reason.endswith("bought nothing")
    assert shop.level == 0 and result.pad == NEUTRAL_PAD and "cross" not in shop.buttons


def test_price_change_after_navigation_never_confirms():
    class ChangedPrice(Shop):
        def apply(self, pad):
            super().apply(pad)
            if "down" in pad.buttons:
                self.rows = ("One $10", "Two $200")

    shop = ChangedPrice(rows=("One $10", "Two $20"))
    assert shop.run(UsePlace({})).reason == "menu-unread"
    assert "cross" not in shop.buttons
