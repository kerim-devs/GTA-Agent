# P14b: A detector that finds what is there

## Why

P14 built the detector's frame: the module, the poller, the player filter, the fetch script, 80 labelled frames and the evaluation. Read `docs/reports/P14-objects.md` with its review first. Its model is too weak for the job. YOLOX Tiny on a frame shrunk to 416 pixels finds 37 in 100 vehicles wider than 100 pixels even when every vehicle kind counts as the same thing, 42 in 100 of the near ones between 200 and 400 pixels wide, and on only 22 of 63 frames the largest vehicle in the picture at all. Half of what it reports matches nothing. Getting into a car (P16) needs exactly the near vehicle, reliably.

Two things were left on the table. The model ran on two CPU threads, although this machine has a GPU and a neural engine and `onnxruntime` here offers the CoreML provider. And the 1280x720 frame was shrunk to a third before the model saw it, so a car 200 pixels wide arrived 65 pixels wide.

## What to build

Keep the interfaces of `objects.py` as they are (`Detector`, `Reader`, `Detection`, the player filter) and replace what is behind them.

Find the model and the input that meet the targets below. Candidates, all with permissive licences: the larger YOLOX exports from the same release (s, m, l) at 640; the frame cut into two overlapping square tiles at its native resolution instead of shrunk; a transformer detector with an Apache licence such as RT-DETR, D-FINE or RF-DETR if a ready ONNX export can be fetched; a torchvision detection model on the GPU if nothing lighter is good enough. Run on the GPU or the neural engine. Measure each candidate you try on the same frames with the same scoring and keep the table; choose the most accurate one that holds the speed target, not the fastest. You have network for packages and weights and for nothing else: no frame, no path and nothing about this project leaves the machine. Weights over 10 MB stay out of git behind the fetch script with a pinned hash, as now.

Score the way the detector is used. A vehicle is a vehicle: a pickup reported as a car is found, and the kind agreement is reported separately. An overlap of 0.4 counts. A report is invented when nothing labelled is under it and it is large enough that it would have been labelled.

The 80 labelled frames were looked at while the first detector was tuned. Label a second set of at least 60 frames that you do not look at until the model and its settings are chosen: drawn with a new fixed seed from the same three recordings, the same rules, with the boxes checked on the full-size frame and not on a contact sheet. Report both sets and say which one the choice was made on. Check the old labels where the two disagree in an obvious way; the first card corrected coordinate errors late.

The player filter removed a real car once in 80 frames and was tuned on those frames; measure it again on the second set.

## Your files

As in P14: `pilot/src/pilot/objects.py`, `pilot/pyproject.toml`, `pilot/uv.lock`, `pilot/models/`, `pilot/tools/fetch_models.py`, `pilot/tools/evaluate_objects.py`, `pilot/tests/test_objects.py` with fixtures, `lab/objects/`, `.gitignore`, and a report of your own, `docs/reports/P14b-objects-that-are-found.md`. Nothing else.

## Done when

On the second set: at least 9 in 10 vehicles wider than 200 pixels are found, at least 8 in 10 wider than 100 pixels, at least 8 in 10 people taller than 80 pixels, and at most 15 in 100 reports are invented. The player is reported on fewer than 2 in 100 frames. Through the poller the caller gets at least eight results a second while a 30 Hz loop runs next to it and a second process keeps one core busy, and a poll never takes longer than a millisecond. Memory is flat over 3000 detections and pinned by a test. The default gate passes in under 90 seconds. The report has the table of candidates, the numbers on both sets, sheets from the second set, and what still fails. If no candidate reaches the targets, say which came closest and what it would take, and leave the best one in place.
