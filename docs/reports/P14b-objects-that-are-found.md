The stronger detector is in place, but P14b does not meet all accuracy targets. YOLOX-L640 at confidence 0.4 is the best eligible measured configuration under the stated selection rule. The independent holdout passes vehicle recall above 100 pixels, player leakage and poller speed; it fails vehicle recall above 200 pixels, person recall and the invention limit. It must not be treated as reliable car-entry or person-detection evidence for dependent skills.

`Detector`, `Reader`, `Detection` and the player-filter interface remain intact. The default backend now uses the pinned official Apache-2.0 YOLOX-L export, full-frame BGR letterboxing at 640, class-agnostic NMS at 0.45 and CoreML MLProgram. Reader reuses an owned frame buffer while preserving busy-frame dropping. Missing/corrupt weights still name the fetch command; there is no runtime download. The model is ignored by git and fetched by `pilot/tools/fetch_models.py`, with SHA-256 `7860ae79de6c89a3c1eb72ae9a2756c0ccfbe04b7791bb5880afabd97855a411`.

The comparison used the original 80 frames for every configuration, the same scorer and a separate busy CPU process. The selection score is the arithmetic mean of the three requested recalls and one minus the invention fraction, restricted to at least 8 poller results/s, polls below 1 ms and player leakage below 2%. This balances the requested behaviours and deliberately does not choose the fastest model. The selected score is 0.61035, versus 0.60783 for M640 at 0.25. All 36 measured configurations and their per-frame predictions are retained in [the candidate receipts](../../lab/objects/candidates.json).

The initial 32-configuration choice was recorded in [selection.json](../../lab/objects/selection.json) before drawing or viewing the new holdout. The named torchvision fallback was measured later on the development set only; all four thresholds delivered 3.6 results/s and were ineligible, so it did not change the choice. An accounting correction changed the invention denominator from matched labels plus inventions to all size-eligible reports. Every saved candidate prediction was recounted, the ranking and selected settings remained unchanged, and both denominator variants remain in the receipts. No model setting or player-filter rule was adjusted after holdout inspection.

Vehicles are matched across car, truck, bus, motorcycle and bicycle kinds at IoU 0.4; people match people. Recall uses non-player truth boxes strictly wider than 200/100 pixels or taller than 80 pixels. An invention is a filtered prediction wider than 60 pixels for vehicles or taller than 40 pixels for people, with no labelled object underneath at IoU 0.4. The denominator is all such size-eligible filtered reports, including a leaked player. Subthreshold reports and duplicate reports over a labelled object are not inventions. Kind agreement is reported independently of recall.

The table below uses the corrected original labels. Native tiles are two overlapping 720-square crops at x=0 and x=560, padded without resizing to 736. Full-frame models use 416 or 640. ONNX intermediate shapes were cleared and inferred again for native exports; merely editing input dimensions caused a CoreML reshape failure and was rejected. FasterRCNN uses torchvision's default 800/minimum and 1333/maximum transform on the MPS GPU. Its individual unsupported operators may fall back to CPU. D-FINE Nano and DEIM D-FINE-S public weight URLs returned HTTP 401 without credentials; they were not measured and no result is claimed for them.

