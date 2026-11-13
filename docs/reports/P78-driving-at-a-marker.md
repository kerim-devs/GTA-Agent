# P78: driving at a marker

The isolated `DriveToBlip` skill is implemented in `pilot/src/pilot/pursuit.py`. Registration and mission planning are left to the reviewer as the card requires. Verification used local recordings and simulation. Existing controller files remain unchanged; no live console, daemon, credentials or Git write was used. The scoped implementation, simulation and replay checks are complete, but the card is not fully accepted: the final gate fails because the shared benchmark cause registry lacks two new P78 terminal reasons.

## What was built

The arguments are `color` (blue/red/yellow), `mode` (reach/follow/catch), and a clamped 1-300 second duration. The class follows the new-skill contract and emits a complete buttonless pad on every tick. Every terminal result is neutral and remains terminal. It consumes `Driver.step`, `Avoider`, `waits_behind`, `terrain.read`, and the existing angle/route helpers without changing those modules.

The skill smooths the marker bearing on the circle, retains it for at most two seconds when the marker is obscured or the map is damaged, releases the pedal afterwards, and fails `blip-gone` after five seconds without a matching color. It selects a road within 45 degrees of the target bearing when available, chooses a dry heading near water, and also brakes for water on the car's current course. Detected traffic is passed through the existing avoider. A marker continuously behind the car for more than one second is handed to the driver's turn. Actual held motion uses the driver's recovery sequence and latch; deliberately waiting behind a close target does not masquerade as a failed recovery.

A rim marker is far. An interior marker uses distance and the rate of distance change to regulate following. Reach slows on approach, brakes without holding reverse after the stop, and requires a fresh marker under the arrow for half a second with explicit stopped-motion evidence throughout that interval. Follow and catch never report arrival; their ordinary terminal is the time limit. Foot, screen and water failures require persistent evidence and return neutral during the uncertain interval. A corrupted flat map does not prove the driver got out. Unknown motion resets the arrival dwell. If every sampled water-avoidance heading stays blocked for four seconds, the skill fails neutral with `vehicle-held`; a dry escape resets that deadline.

## Human evidence and decisions

The first inspection, before implementation, used the objective steps in `missions.json`, their associated `actions.jsonl`, and raw controller states. The initial yacht sample was a blue marker 27.5 pixels ahead. The van samples placed red components approximately 16-33 pixels ahead. The resulting target is 27 map pixels with a wanted band of 16-40 pixels. This band was chosen before the simulator measurements. A pixel is not a metre: the simulator changes map scale with speed.

The table includes every candidate with some labelled vehicle driving, a visible objective, no route, and a blue/red/yellow marker in the step's example observation. `step.blips` is empty in these labels; `sample_observation.blips` carries the actual examples. The table distinguishes pursuit evidence from wait, combat and enter-vehicle boundaries. OCR wording is preserved rather than silently corrected. The extra 150-210 second motorbike chase is explicitly required by the card but has no objective label during that window.

Near/far values below are measured marker-distance percentiles over recorded frames, not the single metadata example. Rim means pinned to the minimap border. R2/L2 are time-weighted raw human pad means. The speed columns are median radar-image motion in pixels per second when R2 is at least .9 or at most .1. They are a visual proxy, affected by turns and map zoom, and cannot establish road speed in km/h. Missing samples are shown as unavailable.

The van's raw pad spends substantial time with R2 released, supporting speed modulation rather than a fixed pedal. In the yacht sample the human largely holds course even while the marker is to one side. Together these observations support following a road near the bearing instead of steering directly at every jittering icon. Red target icons can split into two reader components; neither the table nor the implementation treats those as two confirmed vehicles. With multiple same-color actors the skill keeps the nearest bearing, but has no actor identity beyond color and geometry.

