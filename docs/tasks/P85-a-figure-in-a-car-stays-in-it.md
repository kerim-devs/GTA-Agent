# P85: A figure in a car stays in it, and a lost picture is waited out

## Why

On 13 November, 16:35:38, in the middle of a drive, the stream from the console broke: the bridge could not decode 628 frames, had no video, and stood with a new session 19 s later (recording `/Users/kerim/recordings/pilot/20261113-163218`, read-only, from about 200 s of `play.jsonl`; the head's pictures `head-0022.jpg` to `head-0032.jpg` show it). The console put its notice of the new connection on the screen. Then the pilot did this: the judge called three frames in a row "foot" with the figure sitting in the car (`judge.jsonl` at 222.2, 223.1 to 223.6 s), the event `vehicle_exit` went to the head (evidence "judge mode; occupancy hypothesis"), the head planned `enter_vehicle`, and its Triangle got the figure out of the car. It got in again, and the same happened a second time two seconds later. The map read `tilted` and showed the route throughout. Kerim, watching: why did it get out and in again.

Kerim's order of the same afternoon: a sound base, running smoothly. A figure that leaves its car because of three pictures is not that.

Read `PLAN.md`, `docs/tasks/README.md`, then `pilot/src/pilot/scene.py` (where `vehicle_enter` and `vehicle_exit` are made), the mode filter the conductor uses for the judge's word, `pilot/src/pilot/vehicle_entry.py`, `pilot/src/pilot/conductor.py` where frames arrive and where a hand on the controller or a silent bridge is handled (`pad_refused`, `pad_returned`), and their tests.

## What to do

Three things, each with its test.

Leaving a car is believed on evidence, not on the judge alone. The figure has left its car when the judge says so and the map agrees (flat, no route drawn for a vehicle), or when the pilot itself pressed Triangle to leave, or when the judge has said so for long enough that three bad pictures cannot make it: you find that time on the recordings, from how long the judge and the map disagree at real exits in the pilot's and Kerim's recordings of 12 and 13 November, and say in the report how many real exits were then reported late and by how much. While the map says vehicle and the judge says foot, the seat is unknown, not left.

`enter_vehicle` never presses Triangle for a figure that sits in a vehicle. Before the press it needs what shows a figure on foot beside a car: the figure detected standing, the judge's word, the map; with the map tilted and a route on it and no figure seen on foot, it ends `done` with a reason that says the figure sits already, and the head drives on. Find in the recordings what distinguishes the two cases and use that.

A lost picture is waited out. Frames that do not arrive, or arrive undecodable, are no news: for as long as the picture is gone and for a short settling time after it is back (measure it on this recording: how long until judge, map and HUD agree again), the conductor sends the neutral pad, makes no events out of what it reads, and tells the head once that the picture was gone and is back. The console's notices in the upper right corner (a connection, a trophy, a friend online) are system overlays: they do not change what the figure is doing.

## Your files

`pilot/src/pilot/scene.py`, `pilot/src/pilot/vehicle_entry.py`, `pilot/src/pilot/conductor.py` only for the lost picture and the mode filter's use, the module of the mode filter, their tests, and `docs/reports/P85-a-figure-in-a-car-stays-in-it.md`. Not `drive.py`, `mission.py`, `goals.py`, `waypoint.py`, `cli.py`, `level.py`, `camera.py`: two workers are in those beside you. If the head's rule for `vehicle_exit` in `mission.py` needs to change, say what in the report.

## Done when

A test replays the judge's answers and the map readings of 220 to 230 s of the recording and shows no `vehicle_exit`; a test shows a real exit (the pilot pressed Triangle, the map turns flat) reported within the time you measured; a test shows `enter_vehicle` ending without a press for a seated figure and pressing for a figure on foot beside a car; a test shows the neutral pad and no events through a gap in the frames and the settling time after it. The report says how many real exits in the recordings are reported later than before. The gate passes in `pilot/`: run the tests of your own files while you work and the whole gate once at the end, the machine is shared.
