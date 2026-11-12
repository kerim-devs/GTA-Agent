# P53: Into a car

## Why

Everything the pilot does with a vehicle starts with getting into one, and it cannot. On 12 November `enter_vehicle` ran nine times in seventeen minutes of free play in town and three times alone in the test of the basics (`lab/live/basics.sh`). In free play the figure came to sit three times and the skill ended `done` in none of the nine; alone it came to sit in none of the three. Kerim's word on it the same morning: getting in, walking, driving and choosing a place on the map have to work before anything else is worth doing.

`lab/enter/runs.json` holds what the object detector saw in every one of these tries, ten times a second, with what the map said and what the skill sent to the pad (`lab/enter/dump.py` made it; the sessions with their videos are under `/Users/kerim/recordings/pilot/`). Four things are in it.

The skill sees a vehicle and does not press. In `20261112-103305` from 36 s a vehicle is in the picture in all 252 samples and near by the skill's own measure (`REACH_HEIGHT`, `REACH_BOTTOM`) in 100 of them; it walked in 194, pressed in none and ended with `could not reach it`. It turns the camera until the vehicle stands within nine hundredths of the middle and walks, slowly, only then.

It presses and does not learn what came of it. The button went out five times in all. Three presses led into a seat: in `20261112-102851` at 158.4 s and 209.3 s and in `20261112-103305` at 110.1 s, where the head's event `vehicle_enter` followed after 4.8 s, 11.6 s and 2.6 s. Each time the head then replaced the skill with its next plan before the skill had its proof, so that the skill ended `failed: replaced` with the figure in the seat (six of the nine runs ended that way). Two presses led nowhere: in `20261112-102851` at 99.1 s, and in `20261112-111123` at 11.0 s at a car that was driving past. Whether the game missed the press, the vehicle was out of reach, or it drove on is not known.

It stands still. In `20261112-110449` a car stopped beside the figure, and for fifteen seconds the skill sent nothing: the minimap reader called its reading corrupt on a clean picture in 150 of 250 samples, and the skill does nothing on a corrupt reading. In `20261112-110806` no vehicle was in sight and the skill gave up after five seconds of its twenty-five, having turned on the spot.

Kerim got into a vehicle 71 times in the recordings that are classified (`/Users/kerim/recordings/derived/kerim/*/actions.jsonl`, action `enter_vehicle`, from the press to the vehicle's map; the videos and pad logs are under `/Users/kerim/recordings/kerim/`): 3.1 s from the press to the seat at the median, 5.3 s at the ninth decile.

Read `PLAN.md`, in `docs/LOG.md` the entries from "On foot" on, the reports of P16 and P45, `pilot/src/pilot/vehicle_entry.py` with its tests, `pilot/src/pilot/foot.py` (how `walk_road` finds and follows a road, and its evidence of motion), `pilot/src/pilot/objects.py` and `pilot/src/pilot/contract.py`.

## What to build

First show, from `lab/enter/runs.json` and the frames of the sessions, what happened at every press that led nowhere and in every stretch with a vehicle near and no press. And show how Kerim does it: for a sample of his 71 entries, how large and where in the picture the vehicle was when he pressed (your sandbox cannot run the detector, so read it off the frames, or name the command that measures it), whether it stood or drove, whether he ran to it, and how long he held the button.

Then a skill that gets in. What it has to do is yours to derive from that evidence; the least is this. It chooses a vehicle it can reach: one that stands before one that drives past, a near one before a far one, a car before a lorry or a bus. It goes there fast, steering the figure towards the vehicle while the camera follows, instead of waiting for the camera first. It presses as soon as the game would take the figure to the door, which is earlier than today, and when the press brought nothing it finds out why (too far, the vehicle gone, the door locked or blocked) and tries again or takes another vehicle. With no vehicle in sight it does not turn on the spot and give up: it looks around once and then walks to the road and along it, which is where vehicles are, until its time is up. A minimap reading that is called corrupt holds back the proof that the figure sits, not the walk to the vehicle. From its press until its proof the skill is not cut short by a new plan of the head (the runner knows `uninterruptible`, see `level.py`; say whether the whole skill or only that stretch should be, and what the conductor would need for the second). The skill is done when the figure sits, proven as today, and when it fails it says which of these it was.

The duration may rise above 25 s if the evidence asks for it; say so and why. The rules that call the skill and the minimap reader are not yours: the reader's false alarm is described exactly in the report, with the frames, and left.

## Judging it

Build the choice and the steering as functions of the detections and test them on the samples of `lab/enter/runs.json`: in every stretch named above the changed skill, fed the recorded detections in their order, heads for a vehicle and presses where the recorded one did not, and it does not head for a vehicle that drives through the picture when one stands. The recorded figure did not move as yours would, so this shows the choice and the timing of the first press, not the outcome; say that. Drive the skill in tests against a small model of the game as Kerim's entries show it (the figure reaches the door some seconds after a press within reach, a press out of reach does nothing, a vehicle drives away, a press now and then is lost) and show it get in, and show each of its failures with its reason. For what needs the detector on fresh frames, write the one command and name it in the report under what could not be run; it will be run outside the sandbox. The try on the console is the reviewer's: say what it should look at first.

## Your files

`pilot/src/pilot/vehicle_entry.py`, `pilot/tests/test_vehicle_entry.py`, `lab/enter/` and your report. `pilot/src/pilot/head.py` only for the skill's arguments. Not `mission.py`, `conductor.py`, `skills.py`, `foot.py`, `minimap.py`, `waypoint.py` or `legend.py`, which others are changing: what you need from one of them is described exactly and left, and what you need of `foot.py` you call, not copy. The console is in use by others while you work: the rules of `docs/tasks/README.md` about the daemon hold without exception, and nothing under `/Users/kerim/recordings/` is written, moved or deleted. Write nothing large: the disk has little room left.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green or fails only where your sandbox refuses sockets, Vision or CoreML, which you then name test by test, and the report shows what happened in each recorded try, how Kerim gets in, the runs of the changed skill over the recorded detections and against the model, and what the try on the console should look at first.
