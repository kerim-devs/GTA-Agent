# P107: The brake has a reason

The offline candidate removes braking in both recorded opposite-lane regression cases, releases a recorded following brake at 12.3 m/s, preserves both P106 first full-brake ticks, and keeps the accelerator released behind the newly reported half-hidden queue. Across the eight trips, identical-box replay reduces avoidance L2 from 64.566 to 57.884 seconds, or 5.82 to 5.22 percent of following time. **The three-percent target is not reached.** Onsets increase from 165 to 178, or 8.92 to 9.63 per minute. There are still unjustified brakes, including the empty part of the junction at `051709/64.9`. This is a measured improvement with unresolved acceptance risks, not proof that town driving is now satisfactory.

Only `avoid.py`, the inherited `Skill._around` used by `DriveRoute` and its `AROUND_*` constants, the new test and fixture, and `p107*` evidence were changed. Existing tests were not weakened. There was no console access, model change, commit, or change to another card's files.

The [measurement script](../../lab/avoid/p107_measure.py) ran the unchanged `objects.Detector.detect_split` on 5,590 pictures across the eight recordings and 153 pictures of `061133/75.5–86.5`. [Prefill](../../lab/avoid/p107_prefill.py) added 42 pictures in the pre-onset windows that fell outside following, for **5,785 measurement frames**. The one final gate adds 12 valid detector calls in `test_objects.py` (seven traffic/player checks, one confidence check and four split-player checks), bringing the task total to **5,797**, below 6,000. The saved counter and detection receipts are under `lab/avoid/p107*`. There was one inference process at nice 15, three-second pauses between 100-frame batches and sessions, and no further inference during replay. Sampling is about 0.1 seconds in the 1.5 seconds preceding each recorded onset through one second after release, about 0.27 seconds elsewhere in following, and about 0.05 seconds in the added queue case. Prefill uses 0.15 seconds. Actual capture times, not nominal sampling times, drive the tracker. The JPEG contact sheets are all below 300,000 bytes; the largest is 287,471 bytes. The complete evidence is about 17 MB, including the small compressed tick replays.

All 170 original onsets were reviewed in pictures at onset minus 0.4 seconds, onset, and onset plus 0.7 seconds, alongside the saved box sequences. The [labels](../../lab/avoid/p107-labels.json) retain onset times, notes and sheet names. “Crossing” includes pedestrians in the driven path, including the pavement; “nothing” includes distant traffic without a visible immediate conflict and the player's own car after a collision. “Oncoming” describes direction: notes explicitly mark cases where the own car has entered opposing traffic, rather than assuming every oncoming vehicle is safely in another lane. In particular, the card's `051709/25.2` example is already a side collision and roll in the picture, not a clean slower-lead experiment.

The [replay](../../lab/avoid/p107_replay.py) compares HEAD's avoider with the candidate using the same detections, causal recorded GPS readings, and a fixed 0.15-second capture-to-delivery delay. It counts `follow` and `coast`, excludes the speed law's own L2, and resets on a new skill attempt. The original driver's unmodified stick and movement flag were not logged: the replay estimates the former by subtracting the baseline avoider's push from the recorded resulting stick, and assumes moving is true. It does not reconstruct the live asynchronous detector's exact frame drops or latency. Therefore the recorded 170 onsets and replayed baseline 165 onsets are different measurements. Replay events are joined to reviewed original scenes by temporal overlap or a gap of at most 0.75 seconds; additional unmatched scenes were inspected and retained in [supplemental labels](../../lab/avoid/p107-extra-labels.json). Those supplemental contact sheets carry exploratory replay IDs; timestamps are authoritative. The final [classified events](../../lab/avoid/p107-classified.json) have no unreviewed onset.

Each cell below is **onsets / seconds with L2 / mean observed GPS loss in m/s (number with speed available)**. Loss is the nonnegative difference between onset speed and the minimum recorded speed through one second after release. It is descriptive, includes collision effects, and overlapping pulses can reuse the same fall. In particular, the after column is **not a prediction of speed lost under the new controller**.

