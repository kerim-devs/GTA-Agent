"""What the pilot keeps between sessions is kept whole, and never trusted beyond what was seen."""

import json

import pytest

from pilot import memory
from pilot.memory import Memory


class Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def test_what_one_session_notes_the_next_one_reads(tmp_path):
    clock = Clock()
    first = Memory(tmp_path / "memory.json", clock=clock)
    memory.place_reached(first, "Friseursalon", how="foot")
    memory.door_found(first, "Friseursalon", bearing=-90)
    first.close()

    clock.now += 600
    second = Memory(tmp_path / "memory.json", clock=clock)
    entry = second.get(memory.PLACES, "Friseursalon")
    assert entry["reached"] == 1 and entry["entered"] == 1 and entry["how"] == "foot"
    assert memory.door_of(second, "Friseursalon") == 270.0
    assert second.since(memory.PLACES, "Friseursalon") == 600
    assert memory.door_of(second, "Ammu-Nation") is None


def test_a_place_given_up_twice_in_a_row_is_avoided_for_an_hour_and_a_success_clears_it(tmp_path):
    clock = Clock()
    store = Memory(clock=clock)
    memory.place_failed(store, "Tattoo-Studio", why="no-progress twice")
    assert not memory.place_avoided(store, "Tattoo-Studio")
    memory.place_failed(store, "Tattoo-Studio", why="limit")
    assert memory.place_avoided(store, "Tattoo-Studio")
    clock.now += 3601
    assert not memory.place_avoided(store, "Tattoo-Studio")
    memory.place_failed(store, "Tattoo-Studio", why="limit")
    assert memory.place_avoided(store, "Tattoo-Studio")
    memory.place_reached(store, "Tattoo-Studio", how="car")
    assert not memory.place_avoided(store, "Tattoo-Studio")


def test_a_mission_counts_its_failures_in_a_row_until_it_is_passed():
    store = Memory()
    for _ in range(3):
        entry = memory.mission_result(store, "Trevor", "failed")
    assert entry["failed"] == 3 and entry["failed_in_a_row"] == 3
    entry = memory.mission_result(store, "Trevor", "started")
    assert entry["failed_in_a_row"] == 3
    entry = memory.mission_result(store, "Trevor", "passed")
    assert entry["failed_in_a_row"] == 0 and entry["failed"] == 3
    with pytest.raises(ValueError):
        memory.mission_result(store, "Trevor", "won")


def test_the_file_is_written_whole_and_not_on_every_fact(tmp_path):
    clock = Clock()
    path = tmp_path / "memory.json"
    store = Memory(path, clock=clock)
    memory.errand_done(store, "shop", reached=True)  # within WRITE_EVERY of the start: kept in memory
    assert not path.exists()
    clock.now += memory.WRITE_EVERY
    memory.errand_done(store, "shop", reached=False)
    saved = json.loads(path.read_text())
    assert saved["sections"]["errands"]["shop"] == {"done": 1, "given_up": 1, "at": clock.now}
    assert not path.with_suffix(".json.part").exists()
    memory.errand_done(store, "story", reached=True)
    store.close()
    assert "story" in json.loads(path.read_text())["sections"]["errands"]
    assert memory.errand_age(store, "story") == 0 and memory.errand_age(store, "home") is None


@pytest.mark.parametrize("content", ["{not json", '{"version": 99, "sections": {}}', "[]", '{"version": 1}'])
def test_a_file_that_cannot_be_read_is_an_empty_memory_and_is_not_overwritten(tmp_path, content):
    path = tmp_path / "memory.json"
    path.write_text(content)
    store = Memory(path)
    assert store.error and store.names(memory.PLACES) == []
    memory.place_reached(store, "Suburban", how="foot")
    store.close()
    assert path.read_text() == content
    assert (
        json.loads((tmp_path / "memory.json.new").read_text())["sections"]["places"]["Suburban"]["reached"]
        == 1
    )


def test_only_the_newest_entries_of_a_kind_are_kept_and_what_cannot_be_written_is_refused():
    clock = Clock()
    store = Memory(clock=clock)
    for number in range(memory.KEEP + 20):
        clock.now += 1
        store.note(memory.PROMPTS, f"prompt {number}", button="right")
    names = store.names(memory.PROMPTS)
    assert len(names) == memory.KEEP and "prompt 0" not in names and f"prompt {memory.KEEP + 19}" in names
    with pytest.raises(TypeError):
        store.note(memory.PLACES, "Kino", seen={1, 2})
    with pytest.raises(ValueError):
        store.note(memory.PLACES, "", how="foot")
    assert store.get(memory.PLACES, "Kino") == {}


def test_without_a_path_nothing_touches_the_disk(tmp_path):
    store = Memory()
    memory.prompt_pressed(store, "Drücke um dir die Haare schneiden zu lassen", button="right", worked=True)
    store.close()
    assert list(tmp_path.iterdir()) == []
    assert store.count(memory.PROMPTS, "Drücke um dir die Haare schneiden zu lassen", "worked") == 1


def test_the_session_names_its_memory_once_and_everything_reads_the_same_one(tmp_path):
    try:
        named = memory.use(tmp_path / "memory.json")
        assert memory.active() is named
        memory.place_reached(memory.active(), "Kino", how="car")
        again = memory.use(tmp_path / "memory.json")  # the one before is closed, and so written
        assert again.get(memory.PLACES, "Kino")["reached"] == 1
    finally:
        memory.use(None)
    assert memory.active().get(memory.PLACES, "Kino") == {}
