# P9: Real speed from the distance the game prints on the map

## Why

P8 gave the driver a speed in map pixels per second from the motion of the map. Measured against the game, that number does not follow the speed of the car. While a route is set, the vehicle map prints a turn arrow and the distance to the destination in its lower left corner ("→ 898m", "← 830m", "↑ 1.69km"). On the driving stretch of the long recording (238 to 306 s) that distance falls by 1384 m in 67.5 s, so Kerim drove 20.5 m/s on average. Binning the map speed by the real speed taken from the distance gives:

| Real speed, m/s | Pairs | Map speed, pixels/s (median) | Metres per pixel |
|---|---:|---:|---:|
| 0 to 6 | 1 | 5.4 | 0.7 |
| 6 to 12 | 5 | 8.0 | 1.0 |
| 12 to 18 | 4 | 6.3 | 2.1 |
| 18 to 24 | 8 | 5.7 | 3.6 |
| 24 to 45 | 5 | 8.7 | 3.7 |

The map speed sits between 5 and 9 pixels per second whether the car does 30 or 130 km/h. The game zooms the vehicle map out as the car gets faster; on fast frames the roads near the arrow are drawn about half as wide. So a pixel is somewhere around 0.7 to 1 m at low speed and 3.6 m at high speed, P8's speed limit in pixels per second limits nothing, and its simulator assumed a sensor and a scale the game does not have. The map motion is still good for one thing, telling a moving car from a standing one. Twenty-three pairs from one Wi-Fi recording are thin evidence for the exact numbers and solid evidence for the shape.

The printed distance is the speed sensor the game does have, in metres, and it also says how far it is to the goal and which way the next turn goes.

## What is known about reading it

In the 260x170 HUD crop the text sits in x 36 to 120, y 118 to 142. The macOS recognition at its accurate level, without language correction, on that patch enlarged three to five times, takes about 10 ms per call. On ten picked clean frames it read nine. It makes mistakes that look like numbers: "3884m" for 388, "1284m" for 284, "1 /6 m", "3IUm". Below one kilometre the distance counts in metres, above it reads like "1.69km" and so moves in steps of ten metres. Around 294 s the distance drops from 240 to 98 m within about two seconds, a new route or a misread. `lab/gps/` holds the raw recognised strings for every frame of three stretches of that recording, made with `lab/gps/extract.py`: `093238-a.jsonl` is the yellow route (809 readings in 1544 frames), `-b` a short purple route, `-c` driving without a route, where nothing must be read. The recognition failed inside the sandbox for an earlier worker (`Failed to create CVPixelBuffer`); these files let you build and test the parsing and the estimate without it. Try the live recognition too and say what happened.

## What to build

A reader for the distance and the turn arrow in a new `pilot/src/pilot/gps.py`, taking the HUD crop. The recognition is optional at run time: without it the reader returns nothing and the driver crawls. It must not hold up the 30 Hz loop; decide between reading every few ticks inline and a thread from measured cost, and state it.

An estimate of the speed in metres per second from the timed distances. It has to reject misreads, live with gaps and with the ten metre steps above one kilometre, not turn a jump of the distance into a speed, say "unknown" when its last good reading is too old, and say something sensible when the distance grows because the car backs up or drives away from the route.

The runtime feeds this speed to the driver in place of the map speed. Map motion stays as the moving or standing signal. Every tick of `pilot.jsonl` gets the distance, the arrow and the speed, so a drive can be analysed afterwards.

The driver controls its speed in metres per second: a limit on the straight, a lower speed for bends, lifting and braking before a bend, braking only while the car is known to roll. The path is in pixels and a pixel is not a fixed length, so nothing may depend on one scale. Where a distance to a bend is needed in metres, either estimate the current scale from the two speeds or take the assumption that errs towards braking early, and show in the simulator that the choice holds over the whole range of the table. The printed distance also tells the driver that it is about to arrive. The turn arrow may be used as a check on the path; reading and logging it is required, acting on it is not.

The simulator gets the distance readout as the reader would deliver it (quantised, a few times a second, late, sometimes wrong, sometimes missing for seconds), a map whose scale grows with speed along the table with a generous band around it, and distances to the route measured in metres.

The gate has grown to six and a half minutes. Make the default run finish in under 90 seconds by keeping the wide ranges behind `tools/gate.py --full`; run both and report both.

## Your files

`pilot/src/pilot/gps.py` (new), `drive.py`, `sim.py`, `loop.py`, `replay.py`, `motion.py`, `contract.py` (additions only), `pilot/tools/` including `gate.py`, their tests and fixtures, and your report. Not yours: `bridge.py`, `cli.py`, `minimap.py`, `scene.py` (import from it if useful, do not edit it), everything under `remoteplay/`. `cli.py` builds `DriveConfig(command_delay=0.14, **overrides)` from `--set name=value`, so every tunable stays a numeric field of `DriveConfig` and `command_delay` keeps its name. Tests must pass on a machine without the recordings and without the recognition.

The recordings in `/Users/kerim/Documents/ChatGPT/gta/recordings/` are read-only; decode with `cv2`, never with `av`. A recording whose `meta.json` note contains "pilot shadow" was driven over the cable and is cleaner than the Wi-Fi ones; use it if one has appeared and say so if not.

## What must stay true

Everything P6 and P8 kept: steering only on a vehicle map, letting go without a trustworthy route, a bounded stop when the route is gone, backing out when stuck, giving up after repeated failures, `route-gone` and `failed-recovery` with pedals at zero ending a run, unknown motion never counting as standing still, damaged frames bridged only briefly. The path and the short lookahead of P8 stay. L2 reverses a standing car, so no braking without knowing that the car rolls, except the bounded stops that exist today.

## Done when

On stretch `a` the speed estimate is there for at least 70% of the time, and where it is there it stays within 3 m/s of the slope of the distance over the surrounding four seconds on at least 90% of the samples; report the same for clean and for damaged frames separately. On stretch `c` it never reports a speed. The total of the recognised distance agrees with the 1384 m.

In the simulator, with the readout failing for two seconds at a time and wrong on up to 30% of its readings, every scenario reaches its goal, stays within 5 m of the route from the moment it is first on it, never exceeds the speed limit by more than 2 m/s for longer than a second, and enters every bend at no more than the bend speed plus 2 m/s. This holds across the band of the scale and the ranges of the unknown car from P8. The list of pinned failures is rebuilt; the starts of P8 that were off the route before the first command no longer count.

Both gates pass. The report has the two tables, what the live recognition did, what the simulator still does not model, and the settings for a first real drive at walking-to-town pace with the reasons for each value. Where a target is missed, say so with the number.
