# P109: The brake for what stands is held

## Why

P106 made the avoider brake fully for what stands in the car's lane, and in the eight trips after it the car did not once drive into the back of a queue. P107 (`af48de4`, merged as `5127722`) took brakes without a reason away, scaled the brake behind a slower car and lets it end sooner. In the eighth trip with P107 the car drove into a car standing at a red light.

Recording `/Users/kerim/recordings/pilot/20261114-073626` (read-only), by night, wet road. At 94.0 s a dark car stands at the stop line in the car's lane, about 40 m ahead, the car at a read speed of 21 m/s. The avoider asked for the full brake from 94.52 to 94.85 s (`result.around_pedal` -1, L2 1.0). From 95.19 s the pedal was back, at 0.73, and `around_pedal` fell from 0.98 to 0.52 by 95.65 s, a pedal eased and no brake. From 95.69 s the full brake again, and the car struck the standing car at about 96.2 s at well above 10 m/s (the speed read was 25.8, it lags). It got a star for it, spun round in the wet with the full pedal on the way round, ended against a lamp post, and was shot at 299 s.

I have not found out why the brake was let go after a third of a second: the detector may have lost a dark car by night, or the avoider may have taken the standing car for one that drives ahead slower and scaled the brake as P107 does behind a lead. That is the first thing to find out.

## What to do

Run the detector (`objects.Detector`) over the frames from 93.0 to 96.5 s of that recording, as `lab/avoid/p107_measure.py` does, and replay the boxes through the avoider as it is and as it was before P107 (`af48de4^`, the files `avoid.py` and `skills.py` of P106), with the speed as read. Say for each tick from 94.3 to 96.2 s what the avoider saw (box, lane, time to contact, the closing speed it reckoned) and why it braked, eased or did nothing, in both versions.

If P106 alone would have held the brake to the standing car, find the least change that gives that back without giving back P107: a thing in the lane once braked for fully is braked for until it has left the lane or the car stands, a lost detection of a few ticks does not release it, and a standing thing is not taken for a slower lead on the evidence of a few ticks. If P106 would have let go as well (the detector lost the car), the hold over lost ticks is the change, and say what it costs in brakes without a reason over P107's table (`lab/avoid/p107*`, the 170 onsets): the avoider's L2 share by replay must not rise by more than half a point of the following time.

## Your files

`pilot/src/pilot/avoid.py`; in `pilot/src/pilot/skills.py` only `DriveRoute._around` and the `AROUND_*` constants; a new test file `pilot/tests/test_brake_held.py` with the recorded boxes as a small JSON fixture under `pilot/tests/fixtures/`; `pilot/tests/test_brake_with_a_reason.py`, `test_brake_for_the_lane.py` and `test_avoid.py` only where a behaviour changes on purpose, each change named in the report; scripts and output under `lab/avoid/` with the prefix `p109`, small files only (contact sheets as JPEG under 300 kB each, not to be committed); `docs/reports/P109-the-brake-for-what-stands-is-held.md`. Not yours: `drive.py` (another worker is changing it now), `errands.py`, `minimap.py`, `gps.py`, `loop.py`, `objects.py` and the model.

You work in `/private/tmp/gta-drive-through` (branch `feat/pilot-brake-held`, from the head of `feat/pilot-trip`; the environment is installed) and nowhere else. The rules of `docs/tasks/README.md` hold: no commit, no console, no `PS5_HOST`, nothing sent to `127.0.0.1:9395`. The pilot drives at the console on this machine and uses the same detector on the same accelerator, and another worker runs tests: one process at a time with `nice -n 15`, the detector over no more than 1500 frames in all with a pause of a few seconds between batches, the whole gate once at the end (`cd pilot && nice -n 15 .venv/bin/python tools/gate.py`; under this load it takes about 140 s and prints "default gate exceeded 90 seconds", and `test_a_server_that_is_silent_twice_is_left_alone_for_a_minute` fails now and then under load and passes alone, both known and not yours to fix).

## Done when

The report says, tick by tick, why the brake was let go at 94.85 s, in the avoider of P106 and in today's.

A test that fails with the code as it is: over the recorded boxes of `073626` from 93.0 to 96.5 s with the speed as read, the brake once begun at 94.5 s is not released before the car would stand or the thing has left the lane. The tests of P106 and P107 pass (the two approaches of P106 braked for to the tick, no brake for the oncoming car on the bend, the brake behind a slower lead ended above a crawl), or the report says for each changed one what it asserted and why that is no longer wanted. By replay over P107's eight trips the avoider's L2 share is stated before and after. The gate passes.

What the replay cannot show, said plainly: it is open loop. The next town trips are judged by: cars driven into from behind above 5 m/s, the avoider's L2 as a share of the following time and its onsets a minute.
