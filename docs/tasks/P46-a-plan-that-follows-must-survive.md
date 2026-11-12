# P46: A plan that follows must survive the skill before it

## Why

On the morning of 12 November the pilot stood on foot at the kerb in front of the hospital with a car in sight, and the rules answered as they should: request 7 of session `/Users/kerim/recordings/pilot/20261112-082524` at 73.545 s plans `enter_vehicle`, `set_waypoint`, `drive_route`. The figure never went to the car. The report of P45 (`docs/reports/P45-on-foot-with-nothing-asked.md`, second finding) shows why, from `head.jsonl` and `play.jsonl`: the request was one the conductor makes when the running plan is about to end, so its answer at 73.587 s was appended behind the running `walk_to`. At 73.697 s that `walk_to` reached its time limit, which it reports as a failure; `SkillRunner.tick` clears the queue on a failure, the conductor counts a failed skill and asks again, and the answer at 73.736 s replaced the plan with the walk the rules give after a failed skill. A plan made 0.15 s earlier for the situation as it was, by a head that had been told the old skill was ending, was thrown away by the ending of that skill.

This is the last thing between the pilot and its first car in free roam, and it holds for every plan that follows another: a waypoint after a walk, a drive after an entry.

Read `PLAN.md`, in `docs/LOG.md` the entries from 10 November on, the report of P45 to its end, `pilot/src/pilot/conductor.py` (`_finish_head`, `_request`, the tick around the runner and the events `plan_ending`, `skill_failed`, `skill_ended`), `pilot/src/pilot/skills.py` (`SkillRunner` and how each skill ends at its time limit), their tests and `pilot/tools/conductor_replay.py`.

## What to build

First list, skill by skill, how it ends when its time runs out and with which reason, and which of these endings the rules in `mission.py` answer today. A skill that simply ran its time and a skill that found out something (`stuck`, `blocked`, a target lost, a car that cannot be entered) are different news, and today both arrive as a failure.

Then make the plan that follows survive. An answer that was appended while the head knew the running skill was ending stays in the queue when that skill ends by its time limit, the next skill starts on the following tick, and the head is not asked again because of that ending. A failure that carries news still clears what follows and still reaches the head as `skill_failed`, as today. Whether the difference is made in the runner, in the conductor or in the result a skill gives at its time limit is yours to decide; say in the report why, and keep the epoch rule that discards answers to questions that are out of date.

Check the neighbouring case as well and say what happens in it: an answer that replaces the plan arrives in the same tick in which the replaced skill fails. The new plan must run, and the failure of a skill that is no longer wanted must not ask the head again.

Every ending and what became of the queue goes into `play.jsonl` in the fields the conductor already writes, so that a session shows whether a plan was kept or dropped and why.

## Judging it

Replay the session of 12 November through the changed conductor with `conductor_replay.py` or a replay of your own beside it in `lab/conductor/`, with the recorded head answers at their recorded times: after 73.6 s the runner holds `enter_vehicle`, and no request with `skill_failed` for the timed-out `walk_to` follows. Show the lines. Replay the pier session `/Users/kerim/recordings/pilot/20261111-204712` and one driving session of your choice from `/Users/kerim/recordings/pilot/` and list every tick at which the plan now differs from the recorded one, with the reason. Tests pin the kept plan, the cleared plan after a failure with news, and the same-tick replacement.

## Your files

`pilot/src/pilot/conductor.py`, `pilot/src/pilot/skills.py` (the runner and what a skill returns at its time limit, not what the skills do), their tests, `pilot/tools/conductor_replay.py`, `lab/conductor/` and your report. Not `mission.py`, `foot.py`, `scene.py`, `notes.py`, `minimap.py` or `cli.py`: if the rules need a change to go with yours, describe it exactly and leave it. The console is in use by others while you work: the rules of `docs/tasks/README.md` about the daemon hold without exception, and nothing under `/Users/kerim/recordings/` is written, moved or deleted. Write nothing large: the disk has little room left.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green or fails only where your sandbox refuses sockets or CoreML, which you then name test by test, and the report shows the list of endings, the three replays, what you decided and why, and what the next try on the console should look at first.
