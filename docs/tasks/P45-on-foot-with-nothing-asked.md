# P45: On foot with nothing asked

## Why

On the morning of 12 November the pilot was started on foot in front of the hospital in town, with roads on the minimap and traffic on them, nothing asked of it: session `/Users/kerim/recordings/pilot/20261112-082524`, 180 seconds, with `play.jsonl`, `head.jsonl`, `judge.jsonl` and `video.mp4`. For the first minute the new `walk_road` (P44) did what it was built for: three runs of fifteen seconds took the figure off the plaza to the kerb, with a car driving past at 62 s. Then the rule `foot_target` saw a blue symbol on the minimap and planned `walk_to` blue, and from 63 s to the end the figure walked away from the road, back to the building, into a corner of its glass front, and stood there. Eleven `walk_to` in a row ended in `time-limit` or `blip-gone`, each answered by five seconds of `walk` and the next `walk_to`. Once, at 73.5 s, the rules planned what was wanted, `enter_vehicle`, `set_waypoint`, `drive_route`; the plan was replaced two tenths of a second later by the walk that follows a failed skill.

The same blue symbol led the pilot against a railing on the pier the evening before (`/Users/kerim/recordings/pilot/20261111-204712`; the report of P44 says what it is: a symbol the game pins to the rim of the map, there the question mark of a side mission, here most likely the player's own car). And in the corner nothing freed the figure: the guard of P44 either did not call it stuck or its turns did not lead out, and `play.jsonl` does not say which.

Read `PLAN.md`, in `docs/LOG.md` the entries of 11 November, `docs/reports/P44-on-foot-and-not-getting-anywhere.md` to its end, `pilot/src/pilot/mission.py` with its tests, `pilot/src/pilot/foot.py`, `pilot/src/pilot/skills.py` (`walk_to`, `walk`), `pilot/src/pilot/minimap.py` for how a blip and its place at the rim are read, and `pilot/tools/conductor_replay.py`.

## What to build

First find out from the session and show it: which symbol the reader calls blue from 63 s on and where on the map it sits, tick by tick whether it is marked as pinned to the rim; why `foot_target` wins over a car in sight; and what the guard did in the corner between 120 s and 180 s, by running `walk_to` with its guard over the session's readings and frames as `lab/foot/replay.py` does.

Then, in the rules: with no objective on screen and nothing the game asks for, a symbol at the rim of the map is no place to walk to. On foot with nothing asked, a vehicle in sight is taken (`enter_vehicle`, then the route as today), and without one the figure goes to the road and along it until one is in sight. A blip inside the map, and any blip while an objective stands on screen, is walked to as before. A plan made for a new situation must not be thrown away by the failure of the skill it replaces: find why the plan of 73.5 s was replaced and say whether the fault is in the rules or in the conductor; fix it in the rules if it is there, and describe it exactly if it is in `conductor.py`, which is not yours.

Then the corner. Whatever kept the guard from leading the figure out, repair it in `foot.py`: a figure that has turned away four times and still stands has to end with the failure the rules answer by turning round and heading for the road, within about fifteen seconds of standing still, never after a minute. Let `walk_to` and `walk` put the guard's state into their result's reason or into a field the conductor already logs, so that the next session shows what the guard saw.

## Judging it

Replay both sessions through the changed rules with the real readers, request by request as recorded, and show old plan against new: no `walk_to` to the rim symbol in either, and the plan with `enter_vehicle` at every request at which the detector had a vehicle. Replay the corner through the changed guard and show the second at which it now gives up. Run the rules over the 173 cases of `lab/mission/` and the cases of `lab/take-out/` and list every case whose decision changes, with the reason. Tests pin each of these decisions.

## Your files

`pilot/src/pilot/mission.py`, `pilot/src/pilot/foot.py`, `pilot/src/pilot/skills.py`, their tests, `lab/foot/` and your report. Not `conductor.py`, `minimap.py`, `judge.py`, `vehicle_entry.py`, `drive.py` or `cli.py`. The console is in use by others while you work: the rules of `docs/tasks/README.md` about the daemon hold without exception. Write nothing large: the disk has little room left.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green or fails only where your sandbox refuses sockets or CoreML, which you then name test by test, and the report shows the three findings, the replays, the changed cases and what the next try on the console should look at first.
