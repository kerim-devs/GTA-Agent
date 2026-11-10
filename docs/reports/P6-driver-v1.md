# P6 driver v1 report

Status: incomplete. The human-direction and reader criteria pass, but the closed-loop distance and arrival criteria do not. The retained change fixes the measured steering cancellation, preserves a recently agreed route through bounded damage, and makes the failures reproducible. It is not ready to integrate as a validated driving controller.

The work started from `d2f2e79fd641f26f79ac12cb0cfd18aef975dcce` on `feat/pilot-driver-v1`. No console, daemon, remote-play credentials, network service, commit, or push was used. The task README explicitly says “Git cannot write here: no commit, stash, checkout or reset.” Changes remain for the reviewer under that task-specific rule.

The reader, simulator and Reading contract are unchanged in the final diff. An experimental short-bearing extension was removed after it failed image-based validation. The driver no longer subtracts `corner_bias` from its steering error; that tunable was removed. Bearing/steering smoothing is now 0.1/0.05 seconds with a four-degree neutral band. Delay prediction is disabled inside that band, preventing amplified map jitter from causing repeated countersteering.

Damaged observations can continue `follow` only on a vehicle map with the same route colour, finite confidence at least 0.3, a clean anchor no older than 0.5 seconds, an error above five degrees with the same sign, and at most 25 degrees disagreement. They never refresh the clean anchor. A disagreeing observation falls back to the existing bounded coast/release behavior. Map loss clears the anchor. Route-gone braking, recovery attempts, failed-recovery neutrality and unknown-motion behavior retain their existing tests.

## Human replay

The recording is `20261110-093238`: 14,214 frames, 18,507 human pad events, 695.9 seconds, controller on the Mac over Wi-Fi. Metadata was read first. Video decoding used OpenCV only. This measures descriptive direction agreement, not live latency or successful autonomous driving. The baseline and final replay use the CLI's `command_delay=0.14`. A final complete video decode reproduced the cached-reading truth table exactly.

At zero shift, all 495 ticks with a tilted map, yellow/purple route and human stick magnitude above 0.4 stay in the denominator. V1 follows 424/495 (85.66%, target at least 80%). Within follow, 371/424 (87.50%) commands agree (target at least 85%), 32/424 (7.55%) oppose (target at most 8%), and 21/424 are zero. V0 follows 284/495 (57.37%), with 52 same, 53 opposite and 179 zero commands. The aggregate v1 cohort has 383 same, 38 opposite and 74 zero commands, including coast.

The table separates command releases from wrong-way steering. Command zero means absolute steer at most 1e-9. Raw zero means wrapped `bearing-arrow` within ten degrees; its neutral band is deliberately explicit. Best-command and best-raw shifts are selected independently by correlation over +/-2 seconds, retaining at least half the zero-shift cohort. Human input is sampled at frame time plus shift; negative shift means the human led the frame. Shifted cohorts change and are not substituted for the zero-shift acceptance numbers.

| Version | Alignment | State | Command zero/same/opposite | Raw neutral/same/opposite |
|---|---|---|---:|---:|
| v0 | zero (+0.0000s) | follow | 179/52/53 | 69/211/4 |
| v0 | zero (+0.0000s) | coast | 162/32/17 | 45/155/11 |
| v0 | best command (-0.7560s) | follow | 122/124/30 | 90/155/31 |
| v0 | best command (-0.7560s) | coast | 86/65/6 | 50/90/17 |
| v0 | best raw (-0.1512s) | follow | 172/74/28 | 50/218/6 |
| v0 | best raw (-0.1512s) | coast | 160/23/16 | 36/151/12 |
| v1 | zero (+0.0000s) | follow | 21/371/32 | 85/326/13 |
| v1 | zero (+0.0000s) | coast | 53/12/6 | 29/40/2 |
| v1 | best command (-0.4536s) | follow | 13/370/20 | 98/288/17 |
| v1 | best command (-0.4536s) | coast | 38/14/3 | 31/24/0 |
| v1 | best raw (-0.1512s) | follow | 20/363/22 | 63/327/15 |
| v1 | best raw (-0.1512s) | coast | 54/10/4 | 23/42/3 |

V0 best-command correlation is 0.5240, and v1 is 0.8267. Both raw comparisons have correlation 0.8098. These are correlation diagnostics, not calibrated input-to-screen delays.

## Closed-loop matrix

Each version runs the unchanged six scenarios over delays 0.14/0.21/0.30 seconds, scales 0.5/1/2 metres per pixel, seeds 0/1/2 and dead zones 0/0.25: 324 runs. Simulator and driver default model parameters are retained except the documented v1 driver changes. The driver assumes its default 0.21-second delay throughout this sensitivity grid; actual simulated delay varies independently. V0 uses the original driver source at the commit above. The following table aggregates the 18 runs per scenario/scale, taking worst-case mean distance, maximum distance, flips and progress gap. Each pair is v0 / v1.

