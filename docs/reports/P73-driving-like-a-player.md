# P73 driving like a player

P73 is incomplete. The work below is implemented locally, but the all-profile speed, turn and standing bounds are not met. This task uses simulator and recorded replay evidence only. No console session was started. Historical measurements below are reported from existing reports, not newly verified console performance.

## Before changes

The recordings do not establish a complete partition of physical standing time. Unknown values remain unavailable; lifted pedals, braking and reverse inputs do not establish that the car stood still.

| Recorded evidence | Metres | Seconds | Mean speed | Standing evidence |
| --- | ---: | ---: | ---: | --- |
| Initial town drives, 20261111-130447 through 131628, LOG | 2500 | approximately 625, inferred | 4.0 m/s | Cause totals unavailable |
| Coast 133846, LOG | 1150 | 145 | 7.9 m/s | Cause totals unavailable |
| Coast 134217, LOG | 1530 | 150 | 10.2 m/s | Cause totals unavailable |
| Later town replay window, P55 | 480 net route progress | 59.988 | 8.00 m/s net progress | Cause totals unavailable |
| Later town replay window, P55 | 350 net route progress | 60.014 | 5.83 m/s net progress | Cause totals unavailable |
| Route arrival attempt, WALKTHROUGH | 2000 | Unavailable | About 9 m/s, historical estimate | Two flagged-map stalls of about 70 s each |
| Kerim route-driving replay, P40 | Unavailable | 565.083 | No overall mean retained | Pedal shares are not standing time |

| Standing cause | Available baseline evidence |
| --- | --- |
| Behind vehicle | No measured total; old queue allowance was up to 30 s |
| Flagged map | Approximately 140 s across two documented stalls; P55 separately reports a 70.03 s corrupt-map interval, which is not added because overlap is unresolved |
| Recovery | P55 replay recovery segments of 7.327, 13.370, 27.681, 7.445 and 7.307 s; these are input replay durations, not proven physical standstill |
| Pedal lift for bend | Unavailable |
| Brake | Unavailable |
| Arrival | Unavailable |
| Immobile car | P55 describes three attempts on the same nonmoving car, about 18 s each; physical standing totals unavailable |
| Unknown | Cannot be quantified from the retained aggregate evidence |

Kerim's P40 recorded replay provides 287.479 s of speed/geometry overlap. GPS-slope bend speed median/p90 is 19.843/30.615 m/s over 181.954 s; straight speed median/p90 is 21.660/29.435 m/s over 48.453 s. Full R2 share is 0.821, lifted share 0.154 and L2 share 0.036 over 565.083 s. These estimates are neither a speedometer measurement nor standing-time labels. P55's 137 reverse-or-turn spans total 196.655 s, with median 1.0995 s and p90 2.5930 s.

Sources: docs/LOG.md, docs/WALKTHROUGH.md and reports P40, P54, P55 and P68. The baseline was collected before implementation changes.

## Decisions

Missing historical categories will not be fabricated. Current measurements must state whether they come from simulation or replay. The task's explicit prohibition on Git writes is followed: changes and this report remain in the assigned worktree without commit or pull request.

## Implementation and verification

The existing console settings remain available as `CAREFUL`, with `LIVE` an alias. `drive_route` accepts `style=bold|careful`, defaults to bold, and the CLI conversion accepts `style=careful` alongside numeric overrides. This works through the existing enum parameter validation without changing the registry or head files. Explicitly injected drivers keep their supplied configuration.

Bold waits two seconds behind a detected vehicle and then lets the avoider commit to its observed free side. A queue that remains stationary starts recovery without a second stuck-time wait and uses the opposite lock for its forward escape. Stale boxes cannot authorize the bypass. Both occupied sides still prevent an invented free-side choice. Recovery attempts retain their alternating lock and increasingly long reverse; bold clears their history only after 100 measured forward metres, instead of a brief successful movement. The existing recovery time and attempt limits remain. These decision changes do not yet pass the stopped-car simulation below.

The first simulator candidate, full throttle with a 0.4 holding pedal everywhere, lost the town arrival on the fast-low-grip profile and worsened several reverse-heading runs. Those settings were rejected. The retained extra holding pedal is 0.3 only when both near and far headings fall within the existing steering deadband. Straight speed, lateral acceleration, braking limits and unknown-speed throttle stay at their live values. The final matrix below shows that this does not yet provide the required universal speed improvement.

