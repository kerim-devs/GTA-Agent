# P90: A car from the traffic

## Why

On 13 November, 17:46, the pilot set its waypoint, 2.9 km away, and needed a car (recording `/Users/kerim/recordings/pilot/20261113-174601`, read-only). It walked along a residential street by night from 29 to 180 s, at the roadside by its own reading, and in the 35 pictures the head was asked about there was not one vehicle, only people on foot: `errands.py` plans `enter_vehicle` only when a car, truck or motorcycle is in the picture at the moment the head is asked, and 15 s of `walk_road` otherwise. Then it left the road and stood before a garden wall (mended since: a walk that ended stuck is turned away from before it is tried again). At 17:20 the same logic had a car after 40 s, on a street with parked cars.

Kerim, watching: why no car? The pilot only has to go to the road, stand there, and wait for a car that comes. That is how a person plays it, and it is not what the pilot can do: `EnterVehicle` passes over every vehicle that moves (`_may_take`), passes over every one with a driver seen unless told `occupied=allow`, which nobody plans, and steps back out of the lane when it finds itself in it (`_search`, `_retreat`). P57 and P60 made it so, for reasons that are in `docs/LOG.md` and still hold for the first choice: a parked, empty car is taken without a fight and without a star. What is missing is the second choice, for when there is no such car.

Kerim's order of the same day: a sound base, the pilot gets done what it has set out to do, and it does not hang on one thing.

Read `PLAN.md`, `docs/tasks/README.md`, the entries on P57, P60 and the entering of cars in `docs/LOG.md`, then `pilot/src/pilot/vehicle_entry.py`, the `travel` step in `pilot/src/pilot/errands.py`, `pilot/src/pilot/foot.py` for the road's reading (`lane`, `side`), and their tests.

## What to do

First look at how Kerim does it. His recordings lie under `/Users/kerim/recordings/kerim/` (read-only; `pilot/src/pilot/actions.py` labels what a hand did). Find the times he took a car out of the traffic: Triangle on foot, a car that moved or had a driver shortly before, the map tilted within a few seconds. Say in the report how many you found, where he stood (in the lane, at its edge), how long from the car's stop to the press, how long the press, how long until he sat, and how often a star followed. If there are fewer than five such takes, say so and go by what there is.

Then the skill. `enter_vehicle` gets a way to take a car from the traffic, as an argument of its own or as a second skill, whichever keeps the first choice untouched: the figure goes to the road and stands where a car coming along the lane has to stop for it or passes within reach, waits there, and when a car or motorcycle has stopped within reach it goes to the driver's door and takes it, with the press Kerim's takes show (a driver is pulled out while Triangle does its work; the proof of the seat stays what it is, P85's rules included). It does not walk into a car that does not slow, it does not take a bus, a truck, a police car or an ambulance where the detector tells them apart, and it does not shoot or strike to get a car. It ends with a clear word when no car came within its time, so that the head can walk on and try at the next crossing.

Then the head, in the `travel` step on foot and in the other places that look for a car: the parked, empty car in the picture stays the first choice. When none is in the picture and the figure has reached the road, the wait at the road is planned instead of another 15 s of walking; when the wait ends without a car, the figure walks on along the road, toward the waypoint where the map says which way that is, and waits again further on. A star after a taken car is not this card's: the rules for stars are there, and you check that they still fire.

## Your files

`pilot/src/pilot/vehicle_entry.py`, the `travel` step and the other car-seeking plans in `pilot/src/pilot/errands.py`, `pilot/src/pilot/goals.py` where a list of skills by seat needs the new one, their tests, a script under `lab/entry/` for what you measure, and `docs/reports/P90-a-car-from-the-traffic.md`. Not `drive.py`, `conductor.py`, `judge.py`, `scene.py`, `mission.py`'s rules of the place: they were changed today and are being driven at the console while you work. In `foot.py` only what the wait at the road needs, and say what.

## Done when

The report gives what Kerim's takes show. A test puts the figure at the roadside with no vehicle in the picture and shows the head planning the wait and not a walk; a test of the skill shows it standing through a car that passes without slowing, going to the door of one that has stopped within reach and pressing, and ending with its word when none came; a test shows that a parked, empty car in the picture is still taken first and that a bus or a truck from the traffic is not. No test of entering a car that passed before fails. The gate passes in `pilot/`: run the tests of your own files while you work and the whole gate once at the end, the machine is shared; if the sandbox fails the gate on local sockets, name those tests and do not count them.

Whether a driver in the game really stops for the figure and how the takeover looks in the picture cannot be tried by you, the console is not yours. Say plainly in the report which parts rest on Kerim's recordings and which on your reading of the game, so that the first run at the console knows what to watch.