| Candidate | Vehicle >200 | Vehicle >100 | Person >80 | Invented reports | Player frames | Mean ms | Poller Hz |
|---|---:|---:|---:|---:|---:|---:|---:|
| fasterrcnn-native-c0.15 | 88.57% | 78.49% | 27.27% | 59.15% | 1.25% | 255.80 | 3.6 |
| fasterrcnn-native-c0.25 | 88.57% | 76.34% | 27.27% | 56.46% | 0.00% | 255.55 | 3.6 |
| fasterrcnn-native-c0.4 | 80.00% | 73.12% | 27.27% | 50.90% | 0.00% | 261.69 | 3.6 |
| fasterrcnn-native-c0.55 | 71.43% | 69.89% | 27.27% | 47.89% | 0.00% | 268.48 | 3.6 |
| l-640-c0.15 | 82.86% | 73.12% | 27.27% | 46.51% | 0.00% | 42.69 | 14.8 |
| l-640-c0.25 | 82.86% | 73.12% | 27.27% | 41.29% | 0.00% | 43.24 | 14.8 |
| l-640-c0.4 | 82.86% | 70.97% | 27.27% | 36.96% | 0.00% | 43.53 | 14.8 |
| l-640-c0.55 | 77.14% | 68.82% | 27.27% | 33.06% | 0.00% | 43.73 | 14.8 |
| l-native-tiles-c0.15 | 85.71% | 76.34% | 18.18% | 51.52% | 0.00% | 109.25 | 7.4 |
| l-native-tiles-c0.25 | 85.71% | 76.34% | 18.18% | 49.46% | 0.00% | 109.84 | 7.4 |
| l-native-tiles-c0.4 | 82.86% | 75.27% | 18.18% | 44.97% | 0.00% | 110.14 | 7.4 |
| l-native-tiles-c0.55 | 82.86% | 75.27% | 18.18% | 40.76% | 0.00% | 110.60 | 7.4 |
| m-640-c0.15 | 82.86% | 73.12% | 27.27% | 44.24% | 0.00% | 22.27 | 15.0 |
| m-640-c0.25 | 82.86% | 72.04% | 27.27% | 39.04% | 0.00% | 22.48 | 15.0 |
| m-640-c0.4 | 77.14% | 68.82% | 27.27% | 34.65% | 0.00% | 22.51 | 15.0 |
| m-640-c0.55 | 77.14% | 65.59% | 27.27% | 30.00% | 0.00% | 22.79 | 15.0 |
| m-native-tiles-c0.15 | 85.71% | 78.49% | 18.18% | 49.75% | 0.00% | 58.06 | 14.8 |
| m-native-tiles-c0.25 | 85.71% | 78.49% | 18.18% | 45.86% | 0.00% | 58.90 | 14.8 |
| m-native-tiles-c0.4 | 82.86% | 76.34% | 18.18% | 41.25% | 0.00% | 59.38 | 14.8 |
| m-native-tiles-c0.55 | 80.00% | 75.27% | 18.18% | 38.03% | 0.00% | 59.85 | 14.8 |
| rtdetr-640-c0.15 | 85.71% | 78.49% | 36.36% | 74.14% | 0.00% | 23.68 | 15.0 |
| rtdetr-640-c0.25 | 82.86% | 75.27% | 27.27% | 62.12% | 0.00% | 23.29 | 15.0 |
| rtdetr-640-c0.4 | 71.43% | 67.74% | 27.27% | 49.16% | 0.00% | 23.48 | 15.0 |
| rtdetr-640-c0.55 | 71.43% | 67.74% | 27.27% | 40.82% | 0.00% | 23.68 | 15.0 |
| s-640-c0.15 | 71.43% | 65.59% | 18.18% | 49.38% | 0.00% | 11.31 | 15.0 |
| s-640-c0.25 | 65.71% | 62.37% | 18.18% | 40.77% | 0.00% | 11.47 | 15.0 |
| s-640-c0.4 | 60.00% | 60.22% | 18.18% | 33.64% | 0.00% | 11.34 | 15.0 |
| s-640-c0.55 | 48.57% | 52.69% | 18.18% | 28.24% | 0.00% | 11.34 | 15.0 |
| s-native-tiles-c0.15 | 80.00% | 75.27% | 18.18% | 45.60% | 1.25% | 26.09 | 15.0 |
| s-native-tiles-c0.25 | 77.14% | 73.12% | 18.18% | 40.62% | 0.00% | 26.13 | 15.0 |
| s-native-tiles-c0.4 | 71.43% | 68.82% | 18.18% | 37.06% | 0.00% | 26.08 | 15.0 |
| s-native-tiles-c0.55 | 57.14% | 62.37% | 18.18% | 35.54% | 0.00% | 26.12 | 15.0 |
| tiny-416-c0.15 | 54.29% | 53.76% | 18.18% | 50.68% | 0.00% | 9.55 | 15.0 |
| tiny-416-c0.25 | 40.00% | 45.16% | 18.18% | 42.42% | 0.00% | 8.74 | 15.0 |
| tiny-416-c0.4 | 37.14% | 36.56% | 18.18% | 33.85% | 0.00% | 9.76 | 15.0 |
| tiny-416-c0.55 | 22.86% | 22.58% | 18.18% | 32.50% | 0.00% | 9.70 | 15.0 |

