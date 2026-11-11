# P33: The hands take the judge's word

## Why

Whether the figure is on foot or in a vehicle is asked all over the pilot, and until today the answer came from one place: the shape of the minimap, flat on foot and tilted in a vehicle. The measurement of 11 November showed that this is wrong whenever stars are lit, and the first live rounds of the same day showed it is wrong without stars as well. On a car park under a motorway junction the reader called the map tilted for seven and a half seconds while the figure stood still on foot, the scene detector reported `vehicle_enter`, the head was asked again and the running plan was thrown away. `enter_vehicle` was stopped two seconds after it began, by the very reading it depends on. The sessions are `/Users/kerim/recordings/pilot/20261111-115541` (the map's class in `play.jsonl`, the event in `head.jsonl`) and `/Users/kerim/recordings/pilot/20261111-115803`. In both the judge, where it listened, said "foot" on every one of its judgments.

P29 gave the observation the judge's accepted word (`Observation.mode`) and one function that answers the question, `contract.player_mode(observation)`: the judge's word where there is one, else the minimap's class. So far only the conductor's carry and the rules head ask it. This card makes the hands ask it too, so that a session with a judge no longer trips over the map, and a session without one behaves exactly as before.

Read `PLAN.md`, in `docs/LOG.md` the entries of 11 November, `docs/tasks/P29-the-judge.md` with its report and review, and in the code `contract.py` (`player_mode`), `judge.py` (`ModeFilter`: what "accepted" means, and that the word lapses to `None` when the judge is silent), `conductor.py` (`tick`), `scene.py` (`EventDetector.update`).

## What to build

Every skill that asks how the figure moves asks `player_mode(observation)` instead of the map's class. The places are `skills.py` (walking to a blip and facing it), `level.py`, `vehicle_entry.py` (both the wait for the entry to be confirmed and the approach on foot), `punch.py` and `combat.py`. Look for others; `grep -n "minimap ==\|minimap !=" src/pilot/*.py` finds them. Where a skill needs the map itself and not the mode, it keeps reading the map: the blips' places come from the map whatever the judge says, a damaged reading is still a damaged reading, and the driver (`drive.py`, `loop.py`) reads the route off a tilted map and stays as it is. Say in the report for each place which of the two it is.

A mode of `"none"` means there is nothing to steer: a cutscene, a black screen, a figure that is dead. A skill treats it as it treats an unreadable tick today, which is to let everything go and neither count it as progress nor as failure, unless the skill has a better rule already.

The scene detector follows the judge as well. `EventDetector.update` takes the accepted mode as an optional argument. While the mode is `"foot"` or `"vehicle"` the detector's vehicle state is that word and not the map's class; the judge's word has passed its own filter already, so it is taken at once and not held for `map_seconds` again. The events keep their names, `vehicle_enter` and `vehicle_exit`, and their evidence says that the judge said so. While the mode is `"none"` the vehicle state is left alone. While there is no mode the detector works from the map as today. A change from the judge's word back to the map, when the judge falls silent, must not by itself produce an event: the state the judge left is the state the map starts from, and the map has to hold its own view for `map_seconds` before it overrules it.

The conductor passes the mode in. With that, a change between foot and vehicle would reach the head twice, once from the detector and once as the conductor's own `mode_changed`. So `mode_changed` is kept only for changes to or from `"none"`, which the detector does not report.

Nothing in the route state or the HUD state of the detector changes.

## Judging it

Replay shows whether it works. Run the two sessions named above through the conductor offline, each once without a judge and once with the judgments from its `judge.jsonl` fed back at their recorded times (20261111-115541 was recorded without a judge; for it, and for any stretch you need, `lab/judge/live.py` shows how the package's `Reader` is driven against a recording, and a fake that answers "foot" throughout is enough to show the detector's behaviour). Report how many `vehicle_enter` and `vehicle_exit` events each run produces. Without a judge the numbers must equal what is recorded; with one, the figure never entered a vehicle in either session and the count has to be zero.

Pin with tests: each changed skill with an observation whose map says the opposite of its mode, in both directions, follows the mode; each changed skill with no mode behaves as before (the existing tests are the proof and must pass unchanged, so do not edit an existing test to make it pass; if one has to change, say which and why in the report); `enter_vehicle` confirms the entry on the judge's "vehicle" while the map still reads flat, and does not confirm it on a tilted map while the judge says "foot"; the detector reports nothing while map and judge disagree and the judge has not changed; it reports `vehicle_enter` exactly once when the judge changes from foot to vehicle, whatever the map does around it; a judge that falls silent with the map in agreement produces no event, and with the map in disagreement produces the event only after `map_seconds`; the conductor emits `mode_changed` for foot to none and none to vehicle and not for foot to vehicle.

This card changes what the skills send to the console. Run the full gate, and write down for the reviewer the three places where a wrong mode would do the most harm at the console, with the test that guards each.

## Your files

`pilot/src/pilot/skills.py`, `level.py`, `vehicle_entry.py`, `punch.py`, `combat.py`, `scene.py`, `conductor.py`, their tests, and your report. Not `judge.py`, `contract.py`, `mission.py`, `drive.py`, `loop.py`, `profile.py` or `cli.py`.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green, and the report holds the list of places with what each now asks, the event counts of the replays, and the three places with their guards.