Arrival now waits 0.5 seconds of observed route absence in bold and delivers the driver's bounded braking command before returning the neutral terminal pad. Previously the skill discarded that command when it ended. A 0.7-second braking candidate caused reverse movement in the arrival simulator; the retained 0.35-second bound reuses the live brake-pulse duration and removes that reversal in the measured scenario. Water under the arrow on two consecutive clean frames ends the drive as `dead-or-held`; the first observation yields a neutral pad and the hard duration limit remains authoritative. This is a synthetic interface test, not a new vehicle-state classifier.

Getaway keeps the available forward road, chooses away from police only when multiple onward road exits exist, and retains water avoidance. Its existing simulator water tests pass. Wide-plaza behavior and more complex junction shapes still need broader validation; no console behavior is claimed.

## Replay evidence

`pilot/.venv/bin/python lab/drive/p73_replay.py` reports `14 windows, 12043 ticks, 77 unreadable_ticks, 8 clean_absence_braking_ticks, 0 violations`. It uses six P55 sessions and their existing motion caches. This is a bounded recorded replay, not every historical drive. The 8 earlier braking ticks are explicitly retained as differences: careful coasts on a clean map with `route=none`, while bold has entered arrival braking. A clean absent route is distinguished from an unreadable picture; corrupt, low-confidence and latched map-unreadable cases are not exempted. The per-window evidence is in `lab/drive/p73-replay.json`.

`P68_WORK=/private/tmp/p73-getaway-baseline env -u PS5_HOST pilot/.venv/bin/python lab/getaway/scripts/beside.py` was run after extracting all 15 source recordings with `keys.py` into that temporary work directory. The same script was also run with the HEAD version of `GetAway.choose`, imported from `git show HEAD:pilot/src/pilot/getaway.py` and substituted in memory. The same 665 frames and the same 0.2 to 3.0 second steering window were used for both. Only the compact results, not the 283 MB extraction, were copied into the repository.

| Recorded heading replay, absolute requested turn at least 30 degrees | Turn frames | Same direction | Opposite direction | No steering | Rank correlation |
| --- | ---: | ---: | ---: | ---: | ---: |
| HEAD choice | 341 | 113 (33.14%) | 111 (32.55%) | 117 | 0.01 |
| Road-first choice | 294 | 104 (35.37%) | 93 (31.63%) | 97 | 0.05 |

The matching-direction rate increases by 2.23 percentage points, while the number of requested turns falls. These are conditional rates with different turn denominators, not 2.23 percent more correct decisions across all frames. Evidence: `lab/getaway/p73-heading-careful.json` and `p73-heading-road-first.json`.

## Required checks

`cd pilot && .venv/bin/python -m pytest -q tests/test_player_driving.py tests/test_drive_route.py tests/test_drive_queue.py tests/test_getaway.py tests/test_avoid.py` reported `72 passed in 14.26s`. These cover enum style selection, live-setting preservation, the two-second bypass decision, changed recovery lock before 100 metres and reset after it, water confirmation, hard timeout and neutral ends, stale detection rejection, road choice and the existing getaway water worlds. Legacy queue fixtures explicitly select careful because their assertions intentionally require a 30-second wait.

The first sandboxed full gate reported `9 failed, 2742 passed, 3 skipped, 1376 deselected, 4 xfailed, 6 errors`. Socket-binding and CoreML temporary-directory restrictions caused most failures; a mission timing test also failed. A later formatting check found and corrected one condition layout. The completed final gate with native/local-test permissions is recorded below. This report does not treat the sandboxed run as a successful gate.

After the braking bound and queued recovery adjustment, `cd pilot && .venv/bin/python -m pytest -q tests/test_player_driving.py tests/test_drive_route.py tests/test_drive_queue.py tests/test_drive_recovery.py tests/test_cli.py` reported `48 passed in 2.70s`. An earlier native full gate had all `2768 passed, 1 skipped, 1376 deselected, 4 xfailed`, but exited 1 because 239.15 seconds exceeded its 90-second wall-clock guard. A stale simulator sweep from this task was found still running and terminated before the final gate; it is not being left in the background.

## Parked car and physical arrival

`pilot/.venv/bin/python lab/drive/p73_measure.py` reproduces the in-memory measurements in `lab/drive/p73-measurement.txt`. The parked-car worlds use a lane obstacle from x=-0.9 to 0.9 at y=8 and the existing perspective detection-box helper. Starting at y=0, bold passes y=10 after 6.00 seconds without collision. This is a moving approach, not evidence of clearing a stopped queue. Starting already close at y=7, it does not pass within 15.03 seconds and records 434 collision integration steps. The five-second bypass requirement fails; a stronger steering decision is not proof of physical clearance.

