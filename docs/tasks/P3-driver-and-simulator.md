# P3: the driver, and a simulator to test it against the measured delay

Package: `pilot/`. Your files: `pilot/src/pilot/drive.py`, `pilot/src/pilot/sim.py`, `pilot/tests/test_drive.py`, `pilot/tests/test_sim.py`. `pilot/src/pilot/contract.py` is fixed; do not edit it. Pure Python and numpy, no cv2, no files read at run time.

## What the driver is for

`Driver.step(reading, t, moving) -> Command` is called about 30 times a second with what the minimap reader saw in the newest frame. It has to follow the GPS route of GTA V by car to its end, on a live stream, through a link with a delay. It does not have to drive well. It has to keep going: cutting a corner or scraping a wall is fine, standing still for more than ten seconds or holding the throttle against a wall is not.

## What is known about the real system

The time from a command to the picture that shows its effect is 193 to 233 ms, measured, and stable from sample to sample. Treat 0.21 s as the delay and make the driver hold up from 0.15 to 0.30 s.

A `Reading` has the fields described in `contract.py`. `bearing` and `far_bearing` are directions in the picture from the player arrow to where the route crosses a circle of 30 and 60 crop pixels around it. `arrow` is where the car points in the picture. The map turns with the camera, and the chase camera lags behind the car in a turn, so the arrow is usually near 0 but not always: the steering error is the bearing relative to the arrow. The reader is good but not clean: on consecutive crops 0.2 s apart the near bearing differs by 3.8 degrees in the median and by 15 degrees at the 90th percentile, about one pair in a hundred jumps by more than 60 degrees, and on a damaged frame it reports `corrupt` with low `confidence` and usually no route. `minimap` is "tilted" in a vehicle, "flat" on foot and "none" in a cutscene or a menu.

How many metres a crop pixel covers is not known: the vehicle map is drawn in perspective and zooms out with speed. Somewhere between 0.5 and 2 m per pixel at the near circle is the honest range, and the far circle covers more ground per pixel than the near one. The driver has to work across that range without being told the value.

There is no speedometer. `moving` says whether the map moved over the last 0.2 s, or None when that could not be told. The driver may keep its own rough idea of the speed from the commands it gave.

The controls: steering is the left stick's x, throttle is R2, and L2 brakes and then reverses once the car stands. Analog throttle is confirmed to work. That half a stick deflection steers less than a full one is not confirmed yet, so the driver also has to cope with a car that ignores small deflections.

## The driver

Keep the tunable numbers in one dataclass `DriveConfig` with defaults, passed to `Driver(config=...)`, each with a comment on what it does. The `state` of a command names what the driver is doing. At least these behaviours:

Follow. On a tilted map with a route it steers by the near bearing relative to the arrow, uses the far bearing to see a bend coming and to slow down for it, and accounts for the delay so it does not weave. It has to tolerate single outlier readings without jerking the wheel.

Coast. When the reading is damaged, has low confidence or has briefly no route, it holds the last command for a moment (about 0.3 s) and then eases off the throttle and centres the stick. It never keeps the throttle on a picture it cannot read.

Stop at the end. When the route has been gone for about two seconds on a tilted map, it brakes to a stop and stays in a state that tells the caller the route is gone. Whether that means arrival or a lost route is the head's call, not the driver's.

Recover. When it has commanded throttle for about two seconds and `moving` is False, it is stuck: reverse for a moment with the wheel turned away from the route side, then go forward again. After three failed attempts in a row it stops trying and says so in the state. `moving` being None is not evidence of being stuck.

Idle. When the map is not "tilted" it returns a neutral command.

`step` never raises and never returns a NaN or a value out of range, whatever the reading holds, including None in every optional field and time going backwards.

## The simulator

`sim.py` is a small deterministic model, good enough to catch a wrong sign, an unstable loop under delay and a broken state machine. It is not a model of GTA and no number tuned in it counts as tuned for the game.

A kinematic bicycle on a plane: position, heading, speed. Steering deflection sets the curvature (with an optional dead zone to mimic a car that ignores small deflections), throttle accelerates against drag towards a top speed that grows with the throttle, the brake decelerates and reverses the car once it stands. Commands take effect after a configurable delay. A route is a polyline. When the car has left the route, the visible route first leads from the car to the nearest point on the polyline and continues from there, which is roughly what the game's GPS does when it recalculates. A scenario may contain wall segments that stop the car, so that it only gets free by reversing.

From the true state it produces what the reader would have seen: the bearings at the near and far circle for a configurable map scale in metres per pixel (the far circle may use a larger one), the arrow heading relative to a camera that follows the car's heading with a lag, noise on the angles, occasional outliers, damaged readings with a configurable rate, and `moving` from the true speed. Every random draw comes from a seeded generator.

A run returns what the tests need: whether the end was reached and when, the mean and maximum distance from the route, the longest time without progress, and how often the steering changed sign per second.

## Tests

`test_drive.py` checks the behaviours directly on hand-made readings: idle off a tilted map, coast and throttle release on unreadable frames, braking when the route is gone, the recovery sequence and its limit of three attempts, no jerk on a single outlier, and the guarantee that `step` never raises and stays in range on hostile input.

`test_sim.py` drives closed loop. Scenarios: a straight with the car starting 3 m beside the route and 20 degrees off; a 90 degree turn to the left and one to the right; an S bend; a loop around a city block with four turns; a start facing a wall three metres ahead with the route leading away to the side. Each has to finish for delays of 0.15, 0.21 and 0.30 s, for map scales of 0.5, 1 and 2 m per pixel, with the reader's noise, one percent outliers and five percent damaged readings, on three seeds, and with the steering dead zone both off and at 0.25. Finishing means: the end is reached, the car never goes more than 10 seconds without progress, the mean distance from the route stays under 3 m and the maximum under 10 m, and the steering does not flip sign more than twice a second on the straight. If the driver cannot meet a bound in some corner of that grid, do not loosen the test silently: mark the case as an expected failure with the measured number and name it in the report.

Keep the whole suite under a minute.

## Done when

`.venv/bin/python tools/gate.py` in `pilot/` prints "gate passed". The report describes how the driver decides in a few sentences, gives the table of scenario results across the grid, names every expected failure with its number, and lists the parameters of `DriveConfig` you expect to need tuning on the real game, with the direction to turn them when the car weaves, cuts corners or brakes too late.
