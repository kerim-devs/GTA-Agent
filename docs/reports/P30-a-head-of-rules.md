P30 adds `MissionHead(fallback=None)` in `pilot/src/pilot/mission.py`, frozen recording cases and an offline comparison under `lab/mission/`, and `pilot/tests/test_mission.py`. The head is not wired into the conductor or CLI. It validates every locally generated answer with `parse_response`; delegated requests and answers retain object identity. `last_rule` and `counts` expose local decisions without changing the head protocol. The implementation has no mission-progress state to replay after retry.

The ordered decisions are documented below. Sources refer to `pilot/src/pilot/head_prompt.txt` unless another path is given. Each rule also carries its source in the module.

| Order | Decision | Source and boundary |
| --- | --- | --- |
| 1 | Cutscene, loading or black screen: wait three seconds. | Prompt line 10; recorded loading at Wi-Fi 41.5 and 640 seconds. |
| 2 | Other non-game screens: wait one second for the local reflex. | Prompt lines 49-56; real failed, passed, weapon-wheel, phone, pause, map and wasted frames. Ordinary movement must not enter these screens. |
| 3 | Wanted: escape by the observed means. Flat map without a visible vehicle means sprint; a flat map with a visible vehicle means enter, set an away waypoint and drive. Unknown movement delegates. | Prompt lines 43-47; Wi-Fi 536.7607 and labelled objects 071, 072, 073, 075; `docs/LOG.md:102-106` forbids inferring a vehicle from tilted plus wanted. The vehicle escape branch is reserved for the later judge seam and tested as an explicit counterfactual. |
| 4 | Health below one third: leave by vehicle or sprint on foot; unknown movement delegates. | Prompt lines 35-41; Wi-Fi 25 and 245 seconds. |
| 5 | Failed skill: change the first action, respecting movement mode. On foot walk, or turn before retrying walk; in a vehicle set a new away route, or turn before retrying waypoint. Unknown movement delegates. | Prompt lines 58-60. Recorded calls do not contain a failed skill, so this boundary has explicit counterfactual tests rather than a claimed real failure fixture. |
| 6 | Vehicle with yellow/purple route: drive it. Without route: set an away waypoint and drive. | Prompt lines 25-33; Wi-Fi 160, 230 and 395 seconds. No recorded mission-letter instruction supports a mission waypoint rule. |
| 7 | Red blips without an evidenced combat instruction/weapon state: delegate. | Prompt lines 35-41; real combat frames at Wi-Fi 20, 45 and 50 seconds; `docs/LOG.md:64` only summarizes the earlier model experiment. No fabricated German combat wording is matched. |
| 8 | On foot with yellow/blue target: walk to the mark. | Prompt lines 16-23 and 35-41; Wi-Fi 5.2415 contains the actual weapon-pickup instruction and blue marker. |
| 9 | After failure, pass, menu closure or screen clearance, recompute from the current request; otherwise unmarked foot retry starts with walking. | Prompt lines 49-56; actual OCR variants contain `Fehlgesch agen`, `Fehlgeschlagen`, `fehlgeschlagen` and `Erneut versuchen`. Reflex-event tests are explicitly overlaid on real requests. Blocking failure screens remain the reflex's responsibility. |
| 10 | Unmarked foot exploration with no text or objects: look, walk, look, walk. | Prompt lines 16-23 and the real model response at `/Users/kerim/recordings/pilot/20261110-231512/head.jsonl:2`. |
| 11 | Unmatched request: return the injected fallback answer unchanged. Without one, keep moving. | P30 task card. This default is not a claim to understand an ambiguous scene. |

The shared failed-call guard inserts a different first action before retrying a selected movement plan. Blocking screens are an intentional exception: they remain neutral even if a preceding wait reported failure. Screen/reflex priority prevents a recovery action from walking into a menu. Wanted and health take priority over ordinary task recovery. Rules never choose fight, melee, punch or shoot; an injected fallback remains responsible for its own answer and is deliberately not rewritten.

`movement(request)` is the single replaceable inference seam. Flat means on foot unless the map is corrupt. Tilted means vehicle only with positively read zero wanted stars. Tilted with stars, unread stars, absent map or corrupt map means unknown. This is more conservative than treating unread wanted as zero. P29 integration can replace this helper without changing the protocol or decision rules.

The [complete case table](../../lab/mission/cases.md) records every rule and full argument-level plan beside the recorded model plan, with a judgment for each difference. [comparison.json](../../lab/mission/comparison.json) preserves the same comparison with source locations and timing. There are 173 recorded or frame-reconstructed requests: 18 unchanged model calls, 142 Wi-Fi frame reconstructions, four exact frames with manual vehicle labels, and nine Kerim recording samples. Rules decide 90 cases; 83 delegate. No model was called during this work.

