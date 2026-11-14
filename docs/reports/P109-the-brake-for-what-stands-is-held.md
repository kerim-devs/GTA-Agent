The held-brake change closes the reproduced night-approach gap without changing the initial brake law. Both P106 and P107 release for the same reason: the standing car's centre leaves the narrow brake-entry corridor while its body still overlaps the driven path. The detector does not lose the car there, and P107 does not classify it as a slower lead there. The new replay holds full L2 from 94.5166 to 95.9966 seconds, when the measured overlap finally ends. Across P107's eight trips, any avoidance L2 rises from 57.994 to 60.236 seconds, or 5.228 to 5.430 percent of 1109.335 following seconds. The increase is 0.202 percentage points, below the card's half-point limit. Onsets fall from 178 to 176, or 9.627 to 9.519 per following minute. The earlier three-percent target remains unmet.

The only production file changed is `pilot/src/pilot/avoid.py`. `skills.py`, the driver, readers, model and all existing tests are unchanged. The new test and small recorded fixture, measurement scripts and receipts are under their assigned P109 paths. There was no console or daemon request, credential access, recording write, Git write or work outside this worktree. No commit or pull request was made because this dispatch explicitly prohibits Git writes. The unavailable explorer was replaced with read-only local file commands. The task's console prohibition overrides PLAN.md's historical live permission.

`nice -n 15 pilot/.venv/bin/python lab/avoid/p109_measure.py` selected 51 recorded pilot frames from capture times 93.0–96.5 seconds, at least 0.05 seconds apart, using the unchanged `objects.Detector.detect_split`. It paused for three seconds after frames 25 and 50. Measured inference minimum/median/maximum was 0.0463/0.0643/0.1199 seconds. The [detector receipt](../../lab/avoid/p109-detect.txt), [counter](../../lab/avoid/p109-inferences.txt) and [exact boxes](../../lab/avoid/p109-073626-boxes.jsonl) are retained. Twelve detector calls are reserved for the single final gate, making 63 calls including it, well below 1500. All workloads ran serially at nice 15. The sandbox initially refused setpriority; that attempt stopped at the priority guard before constructing the detector or running inference, and the authorized unsandboxed invocation supplied nice 15.

The [replay program](../../lab/avoid/p109_replay.py) loads both `avoid.py` and `skills.py` from `af48de4^` for P106 and from the frozen task base `6124b3d` for P107; P109 uses the working tree. It feeds identical boxes, capture times and causal recorded GPS to each, with an independent tracker and skill per version and a reset per attempt. It reconstructs the common driver stick by subtracting P106's replay steering push from the logged result, as P107's measurement did. Only follow/coast time counts, the driver's own brake is zero in the replay, and movement is assumed true because that flag and the live detector's selected frames/delivery times were not logged.

For the night account, a fixed 0.05-second delivery delay reproduces the logged first full brake at 94.5166 and its first release tick at 94.8873. This is an explicitly chosen reconstruction near the measured latency minimum, not proof of the live detector's exact schedule. At the existing P107 comparison delay of 0.15 seconds, both old versions instead start at 94.6264 and release at 95.0037, with the same lane cause; P109 holds to 96.0800. Both traces are retained in [the short-delay account](../../lab/avoid/p109-night-trace.jsonl) and [the 0.15-second sensitivity](../../lab/avoid/p109-night-trace-0.15.jsonl). The eight-trip cost comparison always uses P107's 0.15-second delay and its original saved boxes, with no new inference. This timing uncertainty prevents a claim that the exact unlogged live box at 94.8873 is known.

At capture 94.7627, the target centre is 0.431 projected vehicle widths from the centre line and both old versions still brake. At capture 94.8306, it is 0.468 widths away. `in_path` accepts the inner 0.45 widths unconditionally, but its 0.45–0.7 outer region requires convergence with a median lateral slope below -0.3. This target is moving outward, so that test fails. Its box remains matched, TTC is about 1.002 seconds, raw closing speed about 32.69 m/s, and GPS about 22.50 m/s on the first release tick. The stopping-distance law would still brake if admitted. No missing detection or slower-lead veto is involved. P106 has the same entry test and also releases; the card's two proposed explanations did not cover this inherited spatial-release defect.

