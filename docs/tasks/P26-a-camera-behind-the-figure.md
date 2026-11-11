# P26: A camera that stays behind the figure

## Why

Kerim's rule for the stream, said on the morning of 11 November: on foot the view is from behind the figure, straight, as if one looked along with its own eyes, and it stays that way.

Nothing in the pilot holds it there. Every skill moves the camera only sideways: `look`, `face`, the fight, the punch and the approach to a vehicle set the x of the right stick and never the y, so the tilt stays where the game puts it. But after any of them the camera can sit at any angle to the figure. The game swings it back by itself only while the figure walks, and how fast has not been measured. A head that is asked in such a moment sees the figure from the side, and the "walk forward" it answers with goes into the picture and not where the figure faces.

The minimap already says what is needed. It turns with the camera, so up on it is where the camera looks, and `Reading.arrow` is where the figure faces on it. An arrow that points up means the camera is behind the figure. In the four minutes on foot of `/Users/kerim/recordings/pilot/20261110-231512` the arrow was read on 6,349 of 6,352 ticks, its median distance from up was one degree, and it was more than 30 degrees off on 17 percent of the ticks.

Measured on the console on 11 November (`/Users/kerim/recordings/calibrate/20261111-063233/calibration.json`, a run that a jammed controller ended after two checks): the camera does not move at a right stick of 0.2 and moves at 0.3, by about 130 image pixels a second; at 0.45 and more it moves faster than that check could follow; the picture answers an input after about 0.15 s. `face` asks for `min(0.65, angle * 0.01)`, which is under 0.3 for every angle below 30 degrees, so the small turns of the skills are probably lost in the dead zone today. That is for another card; here it means the keeper must never command less than the stick that moves.

Read `docs/tasks/README.md` first, and `docs/reports/P13-never-standing-still.md` for how a tick runs and what carry-on does between two answers of the head.

## What to build

A reflex without a model in a module of its own, `pilot/src/pilot/camera.py`: a `CameraKeeper` with one call per tick that takes the observation and the pad the skill or the carry-on wants to send, and returns the pad to send. The reviewer wires it in behind the skill. It adds an x to a right stick that is neutral and does nothing else: never a y, never a button, never a change to the left stick or the triggers, and never anything on a pad whose right stick the skill has set.

It turns the camera behind the figure when the map is the flat one of a figure on foot, the screen is the game where a HUD reading is given, the reading is not damaged and has an arrow, the skill has left the right stick and L2 alone on this tick and for a while before it (who aims or looks owns the camera), and the arrow has been off for longer than the game would have needed to bring it back by itself. Take the thresholds from the recordings, not from this card: how far off is off, how long to wait, how near to up is done.

Three things need a decision that the report explains. A walk the head chose (`walk` with an x and a y) holds a left stick relative to the picture, and a camera turned under it bends the path into a curve; `walk_to` recomputes its stick from the map every tick and does not mind. The loop has a delay of about 0.15 s and a camera that turns fast at a large stick, so a keeper that pushes until the arrow is up will swing past it. And the reader calls a clean picture damaged about once a second, for up to sixteen ticks, and holds a wrong map class for up to 0.83 s: a tick like that is stood out with what the skill wanted and decides nothing, as the README says.

The stick that moves the camera, 0.3 today, is a parameter with that default. The calibration will be repeated and its number will go in.

In a vehicle the keeper does nothing. Say in the report what the recordings show of the camera there (`recordings/20261110-093238` has several minutes of driving) and whether the same rule would hold.

## Judging it

On the recordings first. The play logs of the two clean sessions (`/Users/kerim/recordings/pilot/20261110-230229` and `20261110-231512`) hold, for every tick, the reading with its arrow and the pad that was sent. Measure from them what a right stick does to the arrow (sign and degrees per second at the sticks that were used), how long the camera stayed off after a `look`, how fast the game brought it back while the figure walked and whether it did while the figure stood. These numbers set the thresholds and go into the report with the stretches they come from.

A simulated camera for the tests, built from those numbers: a dead zone, a speed that grows with the stick, the delay, the game's own swing back while walking. On it the keeper brings an arrow from any angle to within the done threshold, in a time the report states, and does not swing past up by more than it allows itself.

A replay tool, `pilot/tools/camera_replay.py <session>`, that runs the keeper over the readings and pads of a recorded session and prints when it would have acted, for how long, and on how many ticks it stood back for a skill. A recording does not answer the pad, so this shows when the keeper speaks, not whether the camera obeys. Report the share of on-foot ticks more than 30 degrees off as recorded, and how many of those ticks the keeper would have been turning on.

No footage of a tilted camera exists and no check here needs one. Do not build a reader for the tilt.

## Your files

`pilot/src/pilot/camera.py`, `pilot/tests/test_camera.py`, `pilot/tools/camera_replay.py`, a new `lab/camera/`, `.gitignore`, and your report. Not `conductor.py`, `skills.py`, `contract.py`, `cli.py` or the head prompt; if the keeper needs something from them, say so in the report and the reviewer wires it.

## Done when

Tests pin: the keeper turns towards the side the arrow is off to, with the sign the recordings show; it never commands a stick under the one that moves, never a y, a button or a left stick; it leaves a pad alone whose right stick or L2 the skill has set, and for the time after that the report names; it does nothing in a vehicle, on a screen that is not the game, without an arrow and on a damaged tick; it does not act before its waiting time; your decision for the walk the head chose; on the simulated camera it arrives from 30, 90 and 180 degrees without swinging past its limit, with the delay in place. The default gate passes in under 90 seconds. The report says how the reviewer wires it in one call and what to look at on the console in the first live minute.
