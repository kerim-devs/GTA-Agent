# P99: Round to a route behind the car

## Why

Kerim has given the night of 13 November to the driving. Card P98, with another worker, makes the car drive through; this card is the turn.

The first console run of the trip (`/Users/kerim/recordings/pilot/20261113-224327`, 38 s, `docs/reports/P97-one-trip-carried-to-its-end.md`) stood on a dirt track beside the road, a guard rail on its left, and the waypoint's route began behind it and ran forward on the other side of the rail: the near bearing read −90 to −140 degrees, the far bearing −7 to −11, the path's first points lay behind and to the left and its later ones ahead, 24 px to the left. `drive_route` gave up twice within ten seconds with `failed-recovery`. In `play.jsonl` from 9.7 to 31.7 s the brake is never pressed: the stick goes to one lock for 0.57 s and to the other for 0.45 s with the pedal down, then to a third of the pedal, once a second, and the car stays where it is. `_manoeuvre` in `drive.py` begins a turn when the near error is over 120 degrees, reverses only while the far error is over 60, and calls the turn done when the far error is under 25: with the two bearings 120 degrees apart the reverse is skipped, the forward second ends as a turn made, and the next tick begins another, until the count of attempts ends the drive.

P80 (`docs/reports/P80-round-a-stopped-car-and-round-to-the-route.md`) built this turn on 13 November for a route that lies behind the car as a whole, and P34 (`docs/reports/P34-a-route-that-starts-behind-the-car.md`) is the reader's side of it. Read both first.

## What to do

Make the turn one thing from its beginning to its end. What begins it, what it steers by and what ends it have to be the same judgement of where the route goes, and a turn that has begun moves the car: back with one lock, forward with the other, until the way the route leads lies ahead of the car, or until its tries are spent. A turn that did not move the car is not a turn made.

Decide what the right move is where the route's nearest piece lies behind and the route itself runs forward beside the car, as it did here. The game draws such a route when the car stands off the road or on the wrong carriageway, and it means: get onto that road. Often driving on and steering toward it is right and a turn is wrong; behind a rail or a kerb it is not possible at this spot and the car should drive on along its own way until the two meet or the game draws another route. State the rule you choose and what it reads, and show on the recorded readings of `20261113-224327` what the driver now does there tick by tick. The trip (P97) answers a `failed-recovery` by driving on from the spot with `get_away` for three seconds and then asking for the route again; your driver should need that seldom, and where it gives up it should say why in a state the trip can tell from a dead car.

Look at Kerim's own recordings (`/Users/kerim/recordings/kerim`, each with `pad.jsonl`) for what he does when the route begins behind him: how often he reverses and for how long, whether he turns in a forward arc where there is room. P80 measured the turn in the simulator at 4.7 to 7.4 s; say what his takes.

## Your files

In `pilot/src/pilot/drive.py`: `_manoeuvre`, `_end_manoeuvre`, `_recover`, the call into them from `step` as far as the turn's trigger needs it, and the `turn_*`, `bypass_*` and `recovery_*` fields of `DriveConfig`. Everything else in `drive.py` is P98's at this hour: the speed limit, the pulsed brake, the steering of the ordinary drive and the styles in `cli.py`. If the turn needs a change there, say so in the report instead of making it. `sim.py` where the simulator needs a rail or a second road; new tests in `pilot/tests/test_turn_round.py`, existing tests only where a behaviour changes on purpose, each named in the report; scripts and their output under `lab/drive/` with the prefix `p99`; `docs/reports/P99-round-to-a-route-behind.md`. You work in `/private/tmp/gta-turn-round` (branch `feat/pilot-turn-round`, from `dd775a9`; the environment is installed, the detector's model and the minimap crops are in place) and nowhere else. The rules of `docs/tasks/README.md` hold: no commit, no console, no `PS5_HOST`, nothing sent to `127.0.0.1:9395`. The machine is shared and Kerim plays on it while you work: one test process at a time, the whole gate once at the end, at low priority (`nice -n 15`).

## Done when

A test feeds the driver the recorded readings of `20261113-224327` from 9.7 s on and fails today: the driver must not end in `failed-recovery` within ten seconds without the car having been asked to move back or on, and what it asks for must be the rule you stated. The replay is open loop; say what it cannot show.

In the simulator, closed loop, on its car profiles: a route wholly behind the car is faced as fast as P80 measured or faster and on every profile; a route whose nearest piece is behind while it runs forward beside the car, with free ground between, is joined without a reverse; the same with a wall between ends with the car driving on along its own way and not standing, and with a state that says so if the drive ends. Each fails with the driver as it is, or the report says why it already passed.

P80's tests of the turn and of the way round a stopped car still pass, or the report says for each changed one what it asserted and why that is no longer wanted. The gate passes.

What the console has to show cannot be tried by you. Say in the report what a first run has to watch and by which figures in `play.jsonl`.
