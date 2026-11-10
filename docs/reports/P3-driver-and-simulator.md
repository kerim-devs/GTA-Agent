# P3 driver and simulator report

Implemented the controller, deterministic bicycle simulator, direct behavior tests and the complete 324-run closed-loop grid in the four assigned files. The fixed contract is unchanged. The required gate passes with 363 passing tests and 63 explicitly recorded expected failures. Of the 324 simulated drives, 320 reached the endpoint within the 240-second simulation limit and 261 met every acceptance bound. These results do not establish real-game readiness: the 63 cases below remain outside the requested bounds.

`Driver(config=DriveConfig()).step(reading, t, moving)` subtracts the arrow from the near and far picture angles, rejects abrupt single-frame jumps, filters the remaining angles and predicts a bounded amount across the command delay. The near error sets steering; the far angle reduces throttle and defers premature steering into a distant corner. A small steering bias accommodates a physical dead zone. Unreadable observations hold the last supported command for at most 0.3 seconds before releasing both pedals and centering the stick.

The command states are `idle`, `follow`, `coast`, `route-gone`, `recovery-reverse`, `recovery-forward` and `failed-recovery`. Two seconds of reliable route absence trigger a bounded brake pulse; unreadable intervals do not accumulate absence evidence. Once movement is explicitly false or the pulse expires, the pedal stays released while the route-gone state persists. Throttle with explicitly false movement triggers reverse steering away from the route, followed by forward feedback toward it. Short damaged intervals preserve an escape; three unsuccessful consecutive attempts latch neutral failed recovery. Sustained forward movement clears the attempt count. Unknown movement does not start a stuck timer. Invalid or backwards clocks release controls, and a new Driver instance is required to clear failed recovery.

`Simulator(route, position=..., heading=..., walls=..., config=SimConfig(...), seed=...).run(driver)` returns a `SimResult` with endpoint status, elapsed time, mean and maximum distance, longest progress gap, steering flips per second, recovery and collision counts, and final position. The implementation is pure Python with no runtime file access. Commands enter a timestamped queue and take effect at the exact configured delay, including fractional ticks. Walls intercept swept center-point motion. The route is recalculated from its globally nearest polyline projection; readings follow that connector and then the forward polyline to the 30/60-pixel sampling circles or its endpoint. Camera-relative arrow and route angles share a lagging camera. Motion is derived from true speed. All noise draws use one seeded generator.

The model runs at 30 Hz. Scale means metres per pixel, so the near sampling radius is 15, 30 or 60 metres and the far radius is 30, 60 or 120 metres. Equal near/far metres per pixel is an explicit modeling decision; the contract permits a larger far scale, but that additional dimension is not claimed tested. Clean near/far angle noise uses an 85% Gaussian mixture with sigma 3 degrees and a 15% tail with sigma 16 degrees; arrow noise has sigma 1.5 degrees. A seeded 12,000-sample test checks that differences six ticks apart fall around the observed 3.8-degree median and 15-degree p90, allowing 3.3–4.3 and 13–17 degrees respectively. Independent 1% near-angle outliers add 80–170 degrees with random sign, and 5% damaged observations report corrupt, missing route, missing angles and zero confidence. This distribution approximates the measured spread; it is not a fitted or replayed perception model.

The six scenarios are a 120-metre straight starting 3 metres sideways and 20 degrees off heading; mirrored 100-by-100-metre right-angle turns; an S-shaped polyline; a four-turn block route; and a north-facing start with a horizontal wall three metres ahead and a route initially going east. The wall requires reversing. Their exact coordinates and seeds are in `tests/test_sim.py`. Each scenario runs at all three delays (0.15, 0.21, 0.30 seconds), all three scales (0.5, 1, 2 metres/pixel), seeds 0, 1 and 2, and dead zones 0 and 0.25. End arrival requires being within 3 metres of the final point on the nearest final segment. Progress means a new best projected route distance by at least 0.5 metres, so reversing or motion in place does not count as progress. Distances include every tick and the initial pose. Steering flips count changes between nonzero command signs, retaining the last sign across zero.

