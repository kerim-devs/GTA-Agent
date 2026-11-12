P60 is blocked, not complete. The recorded death-to-seat error is repaired and covered by offline regressions. The new roadside questions remain laboratory-only: the best whole-frame 8B wording reaches 90.44% carriageway-versus-rest accuracy but falsely calls 20 of 101 carriageway frames safe (19.80%, against a 5% limit). The full test gate also has two unrelated failures because PyAV is absent and installation is outside this card. No console action was taken.

The corpus is in `lab/where/frames.json`, `vehicles.json`, `labels.json` and the numbered JPEG contact sheets. It contains 360 reviewed foot candidates, of which 251 are usable: 101 carriageway, 43 roadside, 77 open ground/yard and 30 inside. The other 109 are explicitly excluded. The requested roughly 300 usable foot examples were not reached. `label-review.json` records 56 corrected codes from a second visual check, including wrongly labelled roadway frames, cutscenes and obscured supporting surfaces. Asphalt gutters on the road side of a raised kerb count as carriageway; raised kerbs and sidewalks count as roadside. The review happened after exploratory measurements, so these are development labels, not blinded validation. Ten 12 November Kerim section manifests and three current pilot sessions supply daylight, night, town, country, interiors, first-person and several third-person camera views. The first-person hillside samples are open ground. Source recording paths, capture times and exact video frame indices are retained. Samples are clustered within recordings, not an independent held-out population. The current labels.json is authoritative for scoring; raw answer logs retain their original label-at-run for provenance.

The vehicle corpus contains 216 reviewed detector boxes from the existing P57 fresh-detection pool, with 171 usable labels: 89 driving, 49 stopped traffic/occupied, and 33 visibly parked candidates. Forty-five ambiguous boxes are excluded. Review compared the source frame with frames 0.75 seconds before and after. The 33 parked labels do not prove an invisible driver's seat empty; they are candidate labels, not a certified empty-vehicle positive set. This limitation prevents a parked-empty success claim even when the traffic-to-parked rejection metric passes. The requested roughly 200 fully classifiable vehicle examples were therefore not obtained.

Capture time is resolved through `frames.jsonl` to its `i` index before decoding. In Kerim 20261112-092019, capture time reaches 901.9294 seconds while video media duration is only 873.05 seconds. Seeking directly by media seconds would silently label the wrong images. The original recordings were only read.

`judge.WHERE_QUESTIONS`, `ask_where` and `parse_where` contain the exact measured prompts and strict answer parsing. The existing six-question `JOINT` and asynchronous runtime `Reader` are unchanged. `whole` uses the entire image resized to width 640; foot `crop` uses x=15..85%, y=25..100%; vehicle crops pad the detected box by 80% of its dimensions, at least 8% of the image, and retain a red target rectangle. Foot pairs ask position plus edge; vehicle pairs ask vehicle state plus position. The plain variants use a second, shorter wording. Prompts, replies, conditional token probabilities, capture times and response durations are preserved. Malformed replies count as errors, not correct abstentions.

Both models ran only at the authorized PC endpoint `192.168.0.248:1234`. The 4B run is a smaller-model comparison on that PC, not a Mac fallback test. `judge.py` has configurable ordered servers but no bundled Mac model or configured Mac endpoint. The card permits network only to the PC, so Mac fallback behavior and Mac latency remain unverified. Request timings are wall-clock request durations; measurement streams sometimes ran concurrently, and video decoding time is excluded.

Carriageway results follow. The binary score counts an unknown or malformed answer as incorrect. False-safe means a true carriageway image called roadside, open ground or inside; its denominator is all 101 carriageway images.

| Model / variant | Frames | Binary correct | False-safe | Format errors | Median / p95 seconds |
|---|---:|---:|---:|---:|---:|
| 4b whole-plain-single | 251 | 66.14% | 17/101 (16.83%) | 22 | 0.212 / 0.357 |
| 4b crop-plain-single | 251 | 62.95% | 21/101 (20.79%) | 21 | 0.214 / 0.372 |
| 4b whole-pair | 251 | 58.96% | 74/101 (73.27%) | 29 | 0.171 / 0.321 |
| 8b whole-single | 251 | 59.76% | 101/101 (100.00%) | 0 | 0.226 / 0.343 |
| 8b whole-pair | 251 | 59.76% | 101/101 (100.00%) | 0 | 0.148 / 0.294 |
| 8b crop-single | 251 | 60.96% | 98/101 (97.03%) | 0 | 0.226 / 0.342 |
| 8b crop-pair | 251 | 60.56% | 99/101 (98.02%) | 0 | 0.166 / 0.304 |
| 8b whole-plain-single | 251 | 90.44% | 20/101 (19.80%) | 0 | 0.252 / 0.375 |
| 8b crop-plain-single | 251 | 90.04% | 18/101 (17.82%) | 0 | 0.253 / 0.382 |