P106 then remains off L2. P107 resumes at 95.6878 because its separate half-hidden-queue rule finally has both confirmed approach and nearness at least 0.8. Before that, it gives the pedal back, initially fully and then increasingly lifted. The lane projection is zero in both versions for every tick below; P107's bend correction is inactive. At 95.9966 in the short-delay replay, the latest box reaches lateral 1.102 and leaves the existing TRACK=1.1 overlap allowance, releasing both P107's queue hold and P109's new hold. This is a geometrical release on the already recorded collision trajectory, not a claim that a safe pass occurred. The task places contact at about 96.2 seconds; replay cannot move or stop the car and therefore cannot turn this later box motion into avoided-contact evidence. The [136 kB contact sheet](../../lab/avoid/p109-night-sheet.jpg) shows the approach and lateral shift; the JPEG is diagnostic and must not be committed.

The table includes every command tick from 94.3 through 96.2 seconds. The target box, TTC and raw closing estimate are identical in both old trackers, so those columns are shared. Lateral is the absolute centre offset divided by projected width; the braking lane itself is zero. Before the first L2, short growth history gives no brake. From the first release onward, every clear or pedal-only P106/P107 row is rejected by the lane test, irrespective of its still-short TTC. “L2 1 queue” marks P107's close-body exception. “Pedal” is the avoider's multiplier on a requested full accelerator, not the live driver's absolute R2. Exact unrounded values, other detected objects, track matching and decision reasons are in the trace.

