from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest

from pilot.contract import NEUTRAL_PAD, Hud, Observation, Reading
from pilot.place import DoPrompt, Picture
from pilot.prompts import offer
from pilot.scene import SceneText


@pytest.mark.parametrize(
    "text,button",
    [
        ("DrQck8 • o urn dir Waffen 8n2U88hen.", "right"),
        ("Druck8 t*a um dir Panz8rungen 8nzu5èhen.", "right"),
        ("Drucke • ö urn dir Waffan anzu88hen.", "right"),
        ("Druck8 •% urn dir Hemd8n anzus8h8n.", "right"),
        ("DrQcke t*Ö urn dir Shorts 8nzuseh8n.", "right"),
        ("Drucke • a um dir Gilets 8nzuseh8n.", "right"),
        ("Drucke •6, um dich umzuzi8h8n.", "right"),
        ("Druck8 n8b8n 8in8m Fahrzeug, um es als Dèck", "r1"),
        ("Drucka EQ. um in D8ckung zu g8hen.", "r1"),
        ("Drucke O, um ilber dss Auto 8uf d8s Daeh zu klomem, und d88 Fenster zu errdch8n.", "square"),
        ("Drucke t*4 um mir Ohnrn8chtig8r Zorn zu redÈn", "right"),
    ],
)
def test_recorded_spelling(text, button, request):
    result = offer(text)
    assert result is not None and result.button == button and result.known
    index = request.node.callspec.indices["text"]
    path = Path(__file__).resolve().parents[2] / "lab/prompts/frames" / f"{index:02d}.jpg"
    frame = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    now = [0.0]
    skill = DoPrompt({})
    skill.text = SimpleNamespace(
        submit=lambda *args: None, read=lambda: Picture(now[0], SceneText(help=text)), close=lambda: None
    )
    reading = Reading("flat", "none", None, None, None, False, 1.0)
    first = skill.step(Observation(reading, False, now[0], frame, hud=Hud(screen="game")))
    assert first.pad.buttons == (button,)
    now[0] = 0.3
    assert skill.step(Observation(reading, False, now[0], frame, hud=Hud(screen="game"))).pad == NEUTRAL_PAD
    assert skill.stop().pad == NEUTRAL_PAD


def test_unknown_is_explicit_guess_and_plain_text_is_not_an_offer():
    result = offer("Drücke etwas, um das unbekannte Ding zu benutzen.")
    assert result.button == "right" and result.guess
    assert offer("Gehe zu den Waffen.") is None


@pytest.mark.parametrize(
    "text",
    [
        "DrQck8, um d8in T8lefon zu offnen.",
        "Drücke, um im Intern8t Waffen anzusehen.",
        "Drücke, um deinen Spielstand zu speichern.",
        "Drücke, um Aktien zu kaufen.",
        "Drücke, um eine Immobilie zu kaufen.",
        "Drücke, um GTA Online zu starten.",
        "Drücke die PS Taste.",
    ],
)
def test_refusal_precedes_known_table(text):
    assert offer(text) is None
