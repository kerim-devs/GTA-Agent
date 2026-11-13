P70 replaces the fixed free-roam round with weighted, seeded story, shop, mayhem, cruise and home errands. Selection applies shop, home and mayhem cooldowns, suppresses consecutive repeats except story, and halves story weight after a letter fails to start a mission. The optional `Goals(chooser=...)` receives a list of dictionaries containing `name`, `weight` and an English `description`, and returns a name or `None`. Invalid or absent choices use the seeded draw. There is no model or provider call.

The common trip reads the waypoint result before choosing transport. Trips of at most 250 m walk; longer trips seek a vehicle and drive. Story and service visits exit the car and restore the same waypoint before the exact approach. Story requires an objective or cutscene after arrival, remembers nonstarting letters, and schedules a character switch after each pair. Service visits require successful use followed by an observed outdoor exit; a failed use still leaves. Home plans the registered use-place contract with spending disabled and explicitly forbids beds and saves in the head prompt. Mayhem includes the escape after the punch before it completes. Deadlines, attempt budgets and twice-abandoned places bound retries.

The P55 measured recovery behavior remains: held cars are left with a walk away before re-entry, the first unreadable map gets a look and retry and the second leaves the car, a standing waypoint is retained on no-progress, a route lost far away is reset once, and a running drive gets time to classify a disappearing route. Police and escape rules use get_away without a map. Standing responses use the sender's count; a vehicle gets one route retry and leaves on subsequent standing, and repeated indoor standing leaves the building. Objective prompts run once per exact help text. Identical running calls keep their instance except for the specified interruption events, and discarded prompt decisions can be retried.

The old fixed-order, fixed-budget and legend-rotation tests were replaced by scripted errand-world and selection-policy tests in test_errands.py. Existing conductor, held-car, unreadable-map, waypoint-retention, route-completion, unknown-wanted, ownership and undo tests were retained, with cruise explicitly selected where the test needs a driving trip. Mission fixture expectations now use seeded errands and get_away. The fallback-intent fixture removes unrelated help text so that it still tests fallback independently of the new prompt priority. No skill, reader, conductor, loop, CLI or flow implementation was changed.

The implementation relied on PLAN.md, docs/tasks/README.md, the P70 card, WALKTHROUGH.md, the 12 and 13 November LOG entries, and reports P51, P52, P55 and P68. In particular, P51 supplies goal ownership and undo, P52 supplies waypoint-result grammar, P55 supplies the measured trip recoveries, and P68 supplies the no-map escape contract. Unterschlupf is handled explicitly because the current legend classifier does not classify it as a shop.

The focused errand, goal, mission, intent and reason-vocabulary tests passed with `env -u PS5_HOST pilot/.venv/bin/python -m pytest pilot/tests/test_errands.py pilot/tests/test_goals.py pilot/tests/test_mission.py pilot/tests/test_mission_intent.py pilot/tests/test_bench.py::test_every_reason_a_skill_can_end_on_has_a_rule -q --tb=short`: `507 passed in 7.20s`. The continuity reason uses the existing `goal_` prefix understood by the benchmark. The scripted worlds cover every errand at 200 m and 700 m, the 250/251 m transport boundary, failure and deadline paths, attempt limits, sixty completed errands, valid registry calls and no waypoint under stars. A short cruise begun inside a car exits and finishes on foot without calling use_place; the story wait limit interrupts a still-running wait at twenty seconds. The selector and event tests cover cooldowns, story damping, two nonstarting letters, indoor standing, interrupted identical calls and prompt deduplication. Existing conductor recovery tests remain in test_goals.py.

From the repository root, `env -u PS5_HOST pilot/.venv/bin/python lab/errands/replay.py` replayed 1,315 requests from all 238 recorded head.jsonl sessions without an exception. The per-session counts and rule totals are in lab/errands/replay.json; replay.py reproduces them without a runner, image reads, network access or a console. Recorded replaced answers beginning with the same running skill name numbered 89 before; new replay answers doing so number 7. All 89 historical cases and all 7 replay cases lack the running skill's args. Exact name-and-args replacements are therefore not measurable on those rows, rather than proven absent; no comparable identical-call cases were found. Synthetic requests with full args prove go_on for the same call and replacement for the specified exception events. The replay uses fixed historical requests and does not predict the gameplay produced by the new plans.

The replay's rule table follows.

| Rule | Requests |
| --- | ---: |
| drive_ends | 1 |
| failed_skill | 2 |
| failed_vehicle_skill | 2 |
| failed_vehicle_skill_after_failure | 11 |
| foot_explore | 23 |
| foot_target | 15 |
| goal_cruise | 763 |
| goal_home | 2 |
| goal_mayhem | 20 |
| goal_shop | 303 |
| goal_story | 94 |
| judged_wait | 19 |
| judged_wait_after_failure | 2 |
| low_health_on_foot | 6 |
| moving_default | 22 |
| screen_reflex | 4 |
| vehicle_route | 9 |
| vehicle_waypoint | 7 |
| wanted_on_foot_vehicle | 1 |
| wanted_vehicle | 5 |
| wanted_vehicle_route | 4 |

The final full gate ran once after the terminal restart, from `pilot/`, with `env -u PS5_HOST .venv/bin/python tools/gate.py`. Ruff lint and format checking passed. Pytest reported `2817 passed, 1 skipped, 1376 deselected, 4 xfailed in 147.42s`. The command still exited 1 because its overall runtime was 148.22 seconds, exceeding the default 90-second limit; the final output was `default gate exceeded 90 seconds`. The output is saved in `lab/errands/gate.txt`. The user reported heavy shared-machine load and required a single final gate run. No second full run was started and the time limit was not weakened. Therefore the functional checks are green, but the card's requirement for a successful full gate remains open on elapsed time.

An earlier run exposed decision latency from copying the complete session history at every rollback checkpoint. History entries are append-only, so the checkpoint now records their length and undo removes only newly appended entries. Other mutable decision state and the seeded random state still restore together. The focused tests and the final full suite passed after this change, including decision latency and discarded-answer recovery.

`git diff --check` passed. No repository hooks or checks were skipped.


Live console behavior is unverified. The registry's use_place, do_prompt, leave_building and switch_character implementations remain their other cards' responsibility. The registered walk_to_point enter flag also depends on its implementation card. P70 plans those published interfaces and tests scripted outcomes; it does not prove actual doorway entry, wardrobe selection, clothing changes or exit reliability. The standing-event sender belongs to the reviewer. Kerim must still watch each errand once on the console. No live daemon, PS5 connection, external network request, config edit, commit or push was performed. As explicitly required by docs/tasks/README.md, changes are left in this worktree for the reviewer to commit.
