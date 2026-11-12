# P47: The pilot reads pale objectives

## Why

The report of P39 (`docs/reports/P39-what-a-mission-asks-for.md`, from line 41) found that `scene.py` labels many objectives as subtitles: the game prints an objective in white with its target in a pale cyan or pale yellow that the colour test in `scene._objective` does not accept, for example "Begib dich zu dem herrenlosen Auto." at 373 s of `20261111-165543`. For the evaluation of Kerim's recordings this was repaired outside the reader, in `notes.promote_objectives`, which `tools/texts.py` calls on every reading: a line read as subtitle becomes an objective when it opens with an instruction verb, is short and carries a pale target colour.

The pilot itself still reads with `scene.py` alone. In a mission whose objectives are printed pale it has no objective at all, the rules of `mission.py` then treat the situation as free roam, and the events the conductor raises on a new objective never come. The two readers also must not drift apart: what the evaluation calls an objective and what the pilot calls one has to be the same decision in one place.

Read `PLAN.md`, the report of P39 to its end, the report of P7 (`docs/reports/P7-scene-text-and-events.md`), `pilot/src/pilot/scene.py` with its tests and its corpus, `pilot/src/pilot/notes.py` (`pale_target`, `instruction_like`, `promote_objectives`), `pilot/tools/texts.py`, and in `conductor.py` only how the scene's reading reaches the events and the head's request.

## What to build

One decision, in `scene.py`, of what an objective is, that holds the pale targets as well, used by the pilot and by `tools/texts.py` alike. `notes.py` keeps what belongs to notes and calls the reader for the rest; a second colour test beside the first is not wanted. The cost counts: the reader runs inside the pilot's loop, so say what the change adds per reading.

A dialogue line must not become an objective. The subtitles of cutscenes and of phone calls are the risk: measure it on the recordings, where hours of dialogue stand next to 37 known objectives.

## Judging it

The derived data of Kerim's recordings lies under `/Users/kerim/recordings/derived/kerim/<name>/` with `texts.jsonl` (the readings after the repair of P39), `missions.json` and `sections.json`; the recordings themselves under `/Users/kerim/recordings/kerim/<name>/`. Take the objectives of `missions.json` as the list of what must be found, and the text of the sections that are cutscenes as what must not. Show for the changed reader, per recording: objectives found of objectives known, and dialogue lines called objective, with frame and time for each wrong one. The existing corpus of `scene.py` must not get worse; list every case whose label changes.

Your sandbox refuses macOS Vision. Build the comparison so that it runs on stored readings (boxes, words and the frames cut from the video) wherever it can, and where a fresh reading is needed, write the one command that produces it and name it in the report under what could not be run; it will be run for you outside the sandbox and the numbers added.

## Your files

`pilot/src/pilot/scene.py`, `pilot/src/pilot/notes.py` (only to remove what moves into the reader), `pilot/tools/texts.py`, their tests, `lab/notes/` and your report. Not `conductor.py`, `mission.py`, `skills.py`, `foot.py` or `cli.py`. Nothing under `/Users/kerim/recordings/` is written, moved or deleted; write your own output under `lab/notes/` and keep it small, frames as a handful of evidence pictures only: the disk has little room left. The rules of `docs/tasks/README.md` about the daemon hold without exception.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green or fails only where your sandbox refuses sockets, Vision or CoreML, which you then name test by test, and the report shows the two counts per recording, the changed corpus cases, the cost per reading and the command for whatever has to be run outside.