Each table row below covers 18 runs: all delays, seeds and dead zones at that scenario and scale. The numerical columns are the worst observed value across those 18 runs, not averages of averages. A pass requires arrival, progress gaps at most 10 seconds, mean distance below 3 metres, maximum distance below 10 metres and, on the straight only, no more than 2 steering flips per second.

| Scenario | m/px | Pass / 18 | Reached / 18 | Max time (s) | Worst mean (m) | Worst max (m) | Worst gap (s) | Worst flips/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| straight | 0.5 | 18 | 18 | 29.167 | 1.070 | 3.442 | 1.433 | 1.105 |
| straight | 1 | 18 | 18 | 28.200 | 1.322 | 3.576 | 1.400 | 1.062 |
| straight | 2 | 18 | 18 | 27.000 | 2.608 | 3.668 | 1.400 | 1.055 |
| left | 0.5 | 17 | 18 | 55.900 | 2.282 | 10.897 | 4.433 | 1.099 |
| left | 1 | 18 | 18 | 56.133 | 2.513 | 9.535 | 1.767 | 0.778 |
| left | 2 | 9 | 18 | 67.667 | 3.511 | 8.142 | 1.400 | 0.396 |
| right | 0.5 | 18 | 18 | 55.000 | 1.254 | 6.410 | 3.067 | 1.225 |
| right | 1 | 17 | 18 | 57.200 | 3.312 | 11.442 | 2.633 | 0.768 |
| right | 2 | 15 | 18 | 67.467 | 3.474 | 8.225 | 1.367 | 0.418 |
| s_bend | 0.5 | 18 | 18 | 99.967 | 1.510 | 7.464 | 3.333 | 0.669 |
| s_bend | 1 | 17 | 18 | 119.967 | 3.510 | 13.527 | 3.067 | 0.322 |
| s_bend | 2 | 0 | 18 | 108.833 | 9.241 | 21.354 | 4.600 | 0.336 |
| block | 0.5 | 18 | 18 | 151.867 | 2.066 | 8.932 | 3.933 | 0.756 |
| block | 1 | 15 | 18 | 161.967 | 3.212 | 13.836 | 2.633 | 0.434 |
| block | 2 | 0 | 14 | 240.033 | 16.687 | 56.081 | 13.633 | 0.113 |
| wall | 0.5 | 18 | 18 | 54.633 | 1.576 | 6.350 | 7.833 | 0.645 |
| wall | 1 | 9 | 18 | 61.400 | 4.419 | 14.645 | 7.800 | 0.616 |
| wall | 2 | 18 | 18 | 63.300 | 2.595 | 9.006 | 8.500 | 0.616 |

All 54 straight runs meet every bound. Every wall run reaches the endpoint and its worst progress gap is 8.500 seconds; nine wall runs still exceed the route-distance bounds. Large-scale bends and the block expose substantial limitations: the largest mean distance is 16.687 metres and the largest maximum distance is 56.081 metres. Four block runs do not finish within 240 seconds. The gate is green because the card explicitly permits measured expected failures, not because these targets were met.

Every expected failure is listed below. `KNOWN_FAILURES` records these exact cells and their measured violations to three decimal places. A new failing cell is a normal test failure. A changed result in a known cell, including an improvement or a different violation, also fails for review instead of being silently accepted; only an unchanged known result calls `pytest.xfail` with its measured reason. No acceptance threshold was relaxed.