A full-resolution audit added one clearly omitted black sedan to original frame 043 at `[310,350,443,401]`. It did not move labels to match shifted predictions. Ten of eleven original large NPC boxes were confirmed; the eleventh, in damaged original frame 048, remained uncertain and was retained. [label-review.json](../../lab/objects/label-review.json) records the correction and before/after hashes. All candidates were rescored on that same corrected manifest.

The independent holdout has 60 frames, seed 141411 and source counts 18/18/24 from the two cable recordings and the Wi-Fi recording in the original order. All original source/frame pairs were excluded; source/frame pairs and JPEG hashes are disjoint. Each raw 1280x720 frame was checked individually without predictions or contact sheets. All 60 review flags and image hashes passed verification. Nine damaged frames, including fully black frame 037, remain in the evaluation. Prone bodies, partial objects and clearly visible borderline small objects were retained rather than discarded. No new recording, live daemon, console command or external frame upload was used.

| Measure | Target | Original 80 | Independent 60 |
|---|---:|---:|---:|
| vehicles_over_200 | >=90% | 29/35 (82.86%) | 24/27 (88.89%) |
| vehicles_over_100 | >=80% | 66/93 (70.97%) | 61/72 (84.72%) |
| people_over_80 | >=80% | 3/11 (27.27%) | 1/8 (12.50%) |
| Invented reports | <=15% | 51/138 (36.96%) | 23/103 (22.33%) |
| Player reported | <2% of frames | 0/80 (0.00%) | 1/60 (1.67%) |
| Poller results/s | >=8 | 15.000 | 14.667 |
| Maximum poll | <1 ms | 0.127 ms | 0.169 ms |

Kind agreement among size-eligible matched truth boxes is 79/90 on the original set and 60/76 on the holdout. The player filter removes no matched non-player object in the original set, but removes four in the holdout: a real truck in 006 and real people in 040, 041 and 042. Frame 041 also leaks the player. This is a measured limitation of the unchanged camera-relative filter, not evidence that the player has been identified semantically.

[The original-set receipt](../../lab/objects/p14b/metrics.json) and [the holdout receipt](../../lab/objects/holdout/metrics.json) bind labels, weights and evaluated code hashes, preserve predictions and enumerate every miss and invention. [All fifteen holdout sheets](../../lab/objects/holdout/sheets) include all 60 frames at full source resolution, with green truth, pink player and yellow predictions. Useful failure sheets are [004–007](../../lab/objects/holdout/sheets/labelled-004.jpg), including the filtered truck, and [040–043](../../lab/objects/holdout/sheets/labelled-040.jpg), including filtered NPCs and the player leak. The holdout was labelled from the raw frames before these sheets existed.

The hardware evidence goes beyond an available-provider list. [The execution profile](../../lab/objects/p14b/acceleration.json) contains three CoreML kernel events and no CPU kernel events, with CoreML first in the provider order. [The CoreML compute plan](../../lab/objects/p14b/compute-plan.log) places all 435 graph operations on `MLGPUComputeDevice`, Apple M5. The runtime leaves `MLComputeUnits=ALL`; this measured plan used the GPU, not the neural engine. CoreML requires its ordinary macOS model cache to be writable. The initial sandbox-only cache failure was resolved by running the local checks with cache access; no credentials were used.

From `pilot`, `.venv/bin/python tools/evaluate_objects.py --output ../lab/objects/p14b` and `.venv/bin/python tools/evaluate_objects.py --root ../lab/objects/holdout` produced the two receipts with a 30 Hz polling loop and one separate busy CPU process. Holdout output was `results_hz: 14.666666666666666`, `poll_max_ms: 0.169208` and `loop_hz: 30.0`. The model was warmed before measurement. CoreML compilation/startup is outside those steady-state timings.

`PILOT_OBJECTS_MEMORY=1 .venv/bin/python -m pytest -q -s tests/test_objects.py -k native_memory` passed after 100 warmup and 3000 real detections: `rss_growth_bytes: 5292032`, `limit_bytes: 16777216`, `passed: true`; the measured inference loop took 127.41 seconds. [The test output](../../lab/objects/p14b/memory-test.txt) and [RSS samples](../../lab/objects/p14b/memory.json) are retained. The test checks current RSS as well as high-water RSS, so the initialization peak cannot hide growth. The approximately 130-second soak is opt-in; running it inside the default gate would conflict with the 90-second gate limit.

