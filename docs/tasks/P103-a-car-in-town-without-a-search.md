# P103: A car in town without a search

## Why

The trip of P97 now arrives (`/Users/kerim/recordings/pilot/20261114-005357`, 5.5 km in 637 s), and most of the time it loses is lost before the drive: the figure on foot, looking for a car. Kerim's own figure for the last approach to a seat is 6.6 s at the median (P100, `lab/enter/p100-measurements.json`). The pilot's, in the night of 14 November with the routine of P100:

`/Users/kerim/recordings/pilot/20261114-011429`, the city, from the hospital: a seat at 57 s after one failed try, lost again at 71 s (the car's driver pulled the figure out; the trip now drives a car off at once, that part is done), and then six tries of 25 s each without a seat, at 99, 141, 168, 203, 238 s and on, with "vehicle out of reach; presses=2" and "vehicle drove away or was lost; presses=0". Between the tries `walk_road` took the figure off the street and down into the walled cutting of the tram line, where it stood before a tram at 290 s; there is no car to be had there and no way out that it found.

`/Users/kerim/recordings/pilot/20261114-010438`, the city, 282 to 322 s, at the car wash: "vehicle out of reach; tried=2,31,39,30,45; presses=2", then a fight with the driver of the car it went for, and the figure dead at 322 s.

`/Users/kerim/recordings/pilot/20261114-004115`, Sandy Shores, seventeen tries in eleven minutes: from 452 to 466 s the figure stands at a wreck beside the road that no door opens on, pressed twice; from 210 to 246 s it runs after cars that pass on a country road.

`/Users/kerim/recordings/pilot/20261114-002545`: eighteen tries, no seat.

And what works: `20261114-010438` at 150 to 166 s, a car taken from its driver at a junction in sixteen seconds; `20261114-011017` at 34 to 52 s.

Each `trip_attempt` row of `head.jsonl` has the try's whole reason (targets tried, presses, switches, vehicles seen); `lab/live/sheet.py <session> <out.jpg> <seconds>...` puts frames side by side; P100's report (`docs/reports/P100-the-nearest-car-is-taken.md`) says how detections are reconstructed from the video and what the routine does since.

## What to do

Go through every failed try of `011429` and of `010438` from 282 s, and the two stretches of `004115`, on the frames, and say for each what a player would have done at that spot and why the figure did not: which car was there to be had, how far, standing or driving, and where the time went. Then change what the evidence points at. What the night's watching suggests, for you to confirm or correct:

In town the cars are on the street, and they come to the figure: a driver brakes for somebody standing in his lane, and at a junction they stand in a row. The player's way is to the nearest street with traffic, to a car that stands or crawls, and Triangle; not after a car that is driving off, and not along the map's lines to somewhere else. `walk_road` as the answer to a failed try walks away from the cars that were just in the picture and follows whatever the minimap draws as a road, a tram line included. Decide what the figure does between two tries so that it stays where cars are, and how it tells a street from a track or an alley nobody drives through.

A vehicle that did not open on a press is not pressed again and is not the nearest car the next time: a wreck, a trailer, a car behind a fence. The figure leaves it within the three and a half seconds Kerim takes (P100) and the next try does not begin at it.

A try that has no car in reach after a few seconds should say so and end, so that the search between tries gets its turn; 25 s of walking toward boxes that come and go is most of the time lost.

The order of look, walk and road in the trip's car step (`Trip.decide` in `errands.py`, the block under `if self.step == "car" or self.seat_check`) is yours to change with the routine; the rest of the trip is not.

## Your files

`pilot/src/pilot/vehicle_entry.py`; `WalkRoad` and what it uses in `pilot/src/pilot/foot.py`; the car step of `Trip.decide` and `Trip.accept`'s handling of `enter_vehicle`, `look`, `walk`, `walk_road` in `pilot/src/pilot/errands.py`, and nothing else in that file, which is being changed in another worktree tonight (keep your hunks there small and apart); new tests in `pilot/tests/test_car_in_town.py`, existing tests only where a behaviour changes on purpose, each named in the report; scripts and their output under `lab/enter/` with the prefix `p103`, small files only, the disk has 11 GB left; `docs/reports/P103-a-car-in-town-without-a-search.md`. Not yours: `drive.py`, `avoid.py`, `skills.py`'s `DriveRoute`, which another worker changes tonight.

You work in `/private/tmp/gta-nearest-car` (branch `feat/pilot-car-in-town`, from `655dfa6`; the environment is installed, the detector's model and the minimap crops are in place) and nowhere else. The rules of `docs/tasks/README.md` hold: no commit, no console, no `PS5_HOST`, nothing sent to `127.0.0.1:9395`. The pilot drives at the console all night on this machine and needs its tick rate: one process at a time with `nice -n 15`, the detector over the seconds you need at two frames a second and not over whole recordings, the whole gate once at the end (`cd pilot && nice -n 15 .venv/bin/python tools/gate.py`; under this load it takes about 125 s and prints "default gate exceeded 90 seconds", which is known and not yours to fix).

## Done when

The report has the table of the failed tries, each with its frames, what was there, what a player does and what the figure did.

Tests that fail with the code as it is: a vehicle that does not open on a press is left within four seconds and is not the target of the next try; a try with no car in reach ends early and says so; after a failed try in a street with cars in the picture the figure stays at that street and does not walk off along the map; a line on the map that no car has been seen on is not followed as a road, or whatever rule you found in its place, stated; and the recorded readings of the cutting in `011429` do not lead the figure further into it. Where a test replays a recording it is open loop: say what it cannot show.

The tests of P100 and of the trip still pass, or the report says for each changed one what it asserted and why that is no longer wanted. The gate passes.

What the console has to show cannot be tried by you. Say in the report by which figures of `head.jsonl` the next town trips are to be judged: seconds from the trip's car step to the seat, tries per seat, presses per seat.