| Scenario | Delay (s) | m/px | Seed | Dead zone | Measured violations |
| --- | ---: | ---: | ---: | ---: | --- |
| left | 0.15 | 2 | 0 | 0 | mean 3.453m >= 3m |
| left | 0.15 | 2 | 1 | 0 | mean 3.484m >= 3m |
| left | 0.15 | 2 | 2 | 0 | mean 3.063m >= 3m |
| left | 0.21 | 2 | 0 | 0 | mean 3.468m >= 3m |
| left | 0.21 | 2 | 1 | 0 | mean 3.511m >= 3m |
| left | 0.21 | 2 | 2 | 0 | mean 3.113m >= 3m |
| left | 0.30 | 0.5 | 0 | 0 | maximum 10.897m >= 10m |
| left | 0.30 | 2 | 0 | 0 | mean 3.458m >= 3m |
| left | 0.30 | 2 | 1 | 0 | mean 3.496m >= 3m |
| left | 0.30 | 2 | 2 | 0 | mean 3.059m >= 3m |
| right | 0.15 | 2 | 2 | 0 | mean 3.465m >= 3m |
| right | 0.21 | 2 | 2 | 0 | mean 3.456m >= 3m |
| right | 0.30 | 1 | 0 | 0 | mean 3.312m >= 3m; maximum 11.442m >= 10m |
| right | 0.30 | 2 | 2 | 0 | mean 3.474m >= 3m |
| s_bend | 0.15 | 2 | 0 | 0 | mean 8.472m >= 3m; maximum 18.801m >= 10m |
| s_bend | 0.15 | 2 | 0 | 0.25 | mean 6.016m >= 3m; maximum 20.819m >= 10m |
| s_bend | 0.15 | 2 | 1 | 0 | mean 8.214m >= 3m; maximum 20.076m >= 10m |
| s_bend | 0.15 | 2 | 1 | 0.25 | mean 6.313m >= 3m; maximum 20.905m >= 10m |
| s_bend | 0.15 | 2 | 2 | 0 | mean 7.857m >= 3m; maximum 19.910m >= 10m |
| s_bend | 0.15 | 2 | 2 | 0.25 | mean 6.097m >= 3m; maximum 21.320m >= 10m |
| s_bend | 0.21 | 2 | 0 | 0 | mean 8.844m >= 3m; maximum 17.998m >= 10m |
| s_bend | 0.21 | 2 | 0 | 0.25 | mean 6.210m >= 3m; maximum 20.682m >= 10m |
| s_bend | 0.21 | 2 | 1 | 0 | mean 8.360m >= 3m; maximum 20.257m >= 10m |
| s_bend | 0.21 | 2 | 1 | 0.25 | mean 6.452m >= 3m; maximum 20.846m >= 10m |
| s_bend | 0.21 | 2 | 2 | 0 | mean 8.033m >= 3m; maximum 20.160m >= 10m |
| s_bend | 0.21 | 2 | 2 | 0.25 | mean 6.311m >= 3m; maximum 21.354m >= 10m |
| s_bend | 0.30 | 1 | 1 | 0 | mean 3.510m >= 3m; maximum 13.527m >= 10m |
| s_bend | 0.30 | 2 | 0 | 0 | mean 9.241m >= 3m; maximum 17.792m >= 10m |
| s_bend | 0.30 | 2 | 0 | 0.25 | mean 6.714m >= 3m; maximum 20.483m >= 10m |
| s_bend | 0.30 | 2 | 1 | 0 | mean 8.767m >= 3m; maximum 20.972m >= 10m |
| s_bend | 0.30 | 2 | 1 | 0.25 | mean 6.859m >= 3m; maximum 20.362m >= 10m |
| s_bend | 0.30 | 2 | 2 | 0 | mean 8.616m >= 3m; maximum 19.735m >= 10m |
| s_bend | 0.30 | 2 | 2 | 0.25 | mean 6.575m >= 3m; maximum 20.949m >= 10m |
| block | 0.15 | 1 | 2 | 0 | maximum 10.549m >= 10m |
| block | 0.15 | 2 | 0 | 0 | progress gap 13.600s > 10s; mean 14.418m >= 3m; maximum 53.682m >= 10m |
| block | 0.15 | 2 | 0 | 0.25 | not reached at 240.033s; progress gap 11.633s > 10s; mean 15.644m >= 3m; maximum 50.786m >= 10m |
| block | 0.15 | 2 | 1 | 0 | progress gap 12.833s > 10s; mean 14.865m >= 3m; maximum 55.455m >= 10m |
| block | 0.15 | 2 | 1 | 0.25 | progress gap 11.500s > 10s; mean 14.428m >= 3m; maximum 52.720m >= 10m |
| block | 0.15 | 2 | 2 | 0 | progress gap 13.133s > 10s; mean 14.617m >= 3m; maximum 54.616m >= 10m |
| block | 0.15 | 2 | 2 | 0.25 | progress gap 10.767s > 10s; mean 14.455m >= 3m; maximum 45.804m >= 10m |
| block | 0.21 | 2 | 0 | 0 | progress gap 13.600s > 10s; mean 14.433m >= 3m; maximum 53.214m >= 10m |
| block | 0.21 | 2 | 0 | 0.25 | not reached at 240.033s; progress gap 11.600s > 10s; mean 15.056m >= 3m; maximum 50.783m >= 10m |
| block | 0.21 | 2 | 1 | 0 | progress gap 12.833s > 10s; mean 15.207m >= 3m; maximum 55.384m >= 10m |
| block | 0.21 | 2 | 1 | 0.25 | progress gap 11.533s > 10s; mean 15.199m >= 3m; maximum 53.039m >= 10m |
| block | 0.21 | 2 | 2 | 0 | progress gap 13.167s > 10s; mean 14.925m >= 3m; maximum 55.722m >= 10m |
| block | 0.21 | 2 | 2 | 0.25 | progress gap 10.867s > 10s; mean 14.005m >= 3m; maximum 45.164m >= 10m |
| block | 0.30 | 1 | 0 | 0 | mean 3.212m >= 3m; maximum 11.442m >= 10m |
| block | 0.30 | 1 | 1 | 0 | maximum 13.836m >= 10m |
| block | 0.30 | 2 | 0 | 0 | progress gap 13.633s > 10s; mean 14.677m >= 3m; maximum 53.179m >= 10m |
| block | 0.30 | 2 | 0 | 0.25 | not reached at 240.033s; progress gap 11.700s > 10s; mean 15.299m >= 3m; maximum 51.304m >= 10m |
| block | 0.30 | 2 | 1 | 0 | progress gap 12.800s > 10s; mean 15.691m >= 3m; maximum 55.084m >= 10m |
| block | 0.30 | 2 | 1 | 0.25 | not reached at 240.033s; progress gap 11.533s > 10s; mean 16.687m >= 3m; maximum 56.081m >= 10m |
| block | 0.30 | 2 | 2 | 0 | progress gap 13.100s > 10s; mean 14.715m >= 3m; maximum 55.190m >= 10m |
| block | 0.30 | 2 | 2 | 0.25 | progress gap 10.967s > 10s; mean 13.345m >= 3m; maximum 44.183m >= 10m |
| wall | 0.15 | 1 | 0 | 0 | mean 3.502m >= 3m; maximum 11.853m >= 10m |
| wall | 0.15 | 1 | 1 | 0 | mean 3.410m >= 3m; maximum 11.256m >= 10m |
| wall | 0.15 | 1 | 2 | 0 | mean 3.140m >= 3m; maximum 10.265m >= 10m |
| wall | 0.21 | 1 | 0 | 0 | mean 4.033m >= 3m; maximum 13.475m >= 10m |
| wall | 0.21 | 1 | 1 | 0 | mean 3.747m >= 3m; maximum 12.433m >= 10m |
| wall | 0.21 | 1 | 2 | 0 | mean 3.493m >= 3m; maximum 11.482m >= 10m |
| wall | 0.30 | 1 | 0 | 0 | mean 4.419m >= 3m; maximum 14.645m >= 10m |
| wall | 0.30 | 1 | 1 | 0 | mean 4.323m >= 3m; maximum 14.634m >= 10m |
| wall | 0.30 | 1 | 2 | 0 | mean 3.967m >= 3m; maximum 13.082m >= 10m |

