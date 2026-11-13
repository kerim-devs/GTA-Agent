# P93: The mission is not given up at its door

## Why

On 13 November, 18:32, the pilot drove 1.8 km to the mission it had set its waypoint on, "Fremde und Freaks" (recording `/Users/kerim/recordings/pilot/20261113-183223`, read-only; the head's requests and answers are in `head.jsonl`, the pictures beside it). At 232.9 s the map printed 208 m. At 256.5 s, with 46 m printed, the purple route was gone from the radar, as it is when the game takes a destination for reached, and `drive_route` ended as failed with `route-lost-unknown`: the skill's own record of the distance was empty (`end_distance` none in the last skill) although the reading carried `gps_distance` 46. The head kept the story for one answer, `set_waypoint` with `target=mission, instance=1`. Then the conductor handed it the event `route_vanished`, 0.2 s later, and the answer to that was a new goal: a cruise, whose waypoint failed on the map, then a shop, the Discount Store 5.6 km away, and the car drove off. The mission stood 46 m from the car.

Kerim's order of that day: the pilot gets done what it has set out to do. P86 kept the story's goal over a map that would not read; this is the same goal lost on arriving.

Read `PLAN.md`, `docs/tasks/README.md`, the entries of 13 November in `docs/LOG.md`, then the class `DriveRoute` in `pilot/src/pilot/skills.py` (`_distance`, `_route_end`, `arrival_metres`), the steps `travel`, `exit`, `approach` and `await_story` in `pilot/src/pilot/errands.py` with what ends a goal there (`end`, `interruption` in `goals.py`, the `guard` method), and how `mission.py` answers `route_vanished`.

## What to do

First say from the recording why each of the two things happened: why the drive had no distance of its own at its end although the map printed one every few ticks on the way (look at `reading.gps_distance` and `reading.gps_time` in `play.jsonl` from 225 to 257 s against what `_distance` asks of them), and which rule answered `route_vanished` at 256.7 s by ending the story.

Then mend both where they are. A drive whose route vanishes with a small distance last read, by the skill's record or by the reading itself, has arrived, and says so. And the head, on arriving at a story's waypoint or on a route that vanishes near it, goes on to the mission's marker as the steps after `travel` already describe: out of the car, to the marker on foot (`walk_to_point`, or `walk_to` a mission blip on the radar where one shows), and the wait for the mission to begin; it does not set the waypoint again from 46 m, and it does not choose another errand before those steps have been tried. If they fail, the goal ends as it does today after a letter that started no mission.

## Your files

`pilot/src/pilot/skills.py` (the class `DriveRoute` only), `pilot/src/pilot/errands.py`, `pilot/src/pilot/goals.py`, `pilot/src/pilot/mission.py` (the answers to `route_vanished` and to a drive's end for a goal; not the rules of the place and not the rule for `vehicle_exit`), their tests and fixtures, and `docs/reports/P93-the-mission-is-not-given-up-at-its-door.md`. Not `drive.py`, `driveon.py`, `vehicle_entry.py`, `conductor.py`, `judge.py`, `scene.py`: they were changed today and are being driven at the console while you work.

## Done when

A test replays the readings of 225 to 257 s through `DriveRoute` and shows it done as arrived; a test feeds the head the recorded requests of 232.9 to 257.0 s and shows the goal still `story` after them, a plan that leaves the car and walks to the marker, no `set_waypoint` and no cruise or shop; a test shows that a route lost far from the waypoint is still answered as today. No test that passed before fails. The gate passes in `pilot/`: run the tests of your own files while you work and the whole gate once at the end, the machine is shared; if the sandbox fails the gate on local sockets or on the detector's model, name those tests and do not count them.

What the game does at that marker, whether a cutscene starts when the figure walks in, cannot be tried by you. Say in the report what the first run at the console has to watch.