| Tick / capture s | Box xyxy px | GPS m/s | Lateral | TTC s / raw closing m/s | P106 | P107 | P109 L2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 94.3223 / 94.2299 | 620.5,314.2,649.3,334.1 | 21.43 | 0.176 | unknown | clear | clear | 0 |
| 94.3639 / 94.3119 | 618.9,312.2,647.1,332.0 | 21.43 | 0.248 | unknown | clear | clear | 0 |
| 94.4036 / 94.3119 | 618.9,312.2,647.1,332.0 | 20.79 | 0.248 | unknown | clear | clear | 0 |
| 94.4453 / 94.3623 | 616.7,310.1,647.1,331.8 | 20.79 | 0.266 | unknown | clear | clear | 0 |
| 94.4795 / 94.3623 | 616.7,310.1,647.1,331.8 | 20.79 | 0.266 | unknown | clear | clear | 0 |
| 94.5166 / 94.4449 | 612.6,307.0,647.2,329.3 | 20.79 | 0.293 | 1.114 / 39.03 | L2 1 | L2 1 | 1 |
| 94.5573 / 94.4449 | 612.6,307.0,647.2,329.3 | 20.79 | 0.293 | 1.114 / 39.03 | L2 1 | L2 1 | 1 |
| 94.5920 / 94.5119 | 609.7,304.3,646.5,328.3 | 20.79 | 0.323 | 1.003 / 40.53 | L2 1 | L2 1 | 1 |
| 94.6264 / 94.5119 | 609.7,304.3,646.5,328.3 | 20.79 | 0.323 | 1.003 / 40.53 | L2 1 | L2 1 | 1 |
| 94.6607 / 94.5783 | 607.6,303.6,645.5,326.9 | 20.79 | 0.354 | 0.897 / 44.12 | L2 1 | L2 1 | 1 |
| 94.6998 / 94.6451 | 606.2,302.6,644.4,328.2 | 22.50 | 0.386 | 1.405 / 27.98 | L2 1 | L2 1 | 1 |
| 94.7354 / 94.6451 | 606.2,302.6,644.4,328.2 | 22.50 | 0.386 | 1.405 / 27.98 | L2 1 | L2 1 | 1 |
| 94.7707 / 94.6962 | 603.8,300.9,644.2,328.2 | 22.50 | 0.396 | 1.313 / 28.26 | L2 1 | L2 1 | 1 |
| 94.8079 / 94.6962 | 603.8,300.9,644.2,328.2 | 22.50 | 0.396 | 1.313 / 28.26 | L2 1 | L2 1 | 1 |
| 94.8455 / 94.7627 | 599.2,301.0,643.0,330.0 | 22.50 | 0.431 | 0.949 / 36.05 | L2 1 | L2 1 | 1 |
| 94.8873 / 94.8306 | 595.7,301.1,641.5,332.1 | 22.50 | 0.468 | 1.002 / 32.69 | clear | clear | 1 |
| 94.9279 / 94.8306 | 595.7,301.1,641.5,332.1 | 22.50 | 0.468 | 1.002 / 32.69 | clear | clear | 1 |
| 94.9676 / 94.9134 | 589.2,302.6,638.6,336.0 | 23.63 | 0.528 | 1.003 / 30.27 | clear | clear | 1 |
| 95.0037 / 94.9134 | 589.2,302.6,638.6,336.0 | 23.63 | 0.528 | 1.003 / 30.27 | clear | clear | 1 |
| 95.0437 / 94.9636 | 585.3,302.8,637.7,339.5 | 23.63 | 0.544 | 0.864 / 33.15 | clear | clear | 1 |
| 95.0787 / 94.9636 | 585.3,302.8,637.7,339.5 | 23.63 | 0.544 | 0.864 / 33.15 | clear | clear | 1 |
| 95.1187 / 95.0303 | 580.4,304.5,635.2,341.9 | 23.63 | 0.587 | 0.817 / 33.51 | clear | clear | 1 |
| 95.1521 / 95.0303 | 580.4,304.5,635.2,341.9 | 23.63 | 0.587 | 0.817 / 33.51 | clear | clear | 1 |
| 95.1872 / 95.1137 | 572.2,305.0,634.2,346.6 | 23.63 | 0.594 | 0.744 / 32.51 | pedal 0.990 | pedal 0.990 | 1 |
| 95.2206 / 95.1137 | 572.2,305.0,634.2,346.6 | 25.83 | 0.594 | 0.744 / 32.51 | pedal 0.990 | pedal 0.990 | 1 |
| 95.2603 / 95.1804 | 566.5,306.1,631.8,352.1 | 25.83 | 0.626 | 0.713 / 32.23 | pedal 0.939 | pedal 0.939 | 1 |
| 95.2941 / 95.1804 | 566.5,306.1,631.8,352.1 | 25.83 | 0.626 | 0.713 / 32.23 | pedal 0.939 | pedal 0.939 | 1 |
| 95.3354 / 95.2472 | 559.2,307.7,630.5,357.8 | 25.83 | 0.633 | 0.665 / 31.64 | pedal 0.857 | pedal 0.857 | 1 |
| 95.3793 / 95.2472 | 559.2,307.7,630.5,357.8 | 25.83 | 0.633 | 0.665 / 31.64 | pedal 0.857 | pedal 0.857 | 1 |
| 95.4148 / 95.3308 | 548.0,310.5,629.7,366.0 | 25.83 | 0.627 | 0.608 / 30.19 | pedal 0.745 | pedal 0.745 | 1 |
| 95.4537 / 95.3308 | 548.0,310.5,629.7,366.0 | 25.83 | 0.627 | 0.608 / 30.19 | pedal 0.745 | pedal 0.745 | 1 |
| 95.4940 / 95.4136 | 535.0,314.3,628.9,377.2 | 25.85 | 0.619 | 0.558 / 28.64 | pedal 0.645 | pedal 0.645 | 1 |
| 95.5378 / 95.4802 | 522.5,318.5,628.1,386.0 | 25.85 | 0.613 | 0.489 / 29.02 | pedal 0.569 | pedal 0.569 | 1 |
| 95.5787 / 95.4802 | 522.5,318.5,628.1,386.0 | 25.85 | 0.613 | 0.489 / 29.02 | pedal 0.569 | pedal 0.569 | 1 |
| 95.6188 / 95.5310 | 510.8,321.8,626.5,400.5 | 25.85 | 0.616 | 0.502 / 25.83 | pedal 0.517 | pedal 0.517 | 1 |
| 95.6533 / 95.5310 | 510.8,321.8,626.5,400.5 | 25.85 | 0.616 | 0.502 / 25.83 | pedal 0.517 | pedal 0.517 | 1 |
| 95.6878 / 95.6136 | 484.1,329.1,623.2,423.4 | 25.85 | 0.621 | 0.400 / 26.92 | pedal 0.425 | L2 1 queue | 1 |
| 95.7270 / 95.6136 | 484.1,329.1,623.2,423.4 | 25.85 | 0.621 | 0.400 / 26.92 | pedal 0.425 | L2 1 queue | 1 |
| 95.7630 / 95.6803 | 450.8,338.6,619.9,445.5 | 25.85 | 0.619 | 0.324 / 27.35 | pedal 0.345 | L2 1 queue | 1 |
| 95.8003 / 95.7476 | 423.7,328.6,588.4,446.5 | 25.85 | 0.814 | 0.311 / 29.31 | clear | L2 1 queue | 1 |
| 95.8373 / 95.7476 | 423.7,328.6,588.4,446.5 | 25.85 | 0.814 | 0.311 / 29.31 | clear | L2 1 queue | 1 |
| 95.8789 / 95.7978 | 412.8,328.6,570.2,446.6 | 25.85 | 0.943 | 0.306 / 31.15 | clear | L2 1 queue | 1 |
| 95.9195 / 95.8630 | 398.3,332.7,557.5,468.9 | 25.85 | 0.952 | 0.344 / 25.58 | clear | L2 1 queue | 1 |
| 95.9601 / 95.8630 | 398.3,332.7,557.5,468.9 | 25.85 | 0.952 | 0.344 / 25.58 | clear | L2 1 queue | 1 |
| 95.9966 / 95.9141 | 387.5,337.8,547.6,463.0 | 25.85 | 1.102 | 0.320 / 29.29 | clear | clear | 0 |
| 96.0374 / 95.9815 | 374.4,342.8,537.9,469.4 | 27.02 | 1.162 | 0.393 / 23.33 | clear | clear | 0 |
| 96.0800 / 95.9815 | 374.4,342.8,537.9,469.4 | 27.02 | 1.162 | 0.393 / 23.33 | clear | clear | 0 |
| 96.1135 / 96.0631 | 373.2,349.2,531.7,471.8 | 27.02 | 1.224 | 0.559 / 16.93 | clear | clear | 0 |
| 96.1526 / 96.0631 | 373.2,349.2,531.7,471.8 | 27.02 | 1.224 | 0.559 / 16.93 | clear | clear | 0 |
| 96.1857 / 96.0631 | 373.2,349.2,531.7,471.8 | 27.02 | 1.224 | 0.559 / 16.93 | clear | clear | 0 |


