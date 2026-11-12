# P51: A goal that is kept

## Why

On 12 November the pilot played by itself in town for the first time, in rounds of four minutes with nothing asked: sessions `/Users/kerim/recordings/pilot/20261112-102851` and `/Users/kerim/recordings/pilot/20261112-103305`, each with `play.jsonl`, `head.jsonl`, `judge.jsonl` and `video.mp4`. It got into vehicles and drove one along a route for a minute and a half, which it had never done unasked. Kerim watched the second session and said what it looked like: the figure walks back and forth, and it makes no sense unless it picks a goal and carries it out.

The log of that session says the same. In 240 seconds the head was asked 27 times and replaced the running plan 21 times. At 16.5 s it planned to take a car; 2 s later that plan was gone for a waypoint on the map, set on foot; then came waiting, the car again, a walk, the map again. `enter_vehicle` ended twice with `could not reach it` and was replaced once before it could end; `set_waypoint` was replaced four times and failed five more. Every event makes the head decide afresh, every decision is made as if nothing had been decided before, and whatever skill is running is stopped for it.

One cause is repaired already and is not yours: the judge called the figure seated while it stood next to a car, and a flat minimap now overrules it (`judge.ModeFilter`, the fix is in your branch). What is left is that the pilot has no goal.

Read `PLAN.md`, in `docs/LOG.md` the entries from "On foot" on, the reports of P45, P46 and P48, `pilot/src/pilot/mission.py` with its tests, `pilot/src/pilot/head.py`, `pilot/src/pilot/conductor.py` (`_finish_head`, the events, `uninterruptible`), `pilot/src/pilot/skills.py` (`SkillRunner`) and `pilot/src/pilot/head_prompt.txt`.

## What to build

A goal for the pilot when the game asks nothing of it, held until it is reached or given up.

The goals, to begin with, are few and closed: take a vehicle; drive somewhere far and arrive; get out and hit somebody on the street; get away from the police; on foot with no vehicle near, get to a road. For each one say what may start it, its steps with the skills that exist, by what reading it counts as reached, after how many tries or seconds it is given up, and which goal follows. Getting away is started by stars and keeps the rules that exist for them. The order makes a round of play: a vehicle, a drive, a fight, an escape, and again, with a choice between what is possible that is seeded and logged, so that two sessions do not look alike and a replay gives the same answers.

One goal stands at a time. The head's sentence names it, since the sentence is what a viewer of the stream reads, and each answer in `head.jsonl` carries the goal, its step and why it was kept or changed.

Keeping it is the point. While a goal stands and the running skill serves it, a request that brings no reason to change does not stop that skill: a plan about to end, a change of mode the goal itself expects (getting in while taking a vehicle), a help text, a blip that comes and goes. The head must be able to answer "go on" and the conductor must then leave the running skill and its queue as they are; today the only answers are replace and append. Decide how that is said and keep the protection against answers to questions that are out of date. A skill that failed is answered inside the goal: the next try, another vehicle, another way, until the goal's limit.

What ends a goal at once: stars, health under a third, the screens for death and arrest, an objective on screen (then the mission rules of P48 decide, as today), and its own limit. A goal that is given up is not picked again straight away.

## Judging it

Replay the recorded requests of both sessions and of `20261112-100318` and `20261112-100713` through the new head, in order with one head per session as `lab/foot/p45_replay.py` does: how many answers replace the plan, before and after, and the goals with their times. A replay cannot show what would have happened next, so say what the numbers do and do not prove. Drive the conductor in a test with a scripted sequence of the events that occur in these sessions and show that the running skill is not stopped by those that bring no reason, and is stopped by each of the five that do. Run the rules over the cases of `lab/mission/`, `lab/take-out/` and the recorded requests of P45: a case with an objective on screen must keep its decision, and for every case without one that changes, say why. Tests pin each goal's start, reach and giving up, the answer "go on", and the round.

## Your files

A new `pilot/src/pilot/goals.py`, `pilot/src/pilot/mission.py` (only where free roam hands over to the goals; another worker is changing its answer to a failed `walk_road` and its handling of blips at the same time, so leave those lines alone), `pilot/src/pilot/head.py`, `pilot/src/pilot/conductor.py`, in `pilot/src/pilot/skills.py` the `SkillRunner` only, `pilot/src/pilot/head_prompt.txt`, their tests, `lab/goals/` and your report. Not `foot.py`, `minimap.py`, `judge.py`, `vehicle_entry.py`, `waypoint.py`, `punch.py`, `drive.py` or `cli.py`: what one of them needs, such as a vehicle entry that picks a car it can reach or a waypoint that fails less by day, is described exactly with the evidence from the sessions and left. The console is in use by others while you work: the rules of `docs/tasks/README.md` about the daemon hold without exception, and nothing under `/Users/kerim/recordings/` is written, moved or deleted. Write nothing large: the disk has little room left.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green or fails only where your sandbox refuses sockets, Vision or CoreML, which you then name test by test, and the report shows the goals as a table, the replays, the conductor test, the changed cases and what the next try on the console should look at first.