The short 8B whole-frame wording clears the 90% binary mark by 0.44 percentage points but misses the false-safe limit by 14.80 points. All 20 carriageway mistakes are roadside answers: 13 are in 20261112-111357, including the underpass and highway; five are in 105402, including kerbside gutters; one is in 085011; and one is the onset of walking in the road at 22 seconds in 143714. The corresponding crop reaches 90.04% binary accuracy but still falsely calls 18/101 carriageway images safe (17.82%), missing the safety limit by 12.82 points. The smaller 4B whole/plain variant reaches only 66.14% binary accuracy and 16.83% false-safe, missing the respective marks by 23.86 and 11.83 points. The original wording fails much more severely. Confidence thresholding is not a repair: some wrong roadside answers have probability at least 0.95.

Vehicle results follow. The safety denominator is the 138 traffic/driving labels; overall accuracy includes the weaker parked-candidate labels. Passing this negative metric does not establish a reliable empty-seat detector or safe crossing behavior.

| Model / variant | Boxes | Class correct | Traffic called parked | Format errors | Median / p95 seconds |
|---|---:|---:|---:|---:|---:|
| 4b crop-single | 171 | 39.77% | 22/138 (15.94%) | 0 | 0.223 / 0.371 |
| 8b whole-single | 171 | 42.11% | 9/138 (6.52%) | 0 | 0.229 / 0.345 |
| 8b whole-pair | 171 | 43.27% | 12/138 (8.70%) | 0 | 0.184 / 0.296 |
| 8b crop-single | 171 | 46.78% | 5/138 (3.62%) | 0 | 0.235 / 0.365 |
| 8b crop-pair | 171 | 43.27% | 8/138 (5.80%) | 0 | 0.168 / 0.306 |
| 8b whole-plain-single | 171 | 43.27% | 19/138 (13.77%) | 0 | 0.231 / 0.374 |
| 8b crop-plain-single | 171 | 47.95% | 13/138 (9.42%) | 0 | 0.229 / 0.358 |

The original 8B crop/single vehicle question passes the negative mark at 5/138, or 3.62%, but its overall three-class accuracy is 46.78%. The smaller 4B model falsely calls 22/138 traffic vehicles parked, 15.94%, missing the limit by 5.94 points. A visible driver, temporal motion relative to the road, lane/stop-line geometry, and a stable vehicle track are more defensible complementary signals than a missing person box. Parked-empty positive labels need an observable empty seat or a continuous exit/entry sequence without another occupant.

Edge results use 40 visually directional labels and 211 unknown labels. Unknown includes off-road positions and genuinely ambiguous edges. It is a separate qualification problem; high accuracy from answering unknown is not evidence of usable steering.

| Model / variant | Frames | All labels correct | Directional labels correct | Format errors | Median / p95 seconds |
|---|---:|---:|---:|---:|---:|
| 4b whole-pair | 251 | 74.10% | 14/40 | 29 | 0.171 / 0.321 |
| 8b whole-pair | 251 | 21.91% | 25/40 | 0 | 0.148 / 0.294 |
| 8b crop-pair | 251 | 32.27% | 28/40 | 0 | 0.166 / 0.304 |

Complete confusion counts follow, with one row per ground-truth class. C/S/O/I mean carriageway/roadside/open/inside; P/T/D mean parked-candidate/traffic/driving. U is model abstention and E is malformed response. Vehicle and edge matrices use their own explicitly named columns.