The implementation adds a confirmation timestamp and a held-stop bit to each existing track, plus an overlap predicate using the existing TRACK width allowance. It changes no threshold for starting L2. A track can gain the held-stop state only after the original law has already asked for full L2, own speed exceeds 5 m/s, and raw closing lies between own speed and the existing 2.5-times-own-speed bound continuously for at least 0.25 seconds of distinct capture time. For this recorded car the qualifying interval begins at capture 94.4449 and reaches 0.2513 seconds at capture 94.6962; the hold becomes active at tick 94.7707, before the narrow corridor fails. Reusing one detection cannot advance confirmation time. The ratio is evidence compatible with a stationary object, not a calibrated stationary-object classifier.

Once confirmed, the same fresh track retains full braking while its body overlaps the lane, even if a few fitted growth samples suggest a lead or GPS temporarily disappears. Already justified full braking also survives missing boxes only until the last actual box is 0.6 seconds old. A new lane offset is checked against the remembered overlap, so steering away still releases. Fresh evidence that the body leaves the overlap clears the state. L2 releases at or below 2 m/s, and the existing movement-false veto still applies. A nearby completed stop transfers into the existing queue state so the pedal remains released during the final coast; that state already releases when the gap opens. Low-speed initial approaches retain their existing behavior.

Each piece carries a necessary part of the failure. Holding only over missing detections cannot repair this continuously detected target. Merely preserving strength while applying the old entry corridor still releases at 94.8873. Widening the initial corridor would reintroduce brakes for unconfirmed adjacent/oncoming traffic. Holding every isolated full request adds long stops behind noisy lead fits; the quarter-second confirmation and raw closing condition keep P107's slower-lead release behavior. The 5 m/s entry bound preserves P107's existing near-rest uncertainty handling. Passing a completed close stop to the existing queue avoids reapplying throttle during its final coast. The change therefore adds state to an already justified stop rather than weakening the initial lane, oncoming or slower-lead filters.

