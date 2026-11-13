# P91: On along the road where the map shows no route

## Why

On 13 November, 18:10, the pilot drove a jeep along a country road toward its waypoint (recording `/Users/kerim/recordings/pilot/20261113-181047`, read-only). At 172.6 s it entered the Braddock tunnel and `drive_route` failed with `route-lost-far`. The game draws no GPS route on the radar in that tunnel: the pictures `head-0015.jpg` and `head-0018.jpg` of the recording show the white roads, the arrow and no purple line, the second one right after the waypoint had been set again with 2109 m read from the map. From there to the session's end, four minutes, the car stood in the tunnel and the head went round: `set_waypoint` (done), `drive_route` (failed within a second, `route-lost-unknown`, the route never seen), `set_waypoint` again, then a cruise, then a shop, then the story again, each with the pause map opened once more. Kerim's complaints of the same day name exactly this: the map opened again and again, and the pilot hanging on one small thing.

A person drives on. The road is there on the radar, the waypoint stands, and the route is back at the tunnel's end.

`pilot/src/pilot/getaway.py` already drives without a route: `GetAway` reads the roads round the arrow with `terrain.read`, keeps to the road ahead (`choose`), steers through the `Driver` by a bearing (`_towards`), goes round traffic with the `Avoider` and frees a held car. It is built for stars, full throttle, and ends when the stars are gone.

Read `PLAN.md`, `docs/tasks/README.md`, `getaway.py` and its tests, the class `SkillRunner` and the registry in `pilot/src/pilot/skills.py`, the answers to a failed `drive_route` in `pilot/src/pilot/errands.py` (`STALLED`, `reset_waypoint`, the `travel` step), `goals.py` (`VEHICLE_ONLY`, `fits`) and the table of reasons in `bench.py`.

## What to do

A skill `drive_on`, in a vehicle, for a waypoint that stands and a map that shows no route: it follows the road ahead as `GetAway` does, built on it or beside it without changing what `get_away` does, at a pedal fit for a tunnel with traffic (about half; say what you chose and why), around other cars. It is done as soon as the map has shown a sound route, yellow or purple, for a second (`route-back`), and done with its own word at its time limit (30 s by default). It ends as failed on foot, on a lit star (the head has its rules for stars), on a held car, in water, and on a screen that is not the game, with the words `get_away` uses where they fit.

The head plans it where it now opens the map: when `drive_route` fails with a `route-lost` reason without having seen the route at all (`route_seen` false in the last skill), in a vehicle, right after a waypoint was set, the plan is `drive_on` and then `drive_route`, and the map stays shut. When `drive_on` ends at its time limit without a route, it may be planned once more; after the second in a row the map is opened again as today, and the count starts afresh when a route was driven on. A drive that had its route and lost it (`route_seen` true) keeps today's answer once, the waypoint set again, and if the route is still not shown after that, the same `drive_on`.

Replay the recording's own decisions: the head requests of 172.6 to 246.1 s are in `head.jsonl` with the pictures beside it. A test feeds the head the recorded sequence (the failed drive, the waypoint set, the drive failed without a route) and shows `drive_on` planned and no third `set_waypoint`; a test of the skill feeds it the tunnel's readings from `play.jsonl` (a tilted map, roads, no route) and shows it steering along the road ahead with the pedal down, and ending `route-back` when the readings of 21 to 170 s, which have the route, follow.

## Your files

A new `pilot/src/pilot/driveon.py` or `getaway.py` itself (without changing `get_away`'s behaviour, its tests stay as they are), the registry in `skills.py`, `goals.py` for the seat lists, the answers to a failed drive in `errands.py`, `bench.py` for the new reasons, `conductor.py` only if a list of skill names there needs the new one, their tests and fixtures, and `docs/reports/P91-on-along-the-road-where-the-map-shows-no-route.md`. Not `drive.py` (its steering is being changed beside you), not `vehicle_entry.py`, `judge.py`, `scene.py`, `minimap.py`.

## Done when

The two tests above pass, no test that passed before fails, and the report says which parts rest on the recording and which on your reading of the game. The gate passes in `pilot/`: run the tests of your own files while you work and the whole gate once at the end, the machine is shared; if the sandbox fails the gate on local sockets, name those tests and do not count them.