| where: model / variant | Actual | carriageway | roadside | open | inside | unknown | error |
|---|---|---:|---:|---:|---:|---:|---:|
| 4b whole-plain-single | carriageway | 81 | 17 | 0 | 0 | 3 | 0 |
| 4b whole-plain-single | open | 0 | 0 | 47 | 0 | 27 | 3 |
| 4b whole-plain-single | inside | 0 | 0 | 0 | 3 | 8 | 19 |
| 4b whole-plain-single | roadside | 0 | 35 | 0 | 0 | 8 | 0 |
| 4b crop-plain-single | carriageway | 79 | 20 | 1 | 0 | 1 | 0 |
| 4b crop-plain-single | open | 0 | 0 | 42 | 0 | 33 | 2 |
| 4b crop-plain-single | inside | 0 | 0 | 1 | 3 | 7 | 19 |
| 4b crop-plain-single | roadside | 1 | 33 | 0 | 0 | 9 | 0 |
| 4b whole-pair | carriageway | 0 | 74 | 0 | 0 | 0 | 27 |
| 4b whole-pair | open | 0 | 6 | 71 | 0 | 0 | 0 |
| 4b whole-pair | inside | 0 | 2 | 0 | 28 | 0 | 0 |
| 4b whole-pair | roadside | 0 | 41 | 0 | 0 | 0 | 2 |
| 8b whole-single | carriageway | 0 | 101 | 0 | 0 | 0 | 0 |
| 8b whole-single | open | 0 | 5 | 72 | 0 | 0 | 0 |
| 8b whole-single | inside | 0 | 0 | 0 | 30 | 0 | 0 |
| 8b whole-single | roadside | 0 | 43 | 0 | 0 | 0 | 0 |
| 8b whole-pair | carriageway | 0 | 101 | 0 | 0 | 0 | 0 |
| 8b whole-pair | open | 0 | 5 | 72 | 0 | 0 | 0 |
| 8b whole-pair | inside | 0 | 0 | 0 | 30 | 0 | 0 |
| 8b whole-pair | roadside | 0 | 43 | 0 | 0 | 0 | 0 |
| 8b crop-single | carriageway | 3 | 98 | 0 | 0 | 0 | 0 |
| 8b crop-single | open | 0 | 5 | 72 | 0 | 0 | 0 |
| 8b crop-single | inside | 0 | 4 | 0 | 26 | 0 | 0 |
| 8b crop-single | roadside | 0 | 42 | 1 | 0 | 0 | 0 |
| 8b crop-pair | carriageway | 2 | 99 | 0 | 0 | 0 | 0 |
| 8b crop-pair | open | 0 | 5 | 72 | 0 | 0 | 0 |
| 8b crop-pair | inside | 0 | 1 | 0 | 29 | 0 | 0 |
| 8b crop-pair | roadside | 0 | 42 | 1 | 0 | 0 | 0 |
| 8b whole-plain-single | carriageway | 81 | 20 | 0 | 0 | 0 | 0 |
| 8b whole-plain-single | open | 3 | 9 | 64 | 0 | 1 | 0 |
| 8b whole-plain-single | inside | 0 | 0 | 0 | 30 | 0 | 0 |
| 8b whole-plain-single | roadside | 0 | 42 | 1 | 0 | 0 | 0 |
| 8b crop-plain-single | carriageway | 82 | 18 | 0 | 0 | 1 | 0 |
| 8b crop-plain-single | open | 1 | 6 | 66 | 0 | 4 | 0 |
| 8b crop-plain-single | inside | 0 | 1 | 0 | 28 | 1 | 0 |
| 8b crop-plain-single | roadside | 0 | 41 | 2 | 0 | 0 | 0 |
| vehicle: model / variant | Actual | parked | traffic | driving | unknown | error |
|---|---|---:|---:|---:|---:|---:|
| 4b crop-single | driving | 10 | 78 | 1 | 0 | 0 |
| 4b crop-single | parked | 30 | 3 | 0 | 0 | 0 |
| 4b crop-single | traffic | 12 | 37 | 0 | 0 | 0 |
| 8b whole-single | driving | 4 | 85 | 0 | 0 | 0 |
| 8b whole-single | parked | 28 | 5 | 0 | 0 | 0 |
| 8b whole-single | traffic | 5 | 44 | 0 | 0 | 0 |
| 8b whole-pair | driving | 7 | 82 | 0 | 0 | 0 |
| 8b whole-pair | parked | 30 | 3 | 0 | 0 | 0 |
| 8b whole-pair | traffic | 5 | 44 | 0 | 0 | 0 |
| 8b crop-single | driving | 2 | 81 | 6 | 0 | 0 |
| 8b crop-single | parked | 28 | 5 | 0 | 0 | 0 |
| 8b crop-single | traffic | 3 | 46 | 0 | 0 | 0 |
| 8b crop-pair | driving | 4 | 85 | 0 | 0 | 0 |
| 8b crop-pair | parked | 29 | 4 | 0 | 0 | 0 |
| 8b crop-pair | traffic | 4 | 45 | 0 | 0 | 0 |
| 8b whole-plain-single | driving | 15 | 74 | 0 | 0 | 0 |
| 8b whole-plain-single | parked | 29 | 4 | 0 | 0 | 0 |
| 8b whole-plain-single | traffic | 4 | 45 | 0 | 0 | 0 |
| 8b crop-plain-single | driving | 8 | 65 | 16 | 0 | 0 |
| 8b crop-plain-single | parked | 23 | 9 | 1 | 0 | 0 |
| 8b crop-plain-single | traffic | 5 | 43 | 1 | 0 | 0 |
| edge: model / variant | Actual | left | right | unknown | error |
|---|---|---:|---:|---:|---:|
| 4b whole-pair | left | 10 | 0 | 3 | 9 |
| 4b whole-pair | right | 1 | 4 | 6 | 7 |
| 4b whole-pair | unknown | 11 | 15 | 172 | 13 |
| 8b whole-pair | left | 9 | 13 | 0 | 0 |
| 8b whole-pair | right | 2 | 16 | 0 | 0 |
| 8b whole-pair | unknown | 34 | 147 | 30 | 0 |
| 8b crop-pair | left | 13 | 9 | 0 | 0 |
| 8b crop-pair | right | 3 | 15 | 0 | 0 |
| 8b crop-pair | unknown | 55 | 103 | 53 | 0 |

