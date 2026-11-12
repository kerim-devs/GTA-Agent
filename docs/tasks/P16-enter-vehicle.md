# P16: Getting into the nearest vehicle

## Why

Almost everything in this game starts with a car: missions, getting away from the police, crossing the map. The pilot can drive a route once it sits in a vehicle, but it cannot get into one. The head can press triangle, yet it sees one picture every ten seconds and has no way to walk up to a car. P14 is building a detector that reports vehicles and people in the frame about ten times a second (`Detection` in `contract.py`, delivered in `Observation.objects` with the capture time in `objects_time`). This card builds the skill that uses it. Read `docs/tasks/README.md`, sections "A new skill" and "Recordings".

## What the game does, as far as known

Pressing triangle near a vehicle makes the character walk to the nearest door by himself and get in; if somebody sits in it he throws them out first. That walk takes up to several seconds, and pushing a stick during it cancels it. It only starts within a few metres of the vehicle. Once the character sits, the minimap switches to the vehicle map, which the reader reports as `reading.minimap == "tilted"`. None of this has been tried with the pilot yet: treat distances and timings as estimates, keep them as named constants at the top, and list them in the report as things to try live.

## What to build

`pilot/src/pilot/vehicle_entry.py` with a skill `enter_vehicle`: a time limit up to 25 s and an optional choice of kind (any, car, motorcycle).

It picks a target among the detected vehicles, the one that is closest by the look of its box, with a preference for what is in front, and keeps the same target from tick to tick while it stays plausible, so it does not hop between two cars. It turns the camera until the target is in the middle of the picture and walks towards it, slower as the box grows. When the box says the vehicle is within reach it lets go of both sticks, taps triangle, and waits with a neutral pad for the map to switch; if it has not switched after a few seconds it approaches and tries again, a bounded number of times. When no vehicle is visible it turns the camera in steps to look around, for a bounded time. It is done when the vehicle map has been seen for half a second, and it fails with a reason the head can use: nothing found, could not reach it, the door never opened, time up, no detections delivered at all.

Detections are late and imperfect: they describe a frame that is up to a few hundred milliseconds old, a vehicle can be missing for several results in a row, and boxes jitter. Ignore results older than half a second. It never sprints into traffic and never presses anything but triangle.

## Judging it

A simulation: a walker on a plane with a camera behind him, parked and moving vehicles projected into the picture as boxes through a pinhole camera, the detector's period, delay, jitter, misses and false boxes, the 0.14 s between command and picture, and the game's rule that triangle works only within reach and is cancelled by the sticks. Show over many seeds how often and how fast it gets in, that it gives up within its limit when there is no vehicle or the vehicle drives away, and that it never holds anything when it ends. Keep the simulation's assumptions about the camera's field of view and the turn rate in one place and say what happens when they are off by half and by double.

## Your files

`pilot/src/pilot/vehicle_entry.py`, `pilot/tests/test_vehicle_entry.py`, `pilot/tools/sim_vehicle_entry.py`, `lab/vehicle_entry/` for results, and your report. Not `skills.py`, `head.py`, `head_prompt.txt`, `conductor.py`, `contract.py` or `objects.py`.

## Done when

In the simulation it gets into a parked vehicle that starts in view within its limit in at least 9 of 10 runs, also with the camera constants off by half and by double, and every other run ends as a bounded failure with a reason. Tests pin the rules of the README, that the sticks are neutral from the triangle press until the map switches or the wait ends, that stale and missing detections never keep a stick pushed for longer than half a second, and that the target does not change while it is visible. The default gate passes. The report gives the numbers, the constants to tune live, and the text for the head.
