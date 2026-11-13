# P100: The nearest car is taken

## Why

Kerim, leaving for the night of 13 November, on what the pilot has to learn first: drive fluently, and before that find itself the nearest car. The trip of P97 (`docs/reports/P97-one-trip-carried-to-its-end.md`) begins with `enter_vehicle`, and at the console that step is where a trip begun on foot spends its time or ends.

`/Users/kerim/recordings/pilot/20261113-225835`, begun on foot in a side street of Sandy Shores: three entries of 25 s, none got a car. The first found nothing; the second "nothing found; saw 1 vehicle (moving 1)"; the third "nothing found; road search unavailable: stuck; saw 2 vehicles (rejected 0, avoided 0, moving 0)", and the picture at its end shows a buggy on the road thirty metres off and the figure standing at a house wall. `/Users/kerim/recordings/pilot/20261113-230030`, from 440 s, at night in front of a hospital in town: "vehicle drove away or was lost; saw 14 vehicles (moving 1)" at 465 s, the same with 2 vehicles at 492 s, "vehicle out of reach; saw 13 vehicles (moving 0)" at 527 s and again with 11 at 554 s, and then the figure sat in a car at 558 s ("already in a vehicle", so the press that got it in came after the skill had given up). Thirteen vehicles seen, none of them moving, and none reached in 25 s is the fault this card is about. `/Users/kerim/recordings/pilot/20261113-234407` has the opposite, an entry in four seconds beside a car just left (627 s).

P16, P53 and P85 built and changed this skill (`docs/reports/P16-enter-vehicle.md`, `P53-into-a-car.md`, `P85-a-figure-in-a-car-stays-in-it.md`); the log entry of 12 November has Kerim's word on it: taking the next vehicle at once is very good.

## What to do

Find out on these recordings why each failed entry failed: `play.jsonl` has every tick with the observation's objects, the pad and the skill's own words, `video.mp4` the picture. Which vehicle was chosen, was it the nearest that could be reached, did the figure walk toward it and how far did it get, what stopped it (a wall, a kerb, the car leaving, the detector losing it, a choice that changed from tick to tick), when was triangle pressed and at what distance. Say for each of the six failures which of these it was, with the frame.

Then look at how Kerim does it: his recordings under `/Users/kerim/recordings/kerim` with `pad.jsonl`, and the action labels in `/Users/kerim/recordings/derived/kerim/index.jsonl` (`action` per frame) to find his entries. How long from the decision to the seat, how far he walks or runs (he holds the run button), whether he takes a parked car before a driven one, what he does when the first one drives off. State his median and the pilot's from the recordings above, measured the same way.

Change the skill so that a figure with vehicles in sight is seated in the nearest one it can reach, as fast as a player: it keeps to one chosen vehicle until that one is plainly lost, it runs, it goes round what is in the way instead of standing at it, it presses for the door when it is near enough for the game to take the press, and a vehicle it cannot reach after a few seconds is given up for the next nearest rather than for nothing. An entry that ends without a car says what it tried in a form the trip can act on. Parked before driven stays the order where both are near, as Kerim's log entry leaves open; do not turn that round.

## Your files

`pilot/src/pilot/vehicle_entry.py`, its tests in `pilot/tests/test_vehicle_entry.py` and new ones beside it, scripts and their output under `lab/enter/` with the prefix `p100`, and `docs/reports/P100-the-nearest-car-is-taken.md`. Not `errands.py`, `conductor.py`, `skills.py`, `drive.py` or `walk*.py`; if the entry needs something from them, say so in the report. You work in `/private/tmp/gta-nearest-car` (branch `feat/pilot-nearest-car`, from `a41e461`; the environment is installed, the detector's model and the minimap crops are in place) and nowhere else. The rules of `docs/tasks/README.md` hold: no commit, no console, no `PS5_HOST`, nothing sent to `127.0.0.1:9395`. The machine is shared: the pilot drives at the console all night and needs its thirty ticks a second, so run one process at a time at low priority (`nice -n 15`), decode video sparingly, and run the whole gate once at the end.

## Done when

The six failures are explained, each with its cause and its frame. Tests feed the skill the recorded observations of at least three of them (the hospital at 527 s and 554 s among them) and fail today; with your change the skill asks for what a player would have done on those ticks. The replay is open loop, the recorded figure does not answer the new stick: say what it shows and what it cannot.

The existing tests of the entry pass, or the report says for each changed one what it asserted and why that is no longer wanted. The gate passes.

What the console has to show cannot be tried by you: say what the first three entries on foot should be judged on, by which figures in `play.jsonl` and `head.jsonl`, and what Kerim's median is that they are held against.
