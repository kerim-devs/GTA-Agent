P85 implements evidence-based vehicle exits, a guarded entry press, and neutral waiting through missing or undecodable video. Changes stay within the card's source files and their tests. No console, daemon, remote-play configuration, network service, or Git write was used. The reviewer retains the working-tree changes.

The mode filter returns `unknown` while a foot answer contradicts a tilted map. A judge-only exit requires three continuous seconds of fresh foot answers; an intervening answer or a lapse restarts that interval. The event detector accepts an exit from foot plus a sound flat map, sustained judge evidence, or an acknowledged Triangle followed by a sound flat map within three seconds. A map-only change cannot emit an exit. The button evidence comes from the pad accepted by the runtime, not an unsent skill proposal. Event evidence names the basis for the decision. No change to mission.py is needed for the existing vehicle_exit vocabulary.

Before an entry press, the skill requires a fresh detection of the player as a person, a sound flat map, and an on-foot mode. Without a judge, the existing map fallback still requires the fresh player detection. A tilted map with a route and no fresh on-foot player detection keeps the pad neutral and finishes as already seated after the existing two-second confirmation. The old detection exports in lab/enter omit the separately identified player. Their tests now verify that vehicle boxes alone cannot authorize Triangle; no player detection was invented for those recordings. Synthetic entry simulations supply the player explicitly and still cover successful entry, locked doors, delayed animation, retries, and retreat.

Missing frames immediately request the neutral pad. The existing 0.3-second freshness threshold distinguishes a prolonged gap from a single duplicate; a malformed frame body enters the lost-picture state immediately. A prolonged gap abandons stale planning and skill execution once. The first recovered picture starts a one-second settling interval, during which judge observations can warm up but skills, scene events, HUD events, and idle nudges cannot run. A renewed loss restarts recovery. The head receives one picture_returned event with the gap duration after settling; picture_lost and picture_returned are each logged once. Pending scene candidates are discarded during the gap. Unexpected transport/runtime errors still propagate through cleanup. Upper-right system notices already lie outside the SceneText event regions; the connection notice therefore requires no new screen or mission rule.

Measurements used the 201 sessions dated 12 or 13 November with play.jsonl, judge.jsonl, and head.jsonl under /Users/kerim/recordings/pilot. Judge times were aligned as first head request time minus first play time, following the existing replay. These are log-level measurements with twelve Triangle-while-tilted transitions followed by a clean flat map within four seconds, not a claim of complete manual annotation of every human exit. The longest routed-map/foot disagreement was 1.820 seconds in 20261112-143810. A real exit's first foot answer preceded the flat map by up to about 2.73 seconds in 20261112-142428. These observations set the three-second sustained-answer threshold. Triangle-to-flat latency was 1.222 to 2.937 seconds, which sets the acknowledged-button window.

In 20261113-163218 the frame gap was 199.446 to 219.691 seconds, or 20.245 seconds. The clean tilted map returned immediately; the second vehicle judgment arrived at about 220.619 seconds, about 0.93 seconds after return. This sets the one-second settling interval. Directly inspected head-0022.jpg shows the occupied black car, a tilted map with purple route, and the upper-right connection notice. head-0026.jpg shows the player standing beside the open driver door with a flat map and no route. head-0028.jpg shows the subsequent entry. These are visual observations, not saved detector outputs; figure and figure_vehicle were not persisted in these logs.

Two of the twelve measured exits are reported later by the acknowledged-button/flat-map path than by the old accepted judge change: 0.227 seconds and 2.208 seconds. Both old reports preceded the flat map. The other ten have an earlier eligible flat-map report. The comparison uses logged old acceptance arrival and first clean flat-map time, so an unusually late old report can reflect missing or delayed old acceptance, not physical exit duration. Times below are session-relative seconds; delta is new minus old.

