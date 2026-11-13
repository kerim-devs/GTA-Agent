"""Recorded help-text offers. Unrecognized instructions remain explicit guesses."""

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pilot.profile import active

# These destinations are outside the pilot's in-game interaction scope.
FORBIDDEN = (
    ("phone", r"telefon|handy|phone|anruf|anrufen|anrufe|kontakt|ruf .* an"),
    ("internet", r"internet|browser|webseite|website"),
    ("save", r"speicher|schnellspeicher|save|spielstand"),
    ("stock market", r"aktie|borse|bawsaq|lcn|stock market"),
    ("property purchase", r"immobil|grundstuck|property|gebaude kaufen|garage kaufen"),
    # A help text is never the way to buy: what costs money is bought in a shop's menu, where the
    # price is read and held against the limit (place.UsePlace), and nowhere else.
    ("purchase", r"kauf|erwerb|bezahl|\bbuy\b|purchase|dollar"),
    ("bed", r"\bbett|schlaf|\bbed\b|sleep"),
    ("GTA Online", r"gta\s*online|gta\s*\+|gta\+|\bonline\b"),
    ("leaving the game or the mission", r"spiel\w* (?:zu )?beenden|abzubrechen|mission abbrechen|\bquit\b"),
    (
        "PlayStation menus",
        r"playstation|ps\s*(?:taste|button|menu)|ps5|kontrollzentrum|control center|share|create",
    ),
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"(?<=[a-z])8|8(?=[a-z])", "e", text)
    return " ".join(re.sub(r"[^a-z0-9+]+", " ", text).split())


def refusal(text: str) -> str | None:
    if re.search(r"[$€]", text):
        return "purchase"  # a price in a help text: normalize() drops the sign, so it is looked for here
    wording = normalize(text)
    return next((reason for reason, pattern in FORBIDDEN if re.search(pattern, wording)), None)


@dataclass(frozen=True)
class Offer:
    button: str
    kind: str
    seconds: float
    wording: str
    known: bool

    @property
    def guess(self) -> bool:
        return not self.known


TABLE = json.loads(Path(__file__).with_name("prompts.json").read_text())["prompts"]


def offer(text: str, frame=None) -> Offer | None:
    """Return a safe offer; glyphs are not trusted without held-out validation."""
    wording = normalize(text)
    if refusal(text) or not re.search(r"\b(?:dr[uqo]ck\w*|halt\w*|tipp\w*|press|hold|tap)\b", wording):
        return None
    for row in TABLE:
        if any(normalize(pattern) in wording for pattern in row["patterns"]):
            return Offer(row["button"], row["kind"], row["seconds"], row["wording"], True)
    return Offer(
        active().context, "hold" if re.search(r"\b(?:halte|hold)\b", wording) else "press", 0.1, text, False
    )
