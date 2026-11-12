# P17: Driving without a route

## Why

The driver follows the GPS line the game draws on the minimap. Without a line it does nothing: a car the pilot has just stolen stands still, and getting away from the police, which is half of this game, is impossible. This card makes the car follow the road it is on, turn at junctions and keep going, with no route at all. It does not need to drive well. It needs to stay on roads most of the time, get out of what it hits, and look like somebody who wants to get away.

Read `docs/reports/P8-path-and-speed.md` and `P9-speed-from-gps-distance.md` first. Two findings matter here. The vehicle map zooms out with speed, so the motion of the map in pixels says nothing about how fast the car is, and without a route there is no printed distance to take the speed from. And judging a driver by how well it agrees with the human's stick was a mistake once already: the human looks at the world, not at the map. Judge what you build against the picture.

## What to build

`pilot/src/pilot/roam.py`.

A road reader that takes the HUD crop of a vehicle map and returns the road ahead of the arrow as a path in the same form as `Reading.path`: points in map pixels relative to the arrow, x to the right and y up, starting close to the arrow. At a junction it follows the wish it was given: straight on, left or right, and when the wish cannot be met, whatever continues. It says when it cannot see a road under the arrow (off road, a car park, a damaged frame) instead of inventing one. `minimap.py` already separates the map from the world that shines through it and knows the arrow; import from it.

A skill `drive_free` with a time limit up to 120 s, a turn wish (any, straight, left, right) and a pace (slow, normal, fast). It steers along that path. Whether it can reuse `Driver` by handing it a reading with the road as its path, or needs its own steering, is yours to find out; `drive.py` is not yours, so if a small change there would make the reuse possible, describe it in the report instead of making it. Without a speed measurement it must still not fly off at every bend: find a signal for the pace that works without a route, for instance the zoom of the map, which follows speed, or the road's width in pixels, and say how well it holds on the recording. When the map stops moving while it pushes, it backs out like the driver does, and after repeated failures it ends. When no road is readable for a few seconds it slows down and ends with a reason.

## Judging it

The road reader against the picture: draw the path over enlarged crops of at least 60 vehicle-map frames without a route from the long recording, picked with a fixed seed, and count by eye on how many the path lies on the road the car is on for its whole length, on how many it leaves it, and on how many it rightly says nothing. Keep the sheets under `lab/roam/`. About a quarter of that recording is driving without a route, among it the motorbike chase from about 150 s; find the spans with the reader. The route stretches can serve as a check, because there the road under the route is known.

The skill in a simulation of your own: a road network with bends, junctions and dead ends, a car with the pedals and grip of `sim.py` (import it, do not edit it), the map's zoom law, the 0.14 s delay, and a road reader that is noisy, late and sometimes blind. Show over many seeds how long it stays on the road, how it gets out of a dead end and that every run ends within its limits.

## Your files

`pilot/src/pilot/roam.py`, `pilot/tests/test_roam.py` with fixtures, `pilot/tools/evaluate_roam.py`, `pilot/tools/sim_roam.py`, `lab/roam/`, and your report. Not `drive.py`, `sim.py`, `minimap.py`, `skills.py`, `head.py`, `conductor.py` or `contract.py`.

## Done when

On the labelled frames the path lies on the car's road on at least 8 in 10 frames where a road is under the arrow, and it invents a road on fewer than 1 in 20 frames where there is none. The reader takes under 3 ms on average. In the simulation the car stays on the road for at least 80 per cent of the driven time at the normal pace, leaves a dead end, and never exceeds its limits. Tests pin the rules of the README and the behaviour at a junction for each turn wish. The default gate passes. The report shows the sheets, the pace signal with its numbers, what the head is told, and what has to be tried on the real car.
