# P77: Lock first, recorded rhythm and movement after a hit

The implementation is local and offline. Fight takes L2 before any camera turn, fires measured trigger pulses, releases and reacquires the lock, and only turns with both triggers released. Confirmed HUD hits cause a left strafe with the lock held, or one R1 tap with `cover=yes`. Stars, health below one third, loss of the map, timeout and interruption end with a neutral whole pad. The final verification results are recorded below. No console command, daemon request, Git write or live shootout was performed.

The recordings were inspected through the existing action/HUD labels and original controller rows. `recorded-rhythm.json` retains the per-stretch intervals, deduplicated lock measurements, each of the 47 hit windows and summary distributions. There are 523 fire stretches across 26 derived recordings: 427 with red in 17 recordings and 96 without red in 21 recordings. A fight cluster is consecutive fire stretches separated by no more than two seconds. This yields 179 red and 77 no-red clusters; a cluster can occur in both groups as markers change. These are reproducible automatic labels, not 256 independently verified shootouts.

Each stretch is red when at least one noncorrupt cached HUD sample contains red. The cached HUD is approximately 10 Hz. Controller times are native pad times; picture events are shifted by the recording's `labels.json` lead. Some leads are estimated or default values; image-to-hand and post-hit alignment inherit that uncertainty. Full original button intervals are retained instead of clipping holds at action boundaries, and intervals are deduplicated within each group. Long intervals and possible action-label mistakes remain visible in the JSON rather than being silently discarded. R2 and re-lock gaps are conditioned on gaps no longer than two seconds; these are combat cadence, not pauses between unrelated encounters. Stick values below are time-weighted mean magnitudes or signed axes per window. They can exceed one in magnitude because both axes may be active.

| Measurement | Red: n; median [P10, P90] | No red: n; median [P10, P90] |
|---|---|---|
| L2 held, s | 210; 1.101 [0.720, 3.369] | 40; 1.726 [0.843, 5.793] |
| First R2 after L2, s | 207; 0.391 [0.117, 0.958] | 40; 0.571 [0.193, 3.722] |
| R2 held, s | 467; 0.222 [0.146, 3.994] | 106; 0.180 [0.130, 1.194] |
| R2 gap <=2 s, s | 283; 0.726 [0.120, 1.589] | 28; 0.355 [0.070, 1.058] |
| Bursts per L2 hold | 210; 1.000 [1.000, 3.000] | 40; 1.500 [1.000, 3.000] |
| L2 re-lock gap <=2 s, s | 114; 0.536 [0.180, 1.430] | 13; 0.457 [0.172, 0.901] |
| R1 held during fire, s | 26; 0.119 [0.086, 0.894] | 1; 0.098 [0.098, 0.098] |
| Square held during fire, s | 0; not observed | 0; not observed |
| Right stick in 0.5 s before L2 | 210; 0.274 [0.000, 0.827] | 40; 0.372 [0.000, 0.804] |
| Right stick while L2 held | 210; 0.000 [0.000, 0.184] | 40; 0.046 [0.000, 0.232] |
| Left stick while firing | 427; 0.046 [0.000, 1.018] | 96; 0.000 [0.000, 0.995] |
| Left X while firing | 427; 0.000 [-0.337, 0.180] | 96; 0.000 [-0.216, 0.191] |
| Left Y while firing | 427; 0.000 [-0.973, 0.050] | 96; 0.000 [-0.776, 0.003] |

For red locks with an observable preceding readable no-red sample, marker appearance to L2 is 1.704 s median [0.175, 7.138], n=106. The other 104 red locks are censored because onset is absent or interrupted by unreadable samples. This is the beginning of the contiguous red run before the lock, at cached-HUD resolution, not a native-frame reaction-time claim. The no-red group has no corresponding marker-onset requirement.

