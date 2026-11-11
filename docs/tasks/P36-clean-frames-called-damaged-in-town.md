# P36: Clean frames called damaged in town

## Why

On 11 November the pilot drove 2.5 km through town to its waypoint. On the way it stood still for most of two stretches, with a clear road and the purple route straight ahead on the minimap. The minimap reader called the frames damaged: 93 in a hundred between 80 s and 110 s after the first tick and 91 in a hundred between 150 s and 180 s, against 13 in a hundred between 20 s and 50 s, in session `/Users/kerim/recordings/pilot/20261111-130955`. The driver does not act on a reading called damaged, so it let the pedal go. To the eye the minimaps of those stretches are clean: a dense grid of streets and blocks at night, the route, the arrow, the distance below. Frames at 70 s, 100 s, 140 s and 165 s are called damaged, frames at 40 s and 78 s are not, and they look alike.

The driver now rides out two seconds of readings called damaged, which got the car to its waypoint, but that is patience with a wrong answer and no cure: a reading that really is damaged is trusted for two seconds as well.

The session folder has `video.mp4`, `frames.jsonl` with every frame's capture time, and `play.jsonl` with the reading of every tick and its time `t`; ticks and frames are matched by `frame_id`. Sessions `20261111-131346` and `20261111-131628` continue the same drive.

Read `PLAN.md`, in `docs/LOG.md` the entries of 11 November, and `pilot/src/pilot/minimap.py` with its tests and its lab folder, in particular how damage is told and on which recorded damage that was built.

## What to build

The minimap reader does not call a clean minimap damaged because the town's map is a grid of blocks, by day or by night. Find out first which of its signs of damage fires on these frames and on what in the picture; say in the report which, with the numbers of one frame called damaged and one of its neighbours called clean.

What it rightly calls damaged stays damaged: the recorded codec damage the reader was built on, a map half drawn during a transition, a picture frozen or torn. Where a sign cannot tell the town's grid from damage, it may ask for more before it speaks, but the reader's present answers on its recorded evidence must not get worse, and no frame of the recorded damage set may turn clean.

## Judging it

Replay every frame of the three sessions through the reader before and after and report, for each session, how many frames are called damaged. Label a sample of at least sixty frames from the stretches named above by eye, clean or damaged, with a contact sheet kept in the lab folder, and report the reader against the labels before and after. Run the reader's existing evaluation over its recorded sets and report the numbers before and after next to each other, the damage numbers above all.

Pin with tests: clean town frames from this evidence, kept as small crops the way the reader's other fixtures are, are not called damaged; the recorded damage stays damaged; the existing tests pass unchanged.

## Your files

`pilot/src/pilot/minimap.py`, its tests and fixtures, the reader's lab folder, and your report. Not `drive.py`, `motion.py`, `scene.py`, `conductor.py`, `cli.py` or any skill.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py` in `pilot/` is green, and the report names the sign that fired and why, shows the counts before and after on the three sessions, on the labels and on the old sets, and lists what in these sessions the reader still gets wrong.