| Picture class | Recorded live | Before, replay | After, replay |
| --- | --- | --- | --- |
| Standing vehicle in path | 31 / 12.629 / 3.35 (29) | 31 / 12.362 / 3.42 (29) | 36 / 11.850 / 3.70 (35) |
| Slower vehicle ahead | 36 / 13.525 / 1.67 (32) | 35 / 11.655 / 1.57 (29) | 42 / 11.141 / 1.75 (36) |
| Oncoming vehicle | 23 / 7.501 / 2.67 (18) | 22 / 7.498 / 4.15 (15) | 17 / 5.170 / 3.59 (14) |
| Crossing vehicle or person | 42 / 20.493 / 3.04 (40) | 44 / 22.316 / 2.84 (43) | 45 / 20.048 / 2.46 (43) |
| Parked or moving beside | 9 / 2.979 / 0.88 (8) | 8 / 3.295 / 0.57 (6) | 17 / 4.618 / 1.38 (15) |
| Nothing in the immediate path | 29 / 8.071 / 3.89 (18) | 25 / 7.441 / 3.06 (19) | 21 / 5.056 / 3.04 (16) |

The following are median **raw closing speed / own speed**, followed by the number of onsets with both estimates. The raw estimate is `(bumper distance + camera offset) / TTC`, before the own-speed cap. At an onset the first replay tick with usable speed and a requesting track is used; where several tracks request, the largest raw estimate is shown. These are replay associations, since the live log has no object identity. Missing estimates remain missing: there are only 82 such associations for the 170 recorded onsets. The full distributions and ratios are in [the table JSON](../../lab/avoid/p107-table.json).

| Class | Recorded-onset association, m/s | Before replay, m/s | After replay, m/s |
| --- | --- | --- | --- |
| Standing | 12.90 / 16.26 (18) | 12.90 / 14.47 (26) | 12.90 / 16.21 (30) |
| Slower | 14.67 / 15.03 (20) | 14.32 / 16.07 (28) | 15.09 / 18.51 (31) |
| Oncoming | 22.68 / 12.27 (6) | 17.36 / 12.72 (10) | 11.85 / 12.45 (9) |
| Crossing | 4.77 / 8.24 (27) | 4.73 / 8.29 (34) | 6.49 / 8.24 (33) |
| Beside | 20.89 / 18.64 (4) | 23.96 / 17.08 (5) | 12.33 / 18.83 (12) |
| Nothing | 11.08 / 20.95 (7) | 10.55 / 16.95 (12) | 13.08 / 19.54 (10) |

The changes follow these limitations. A vehicle closing above 2.5 times own speed, at own speed above 5 m/s and outside the inner quarter-width of the corridor, no longer requests L2. The uncapped estimate is inspected first; steering remains. A blanket two-times-speed veto is unsafe: P106's stationary queue itself fits 47.98 m/s against GPS 22.18 m/s, a ratio of 2.16. Central apparent head-on threats retain braking.

For bends, `_around` projects a bounded lane offset from trusted route bearing minus heading. An error below eight degrees leaves the original corridor unchanged. A larger error must agree with the commanded steering and either consistent near/far bearings or a heading error already shrinking over time. The latter avoids interpreting the upcoming junction beyond the newly reported queue as the current lane. The projection is approximate, capped at 0.18 picture widths, and affects braking rather than the original P96 steering corridor. It removes 0.949 seconds of baseline L2 in the `051709/123.2–126.0` fixture and 0.498 seconds in the `055729/89–93` oncoming-lorry fixture; both now request no L2 throughout.

For a slower lead above 5 m/s own speed, closing below 70 percent of own speed with more than 1.5 seconds of contact time remaining after observation age permits coasting when beyond the bumper gap. When stopping distance still requires L2, strength scales as closing speed divided by 70 percent of own speed, capped at one; every avoidance brake suppresses R2 and retains the steering push. Remembered brakes are re-evaluated instead of holding obsolete full strength. The recorded `053655/612.7–615.7` case retains a real brake but reduces it from 0.251 to 0.110 seconds, releases earlier, and ends at 12.33 m/s. The `051709/73.2–78.0` replay's short 0.115-second request disappears. The five-m/s lower bound matters: without it, GPS lag near rest made the existing parked-car simulation look like a moving lead and delayed its recovery beyond the unchanged timeout assertion.