Probability calibration follows for every measured question/variant. Each cell is count / mean declared probability / empirical class accuracy. Empty bins are shown as none. These are conditional probabilities normalized across the offered answer letters, not calibrated confidence in safety.

| Model / variant / question | p < .5 | .5 <= p < .8 | .8 <= p < .95 | p >= .95 |
|---|---|---|---|---|
| 4b whole-plain-single where | 1 / 0.443 / 0.00% | 26 / 0.668 / 57.69% | 27 / 0.887 / 59.26% | 175 / 0.995 / 77.14% |
| 4b crop-plain-single where | 1 / 0.484 / 0.00% | 17 / 0.637 / 47.06% | 32 / 0.898 / 62.50% | 180 / 0.996 / 71.67% |
| 4b whole-pair where | none | 9 / 0.647 / 66.67% | 15 / 0.898 / 93.33% | 198 / 0.998 / 60.61% |
| 4b whole-pair edge | 3 / 0.473 / 66.67% | 56 / 0.659 / 67.86% | 50 / 0.884 / 76.00% | 113 / 0.991 / 95.58% |
| 8b whole-single where | none | 7 / 0.699 / 57.14% | 21 / 0.894 / 85.71% | 223 / 0.996 / 55.16% |
| 8b whole-pair where | none | 1 / 0.691 / 0.00% | 10 / 0.895 / 90.00% | 240 / 0.999 / 56.67% |
| 8b whole-pair edge | 14 / 0.434 / 57.14% | 143 / 0.650 / 19.58% | 83 / 0.874 / 22.89% | 11 / 0.964 / 0.00% |
| 8b crop-single where | none | 14 / 0.673 / 57.14% | 26 / 0.906 / 57.69% | 211 / 0.995 / 56.87% |
| 8b crop-pair where | none | 8 / 0.669 / 87.50% | 5 / 0.904 / 40.00% | 238 / 0.999 / 57.14% |
| 8b crop-pair edge | 14 / 0.435 / 35.71% | 151 / 0.643 / 21.85% | 70 / 0.874 / 45.71% | 16 / 0.976 / 68.75% |
| 8b whole-plain-single where | 2 / 0.465 / 100.00% | 37 / 0.693 / 54.05% | 34 / 0.890 / 79.41% | 178 / 0.993 / 94.38% |
| 8b crop-plain-single where | none | 31 / 0.649 / 67.74% | 25 / 0.885 / 80.00% | 195 / 0.995 / 90.26% |
| 4b crop-single vehicle | none | 19 / 0.663 / 15.79% | 19 / 0.882 / 26.32% | 133 / 0.996 / 45.11% |
| 8b whole-single vehicle | none | 7 / 0.671 / 28.57% | 10 / 0.879 / 30.00% | 154 / 0.997 / 43.51% |
| 8b whole-pair vehicle | none | 8 / 0.621 / 37.50% | 8 / 0.900 / 37.50% | 155 / 0.998 / 43.87% |
| 8b crop-single vehicle | none | 9 / 0.634 / 66.67% | 18 / 0.875 / 61.11% | 144 / 0.996 / 43.75% |
| 8b crop-pair vehicle | none | 8 / 0.647 / 62.50% | 7 / 0.896 / 57.14% | 156 / 0.999 / 41.67% |
| 8b whole-plain-single vehicle | 2 / 0.486 / 0.00% | 34 / 0.673 / 32.35% | 38 / 0.887 / 28.95% | 97 / 0.989 / 53.61% |
| 8b crop-plain-single vehicle | 2 / 0.489 / 50.00% | 28 / 0.636 / 42.86% | 31 / 0.890 / 35.48% | 110 / 0.990 / 52.73% |