| Decision | Cases |
| --- | ---: |
| Foot exploration | 24 |
| Blocking-screen hold | 14 |
| Loading hold | 2 |
| Low health on foot | 3 |
| Low health in vehicle | 1 |
| Marked foot target | 6 |
| Vehicle waypoint | 15 |
| Vehicle route | 6 |
| Wanted on foot | 15 |
| Wanted on foot with visible vehicle | 4 |
| Fallback | 83 |

The eight older model responses repeatedly wait in an otherwise free scene; the moving rule is preferable under prompt lines 16-23. The ten later responses and the exploration rule both use look/walk. Their angle, duration, sprint and step differences do not establish that either path is better because the requests contain no observed destination. The rule keeps fixed parameters and avoids claiming progress. Mission-frame cases have no saved model answer, so their comparison is limited to observed inputs and prompt consistency, not invented agreement with the earlier model experiments.

Evidence generation ran locally from `pilot`: `.venv/bin/python ../lab/mission/build_cases.py`, `.venv/bin/python ../lab/mission/read_frames.py`, `.venv/bin/python ../lab/mission/read_extra_frames.py`, and `.venv/bin/python ../lab/mission/compare.py`. The frozen corpus needs no video, detector or host at test time. `.venv/bin/python -m pytest -q tests/test_mission.py --tb=short` passed 238 tests in 0.14 seconds. These cover every recorded rule branch, serialization through `parse_response`, unchanged fallback identity, wanted-state permutations, failed-call recovery, blocking screens and retry replanning. A 300-call timing test requires the rule path's 95th percentile to remain below five milliseconds.

The baseline default gate was already blocked by sandbox permissions: five existing commentator/overlay tests could not bind loopback sockets, and five existing object tests could not create a CoreML compilation directory. It reported 1,100 passed, five failed, five errors, three skipped and four expected failures. The unchanged `.venv/bin/python tools/gate.py` was rerun with local socket and temporary-file access and passed in 58.35 seconds: 1,350 passed, one skipped, 1,376 deselected and four expected failures. Ruff check and format check passed. Its complete output is recorded in `lab/mission/gate.txt`.

Unverified scope is explicit. There was no live game, live model call or conductor integration. The saved corpus does not prove actual mission completion, vehicle-entry success or path safety. The raw model answers for the mission experiments described in `docs/LOG.md:64` are absent. No recorded combat imperative or mission-letter instruction justifies those text rules, so combat selection is left to fallback and mission-letter routing is not implemented. There is no real failed-skill request or preserved post-retry HeadRequest, so those conditions have counterfactual contract coverage only. These evidence gaps prevent claiming that every requested rule is pinned to an actual historical head call. Kerim's sample frames have no OCR/object observations; the four vehicle cases use manual labels, not detector predictions. No new detector confidence or event history is fabricated.

The code and default gate are complete for the supported observations, but the card cannot be declared fully closed against its demand for a real request for every rule. The missing combat/mission-letter evidence and historical failure/retry calls cannot be recovered from the available artifacts. No new live session was attempted to manufacture that evidence. The next integration can rely on the injectable protocol implementation and frozen replay corpus, but must supply its fallback head and replace the conservative movement helper with P29 evidence before treating tilted wanted frames as vehicle observations. No files outside the card's allowed paths were changed. No commit, push or pull request was created: `docs/tasks/README.md` reserves Git and integration for the central workflow.

## Review

The worker wrote only the rules a recording proves, which left out the two that move the story, so the review added them from the prompt and marked their tests as overlays on a recorded request. A route that the pilot makes itself now leads to a mission letter and not just away; when the map shows no letter the waypoint skill fails, the next routes lead away, and after four of them the map is asked again. On foot with no objective, no marker and a car in view, the plan is the one the prompt names: get in, set the waypoint, drive. Where a route has just ended the rules do not set another one: what the place wants is in the picture, so the fallback is asked. With stars, a waypoint that is still up is driven without opening the map again. Looking around on foot no longer needs the frame to be empty of people.

With these, the rules decide 94 of the 173 cases and the fallback 79; `cases.md` and `comparison.json` are regenerated. The default gate passes with 1354 tests in 62 s, 242 of them in `tests/test_mission.py`.

The head is not wired yet. It needs a command-line choice with the Codex head as its fallback, and `movement` has to take the judge's word once P29 is merged: until then every frame with stars and a tilted map goes to the fallback, which is the right answer to not knowing and costs its seconds exactly when the police are close. None of the rules has run on the console.