The [new regression](../../pilot/tests/test_brake_held.py) replays the full recorded fixture and requires uninterrupted full L2 with zero R2 from 94.5166 through the last overlapping tick at 95.9601. It also repeats that requirement after deleting detections over capture 95.0–95.2, checks sustained misleading steady boxes, missing speed, bounded lost-box memory, release at rest or on lane exit, duplicate detections, and the transition from stopped waiting to following when the gap opens. `nice -n 15 pilot/.venv/bin/python lab/avoid/p109_red.py` temporarily substitutes HEAD's owned avoider and restores the working bytes in finally. Its [final baseline receipt](../../lab/avoid/p109-before-tests.txt) is `5 failed, 6 passed in 0.16s`: both recorded variants, the steady-box reclassification case, the missing-speed case and the completed-stop/no-creep case fail before this change.

No existing test assertion was changed. P106's queue and lorry first full-brake ticks remain exactly 272.2701 and 295.2243 seconds with zero R2. Its GPS-gap, wholly unknown-speed, partial-width, far-obstacle dynamics and negative stopping-margin assertions pass unchanged. P107's two opposite-lane fixtures still request no L2, its recorded slower lead still releases at 12.33 m/s, its proportional brake/steering case is unchanged, and its half-hidden queue still waits through the recorded GPS gap. The initial candidate exposed a low-speed queue timing regression and a final-coast regression; those were fixed in the owned avoider, not by changing the inherited test expectations. The [focused final receipt](../../lab/avoid/p109-focused-final.txt) is `129 passed in 3.46s` for the new tests plus the existing brake-with-a-reason, brake-for-the-lane, avoider, player-driving, drive-queue and round-what-stands suites.

The following table is any avoidance L2, not strength-integrated L2 and not all controller braking. Each denominator is unchanged follow/coast time. Run `PYTHONHASHSEED=0 nice -n 15 pilot/.venv/bin/python lab/avoid/p109_replay.py --trips` to reproduce the [summary](../../lab/avoid/p109-trip-replay.json), [console receipt](../../lab/avoid/p109-trip-replay.txt) and small compressed per-trip tick traces.

| Trip | Following s | P107 L2 s / percent | P109 L2 s / percent |
| --- | --- | --- | --- |
| 051709 | 137.026 | 9.284 / 6.775 | 9.749 / 7.115 |
| 052018 | 166.356 | 4.080 / 2.452 | 5.053 / 3.037 |
| 052402 | 134.225 | 5.777 / 4.304 | 6.116 / 4.556 |
| 052653 | 109.771 | 9.917 / 9.034 | 9.917 / 9.034 |
| 053655 | 154.037 | 11.072 / 7.188 | 11.110 / 7.212 |
| 054734 | 180.372 | 6.786 / 3.762 | 6.786 / 3.762 |
| 055349 | 143.563 | 7.044 / 4.907 | 7.472 / 5.205 |
| 055729 | 83.984 | 4.034 / 4.804 | 4.034 / 4.804 |
| Total | 1109.335 | 57.994 / 5.228 | 60.236 / 5.430 |