```
session          Triangle  old arrival  new flat  delta
20261112-110407      3.098        5.283     4.662  -0.621
20261112-122231      3.141        5.851     6.077  +0.227
20261112-122312     16.482       30.875    17.824 -13.051
20261112-122904      3.173        6.386     6.022  -0.365
20261112-142428    242.432      242.951   245.159  +2.208
20261112-143917      0.319        2.598     1.843  -0.755
20261112-144023      0.320        2.388     1.813  -0.576
20261112-144404     40.581       42.449    41.924  -0.524
20261112-144404    166.496      168.634   168.595  -0.039
20261113-163218    223.612      225.622   225.306  -0.316
20261113-163218    279.827      281.729   281.393  -0.336
20261113-163218    565.608      567.499   566.829  -0.670
```

The literal 220–230-second zero-exit acceptance condition conflicts with the recording. The old pilot sent Triangle at 223.612 seconds, producing a real exit and a flat map from 225.306 seconds. The complete stored judge/map fixture therefore expects no false exit and exactly one genuine exit at the sampled flat reading, 225.370 seconds. A separately labeled counterfactual keeps the seated map after suppressing that old Triangle and expects zero exits through the full interval. It uses all 36 judge samples from 220.270 to 229.814 seconds. This distinction preserves the evidence instead of labeling the real on-foot frames as seated.

The new regressions cover the recorded false-foot cluster, sustained and interrupted disagreements, an acknowledged Triangle with a flat map at the measured worst-case 2.937 seconds, seated entry with contradictory modes, missing player evidence, neutral gap/settling behavior, and run_play with both absent and malformed frame bodies. Six regressions fail against the original four source files and pass with the changes. The original sources were temporarily restored with git show, tested, and the changes restored in a finally block; no Git state was changed.

```
cd pilot
.venv/bin/python -m pytest -q tests/test_conductor_seat.py tests/test_scene.py tests/test_judge.py tests/test_vehicle_entry.py tests/test_conductor.py tests/test_conductor_judge_replay.py
229 passed, 1 skipped in 9.81s

# Selected replay, seated-entry, and runtime-gap regressions against original sources:
6 failed, 1 passed in 0.47s

.venv/bin/python tools/gate.py
ruff check: All checks passed!
ruff format --check: 200 files already formatted
14 failed, 3424 passed, 3 skipped, 1376 deselected, 4 xfailed, 16 errors in 123.09s
gate failed at: pytest -q
```

The card's literal zero-exit expectation is not met for the unmodified historical aftermath, for the reason above. No live-console test was attempted, as the worker rules prohibit it. The reviewer should retain the distinction between the actual recording and the counterfactual replay, and verify current player detections before relying on live entry availability. If the figure is not detected, the safe result is no press, not a successful entry claim.

The whole gate was run exactly once, as requested. Five failures exposed P85 integration expectations and have been addressed: the bench now sees the existing interrupted stop reason; one damaged map sample does not cancel carry just because the test clock advanced; the two game-profile entry fixtures now include the player; and the tick-path test now requires releasing a held button on a damaged picture. The profile and tick-path edits are tests of the card's entry and conductor changes, not changes to neighboring production modules.

The remaining gate blockers are environmental: nineteen local HTTP/IRC/overlay test cases cannot bind loopback sockets (PermissionError: Operation not permitted), and six object-detector cases cannot load the missing or corrupt pilot/models/yolox_l.onnx weights. No attempt was made to download weights or change the machine. The task rules say, "You work only inside your worktree and only on the files your card names." Adding model files is outside that write set. The reviewer must supply the verified existing model artifact and run the gate in an environment that permits its local test servers. The gate is not green, so the card is not fully accepted despite passing scoped behavior checks.

Final scoped verification after those integration fixes:

```
cd pilot
.venv/bin/python -m ruff check src tests tools
All checks passed!
.venv/bin/python -m ruff format --check src tests tools
200 files already formatted
.venv/bin/python -m pytest -q tests/test_conductor_seat.py tests/test_scene.py tests/test_judge.py tests/test_vehicle_entry.py tests/test_conductor.py tests/test_conductor_judge_replay.py tests/test_profile.py tests/test_moving.py tests/test_review_tick_path.py tests/test_bench.py::test_every_reason_a_skill_can_end_on_has_a_rule
279 passed, 1 skipped in 7.13s
```

The changed tracked files also pass git diff --check. The isolated /tmp LFS cache used for that read-only check avoids writes to the parent checkout's shared LFS cache.
