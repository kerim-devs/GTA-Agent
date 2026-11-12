# P14: Seeing vehicles and people

## Why

On foot the pilot is blind to everything the minimap does not draw. It cannot walk to a car, cannot tell whether somebody stands in front of it, and the head, which sees a picture every ten seconds, cannot close a loop on anything. A local detector that names the vehicles and people in the frame several times a second is what stealing a car, aiming and avoiding people will be built on (P16 and P18 are written against its output at the same time as you write it).

## What to build

`pilot/src/pilot/objects.py` with a detector and a poller.

The detector takes a 1280x720 RGB frame and returns `Detection` objects from `contract.py`: kind (person, car, truck, bus, motorcycle, bicycle), box in frame pixels, confidence. It runs on this Mac without a GPU server; the Apple neural engine or GPU through whichever runtime you choose is fine. The licence of the model and of its weights must be permissive (Apache 2.0, MIT or BSD); say which it is. The weights are fetched once by `pilot/tools/fetch_models.py` with a pinned SHA-256 into `pilot/models/`; commit them if they are under 10 MB, otherwise keep them out of git and make the module fail with a message that names the fetch command when they are missing. You have network for this card: use it to fetch packages and weights and for nothing else. No frame, no path and nothing about this project leaves the machine.

The player is always in the picture: the character from behind on foot, the own car or motorbike when driving. The detector must not report the player's own figure or vehicle. Find out from the recordings where they sit and how stable that is, and filter them; report how often the filter removes something else.

The poller follows `gps.Reader`: one background thread, no queue, `poll(frame, t)` hands over the newest frame when the thread is free and returns the newest finished result as `(capture_time, detections)` or None, `close()` ends it. It must never delay the caller's 30 Hz loop. Memory has to stay flat: the two text readers of this project each leaked megabytes per call until the buffers were handed over inside an autorelease pool, so measure the process over at least 3000 detections and pin it with a test.

## Judging it

Label by eye at least 80 frames, drawn with a fixed seed from `/Users/kerim/recordings/pilot/20261110-230229`, `20261110-231512` (clean, on foot) and the long recording (driving, shootout, damaged frames): a box for every vehicle wider than 60 pixels and every person taller than 40 pixels, and the player marked separately. Save frames and labels under `lab/objects/` so the measurement can be repeated, and keep a few sheets with the boxes drawn. Report per kind what was found, missed and invented at an overlap of one half, and the time per frame as mean and 95th percentile, measured while a second process keeps one core busy.

## Your files

`pilot/src/pilot/objects.py`, `pilot/pyproject.toml` and `pilot/uv.lock` for the dependency, `pilot/models/`, `pilot/tools/fetch_models.py`, `pilot/tools/evaluate_objects.py`, `pilot/tests/test_objects.py` with its fixtures, `lab/objects/`, `.gitignore` for the weights, and your report. Nothing else; in particular not `contract.py`, `skills.py`, `conductor.py` or `cli.py`. If the contract needs another field, say so in the report.

## Done when

On the labelled frames at least 85 in 100 vehicles wider than 100 pixels and people taller than 80 pixels are found, at most one report in ten is invented, and the player is reported on fewer than 2 in 100 frames. A detection takes under 40 ms on average, so the poller delivers at least ten results a second next to the loop. Memory is flat and pinned. A test reads real frames from the fixtures and fails when the detector returns nothing or the player. The default gate passes. The report names the model, its licence, the numbers, the sheets, and what fails: small objects, night, damaged frames.