| Recording / seconds | Objective (OCR) and context | Color; marker px p10/median/p90; rim | R2 / L2 mean; radar motion gas/coast | Ending in labels; replay end | Clear turns same/compared |
| --- | --- | --- | --- | --- | --- |
| 20261111-165543<br>222.570-284.502 (61.9s) | Warte auf Tonya. (boundary: mixed context) | blue; 18.9/79.5/87.0; 6% | 0.27/0.03; 9.5/1.0 px/s | unknown; still running | 265/475 |
| 20261111-171046<br>329.012-391.001 (62.0s) | Steig wieder in den Lieferwagen. (boundary: mixed context) | blue; 4.5/5.4/11.2; 3% | 0.79/0.01; 11.0/12.9 px/s | unknown; on-foot at 331.10s | 0/0 |
| 20261111-180814<br>311.005-376.034 (65.0s) | Bring Franklin nahe an die Yacht. (pursuit/reach evidence) | blue; 14.7/21.7/37.8; 1% | 0.79/0.00; 16.4/20.6 px/s | unknown; blip-gone at 327.99s | 0/0 |
| 20261111-180814<br>394.002-456.005 (62.0s) | Verfolge die Yacht. (pursuit/reach evidence) | blue; 13.0/20.2/27.5; 0% | 0.78/0.01; 16.8/15.7 px/s | unknown; blip-gone at 422.58s | 1/1 |
| 20261111-185323<br>774.502-841.009 (66.5s) | Kehr zurück zu Lamar und Stretch. (boundary: mixed context) | blue; 12.6/34.9/92.2; 14% | 0.48/0.11; 10.2/3.4 px/s | unknown; on-foot at 775.53s | 0/0 |
| 20261111-201615<br>448.003-508.003 (60.0s) | Mach dlch auf zur K8nBlmündung. (boundary: mixed context) | red; 14.6/23.8/35.0; 32% | 0.92/0.02; 9.2/11.3 px/s | unknown; water at 452.23s | 0/0 |
| 20261111-212314<br>73.507-116.004 (42.5s) | Begib dlch zum Juweller. (boundary: low vehicle coverage) | yellow; 7.5/31.7/38.2; 0% | 0.00/0.00; unavailable/3.2 px/s | next objective; on-foot at 76.51s | 0/114 |
| 20261112-090514<br>207.006-265.013 (58.0s) | Halte die V"vtJi5 Iv auf. (boundary: low vehicle coverage) | blue; 5.1/19.5/53.2; 4% | 0.05/0.03; 6.4/5.9 px/s | next objective; on-foot at 210.93s | 6/8 |
| 20261112-090514<br>524.002-591.039 (67.0s) | Schalte dle Cops aus, bevor du den Treffpunkt erreichst. (boundary: mixed context) | yellow; 38.5/86.6/110.8; 51% | 0.73/0.00; 7.7/8.0 px/s | next objective; blip-gone at 581.90s | 773/946 |
| 20261112-092019<br>404.008-408.035 (4.0s) | Folge dem Lleferwagen. (pursuit/reach evidence) | red; 15.4/23.1/29.9; 0% | 1.00/0.00; 10.9/unavailable px/s | next objective; still running | 0/0 |
| 20261112-092019<br>408.035-468.035 (60.0s) | Folge dem l_ieferwagen. (pursuit/reach evidence) | red; 11.4/20.0/31.2; 0% | 0.72/0.01; 9.9/8.2 px/s | unknown; blip-gone at 444.73s | 29/32 |
| 20261112-130333<br>691.509-758.016 (66.5s) | Schalte den Biker aus. (catch with combat) | red; 52.8/73.7/88.6; 40% | 0.02/1.00; 0.0/0.0 px/s | unknown; blip-gone at 703.21s | 0/0 |
| 20261112-130333<br>962.510-1029.001 (66.5s) | Schalte den Biker aus. (catch with combat) | red; 53.2/63.6/87.8; 36% | 0.01/0.94; 0.0/0.0 px/s | unknown; blip-gone at 974.49s | 0/0 |
| 20261112-130333<br>1637.014-1668.014 (31.0s) | Bring mlch zu melnem Flugzeug, Ronl (boundary: low vehicle coverage) | red; 24.0/38.0/89.9; 13% | 0.46/0.48; 2.5/2.5 px/s | failed; on-foot at 1638.01s | 0/0 |
| 20261112-130333<br>1690.502-1751.017 (60.5s) | Brlng mlch zu diesem Flugzeug. (boundary: low vehicle coverage) | blue; 3.9/4.6/5.3; 3% | 0.58/0.00; 2.1/2.7 px/s | unknown; on-foot at 1691.51s | 0/0 |
| 20261113-031159<br>940.018-1003.509 (63.5s) | Zerstöre das Meth-Labor der O'Neils. (boundary: mixed context) | red; 26.6/42.5/54.3; 0% | 0.02/0.82; 0.0/0.0 px/s | unknown; blip-gone at 992.12s | 0/0 |
| 20261113-035200<br>1173.505-1200.200 (26.7s) | Steig in den Laster. (boundary: mixed context) | blue; 4.5/5.3/6.0; 4% | 0.70/0.01; 8.6/8.0 px/s | unknown; on-foot at 1174.72s | 0/0 |
| 20261113-041201<br>1041.513-1083.504 (42.0s) | Stelg In den Frachtlader. (boundary: mixed context) | blue; 3.5/4.6/98.6; 12% | 0.57/0.06; 8.1/1.7 px/s | next objective; on-foot at 1042.53s | 0/0 |
| 20261113-043201<br>30.006-95.512 (65.5s) | Beglb dich zum Kran. (boundary: mixed context) | yellow; 8.7/13.4/48.6; 0% | 0.53/0.06; 5.3/2.3 px/s | unknown; on-foot at 64.35s | 120/612 |
| 20261110-093238<br>150.000-210.000 (60.0s) | Unlabelled motorbike chase (task reference) (historical chase, no objective label) | blue; 22.4/69.7/104.3; 26% | 0.65/0.05; unavailable/unavailable px/s | unlabelled; screen-phone at 154.84s | 23/23 |

