# P37: A car that cannot be freed

## Why

On 11 November the pilot left the coast road on the outside of a bend and came to rest with the front of the car on a bridge parapet, one wheel in the air (session `/Users/kerim/recordings/pilot/20261111-134519`, from 15 s). The driver tried its three escapes and gave up with `failed-recovery`, which is right: by hand neither full pedal nor full reverse moved the car afterwards. What followed is the fault. The rules head set about a new waypoint, then started `drive_route` again in the same car, which failed the same way, and so on until the time ran out. Nothing in the pilot knows that a car can be finished.

Getting out by hand worked: triangle, a few steps around the car and over the low wall, and Franklin stood on the road, where traffic stops for him (the snapshots are in the LOG entry of that afternoon). Then `enter_vehicle` was asked for a car. It walked back to the nearest standing vehicle, which was the dead one, and got in (sessions `20261111-135330` and `20261111-135411`, the second starts with Franklin already back in the seat and ends in `failed-recovery` again). A car that stops in front of him on the road was there in the first of the two.

The measure for the stream is that the story goes on, and the plan asks that the pilot frees itself from a standstill in about ten seconds. A dead car is the plainest standstill there is.

Read `PLAN.md`, the entries of 11 November in `docs/LOG.md`, `pilot/src/pilot/mission.py` and `rules` as the head uses them, `pilot/src/pilot/vehicle_entry.py`, `pilot/src/pilot/skills.py` and the conductor's tests that replay a session.

## What to build

The rules head gives a car up. When `drive_route` ends in `failed-recovery`, and again when a second `drive_route` in the same car fails that way or the distance to the waypoint has not changed over it, the head stops asking for the route in that car and plans leaving it: out of the car, away from it, another vehicle, and only then the route again. The waypoint is still set, so nothing has to be done on the map.

Leaving has to end somewhere a car can be taken. The car left behind is the largest vehicle near the figure right after getting out; the way away from it is the open side, and a road is where vehicles move. Use what the pilot has: the detector's boxes, the judge's answers (`path`, `car`), the minimap on foot. A low wall is climbed with the jump button while walking against it.

`enter_vehicle` must be able to leave one vehicle out: the one just left. How it knows that vehicle is yours to decide and to show on the recordings. Its box right after getting out, followed from frame to frame while it stays in the picture, is one way; a short walk away first and a refusal of whatever stands where the figure came from is another. A moving vehicle is no target until it has stopped; one that has stopped close by is the best there is.

If no other vehicle is taken within a time you choose, the head falls back to what it did before, so that the pilot is never worse off than today.

## Judging it

Replay the three sessions' frames through the real detector and readers and show: where the head now gives the car up in `20261111-134519`; that in `20261111-135330` the skill refuses the dead car and which vehicle it picks instead, frame by frame for the stretch where the pickup with the boat stands in front of Franklin; and that nothing changes in the entry that worked that morning (`20261111-122034`). Tests pin the head's decision after one and after two failed recoveries, the refusal of the vehicle just left, and the fallback.

## Your files

`pilot/src/pilot/mission.py`, the rules the head uses, `pilot/src/pilot/vehicle_entry.py`, `pilot/src/pilot/skills.py` where a new skill or argument needs registering, their tests, a lab folder for the replay, and your report. Not `drive.py`, `avoid.py`, `minimap.py`, `waypoint.py`, `conductor.py` or `cli.py`.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green, and the report shows the three replays, says how the vehicle left behind is known and where that can go wrong, and lists what a first live try should look at.