Both P106 first requests remain full L2 with zero R2, exactly to their original tick: **queue 272.2701 seconds, lorry 295.2243 seconds**. Their bearing errors are 0.70 and 6.58 degrees, so the bend correction is inactive. Their raw closing speeds are 47.98 and 16.06 m/s against own speeds 22.18 and 16.75; neither meets the oncoming veto or slower-lead release condition, and both request full strength. Nearness is zero on those first boxes, so the new close-queue state does not initiate either brake. GPS-gap, unknown-speed, width-growth and lost-box P106 tests remain green. This preserves early requests, not a new proof of stopping distance: P106's recorded queue still has the negative idealized stopping margin documented by its unchanged test.

The added `061133/76–86` case exposes the other failure. At capture 76.939 seconds the central lead box is 41.8 pixels high and 100.7 wide, near 0.573, with fitted TTC 0.136 seconds and bumper distance 8.90 m. That implausibly short TTC already shows why the raw fit cannot be treated as calibrated truth. Later the visible vehicle body is left of the original centre corridor and half hidden by the own car. Height stops growing even while the car is still closing; the old controller releases L2 and eventually R2 suppression as well.

| Queue capture time | Box height / width, px | TTC, s | Nearness | Estimated gap, m | Recorded own speed at delivery, m/s |
| --- | --- | --- | --- | --- | --- |
| 78.687 | 95.6 / 134.4 | 1.048 | 0.798 | 5.16 | 20.01 |
| 78.838 | 117.0 / 129.5 | 0.646 | 0.853 | 4.26 | 20.01 |
| 79.069 | 115.8 / 127.2 | 1.061 | 0.846 | 4.36 | 17.76 |
| 79.370 | 117.1 / 135.9 | 28.024 | 0.853 | 4.25 | 13.78 |
| 79.988 | 114.0 / 148.1 | Infinite | 0.860 | 4.13 | 7.61 |
| 80.456 | 112.5 / 146.8 | Infinite | 0.855 | 4.21 | 5.47 |

A track with sustained imminent approach for at least 0.15 seconds, closing at 0.7–1.3 times own speed, can retain a queue stop while its close visible body still overlaps the own track. This requires near 0.8, a box bottom above the detector’s 510-pixel own-vehicle exclusion boundary and an approximately straight corridor; proximity alone cannot start it. Fresh evidence of that same close body retains full L2 above 2 m/s and zero R2 through the GPS gap and at rest, even after height-derived TTC becomes infinite. Leaving the overlap, losing fresh detections or opening the gap releases the state. An adjacent steady car cannot start it, and a vanished box cannot hold it indefinitely.

In this separate case, the recorded three pulses integrate to **0.605 seconds** with tick-interval accounting; the coordinator's approximate pulse lengths sum to 0.50 seconds. Baseline replay has three onsets / 1.293 seconds / mean observed loss 5.54 m/s; the candidate has four / 5.556 / 6.62 m/s. The recorded mean loss is 5.59 m/s. All are standing-queue class; this case is excluded from the eight-trip denominator. The first request remains 77.0147 seconds. The sustained candidate brake runs 79.078–82.612 and 82.756–83.517, with zero accelerator across the intervening missing-speed period. The recorded regression requires zero R2 on every tick from 80.3 seconds to its end, full L2 when known speed exceeds 2 m/s, and no L2 below that threshold or through the unknown-speed interval. These are stop-and-wait commands. They do not demonstrate that the real car would already be standing before contact: the replay cannot move the vehicle or repair the very uncertain distance estimate.

| Trip suffix | Following seconds | Before L2 seconds / percent | After L2 seconds / percent |
| --- | --- | --- | --- |
| 051709 | 137.026 | 10.629 / 7.757 | 9.284 / 6.775 |
| 052018 | 166.356 | 4.005 / 2.407 | 4.080 / 2.452 |
| 052402 | 134.225 | 8.230 / 6.131 | 5.777 / 4.304 |
| 052653 | 109.771 | 9.376 / 8.541 | 9.917 / 9.034 |
| 053655 | 154.037 | 12.714 / 8.254 | 11.072 / 7.188 |
| 054734 | 180.372 | 7.419 / 4.113 | 6.786 / 3.762 |
| 055349 | 143.563 | 7.694 / 5.359 | 7.044 / 4.907 |
| 055729 | 83.984 | 4.500 / 5.358 | 3.924 / 4.672 |
| Total | 1109.335 | 64.566 / 5.820 | 57.884 / 5.218 |