The separate 1637.014-1668.014 second airplane request in 20261112-130333 ends in mission failure because the ally died, with the banner event at 1667.894. That is not the outcome of either earlier biker chase. A labelled unknown ending remains unknown. Later death banners outside a listed interval are not attributed to that interval. A replay terminal is the skill's decision on recorded inputs, not evidence that the human failed the mission.

## Simulation

`pilot/tests/test_pursuit_worlds.py` imports `Car`, `World`, `Run.objects`, `render`, and the geometry helpers from `test_getaway.py`. The second car follows a polyline, turns, drives at traffic speed, flees at a speed matchable by every profile, and pauses twice. The follower starts 19 metres behind; the fleeing target starts 60 metres away. Reach starts 300 metres from a stationary marker on a straight road crossing junctions at 100 and 200 metres. The acceptance check requires crossing both junctions. The moving-target cases instead turn at two junctions. These are local bearing-following tests, not proof of graph route planning.

The simulation supplies geometric marker readings, as the P68 worlds do, while drawing the marker and terrain in the HUD. It does not model every real reader error. Separate contract tests cover occlusion, corruption, color loss and mode errors. Water, a wall requiring recovery, and detected moving traffic are additional scenarios for every car profile. Each main scenario runs for a minute or until observed arrival; the safety scenarios run for 30 seconds. All stationary intervals below .5 m/s count toward the held metric, including braking, reverse transitions and waiting. The follow checks also reject any crossing of the target's along-road progress. Catch means centre distance within 10 metres, representing two five-metre car lengths.

The first complete matrix used 14 m roads at every junction. It failed 14 of 66 cases. Traces exposed two causes: the unchanged terrain reader classified some wide bright junctions as water, and a full arrival brake could skip the stopped-motion observation and engage reverse on strong-braking profiles. The complete negative receipt is preserved in `lab/pursuit/wide-junction-simulation.json`, its metadata and log. The final fixture uses the existing P68 main-road width of 12 m, also for its crossings. The arrival trigger was separately limited to .25 and now requires an explicit stopped observation continuously for .5 seconds. This is a declared geometry constraint: broad-junction classification remains an upstream limitation, and the skill does not weaken water avoidance to pass it.