No new roadside or parked signal is enabled in the live loop, `foot.py`, or vehicle selection. The positional mark fails and the edge question is unusable. The vehicle rejection mark passes in isolation, but the question measured a particular marked detector box, while the current `Reader.poll(rgb, capture)` receives no detector target or identity. Appending a vehicle answer to the six-question prompt would change the measured question and could apply one car's answer to another. The positive empty-vehicle labels are also insufficient.

The exact integration handoff is to provide a separate timestamped vehicle judgment at `conductor.py`'s existing judge-poll/Observation construction boundary: pass a normalized target box and its detector capture time into a separate asynchronous vehicle request, retain that same box in the returned evidence, and carry it separately from the six-question mode judgment. A corresponding optional `Observation.vehicle_judgment` in `contract.py` would preserve its own capture clock. The consumer must reject future/stale evidence, mismatched tracks and changed boxes before applying the measured crop/single answer. Those conductor/contract edits are outside this card and are left undone. After the road-position and direction marks pass, a separate field with its own age is needed for road evidence as well; do not merge answers with different capture times under a single newer timestamp.

The independent seat repair is active. In 143128 the map is clean `none` from t=21.925, but the judge's accepted mode becomes `vehicle` near t=22.524. `player_mode()` preferred that accepted mode over the absent map, so the old one-second confirmation could report success after death. A clean absent map now vetoes seat confirmation even when the judge says vehicle, and clears the continuous proof. A clean none-mode, fresh death/banner answer, fresh contradictory mode, or wasted/busted HUD also clears it. Stale banners do not veto new proof. Existing accepted vehicle mode with a visible flat map remains supported; requiring a tilted map everywhere was not necessary to repair the demonstrated error. Terminal reasons now name the missing roadside eye and final known road position; successful confirmation explicitly says seated.

`death_replay.py` replays 112 recorded seat-window ticks with original minimap readings and original timestamped judge answers. The pre-change implementation reports done on 22 ticks; the corrected implementation reports done on 0. The first reconstructed old success is at 23.573 seconds, about one play tick from the recorded success. This isolates seat proof after an existing press; it is not a movement or full-controller replay.

The model cases extend the existing EntryGame simulation with lateral target geometry and stored measured position answers. Wrong answers are sampled from the measured class-specific pool; every fifth delivery is deliberately two seconds old, while other deliveries retain their measured request duration. The new eye is deliberately not consumed, so successes below demonstrate the existing map fallback under that input, not successful new visual control. Full per-tick pads, reasons and observed answer IDs/ages are in `model-cases.json`.

| Model case | Acceptance met | End / seconds | Presses | Final lateral x |
|---|---|---|---:|---:|
| passing_then_waiting | True | failed / 12.0 | 0 | 15.723755122907543 |
| parked_across | True | done / 17.3 | 2 | -10.255051240414295 |
| start_lane | True | failed / 6.0 | 0 | 15.929278976011629 |
| timeout_lane | False | failed / 0.2 | 0 | 1.9633802059287926 |
| no_judge | True | done / 4.2 | 1 | None |

The timeout case has a 0.2-second budget and ends at x=1.96 inside the lane, with a neutral pad and an explicit still-in-lane reason. It is an unmet requirement, not a passing roadside guarantee. The simulation's road and target geometry is simplified; it cannot establish real collision clearance or the requested live twenty-second parked-empty capability.

The 143714 entry replay covers all 870 recorded ticks, t=5.950..46.015, with the recorded duration=40. Original detections were not logged, so `replay-detections.json` contains 162 fresh 4 Hz detections recomputed from the original frames. `replay-answers.jsonl` contains real PC judge answers; each becomes available after its measured response duration and retains its capture age. `replay-ticks.jsonl` records the original pad, shadow pad, age and unqualified visual advice for every tick. On identical reconstructed observations, 0 ticks change pad/status against HEAD and 2 change reason. Differences from the historical recording occur on 500 ticks and cannot be attributed solely to P60 because the detections and timing were reconstructed. The recorded figure does not follow shadow decisions. Since the new eye is not enabled, there is no claim that this replay fixes the pickup pursuit or the ending in the junction.

