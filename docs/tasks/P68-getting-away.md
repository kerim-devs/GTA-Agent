# P68: Getting away: with stars lit, drive off at once, with no map and no destination

## Why

On the evening of 12 November the pilot ran with one star lit for the first time while Kerim watched (session `/Users/kerim/recordings/pilot/20261112-221857`, log of that day, "Stars"). It sprinted on the first tick and sat in a vehicle after 8.4 s, which he found very good. Then the head's rules opened the pause map to set a waypoint "away", five times in 75 s, four of them failing, and the truck stood on a dirt track with two stars lit when the run ended.

Kerim's verdict, as the player: that makes no sense. With the police behind you nobody enters a destination. You drive, right, left, wherever there is room; in open country you can leave the road and cross the fields, sooner or later you are on a road again; you can drive up the hills; only never into water. He will teach the finer points of driving a piece at a time. And he set the frame for all of it: GTA V is the preparation for GTA VI, where by rumour the minimap no longer shows where the police are and getting away takes more (changing clothes among it). What carries over is the movement, the logic is taught anew per game. So this skill must not depend on the map screen at all, and what it takes from the minimap must be a part that can be left out.

Read `pilot/src/pilot/drive.py` (the driver, its recoveries and how it turns a steering wish into a `Command`), `avoid.py`, `skills.py` for `DriveRoute` and how a driver is handed to a skill, `mission.py` from the `wanted` rules down, `contract.py`, `sim.py` and `tools/` for the driving simulation, and `docs/tasks/README.md`, whose rules for a new skill hold.

## What to do, in this order

Write what each step gives into the report as soon as it is there.

How Kerim gets away. In his recordings (`/Users/kerim/recordings/kerim/`, labels under `derived/kerim/`) find the stretches in a vehicle with stars lit, from the first star to the last one gone or to the end of the recording. For each: how long until the stars were gone, how much of it he was on a road and how much across country (as far as the minimap shows it), how often and how hard he steers, whether he ever opens the map (expected: never), and what ends a failed escape (water, a wreck, an arrest, a death). This is the measure the skill is held against, and the report gives it as a table.

What the picture gives for steering, as small readings in a module of your own, none of them in an existing reader: from the minimap crop, where a road leaves the arrow ahead, to the left and to the right, where water lies within the map's range and on which side, and where police markers are if the game draws any; and from the detector's boxes, what `avoid.py` already makes of them. Each reading returns nothing where it is not sure, and each is measured on frames from the recordings with what the frame shows beside it. The readings from the minimap sit behind one switch, so that the skill can be run without them, as GTA VI may require.

The skill, `get_away`, as one class in a module of its own under the rules for a new skill. It never opens the map or any menu. It drives from the first tick: full throttle with what the avoider takes off, the heading away from the police where they can be seen and otherwise straight on, along a road while one leads roughly that way and across country when none does, around what the detector sees ahead, and away from water before it is reached. It reuses the driver's recoveries when the car is held. It ends done when no star has been lit for three seconds, and fails with a reason the head can act on: the vehicle no longer moves after its recoveries, the figure is out of the vehicle, water, or its time limit. With the minimap readings switched off it still drives, on the detector and the recoveries alone.

Try it in the simulation and on recorded frames before any console: the heading it would take on the stretches of Kerim's own escapes, beside what he steered, and what it does on the frames of the session named above from the moment the figure sits in the truck.

## Your files

A module for the readings and one for the skill under `pilot/src/pilot/` with their tests, fixtures under `lab/getaway/` (crops and small tables, under 2 MB), and `docs/reports/P68-getting-away.md`. Not `skills.py`, `head.py`, `head_prompt.txt`, `mission.py`, `conductor.py`, `guard.py`, `drive.py`, `avoid.py`, `contract.py` or any existing reader: the reviewer registers the skill and changes the head's `wanted` rules to use it. If the driver needs a change for this, the report says which.

The rules of `docs/tasks/README.md` hold: no git writes, never the daemon on port 9395, no `ps5rp`, no `PS5_HOST`, recordings are read and never written. Other workers measure on this Mac and somebody may be playing on the console: nothing that keeps the machine busy for minutes in one go, and not the full gate.

## Done when

The report has the table of Kerim's own escapes. Each reading is measured: on at least forty frames each, the road reading names a road that is there in nine of ten and none where there is none in nine of ten, and the water reading never misses water that lies ahead within the map's range. In the simulation the skill keeps moving for sixty seconds on open ground, on a road with traffic and towards water, never enters the water, and is never held for more than five seconds at a time. On the frames of the session named above it steers from its first tick and never asks for the map. `env -u PS5_HOST .venv/bin/python -m pytest` on your tests and ruff pass in `pilot/`, with tests for: no button other than the driving ones ever pressed, driving with the minimap readings off, away from water, done only after three seconds without a star, each failure with its reason, and the neutral pad at every end.

What stays open after this card is the console: Kerim watching it get away, and saying what a driver would do differently.