| Profile | Follow in band | Catch first <=10 m | Catch close share | Reach time | Reach gap | Stop speed | Longest held |
|---|---:|---:|---:|---:|---:|---:|---:|
| nominal | 100.0% | 13.4 s | 44.5% | 36.0 s | 3.65 m | 0.150 m/s | 3.2 s |
| range-00 | 100.0% | 31.5 s | 40.3% | 51.4 s | 3.80 m | 0.234 m/s | 2.4 s |
| range-01 | 100.0% | 13.4 s | 42.8% | 36.0 s | 3.65 m | 0.150 m/s | 3.2 s |
| range-02 | 100.0% | 9.0 s | 9.7% | 29.4 s | 3.45 m | 0.011 m/s | 3.1 s |
| range-10 | 100.0% | 30.6 s | 49.0% | 50.8 s | 4.35 m | 0.180 m/s | 2.4 s |
| range-11 | 100.0% | 16.2 s | 59.3% | 42.4 s | 4.84 m | 0.038 m/s | 2.4 s |
| range-12 | 100.0% | 7.9 s | 16.2% | 28.4 s | 1.27 m | 0.236 m/s | 4.0 s |
| range-20 | 100.0% | 39.2 s | 34.7% | 50.6 s | 4.68 m | 0.036 m/s | 2.4 s |
| range-21 | 100.0% | 13.4 s | 51.7% | 36.8 s | 2.73 m | 0.239 m/s | 3.6 s |
| range-22 | 100.0% | 14.8 s | 62.2% | 40.7 s | 2.85 m | 0.147 m/s | 4.5 s |
| fast-low-grip | 100.0% | 7.9 s | 12.3% | 27.6 s | 1.42 m | 0.238 m/s | 4.0 s |

All 66 final cases passed. Every follow stayed behind the target and retained it. Every reach crossed both junctions and ended `done/reached` with stopped-motion evidence. No case entered the physical water polygon or emitted a button. The close-share column measures the fraction of the complete catch minute spent within two car lengths, including the initial chase; catching once does not imply permanent tailgating. `simulation-meta.json` binds the final receipt to the controller, world harness, simulator and runner source digest.

## Recorded replay

`lab/pursuit/scripts/replay.py` decodes sequentially against the exact `frames.jsonl` indices. It runs the minimap reader on every selected frame, reads the HUD, and computes motion from crop history using the P68 .2 second comparison with a longer fallback. Where existing `judge.json` annotations are available, including the primary yacht, van and biker recordings, it supplies the latest mode at or before the frame index, never a future annotation. Those sparse visual labels are context, not a new live model call.

An initial replay omitted that mode context and falsely inferred foot from a flat vehicle map. The final replay recomputes every recording with the final controller and the available causal mode context. Each summary records `causal-judge` or `minimap-fallback`; traces without annotations, including the historical motorcycle recording, retain the inference limitation. `replay-meta.json` records source digests and completion of all fourteen recording shards. Every full interval is decoded, but a terminated skill is not silently restarted or counted as still steering.

The P68 comparison uses the human left-stick integral over frame time +.2 to +1.5 seconds. A clear human turn has magnitude at least .15; a compared skill turn has a relative heading magnitude of at least 30 degrees. The frozen P68 report records 104 same-direction and 88 opposite-direction turns, or 54.17% among 192 clear comparisons. Its other 149 turns had no clear human steering and are outside this denominator. The newer P73 temporary baseline has different counts and is not substituted for P68.

All 20 candidate intervals were decoded, totaling 62,879 recorded frames. Across all candidates, 1,217 of 2,211 compared clear turns agree (55.04%), compared with P68's 104 of 192 (54.17%). This clears the requested comparison but is only a narrow margin and mixes the documented boundary contexts.

For the six objective-qualified yacht, van and biker intervals, agreement is 30 of 33 compared turns (90.91%). Of these, 29 of 32 are from the main van-follow interval and one is from the yacht. The reach and biker intervals contain no qualifying large-heading/clear-human turns; they cannot support a separate catch-heading claim. Without the 30-degree skill-heading cutoff, 531 of 838 human-clear frames have the same heading sign (63.37%). Only 3,109 of 19,402 frames in these six intervals qualify as clean, vehicle, no-route, marker-visible, still-running evidence. These temporally adjacent frames are not independent trials.

The corrected yacht reach ends `blip-gone` at 327.989 seconds, yacht follow at 422.581, the main van follow at 444.734, and the two biker runs at 703.213 and 974.494. The short van lead-in runs to its labelled endpoint. Thus this replay validates the measured heading comparison, but also exposes substantial marker-reader dropout. It does not demonstrate sustained pursuit in those recorded missions. The historical unannotated motorcycle comparison is 23/23 (100%) and stops `screen-phone` at 154.839; its unavailable mode context is a separate limitation and it is not included in the six-interval primary result.