| Scenario | m/px | Reached (of 18), v0/v1 | Worst mean m, v0/v1 | Max m, v0/v1 | Max flips/s, v0/v1 | Max progress gap s, v0/v1 |
|---|---:|---:|---:|---:|---:|---:|
| straight | 0.5 | 18/18 | 1.086/1.164 | 3.444/3.344 | 1.260/0.767 | 1.433/1.400 |
| straight | 1 | 18/18 | 1.325/1.645 | 3.579/3.523 | 1.062/0.771 | 1.400/1.367 |
| straight | 2 | 18/18 | 2.639/2.920 | 3.671/4.004 | 1.057/0.778 | 1.400/1.300 |
| left | 0.5 | 18/18 | 2.282/0.863 | 10.897/6.146 | 1.099/0.879 | 4.433/1.033 |
| left | 1 | 18/18 | 2.513/2.780 | 9.535/13.328 | 0.778/0.794 | 1.767/1.033 |
| left | 2 | 18/18 | 3.511/7.174 | 8.145/27.626 | 0.395/0.708 | 1.400/1.367 |
| right | 0.5 | 18/18 | 1.254/0.824 | 6.410/6.293 | 1.225/0.770 | 3.067/1.033 |
| right | 1 | 18/18 | 3.312/2.943 | 11.442/13.498 | 0.768/0.715 | 2.633/1.033 |
| right | 2 | 18/18 | 3.474/7.180 | 8.225/27.881 | 0.420/0.596 | 1.367/1.367 |
| s_bend | 0.5 | 18/18 | 1.510/1.196 | 7.464/6.208 | 0.698/0.673 | 3.333/1.033 |
| s_bend | 1 | 18/18 | 3.510/3.620 | 13.527/13.190 | 0.332/0.628 | 3.067/1.033 |
| s_bend | 2 | 18/18 | 9.241/8.594 | 21.359/22.791 | 0.315/0.633 | 4.600/1.033 |
| block | 0.5 | 18/18 | 2.066/1.158 | 8.932/6.293 | 0.791/0.689 | 3.933/1.033 |
| block | 1 | 18/18 | 3.212/4.079 | 13.836/13.876 | 0.474/0.544 | 2.633/1.033 |
| block | 2 | 14/0 | 16.687/18.676 | 56.081/35.601 | 0.141/0.529 | 13.633/122.267 |
| wall | 0.5 | 18/18 | 1.576/1.411 | 6.350/6.137 | 0.628/0.748 | 7.833/7.767 |
| wall | 1 | 18/18 | 4.419/3.435 | 14.645/13.589 | 0.616/0.712 | 7.800/7.733 |
| wall | 2 | 18/18 | 2.595/10.008 | 9.072/28.243 | 0.519/0.643 | 7.867/23.300 |

V1 reaches 306/324 destinations; all 18 block cases at 2 m/px miss arrival. All 324 runs satisfy flips <=2/s (worst 0.879/s), but only the 54 straight runs meet the full P6 grid criteria. Every turning scenario misses the tightened 4 m or 6 m maximum-distance bound; the worst is 35.601 m. Removing steering cancellation makes corner cutting worse than v0 in this planar model. This regression remains unresolved and is the reason the card is incomplete.

`tests/test_sim.py` now checks the requested delays, the scale-specific distance limits and the flip limit for every scenario. The 270 measured v1 failures are pinned explicitly in `tests/fixtures/driver-v1-failures.json`, including the existing mean-distance/progress constraints. Each pin must match its exact three-decimal error list before it can xfail; changed or improved behavior fails for review. The original gate had 63 v0 xfails under the older .15-second/10-metre matrix. The increase is not a successful acceptance result or a widened tolerance.

## Reader and verification

The final reader source is byte-identical to the starting version. Dev: 34/34 routes, zero false routes, all near errors within 45 degrees, mean 1.01 ms, minimap accuracy 95.8%. Held: 11/11 routes, zero false routes, all near errors within 45 degrees, mean 0.72 ms, minimap accuracy 93.8%. Both satisfy the reader targets; no metric is claimed for an accepted short target because none was retained.

The package gate passes: 239 passed, 270 explicitly xfailed, 8.69 seconds. Ruff check and format check pass. Added regressions cover the cancelling bend, bounded damaged-frame agreement, stale trust, invalid/disagreeing damage, vehicle-map loss, predictive jitter, and state-separated replay counts. Existing route-gone, recovery, hostile-input and unknown-motion tests still pass. Gate success verifies implementation consistency with documented failures; it does not satisfy the missing simulator goals.

## Experiment notebook and decisions

First, the original full video replay reproduced the card's 495-tick zero/same/opposite baseline. Removing corner cancellation alone restored steering but produced wide turns; it was not sufficient. The corrupt-frame cohort contained 207 ticks, with time since clean route p50 0.207 s and p90 0.555 s. The 0.5-second cutoff deliberately excludes the tail and never chains damaged observations into indefinite trust. The 25-degree agreement bound is above the observed p90 angular difference of 8.37 degrees while rejecting new directions.

