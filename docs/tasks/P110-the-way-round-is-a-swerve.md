# P110: The way round is a swerve, not a spin

## Why

Kerim watched two drives on 14 November and said two things: the car starts well and then stops before something instead of driving round it, and the tools of the night are too faulty to build on. He does not mind a lamp post touched. He minds a car that stands, and one that turns circles. The goal has changed with it: a base that drives passably and simply, on which a model can later choose what to do; not one more rule for one more case.

Recording `/Users/kerim/recordings/pilot/20261114-110629` (read-only), a trip to the cinema that failed after 384 s without ever coming nearer than 918 m. What went wrong is in the first minute.

From 24 to 37 s the car drives well, 14 to 16 m/s up Spanish Avenue. From 35.4 s the pedal is at 0.0 under the reason `curve` while the speed read stays at 14 to 16 m/s; the road climbs, and the picture from 38.5 s on does not change: the car stands at the right kerb, wheels to the right (stick 0.33), the route read 10 degrees to the right, nothing in front of it. From 39.5 s the pedal is 0.51 (`unknown-speed`) and the car does not move.

At 42.5 s the way round begins, blind (`_start_bypass(..., blind=True)`): `bypass-reverse` with the full L2 for 1.8 s, down the hill it had come up, into the junction below; then `bypass-forward` with the full stick to one side and the full pedal, which `_manoeuvre` holds for at least 2.6 s (`lock_time`), 4.5 s at most; then again to the other side. By 52 s the route lies 97 to 117 degrees to the left of the car, which stands across the junction with its front wrecked. The trip's recoveries take over at 57 s and the rest of the trip is a garage wall (120 s), a lawn (185 s), the gate of a car park (210 s) and the car park itself (228 s). Of 189 s with the driver in charge 31 percent were following, 26 percent turns on the spot, 12 percent recoveries.

Full stick with the full pedal for 2.6 s from a standstill turns a car by more than a right angle and takes it a car park's width sideways. That is a U-turn, not a way past a parked car, and it is what `bypass-forward` does every time. The night's figures say the same: ways round took 10 to 15 percent of the drive and were followed by pavements, trees and drivers pulling the figure out (`docs/LOG.md`, 14 November).

## What to do

Measure first, over the recordings of 14 November from 05:17 (`/Users/kerim/recordings/pilot/20261114-05*` to `-11*`): every `bypass-*` episode, with the heading it began at and ended at against the route (`reading.bearing`, `far_bearing`, `arrow`), the metres it moved the car by the printed distance, whether the car was on its route and following within five seconds after it, and what it began from (a detected vehicle ahead, or blind). Say how many ended further from the route's heading than 45 degrees.

Then make the way round one simple thing, in `_manoeuvre` and what starts it:

A car that stands while it follows, with nothing detected in front of it, first tries to drive on: more pedal for a moment, the stick towards the route's onward heading. Only a car that still does not move backs off.

Backing off is short and bounded by what it does, not only by time: a little way, straight, at part L2, and it ends as soon as the car has moved a car's length or stands again. Not 1.8 s of the full L2 down a hill.

Driving past is a swerve held by the heading: the car is turned some thirty degrees off the route's onward heading towards the free side, at part pedal, driven until it is abreast, and turned back to the heading. The stick comes from the heading's error, as `bypass-pass` already steers; no fixed time of full lock. It ends when the car is on its heading and moving, and it gives up after a bounded number of tries as today.

Take things away where you can: `lock_time`, the doubled reverse for blind tries, the arcs that grow with the attempts. If a state or a constant is no longer needed, remove it.

## Your files

`pilot/src/pilot/drive.py`: `_manoeuvre`, `_start_bypass`, `_retry_bypass`, and in `Driver.step` only what starts a way round from a standstill. New tests in `pilot/tests/test_swerve.py`; `pilot/tests/test_car_in_town.py`, `test_turn_round.py`, `test_drive.py`, `test_sim.py` only where a behaviour changes on purpose, each change named in the report. Scripts and output under `lab/drive/` with the prefix `p110`, small files only (contact sheets as JPEG under 300 kB, not to be committed). `docs/reports/P110-the-way-round-is-a-swerve.md`. Not yours: `avoid.py`, `skills.py`, `errands.py`, `minimap.py`, `gps.py`, `loop.py`, `cli.py`. The turn round to a route behind the car (`turn-*`) is another card's and stays, except where it shares a line with what you change.

You work in `/private/tmp/gta-drive-through` (branch `feat/pilot-swerve`, from the head of `feat/pilot-trip`; the environment is installed) and nowhere else. The rules of `docs/tasks/README.md` hold: no commit, no console, no `PS5_HOST`, nothing sent to `127.0.0.1:9395`. One process at a time with `nice -n 15`, the whole gate once at the end (`cd pilot && nice -n 15 .venv/bin/python tools/gate.py`; it takes about 125 s and prints "default gate exceeded 90 seconds", and `test_a_server_that_is_silent_twice_is_left_alone_for_a_minute` fails now and then under load and passes alone, both known and not yours to fix).

## Done when

The report has the table of the night's ways round and says what share turned the car away from its route.

Tests that fail with the code as it is: from a standstill behind a standing box in the planar simulator the car passes it and is within 20 degrees of the road's heading afterwards, having never been further than 50 degrees from it; a car that stands at a kerb with nothing in front drives on without reversing; backing off on a slope ends after a car's length. Replayed open loop over `110629` from 38 to 57 s the stick is not held at the full lock for longer than a second and the full L2 not for longer than a second.

The tests of P101 (past what stands), of `test_car_in_town.py`, `test_sim.py`, `test_turn_round.py` and `test_drive.py` pass, or the report says for each changed one what it asserted and why that is no longer wanted. `drive.py` is not longer than before. The gate passes.

What the simulator and the replay cannot show, said plainly. The next trips at the console are judged by: seconds standing while following, ways round a ten minutes, the share of them after which the car follows its route within five seconds, and whether Kerim says it looks like driving.
