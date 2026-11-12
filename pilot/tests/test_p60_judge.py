"""Use saved LM Studio answers; automated tests never contact the server."""

import json
from pathlib import Path

import pytest

from pilot.judge import JOINT, QUESTIONS, parse_where


def test_stored_wrong_answer_keeps_capture_and_does_not_change_runtime_prompt():
    records = json.loads((Path(__file__).resolve().parents[2] / "lab/where/stored-choices.json").read_text())
    record = next(row for row in records if row.get("names") == ["where", "edge"])
    result = parse_where(record["choice"], 24.0, record["duration"], "stored")
    # f312 is on the carriageway. Confidence is not a safety guarantee.
    assert result.answers["where"].value == "roadside"
    assert result.capture == 24.0
    assert result.duration == record["duration"]
    assert set(QUESTIONS) == {"mode", "overlay", "banner", "wanted", "path", "car"}
    assert "carriageway" not in JOINT


@pytest.mark.parametrize("content", ["A", "A A A", "A Z", "left right", None])
def test_incomplete_or_free_text_roadside_replies_are_rejected(content):
    with pytest.raises(ValueError):
        parse_where({"message": {"content": content}}, 2, 0.3, "stored")


def test_explicit_unknown_is_preserved_without_inventing_probability():
    result = parse_where({"message": {"content": "E C"}}, 2, 0.3, "stored")
    assert result.answers["where"].value == "unknown"
    assert result.answers["edge"].value == "unknown"
    assert result.answers["where"].probability is None
