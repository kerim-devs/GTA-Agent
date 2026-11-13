# P95: The short aim before a corner

## Why

Kerim does not accept the steering: the car weaves. `docs/LOG.md`, the entry "The steering against Kerim's hand" of 13 November, has what was measured that evening; read it first. In short: on a straight way the aim lies 20 px out and the car is steady, at the console and in the closed loop with the car as measured (`lab/drive/measured.py`). Wherever the way bends the aim lies 8 px out, on 25, 9 and 15 percent of the ticks of the three console drives of that day, and there the car swings: by 8 to 10 degrees in the measured loop, 5 to 6 with the turn still to show taken off the error, and by 18 to 37 degrees to either side at the console.

Two things are wrong with the short aim, and both sit in `_target` in `pilot/src/pilot/drive.py`.

It is the reader's wander over a short arm. The path's first point lies 11 px out and more, so the aim at 8 px is found by continuing the first visible segment, 5 to 6 px long, back under the arrow. Each end of that segment wanders by about a pixel. In the measured loop the swing goes with the arm and hardly with the speed: with the aim forced to 8, 10, 12, 14 and 16 px the spread of the heading is 8, 3.6, 1.7, 1.0 and 0.5 degrees at 8, 12 and 16 m/s alike. Simply taking the short aim further out is not the answer: at 10 px the planar simulator's hidden bend is cut and 5 cases of `tests/test_sim.py` and `tests/test_gps.py` fail, at 12 px 17.

And before a corner it points the wrong way. Recording `/Users/kerim/recordings/pilot/20261113-183223` (read-only), 206 to 216 s: a right-angled turn to the right lies ahead, 37 px out at 207.0 s and 22 px out at 210.6 s, on a map of about 3 m to the pixel, the car at 9 to 13 m/s and gaining. The path read at 210.07 s is `(0,13) (1,18) (6,23) (13,24) (19,24) …`. Until 210.1 s both aims lay 1 to 3 degrees off straight ahead and the stick at zero, which is right as long as the corner is far. Then the first visible segment began to lean into the turn, its continuation back under the arrow came to lie left of the car, and the aim at 8 px went to 6, 14 and 28 degrees to the left while the far aim said 9, 13 and 18 to the right: the stick went to 0.39, 0.45 and 0.65 to the left, into a right turn, and the brake came at 210.9 s with 0.63. The pedal had let the car gain speed all the way to there.

Kerim's order of that day: a sound base, driving first, and it has to run smoothly.

## What to do

First show both faults where they can be repeated: the readings of 206 to 216 s from `play.jsonl` replayed through the `Driver` (the stick, the two aims and the pedal by tick, as `docs/LOG.md` has them), and the short aim's swing in `lab/drive/measured.py`.

Then a short aim that is steadier and does not point away from a turn. The leads, and you follow the numbers: the car stands on the route or beside it, so the way from the car to the path's first point is known and needs no continuation of a short segment backwards; the direction of the path's beginning can be taken from more than two points where they lie in a line; the aim's distance can go by how far away the bend is, far while the corner is far and short only when it comes within reach, instead of 8 px from the moment the way bends anywhere within 40. What the short aim is there for has to stay: a corner hidden under the arrow or just behind the path's first point is not cut, which the planar simulator's bends and `test_hidden_bend_does_not_cut_the_route_on_a_zoomed_map` hold.

Then the pedal before a corner, only as far as this recording shows it: the car gained speed from 9 to 13 m/s toward a right angle 60 to 70 m ahead and braked a second before it. Say from the replay why `_speed_limit` and the bend the pedal goes by did not slow it, and mend it if the mend is small and the planar simulator's limits for the speed in a bend hold; if it is not small, say what you found and leave it.

## Your files

`pilot/src/pilot/drive.py` (`_target`, `_straight`, the choice of the aim in `Driver.step`, and the pedal's bend only for the third part), `pilot/tests/test_drive*.py`, `pilot/tests/test_sim.py` and `pilot/tests/test_gps.py` for baselines that move, a fixture of the recorded readings, `lab/drive/`, and `docs/reports/P95-the-short-aim-before-a-corner.md`. Not the turn memory (`_pending`, `yaw_memory`) and not the far aim on a straight: both are measured and stay. Not `skills.py`, `errands.py`, `mission.py`, `conductor.py`.

## Done when

A test replays the readings of 209.5 to 211 s and shows the stick not going to the left of zero before that right turn; a test in the planar simulator holds the bends within the limits they have today and not more than half a metre further from the road than today on any of them; `lab/drive/measured.py` shows the short aim's spread on a straight at 8, 12 and 16 m/s under 3 degrees (5 to 6 today), and the report gives its table before and after, with the cars that turn more, answer later and show on a closer map. No test that passed before fails; baselines of known failures that move are named with their old and new figures. The gate passes in `pilot/`: run the tests of your own files while you work and the whole gate once at the end, the machine is shared; if the sandbox fails the gate on local sockets or on the detector's model, name those tests and do not count them.

If the three degrees cannot be had without cutting the hidden bend, the report says how far you came and what each try gave. A measured no is worth more than a change that is not shown to work.
