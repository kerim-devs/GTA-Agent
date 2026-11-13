# P83: Down the stairs from a landing

## Why

On 13 November, 12:15, the pilot stood in an apartment, pushed the front door open at 20 s, stood for eight seconds on the landing outside, one floor above the street with the stairs down in front of it, and walked back in (recording `/Users/kerim/recordings/pilot/20261113-121513`, read-only; 22.5 to 30 s are the landing: a platform a few steps wide, a chain-link fence with a gate, a neighbour's barred door, and a staircase with a handrail that leads down along the wall). Kerim, watching: it was outside already; it has to walk down the stairs.

The local model tells a room, such a landing and the street apart (`ahead.WHERE` in this worktree, 31 of 31 frames of that landing, see `lab/models`), and the walk's guard already knows how to look round a room for the door and run through it (`WayRound.leave` and `enter` in `wayround.py`, the questions `EXIT` and `ENTRANCE`). What is missing is the same for the way down: a skill that, on a landing, looks for the stairs, walks down them and says when the figure is on the street. Another card, P82, makes the head plan this skill by the name `descend` when its sense of place says `landing`; it does not build it.

Read `PLAN.md`, `docs/tasks/README.md` (the section on a new skill binds you), then `pilot/src/pilot/ahead.py` (`STAIRS`, `WHERE`, `View.where`, `Ahead.ask(stairs=..., where=...)` are already there, do not change the file), `wayround.py` in full, `leave.py`, `indoors.py`, `foot.py` where the guard's base is, and `tests/test_buildings.py`, whose scripted askers and observations are the model for your tests.

## What to do

The decisions below are made; where one turns out not to work, say so in the report and do the nearest thing that keeps its purpose.

### The skill

A class `Descend` in a new module `pilot/src/pilot/descend.py`, name `descend`, one parameter `duration` from 5 to 60 seconds, default 40. It is built like `LeaveBuilding` and keeps that skill's care on every tick: a time that is no number, stands or runs back, a gap, an unreadable or tilted map, a figure not on foot, a frame that is not a picture or repeats the last one, all give the neutral pad and reset what was being confirmed; a finished skill returns what it finished with; `stop()` never overwrites a verdict.

Where it stands. The skill asks for the place itself, through `ahead.place()` with `where=True`, one frame at a time and at most every 0.6 s. An answer counts when it came within two seconds of its frame, has no error and gives its strongest place at least 0.6; a place is confirmed by two counted answers in a row that name it (`indoors.Confirm` holds any value). With no asker the skill fails `place-unread` on its first valid step, and the same when eight seconds of valid steps bring no confirmed place.

Confirmed `street` before it has moved: done, reason `street` (the head may call it late). Confirmed `room` before it has moved: failed, reason `in-room`; the head leaves the building first. Confirmed `landing`: it begins.

The way down. The guard gets a third search beside `leave` and `enter`: `WayRound.descend(observation)`, which looks round as those do, the camera a fifth of a circle at a time, and asks of each view `ask(frame, now, indoors=False, ahead=False, stairs=True)`. A view whose `exit` share reaches the guard's `OPEN` shows stairs: the camera turns to the part of the picture they are in and the figure runs at them, as it runs at a door. While it runs it keeps asking the same question at the guard's `WATCH_EVERY` and nudges the view to the part the stairs are in, as `_watch` does for a door; the place is not the guard's to watch here, the skill does that. With every view called empty, or no answer, the figure goes round along the landing's edges as it goes round a room's walls. The figure never climbs or jumps here (`climb=False`): over the railing is a floor's fall.

Down. On the stairs the model goes on saying `landing`, which the question's second answer includes. The skill ends `done` with reason `street` when `street` has been confirmed and stayed for the guard's `CLEAR` seconds, during which the figure walks straight on, away from the foot of the stairs. Confirmed `room` after it began means it walked through a door: failed, reason `entered-room`, with the neutral pad. The guard giving up is failed `no-stairs`; the limit is `time-limit`.

### What stays

`leave`, `enter`, `back_out` and `leave_heading` behave as they do; the tests of `tests/test_buildings.py` pass unchanged. The timings of the guard (`LOOK_SETTLE`, `LOOK_WAIT`, `WATCH_EVERY`, `CLEAR`, `AIM_TURN`) are not changed.

## Your files

`pilot/src/pilot/descend.py` (new), `wayround.py`, `tests/test_descend.py` (new), `docs/reports/P83-down-the-stairs-from-a-landing.md`. Not `ahead.py`, `indoors.py`, `leave.py`, `skills.py`, `head.py`, `head_prompt.txt`, `mission.py`, `errands.py`, `conductor.py`, `bench.py`: P82 works beside you, and the reviewer wires the skill in and adds the bench's rules for your failure reasons; name those reasons in the report.

Tests never contact a model server: scripted askers answer.

## Done when

A test for each of these fails before the change and passes after it: no asker fails `place-unread` at once and eight unanswered seconds fail the same; `street` at the start is done and `room` at the start fails `in-room`; on a landing the camera turns view by view and the question asked is `ahead.STAIRS` and no other; a view with stairs in its left part turns the camera left and then runs; while running a later answer with the stairs in the right part nudges the view right; with no stairs in any view the figure goes round the edges; `street` confirmed and held for `CLEAR` ends done `street` with the figure having walked straight on meanwhile, and one counted `street` followed by `landing` does not end it; `room` after the start fails `entered-room`; the limit fails `time-limit`; no pad of any path presses Square, Cross, `ps` or `create`, and the last result of every ending carries the neutral pad; a finished skill returns the same result again and `stop()` does not change it. The gate passes in `pilot/`: run the tests of your own files while you work and the whole gate once at the very end, because the machine is shared and a measurement is running on it.
