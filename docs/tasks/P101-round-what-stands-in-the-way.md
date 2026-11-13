# P101: Round what stands in the way

## Why

Kerim has given the night of 13 to 14 November to one loop: the nearest car, a place, the drive, the arrival. With the bold driver of P98 and the turn of P99 merged, the third night trip drove 5.7 km through country and town and did not arrive: `/Users/kerim/recordings/pilot/20261114-000623` stood 52 m before the shop, in a town street at night, behind a white van parked in its lane, from about 705 s to the end at 878 s. `play.jsonl` has the driver's state in every tick (`result.driver_state`): `follow` with the pedal at 0.4 against the van for 25 s at a time, then the trip's own recovery (`get_away`, three seconds straight on), nine recoveries in all, `bypass-wait` on 3 % of the ticks, `bypass-reverse` on 1 %, and the drive given up as "recovery exhausted: no-progress". The next trip began in the same spot, `20261114-002126`: 170 s, the way to its place 1020 m at the start and 1010 m at the end, `follow` 60 %, `recovery-forward` 25 %, `recovery-reverse` 15 %, six recoveries, given up.

P80 (`docs/reports/P80-round-a-stopped-car-and-round-to-the-route.md`) built the way round a stopped vehicle for the bold style: two seconds behind it, straight back for at most 0.9 s, forward with the lock toward the side the avoider calls free. It needs the avoider to say that a vehicle stands ahead and which side is free (`avoid.py`, `waits_behind`, the detector's boxes), and its own report says the detector's judgement of what stands ahead is the weak part. P96 (`P96-a-car-that-drives-ahead-is-followed.md`) changed how a vehicle ahead is judged on 13 November. Read both first, and the P98 and P99 reports for what changed in the driver tonight.

## What to do

Find out on the two recordings, tick by tick from 700 s of the first and for the whole of the second, why the car did not go round the van: run the detector over the video's frames at those times (the tick log has no boxes), and see what the avoider said, whether `ahead` was true, whether a side was called free, what the driver's stuck logic and its recovery did and why backing off and going forward again ended in the same place. The picture shows a wide street with the oncoming lane empty to the left of the van. Say what a player does there, with Kerim's recordings as the measure (`/Users/kerim/recordings/kerim`, `pad.jsonl`): how long he stands behind something that does not move, how far he backs off, how he steers past.

Then make the bold driver get past a thing that stands in its lane: a stopped or parked vehicle seen by the detector, and also a thing the detector does not name, known only because the car does not move with the pedal down while the route runs straight ahead. For the second case the car has only its own stillness to go by: back off far enough to have room, then forward with a lock held to one side long enough to clear a vehicle's width, the other side on the next try, back onto the route after it. The tries must differ from one another and a try that moved the car past must end the standing; three tries that end in the same spot must not be the same try three times. Keep what P80 measured as good: no manoeuvre beside a lorry in the next lane, no reverse into what stands behind for longer than its bound.

The careful style stays as it is.

## Your files

`pilot/src/pilot/drive.py` (the stuck logic, `_recover`, the bypass phases of `_manoeuvre`; the turn of P99 and the speed law of P98 in the same file are finished work, change them only where your manoeuvre has to hand over to them and say so), `pilot/src/pilot/avoid.py`, `sim.py` where the simulator needs a parked vehicle the detector does not report, new tests in `pilot/tests/test_round_what_stands.py`, existing tests only where a behaviour changes on purpose and each named in the report, scripts and their output under `lab/drive/` with the prefix `p101`, and `docs/reports/P101-round-what-stands-in-the-way.md`. Not `errands.py`, `conductor.py`, `skills.py`, `vehicle_entry.py`. You work in `/private/tmp/gta-round` (branch `feat/pilot-round-what-stands`, from `286678f`; the environment is installed, the detector's model and the minimap crops are in place) and nowhere else. The rules of `docs/tasks/README.md` hold: no commit, no console, no `PS5_HOST`, nothing sent to `127.0.0.1:9395`. The pilot drives at the console all night on this machine and needs its tick rate: one process at a time at low priority (`nice -n 15`), run the detector over as few frames as answer the question, the whole gate once at the end.

## Done when

The report says for the two recordings what the detector saw, what the avoider said and why the car stayed, with frames. A test feeds the driver the recorded readings and detections of the van (from 705 s) and fails today: within ten seconds of standing the new driver asks for a backing off and then a forward lock held to one side, and on the next standing for the other side. The replay is open loop; say what it cannot show.

In the simulator, closed loop, on its car profiles: a vehicle parked in the lane that the detector reports is passed as P80 measured or faster; one that the detector does not report, on a road wide enough, is passed within twenty seconds of the first standing on every profile; with a wall on one side the other side is taken. Each of the last two fails with the driver as it is.

P80's, P96's, P98's and P99's tests pass, or the report says for each changed one what it asserted and why that is no longer wanted. The gate passes.

What the console has to show cannot be tried by you: say by which figures in `play.jsonl` a standing behind something and the way past it are to be judged on the first night trips.