In the nominal deterministic 100-metre arrival simulation, the route is removed inside the three-metre destination radius. Route loss is at 15.4667 seconds, terminal `arrived` at 16.3667, and physical speed falls below 0.01 m/s at 16.5333, or 1.0667 seconds after route loss. Minimum speed is 0.0 m/s with the retained 0.35-second pulse, so the earlier reverse regression is absent. The car stops 0.597 metres beyond the destination, with a neutral terminal pad. This meets the timing bound in this one straight scenario only. It is not an all-profile or roadside parking proof. The skill finishes before the delayed final braking input has physically completed, which the harness explicitly measures.

## Final gate receipt

The final `.venv/bin/python tools/gate.py` completed with exit 1. Ruff lint and formatting passed. Pytest reported `1 failed, 2767 passed, 1 skipped, 1376 deselected, 4 xfailed in 455.60s`. The sole failure was `tests/test_mission.py::test_rule_path_is_within_a_few_milliseconds`: measured p95 was 7.595708 ms against a less-than-5 ms assertion. Unlike the earlier all-tests-passed run, this final invocation stopped at pytest before the gate could report its duration guard. The full final receipt is `lab/drive/p73-gate.txt`.

An isolated repeat with `.venv/bin/python -m pytest -q tests/test_mission.py::test_rule_path_is_within_a_few_milliseconds` also failed, at p95 7.729167 ms, `1 failed in 1.00s`. Concurrent test jobs were observed on the machine, but that does not prove the sole cause of the timing failure. No mission code or performance threshold was changed: `mission.py` is explicitly outside this card. The gate remains failed, not waived.

The final diff passes `git diff --check`; the two added lab measurement scripts pass Ruff. All changes remain within the card's permitted files. Added lab evidence is below 0.4 MB, within the 3 MB limit.

## Remaining blockers and reliance limits

The all-profile faster-arrival criterion is not met. The current behind-route behavior also exceeds six seconds to align and can stand more than three seconds outside recovery. No handbrake U-turn was added: the current driver Command has no handbrake channel, the simulator has no calibrated handbrake dynamics, and terrain road widths are angular map crossings rather than measured turning clearance. Guessing a new R1 effect would manufacture the requested proof. This needs a defensible simulator/control contract and calibration before the six-second claim can be made.

The requested last-clean-route plus terrain fallback for persistently flagged maps is not implemented. Existing cautious unreadable behavior remains, including its current timeout. The replay demonstrates input compatibility only; it does not demonstrate elimination of the historical map stalls. A complete physical standing-cause partition cannot be recovered from the retained logs: driver phase, obstacle detections and true vehicle speed are not recorded on every tick. The available map-motion estimates below are explicitly proxies.

There is no observation field or classifier for an overturned/burning vehicle, red lights or cross traffic. Water confirmation and the existing held-car recovery failure are available; the missing visual conditions are not silently guessed. The allowed files do not include the detection contract or its producer. Road-edge arrival is also not implemented or measured: the simulator route alone does not establish a roadside parking position. The added tests therefore do not cover every cause or every Done-when bound.

Do not rely on this branch as completion of P73 or as a qualified console driving style. The reviewer must resolve these gaps, repeat the acceptance matrix, then arrange the explicitly outstanding console drive with Kerim. No commit, push, pull request, daemon request or console input was made.

## Final simulator matrix

`cd pilot && .venv/bin/python tools/evaluate_player_driver.py --out ../lab/drive/p73-styles.json` runs all eleven profiles on three explicit routes, with identical seed 0 and a 120-second limit for each style. Arrival here means entering the simulator destination radius, not parking. All 66 runs reach that radius and have zero recoveries, hence zero recoveries/km. The source separately measures actual speed below 0.5 m/s outside recovery; `max_no_progress` is not mislabeled as standing. Behind-route alignment means coming within 30 degrees of the first road heading. These are simulator results, not console capacity or handling evidence.

