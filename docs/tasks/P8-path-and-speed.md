# P8: A driver that takes corners: route path, speed, short lookahead

## Why

Driver v1 (P6) steers the right way but cannot take a corner. It aims at the point where the route crosses a circle of 30 map pixels around the arrow, so it starts every turn 30 pixels early and cuts it by about a third of that. A road is roughly 10 to 15 pixels wide near the arrow, so the car leaves the road at every junction, whatever a pixel is in metres. It also has no idea how fast it is going: it holds a pedal position, and a car that arrives at a corner at full speed does not make it with any steering. Read `docs/reports/P6-driver-v1.md` with its review section first.

P6 tried a target closer to the arrow and dropped it because it agreed less often with the human's stick. That yardstick was wrong, and it was this project's mistake, not the worker's: just before a corner the route close to the arrow is still straight while a person already steers, and on the Wi-Fi recording the person steers on a picture that is most of a second old. A short target is judged against the picture, not against the stick.

## What to build

Three things that belong together.

The reader hands over the route as a path instead of two angles. `_trace` already follows the route outward from the arrow; give `Reading` a new last field with a default, for instance `path: tuple[tuple[float, float], ...] = ()`, holding points of the route ordered outward from the arrow, in map pixels relative to the arrow with x to the right and y up. Take them where the route is really visible: the arrow is about 18 pixels long and hides the route under it and under its tip, so the first trustworthy point lies around 11 to 15 pixels out, and what the flood guesses under the arrow is not evidence. Points every few pixels out to the edge of the map are enough. `bearing` and `far_bearing` stay as they are.

The driver gets a rough speed. `map_motion` returns how many pixels the map moved between two crops about 0.2 s apart; divided by the time between them that is a speed in map pixels per second. `loop.py` computes the displacement already and reduces it to a yes or no for the driver. Pass the speed along as well, as a new optional argument of `Driver.step` that defaults to unknown. It is rough: it abstains on damaged frames, it mixes in the rotation of the map in a turn, and the map is drawn in perspective. Treat it as a noisy sensor that is sometimes missing.

The driver steers at a short lookahead and plans its speed. It aims at a point on the path a configurable distance out (`lookahead_px`, start near the closest visible point), looks further along the path for how sharp the road bends, and from that decides how fast it may be: lift early, brake if it is clearly too fast, and only then turn in. Braking uses L2, which reverses a standing car, so it brakes only while the measured speed says the car is rolling, and for a bounded time when the speed is unknown. Without a path or without a speed it must still behave sensibly: fall back to the bearings, and without a speed drive slowly rather than blind.

The simulator has to make this testable. It needs a car whose speed follows the pedals and which runs wide when it is too fast for the bend (a grip limit), the path and the speed reading as the reader and the runtime would deliver them (hidden under the arrow, noisy, sometimes missing, delayed), and a range for everything about the real car that is unknown: grip, acceleration, braking, top speed, pixel scale. The driver must hold up across that range, not at one tuned point.

## Judging the path

Against the picture. Draw the returned points over enlarged crops and look at them: at least 60 clean crops with a route, half of them picked at random and half where the short direction differs from `bearing` by more than 25 degrees, which is where corners and mistakes both are. Count how many are right, by which you mean every point sits on the drawn route line. Report the share of clean route crops that get a first point within 16 pixels, and the jitter of the short direction between consecutive video frames compared with that of `bearing`. Measure the width of a road near the arrow in pixels on a dozen vehicle maps and state it; the limit below rests on it.

Agreement with the human stick may be reported, and it must not decide anything on the Wi-Fi recordings. New recordings may appear in `/Users/kerim/Documents/ChatGPT/gta/recordings/` while you work. One whose `meta.json` note contains "pilot shadow" was driven over the cable with about 0.14 s from input to picture; on such a recording the human is a fair reference for direction and for timing, so use it if it is there, and say so if it is not.

## Your files

`pilot/src/pilot/contract.py` (additions only), `minimap.py`, `motion.py`, `drive.py`, `sim.py`, `replay.py`, `loop.py` (only to pass the speed and what the contract addition forces), their tests and fixtures, evaluation scripts under `pilot/tools/`, and your report. Not yours: `bridge.py`, `cli.py`, `scene.py`, everything under `remoteplay/`. `cli.py` builds `DriveConfig(command_delay=0.14, **overrides)` from `--set name=value`, so every tunable stays a numeric field of `DriveConfig` and `command_delay` keeps its name. Keep generated evidence small: tables and a few overlay sheets, no replay logs of several megabytes.

The recordings are read-only; write outputs into your worktree. Decode video with `cv2`, never with `av`. The labelled crops are in `lab/minimap/data/crops.npy`; the harness runs as `cd lab/minimap && /Users/kerim/Documents/ChatGPT/gta/lab/minimap/.venv/bin/python harness.py impl_pilot/minimap.py --split dev` (and `held`).

## What must stay true

Everything P6 kept: the driver steers only on a vehicle map, lets go without a trustworthy route, stops with bounded braking when the route is gone, backs out when stuck, gives up after repeated failures, and `route-gone` and `failed-recovery` with pedals at zero still end a run in `loop.py`. Unknown motion never counts as standing still. Damaged frames are bridged only briefly and only when they agree with the last clean one. The reader does not get worse on the labelled splits (no false route, every labelled route found, near bearing within 45 degrees, under 3 ms on average including the path), and the direction numbers of P6 on the long recording do not fall below its targets.

## Done when

In the simulator every scenario reaches its goal and stays within 5 map pixels of the route (2.5, 5 and 10 m at 0.5, 1 and 2 m per pixel), at command delays of 0.14, 0.21 and 0.3 s and across the ranges of the unknown car, with the steering flipping at most twice a second. The list of pinned failures is rebuilt for the new driver; the aim is an empty list for the middle of the ranges, and every entry that remains at the edges is explained by what would have to be true of the real car for it to matter.

On the picture check at least 90% of the inspected crops have every point on the route line, and the errors are described.

The gate passes. The report has the simulator table against P6, the picture check with a few overlay sheets, the notebook of what was tried, what the simulator still does not model, and the short list of `DriveConfig` fields to set on the first real drive with careful starting values, including the slowest sensible speed limit. Where a target is missed, say so with the number.
