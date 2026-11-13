"""What the pilot keeps from one session to the next: places, what failed there, and what worked.

Every session used to begin knowing nothing. The walk that ran into the barber's door on 13 November
ran into it again half an hour later, the errands chose a shop the figure had just come out of, and a
place whose waypoint failed three times in a row was the next one asked for. Kerim that night: remember
the entrance when you go into a shop, and such things have to get better far more quickly.

The memory is one small file beside the recordings. It holds facts with a count and a time, never an
instruction: which place was reached how often and how, on which side its door was found, which errand
was last done when, which mission failed how often in a row. Whoever decides reads it before deciding;
nothing in it is trusted further than a count of observations deserves, and a fact that was wrong
is outvoted by what is seen the next time.

Times are wall-clock seconds, since a session's own clock starts at nothing each time.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

VERSION = 1
# A file larger than this is not this module's: it is left alone and the memory starts empty.
MAX_BYTES = 2_000_000
# Seconds between two writes while facts keep coming; the last ones are written by `close`.
WRITE_EVERY = 5.0
# How many entries of one kind are kept; the oldest go first.
KEEP = 400


class Memory:
    """Sections of entries by name. Without a path nothing is read or written and it lasts the session."""

    def __init__(self, path: Path | str | None = None, *, clock=time.time):
        self.path = None if path is None else Path(path)
        self.clock = clock
        self.lock = threading.Lock()
        self.data: dict[str, dict[str, dict]] = {}
        self.dirty = False
        self.written = clock()
        self.error: str | None = None
        if self.path is not None:
            self._load()

    def _load(self):
        try:
            if not self.path.exists():
                return
            if self.path.stat().st_size > MAX_BYTES:
                raise ValueError("file too large")
            raw = json.loads(self.path.read_text())
            if not isinstance(raw, dict) or raw.get("version") != VERSION:
                raise ValueError("unknown version")
            sections = raw.get("sections")
            if not isinstance(sections, dict):
                raise ValueError("no sections")
            for section, entries in sections.items():
                if isinstance(entries, dict):
                    self.data[section] = {
                        str(name): dict(entry) for name, entry in entries.items() if isinstance(entry, dict)
                    }
        except (OSError, ValueError) as exc:
            # A memory that cannot be read is an empty one, and the file is not overwritten blindly:
            # the next write goes beside it.
            self.error = f"{type(exc).__name__}: {exc}"
            self.data = {}
            self.path = self.path.with_suffix(self.path.suffix + ".new")

    # ------------------------------------------------------------------ reading

    def get(self, section: str, name: str) -> dict:
        """A copy of the entry, empty when nothing is known."""
        with self.lock:
            return dict(self.data.get(section, {}).get(name, {}))

    def names(self, section: str) -> list[str]:
        with self.lock:
            return list(self.data.get(section, {}))

    def count(self, section: str, name: str, key: str) -> int:
        value = self.get(section, name).get(key, 0)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    def since(self, section: str, name: str, key: str = "at") -> float | None:
        """Seconds since the entry's time, None when it has none or the clock ran backwards past it."""
        at = self.get(section, name).get(key)
        if isinstance(at, bool) or not isinstance(at, (int, float)):
            return None
        elapsed = self.clock() - at
        return elapsed if elapsed >= 0 else None

    # ------------------------------------------------------------------ writing

    def note(self, section: str, name: str, **facts) -> dict:
        """Set facts on an entry and stamp it; returns the entry as it now is."""
        return self._change(section, name, facts, {})

    def bump(self, section: str, name: str, key: str, by: int = 1, **facts) -> dict:
        """Add to a counter of the entry, set whatever other facts are given, and stamp it."""
        return self._change(section, name, facts, {key: by})

    def forget(self, section: str, name: str | None = None):
        with self.lock:
            if name is None:
                self.data.pop(section, None)
            else:
                self.data.get(section, {}).pop(name, None)
            self.dirty = True
        self._write()

    def _change(self, section, name, facts, counters):
        if not isinstance(section, str) or not isinstance(name, str) or not section or not name:
            raise ValueError("a memory entry needs a section and a name")
        json.dumps(facts)  # what cannot be written is refused here and not at the next write
        with self.lock:
            entries = self.data.setdefault(section, {})
            entry = entries.setdefault(name, {})
            entry.update(facts)
            for key, by in counters.items():
                held = entry.get(key, 0)
                entry[key] = (held if isinstance(held, int) and not isinstance(held, bool) else 0) + by
            entry["at"] = self.clock()
            if len(entries) > KEEP:
                oldest = sorted(entries, key=lambda item: entries[item].get("at", 0))
                for stale in oldest[: len(entries) - KEEP]:
                    del entries[stale]
            self.dirty = True
            result = dict(entry)
        self._write()
        return result

    def _write(self, force=False):
        if self.path is None:
            return
        with self.lock:
            now = self.clock()
            if not self.dirty or (not force and 0 <= now - self.written < WRITE_EVERY):
                return
            text = json.dumps({"version": VERSION, "sections": self.data}, ensure_ascii=False, indent=1)
            self.dirty, self.written = False, now
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            partial = self.path.with_suffix(self.path.suffix + ".part")
            partial.write_text(text)
            os.replace(partial, self.path)  # whole or not at all: a session can end on any tick
        except OSError as exc:
            self.error = f"{type(exc).__name__}: {exc}"

    def close(self):
        self._write(force=True)