| Profile | Route | Careful seconds | Bold seconds | Bold maximum standing seconds | Bold alignment seconds |
| --- | --- | ---: | ---: | ---: | ---: |
| nominal | town | 64.57 | 64.57 | 0.87 | - |
| nominal | country | 52.80 | 52.80 | 0.87 | - |
| nominal | behind | 24.60 | 24.60 | 4.33 | 7.67 |
| range-00 | town | 83.73 | 83.73 | 1.33 | - |
| range-00 | country | 72.57 | 72.57 | 1.33 | - |
| range-00 | behind | 34.27 | 34.27 | 4.43 | 9.10 |
| range-01 | town | 71.07 | 71.07 | 0.87 | - |
| range-01 | country | 53.37 | 53.27 | 0.87 | - |
| range-01 | behind | 35.27 | 35.27 | 4.33 | 10.40 |
| range-02 | town | 71.50 | 71.50 | 0.57 | - |
| range-02 | country | 45.13 | 45.13 | 0.57 | - |
| range-02 | behind | 49.07 | 48.93 | 2.47 | 15.10 |
| range-10 | town | 80.90 | 80.90 | 1.33 | - |
| range-10 | country | 72.70 | 72.70 | 1.33 | - |
| range-10 | behind | 32.53 | 32.50 | 4.43 | 8.30 |
| range-11 | town | 64.57 | 64.57 | 0.87 | - |
| range-11 | country | 52.80 | 52.80 | 0.87 | - |
| range-11 | behind | 24.60 | 24.60 | 4.33 | 7.67 |
| range-12 | town | 53.97 | 53.97 | 0.57 | - |
| range-12 | country | 41.90 | 41.17 | 0.57 | - |
| range-12 | behind | 21.90 | 21.87 | 2.47 | 8.00 |
| range-20 | town | 81.10 | 81.10 | 1.33 | - |
| range-20 | country | 72.70 | 72.70 | 1.33 | - |
| range-20 | behind | 32.50 | 32.50 | 4.43 | 8.30 |
| range-21 | town | 62.17 | 62.17 | 0.87 | - |
| range-21 | country | 52.80 | 52.80 | 0.87 | - |
| range-21 | behind | 23.20 | 23.20 | 4.33 | 7.33 |
| range-22 | town | 52.73 | 52.73 | 0.57 | - |
| range-22 | country | 46.10 | 46.10 | 0.57 | - |
| range-22 | behind | 20.23 | 20.23 | 2.47 | 6.77 |
| fast-low-grip | town | 70.60 | 70.60 | 0.57 | - |
| fast-low-grip | country | 45.13 | 45.13 | 0.57 | - |
| fast-low-grip | behind | 49.07 | 48.93 | 2.47 | 15.10 |

Bold reaches every route but is equal in time in most cases. Behind-route alignment takes 6.77 to 15.10 seconds, above the six-second target. Several profiles stand 4.33 to 4.43 seconds outside a recovery, above the three-second bound. These failures are not waived.

## Recorded window measurements

The following table is derived from the immutable P55 recorded windows, not from the changed driver. Net route progress can be negative and is not distance travelled. The rate is net progress divided by window length. Stationary time is a map-motion estimate; the flagged and braking columns overlap and describe coincident inputs, not established causes. Missing obstacle and internal-phase telemetry prevents assigning the rest to queue, recovery, bend, arrival or immobile-car causes.

| Replay session / start | Net route progress m | Window s | Net progress m/s | Map stationary s | Flagged while stationary s | Braking while stationary s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 20261112-102851 / 199.018 | Unavailable | 7.592 | Unavailable | 2.651 | 0.000 | 0.349 |
| 20261112-103305 / 112.997 | 480.0 | 59.988 | 8.00 | 1.040 | 0.000 | 0.000 |
| 20261112-103305 / 173.024 | 10.0 | 25.411 | 0.39 | 13.976 | 0.000 | 1.670 |
| 20261112-104424 / 3.110 | 350.0 | 60.014 | 5.83 | 5.400 | 0.000 | 1.264 |
| 20261112-104424 / 63.163 | -1.0 | 36.739 | -0.03 | 29.858 | 0.000 | 6.308 |
| 20261112-104424 / 155.304 | 0.0 | 18.114 | 0.00 | 16.158 | 0.000 | 3.796 |
| 20261112-104827 / 25.474 | -560.0 | 39.834 | -14.06 | 4.618 | 0.000 | 1.266 |
| 20261112-104827 / 65.408 | 100.0 | 59.928 | 1.67 | 12.535 | 0.000 | 3.814 |
| 20261112-104827 / 125.346 | 200.0 | 45.837 | 4.36 | 3.244 | 0.000 | 1.135 |
| 20261112-104827 / 174.896 | 180.0 | 59.981 | 3.00 | 4.586 | 0.035 | 1.254 |
| 20261112-105230 / 4.329 | -50.0 | 32.543 | -1.54 | 20.310 | 0.000 | 4.908 |
| 20261112-105230 / 36.949 | 0.0 | 18.023 | 0.00 | 14.386 | 0.000 | 3.153 |
| 20261112-105230 / 55.053 | 0.0 | 4.939 | 0.00 | 2.708 | 0.000 | 0.228 |
| 20261112-105332 / 3.229 | 0.0 | 17.880 | 0.00 | 17.880 | 0.000 | 3.787 |