Validation was run from `pilot/` with `.venv/bin/python tools/gate.py`. Its relevant output was:

```text
$ ruff check src tests tools
All checks passed!
$ ruff format --check src tests tools
9 files already formatted
$ pytest -q
363 passed, 63 xfailed in 19.21s
gate passed
```

The suite stays below the one-minute budget. Direct tests cover relative angle signs, speed reduction before bends, neutral non-vehicle maps, bounded coasting, route disappearance across unreadable frames, brake release without indefinite reverse, three failed escapes, genuine sustained-motion reset, intermittent damage during recovery, isolated outliers, hostile scalar fields and backwards clocks. Model checks cover seeded reproducibility, fractional command delay, map scales and camera subtraction, global rerouting, dead-zone response, braking into reverse, wall sweep collision, closed-loop start/end ambiguity and the noise distribution. `git diff --check` also passed. Git writes were prohibited by the task README; changes remain in the existing `feat/pilot-driver` worktree for the reviewer to commit, with no push or pull request.

The primary real-game tuning directions are below. Every tunable has a field comment in `DriveConfig`. Values are conservative model choices, not measured GTA handling constants.

| Symptom | Parameters and direction |
| --- | --- |
| Weaving or small rapid steering reversals | Reduce `steer_gain` or `steering_bias`; increase `bearing_smoothing`, `steer_smoothing` or `steer_deadband`. Keep `command_delay` aligned with measured latency and reduce `prediction_limit` if prediction amplifies noise. More filtering also delays real turns. |
| Turning too early and cutting inside a distant corner | Increase `corner_bias` to defer steering relative to the far bearing. Check the actual near/far perception and map perspective first; this heuristic still fails on multi-turn large-scale routes. |
| Running wide because steering is weak or delayed | Reduce excessive smoothing or `corner_bias`, then increase `steer_gain`; increase `steering_bias` only after confirming a physical dead zone. Lower `cruise_throttle` or `bend_throttle` while calibrating. |
| Braking or slowing too late | Increase `bend_gain`, reduce `bend_throttle` and, if necessary, `cruise_throttle`. Follow mode currently slows by releasing throttle, not by asserting L2. Calibrate `stop_brake_time` separately for route disappearance; extending it can cause reverse. |
| Wrong recovery duration or nuisance recovery | Tune `stuck_time`, `reverse_time`, `forward_time`, `recovery_steer`, `recovery_throttle` and `recovery_clear_time` against actual forward/reverse movement. Preserve the bounded `max_recoveries` stop and the distinction between false and unknown motion. |
| False outlier rejection or unsafe stale controls | Check `confidence_min`, `outlier_angle` and `outlier_window` against held reader crops. Keep `hold_time` short and tune `route_gone_time` only with clear arrival/lost-route evidence. |

