# P110: The way round is a swerve, not a spin

The driver now tries to drive on before an unseen obstruction warrants reverse, backs straight at part L2, and steers a 32-degree swerve from the road heading before returning to it. The simulator and replay checks pass, but P110 is not fully accepted: the single whole gate found two new straight-road regressions, which were corrected and passed focused verification afterwards; the whole gate was not repeated. These are offline results, not evidence of a successful console trip. Physical retreat including the gear-change tail still exceeds a car's length beside a wall; the implementation does not establish a universal four-metre stopping bound.

The measurement covers 34 recordings from `20261114-051709` through `20261114-110629`. It found 359 `bypass-*` episodes under the grouping rule below: 130 include reverse, 224 only wait, and five are forward-only fragments separated from earlier manoeuvres by longer coast gaps. Among all 135 driven portions, 65 end more than 45 degrees from the near route heading: **48.15%**. Restricting the denominator to the 130 episodes with reverse gives 63/130, or **48.46%**. This is an endpoint measure, not proof that the manoeuvre caused all of that deviation, and the forward-only fragments are not necessarily independent attempts. The complete table retains every portion and every wait.

| Population | Episodes | Near heading beyond 45° at end | Far heading beyond 45° at end | Following/aligned log proxy within 5 s |
|---|---:|---:|---:|---:|
| All bypass episodes | 359 | 117 (32.59%) | 153 (42.62%) | 173 (48.19%) |
| All driven portions | 135 | 65 (48.15%) | 70 (51.85%) | 46 (34.07%) |
| Episodes with reverse | 130 | 63 (48.46%) | 68 (52.31%) | 46 (35.38%) |
| Forward-only fragments | 5 | 2 (40%) | 2 (40%) | 0 |
| Wait only | 224 | 52 (23.21%) | 83 (37.05%) | 127 (56.70%) |

`p110_measure.py` measures wrapped `bearing - arrow` and `far_bearing - arrow` at the first and last bypass tick. It bridges `coast` gaps of at most 0.5 s and otherwise ends an episode at the following tick. Printed metres are the first and last available GPS distance within the episode; a positive delta means farther from the destination. They are not odometry, and stale readings, rounding and rerouting can distort them. Raw bearing, far bearing, arrow, endpoint times, phase lists, first reverse durations and source SHA256 hashes are retained in [p110-episodes.json](../../lab/drive/p110-episodes.json). The inventory and table are reproducible with `nice -n 15 .venv/bin/python ../lab/drive/p110_measure.py` and `nice -n 15 .venv/bin/python ../lab/drive/p110_tables.py` from `pilot`.

The logs do not retain the detector boxes or reliable visual lane membership. Origin D is inferred from an initial `bypass-wait`; B from an initial reverse lasting more than 1.3 s without a preceding wait, the old blind branch's longer reverse. The 130 active episodes comprise 86 D, 33 B and 11 unknown. Those are inferred origins, not reconstructed detections. The five-second column means at least one subsequent `follow` tick with both headings within 20 degrees. It does not establish sustained motion or that the body was actually on the road. Actual on-route recovery is therefore unverified where video has not been reviewed; the proxy must not be used as a console success rate.

In `110629`, the first episode is 42.480–57.150 s: near heading 9.79° to -72.42°, far heading 53.16° to -37.35°, and printed distance 931 to 941 m. It starts with a 1.808 s reverse and has no five-second following proxy. The six-frame JPEG at `lab/drive/p110-110629-sheet.jpg` shows the car at the kerb at 38.52 and 42.55 s, across the junction at 44.43 and 47.01 s, and facing the wall and kerb at 52.01 and 56.03 s. It is a local review artifact under 300 kB and must not be committed.

The clear-road standstill entry now supplies R2 0.7 with heading feedback after sustained stillness. At a first launch it retains the existing stuck wait; after observed forward travel, a later stop can start the push after 0.3 s. This distinction avoids treating a car's normal launch as a recovery. Real movement hands back to following; continuing stillness after one second starts reverse. Missing motion alone never authorizes reverse, and an inconclusive push releases after two seconds. The reverse command is straight at L2 0.7, ends on sustained rear stillness, estimated travel of 3 m including input-delay allowance, or a 2 m increase in printed route distance, and has a uniform 1.8 s fallback ceiling. The distance thresholds leave room for delayed observations but cannot turn stale route-distance readings into ground-truth odometry.

Forward motion aims 32 degrees towards the selected side using the local route tangent, falling back to the far heading. Steering is proportional to heading error and bounded at 0.95. R2 is 0.8 for the gear change and 0.65 afterwards. The short initial inversion of the heading feedback accounts for reverse momentum; it does not hold a fixed steering lock. After 4 estimated metres it aims along the road. Handover requires movement, less than 20 degrees of onward-heading error and 4 m of net printed progress when an origin is available, or 6 estimated forward metres without that origin. The progress check prevents an aligned but uncompleted swerve handing the frozen replay into a separate `turn-join` manoeuvre. An attempt is bounded at eight seconds of forward/pass motion; blocked attempts alternate sides and consume the existing recovery budget, ending with neutral controls.

Removed the blind/detected manoeuvre split, `_bypass_blind`, `_bypass_attempts`, doubled blind reverse duration, `lock_time`, growing arcs, the fixed full-lock/full-pedal branch and the timed handovers that ignored heading. The existing attempt counter now owns the budget and side alternation. `bypass_reverse_time` remains because `turn-clear` still uses it. The separate `turn-*` behavior was retained; its shared movement bookkeeping was condensed without changing its thresholds. `drive.py` is **1359 lines before and 1359 after**. No changes were made to the forbidden modules.

The original required regressions are red against HEAD. [p110-acceptance-before.txt](../../lab/drive/p110-acceptance-before.txt) ends with `14 failed, 3 deselected in 0.99s`: all eleven `test_parked_box_is_passed_without_turning_away_from_the_road` profiles, `test_standing_at_a_clear_kerb_first_drives_on_without_reversing`, `test_downhill_backing_releases_l2_within_a_car_length`, and `test_recorded_seconds_do_not_hold_full_lock_or_full_reverse`. `p110_red.py` temporarily writes `git show HEAD:pilot/src/pilot/drive.py`, runs those tests and restores the exact working bytes in `finally`; the pre-gate restored SHA256 was `25194f50e35d2cabf1cff6b2615ea46f5b287aa2caf1eefb0578a978cd67ac3d`. The old free-side simulator reaches 116.23° and retreats 5.28 m; the old downhill-momentum case releases reverse only at 15.02 m. The pre-gate focused receipt, [p110-focused-final.txt](../../lab/drive/p110-focused-final.txt), is `86 passed in 3.81s`. It includes all P101 tests, all new tests and the manoeuvre safety tests. The final post-correction result and gate status are recorded below.

The following are every existing test changed. The coordinator explicitly authorized these five functions in `test_round_what_stands.py` and `test_player_manoeuvres.py`; no other function in those files was changed. No assertions in `test_car_in_town.py`, `test_turn_round.py`, `test_drive.py` or `test_sim.py` were changed.

| Existing test | Before | Now and reason |
|---|---|---|
| `test_unseen_reverse_stops_early_when_the_rear_is_blocked` | Ran a fixed 65 ticks before scheduling motion and rear stillness relative to reverse start; asserted neutral pedals on the first still tick and forward with L2 released on sustained stillness. | Stops setup at the first observed reverse tick, then retains the same assertions. The earlier push/reverse entry otherwise made the old setup send time backwards. |
| `test_bypass_wait_reverse_forward_and_return_to_route` | Expected neutral waiting, full L2, full forward lock and full R2 at fixed times, then a timed return to following. | Observes reverse, forward and pass; requires part pedals, steering to unwind at the 32° outward heading, continued manoeuvring while misaligned, return steering and handover after alignment. Full lock and timed handover are deliberately removed behavior. |
| `test_reverse_is_bounded_and_ends_when_motion_stops` | Asserted the neutral rear-stop tick, transition to forward after sustained stillness, and detected reverse ending at the old 0.9 s timer; turn reverse used its existing bound. | Preserves the rear-stop assertions for bypass and turn, observes the forward transition and checks it against the unified 1.8 s maximum for bypass and unchanged turn bound. A detected car now has the same distance-bounded reverse as an unseen one. |
| `test_external_stop_in_every_phase_returns_and_keeps_a_complete_neutral_pad` | Reached five phases by fixed timestamps, then asserted failed/operator-stop, zero sticks and triggers, no buttons, and identical stopped results thereafter. | Reaches those same five phases by observing the commands. Every external-stop and persistent-neutral assertion is unchanged. |
| `test_bypass_retries_other_side_and_respects_existing_recovery_limit` | Forced forward motion and failure at fixed timestamps, then asserted the other side and failure after two tries. | Observes forward, then supplies sustained stillness and observes the opposite-side reverse. It retains the exact two-try limit and adds an explicit neutral-controls assertion at final failure. |

The planar runs reuse P101's closed 1.8 m by 4 m rectangle, optional walls at x = ±1.25 m, the complete `DriveRoute` skill and all eleven existing car profiles. They use a straight road and deterministic clean perception. All 33 cases pass the obstruction in 6.90–15.93 s after first contact and rejoin the road by 21.77 s from start. The blocked-left cases require the second side; no assertion was relaxed to admit them. [p110-sim-before.json](../../lab/drive/p110-sim-before.json), [p110-sim-after.json](../../lab/drive/p110-sim-after.json) and [p110-sim-final.txt](../../lab/drive/p110-sim-final.txt) contain all profiles and phase transitions. The maxima below are across each eleven-profile set; the heading after a way round is measured at its last bypass tick, not much later after the follower repairs it.