The frozen-source baseline is 0.110 seconds above the archived P107 report's 57.884 seconds. Seven trip totals reproduce exactly. The difference is confined to three ticks of 055729 at 81.3112, 81.3460 and 81.3837 on frame 19139, where this baseline requests L2 and the archived P107 trace does not. It lies in the “beside” class, and P109 does not alter it. The source versions and the discrepancy are retained in [the comparison evidence](../../lab/avoid/p109-comparison.json); the historical discrepancy is unresolved and is not attributed to this fix. The before/after increase compares the two fresh runs with identical inputs, so it remains 2.242 seconds / 0.202 percentage points. P106 replays at its archived 64.566 seconds. Strength-integrated P107/P109 exposure is separately 48.991/51.290 full-L2-equivalent seconds.

The 170 originally reviewed live onsets remain the scene-label reference, with P107's supplemental labels and the same overlap/0.75-second association rule. The [evidence script](../../lab/avoid/p109_evidence.py) preserves all changed intervals. Event labels describe the recorded scene; they cannot prove that an extended counterfactual stop is necessary.

| Reviewed P107 class | Before onsets / L2 s | After onsets / L2 s | Change s |
| --- | --- | --- | --- |
| standing | 36 / 11.850 | 36 / 12.315 | 0.465 |
| slower | 42 / 11.141 | 40 / 12.542 | 1.400 |
| oncoming | 17 / 5.170 | 17 / 5.547 | 0.376 |
| crossing | 45 / 20.048 | 45 / 20.048 | 0.000 |
| beside | 17 / 4.728 | 17 / 4.728 | 0.000 |
| nothing | 21 / 5.056 | 21 / 5.056 | 0.000 |

All added any-L2 time is in these six extensions; there are no added onset events, and two pairs of existing pulses join. “Nothing”, “beside” and crossing time do not grow. Standing grows by 0.465 seconds; slower-lead scenes grow by 1.400 seconds and oncoming scenes by 0.376 seconds. The latter are the existing own-car-turn-toward-opposing-traffic scene and the own-car head-on-contact scene, not either bend regression. Conservatively counting every added non-standing interval as unproved/unwanted costs 1.777 seconds, 0.160 percentage points of following time; even counting every added interval as unwanted is only 0.202 points. This does not excuse the pre-existing false brakes or assert that the lead extensions are beneficial.

| Trip | Added interval s | L2 s | Reviewed onset class |
| --- | --- | --- | --- |
| 051709 | 88.2139–88.6793 | 0.465 | standing |
| 052018 | 94.6971–94.8136 | 0.117 | slower |
| 052018 | 125.2373–126.0936 | 0.856 | slower |
| 052402 | 149.5222–149.8608 | 0.339 | oncoming |
| 053655 | 418.2373–418.2750 | 0.038 | oncoming |
| 055349 | 193.5124–193.9399 | 0.428 | slower |

The final package gate ran once as `cd pilot && nice -n 15 .venv/bin/python tools/gate.py`. Ruff check and format check passed, and all functional tests passed. The [gate receipt](../../lab/avoid/p109-gate.txt) ends with:

```text
3884 passed, 1 skipped, 1376 deselected, 1 xfailed in 130.45s (0:02:10)
gate passed in 130.89s (default)
default gate exceeded 90 seconds
```

The process exits 1 solely because of the card's known 90-second runtime budget under load. This is not an unqualified green gate. The intermittent silent-server test did not fail and was not rerun. The diagnostic JPEG remains uncommitted and must be excluded from any later commit. The fixture, raw boxes and traces are small text/compressed data; no recording was copied.

Open-loop replay shows requests on fixed pictures, not stopping distance or avoidance of this collision. Changed braking would change subsequent speed, camera pose, steering, detections and track associations. The recorded post-brake GPS values still rise above 25 m/s because they belong to the original drive and lag the motion. A frame-selected, fixed-delay reconstruction cannot prove the original asynchronous reader's exact decisions, and the inferred unmodified steering and movement assumption remain limitations. The overlap model, approximate camera scale, type voting and closing fit can still be wrong. The next comparable town trips must count video-confirmed rear-end contacts above 5 m/s, any avoider L2 divided by follow/coast time, and avoider onsets per following minute. Console acceptance and collision prevention remain unverified; no live run is authorized in this card.