The final `.venv/bin/python tools/gate.py` output was `479 passed, 1 skipped, 1376 deselected, 4 xfailed in 24.33s` and `gate passed in 24.58s (default)`. Ruff check and format check also passed. The new scoring tests cover cross-kind vehicles at the 0.4 boundary, size-gated inventions and the report denominator; existing real-frame, player-filter, corrupt-weight and asynchronous ownership/recovery tests pass with the new default. The soak was executed separately rather than counted as a default-gate pass. `git diff --check` passed.

Reproduction uses the locked development dependencies in `pilot/uv.lock`, the pinned fetch script, `lab/objects/compare.py` for YOLOX/RT-DETR and `lab/objects/compare_torchvision.py` for the heavier fallback. Both scripts only use local recordings and model files. Weights above 10 MB remain ignored under `pilot/models`; the fetch script includes their hashes. Historical P14 metrics and reports remain available alongside the P14b receipts.

No tested configuration met all quality targets. The best speed-eligible balanced result remains YOLOX-L640 at 0.4; M-native had higher vehicle recall but poorer person recall and more inventions, and L-native and FasterRCNN missed speed. Further progress needs locally labelled game-domain training or another demonstrably stronger permissive model, together with a player filter that distinguishes nearby NPCs and traffic from the controlled character. That work would need another unseen holdout because both current sets have now been inspected. No claim is made that additional training will meet the targets. The current result is suitable for continued offline development, not a completed accuracy acceptance gate.

All changes are confined to the card's write set. Under `docs/tasks/README.md`, changes are left in the existing worker branch without a commit or pull request for the reviewer to integrate. No live-console test, merge, deployment or publication was performed.

## Review

Checked in the night of 10 to 11 November. The numbers of the report reproduce exactly from its command. They understate the detector, because the second labelled set is wrong in places, and every error I found counts against the detector.

The report says each frame of the second set was checked on the raw picture. Frame 004 has five labels and four of them lie on nothing: a "bus" 207 pixels wide over the health bar, two trucks and a car on a wall and on the pavement, while the two trucks and the car that are on the road have no label. On frame 009 the three large labels sit 100 to 150 pixels below their vehicles on the empty road; the detector's boxes sit on the vehicles and are counted as three misses and three inventions. On frame 012 a car's label is 28 pixels low, enough to fall under the overlap of 0.4. On frames 008 and 029 one label spans two vehicles. `holdout/sheets/labelled-004.jpg` and `labelled-008.jpg` show it. So all three misses over 200 pixels are label errors, and of the eleven over 100 pixels six are (004, three on 009, 012, 029), one was found and then removed by the player filter (006), one is a truck mostly hidden behind a car (010), and three I could not judge (035, 055, 056, two of them on damaged frames). Several of the "invented" reports are real vehicles that were not labelled. On the frames I looked at, the detector found every vehicle a person would call near and visible. That is what getting into a car needs, and the model stays.

The set has to be corrected before it is used as a yardstick again; the numbers in the table above should not be quoted as the detector's quality.

People are a different matter and stay open: eight in the second set, all from one shootout, most of them half behind cover. Three of the seven misses were found by the model and then removed by the player filter, which took everyone standing where the player usually is. It takes only the largest such person and the largest such vehicle now, since the player is the one closest to the camera. On the second set that turns one of eight people found into three of eight and four wrongly removed objects into two, with the player reported on the same single frame; the first set is unchanged, with the player reported on none. The receipts of this version are `lab/objects/review/original.json` and `holdout.json`.

The frames of the first live session (`20261110-230229`) show no character at all: the game was in the first-person view there. The player filter then removes a truck in the middle of the road as the player's own vehicle (frame 006). The pilot should run in the third-person view.

Two more changes. `torch`, `torchvision` and `onnx` were added to the default development packages for comparisons that lost; they are in a dependency group of their own now and the default environment is 0.3 GB again instead of 1 GB. Eight breaks were tried against the tests, six failed one, and two are pinned now: reports below the confidence floor, and a frame offered while the detector is busy, which would have overwritten the pixels being read since the reader reuses one buffer.

Open: the detector takes 40 ms on the GPU of this machine and nothing else used the GPU while it was measured; the stream will encode video next to it. It is not attached to `pilot play` yet.
