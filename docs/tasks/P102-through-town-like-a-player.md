# P102: Through town like a player

## Why

In the night of 14 November the trip of P97 arrived for the first time: 5.5 km from Sandy Shores to a shop in the city (`/Users/kerim/recordings/pilot/20261114-005357`). On the freeway the bold driver of P98 was faster than Kerim: 25 to 30 m/s at the median over two minutes, the brake hardly touched. In town it is neither safe nor fluent, and Kerim's order for the night is both: "He must not brake that often. He should drive through," and a car that gets where it is going.

What the trips in town measured, all with the bold style, each tick of `play.jsonl` carrying `driver_state`, and from `20261114-011017` on also `speed_reason` and `around_pedal` in its `result`:

`/Users/kerim/recordings/pilot/20261114-011017`, 98 to 106 s: from a standstill behind a lorry the car is taken from 6.6 to 22 m/s in five and a half seconds with `speed_reason` "straight", the route turns left at the junction ahead, and the first thing the speed law says of it is "hidden-turn" at 104.0 s with the brake at 0.8 and the car at 22 m/s. At 106 s it is in the side of a police car in the middle of the junction, two stars follow, the police pin it to a wall and the trip ends in an arrest. The turn was on the map for all of those seconds.

`/Users/kerim/recordings/pilot/20261114-010438`, 13 to 265 s, a kilometre through the city: where the car moves its median is 8.4 m/s, L2 is down on 8 percent of the ticks that follow the route (Kerim's drives: 0.7 to 3.6 percent), there are 17 brake pulses a minute and no pedal on 29 percent of the ticks. `20261114-005357` from 545 s to its end is the same picture on the last 600 m before the shop: sixty seconds for the last 200 m.

So in town the driver is too fast where it has to turn and brakes too often where it does not.

## What to do

Find out first, on the recordings, and write down: why the turn of `011017` was not in the speed limit before the arrow was on it (the path's length on the map at that speed and zoom, `curve_step`, `curve_trim`, the scale the law assumes at each speed, what the reader gave as the path), and for a town stretch of `010438` and of `011017` what each brake pulse and each second without the pedal was for, by `speed_reason`, `around_pedal` and the picture: a bend that was there, a vehicle that was there, or nothing. `lab/live/replay_drive.py` runs the reader and the driver over a recording; `lab/drive/p98*` are the scripts and figures of the card that built this speed law, and `docs/reports/P98-the-car-drives-through.md` says what it measured and decided. Read it before you touch the law.

Then measure what Kerim does in town (`/Users/kerim/recordings/kerim`, each with `pad.jsonl`; `lab/drive/human-day-measurements.json`, `humandrive.py`): how fast he comes to a junction where his route turns, where he lifts and where he brakes before it, how fast he is in the turn, how fast between two junctions a block apart, and how much of the time L2 is down. State the pilot's targets against his figures.

Then change the speed law so that both hold. A turn of the route at a junction is in the limit as soon as the map shows it, and the car reaches it at a speed at which it turns: lifted early, braked once and in time where lifting is not enough, not with a late hard pulse in the junction. Where the map does not show far enough to know that the road goes on straight, the car is not taken to a speed it cannot shed within what the map shows. And between junctions, where the road is straight and nothing is in the way, there is no brake and no lifted pedal that you cannot name the reason for. The freeway must stay as fast as it is: the stretches of `20261114-005357` from 400 to 520 s are the measure, 25 to 30 m/s at the median with at most a handful of pulses.

If the evidence says that the many pulses come from the avoider (`around_pedal` below 1 or at −1) and not from the speed law, say so with the figures and change what the evidence points at; `avoid.py` is yours for that, its waiting and passing logic of P101 is not to be undone.

## Your files

In `pilot/src/pilot/drive.py`: `_road_limit`, `_speed_limit`, `_map_scale`, `_pedal`, `_pulsed` and the fields of `DriveConfig` they read; the styles in `pilot/src/pilot/cli.py`; `avoid.py` as far as the last paragraph above allows; `sim.py` where the simulator needs a junction it does not have; new tests in `pilot/tests/test_town_corners.py`, existing tests only where a behaviour changes on purpose, each named in the report; scripts and their output under `lab/drive/` with the prefix `p102`, small files only, the disk has 11 GB left; `docs/reports/P102-through-town-like-a-player.md`. Not yours: `_manoeuvre`, `_recover`, the turn and the way round of P99 and P101, the steering, `skills.py`, `errands.py`, `vehicle_entry.py`, which are being changed in another worktree tonight. If the speed law needs something from them, say so in the report instead of doing it.

You work in `/private/tmp/gta-drive-through` (branch `feat/pilot-town-corners`, from `60a9747`; the environment is installed, the detector's model and the minimap crops are in place) and nowhere else. The rules of `docs/tasks/README.md` hold: no commit, no console, no `PS5_HOST`, nothing sent to `127.0.0.1:9395`. The pilot drives at the console all night on this machine and needs its tick rate: one process at a time with `nice -n 15`, the reader over the seconds you need and not over whole recordings, the whole gate once at the end (`cd pilot && nice -n 15 .venv/bin/python tools/gate.py`; under this load it takes about 125 s and prints "default gate exceeded 90 seconds", which is known and not yours to fix).

## Done when

A script replays the driver over `011017` from 96 to 106 s and prints, before and after, the limit, its reason and the pedal tick by tick: after, the turn is in the limit seconds before the arrow reaches it and the pedal and the brake ask for a speed the car can turn at, by Kerim's figure for such a turn. The replay is open loop, the recorded car does not answer: say what it can and cannot show.

In the simulator, closed loop, on its car profiles: a block of 150 m from a standstill to a right-angled turn of the route at a junction, taken without leaving the road by more than the simulator's tests allow today and entered at a speed you state against Kerim's; two such blocks in a row; and a straight kilometre and the exit of P98 as fast as P98 left them. The junction tests fail with the driver as it is, or the report says why they already passed and what then explains the recording.

Over the town stretches you analysed, replayed: the count of brake pulses and of seconds without the pedal that have no bend and no vehicle behind them, before and after, and after it is none or each is named.

The driving tests that exist still pass, or the report says for each changed one what it asserted and why that is no longer wanted. The gate passes.

What the console has to show cannot be tried by you. Say in the report which figures of `play.jsonl` the first town trips are to be judged on.