The right stick is usually still while aiming, although it often moves in the preceding half second. The policy follows Kerim's explicit L2-first instruction rather than copying a compulsory pre-turn. Left movement during fire is usually small; the recordings do not justify claiming he always strafes. Square was absent during the fire labels themselves. Including the two seconds after a fire label gives five distinct Square presses in the red group, 0.764 s median after the end of the associated label [0.158, 1.107] min/max, and none in the no-red group. There are 40 red and six no-red R1 edges in that wider window. Their timing relative to label end is -1.317 s median [-22.438, 1.951] and 1.478 s [-0.547, 1.764], respectively. Overlapping windows are deduplicated by the original press edge. R1 is a cover input and Square a possible reload input; neither proves that cover attached or a reload animation happened.

All 47 labelled hits are included, 43 red and four no-red. Using the two seconds after each lead-corrected hit, red movement above magnitude 0.2 occupies 21.063/86 s; no-red movement occupies 0.426/8 s. Of the red moving time, dominant negative X accounts for 5.348 s, positive X 2.298 s, negative Y 12.610 s and positive Y 0.807 s. Negative X has median active magnitude 1.0. Negative Y is predominantly forward in the controller convention, so the bounded evasive policy chooses the observed secondary lateral response instead of claiming forward movement is backing away. Two red hit windows include R1 and three include Square; the four no-red hits include no R1 and one Square. `movement.json` contains the aligned, time-weighted counts. These differ from a raw, unshifted quick pass and supersede that preliminary pass.

The acquisition wait is 0.206 s, the observed lower quartile of 207 red L2-to-R2 intervals (P25 0.2055 s), rather than the 0.391 s median. This is an explicit responsiveness choice using Kerim's faster observed acquisitions, not a measurement of the game's minimum safe lock time. A frontal lock remains held for the observed 1.101 s median L2 duration. An off-axis lock is released after its scheduled burst so the camera can be corrected while L2 is up. R2 holds for 0.222 s, with one burst per lock from the observed median count. The measured 0.726 s inter-burst gap is retained as provenance but unused by the current one-burst policy. Re-lock separation is 0.536 s. The active pre-lock horizontal right-stick median is 0.99 over 31.911 s, so camera correction uses that magnitude. The cover tap is 0.120 s from the 0.11915 s median of 26 recorded cover holds. The two-second hit-response window is required by the card; the lateral magnitude is the measured 1.0. Existing map/timeout limits, conservative five-degree reacquisition alignment and melee range remain safety policy inherited from P18, not newly measured game physics.

Fight now ends immediately with existing reason `health-still-low` below one third, allowing the head and guard to flee. Previously it entered a four-second recovery branch. This decision follows the card's terminal low-health requirement; Melee retains its recovery behavior. Melee also keeps its turn-first geometry, range, aim wait, release wait and termination reasons. Only its pulse gap changes to `Punch.PULSE_PERIOD - Punch.PULSE_DURATION`, preserving the authoritative 0.12 s press and 0.21 s period. The guard's source and tests are unchanged. Hits is a confirmed HUD drop, with the existing quiet interval and agreeing readings, so evasion begins after confirmation rather than at the first physical impact. Cover attachment is still unverified.

A conservative weapon-corner reader was tried on 40 fire frames and 40 melee candidate-negative frames. `weapon-samples.json` names each source recording and native frame; `weapon-components.json` retains features. The upper-right ammunition counter was visually checked. Melee inputs are not guaranteed proof of an empty hand, so these are action-derived, visually checked candidate labels, not independently verified weapon-state ground truth. The tested 1280x720 crop was x=1030:1240, y=20:100, HSV saturation <=95 and value >=180, with components of area 6..350, height 5..35 and width 1..28. Component-count >=3 gave TP26/TN33/FP7/FN14; largest-component >=99 gave TP26/TN35/FP5/FN14 (61/80). A zero-false-positive threshold recognized only 2/40 armed frames. This is below the 40/40 evidence target for a reliable reader. No `armed(frame)` module or `no-weapon` termination was installed, and no corresponding unit test is claimed. Existing callers may omit `Observation.frame`; any later validated reader also needs caller-frame availability checked by its owner.