| Model and case | Passed / rejoined | Greatest bypass heading | Greatest final bypass heading | Longest reverse leg including gear change | Greatest total reversed per run |
|---|---:|---:|---:|---:|---:|
| Before, no side wall | 11/11 | 116.23° | 32.79° | 5.28 m | 5.28 m |
| After, no side wall | 11/11 | 35.36° | 19.26° | 3.81 m | 3.81 m |
| Before, left wall | 11/11 | 68.13° | 7.53° | 5.28 m | 10.57 m |
| After, left wall | 11/11 | 40.44° | 19.09° | 5.18 m | 8.63 m |
| Before, right wall | 11/11 | 116.23° | 32.79° | 5.28 m | 5.28 m |
| After, right wall | 11/11 | 35.36° | 19.26° | 3.81 m | 3.81 m |

While the reverse command is still active, the longest measured retreat is 2.39 m without a side wall and 4.06 m on a left-wall retry. The latter exceeds 4 m by 0.06 m, and its physical reverse leg including the delayed gear change reaches 5.18 m. This is a remaining bound limitation. A 1.3 s timer experiment reduced retreat but failed nine P101 blocked-left cases; it was rejected rather than weakening those assertions. Its receipt is [p110-short-reverse-trial.txt](../../lab/drive/p110-short-reverse-trial.txt). The selected 1.8 s ceiling retains P101 passage while cutting the old full-L2 command and using distance to release early when the readings support it.

The slope substitute gives the planar car an initial reverse velocity of 8 m/s and a reverse-speed ceiling of 12 m/s. Original L2 release was at 1.833 s and 15.019 m; new release is at **0.300 s and 2.270 m**. The planar simulator has no grade or gravity, and this test measures release of L2, not the eventual stopping position down a real hill. It cannot prove a physical four-metre hill stop.

The inherited detected-car matrix, left unchanged, passes 104/110 cases inside its original 12 s horizon with both HEAD and the final driver. Both versions miss the same six cases, all at a 12 m gap. With the final driver and a 20 s horizon they pass in 15.50–16.27 s. No detected case ends in a failure state. Receipts are [p110-detected.json](../../lab/drive/p110-detected.json), [p110-detected-before.json](../../lab/drive/p110-detected-before.json) and [p110-detected-tail.json](../../lab/drive/p110-detected-tail.json).

The open-loop replay uses all 506 fresh ticks from 38.0318 to 56.9737 s in `110629`, the recorded readings, original frame IDs and timestamps, normalized GPS ages and existing minimap motion extraction over the recorded video. Motion is true on 259 ticks, unknown on 166 and false on 81. It assumes no detector boxes, consistent with the targeted kerb scene; it does not claim to recover absent detector history. Extraction has a 36 s warmup and is cached in the small `p110-replay-inputs.json.gz`. `nice -n 15 .venv/bin/python ../lab/drive/p110_replay.py` reproduces both versions without decoding again or sending inputs. `--extract` rebuilds the cache read-only with cv2.

| Frozen replay, 38–57 s | Original driver | New driver |
|---|---:|---:|
| Longest same-sign full stick, magnitude ≥0.999 | 2.052 s | 0 s |
| Longest full L2, magnitude ≥0.999 | 1.818 s | 0 s |
| Longest strong stick, magnitude ≥0.9 | 2.052 s | 1.574 s |
| Follow ticks | 119 | 74 |
| Reverse ticks | 145 | 144 |
| Forward / pass ticks | 179 / 62 | 212 / 48 |

The new controller still uses strong heading correction, so the zero full-lock result is not a claim that steering is always small. The planar heading bounds and the test that steering unwinds at the outward heading provide the independent behavior check. The new replay's fewer follow ticks cannot be read as better or worse real progress: the car continues to show the original driver's future pictures. The replay proves command bounds under those inputs, not that the new commands would clear the junction, avoid a collision, reach the route or finish the cinema trip. The simulator models a point crossing line segments, not full body clearance, deforming cars, pedestrians, road grades, camera motion, tyre damage or live perception errors. The kerb test supplies movement after sufficient pedal; it proves the controller tries forward first, not that GTA's kerb can always be climbed.

No console or daemon call was made, no PS5 command was run, no PS5_HOST was set, recordings stayed read-only, and no Git commit, stash, checkout or reset was used. Numerical jobs ran serially at nice 15. The existing unrelated `lab/avoid/p109-night-sheet.jpg` was left untouched. The next console trips must measure seconds standing while following, ways round per ten minutes, actual route-following within five seconds after each, and Kerim's judgement of whether it looks like driving.

The whole gate ran exactly once from `pilot` with `nice -n 15 .venv/bin/python tools/gate.py`, recording [p110-gate.txt](../../lab/drive/p110-gate.txt). Lint passed and all 216 files passed the format check. Its last lines are:

```text
FAILED tests/test_drive_through.py::test_drive_through_roads_with_the_existing_car_profiles[range-12-kilometre]
FAILED tests/test_drive_through.py::test_drive_through_roads_with_the_existing_car_profiles[fast-low-grip-kilometre]
2 failed, 3900 passed, 1 skipped, 1376 deselected, 1 xfailed in 127.89s (0:02:07)
gate failed at: pytest -q
```

These two failures were regressions, not the card's known flaky server test. The default gate's selected P101, `test_car_in_town.py`, `test_sim.py`, `test_turn_round.py` and `test_drive.py` cases passed. Both failing cases passed against HEAD (`2 passed in 0.56s`, [p110-gate-baseline.txt](../../lab/drive/p110-gate-baseline.txt)). The early push had altered normal launch dynamics before the car had ever moved, causing the existing follower to brake near 948 m on the kilometre road. The correction confines the shortened wait to stops after observed forward travel, using the existing distance counter and adding no state. The two existing straight-road assertions were not changed. The affected suites `test_swerve.py`, `test_round_what_stands.py`, `test_player_manoeuvres.py` and the complete `test_drive_through.py` then passed: **138 passed in 17.22s**, recorded in [p110-post-gate-focused.txt](../../lab/drive/p110-post-gate-focused.txt). Final focused lint and format checks pass; simulator and replay receipts were refreshed for the corrected entry. The full gate has no passing receipt for this final source because the instruction permits only one run. The recorded gate exited at pytest before reaching its runtime check, so it did not print `default gate exceeded 90 seconds`; its pytest duration alone was nevertheless above 90 s. Full acceptance and live-console validation remain open.

The complete morning table follows. All recordings are from 14 November 2026; the recording column is HHMMSS. R means the episode contains reverse, W means wait only, and F is a forward-only fragment with no reverse in that portion. Near and far columns show the start and end errors against the arrow. Printed metres show first → last and the signed delta in parentheses. D and B are the inferred origins described above, `?` means unknown. The final column is only the five-second following/alignment proxy described above, not visually verified road membership.

