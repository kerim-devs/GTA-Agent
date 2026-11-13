# P80: Round a stopped car from close behind, and round to a route that lies behind

## Why

Card P73 gave the driver a second style, `bold`: two seconds behind a stopped vehicle instead of thirty, then a recovery that backs up and goes forward with the other lock. Its own report (`docs/reports/P73-driving-like-a-player.md`) says where that stops short, and those are the two things a player sees first when he watches the pilot drive.

From close behind. The pilot brakes when a vehicle is near, so it comes to rest a metre or two behind what stands in its lane: a queue at a light, a car parked on the carriageway, a wreck. From there the measurement of P73 (`lab/drive/p73_measure.py`: an obstacle from x=-0.9 to 0.9 at y=8, the car starting at y=7) did not get past in fifteen seconds and touched the obstacle on 434 steps of the simulation. A player backs up a car's length, turns out and is past in three or four seconds, over the pavement or the other lane, whichever is free.

A route behind the car. After a waypoint is set the route often starts behind the car, and after a wrong turn it does too. The simulator's `behind` route takes the bold driver 6.8 to 15.1 seconds to face within thirty degrees of it, and it stands for more than four seconds on the way on most car profiles. A player makes a three-point turn in the road or swings round over the pavement in four or five.

Kerim on 13 November: it does not have to drive by the rules of the road, this is Grand Theft Auto; it may drive over the pavement, wherever. And it has to be clean: what is built here is the path that sends inputs to the console, it cannot be tried there before he watches, and the careful style he has seen arrive must keep behaving exactly as it does.

Read `PLAN.md`, `docs/tasks/README.md`, the reports P73, P55 and P54, then `pilot/src/pilot/drive.py` (the queue in `_queue`, the recovery in `_recover` and the two phases after it, `bypassing`), `avoid.py`, `Skill._around` and `DriveRoute` in `skills.py`, `BOLD` and `CAREFUL` in `cli.py`, `sim.py`, `pilot/tools/evaluate_player_driver.py` and `lab/drive/p73_measure.py`.

## What to do, in this order

See it first. For the parked car and for the route behind, on the nominal profile and on the two that did worst in P73's table (`range-02` and `fast-low-grip`): the car's path, heading, speed and the driver's state on every tick, drawn or tabulated, so that the report can say in a sentence each why the car does not get past and why the turn takes as long as it does. Do not change anything before that sentence is written; the fix follows from it.

Round the stopped car. With the queue's two seconds spent and the vehicle still close ahead: straight back far enough to turn out (find the distance in the simulator on every profile; a car's length is the first guess), then forward with the lock towards the side the avoider calls free, or, where it calls neither free, away from the middle of the road as the route's side of the minimap shows it and otherwise to the right, where the pavement is in this game's traffic. The lock is held until the vehicle's box has left the car's track, then the route has the wheel again. What stands behind the car is not seen, so the way back is short and ends at once when the car stops moving. If the first side does not get it past, the other is tried, and after both the existing limit on recoveries applies. All of this belongs to `bold` alone.

Round to the route. With the route's bearing more than 120 degrees off and the car slower than a walking pace: back with the lock that swings the nose towards the route, forward with the other lock, as often as it takes and at most three times, each phase ended by the heading reached or the car stopping against something. Faster than that the car is already turning and is left to. `bold` alone as well.

Hold both against the simulator on all eleven profiles with `evaluate_player_driver.py`, extended by the parked-car world at four starting distances (2, 4, 7 and 12 m behind the obstacle) and by the same world with a second obstacle beside the first, so that one side is taken. Give the table before and after.

Then the recorded drives, as P73 did (`lab/drive/p73_replay.py`): the changed driver over the same fourteen windows, with every tick counted on which the new code would have started a manoeuvre. A replay does not answer the driver's pad, so this cannot show a manoeuvre working; it shows how often it would begin on real pictures, and each beginning is looked at on its frame (a sheet of the frames in `lab/drive/`) and named in the report as a car that really stood ahead or not.

## Your files

`pilot/src/pilot/drive.py`, `avoid.py`, `Skill._around` and `DriveRoute` in `pilot/src/pilot/skills.py`, `BOLD` in `pilot/src/pilot/cli.py`, `sim.py`, `pilot/tools/evaluate_player_driver.py`, their tests, `lab/drive/` for scripts and tables (under 2 MB added) and `docs/reports/P80-round-a-stopped-car-and-round-to-the-route.md`. Not `getaway.py`, `terrain.py`, `conductor.py`, `loop.py`, `mission.py`, `errands.py` or `bench.py`. `CAREFUL` and every test that runs with it stay as they are: a test that needs the old behaviour selects `careful`, as P73's did.

Every tick returns the whole pad; nothing is held when the drive ends or is stopped from outside in the middle of a manoeuvre; a manoeuvre never starts on a damaged picture or with boxes older than the avoider's own limit; and reverse is never held for longer than the bound you measured.

## Done when

The report says in a sentence each why the car did not get past and why the turn was slow, with the picture or table behind it. In the simulator, on every profile: from 2, 4 and 7 m behind the parked car the bold driver is past it within six seconds of the two seconds' wait and touches it on no step; with one side taken it goes round the other; from 12 m it steers round without stopping, as it did. The route behind is faced within thirty degrees in under six seconds from standing on at least nine of the eleven profiles and in under eight on all, and the car stands outside a manoeuvre for no more than a second on the way. Arrival on the town, country and behind routes is no later than in P73's table on any profile. Every careful number is unchanged. Tests cover: each phase of both manoeuvres with its end, the side chosen with one side taken, both taken and neither, no start on a damaged picture or stale boxes, the bound on reverse, a stop from outside in each phase with a neutral pad, and the limit on recoveries. The gate passes in `pilot/`: run it once at the very end, and the tests of your own files while you work, because the machine is shared.

What stays open after this card is the console: a drive through town with Kerim watching, bold beside careful.