`observe_lock.py` inspected 43 quiet-stick locks at native frames 100 ms before and 500 ms after L2 plus lead, requiring exactly one readable red marker in both pictures. It found zero unambiguous off-axis-to-front candidates. The clips therefore do not establish a numeric lock cone or prove same-target identity. The simulator explicitly retains the inherited 25-degree cone and 180 deg/s camera assumption and additionally checks 15 and 45 degrees. It now snaps the camera on an L2 rising edge inside the cone. This tests the controller policy under stated physics; it does not validate GTA's lock cone, tracking, damage or enemy deaths.

The 20-scene comparison in `replay-comparison.json` gives P65: 3/20 L2 aims within one second and 4/20 scenes with any R2. The frozen old controller at fixed 30 Hz gives 3/20 and 3/20. Final P77 gives **15/20 and 16/20**, respectively. The aim target is met. P65 used realtime scheduling; its single R2 tick on enemy-09 disappears in the fixed-schedule baseline, so those baselines are kept separate. P77 stores metrics from all raw post-onset samples before the bench compacts them. Historical aim uses the saved L2 answer transition, while historical firing uses guard episode fire counters. The ledger records the exact combat source hash used by that run. A subsequent defensive check also rejects explicitly absent maps when an externally constructed reading claims foot mode and red blips. Real reader-produced absent maps already have confidence zero and no blips (`minimap.py:868-873`), so this additional veto cannot change the recorded replay decisions. Its regression test passed in the final 84-test focused run.

| Scene | P65 aim <=1 s / fired | P77 first L2, s | P77 first R2, s |
|---|---|---|---|
| enemy-01 | no / no | 0.133 | 0.367 |
| enemy-02 | no / no | none | none |
| enemy-03 | no / no | 0.067 | 0.300 |
| enemy-04 | no / no | none | none |
| enemy-05 | no / no | 2.867 | 3.100 |
| enemy-06 | no / no | 2.567 | 3.067 |
| enemy-07 | no / yes | 0.067 | 0.300 |
| enemy-08 | no / no | 0.100 | 0.767 |
| enemy-09 | no / yes | 1.500 | 1.733 |
| enemy-10 | no / no | 0.100 | 0.333 |
| enemy-11 | no / no | 0.100 | 0.333 |
| enemy-12 | yes / yes | 0.100 | 0.333 |
| enemy-13 | no / no | 0.100 | 0.333 |
| enemy-14 | no / no | 0.067 | 0.300 |
| enemy-15 | no / no | 0.800 | none |
| enemy-16 | no / no | 0.767 | none |
| enemy-17 | yes / yes | 0.100 | 0.333 |
| enemy-18 | yes / no | 0.100 | 0.333 |
| enemy-19 | no / no | 0.100 | 0.333 |
| enemy-20 | no / no | 0.100 | 0.333 |

These include all 20 requested rows, including late or absent actions. The choice to replay at fixed 30 Hz and a modelled 100 ms head delay avoids machine-load frame skipping; it is not a measured inference-latency result. Runtime guard/head selection and unsafe pictures still suppress some actions. All output and scratch for the completed comparisons is confined to `lab/combat`; the initial interrupted CLI exploration was superseded and its temporary scratch cleaned itself up. No source recording or reaction ledger was changed.

The first on-target shot in `lab/combat/p77-simulation.json` is faster for side and rear enemies and no later for the enemy ahead. The same result holds for assumed lock half-cones 15, 25 and 45 degrees. At the inherited 25-degree half-cone:

| Enemy bearing | Frozen old, s | P77, s |
|---|---|---|
| ahead (0 degrees) | 0.300 | 0.208 |
| side (90 degrees) | 1.608 | 1.183 |
| behind (175 degrees) | 2.467 | 1.608 |

The deterministic first-shot comparison samples at 120 Hz to resolve policy timing. The noisy 30 Hz survival simulation clears 20/20 ordinary seeds, with 20 neutral endings and zero invalid attacks. All 20 high-pressure seeds stop `health-still-low`, and all 20 missing-map seeds stop `minimap-unreadable`. Melee has 20 neutral endings and zero invalid attacks; only 6/20 enemy sets are cleared and only two end `no-red-blips` before the ten-second limit. That melee clear rate is not presented as a validated combat success rate. The safety invariant checks damaged/no-map attacks; an off-axis shot while attempting aim assist is not counted as unsafe merely because the replay marker has not turned.

