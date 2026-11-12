# P54: A clean map called damaged

## Why

The minimap reader marks a reading as corrupt when it finds the 16 px block borders of the video codec in the map (`_blocks` in `pilot/src/pilot/minimap.py`), and a corrupt reading is one the skills do not act on: `enter_vehicle`, the walks and the driver send nothing or hold what they had, and the confidence is capped at 0.35. That is right for a damaged picture. On 12 November, on a cable connection whose pictures are clean, the reader called 1,937 of 52,019 ticks of the pilot's sessions corrupt (3.7 %), and in seven runs it did so for more than two seconds on end, 54 seconds in all, each time with the figure standing or barely moving:

- `20261112-110449` from 10.5 s, 15.1 s, map flat, during `enter_vehicle`: a car stopped beside the figure and the skill sent nothing until its time was up.
- `20261112-102851` from 73.6 s, 15.2 s, map flat, during `walk_road`.
- `20261112-100713` from 179.3 s (5.3 s, `look`), 194.3 s (3.2 s, map tilted, `walk`), 199.5 s (7.3 s, `walk`) and 207.1 s (5.7 s, `walk_road`).
- `20261112-104424` from 121.7 s, 2.6 s, map tilted, during `wait`.

The sessions are under `/Users/kerim/recordings/pilot/`, each with `play.jsonl` (the reading of every tick, with `corrupt` and `confidence`), `frames.jsonl` (frame number, frame id and time) and `video.mp4`. The alarm feeds on itself: a figure that stands keeps the same map in the picture, the alarm stays, and the skill that would move the figure waits for it to pass.

The reader's own note says where the gap is: a narrow bright stroke on a block border is taken for a road only where a route is drawn (`route_strokes`), "keep the raw detector for motion and route-free frames". On foot there is no route.

Read `PLAN.md`, in `docs/LOG.md` the entries on damage and on the minimap, the reports of P36 and P2, `pilot/src/pilot/minimap.py` with `pilot/tests/test_minimap.py` and `pilot/tests/test_minimap_behind.py`, and `lab/minimap/`.

## What to build

First show, on the frames of the seven runs, which block pieces raise the alarm and what in the map they are: the edge of a road that happens to lie on a block border, a symbol, the map's own frame, or damage after all. Say for each run whether the picture outside the map is clean, and whether among the day's other corrupt ticks (the short ones) there is real damage.

Then an alarm that tells a clean map from a damaged one in these cases and still rings for every damaged picture the tests and `lab/minimap/` hold. What tells them apart is yours to find from the frames; among the things to look at: the map's own drawing has edges that continue across the block border while a displaced block does not, real damage changes from one frame to the next while a still clean map repeats itself exactly, and damage is rarely confined to the map. Whatever you choose, show what it costs on real damage: an alarm that comes a tick later is acceptable, one that misses a damaged route is not.

The skills and the conductor are not yours. If a skill should treat a corrupt reading differently, describe it exactly in the report and leave it.

## Judging it

Replay the reader over the frames of the seven runs before and after: ticks called corrupt, and the longest run. Replay it over every damaged picture and sequence the tests and `lab/minimap/` hold, and over the three of Kerim's recordings in which the reader finds the most damage (`/Users/kerim/recordings/derived/kerim/*/sections.json` gives the share of damaged readings of each stretch as `damaged`; the videos are under `/Users/kerim/recordings/kerim/`): the alarms kept and lost, with the frames of every lost one looked at and named as damage or not. Over one whole clean session of the pilot give the share of corrupt ticks before and after, and the reader's time per tick before and after, which must not grow by more than a tenth.

## Your files

`pilot/src/pilot/minimap.py`, `pilot/tests/test_minimap.py`, `pilot/tests/test_minimap_behind.py`, `lab/minimap/` and your report. No other source file: other workers are changing `vehicle_entry.py`, `mission.py`, `conductor.py`, `waypoint.py` and `legend.py` at the same time. The console is in use by others while you work: the rules of `docs/tasks/README.md` about the daemon hold without exception, and nothing under `/Users/kerim/recordings/` is written, moved or deleted. Write nothing large: the disk has little room left, so keep crops and small sheets, not frames in bulk.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green or fails only where your sandbox refuses sockets, Vision or CoreML, which you then name test by test, and the report shows what raised the alarm in each of the seven runs, the rule you chose with its cost on real damage, and the replays before and after.
