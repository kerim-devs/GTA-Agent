# P56: The view the pilot needs

## Why

The pilot was built on the far view from behind the figure: `enter_vehicle` measures reach by where a vehicle's lower edge stands in that picture, `objects.is_player` cuts the figure out where it stands in it, the guard of the walks looks at the world around it, `level_camera` levels it. A person who plays leaves the view wherever they like. On 12 November Kerim and his brother played in first person, and when the pilot took over, the opening `level_camera` ended `failed: time-limit` and the first plan went with it (`/Users/kerim/recordings/pilot/20261112-114441`, on foot facing a wall; `20261112-115658` begins on a quad in first person). From now on people and the pilot take turns on the console all day, so the pilot has to put the view right itself, every time it takes over.

The touchpad steps through four views, on foot in this order: far, first person, near, middle, far again; a vehicle keeps a setting of its own. `lab/camera/views/` holds eight pictures of two rounds on foot at Sandy Shores by day, the view in each name (`foot-1-far.jpg` to `foot-8-middle.jpg`), each taken after a press of the touchpad and a step forward that lets the camera settle behind the figure, and `detections.json` beside them with what the object detector reports in each, the figure included and marked `player`. In these the figure's box is 237 px high in the far view, 302 and 323 px in the middle one, 417 px and cut by the lower edge in the near one, and there is none in first person. In `foot-1-far.jpg` a quad hides the figure and the detector does not report it.

Read `PLAN.md`, in `docs/LOG.md` the entries on the camera, `pilot/src/pilot/level.py`, `pilot/src/pilot/objects.py`, `pilot/src/pilot/vehicle_entry.py` and `pilot/src/pilot/foot.py` for what they assume of the view, `pilot/src/pilot/cli.py` for the opening of a session, and `lab/camera-live/`.

## What to build

A reading of the view: first person, near, middle or far, or unknown, on foot, from what the conductor already has in a tick (the frame and the detections, the figure among them when asked for). It has to hold when the figure is partly hidden, when it runs or stands in a doorway, at night, and when another person stands where the figure usually is; and it must say unknown rather than guess, because a wrong reading presses the touchpad and makes things worse. Kerim's recordings (`/Users/kerim/recordings/kerim/`, sections in `/Users/kerim/recordings/derived/kerim/*/sections.json`) are hours of play in whatever views he used: take from them what the eight pictures cannot show, and say which views occur in them and how you know.

A skill that sets the far view: it reads the view over a moment, presses the touchpad when it is not the far one, lets the picture settle, reads again, and ends `done` when the far view stands and `failed` with what it saw when four presses did not get there or the view stays unknown. It never presses on a screen that is not the game. A press is short, as a person's is.

The opening of a session: the view is set before the camera is levelled, and neither of the two failing takes the first plan with it; say exactly what the conductor would need for the second if it is not yours to change.

In a vehicle the same question stands and the pictures for it do not exist yet. Say what a round of the four views in a car and on a motorcycle has to be recorded as for you to build on, as a command for the reviewer, and build the reading so that the vehicle's views can be added without taking it apart.

## Judging it

The reading on the eight pictures with their detections, and on a sample from Kerim's recordings that you label by eye and keep small, with every miss looked at. The skill in tests against a model of the game's view that steps as the touchpad does, loses a press now and then, and hides the figure for a while. Your sandbox cannot run the detector: build the reading as a function of the detections and the frame, test it on stored ones, and for what needs the detector on fresh frames write the one command and name it in the report under what could not be run. The try on the console is the reviewer's: say what it should look at first.

## Your files

A new `pilot/src/pilot/camera.py` with its tests, `pilot/src/pilot/cli.py` only for the opening, `pilot/src/pilot/skills.py` only to register the skill, `pilot/src/pilot/head.py` only if the skill's arguments need it, `lab/camera/` and your report. Not `level.py`, `objects.py`, `conductor.py`, `mission.py`, `goals.py`, `vehicle_entry.py`, `foot.py`, `drive.py` or `minimap.py`, which others are changing: what you need from one of them is described exactly and left. The console is in use by others while you work: the rules of `docs/tasks/README.md` about the daemon hold without exception, and nothing under `/Users/kerim/recordings/` is written, moved or deleted. Write nothing large: the disk has little room left.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green or fails only where your sandbox refuses sockets, Vision or CoreML, which you then name test by test, and the report shows the reading on the eight pictures and on the sample from the recordings, the skill against the model, what the opening does now, and what has to be recorded for the vehicle's views.