A replay never responds to this skill's pad. Agreement establishes a plausible heading on the compared frames, not successful driving, distance keeping, obstacle avoidance, or mission completion on the console.

## Commands and evidence

All commands run from `pilot/` unless stated otherwise. The changed-file command is `.venv/bin/pytest -q tests/test_pursuit.py tests/test_pursuit_worlds.py`. The final 47 contract cases include unknown-motion arrival, persistent all-direction water blockage, and reset of that blockage deadline after a dry escape. The full profile acceptance matrix is `.venv/bin/python ../lab/pursuit/scripts/simulate.py`; its per-case checkpoint and source digest allow interrupted work to resume without duplicating finished cases. The repository's 90-second default gate retains three representative world runs and the safety smoke; the complete profile matrix is a separately asserted acceptance run, not silently deselected tests or a modification of `conftest.py`.

The replay command is `.venv/bin/python ../lab/pursuit/scripts/replay.py`; completed recording shards are retained, and only a missing or explicitly invalid primary context is recomputed. `.venv/bin/python ../lab/pursuit/scripts/tables.py` builds the human table from those receipts without decoding videos again.

Before the restart, the unchanged baseline gate ended with `9 failed, 2772 passed, 3 skipped, 1376 deselected, 4 xfailed, 6 errors in 560.70s`. Its failures included sandbox-denied loopback servers and CoreML temporary-directory creation, plus a timing assertion on the overloaded shared machine. These are baseline observations, not P78 results. After the restart, only changed-file checks run during development, followed by one final full gate with the local permissions required by those existing tests.

The final contract run passed: `47 passed in 0.26s`. The changed-file world checks passed during development, and the final source-bound acceptance matrix passed all 66 main and safety cases. The final replay completed all fourteen recordings and all twenty intervals in 625.9 seconds. Its comparison is 55.04% against the frozen P68 54.17%; the six primary intervals separately score 90.91%. Ruff check and format passed for the owned source and tests using the configuration from `pilot/`.

The full gate was run exactly once after the restart, at the end, with local sandbox restrictions lifted for the existing loopback/CoreML tests and `OPENCV_FOR_THREADS_NUM`, `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS` and `VECLIB_MAXIMUM_THREADS` each set to `1`. Its output was `All checks passed!`, `171 files already formatted`, then `1 failed, 2839 passed, 1 skipped, 1376 deselected, 4 xfailed in 175.96s`. The wrapper recorded exit code 1 and 176.8 seconds in `lab/pursuit/gate-meta.json`; the full output is in `lab/pursuit/gate.log.gz`. That elapsed time also exceeds the default gate's 90-second budget, so there is no timing pass to claim.

The sole failure is `tests/test_bench.py::test_every_reason_a_skill_can_end_on_has_a_rule` at line 559. Its scan discovers `invalid-time` and `reached` in the new skill and requests rules in `bench.CAUSE_RULES`. This is a P78 integration gap, not an unrelated baseline failure. The reviewer must add those cause explanations in `pilot/src/pilot/bench.py:522` (`CAUSE_RULES`) and rerun the gate after integration; `reached` is the card's required success reason, while `invalid-time` reports a rejected observation clock. No test was disabled and no reason was hidden from the scan.

That registry is outside this card's allowed write set. `docs/tasks/README.md:5` is explicit: “If you need something from a file that is not yours, say so in your report instead of editing it.” The allowed set is in `docs/tasks/P78-driving-at-a-marker.md:25`. The decision is to leave the shared registry unchanged and hand off this concrete integration dependency. Consequently, the card's “The gate passes in pilot/” condition remains unmet. No second full gate or duplicate long-running job was started.

## Remaining evidence

The reviewer still needs to integrate the class and benchmark cause rules, reconcile P73's caller interfaces, obtain a passing full gate and run a supervised console mission that says follow. No console or production success is claimed. Minimap pixels do not yield a fixed real-world gap; multiple matching actors and fragmented target icons remain identity ambiguities. Actual map-reader availability and mode annotations matter even when the steering comparison is good.
