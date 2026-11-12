# P55: A drive that gets there

## Why

On 12 November the pilot drove fourteen times for five seconds and more in seventeen minutes of free play in town (sessions `20261112-102851`, `-103305`, `-104424`, `-104827`, `-105230`, `-105332` under `/Users/kerim/recordings/pilot/`, each with `play.jsonl`, `head.jsonl` and `video.mp4`), a route on the minimap in all of them. None arrived. Kerim's word on it: getting in, walking, driving and choosing a place have to work before anything else, and the driving has to become better and faster.

What the logs say, with the distance to the destination as the game prints it under the minimap:

- Six drives ended `failed-recovery`. In three the car never moved at all: `20261112-104424` from 155 s, `20261112-105230` from 37 s and `20261112-105332` from 3 s, eighteen seconds each, 1990 m and twice 1820 m to go at both ends, top speed 0. By the distance the last two and the one before them (`20261112-105230` from 4 s, 1770 m to 1820 m) are the same car at the same place, tried three times. The other two: `20261112-103305` from 173 s (25 s, 1350 m to 1340 m) and `20261112-104424` from 63 s (37 s, 521 m to 522 m).
- The drives that moved did not get nearer. `20261112-104827` drove four times in a row for 206 seconds: 1810 m to 2370 m, 2370 m to 2270 m, 2230 m to 2030 m, 2010 m to 1830 m. After three and a half minutes it was where it had started. The best were `20261112-103305` from 113 s (1850 m to 1370 m in 60 s, 8 m/s) and `20261112-104424` from 3 s (1390 m to 1040 m in 60 s).
- The distance was read on 57 of 100 ticks of these drives, so the driver often does not know its speed, and nothing knows whether a drive gets nearer.
- The skill cannot arrive. It ends `done` with `route-gone` when the route has been absent for two seconds, which is true at the destination and true when the route is lost, and with `time-limit` after sixty seconds wherever it is; the rules take a `done` without a route for "where it led".

Kerim drives in the recordings that are classified: 131 minutes, 336 stretches of following a route and 137 of reversing or turning to get free (`/Users/kerim/recordings/derived/kerim/*/actions.jsonl`, actions `follow_route` and `reverse_or_turn`; videos and pad logs under `/Users/kerim/recordings/kerim/`). P40 compared the driver with him on 565 seconds (`pilot/tools/human_drive.py`, `lab/human-drive/`): the driver steers to his side on 66 of 100 clear moments.

Read `PLAN.md`, in `docs/LOG.md` the entries on driving ("The first drive to a waypoint", "Faster, and around what is in the road", "Kerim's play as the measure"), the reports of P3, P9, P34, P36 and P40, `pilot/src/pilot/drive.py`, `pilot/src/pilot/gps.py`, `pilot/src/pilot/motion.py`, in `pilot/src/pilot/skills.py` the class `DriveRoute`, and their tests.

## What to build

First show what happened, from the frames: in each of the six drives that ended `failed-recovery`, what the car stood against or why it did not move (a wall, another car, on its roof, the engine dead, the figure not in a car at all) and what the three recoveries did; in `20261112-104827`, where the car went while the distance grew by 560 m, and whether it followed the route the wrong way, missed turns, or the route itself led round. And show how Kerim gets free: for a sample of his 137 stretches, how long he reverses, how he steers while reversing and after, and how often one try is enough.

Then, in this order:

A drive that knows whether it gets nearer. The distance is the measure, so it has to be read: find out why it is missing on 43 of 100 ticks (the report of P9 has the reader's history) and raise that as far as the frames allow; where it cannot be read the last reading and the time since are kept. The skill carries in its result how far it was at the start and at the end.

An ending for having arrived, apart from the route being lost: `done` with `arrived` when the route ends and the last distances were small and falling, `failed` with a reason of its own when the route goes with the destination far away. And an ending for a drive that goes nowhere: when the distance has not fallen over a stretch you derive from the drives above although the car moves, the skill says so instead of driving on until its time is up.

A recovery that frees the car or says that it cannot. Today it is 1.25 s of reversing with the wheel turned and four seconds forward, three times, whatever the car stands against. Take from Kerim's stretches what a recovery should be, let the tries differ from one another, and let a car that has not moved at all through a full try end at once with a reason that says the car is dead or held, so that the rules can leave it. The same place tried three times, eighteen seconds each, must not happen.

Faster driving is the next card, not this one; but say in the report what the drives above and Kerim's driving tell about speed, with numbers: his metres a second on a route against the pilot's 6 to 8.

The rules that call the skill are not yours: say exactly which answer each new ending should get.

## Judging it

Replay the changed driver and skill over the fourteen drives tick by tick, with the recorded readings, as `pilot/tools/human_drive.py` does for Kerim's: the ending each would now get and when. The recorded car did not move as yours would, so this shows the endings and the reading of the distance, not the outcome; say that. Show the recovery in the simulator the driver's tests use, against a car that is held, one that comes free on the second try and one that never does. For the distance reader give the share of ticks read before and after on these drives; your sandbox refuses the native text reader, so build the change as a function of what the reader returns where you can, and for the rest write the one command and name it in the report under what could not be run. The try on the console is the reviewer's: say what it should look at first.

## Your files

`pilot/src/pilot/drive.py`, `pilot/src/pilot/gps.py`, `pilot/src/pilot/motion.py`, in `pilot/src/pilot/skills.py` only the class `DriveRoute`, their tests, `lab/drive/` and your report. Not `mission.py`, `conductor.py`, `head.py`, `vehicle_entry.py`, `minimap.py`, `waypoint.py` or `legend.py`, which others are changing at the same time. The console is in use by others while you work: the rules of `docs/tasks/README.md` about the daemon hold without exception, and nothing under `/Users/kerim/recordings/` is written, moved or deleted. Write nothing large: the disk has little room left.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green or fails only where your sandbox refuses sockets, Vision or CoreML, which you then name test by test, and the report shows what happened in the six failed drives and in the one that went round, how Kerim gets free, the replays with the new endings, the recovery in the simulator, the distance reader before and after, and the answer the rules should give to each ending.
