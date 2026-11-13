# P98: The car drives through

## Why

Kerim, watching the fourth console run of 13 November: "He must not brake that often. Why does he brake? He should drive through. There is no reason for him to brake," and a moment later that the car drives very slowly. He has given the night to the driving, and this card is its first part. The second, the turn to a route behind the car, is card P99 with another worker.

What the runs of the evening measured, all with the bold style and the trip of P97 (`docs/reports/P97-one-trip-carried-to-its-end.md` has them in order):

`/Users/kerim/recordings/pilot/20261113-225006`, a highway by day, 13 to 105 s: 23 brake pulses in 115 s on a straight road, the pedal at 0.48 on average and never above 0.9, a fifth of the ticks with no pedal at all. `/Users/kerim/recordings/pilot/20261113-230030`, a highway at night with nobody on it, 565 to 779 s: median 12.5 m/s, pedal 0.49 on average, seven pulses in 82 s. `lab/live/replay_drive.py` over the two gives the limit the driver held itself to: median 11.2 and 15.0 m/s, and "over-limit" with the pedal at zero on 756 and 656 ticks. The limit is `speed_limit` (22 m/s) divided by `1 + bend / 15`, so a few degrees between the car and the route take a third off it, the curve search works with the smallest map scale (`map_scale_min` 0.7 m to the pixel, on a highway the map shows three times as much), and the speed it is compared with is the slope of a distance printed in steps of ten metres, which lags and jumps (`gps.py`, P9, the log of 13 November 20:24).

And the other side of the same law, in `20261113-225006` from 205 to 236 s: the route left the highway to the left, the far bearing went from −16 to −71 degrees in fourteen seconds, the stick lay at −0.3 to −0.5, the car stood at 214 s and was in the bushes beside the exit at 220 s. A car that is to drive through has to take the exit.

## What to do

Make the bold driver drive a road the way a player does: the pedal down where the road is straight or bends gently, off the pedal and, where that is not enough, on the brake before a bend that the car cannot take at its speed, and through the bend with the lock it needs. No brake on a straight without something in the way. Kerim's own drives are the measure of what a road allows (`/Users/kerim/recordings/kerim`, each with `pad.jsonl`; `humandrive.py` and P40's report compare a hand with the driver, `lab/drive/human-day-measurements.json` and `human-night-measurements.json` are two of his drives measured): find what he does with R2 and L2 on straights, before bends and in them, and how fast he is, and state the pilot's targets against his figures.

First find out and write down why each of the brake pulses and each second without the pedal on the two highway stretches happened: which term of the limit, which reading of the speed. Then change what the evidence points at. What the evening's reading of the code suggests, for you to confirm or correct: the limit of a straight should not fall with the angle between car and route, which is the steering's business; the curve search should use a map scale that is measured or at least not the smallest; the brake should answer a bend ahead and a thing in the way, not a noisy speed over a limit; and the speed itself may be better taken from the movement of the map (`motion.py` measures it already for "is it moving") than from the printed distance. The log entry of 13 November 20:24 and the P8 and P9 reports say what was tried before and why the brake that holds a speed was switched off on 11 November: a brake held at a standstill is reverse to the game. That must not come back.

For the exit: find in the replay why the stick stayed at a third of its travel while the far bearing ran away, and make the driver take a route that leaves the road, slowing for it first if the speed asks for that. P95 (`docs/reports/P95-the-short-aim-before-a-corner.md`) changed the aim before a corner on 13 November; read it before you touch the aim.

The careful style stays as it is unless a number is plainly wrong for both; say so if you change it.

## Your files

`pilot/src/pilot/drive.py` except `_manoeuvre`, `_end_manoeuvre`, `_recover` and the `turn_*`, `bypass_*` and `recovery_*` fields of `DriveConfig`, which are P99's; the styles in `pilot/src/pilot/cli.py` (`CAREFUL`, `BOLD`); `gps.py` and `motion.py` where the speed comes from; `DriveRoute` in `skills.py` only where a new reading has to reach the driver; `sim.py` where the simulator needs a road it does not have; new tests in `pilot/tests/test_drive_through.py`, existing driving tests only where a behaviour is changed on purpose, each named in the report; scripts and their output under `lab/drive/` with the prefix `p98`; `docs/reports/P98-the-car-drives-through.md`. You work in `/private/tmp/gta-drive-through` (branch `feat/pilot-drive-through`, from `dd775a9`; the environment is installed, the detector's model and the minimap crops are in place) and nowhere else. The rules of `docs/tasks/README.md` hold: no commit, no console, no `PS5_HOST`, nothing sent to `127.0.0.1:9395`. The machine is shared and Kerim plays on it while you work: one test process at a time, the whole gate once at the end, at low priority (`nice -n 15`).

## Done when

A script replays the driver over the two highway stretches and over the exit and prints, before and after: brake pulses, share of ticks without the pedal, mean pedal, the limit's median. After: no brake and no lifted pedal on the straight stretches except where you can name the bend or the vehicle that asked for it, tick by tick. The replay is open loop, the recorded car does not answer the new pedal: say what it can and cannot show.

In the simulator, closed loop, on its car profiles: a straight kilometre at a speed you state against Kerim's on such roads, without a brake; bends of the radii his recordings show, taken without leaving the road by more than the simulator's tests allow today; and an exit that leaves a fast road as the recorded one did, taken, on a road you build from the recorded path if the simulator has none. Each of these fails with the driver as it is.

The driving tests that exist still pass, or the report says for each changed one what it asserted and why that is no longer wanted. The gate passes.

What the console has to show cannot be tried by you. Say in the report which three stretches a first run should be judged on and by which figures, so that the reviewer can read them from `play.jsonl` without a second opinion.