The focused run `python -m pytest tests/test_combat.py tests/test_guard.py -q` passed **84 tests**. It covers initial off-axis L2, measured acquisition/release/reacquisition timing, camera turns only with L2 up, confirmed-hit strafe/cover, every existing terminal reason with neutral pads, stars on a firing tick, immediate no-map/damaged-frame neutralization, Melee geometry and Punch cadence, and all nine simulator comparison cases. The weapon-reader test is conditional on a successful reader and is deliberately absent because the experiment failed. Scoped Ruff checks and formatting passed; `git diff --check` passed. Weapon analysis scripts were syntax-checked and `score_weapon.py` reproduced the four confusion matrices from the retained features.

Reproduction commands from `pilot/` are shown below. The final replay runner checks the combat source hash and resumes only missing scene IDs in a matching ledger; it refuses mixed implementations. The historical baseline is already complete and should be reused instead of rerun. OpenCV is limited to one thread in the replay and native-frame observer.

```sh
.venv/bin/python tools/evaluate_combat.py --output ../lab/combat/recorded-rhythm.json
.venv/bin/python ../lab/combat/measure_movement.py
.venv/bin/python ../lab/combat/observe_lock.py
.venv/bin/python ../lab/combat/score_weapon.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python ../lab/combat/replay_fights.py --output ../lab/combat/p77-final.jsonl
.venv/bin/python ../lab/combat/summarize_replay.py
.venv/bin/python tools/sim_combat.py --seeds 20 --output ../lab/combat/p77-simulation.json
.venv/bin/python -m pytest tests/test_combat.py tests/test_guard.py -q
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python tools/gate.py
```

Recorded outputs include `84 passed`, replay counts `aim_within_1s: 15` and `fired: 16`, simulator `cleared: 20`, `neutral_ends: 20` and `invalid_attacks: 0` for ordinary combat, and weapon `largest>=99: TP26 TN35 FP5 FN14`. The added lab evidence is approximately 1.1 MB, below the three-megabyte limit; source videos and frame images were not copied into the repository. Existing `lab/combat/simulation.json` was preserved and the new run has its own `p77-simulation.json`.

The full gate was run exactly once after the session resumed. Its Ruff check and format stages passed (`168 files already formatted`). Pytest finished with `2 failed, 2798 passed, 1 skipped, 1376 deselected, 4 xfailed in 238.31s`. Both failures were `tests/test_profile.py::test_actions_emit_profile_buttons[gta5/gta6]`: the old assertion expected R1 at health 0.2, contradicting this card's terminal low-health requirement. Only the combat assertions in that profile test were changed. It now verifies neutral `health-still-low` and verifies each profile's cover button after a real confirmed HUD hit. The targeted follow-up was `python -m pytest tests/test_profile.py -q`: **25 passed in 0.43s**, with Ruff check/format passing. The final combat/guard run, including the defensive absent-map case added while the gate was running, was **84 passed in 1.65s**.

There is no all-green full-gate rerun after those final changes. The user's explicit instruction to run the whole gate only once was followed. All failures from that run were corrected and individually rechecked, but a fresh zero-exit full-gate result remains unverified. The card's literal all-green-gate evidence condition is therefore not claimed as met. This is the remaining local verification limitation for the reviewer; no failing combat or profile test is known. The full-gate log is retained at `/tmp/p77-final-gate.log` for this machine session.

The remaining acceptance is the live console: a shootout with Kerim watching, weapon visibly in hand and full aim assist enabled, from marker onset through the last enemy down. Replay never turns the recorded camera or acquires a real lock. An L2/R2 tick proves the controller decision only. The weapon-state uncertainty and assumed lock geometry must be understood before relying on this to send inputs to the console. Per the task README, changes are left in this worktree for the reviewer; there is no commit or pull request.
