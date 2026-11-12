# P57: Not in the road

## Why

The pilot gets into a vehicle now (P53), and the first try in traffic killed the figure. Session `/Users/kerim/recordings/pilot/20261112-122312`, Trevor at Sandy Shores by night, in the chain of the basics test: the step before, `walk_road` in `20261112-122242`, had taken the figure to the road and along it and ended with the figure standing on the carriageway. The next session opened with `level_camera`, which stands still for six seconds, and a pickup ran the figure over five seconds in. `enter_vehicle` then pressed at the cars that had stopped around it, got into the pickup at the third press, and the driver pulled Trevor out and beat him down; the game was in a mission and ended it. `lab/enter/runs-console.json` holds what the detector saw in that session and in the two tries that went well (`20261112-122056`, beside a parked quad, one press, six seconds; `20261112-122628`).

Two things are wrong, and neither is the pressing. The pilot stands still in the carriageway: `walk_road` walks on the road and ends there, and whatever comes next and stands (the camera's levelling, a wait, the seven seconds `enter_vehicle` gives a door) stands in traffic. And it takes any vehicle within reach, a car with a driver in it as readily as a parked one, whatever the figure's health.

Kerim got into a vehicle 71 times in the classified recordings (`/Users/kerim/recordings/derived/kerim/*/actions.jsonl`, action `enter_vehicle`; videos under `/Users/kerim/recordings/kerim/`). The report of P53 looked at five of them: all five vehicles stood.

Read `PLAN.md`, in `docs/LOG.md` the entries from "On foot" on and "The basics, measured", the reports of P44, P50 and P53 with its review, `pilot/src/pilot/foot.py`, `pilot/src/pilot/vehicle_entry.py`, `pilot/src/pilot/minimap.py` for what the map shows of a road, and `pilot/src/pilot/level.py`.

## What to build

First show, from the frames: where the figure stood on the road at the end of `20261112-122242` and through the first seven seconds of `20261112-122312`, and what the minimap and the picture showed of it; and from Kerim's 71 entries, a count: how many of the vehicles were parked and empty, how many stood in traffic with a driver, how many moved, where he stood when he pressed (on the pavement, at the kerb, in the road), and what followed a car with a driver (a fight, a chase, nothing).

Then, in this order. A walk along a road goes at its side and ends at its side: `walk_road` keeps the figure off the middle of the carriageway where the map and the picture let it tell, and when it ends it does not leave the figure standing in a lane. Say what tells the side of a road from its middle, on the map (the figure's arrow against the road's width) or in the picture, and how sure it is; where it cannot tell, it says so in its result, so that what follows knows.

`enter_vehicle` does not wait in the carriageway. With only moving vehicles in sight it stays or goes to the side and waits there for one that stands; it goes into the road only to a vehicle that stands, and after a press that brought nothing it does not stand in a lane for seven seconds.

A parked vehicle before one with a driver. Find what tells them apart in the detections and the frame (a driver's box inside the vehicle's, lights at night, a vehicle that stood before the figure came against one that stopped for it) and how often it is right on the entries above; prefer the empty one, and say in the result which kind was taken. Whether an occupied car may be taken at all is the rules' to say: give the skill an argument for it and name the call the rules should make when the figure's health is low or a mission runs.

The opening `level_camera` and the rules are not yours: say what the conductor or the rules need so that the camera is not levelled in a lane.

## Judging it

Replay the changed `walk_road` over the frames of `20261112-122242` and of the walks of the morning (`20261112-110418`, `-110736`, `-111053`, `-122558`) tick by tick with the real readers, as `lab/foot/` does: where it would have ended. Replay the changed `enter_vehicle` over `lab/enter/runs.json` and `lab/enter/runs-console.json`: at the samples of `20261112-122312` it does not press at a vehicle it calls occupied or moving while the figure is in the road, and at `20261112-122056` it still gets on the quad at once. The recorded figure does not move as yours would; say what the replays show and what they cannot. Tests against the model of the game that P53 built, extended by a road with lanes, a kerb, and a driver who gets out. Your sandbox cannot run the detector: for what needs it on fresh frames, write the one command and name it in the report under what could not be run. The try on the console is the reviewer's.

## Your files

`pilot/src/pilot/foot.py`, `pilot/src/pilot/vehicle_entry.py`, their tests, `pilot/src/pilot/head.py` only for a skill's arguments, `lab/enter/`, `lab/foot/` and your report. Not `mission.py`, `goals.py`, `conductor.py`, `skills.py`, `level.py`, `minimap.py`, `drive.py`, `camera.py`, `waypoint.py` or `legend.py`, which others are changing: what you need from one of them is described exactly and left. The console is in use by others while you work: the rules of `docs/tasks/README.md` about the daemon hold without exception, and nothing under `/Users/kerim/recordings/` is written, moved or deleted. Write nothing large: the disk has little room left.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green or fails only where your sandbox refuses sockets, Vision or CoreML, which you then name test by test, and the report shows where the figure stood in the two sessions, the count over Kerim's entries, the replays of the walk and of the entry, what tells a parked vehicle from one with a driver and how often rightly, and what the rules and the conductor should do with it.
