# P84: The drive does not weave

## Why

On 13 November, 16:34, the pilot took a parked car and drove a route of 1245 m by night (recording `/Users/kerim/recordings/pilot/20261113-163218`, read-only; `drive_route` runs from 120 s to 315 s of `play.jsonl`). Kerim, watching: why does it drive in so many snaking lines, why does it drive so stupidly. At about 215 s the car stood on a verge beside the road, at a wall.

What `play.jsonl` shows of those ticks, in quarter minutes: from 120 to 150 s the bearing read from the purple route spreads by 55 and 59 degrees (standard deviation of `reading.bearing`) with the stick at 0.62 and 0.78 of full on average; from 150 to 195 s the spread is 9 to 23 degrees; from 225 to 255 s it is 44 and 50 again. The stick changes side four to six times in every quarter minute, about once in three seconds, with the throttle at 0.14 to 0.37 on average. Whether the reading jumps or the control overcorrects is not known: nobody has measured it.

One lead, from a second reading of the same data, to be checked and not taken on trust: `reading.bearing` is not what the driver steers by when the reader has traced the route. In `drive.py` the error then comes from `_target(path, lookahead_px)`, and where the first point of the path lies further out than the look-ahead (the reader in `minimap.py` gives no point nearer than 11 px, "Export only observed route pixels") `_target` continues the first two raster points of the path back to the look-ahead's radius. Two neighbouring raster points give a direction in steps of 45 degrees. Computed from the recording, that angle jumps by 14.0 degrees from one frame to the next at the ninetieth percentile between 150 and 165 s and by 14.4 between 180 and 195 s, where the bearing less the arrow moves by 3.4 and 3.1. The weaving is there before the stream broke at 199.6 s (no frames until 219.7 s), with the frames fresh and the loop at 35 ms in the median. Measure the angle the driver really uses and what it does to the stick, not only `reading.bearing`.

Kerim's order of the same afternoon: a sound base comes first, and driving is the first part of it. It has to run smoothly.

Read `PLAN.md`, `docs/tasks/README.md`, the entries on driving in `docs/LOG.md` (P73, P80 and the night of 12 to 13 November), then `pilot/src/pilot/drive.py`, the class of `drive_route`, what it reads its bearing from, `pilot/src/pilot/sim.py` and `tests/test_sim.py`, `tests/test_drive*.py`.

## What to do

Measure first, and put the numbers in the report. A script under `lab/drive/` reads the recording (video, `frames.jsonl`, `play.jsonl`) and says for the drive: how far the bearing read on each frame lies from the course the route's own path gives over the next stretch (the reader's noise), how the bearing jumps from one frame to the next while the car goes straight, how long after a change of the bearing the stick follows and how long after the stick the map turns (the loop's delay), and how often the stick changes side with no change of course behind it. Do the same for one stretch of Kerim's own driving on a route (`/Users/kerim/recordings/kerim/` of 13 November and the recordings named in `docs/tasks/README.md`), so that a hand on the stick is the comparison. Night and day, if both are there.

Then mend what the numbers name, and only that. If the reading jumps, it is steadied where it is read or where it is used, without making the car late in a real bend. If the control overcorrects, its gain, its look-ahead or its damping is changed, by speed where that matters. If the car was sent off the road by something else, a route read behind the car, a turn taken too late, say what, and mend it if it is in your files.

Every change is shown twice: on the recording's own readings, replayed through the controller, where the stick must not change side more than twice in a quarter minute of a straight stretch, and in the simulator's closed loop (`sim.py`), with the noise you measured put in, where the car stays on the road through the existing course and a bend.

## Your files

`pilot/src/pilot/drive.py`, the class of `drive_route` and its helpers where they are not in `drive.py`, `pilot/src/pilot/sim.py` only to put in measured noise or delay, their tests, `lab/drive/` (new), and `docs/reports/P84-the-drive-does-not-weave.md`. Not `minimap.py`'s classes of the map and its blips, not `conductor.py`, `scene.py`, `vehicle_entry.py`, `mission.py`: two workers are in those beside you. If the fault is in the reader of the route in `minimap.py`, mend it there only in the functions that trace the route, and say so.

## Done when

The report gives the measured noise, delay and count of side changes before and after, for the pilot's drive and for Kerim's. A test replays the recorded readings of a straight stretch of this drive and fails before the change on the count of side changes and passes after it; a test in the simulator drives a course with the measured noise and stays on the road; no test of driving that passed before fails. The gate passes in `pilot/`: run the tests of your own files while you work and the whole gate once at the end, the machine is shared.