The live reference is 65.197 seconds, 5.877 percent and 170 onsets. The candidate reduces identical-input brake exposure by 10.35 percent, while strength-integrated exposure is 48.890 full-L2-equivalent seconds, 4.41 percent. That latter figure does not replace the requested any-L2 measure. Standing, slower and crossing classes alone account for 43.040 seconds, 3.88 percent: queues, buses across the path and pedestrians on the driven pavement are real reasons to slow. Thus removing every other class would still miss three percent on this recorded trajectory. But a class is not proof of correct timing or intensity: distant crossing traffic is included, and the current controller is still too conservative in some of those scenes.

Specifically, `051709/64.9` still receives 0.462 seconds of replay L2. At its onset the crossing car's wide, shallow box is 133.9 by 44.9 pixels; the current width-based distance estimate says 5.20 m and TTC 1.02 seconds, despite the pictured empty immediate path. The candidate reduces its strength to about 0.707 but does not remove the request. “Nothing” retains 5.056 seconds and “beside” grows from 3.295 to 4.618 seconds. Some added close-body requests are the cost of the occluded-queue guard. These are unresolved false-positive and fragmentation risks, not justified merely by assigning a class. The next change needs better evidence for visible side aspect versus true occlusion and for the vehicle's actual projected path; more aggressive raw-closing or blanket near-box vetoes would endanger the P106 and added queue cases.

The [baseline receipt](../../lab/avoid/p107-before-tests.txt), produced by `nice -n 15 pilot/.venv/bin/python lab/avoid/p107_red.py`, is `7 failed, 4 passed`. It temporarily restores HEAD with `git show` and restores both working files byte for byte in `finally`. Failures are both recorded opposite-lane cases, the first slower-lead case, the half-hidden queue, the recorded release at 12.3 m/s, partial braking with steering retained, and the queue-loss test's initial requirement to be waiting. The unchanged P106 first-tick tests pass in both versions, as intended. The final focused command is:

```sh
nice -n 15 pilot/.venv/bin/python -m pytest -q pilot/tests/test_brake_with_a_reason.py pilot/tests/test_brake_for_the_lane.py pilot/tests/test_avoid.py pilot/tests/test_player_driving.py pilot/tests/test_drive_queue.py pilot/tests/test_round_what_stands.py
```

It reports `118 passed in 3.71s`. No P96, P101 or P106 expectation was changed. The whole gate was run once, from `pilot`, as `nice -n 15 .venv/bin/python tools/gate.py`. Lint and format checks passed, and its [last lines](../../lab/avoid/p107-gate.txt) are:

```text
3869 passed, 1 skipped, 1376 deselected, 1 xfailed in 125.54s (0:02:05)
gate passed in 125.94s (default)
default gate exceeded 90 seconds
```

**The gate process exits 1**, solely on the card's known runtime-budget condition. There was no silent-server failure to rerun. This is not an unqualified green gate.

The saved boxes can be replayed without inference using `p107_replay.py`, then `p107_table.py`, `p107_fixtures.py` and `p107_evidence.py`, all at nice 15. `p107_replay.py --only 061133` refreshes the added case separately. The fixed baseline is the task branch's HEAD before these changes; changing HEAD changes the comparison. No detector run is needed to reproduce the tables or the tests.

Open-loop replay establishes which pads the same boxes and readings request, their timing, strength and release, and the two P106 tick-preservation properties. The recorded car had already braked, struck other traffic, turned and sometimes rolled. A different controller would change every later box, camera pose, GPS reading and detector association. Neither the GPS-loss columns nor unchanged first brake times establish avoided collisions, stopping distance, live detector latency, route progress, or the car actually standing behind the added queue. The side-aspect distance error, approximate camera calibration, inferred driver stick, reduced sampling outside onset windows and manual scene labels remain limits.

The next comparable town trips should be judged first by collisions followed by recovery or a way round, with rear-end queue/lorry impacts and the `061133` queue failure called out separately. The eight earlier trips' zero queue/lorry rear-end recoveries must be retained, and the added case must visibly end standing behind the queue without pushing it. Then compare any avoidance L2 divided by following time against the below-three-percent target, report the speed law separately, and compare avoidance onsets per following minute against the live 9.19 and candidate replay 9.63. Finally compare metres of route advanced per second over the whole drive, including waits, bypass and recovery, rather than reporting GPS speed alone. Lower brake duty achieved by losing the stopping protection, or higher speed achieved through more collision recovery, would fail acceptance.