| # | Recording | Seconds | Kind | Near degrees | Far degrees | Printed metres | Origin | Follow in 5 s |
|---:|---|---|---|---|---|---|---|---|
| 1 | 052018 | 14.06–14.90 | W | 125.2 → 125.2 | 107.4 → 107.4 | 1260.0 → 1260.0 (0.0) | D | no |
| 2 | 052018 | 40.48–47.50 | R | -3.5 → 102.1 | 51.0 → 78.5 | 987.0 → 1020.0 (33.0) | B | no |
| 3 | 052018 | 66.02–70.44 | R | 57.4 → 22.7 | 68.3 → 33.4 | 934.0 → 936.0 (2.0) | D | yes |
| 4 | 052018 | 168.25–175.26 | R | 5.3 → 125.0 | 27.2 → 99.0 | 71.0 → 94.0 (23.0) | B | no |
| 5 | 052018 | 200.34–201.44 | W | -114.3 → -114.0 | -108.7 → -109.2 | 199.0 → 192.0 (-7.0) | D | no |
| 6 | 052402 | 142.08–146.19 | R | -31.1 → -43.4 | -56.3 → -69.3 | 142.0 → 143.0 (1.0) | D | no |
| 7 | 052653 | 15.44–19.58 | R | -151.3 → -162.2 | -151.3 → -149.2 | 1790.0 → 1790.0 (0.0) | D | no |
| 8 | 052653 | 32.47–32.51 | W | -3.0 → -3.0 | -2.9 → -2.9 | 1710.0 → 1710.0 (?) | D | yes |
| 9 | 052653 | 50.02–53.15 | R | 9.4 → 79.8 | 9.8 → 77.3 | 1520.0 → 1520.0 (0.0) | D | yes |
| 10 | 052653 | 136.29–136.33 | W | -33.3 → -33.3 | -41.4 → -41.4 | ? → ? (?) | D | no |
| 11 | 052653 | 136.45–137.41 | W | -33.2 → -32.5 | -41.1 → -41.0 | ? → ? (?) | D | no |
| 12 | 052653 | 137.51–140.34 | R | -32.6 → -21.0 | -41.2 → -30.9 | 614.0 → 614.0 (0.0) | D | no |
| 13 | 053655 | 391.39–391.90 | W | -80.7 → -81.0 | -98.9 → -99.0 | 1520.0 → 1520.0 (0.0) | D | no |
| 14 | 053655 | 489.85–489.89 | W | -32.3 → -32.3 | -48.5 → -48.5 | 1290.0 → 1290.0 (?) | D | no |
| 15 | 053655 | 490.67–490.72 | W | -27.4 → -27.4 | -42.9 → -42.9 | 1290.0 → 1290.0 (?) | D | no |
| 16 | 053655 | 491.51–491.59 | W | -27.0 → -27.0 | -42.4 → -42.5 | 1290.0 → 1290.0 (0.0) | D | no |
| 17 | 053655 | 492.78–492.92 | W | -26.6 → -26.6 | -43.3 → -43.3 | 1260.0 → 1260.0 (0.0) | D | no |
| 18 | 053655 | 494.76–494.83 | W | -27.8 → -27.7 | -43.2 → -43.2 | 1260.0 → 1260.0 (0.0) | D | yes |
| 19 | 053655 | 495.99–498.89 | R | -27.2 → 1.3 | -42.8 → -13.1 | 1260.0 → 1260.0 (0.0) | D | yes |
| 20 | 053655 | 516.15–516.34 | W | 20.9 → 20.9 | 8.8 → 8.8 | 1110.0 → 1110.0 (0.0) | D | yes |
| 21 | 053655 | 516.40–516.91 | W | 20.8 → 20.8 | 8.7 → 8.7 | 1110.0 → 1110.0 (0.0) | D | yes |
| 22 | 053655 | 517.06–520.43 | R | 20.8 → 1.5 | 8.7 → -5.5 | 1110.0 → 1110.0 (0.0) | D | yes |
| 23 | 053655 | 570.20–575.38 | R | 33.2 → -13.2 | 47.2 → -36.7 | 524.0 → 528.0 (4.0) | D | yes |
| 24 | 054734 | 75.33–75.37 | W | -24.8 → -24.8 | -22.7 → -22.7 | 1550.0 → 1550.0 (?) | D | yes |
| 25 | 054734 | 75.81–75.86 | W | -12.6 → -12.6 | -7.7 → -7.7 | 1550.0 → 1550.0 (?) | D | yes |
| 26 | 054734 | 167.69–167.80 | W | -1.6 → -1.7 | 0.6 → 1.3 | ? → ? (?) | D | yes |
| 27 | 054734 | 167.83–168.02 | W | -1.7 → -1.7 | 1.4 → 1.3 | 439.0 → 439.0 (0.0) | D | yes |
| 28 | 054734 | 168.32–168.51 | W | -1.6 → -1.6 | 1.4 → 1.4 | 439.0 → 439.0 (0.0) | D | yes |
| 29 | 054734 | 168.55–168.62 | W | -1.6 → -1.6 | 1.4 → 1.4 | 439.0 → 439.0 (0.0) | D | yes |
| 30 | 054734 | 168.66–168.81 | W | -1.6 → -1.6 | 1.4 → 1.4 | 439.0 → 439.0 (0.0) | D | yes |
| 31 | 054734 | 168.88–169.00 | W | -1.6 → -1.6 | 1.4 → 1.4 | 439.0 → 439.0 (0.0) | D | yes |
| 32 | 054734 | 169.02–172.94 | R | -1.6 → -33.9 | 1.4 → -27.8 | 439.0 → 440.0 (1.0) | D | yes |
| 33 | 054734 | 177.27–178.15 | W | 15.5 → 15.6 | 16.4 → 16.5 | 424.0 → 424.0 (0.0) | D | yes |
| 34 | 054734 | 178.70–181.92 | R | 17.5 → 61.1 | 18.4 → 61.0 | 424.0 → 425.0 (1.0) | D | yes |
| 35 | 054734 | 217.02–225.31 | R | 66.2 → -37.8 | 80.9 → -32.0 | 114.0 → 116.0 (2.0) | B | no |
| 36 | 054734 | 323.38–323.75 | W | 54.6 → 54.7 | 63.0 → 63.0 | 115.0 → 115.0 (0.0) | D | yes |
| 37 | 055349 | 86.48–86.58 | W | 0.3 → 0.2 | 4.8 → 4.8 | 1230.0 → 1230.0 (0.0) | D | yes |
| 38 | 055349 | 86.99–87.15 | W | 1.3 → 1.4 | 5.9 → 5.9 | 1230.0 → 1230.0 (0.0) | D | yes |
| 39 | 055349 | 87.53–87.56 | W | -1.1 → -1.1 | 3.5 → 3.5 | 1230.0 → 1230.0 (?) | D | yes |
| 40 | 060000 | 120.97–134.17 | R | 12.4 → -141.7 | -1.2 → -141.7 | 867.0 → 866.0 (-1.0) | B | no |
| 41 | 060000 | 238.86–239.12 | W | 29.6 → 30.1 | 54.3 → 54.8 | 1310.0 → 1310.0 (0.0) | D | no |
| 42 | 060000 | 240.40–240.43 | W | 49.8 → 49.8 | 72.0 → 72.0 | 1310.0 → 1310.0 (?) | D | no |
| 43 | 060000 | 240.46–240.50 | W | 53.6 → 53.6 | 72.7 → 72.7 | 1310.0 → 1310.0 (?) | D | no |
| 44 | 060000 | 321.45–321.83 | W | 63.2 → 63.2 | 84.5 → 84.5 | 893.0 → 893.0 (0.0) | D | no |
| 45 | 060000 | 329.97–330.20 | W | 48.1 → 48.1 | 40.8 → 40.8 | 859.0 → 859.0 (0.0) | D | yes |
| 46 | 060000 | 330.24–330.43 | W | 48.1 → 48.1 | 40.8 → 40.8 | 859.0 → 859.0 (0.0) | D | yes |
| 47 | 060700 | 15.01–19.15 | R | -18.6 → -14.4 | 48.7 → 54.4 | 1830.0 → 1830.0 (0.0) | D | no |
| 48 | 060700 | 29.82–36.80 | R | 42.0 → 34.6 | 66.7 → 67.4 | 1750.0 → 1750.0 (0.0) | D | no |
| 49 | 061133 | 11.35–16.12 | R | 57.9 → 35.8 | 58.6 → 35.7 | 1270.0 → 1270.0 (0.0) | D | yes |
| 50 | 061133 | 47.98–55.82 | R | 33.6 → -42.9 | 42.5 → -62.8 | 872.0 → 995.0 (123.0) | B | no |
| 51 | 061133 | 85.21–98.74 | R | 32.1 → -52.0 | 52.1 → -73.7 | 538.0 → 490.0 (-48.0) | D | no |
| 52 | 061133 | 100.94–101.06 | W | -51.8 → -51.8 | -73.5 → -73.5 | 490.0 → 490.0 (0.0) | D | no |
| 53 | 061133 | 102.99–103.07 | W | -51.2 → -51.2 | -73.0 → -73.0 | 490.0 → 490.0 (0.0) | D | no |
| 54 | 061133 | 103.81–104.26 | W | -51.2 → -51.2 | -72.9 → -72.9 | 490.0 → 490.0 (0.0) | D | no |
| 55 | 061133 | 104.34–104.49 | W | -51.2 → -51.2 | -72.9 → -72.9 | 490.0 → 490.0 (0.0) | D | no |
| 56 | 061133 | 104.57–104.64 | W | -51.2 → -51.2 | -72.9 → -72.9 | 490.0 → 490.0 (0.0) | D | no |
| 57 | 061133 | 104.72–104.80 | W | -51.2 → -51.2 | -72.9 → -72.9 | 490.0 → 490.0 (0.0) | D | no |
| 58 | 061133 | 106.85–107.01 | W | -51.5 → -51.5 | -73.2 → -73.2 | 490.0 → 490.0 (0.0) | D | no |
| 59 | 061133 | 107.08–107.30 | W | -51.6 → -51.6 | -73.3 → -73.3 | 490.0 → 490.0 (0.0) | D | no |
| 60 | 061133 | 107.46–107.61 | W | -51.6 → -51.6 | -73.3 → -73.3 | 490.0 → 490.0 (0.0) | D | no |
| 61 | 061133 | 108.67–108.78 | W | -51.6 → -51.5 | -73.3 → -73.2 | 490.0 → 490.0 (0.0) | D | no |
| 62 | 061133 | 108.86–108.94 | W | -51.6 → -51.6 | -73.3 → -73.3 | 490.0 → 490.0 (0.0) | D | no |
| 63 | 061133 | 111.02–126.55 | R | -51.6 → 106.9 | -73.3 → 106.0 | 490.0 → 511.0 (21.0) | B | no |
| 64 | 061133 | 148.59–148.63 | W | -7.8 → -7.8 | -53.3 → -53.3 | 342.0 → 342.0 (?) | D | no |
| 65 | 061133 | 148.70–149.62 | W | -7.9 → -7.9 | -53.4 → -53.4 | 342.0 → 342.0 (0.0) | D | no |
| 66 | 061133 | 150.19–150.43 | W | -7.8 → -8.0 | -53.3 → -53.5 | 342.0 → 341.0 (-1.0) | D | no |
| 67 | 061133 | 150.50–150.91 | W | -8.0 → -7.9 | -53.5 → -53.7 | 341.0 → 341.0 (0.0) | D | no |
| 68 | 061659 | 115.28–120.44 | R | -30.6 → 15.2 | -60.8 → -18.2 | 862.0 → 862.0 (0.0) | D | no |
| 69 | 061659 | 167.28–167.32 | W | -38.9 → -38.9 | -50.7 → -50.7 | 819.0 → 819.0 (?) | D | no |
| 70 | 061659 | 167.86–172.84 | R | -38.8 → -12.4 | -50.7 → -25.9 | 819.0 → 819.0 (0.0) | D | yes |
| 71 | 061659 | 186.41–195.65 | R | -1.1 → 13.8 | -0.8 → -10.1 | 745.0 → 752.0 (7.0) | B | yes |
| 72 | 062124 | 83.29–83.40 | W | 30.3 → 30.7 | 50.5 → 49.9 | 411.0 → 411.0 (0.0) | D | no |
| 73 | 062124 | 83.54–83.81 | W | 30.9 → 30.5 | 50.2 → 49.8 | 411.0 → 411.0 (0.0) | D | no |
| 74 | 062124 | 84.28–84.39 | W | 30.5 → 30.5 | 49.7 → 49.8 | 412.0 → 412.0 (0.0) | D | no |
| 75 | 062124 | 84.43–84.54 | W | 30.5 → 30.4 | 49.8 → 49.7 | 412.0 → 412.0 (0.0) | D | no |
| 76 | 062124 | 85.83–86.23 | W | 33.8 → 32.7 | 53.0 → 52.6 | 411.0 → 411.0 (0.0) | D | no |
| 77 | 062124 | 86.30–86.35 | W | 32.1 → 32.1 | 52.1 → 52.1 | 411.0 → 411.0 (?) | D | no |
| 78 | 062124 | 87.14–87.54 | W | 32.7 → 31.9 | 52.0 → 51.9 | 411.0 → 411.0 (0.0) | D | no |
| 79 | 062124 | 87.84–88.14 | W | 32.1 → 32.0 | 51.3 → 51.3 | 411.0 → 411.0 (0.0) | D | no |
| 80 | 062124 | 88.21–88.36 | W | 32.0 → 32.0 | 51.3 → 51.3 | 411.0 → 411.0 (0.0) | D | no |
| 81 | 062124 | 88.44–90.65 | R | 31.9 → 25.7 | 51.2 → 45.4 | 411.0 → 413.0 (2.0) | D | no |
| 82 | 062124 | 94.84–102.36 | R | 38.5 → -76.2 | 59.6 → -48.2 | 411.0 → 421.0 (10.0) | B | no |
| 83 | 062124 | 111.48–111.60 | W | -0.4 → 1.8 | 28.3 → 37.9 | 433.0 → 433.0 (0.0) | D | no |
| 84 | 062411 | 34.70–34.92 | W | -60.7 → -60.4 | -55.4 → -55.0 | 1720.0 → 1720.0 (0.0) | D | no |
| 85 | 062411 | 35.21–35.65 | W | -59.8 → -59.8 | -54.4 → -54.4 | 1720.0 → 1720.0 (0.0) | D | no |
| 86 | 062411 | 36.77–36.82 | W | -60.0 → -60.0 | -54.6 → -54.6 | 1720.0 → 1720.0 (?) | D | no |
| 87 | 062411 | 38.16–38.21 | W | -60.9 → -60.9 | -55.1 → -55.1 | 1720.0 → 1720.0 (?) | D | no |
| 88 | 062411 | 38.67–38.71 | W | -60.9 → -60.9 | -55.1 → -55.1 | 1720.0 → 1720.0 (?) | D | no |
| 89 | 062411 | 79.11–79.50 | W | 54.2 → 54.2 | 53.9 → 53.9 | 1400.0 → 1400.0 (0.0) | D | no |
| 90 | 062411 | 79.76–80.12 | W | 54.2 → 54.3 | 53.9 → 54.0 | 1400.0 → 1400.0 (0.0) | D | no |
| 91 | 062411 | 80.23–80.31 | W | 54.3 → 54.2 | 54.0 → 53.9 | 1400.0 → 1400.0 (0.0) | D | no |
| 92 | 062411 | 80.69–81.19 | W | 54.1 → 53.8 | 53.8 → 53.5 | 1400.0 → 1400.0 (0.0) | D | no |
| 93 | 062411 | 82.21–82.72 | W | 53.8 → 53.7 | 53.5 → 53.4 | 1400.0 → 1400.0 (0.0) | D | yes |
| 94 | 062411 | 83.94–86.22 | R | 53.7 → 38.6 | 53.4 → 44.1 | 1400.0 → 1400.0 (0.0) | D | yes |
| 95 | 062411 | 104.90–104.98 | W | -24.6 → -24.9 | -26.3 → -26.3 | 1370.0 → 1370.0 (0.0) | D | yes |
| 96 | 062411 | 124.24–125.53 | W | -0.8 → -0.6 | -0.3 → -0.1 | 1010.0 → 1010.0 (0.0) | D | yes |
| 97 | 062411 | 125.69–129.68 | R | -0.6 → -34.4 | -0.1 → -32.2 | 1010.0 → 1010.0 (0.0) | D | yes |
| 98 | 062411 | 157.90–158.02 | W | -31.4 → -31.4 | -57.4 → -57.4 | 790.0 → 790.0 (0.0) | D | no |
| 99 | 062755 | 16.29–21.03 | R | -141.2 → -167.5 | -141.2 → -167.5 | 1800.0 → 1800.0 (0.0) | D | no |
| 100 | 062755 | 47.26–48.00 | W | 60.7 → 60.7 | 60.7 → 60.7 | 1820.0 → 1840.0 (20.0) | D | no |
| 101 | 062755 | 49.17–64.01 | R | 60.5 → -10.8 | 60.5 → -13.2 | 1840.0 → 1830.0 (-10.0) | D | no |
| 102 | 062755 | 146.18–146.25 | W | 12.6 → 10.8 | 13.8 → 12.9 | 1680.0 → 1680.0 (0.0) | D | yes |
| 103 | 062755 | 231.34–240.22 | R | -60.6 → 162.8 | -71.6 → 131.2 | 1460.0 → 1490.0 (30.0) | B | no |
| 104 | 062755 | 320.78–320.82 | W | -9.7 → -9.7 | -21.2 → -21.2 | 1480.0 → 1480.0 (?) | D | no |
| 105 | 062755 | 338.37–338.52 | W | -29.0 → -28.9 | -33.2 → -33.0 | 1250.0 → 1250.0 (0.0) | D | no |
| 106 | 062755 | 341.15–342.62 | R | -28.0 → -41.1 | -32.2 → -46.8 | 1250.0 → 1250.0 (0.0) | ? | no |
| 107 | 062755 | 415.19–432.12 | R | 9.2 → 165.1 | 34.0 → -164.7 | 1220.0 → 1200.0 (-20.0) | B | no |
| 108 | 062755 | 473.48–473.52 | W | -12.0 → -12.0 | 43.7 → 43.7 | 1200.0 → 1200.0 (?) | D | no |
| 109 | 062755 | 484.79–485.18 | W | 8.3 → 8.6 | 2.5 → 2.8 | 1040.0 → 1040.0 (0.0) | D | yes |
| 110 | 062755 | 485.78–485.81 | W | 9.0 → 9.0 | 3.2 → 3.2 | ? → ? (?) | D | yes |
| 111 | 062755 | 488.29–491.45 | R | 9.4 → 26.2 | 3.1 → 20.3 | 1040.0 → 1040.0 (0.0) | B | no |
| 112 | 063908 | 12.10–12.71 | W | 39.6 → 39.7 | 45.3 → 45.4 | ? → ? (?) | D | yes |
| 113 | 063908 | 12.75–12.86 | W | 39.7 → 39.7 | 45.4 → 45.4 | ? → ? (?) | D | yes |
| 114 | 063908 | 12.94–13.25 | W | 39.7 → 39.7 | 45.4 → 45.4 | ? → ? (?) | D | yes |
| 115 | 063908 | 13.29–13.64 | W | 39.7 → 39.7 | 45.4 → 45.4 | ? → ? (?) | D | yes |
| 116 | 063908 | 13.76–13.91 | W | 39.7 → 39.7 | 45.4 → 45.4 | ? → ? (?) | D | yes |
| 117 | 063908 | 13.98–14.06 | W | 39.0 → 39.0 | 45.9 → 45.9 | ? → ? (?) | D | yes |
| 118 | 063908 | 14.10–14.21 | W | 39.0 → 39.0 | 45.9 → 45.9 | ? → ? (?) | D | yes |
| 119 | 063908 | 54.26–80.01 | R | 1.9 → -73.1 | 13.7 → -64.5 | 870.0 → 869.0 (-1.0) | B | no |
| 120 | 063908 | 121.12–128.36 | R | 7.3 → 28.6 | -84.4 → -14.7 | 486.0 → 488.0 (2.0) | ? | no |
| 121 | 064206 | 66.69–66.80 | W | 8.5 → 8.8 | 13.8 → 14.1 | 1620.0 → 1620.0 (0.0) | D | yes |
| 122 | 064206 | 70.09–70.13 | W | 3.1 → 3.1 | 6.3 → 6.3 | 1560.0 → 1560.0 (?) | D | yes |
| 123 | 064206 | 70.17–70.52 | W | 3.2 → 3.9 | 6.3 → 6.2 | 1560.0 → 1560.0 (0.0) | D | yes |
| 124 | 064206 | 70.56–70.80 | W | 3.2 → 3.2 | 5.1 → 5.2 | 1560.0 → 1560.0 (0.0) | D | yes |
| 125 | 064206 | 70.88–71.03 | W | 3.2 → 3.2 | 5.5 → 5.6 | 1560.0 → 1560.0 (0.0) | D | yes |
| 126 | 064206 | 71.19–71.34 | W | 3.3 → 3.2 | 5.6 → 5.5 | 1560.0 → 1560.0 (0.0) | D | yes |
| 127 | 064206 | 71.49–71.86 | W | 3.2 → 3.0 | 5.5 → 5.4 | 1560.0 → 1560.0 (0.0) | D | yes |
| 128 | 064206 | 71.90–72.44 | W | 3.0 → 3.0 | 5.4 → 5.3 | 1560.0 → 1560.0 (0.0) | D | yes |
| 129 | 064206 | 72.84–77.35 | R | 3.0 → 174.2 | 5.0 → 174.2 | 1560.0 → 1560.0 (0.0) | D | yes |
| 130 | 064206 | 80.10–80.45 | W | 20.4 → 14.8 | 20.9 → 16.0 | 1560.0 → 1560.0 (0.0) | D | yes |
| 131 | 064206 | 81.12–81.16 | W | 7.1 → 7.1 | 7.7 → 7.7 | 1560.0 → 1560.0 (?) | D | yes |
| 132 | 064206 | 84.05–104.67 | R | 7.9 → -15.3 | 8.3 → -3.0 | 1550.0 → 1560.0 (10.0) | B | yes |
| 133 | 064206 | 166.71–170.39 | R | -16.6 → -16.7 | -13.7 → -13.9 | 630.0 → 631.0 (1.0) | D | no |
| 134 | 064206 | 204.22–204.38 | W | -1.0 → -0.9 | -2.4 → -2.3 | ? → ? (?) | D | yes |
| 135 | 064206 | 205.07–216.82 | R | -0.9 → 73.6 | -2.4 → 61.3 | 502.0 → 520.0 (18.0) | D | no |
| 136 | 064206 | 235.76–235.80 | W | -6.5 → -6.5 | -12.8 → -12.8 | 523.0 → 523.0 (?) | D | yes |
| 137 | 064206 | 235.83–235.88 | W | -6.6 → -6.6 | -12.7 → -12.7 | 523.0 → 523.0 (?) | D | yes |
| 138 | 064206 | 236.21–236.25 | W | -6.8 → -6.8 | -13.2 → -13.2 | 523.0 → 523.0 (?) | D | yes |
| 139 | 064206 | 236.29–236.38 | W | -6.8 → -6.5 | -12.4 → -12.8 | 523.0 → 523.0 (0.0) | D | yes |
| 140 | 064206 | 236.49–236.53 | W | -6.2 → -6.2 | -12.5 → -12.5 | 523.0 → 523.0 (?) | D | yes |
| 141 | 064206 | 236.68–236.76 | W | -6.3 → -6.9 | -12.8 → -12.9 | 523.0 → 523.0 (0.0) | D | yes |
| 142 | 064206 | 236.90–236.94 | W | -6.7 → -6.7 | -13.0 → -13.0 | 523.0 → 523.0 (?) | D | yes |
| 143 | 064206 | 236.97–237.06 | W | -6.6 → -7.0 | -12.6 → -13.0 | 523.0 → 523.0 (0.0) | D | yes |
| 144 | 064206 | 237.35–237.38 | W | -6.0 → -6.0 | -12.4 → -12.4 | 523.0 → 523.0 (?) | D | yes |
| 145 | 064206 | 237.46–237.56 | W | -6.6 → -6.6 | -12.6 → -12.7 | 523.0 → 523.0 (0.0) | D | yes |
| 146 | 064206 | 237.97–242.88 | R | -6.2 → -42.8 | -12.4 → -46.7 | 523.0 → 523.0 (0.0) | D | no |
| 147 | 064206 | 245.99–250.36 | R | -39.0 → -27.2 | -43.3 → -30.5 | ? → ? (?) | D | no |
| 148 | 064206 | 252.78–256.91 | R | -25.6 → -3.2 | -30.0 → -7.9 | ? → ? (?) | D | yes |
| 149 | 064206 | 269.21–269.25 | W | -17.2 → -17.2 | -21.4 → -21.4 | ? → ? (?) | D | yes |
| 150 | 064206 | 269.32–269.36 | W | -17.2 → -17.2 | -21.4 → -21.4 | ? → ? (?) | D | yes |
| 151 | 064206 | 270.00–274.05 | R | -17.2 → -9.8 | -21.4 → -14.3 | ? → ? (?) | D | yes |
| 152 | 064206 | 279.32–279.40 | W | -8.1 → -8.1 | -13.7 → -13.7 | ? → ? (?) | D | yes |
| 153 | 064206 | 279.43–279.47 | W | -8.1 → -8.1 | -13.7 → -13.7 | ? → ? (?) | D | yes |
| 154 | 064206 | 279.51–279.54 | W | -8.1 → -8.1 | -13.7 → -13.7 | ? → ? (?) | D | yes |
| 155 | 064206 | 279.62–279.73 | W | -8.1 → -8.1 | -13.7 → -13.7 | ? → ? (?) | D | yes |
| 156 | 064206 | 279.82–279.94 | W | -8.2 → -8.2 | -13.8 → -13.8 | ? → ? (?) | D | yes |
| 157 | 064206 | 280.01–280.27 | W | -8.1 → -8.0 | -13.7 → -13.4 | ? → ? (?) | D | yes |
| 158 | 064206 | 280.32–280.36 | W | -6.9 → -6.9 | -13.2 → -13.2 | ? → ? (?) | D | yes |
| 159 | 064206 | 280.56–280.67 | W | -6.7 → -6.8 | -13.0 → -13.1 | ? → ? (?) | D | yes |
| 160 | 064206 | 280.82–280.89 | W | -6.9 → -6.9 | -13.2 → -13.2 | ? → ? (?) | D | yes |
| 161 | 064206 | 281.48–281.71 | W | -7.0 → -7.0 | -13.5 → -13.5 | ? → ? (?) | D | yes |
| 162 | 064206 | 281.79–281.86 | W | -7.1 → -7.1 | -13.6 → -13.6 | ? → ? (?) | D | yes |
| 163 | 064206 | 284.40–284.44 | W | -7.7 → -7.7 | -12.8 → -12.8 | ? → ? (?) | D | yes |
| 164 | 064206 | 284.51–284.59 | W | -7.7 → -7.7 | -12.8 → -12.8 | ? → ? (?) | D | yes |
| 165 | 064206 | 285.22–289.25 | R | -7.7 → 0.7 | -12.8 → -3.5 | ? → ? (?) | D | yes |
| 166 | 064206 | 293.43–293.55 | W | -9.1 → -9.1 | -14.6 → -14.6 | ? → ? (?) | D | yes |
| 167 | 064206 | 294.37–294.41 | W | -9.1 → -9.1 | -14.6 → -14.6 | ? → ? (?) | D | yes |
| 168 | 064206 | 297.66–297.74 | W | -9.0 → -9.0 | -14.5 → -14.5 | ? → ? (?) | D | yes |
| 169 | 064206 | 298.61–298.65 | W | -9.1 → -9.1 | -14.5 → -14.5 | ? → ? (?) | D | yes |
| 170 | 064206 | 299.26–299.49 | W | -9.2 → -9.2 | -14.7 → -14.7 | ? → ? (?) | D | yes |
| 171 | 064206 | 300.23–300.27 | W | -9.1 → -9.1 | -14.6 → -14.6 | ? → ? (?) | D | yes |
| 172 | 064206 | 305.37–305.45 | W | -9.0 → -8.9 | -14.5 → -14.4 | ? → ? (?) | D | yes |
| 173 | 064206 | 309.93–310.00 | W | -9.0 → -9.0 | -14.4 → -14.5 | ? → ? (?) | D | yes |
| 174 | 064206 | 311.33–311.37 | W | -9.1 → -9.1 | -14.6 → -14.6 | ? → ? (?) | D | yes |
| 175 | 064206 | 313.23–313.30 | W | -9.1 → -9.2 | -14.6 → -14.6 | ? → ? (?) | D | yes |
| 176 | 064206 | 313.85–313.88 | W | -8.9 → -8.9 | -14.4 → -14.4 | ? → ? (?) | D | yes |
| 177 | 064206 | 314.75–314.78 | W | -9.1 → -9.1 | -14.6 → -14.6 | ? → ? (?) | D | yes |
| 178 | 064206 | 315.37–315.64 | W | -9.2 → -9.2 | -14.6 → -14.6 | ? → ? (?) | D | yes |
| 179 | 064206 | 316.40–316.44 | W | -9.3 → -9.3 | -14.8 → -14.8 | ? → ? (?) | D | yes |
| 180 | 064206 | 318.21–318.25 | W | -9.0 → -9.0 | -14.5 → -14.5 | ? → ? (?) | D | yes |
| 181 | 064206 | 318.29–318.33 | W | -9.1 → -9.1 | -14.6 → -14.6 | ? → ? (?) | D | yes |
| 182 | 064206 | 318.37–318.44 | W | -9.1 → -9.1 | -14.6 → -14.5 | ? → ? (?) | D | yes |
| 183 | 064206 | 319.19–319.23 | W | -9.1 → -9.1 | -14.5 → -14.5 | ? → ? (?) | D | yes |
| 184 | 064206 | 319.42–319.46 | W | -9.2 → -9.2 | -14.7 → -14.7 | ? → ? (?) | D | yes |
| 185 | 064206 | 321.24–321.28 | W | -9.2 → -9.2 | -14.7 → -14.7 | ? → ? (?) | D | yes |
| 186 | 064206 | 321.32–321.35 | W | -9.3 → -9.3 | -14.8 → -14.8 | ? → ? (?) | D | yes |
| 187 | 064206 | 324.62–324.66 | W | -9.1 → -9.1 | -14.4 → -14.4 | ? → ? (?) | D | yes |
| 188 | 064206 | 325.57–325.61 | W | -9.1 → -9.1 | -14.6 → -14.6 | ? → ? (?) | D | yes |
| 189 | 064206 | 325.80–325.99 | W | -9.2 → -9.2 | -14.7 → -14.7 | ? → ? (?) | D | yes |
| 190 | 064206 | 326.91–326.94 | W | -9.0 → -9.0 | -14.5 → -14.5 | ? → ? (?) | D | yes |
| 191 | 064206 | 328.13–328.91 | W | -9.0 → -8.8 | -14.5 → -14.3 | ? → ? (?) | D | yes |
| 192 | 064206 | 329.55–330.31 | W | -8.9 → -8.8 | -14.4 → -14.3 | ? → ? (?) | D | yes |
| 193 | 064206 | 330.55–332.80 | R | -8.8 → -17.7 | -14.3 → -22.9 | ? → ? (?) | D | no |
| 194 | 064206 | 338.83–338.94 | W | -30.0 → -30.0 | -34.7 → -34.7 | ? → ? (?) | D | no |
| 195 | 064206 | 339.69–339.73 | W | -30.7 → -30.7 | -35.5 → -35.5 | ? → ? (?) | D | no |
| 196 | 064206 | 339.77–339.81 | W | -30.6 → -30.6 | -35.5 → -35.5 | ? → ? (?) | D | no |
| 197 | 064206 | 339.85–339.89 | W | -31.3 → -31.3 | -36.1 → -36.1 | ? → ? (?) | D | no |
| 198 | 064206 | 339.93–339.97 | W | -31.5 → -31.5 | -36.3 → -36.3 | ? → ? (?) | D | no |
| 199 | 064206 | 340.01–340.21 | W | -31.2 → -31.2 | -36.0 → -36.0 | ? → ? (?) | D | no |
| 200 | 064206 | 340.28–340.44 | W | -31.0 → -31.0 | -35.8 → -35.8 | ? → ? (?) | D | no |
| 201 | 064206 | 340.52–340.55 | W | -31.0 → -31.0 | -35.8 → -35.8 | ? → ? (?) | D | no |
| 202 | 064206 | 343.61–347.71 | R | -25.0 → -19.1 | -30.3 → -23.9 | ? → ? (?) | D | yes |
| 203 | 064206 | 350.54–351.43 | W | -10.9 → -10.7 | -16.3 → -16.1 | 509.0 → 509.0 (0.0) | D | yes |
| 204 | 064206 | 351.47–351.85 | W | -10.7 → -10.7 | -16.1 → -16.1 | 509.0 → 509.0 (0.0) | D | yes |
| 205 | 064206 | 352.73–352.92 | W | -13.3 → -14.7 | -17.4 → -19.0 | 509.0 → 509.0 (0.0) | D | yes |
| 206 | 064206 | 352.96–353.25 | W | -15.0 → -13.6 | -19.5 → -18.7 | 509.0 → 508.0 (-1.0) | D | yes |
| 207 | 064206 | 353.29–353.36 | W | -12.6 → -12.5 | -17.7 → -17.6 | 508.0 → 508.0 (0.0) | D | yes |
| 208 | 064206 | 353.44–353.56 | W | -11.8 → -11.7 | -16.9 → -16.8 | 508.0 → 508.0 (0.0) | D | yes |
| 209 | 064206 | 356.46–356.50 | W | -8.7 → -8.7 | -14.8 → -14.8 | 505.0 → 505.0 (?) | D | yes |
| 210 | 064206 | 356.58–362.02 | R | -8.5 → -132.6 | -14.7 → -132.6 | 505.0 → 516.0 (11.0) | ? | no |
| 211 | 064206 | 364.42–365.44 | W | -78.9 → -79.0 | -78.3 → -78.3 | 514.0 → 514.0 (0.0) | D | no |
| 212 | 064206 | 367.64–369.52 | W | -72.4 → -65.8 | -74.4 → -68.3 | 513.0 → 513.0 (0.0) | D | no |
| 213 | 064206 | 369.76–369.80 | W | -65.8 → -65.8 | -68.0 → -68.0 | 513.0 → 513.0 (?) | D | no |
| 214 | 064206 | 371.10–375.92 | R | -66.5 → -67.8 | -69.1 → -66.1 | 513.0 → 514.0 (1.0) | D | no |
| 215 | 065053 | 98.94–106.38 | R | -132.2 → -50.9 | -116.2 → -28.1 | 1620.0 → 1650.0 (30.0) | D | yes |
| 216 | 065053 | 107.61–107.65 | W | -6.6 → -6.6 | 21.7 → 21.7 | 1650.0 → 1650.0 (?) | D | no |
| 217 | 065053 | 185.77–194.97 | R | 16.9 → 52.0 | 19.6 → 10.1 | 856.0 → 818.0 (-38.0) | B | yes |
| 218 | 065053 | 257.55–263.72 | R | -53.9 → -133.5 | -54.4 → -134.9 | 304.0 → 301.0 (-3.0) | D | no |
| 219 | 065053 | 292.75–293.24 | W | 73.8 → 73.7 | 78.3 → 78.1 | 103.0 → 103.0 (0.0) | D | no |
| 220 | 065053 | 293.80–295.98 | R | 73.9 → 74.7 | 78.4 → 78.3 | 103.0 → 103.0 (0.0) | D | no |
| 221 | 065053 | 299.52–299.77 | W | 74.9 → 74.2 | 78.1 → 78.3 | 103.0 → 103.0 (0.0) | D | no |
| 222 | 065053 | 300.34–305.25 | R | 74.8 → 98.0 | 78.3 → 99.5 | 103.0 → 102.0 (-1.0) | D | no |
| 223 | 065700 | 141.24–141.35 | W | -31.0 → -30.9 | -38.3 → -38.1 | ? → ? (?) | D | no |
| 224 | 065700 | 141.40–141.52 | W | -31.0 → -30.8 | -38.3 → -38.1 | ? → ? (?) | D | no |
| 225 | 065700 | 141.73–141.80 | W | -30.9 → -30.9 | -38.2 → -38.2 | ? → ? (?) | D | yes |
| 226 | 065700 | 142.79–146.58 | R | -31.1 → -6.0 | -38.4 → -9.5 | 513.0 → 517.0 (4.0) | D | yes |
| 227 | 065700 | 152.41–152.48 | W | 3.1 → 2.9 | -1.7 → -1.9 | 493.0 → 493.0 (0.0) | D | yes |
| 228 | 065700 | 152.52–152.59 | W | 2.8 → 2.5 | -2.7 → -2.9 | 493.0 → 493.0 (0.0) | D | yes |
| 229 | 070018 | 16.99–17.06 | W | -14.1 → -13.7 | 51.7 → 52.1 | 1810.0 → 1810.0 (0.0) | D | no |
| 230 | 070018 | 17.26–17.30 | W | -12.3 → -12.3 | 54.5 → 54.5 | 1810.0 → 1810.0 (?) | D | no |
| 231 | 070018 | 18.52–37.31 | R | -9.1 → -152.5 | 55.7 → -128.3 | 1810.0 → 1960.0 (150.0) | D | no |
| 232 | 070018 | 71.65–75.98 | R | 113.2 → -19.6 | 98.0 → -35.4 | 1850.0 → 1850.0 (0.0) | D | no |
| 233 | 070018 | 76.55–76.66 | W | -20.5 → -20.5 | -35.6 → -35.6 | 1850.0 → 1850.0 (0.0) | D | yes |
| 234 | 070018 | 76.78–76.85 | W | -20.5 → -20.5 | -35.6 → -35.6 | 1850.0 → 1850.0 (0.0) | D | yes |
| 235 | 070018 | 77.27–81.19 | R | -20.5 → -1.0 | -35.6 → -17.4 | 1850.0 → 1850.0 (0.0) | D | yes |
| 236 | 070018 | 86.61–86.88 | W | -105.1 → -104.8 | -111.5 → -111.6 | 1890.0 → 1890.0 (0.0) | D | no |
| 237 | 070018 | 86.99–87.74 | W | -104.8 → -104.9 | -111.6 → -111.7 | 1890.0 → 1830.0 (-60.0) | D | no |
| 238 | 070018 | 87.81–91.12 | R | -104.9 → -120.2 | -111.7 → -128.9 | 1830.0 → 1830.0 (0.0) | D | no |
| 239 | 070018 | 112.30–115.59 | R | 48.0 → 88.2 | 75.1 → 113.4 | 1750.0 → 1750.0 (0.0) | D | no |
| 240 | 070018 | 123.80–125.41 | R | 44.6 → 40.1 | 60.7 → 61.4 | 1740.0 → 1750.0 (10.0) | D | no |
| 241 | 070018 | 139.49–143.39 | R | -10.5 → -51.8 | -9.5 → -44.4 | 1660.0 → 1660.0 (0.0) | D | yes |
| 242 | 070018 | 232.70–232.77 | W | -94.4 → -94.4 | -97.4 → -97.4 | 240.0 → 240.0 (0.0) | D | no |
| 243 | 070018 | 233.40–237.80 | R | -93.9 → -128.5 | -97.0 → -126.0 | 240.0 → 239.0 (-1.0) | D | no |
| 244 | 070018 | 246.64–251.91 | R | -53.9 → -148.8 | -58.8 → -146.7 | 238.0 → 233.0 (-5.0) | D | no |
| 245 | 070454 | 71.44–75.54 | R | 31.2 → -3.1 | 52.3 → 21.6 | 548.0 → 548.0 (0.0) | D | yes |
| 246 | 070454 | 98.16–98.53 | W | -23.5 → -23.5 | -61.5 → -61.5 | 327.0 → 327.0 (0.0) | D | no |
| 247 | 070454 | 99.18–99.89 | W | -23.7 → -33.2 | -61.8 → -63.5 | 327.0 → 327.0 (0.0) | D | no |
| 248 | 070707 | 79.55–85.06 | R | 5.4 → 106.2 | -20.5 → 106.2 | 1350.0 → 1350.0 (0.0) | D | no |
| 249 | 070707 | 114.75–123.11 | R | 2.9 → 20.4 | -0.9 → 14.3 | 1080.0 → 1090.0 (10.0) | B | yes |
| 250 | 070707 | 148.22–153.00 | R | -4.7 → -63.3 | -2.3 → -57.6 | 612.0 → 612.0 (0.0) | D | yes |
| 251 | 070707 | 163.24–172.40 | R | -9.2 → 37.2 | -3.9 → 17.5 | 565.0 → 562.0 (-3.0) | B | no |
| 252 | 071049 | 152.07–155.71 | R | 51.2 → 73.1 | 62.8 → 82.4 | 404.0 → 405.0 (1.0) | D | no |
| 253 | 071436 | 73.57–76.69 | R | 39.0 → 24.8 | 85.7 → 75.0 | 1040.0 → 1040.0 (0.0) | D | no |
| 254 | 071436 | 97.08–103.75 | R | -73.5 → -83.8 | -104.9 → -116.1 | 874.0 → 874.0 (0.0) | B | no |
| 255 | 071436 | 104.68–111.20 | R | -83.8 → -96.9 | -116.1 → -131.4 | 874.0 → 874.0 (0.0) | B | no |
| 256 | 071436 | 289.98–292.74 | R | 23.9 → 21.7 | 34.3 → 31.5 | 1300.0 → 1300.0 (0.0) | D | no |
| 257 | 071436 | 297.17–302.00 | R | 14.0 → -103.0 | 24.4 → -98.8 | 1290.0 → 1300.0 (10.0) | B | no |
| 258 | 071436 | 607.21–607.25 | W | -12.6 → -12.6 | -57.6 → -57.6 | 628.0 → 628.0 (?) | D | no |
| 259 | 071436 | 608.21–612.30 | R | -11.5 → -13.1 | -57.0 → -12.4 | 623.0 → 626.0 (3.0) | D | yes |
| 260 | 071436 | 690.46–690.50 | W | -11.0 → -11.0 | -14.2 → -14.2 | 413.0 → 413.0 (?) | D | yes |
| 261 | 071436 | 690.61–690.65 | W | -14.6 → -14.6 | -16.4 → -16.4 | 413.0 → 413.0 (?) | D | yes |
| 262 | 071436 | 697.19–697.26 | W | -8.0 → -8.4 | -11.2 → -11.6 | 408.0 → 408.0 (0.0) | D | yes |
| 263 | 071436 | 716.69–730.22 | R | -48.6 → 19.6 | -79.5 → 20.4 | 205.0 → 185.0 (-20.0) | B | yes |
| 264 | 072659 | 24.99–25.03 | W | -30.5 → -30.5 | -67.9 → -67.9 | 1790.0 → 1790.0 (?) | D | no |
| 265 | 072659 | 48.97–52.30 | R | -1.6 → 34.1 | -6.5 → 30.1 | 1390.0 → 1400.0 (10.0) | D | yes |
| 266 | 072659 | 134.36–134.44 | W | -2.9 → -0.0 | -12.9 → -14.2 | 248.0 → 248.0 (0.0) | D | yes |
| 267 | 072659 | 138.42–139.07 | W | -6.2 → -6.2 | -10.2 → -10.1 | 246.0 → 246.0 (0.0) | D | yes |
| 268 | 072659 | 140.24–142.97 | R | -5.4 → -1.4 | -10.4 → -1.9 | 246.0 → 250.0 (4.0) | D | yes |
| 269 | 072659 | 148.31–151.68 | R | 3.5 → -1.1 | -6.7 → -0.3 | 244.0 → 250.0 (6.0) | D | yes |
| 270 | 072659 | 229.46–236.69 | R | 40.0 → -105.2 | 40.0 → -103.4 | 79.0 → 82.0 (3.0) | D | no |
| 271 | 072659 | 403.94–413.02 | R | 77.7 → -92.2 | 89.5 → -10.5 | 883.0 → 899.0 (16.0) | B | no |
| 272 | 072659 | 428.58–428.63 | W | 7.2 → 7.2 | -3.0 → -3.0 | 1210.0 → 1210.0 (?) | D | yes |
| 273 | 072659 | 429.11–429.23 | W | 9.1 → 7.6 | -2.3 → -4.1 | 1210.0 → 1210.0 (0.0) | D | yes |
| 274 | 072659 | 489.20–489.34 | W | 8.5 → 8.5 | 10.9 → 10.9 | 355.0 → 355.0 (0.0) | D | no |
| 275 | 072659 | 490.89–493.14 | R | 8.5 → 9.7 | 10.9 → 10.9 | 355.0 → 355.0 (0.0) | D | no |
| 276 | 072659 | 494.80–495.40 | F | 8.4 → 9.2 | 8.9 → 9.7 | 356.0 → 356.0 (0.0) | ? | no |
| 277 | 072659 | 497.10–506.76 | R | 15.4 → 19.9 | 15.6 → 17.4 | 355.0 → 359.0 (4.0) | B | yes |
| 278 | 073626 | 24.60–42.40 | R | -75.6 → 177.8 | -110.4 → -176.7 | 1830.0 → 1830.0 (0.0) | D | no |
| 279 | 073626 | 48.19–54.57 | R | 165.8 → 46.4 | 168.0 → 38.1 | 1830.0 → 1840.0 (10.0) | D | yes |
| 280 | 073626 | 70.75–74.89 | R | 8.0 → 15.0 | 5.4 → 12.1 | 1710.0 → 1710.0 (0.0) | D | yes |
| 281 | 073626 | 78.91–79.10 | W | 1.5 → 0.2 | -0.8 → -3.1 | 1710.0 → 1710.0 (0.0) | D | yes |
| 282 | 073626 | 100.12–100.47 | W | 9.9 → 10.1 | 10.8 → 11.0 | 1360.0 → 1360.0 (0.0) | D | yes |
| 283 | 073626 | 101.70–101.86 | W | 13.4 → 14.4 | 13.6 → 14.6 | 1360.0 → 1360.0 (0.0) | D | yes |
| 284 | 073626 | 102.08–102.36 | W | 13.9 → 13.5 | 14.1 → 13.7 | 1360.0 → 1360.0 (0.0) | D | yes |
| 285 | 073626 | 104.40–113.19 | R | 18.2 → -62.8 | 18.4 → -60.1 | 1360.0 → 1380.0 (20.0) | B | no |
| 286 | 073626 | 147.12–154.23 | R | 6.8 → 166.5 | 10.1 → 166.2 | 1350.0 → 1350.0 (0.0) | D | no |
| 287 | 073626 | 189.64–189.72 | W | 74.3 → 73.8 | 80.7 → 80.0 | 1280.0 → 1280.0 (0.0) | D | yes |
| 288 | 073626 | 194.56–194.60 | W | 9.3 → 9.3 | 10.7 → 10.7 | 1270.0 → 1270.0 (?) | D | yes |
| 289 | 073626 | 202.09–206.25 | R | -12.5 → -53.7 | -8.7 → -49.0 | 1220.0 → 1220.0 (0.0) | D | no |
| 290 | 073626 | 240.29–243.73 | R | -112.2 → -103.7 | -112.1 → -105.9 | 1210.0 → 1210.0 (0.0) | B | no |
| 291 | 073626 | 244.74–257.87 | R | -101.4 → -89.0 | -106.3 → -95.0 | 1210.0 → 1210.0 (0.0) | B | no |
| 292 | 073626 | 260.17–263.89 | R | -87.7 → -87.2 | -94.2 → -90.2 | 1210.0 → 1210.0 (0.0) | B | no |
| 293 | 073626 | 274.09–274.42 | W | -82.3 → -83.0 | -87.2 → -88.2 | 1210.0 → 1210.0 (0.0) | D | no |
| 294 | 073626 | 274.57–274.68 | W | -80.7 → -81.9 | -87.2 → -87.8 | 1210.0 → 1210.0 (0.0) | D | no |
| 295 | 073626 | 274.72–278.20 | R | -81.0 → -81.7 | -88.0 → -88.0 | 1210.0 → 1210.0 (0.0) | D | no |
| 296 | 073626 | 280.86–296.56 | R | -79.8 → -81.5 | -87.2 → -88.7 | 1210.0 → 1210.0 (0.0) | ? | no |
| 297 | 074427 | 29.38–33.51 | R | 51.8 → -34.8 | 63.5 → -16.1 | 1150.0 → 1150.0 (0.0) | D | no |
| 298 | 074427 | 53.91–53.94 | W | 32.7 → 32.7 | 40.2 → 40.2 | 1150.0 → 1150.0 (?) | D | yes |
| 299 | 074427 | 61.16–84.90 | R | 25.4 → 86.6 | 32.1 → 56.9 | 1110.0 → 1090.0 (-20.0) | ? | no |
| 300 | 074427 | 131.59–132.09 | W | 64.1 → 65.9 | 80.5 → 82.4 | ? → ? (?) | D | no |
| 301 | 074427 | 132.27–138.96 | R | 66.6 → 30.6 | 83.3 → 49.8 | ? → ? (?) | D | no |
| 302 | 074427 | 160.60–165.64 | R | 47.7 → -174.9 | 63.1 → -174.9 | 1190.0 → 1180.0 (-10.0) | D | yes |
| 303 | 074427 | 209.37–211.02 | W | 26.7 → 26.7 | 44.2 → 44.2 | 538.0 → 538.0 (0.0) | D | no |
| 304 | 074427 | 211.38–227.13 | R | 26.2 → -102.0 | 43.7 → -67.4 | 538.0 → 544.0 (6.0) | B | no |
| 305 | 074427 | 230.67–230.74 | W | -102.5 → -102.5 | -67.9 → -67.9 | 544.0 → 544.0 (0.0) | D | no |
| 306 | 074427 | 241.86–246.51 | R | -103.9 → -75.1 | -71.7 → -47.1 | 544.0 → 542.0 (-2.0) | D | no |
| 307 | 074427 | 248.30–252.79 | R | -78.0 → -98.0 | -48.5 → -67.8 | 543.0 → 543.0 (0.0) | D | no |
| 308 | 074427 | 328.13–329.24 | W | 22.8 → 22.9 | 22.8 → 22.9 | 88.0 → 88.0 (0.0) | D | yes |
| 309 | 074427 | 330.67–333.81 | R | 23.0 → 7.7 | 23.0 → 7.7 | 88.0 → 88.0 (0.0) | D | yes |
| 310 | 075023 | 64.86–65.32 | W | 5.7 → 5.2 | 8.8 → 8.2 | 1550.0 → 1550.0 (0.0) | D | yes |
| 311 | 075023 | 65.47–65.85 | W | 5.0 → 4.7 | 8.0 → 7.6 | 1550.0 → 1550.0 (0.0) | D | yes |
| 312 | 075023 | 66.19–68.90 | R | 4.3 → 40.6 | 7.3 → 40.0 | 1550.0 → 1550.0 (0.0) | ? | yes |
| 313 | 075023 | 93.60–102.54 | R | -39.8 → -110.3 | -62.4 → -112.4 | 1250.0 → 1270.0 (20.0) | D | no |
| 314 | 075023 | 186.12–189.99 | R | -15.6 → -11.5 | -33.8 → -29.8 | 1250.0 → 1250.0 (0.0) | D | yes |
| 315 | 075023 | 383.87–383.99 | W | 11.5 → 11.4 | 56.1 → 56.0 | 900.0 → 900.0 (0.0) | D | no |
| 316 | 075023 | 384.07–384.11 | W | 11.4 → 11.4 | 56.1 → 56.1 | 900.0 → 900.0 (?) | D | no |
| 317 | 075023 | 384.34–388.30 | R | 11.4 → 8.1 | 56.1 → 55.4 | 900.0 → 901.0 (1.0) | D | no |
| 318 | 075023 | 391.99–397.35 | R | 43.8 → 19.2 | 67.1 → 36.8 | 895.0 → 896.0 (1.0) | D | no |
| 319 | 075023 | 401.99–406.36 | R | 11.5 → -41.6 | 37.2 → -20.3 | 896.0 → 895.0 (-1.0) | D | no |
| 320 | 075023 | 481.28–484.99 | R | 2.1 → -4.7 | 6.3 → -1.1 | 628.0 → 628.0 (0.0) | D | yes |
| 321 | 075023 | 605.26–605.89 | W | -8.5 → -6.2 | -8.7 → -7.2 | 554.0 → 554.0 (0.0) | D | yes |
| 322 | 075023 | 606.33–607.82 | R | -8.2 → -8.1 | -8.0 → -7.9 | 554.0 → 554.0 (0.0) | D | yes |
| 323 | 075023 | 608.44–610.64 | R | -7.2 → -14.6 | -8.2 → -15.5 | 554.0 → 557.0 (3.0) | ? | yes |
| 324 | 075023 | 621.43–622.66 | R | -31.3 → -20.7 | -32.9 → -23.5 | 523.0 → 525.0 (2.0) | ? | yes |
| 325 | 075023 | 640.42–643.45 | R | -1.5 → -7.7 | -3.6 → -9.2 | 404.0 → 405.0 (1.0) | D | no |
| 326 | 075023 | 644.01–644.20 | F | -11.5 → -12.6 | -13.9 → -13.4 | 404.0 → 404.0 (0.0) | ? | no |
| 327 | 075023 | 644.75–645.09 | R | -9.9 → -12.2 | -10.0 → -11.9 | 404.0 → 404.0 (0.0) | ? | no |
| 328 | 075023 | 835.39–835.47 | W | 23.9 → 23.9 | 24.2 → 24.2 | 402.0 → 402.0 (0.0) | D | no |
| 329 | 075023 | 835.69–835.84 | W | 23.0 → 22.5 | 24.4 → 23.9 | 402.0 → 401.0 (-1.0) | D | no |
| 330 | 075023 | 836.68–841.56 | R | 22.4 → 53.9 | 23.9 → 50.4 | 401.0 → 400.0 (-1.0) | D | yes |
| 331 | 080500 | 54.39–60.24 | R | -10.9 → 148.9 | -27.9 → 119.2 | 1870.0 → 1880.0 (10.0) | D | no |
| 332 | 080500 | 71.76–82.06 | R | -17.7 → 39.1 | -22.9 → 15.4 | 1830.0 → 1820.0 (-10.0) | B | yes |
| 333 | 080500 | 147.44–149.05 | W | 44.1 → 44.0 | 65.7 → 65.6 | 939.0 → 939.0 (0.0) | D | no |
| 334 | 080500 | 149.22–152.59 | R | 44.0 → 83.3 | 65.6 → 105.4 | 939.0 → 940.0 (1.0) | D | no |
| 335 | 080500 | 154.36–154.41 | W | 80.5 → 80.5 | 104.5 → 104.5 | 941.0 → 941.0 (?) | D | no |
| 336 | 080500 | 154.97–155.33 | W | 80.5 → 79.3 | 104.5 → 104.7 | 941.0 → 941.0 (0.0) | D | no |
| 337 | 080500 | 155.83–155.91 | W | 80.7 → 80.7 | 104.7 → 104.7 | 941.0 → 941.0 (0.0) | D | no |
| 338 | 080500 | 155.98–156.10 | W | 80.7 → 80.7 | 104.7 → 104.7 | 941.0 → 941.0 (0.0) | D | no |
| 339 | 080500 | 156.18–156.47 | W | 80.8 → 80.9 | 104.8 → 104.5 | 941.0 → 941.0 (0.0) | D | no |
| 340 | 080500 | 156.79–156.90 | W | 80.9 → 80.9 | 104.5 → 104.5 | 941.0 → 941.0 (0.0) | D | no |
| 341 | 080500 | 157.19–157.45 | W | 80.9 → 80.9 | 104.5 → 104.5 | 941.0 → 941.0 (0.0) | D | no |
| 342 | 080500 | 157.68–157.75 | W | 80.9 → 80.9 | 104.5 → 104.5 | 941.0 → 941.0 (0.0) | D | no |
| 343 | 080500 | 157.83–163.17 | R | 80.9 → 40.7 | 104.5 → 57.3 | 941.0 → 938.0 (-3.0) | D | yes |
| 344 | 080500 | 183.59–187.29 | R | 7.3 → 50.2 | -33.0 → -7.0 | 650.0 → 652.0 (2.0) | D | no |
| 345 | 080500 | 198.73–200.58 | R | -49.8 → -49.8 | -68.2 → -68.2 | 569.0 → 569.0 (0.0) | D | no |
| 346 | 080500 | 202.08–203.69 | F | -45.4 → -57.6 | -64.2 → -77.8 | 570.0 → 569.0 (-1.0) | ? | no |
| 347 | 080500 | 205.22–206.02 | F | -58.2 → -65.8 | -78.4 → -82.4 | 569.0 → 569.0 (0.0) | ? | no |
| 348 | 081506 | 108.20–112.37 | R | -8.8 → 62.5 | 2.8 → 63.8 | 1570.0 → 1570.0 (0.0) | B | no |
| 349 | 110153 | 36.24–38.29 | R | 56.8 → 56.8 | 61.6 → 61.6 | 1570.0 → 1570.0 (0.0) | D | no |
| 350 | 110153 | 68.97–73.13 | R | 56.3 → 39.5 | 60.9 → 44.5 | 1570.0 → 1580.0 (10.0) | D | yes |
| 351 | 110153 | 110.57–113.24 | R | 6.3 → 36.0 | 11.2 → 43.4 | 1180.0 → 1190.0 (10.0) | ? | no |
| 352 | 110153 | 113.99–117.13 | R | 36.4 → 35.2 | 44.9 → 53.5 | 1190.0 → 1190.0 (0.0) | ? | no |
| 353 | 110153 | 117.13–118.59 | F | 35.6 → 10.5 | 53.9 → 29.1 | 1190.0 → 1200.0 (10.0) | ? | no |
| 354 | 110153 | 154.68–158.71 | R | 61.2 → 85.4 | 12.9 → 92.4 | 1180.0 → 1200.0 (20.0) | B | no |
| 355 | 110153 | 186.49–186.63 | W | 12.3 → 9.4 | 9.8 → 0.7 | 1250.0 → 1250.0 (0.0) | D | yes |
| 356 | 110629 | 42.48–57.24 | R | 9.8 → -72.4 | 53.2 → -37.4 | 931.0 → 941.0 (10.0) | B | no |
| 357 | 110629 | 129.95–130.02 | W | 6.4 → 6.4 | -1.5 → -1.5 | 959.0 → 959.0 (0.0) | D | yes |
| 358 | 110629 | 132.12–138.25 | R | 6.2 → -105.4 | -1.7 → -102.0 | 959.0 → 931.0 (-28.0) | B | no |
| 359 | 110629 | 180.57–189.47 | R | 17.5 → -82.7 | 63.1 → 4.9 | 914.0 → 911.0 (-3.0) | B | no |
