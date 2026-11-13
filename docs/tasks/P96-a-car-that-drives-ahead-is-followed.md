# P96: A car that drives ahead is followed

## Why

Kerim does not accept the driving: the car weaves. `docs/LOG.md`, the entry "The steering against Kerim's hand" of 13 November, has what the route's steering does about it. This card is the other half. In the stretches of the drive of 18:32 (`/Users/kerim/recordings/pilot/20261113-183223`, read-only) where the far aim steered and the route's stick was steady, up to 0.45 was added to that stick on a tenth of the ticks, in eleven pushes of 0.3 to 1.6 s. That is `Avoider` in `pilot/src/pilot/avoid.py`, called from `_around` in `skills.py` after the driver. The car turns by 77 degrees a second per unit of the stick past a dead zone of 0.29, so 0.45 for 1.4 s is a swerve of 17 degrees toward the roadside, and then the route pulls the car back.

What it pushed for, from the video: between 150 and 164 s a lorry drove along the country road ahead of the jeep and then beside it, at about its speed. The stick was pushed to the right five times in a row, with the pedal down to 0.3 of what the driver asked, and the jeep ended on the dirt shoulder to the right of the lorry (frames at 160.4 and 163.1 s). At 23.6 s the push was 0.45 toward the guard rail for a cement lorry in the next lane. From 24.7 to 30.5 s it pushed for a "bus", a "truck" and a "person" straight ahead with a nearness of 0.4 to 0.8 while the road ahead was free for a hundred metres; whether those boxes are parts of the own jeep is for you to say.

The avoider was built for what stands in the road, and judges a thing by the size of its box at this instant. Kerim, the same evening, about his own driving: he fits what he does to the speed and to how fast something comes closer. A car that drives ahead at the own speed is not in the way. A person follows it, and goes round only what stands or crawls.

`pilot/tests/fixtures/p96_traffic.json` holds four stretches of that drive (20 to 32, 94 to 103, 148 to 165 and 214 to 218 s): under `boxes` the detector's boxes on every sixth frame of the recorded video, ten a second, since the detector's model does not compile in your sandbox; under `ticks` the stick and pedal the driver would have sent (replayed) and those that were sent, with the aim's distance and the speed where it was read. The avoider replayed on these boxes gives the stick added at the console (correlation 0.89, more than 0.1 added on 34 percent of the far-aim ticks against 35). The video is beside the recording's `frames.jsonl`; `pilot/src/pilot/replay.py` and `lab/drive/analyze.py` show how frames are read by time.

Read `PLAN.md`, `docs/tasks/README.md`, `avoid.py` with its tests, `_around` in `skills.py`, the player's own vehicle in `objects.py` (`is_player`, `split_player`), and the entries on the avoider and on waiting in a queue in `docs/LOG.md`.

## What to do

First say for each push in the fixture what the box was: a vehicle driving ahead in the own lane, one beside the car in the next lane, a part of the own car, or something standing in the way, with its nearness over the seconds before the push. Look at the frames.

Then the rule. A vehicle ahead in the car's own track whose nearness does not grow is followed: no push to the side, and the pedal lifted from a nearness you state so that the car keeps its distance. One that the car closes on steadily, because it stands or is much slower, is gone round as today. A vehicle beside the car is not pushed away from toward the roadside. Boxes that are parts of the own car are left out, and you say how you tell them. How fast a thing comes closer needs the boxes of the last second or so and a way to know that two boxes are the same thing; keep that as small as it can be, and say what it does when the detector loses a thing for a few frames or calls it a bus in one frame and a truck in the next, as it does in the fixture.

What stays: a thing standing in the road is gone round and braked for as today, the waiting behind a queue and the way round it after the wait (`waits_behind`, `passing_side`, the `bypass` argument) are not changed, and without boxes the driver's command passes through untouched.

## Your files

`pilot/src/pilot/avoid.py`, `_around` in `pilot/src/pilot/skills.py` and what it keeps for the avoider there, `pilot/src/pilot/objects.py` only for parts of the own car and only if the fixture shows them, their tests, the fixture, and `docs/reports/P96-a-car-that-drives-ahead-is-followed.md`. Not `drive.py` (a worker is changing the short aim there), not `errands.py`, `mission.py`, `conductor.py`, `vehicle_entry.py`.

## Done when

The report classes the pushes of the fixture. A test replays the fixture's boxes through the new avoider and shows no push to the side in the stretches the report classes as a vehicle driving along ahead or beside, the pedal lifted where the car follows close, and nothing added for parts of the own car. A test with made boxes shows a vehicle that grows in the picture gone round as before and one of a steady size followed; a test shows the steadiness against a lost frame and a changed label. The tests of the avoider that passed before still pass or are changed for a reason the report gives. The gate passes in `pilot/`: run the tests of your own files while you work and the whole gate once at the end, the machine is shared; if the sandbox fails the gate on local sockets or on the detector's model, name those tests and do not count them.

Whether the car then keeps its lane behind a lorry at the console cannot be tried by you. Say in the report what the first run has to watch.