# ---------------------------------------------------------------------- the session's memory
#
# One memory for the session, named once by whoever starts it (`pilot play`), as the judge's servers
# are for `ahead` and `sides`. Until it is named, what is noted lasts as long as the process.

_active = Memory()


def use(path: Path | str | None) -> Memory:
    """Name the file the session's memory is kept in; None keeps it in the process only."""
    global _active
    _active.close()
    _active = Memory(path)
    return _active


def active() -> Memory:
    return _active


# ---------------------------------------------------------------------- the facts the pilot keeps
#
# One place for the names, so that what writes a fact and what reads it agree on them.

PLACES = "places"  # by the legend's name: reached, failed, entered, used, door, left
ERRANDS = "errands"  # by the errand's kind: done, given_up
MISSIONS = "missions"  # by the mission's name or letter: started, failed, passed, nothing
PROMPTS = "prompts"  # by the help text's wording: pressed, worked, button


def place_reached(memory: Memory, place: str, *, how: str):
    """The figure got to the place, on foot or by car."""
    return memory.bump(PLACES, place, "reached", how=how, failed_in_a_row=0)


def place_failed(memory: Memory, place: str, *, why: str):
    """A trip to the place was given up."""
    entry = memory.get(PLACES, place)
    return memory.bump(
        PLACES, place, "failed", why=why, failed_in_a_row=int(entry.get("failed_in_a_row", 0) or 0) + 1
    )


def place_avoided(memory: Memory, place: str, *, tries: int = 2, seconds: float = 3600.0) -> bool:
    """Given up this often in a row, and the last time within the hour: not the next place to go to."""
    entry = memory.get(PLACES, place)
    recent = memory.since(PLACES, place)
    return int(entry.get("failed_in_a_row", 0) or 0) >= tries and recent is not None and recent < seconds


def door_found(memory: Memory, place: str, *, bearing: float):
    """Where the way in was, as a compass bearing in degrees from the place's symbol to the door.

    The walk reads the map's north and the arrow; a bearing by the compass means the same thing whichever
    way the camera looks the next time."""
    return memory.bump(PLACES, place, "entered", door=float(bearing) % 360.0)


def door_of(memory: Memory, place: str) -> float | None:
    door = memory.get(PLACES, place).get("door")
    return float(door) if isinstance(door, (int, float)) and not isinstance(door, bool) else None


def errand_done(memory: Memory, kind: str, *, reached: bool):
    return memory.bump(ERRANDS, kind, "done" if reached else "given_up")


def errand_age(memory: Memory, kind: str) -> float | None:
    """Seconds since an errand of this kind last ended, whichever way."""
    return memory.since(ERRANDS, kind)


def mission_result(memory: Memory, name: str, result: str):
    """`started`, `failed`, `passed` or `nothing` (the letter was stood on and nothing began)."""
    if result not in {"started", "failed", "passed", "nothing"}:
        raise ValueError(f"unknown mission result {result!r}")
    entry = memory.get(MISSIONS, name)
    row = int(entry.get("failed_in_a_row", 0) or 0)
    row = row + 1 if result == "failed" else 0 if result == "passed" else row
    return memory.bump(MISSIONS, name, result, failed_in_a_row=row)


def prompt_pressed(memory: Memory, wording: str, *, button: str, worked: bool):
    """A help text's button was pressed, and the text went or stayed."""
    return memory.bump(PROMPTS, wording, "worked" if worked else "no_effect", button=button)