Second, a seven-pixel geometry target drove all 324 planar cases inside the requested limits with slow smoothing, with worst distances 3.233/3.235/5.783 m by scale and worst flips 1.548/s. This was rejected as acceptance evidence: the point came from the simulator's true polyline. The image reader's multi-pixel flood seed instead produced ambiguous under-arrow bearings. An annulus/seed visibility guard still gave 64 wrong-way short bearings among 202 eligible ticks. Early centered path sections (flood steps 2..4) gave 382 same/109 opposite; later sections (4..7) gave 447/47 among 494 usable ticks, essentially the existing near value's 447/48 among 495. A local tangent fit (2..9) gave 443/50. Flood steps are not a calibrated crop radius, so none provided a defensible equivalent of the simulator target. The extension was removed from contract, reader, simulator and driver rather than treating the idealized result as an image-perception success.

Third, faster filtering alone met replay direction goals but raised simulated flip rates to 7.677/s. Removing prediction entirely worsened replay opposite commands. Applying prediction only outside the four-degree neutral band preserved the replay thresholds and reduced worst grid flips to 0.879/s. Slower filtering and confirmed sign-change resets did not recover the zero-shift replay target and were discarded.

No brake pulse was added to cure corner geometry. There is no measured speed/deceleration model for the real car, and the reverse/brake trigger can reverse at rest. Existing throttle reduction for bends and bounded stop/recovery braking remain. Slower bend throttle (0.18 instead of 0.22) in the short-target study caused block timeouts without establishing real-car braking evidence, so it was discarded.

No defensible real m/px estimate or perspective correction is available from the metadata or labels. They contain no world pose, known travelled distance or calibrated per-frame world reference. The 0.5/1/2 m/px range is a sensitivity range, not a measured calibration. The unresolved need is a directed local route/arrow-exit representation validated in real crops, with its observability and perspective modeled in simulation. The current 30/60-pixel angles alone did not support a controller that passed both replay direction and tight closed-loop geometry in these experiments.

For a supervised real-car investigation, the existing CLI start configuration remains `DriveConfig(command_delay=0.14)` with v1 defaults: steer_gain 0.035, steering_bias 0.25, bearing_smoothing 0.1, steer_smoothing 0.05, steer_deadband 4, prediction_limit 8, cruise_throttle 0.58 and bend_throttle 0.22. Damage hold is 0.5 s, confidence_min 0.5, coast hold 0.3 s, route_gone_time 2 s and stop_brake_time 0.7 s. These are proposed starting values, not executed or calibrated real-car settings. The safe next dependency is offline/local-route validation followed by supervised shadow evaluation; the failed simulator gate does not support autonomous driving or integration approval.

## Reproduction and artifacts

Run the package gate with `cd pilot && .venv/bin/python tools/gate.py`. From the package directory, `tools/evaluate_driver.py --out tools/p6-results/v1-matrix.json` runs the full matrix under the package interpreter. `--rows tools/p6-results/v0.jsonl --pad /Users/kerim/Documents/ChatGPT/gta/recordings/20261110-093238/pad.jsonl --rerun --config '{"command_delay":0.14}' --out tools/p6-results/v1-truth.json` repeats the final driver on unchanged cached readings. `python -m pilot.cli replay /Users/kerim/Documents/ChatGPT/gta/recordings/20261110-093238 --out <absolute-worktree-output>` decodes the entire recording and prints both alignment tables. Always pass an output in this worktree; do not use replay's recording-directory default.

The local `pilot/tools/p6-results/` evidence contains baseline/final replay logs, truth tables and per-case matrices. These are generated evidence, not runtime dependencies. Baseline matrix measurements were produced by loading the original driver with `git show d2f2e79fd641f26f79ac12cb0cfd18aef975dcce:pilot/src/pilot/drive.py` into an isolated in-process module and running the unchanged simulator. No Git history was changed.

## Review

Checked on 10 November. The replay numbers reproduce from a full decode of the recording: 424 of 495 ticks in `follow`, 371 the human's way, 32 against, 21 zero. Each of the four new behaviours fails a test when it is taken out again: bridging damage, the bound on how long damage is trusted, no prediction inside the neutral band, and no cancelling of the steering in a bend. The two replay logs of 5 MB each are not committed; the command above regenerates them.

The simulator result stands as the worker states it and is the open problem. A lookahead of 30 map pixels starts a turn 30 pixels before the corner and cuts it by roughly a third of that, about a road width, and the old cancelling rule only hid this by not steering at all. It does not depend on the unknown scale: a road is about 12 to 15 pixels wide near the arrow, so the cut has to stay under about 6 pixels whatever a pixel is in metres. The card asked for agreement with the human's stick, and that was the wrong yardstick for a shorter lookahead: just before a corner the route close to the arrow is still straight while a person already steers, and on the Wi-Fi recording the person steers on a picture that is most of a second old. The worker's rejection of the short bearing on that yardstick is therefore not evidence against it. The next card gives the reader bearings at several radii and judges them against the picture instead.

This is merged as the base for that work. It must not drive the real car through a turn yet.