No real console, daemon, ps5rp command, network service, PS5_HOST variable or remote-play configuration was accessed. Actual GTA steering response, braking distance, analog steering, map perspective changes, tire slip, vehicle dimensions, collision response, and real reader/runtime integration remain unverified. The wall model uses a point vehicle and does not model body contact or sliding. The 0.7-second route-stop pulse and optional motion feedback cannot guarantee a physical stop from an unknown speed; they bound L2 so a missing picture cannot cause indefinite reverse. Failed recovery intentionally releases both pedals rather than holding L2. Idle maps remain neutral even after a failure latch, which becomes visible again when a tilted map returns.

The next worker can rely on the unchanged Reading/Command contract and on these local tests, not on all-grid route following or real-game safety. Pass monotonic seconds and preserve `moving=None` when motion is unknown. Route-gone reports only route disappearance; arrival versus a lost route is still the head's decision. Resolve the listed distance/progress failures and calibrate handling against authorized real-game evidence before treating this controller as ready for unattended driving. The remaining deviations are recorded, not fixed by hiding the scale range or weakening the bounds.

## Review

The gate was rerun outside the sandbox: 363 passed, 63 expected failures, 19 s. The driver is accepted as a first version to take onto the real game, not as a tuned controller.

One thing the scenarios do not cover was tested in review: smooth curves. On a 120 degree arc, worst of two seeds, the car stays within 4.4 m of the route at 0.5 m per pixel for radii of 40, 80 and 150 m. At 1 m per pixel it runs up to 14.5 m wide on the 40 m radius, 7.5 m on 80 m and 4 m on 150 m, and at 2 m per pixel 13 to 27 m. The cause is the corner rule: on a steady curve the far bearing is always about twice the near one, which the rule reads as a corner still ahead and answers by holding the steering back. Together with the failures at 2 m per pixel in the grid this says the same thing twice: two bearings at fixed radii are not enough to place a turn once the near circle covers more than about 30 m. The real scale of the vehicle map is therefore the first thing to measure live, and if it is above 1 m per pixel the reader has to hand over points of the route closer to the arrow.

The expected failures are pinned to three decimals for the default configuration. The runtime passes the measured delay through its own configuration instead of changing the defaults, so the baseline stays valid until the driver itself is changed.