Validation used `env -u PS5_HOST .venv/bin/python -m pytest -q tests/test_wiring.py tests/test_p60_judge.py tests/test_p60_vehicle_entry.py tests/test_vehicle_entry.py tests/test_judge.py tests/test_foot.py` in pilot: 220 passed in 5.34 seconds (`lab/where/gate-focused.log`). The automated tests use stored responses and synthetic observations; they never ask the server. Ruff check and format checks pass. The original full sandbox gate completed with 3337 passed, 3 skipped, 236 xfailed, six CoreML setup errors and two missing-PyAV failures. The CoreML errors were `tests/test_objects.py::test_real_traffic_and_player_exclusion`, `test_bad_frames_are_rejected[None]`, `[bad1]`, `[bad2]`, `test_reports_below_the_confidence_floor_are_left_out`, and `test_the_real_detector_gives_the_cut_out_figure_beside_the_filtered_list`; the cache under `~/Library/Caches/org.python.python/com.apple.e5rt.e5bundlecache` was denied. With local cache permission, the same Detector successfully produced the offline replay detections.

The two non-sandbox failures are `tests/test_trimming.py::test_packet_copy_b_frames_and_failure_checks` and `tests/test_trimming.py::test_action_video_reader_uses_original_clock_and_resets_motion`, both `ModuleNotFoundError: No module named 'av'`. They predate the changes in this run and are outside the allowed files. `docs/tasks/README.md:11` states: “The Python environment of your package is already installed and there is no network.” P60 grants only the judge endpoint exception, and its allowed write set excludes dependency/environment changes. No dependency was installed and no unrelated test was skipped or changed. A second exact `env -u PS5_HOST .venv/bin/python tools/gate.py --full` run with local CoreML permission is recorded in `lab/where/gate-full.log`. It finished with 3358 passed, 1 skipped, 236 xfailed and three failures: the same two missing-PyAV tests plus `tests/test_wiring.py::test_a_plan_from_the_head_starts_and_stops_every_new_skill[enter_vehicle]`, whose exact status reason still expected the old text. That direct vehicle-entry assertion was updated for the intentional road/eye suffix and passed in the subsequent focused run. The historical full log is retained unchanged; the full suite was not rerun after that test-only correction. The two dependency failures remain unresolved, so the card does not meet its Done condition.

Latest full-gate output: 3 failed, 3358 passed, 1 skipped, 236 xfailed in 956.54s (0:15:56); gate failed at: pytest -q --full

Reproduction commands from the repository root are `env -u PS5_HOST pilot/.venv/bin/python lab/where/measure.py sample`, `... measure.py vehicles`, `... measure.py freeze`, and `... measure.py run` with `--dataset vehicle`, `--model qwen/qwen3-vl-4b`, or `--variants whole-plain-single crop-plain-single whole-pair` as appropriate. The original 8B run uses the default four whole/crop single/pair variants. Use `... analyze.py` for tables, `... replay.py detect`, `... replay.py judge`, `... replay.py replay`, `... death_replay.py`, and `... model_cases.py` for evidence. Only explicit laboratory run/judge commands contact the authorized PC; replay, model probes and automated tests are offline. Review labels are intentionally frozen, not regenerated by the model.

The first supervised console check, after the blocked qualification/integration work is resolved, should reproduce the night-highway death with a false accepted vehicle mode and confirm that no seat success occurs on a missing map. Then inspect a passing pickup that stops at a junction, a truly empty parked car across the road, and a near-deadline exit from the lane, checking capture age, box identity and the actual ending position. The console remains untested in this task and was never contacted.

The work remains on the existing `feat/pilot-where` branch without Git writes or a PR. The global AGENTS.md requires branch/PR delivery, but this worker's README makes Git metadata read-only and forbids commit/stash/checkout/reset, and P60 permits network only to the judge. That delivery constraint remains explicit rather than being bypassed. No forbidden integration file, recording, daemon, PS5 configuration or secret was changed or accessed. The next owner must resolve the missing dependency, qualify road position and direction, strengthen empty-seat labels, and authorize the scoped integration boundary before treating P60 as complete.

The laboratory directory currently contains 5,388,157 bytes, below the 6,000,000-byte limit.
