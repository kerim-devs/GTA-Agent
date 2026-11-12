P58 adds the complete 18-capability catalogue, offline proofs and reason classification, an append-only ledger with separate reviewer marks, an injectable console runner, and Markdown plus standalone HTML boards. The frozen 12 November sample contains 43 attempts: 3 passed, 24 failed and 16 were excluded. Fourteen reported waypoint successes fail the independent visible-route requirement. None of the 24 counted failures remains unclear.

The board is [bench.html](../../lab/bench/bench.html), with its text version in [bench.md](../../lab/bench/bench.md), ledger in [bench.jsonl](../../lab/bench/bench.jsonl), and frozen import list in [import-source.tsv](../../lab/bench/import-source.tsv). These are offline observations, not a new console round. No daemon or PS5 command was called and no file below /Users/kerim/recordings was written. All console calls are isolated in bridge() and pilot(), both replaced by model functions in tests.

The input TSV was changing during the task because the console was in use. The report and baseline comparison therefore use the exact 43 imported attempts, frozen in import-source.tsv. This sample has seven leave, six walk, five enter, four drive, eighteen legend place and three cursor waypoint attempts. It includes later runs than the early summary in docs/LOG.md, which reported leave 1/1, walk 4/4, entry 0/3, cursor waypoint 0/3 and driving untried; the later first legend series reported 6/8.

Each attempt stores the execution time from meta.started where available, the source commit and dirty status, session, observed start state, outcome, cause, terminal skill reason, elapsed seconds and proof numbers. Historical meta.json files do not contain a source revision, so their commit is unknown and dirty is null. judged_with records the evaluator revision separately and is not presented as the historical execution revision. Rejudging appends a revision; board rates use the latest revision of each session/capability/event, avoiding duplicate counting. Reviewer marks append to bench.marks.jsonl and are visibly applied without changing the ledger.

The first second establishes foot or vehicle mode from uncorrupted minimap shape, requiring 80% agreement. Game state comes from HUD readings in head requests. Head timestamps are absolute monotonic time and play timestamps are session-relative; the initial request is aligned with the first play tick and duplicate request/response records are removed by id. This is an approximate alignment, not an exact frame synchronization. End-state mission evidence older than five seconds triggers a short wait probe before further movement. Missing evidence excludes an attempt instead of making it a success or an unclassified failure.

Both skill and independent proof must be true for ok. A true/false disagreement in either direction is failed/proof. Both false use the cause map below. An unknown terminal result, unknown proof, unsupported capability or invalid start is not_counted with a reason. A capability can remain not measurable while some failures are conclusively disproved: no final route falsifies map.place, but a route alone cannot prove the identity of the selected legend entry. Every capability uses the mark of nine successes in the last ten counted attempts; fewer than ten does not become green.

The catalogue follows. Missing fields identify the responsible reader and logger; those modules were left unchanged.

foot.view (Set the view, group foot): start foot; 15 seconds; plan level_camera {}. Proof: Final independent camera pose and follow distance. Unavailable evidence or implementation: Camera pose/distance missing: perception reader and cli play logger.

foot.walk (Walk, group foot): start foot; 28 seconds; plan walk_road {'duration': 20}. Proof: Independent moving observations over 20 seconds; >50% moving, no 3-second hold. Unavailable evidence or implementation: Independent moving field missing: flow reader and conductor play logger.

foot.walk_to (Walk to a point, group foot): start foot, yellow_target; 18 seconds; plan walk_to {'duration': 10, 'color': 'yellow', 'sprint': False}. Proof: independent metric distance to the selected yellow blip is at most ten metres. Unavailable evidence or implementation: Blip distance in metres missing: minimap reader and cli play logger.

foot.roadside (Stay roadside, group foot): start foot; 28 seconds; plan no standalone plan. Proof: Every sampled foot position is outside the carriageway. Unavailable evidence or implementation: Roadside position missing: road reader and cli play logger; no roadside skill.

foot.enter (Enter a vehicle, group foot): start foot; 28 seconds; plan enter_vehicle {'duration': 20, 'kind': 'any'}. Proof: Stable vehicle mode within 20s; target was stationary and unoccupied. Unavailable evidence or implementation: Target speed and driver occupancy missing: vehicle detector and cli/head logger.

car.leave (Leave a vehicle, group car): start vehicle; 8 seconds; plan press {'button': 'triangle', 'duration': 1}. Proof: Final stable flat minimap, initially tilted; independent of press result. The proof reads logged observations independently of the skill terminal status.

car.follow (Follow the route, group car): start vehicle, route; 38 seconds; plan drive_route {'duration': 30}. Proof: GPS distance drops >=100m within 30s; speed never held for 5s. The proof reads logged observations independently of the skill terminal status.

car.arrive (Arrive, group car): start vehicle, route; 66 seconds; plan drive_route {'duration': 60}. Proof: Final GPS <=30m, speed stopped, arrival sentence in head response. The proof reads logged observations independently of the skill terminal status.

car.free (Get unstuck, group car): start vehicle; 10 seconds; plan harvested, no standalone plan. Proof: Held vehicle moves again within 10s. Unavailable evidence or implementation: Recovery attempt identity/start missing: driver and cli play logger.

car.turn (Turn around, group car): start vehicle, route, behind; 15 seconds; plan no standalone plan. Proof: Route-relative heading aligned within 15s. Unavailable evidence or implementation: No standalone turn skill; route-relative heading missing from play logger.

map.open_close (Open and close the map, group map): start game; 8 seconds; plan press {'button': 'options', 'duration': 0.2}, wait {'duration': 2}, press {'button': 'circle', 'duration': 0.2}. Proof: Independent HUD screen visits map and returns to game. The proof reads logged observations independently of the skill terminal status.

map.place (Choose a listed place, group map): start game; 52 seconds; plan set_waypoint {'kind': 'shop'}. Proof: Real legend entry selected and purple route persists in final minimap. Unavailable evidence or implementation: Selected legend entry identity/type missing: legend reader and conductor head/play logger.

map.mission (Choose a mission, group map): start game; 52 seconds; plan set_waypoint {'kind': 'mission'}. Proof: Mission legend entry and resulting route. Unavailable evidence or implementation: Independent selected legend identity/type missing: legend reader and conductor head/play logger.

goal.keep (Keep a goal, group goal): start game; 60 seconds; plan no standalone plan. Proof: Stable goal id through completion or listed interrupt, no plan replacement. Unavailable evidence or implementation: Goal lifecycle/id/end condition missing from head/play logger; no fixed goal plan.

incident.menu (Close an unexpected menu, group incident): start harvested event; 5 seconds; plan harvested, no standalone plan. Proof: HUD menu onset to game <=5s. Unavailable evidence or implementation: Recovery handler result/attempt id missing: conductor play/head logger.

incident.down (Resume after death or arrest, group incident): start harvested event; 30 seconds; plan harvested, no standalone plan. Proof: Death/arrest, respawn, then playing within 30s. Unavailable evidence or implementation: Explicit respawn timestamp and resumed control missing: HUD reader and cli logger.

incident.wanted (Lose wanted stars, group incident): start harvested event; 180 seconds; plan harvested, no standalone plan. Proof: HUD wanted rises above zero and reaches zero within 180s. Unavailable evidence or implementation: Recovery handler result/attempt id missing: conductor play/head logger.

chain.basic (Basic chain, group chain): start foot; 150 seconds; plan enter_vehicle {'duration': 20, 'kind': 'any'}, set_waypoint {'kind': 'shop'}, drive_route {'duration': 60}, press {'button': 'triangle', 'duration': 1}. Proof: Ordered entry, real place route, stopped arrival, exit in one session. Unavailable evidence or implementation: Real legend selection and arrival declaration missing; depends on map.place proof.

Proof implementations read play.reading.minimap for exit and entry mode; entry timing can disprove the 20-second limit but cannot prove a stationary, driverless target. Walking requires an independent moving field with coverage for twenty seconds, moving for more than half the interval, no three-second hold and sample gaps below three seconds. The historical logs contain no such field; motion=going in a skill reason and pad commands are deliberately not accepted as independent movement. Route following reads gps_distance and gps_speed, needs 100 metres of progress in thirty seconds, and rejects five-second holds or insufficient sampling. Arrival additionally needs stopped speed, at most thirty metres and an arrival declaration in the head sentence. Walk-to only targets the nearest visible yellow blip in the existing skill; a purple waypoint route does not satisfy that start condition. It requires a target-bound metric distance field, which is not persisted. Generic GPS distance cannot independently prove arrival at that blip. Map round-trip uses HUD map/game transitions. Place and mission selection can falsify completion with a full final second of route=none, but cannot certify the legend identity from a skill-authored success string.

Harvesting detects menu onset, death/arrest and wanted-star onset from HUD transitions in every imported and newly run source session, excluding an intentional set_waypoint menu. A vehicle hold can be harvested only when independent moving observations exist. Separate event_start values keep repeated incidents distinct. Resolution windows are five, thirty, 180 and ten seconds as specified. Missing recovery-handler terminal results and attempt ids currently prevent these observations from being counted as skill/proof successes; respawn also needs an explicit timestamp. The frozen sample exposes no harvestable events. The board states these limitations rather than inventing incident successes.

The failure taxonomy uses see, decide, act, proof, world, tech and unclear. Sustained stale frames for two seconds, HTTP errors and explicit stream/clock errors indicate tech; an ordinary unsent duplicate pad tick with status=null does not. HUD health loss, wanted stars, death/arrest/failed screens and corresponding events supply world evidence. A generic timeout with an entry plan and delivered empty detections is see; observed GPS approach without arrival is act; unsupported ambiguity stays unclear. Exact terminal mappings follow. A null mapping means success or a reason that needs the contextual checks, with unclear as the fallback.

see: 'map-unreadable'; 'minimap-unreadable'; 'nothing found'; 'detections lost after entry press'; 'map-picture-missing-or-damaged'; 'interactive-map-or-cursor-unverified'; 'player-marker-unreadable; centre the map manually'; 'target-not-uniquely-trackable; inspect the map manually'; 'target-tracking-unverified; inspect the selected marker'; 'map-texture-unverified; need a clean detailed map'; 'map-shift-unverified; damaged or ambiguous map pair'; 'sea-or-distance-unverified-after-inland-look'; 'minimap unreadable; restore an on-foot game view'; 'target person lost; restore visibility before retrying'; 'no person found; face a visible person before retrying'; 'blip-gone'; 'blip-bearing-undefined'; 'waypoint-unproven-on-a-later-page'; 'return-unverified'.

decide: 'interrupted'; 'replaced'; 'already in a vehicle'; 'not on foot'; 'wrong-screen-while-exiting; gameplay observed'; 'start-screen-unverified; start from visible gameplay'; 'existing-waypoint-at-target; avoid toggling it off'; 'player is in a vehicle; exit before punching'; 'person already on the ground; face a standing person'; 'selection-changed-before-waypoint'.

act: 'failed-recovery'; 'blocked'; 'stuck'; 'vehicle out of reach'; 'door locked or blocked'; 'entry press had no effect'; 'could not reach it'; 'gameplay returned without a waypoint'; 'waypoint-not-visible-after-cross'; 'cursor-did-not-approach-target; check stick direction and map scale'; 'cursor-move-limit'; 'map-unmoved-after-alternate; check map edge or video feed'; 'map-shift-wrong-direction; check stick mapping'; 'map-move-limit'; 'melee-target-too-far'; 'legend-selection-did-not-move'; 'legend-selection-skips-the-place'.

world: 'death_or_arrest'; 'objective'; 'low_health'; 'stars'; 'gameplay interrupted; restore the game screen'; 'health-depleted'; 'health-still-low'; 'health below 30%; retreat and recover'.

tech: 'clock-reversed'; 'clock-invalid'; 'invalid observation'; 'invalid observation time'; 'invalid-observation-time'; 'no-frame'; 'no detections delivered at all'; 'picture-unchanged-after-input; check the video feed'; 'invalid observation; check detector and HUD readings'; 'person detector unavailable or stale; check detector delivery'.

Context-dependent or successful terminal reasons: 'time-limit'; 'route-gone'; 'arrived'; 'entered vehicle'; 'vehicle drove away or was lost'; 'levelled'; 'combat-timeout'; 'waypoint set; route on the minimap'; 'waypoint set; no route yet'; 'limit'; 'punch time limit reached; move closer or choose another person'; 'target person remained on the ground'; 'aligned'; 'no-red-blips'.

Dynamic reason prefixes: 'skill-error:' => tech; 'wrong-screen:' => decide; 'map-check-failed:' => see; 'no-visible-' => see; 'legend-selection-skips-the-place:' => act; 'place-not-in-legend:' => see; 'nothing found; road search unavailable:' => see; 'goal_' => decide; 'waypoint set:' => context-dependent or success; 'time-limit:' => context-dependent or success. Terminal suffixes such as gameplay observed and places are matched against the underlying exact reason. time-limit prefixes inspect their failure or phase. Composite road-search failures map to see; goal_ stops and replaced plans map to decide. Literal proof contradictions override this reason map.

The frozen baseline comparison uses the existing basics.py interpretation on these same attempts: leave 3/3 with four excluded; walk 5/6; enter 2/5; legend place 15/18; cursor waypoint 0/3; drive 0/1 with three excluded. basics.py accepts skill status for waypoint placement, parses skill-owned motion diagnostics for walking, and counts entered/already seated status for entry. The bench merges cursor and legend placement into map.place, requires independent evidence, excludes the already-seated entry, and cannot certify the other successful entry without occupancy and standstill evidence. This changes both numerator and denominator intentionally.

foot.walk: 0/0 counted successes; 6 excluded; state not measurable; failure causes {}; median counted session duration None seconds.

foot.enter: 0/3 counted successes; 2 excluded; state not measurable; failure causes {'act': 2, 'see': 1}; median counted session duration 32.992 seconds.

car.leave: 3/3 counted successes; 4 excluded; state too few tries; failure causes {}; median counted session duration 7.987 seconds.

car.follow: 0/1 counted successes; 3 excluded; state not measurable; failure causes {'decide': 1}; median counted session duration 66.0 seconds.

map.place: 0/20 counted successes; 1 excluded; state not measurable; failure causes {'decide': 2, 'see': 4, 'proof': 14}; median counted session duration 31.991 seconds.

The final unclear share is 0/24 counted failures, also 0/43 imported attempts. This meets the below-ten-percent target but does not hide the sixteen excluded attempts. Logging independent movement, target occupancy/motion, selected legend identity and recovery results would lower exclusions. Better calibrated world-event and reader evidence remains necessary for future ambiguous failures. The repair ranking is led by map.place proof contradictions, then entry approach failures and selecting an existing waypoint; the complete ordered ranking and all source folders are on the board. Source commit comparison is unavailable for the historical sample, and the board says unknown instead of implying a before/after result.

All fourteen skill/proof disagreements were inspected using their four-frame video sheets, including the final decoded video frame, and the last native head image. Each sheet has four source frame indices spread across the video. None showed a continuous purple navigation route at the end. Single purple markers remain visible in several images. The proof is supported for the specified visible-route requirement; the stronger assertion that no waypoint was set is not established. On-foot route-display semantics may require a future product decision and a different independent waypoint field; the task criterion was preserved here. The cases follow, using the common /Users/kerim/recordings/pilot/20261112- prefix.

120925: daylight, marker lower/right; no visible route in the four-frame sheet or last native head image. Skill says waypoint set, proof says false, and the visual evidence supports the proof for the catalogue criterion.

120959: daylight, marker centre/right; no visible route in the four-frame sheet or last native head image. Skill says waypoint set, proof says false, and the visual evidence supports the proof for the catalogue criterion.

121033: daylight, marker lower/centre; no visible route in the four-frame sheet or last native head image. Skill says waypoint set, proof says false, and the visual evidence supports the proof for the catalogue criterion.

121141: dusk, marker right/centre; no visible route in the four-frame sheet or last native head image. Skill says waypoint set, proof says false, and the visual evidence supports the proof for the catalogue criterion.

121249: dusk, marker right/lower; no visible route in the four-frame sheet or last native head image. Skill says waypoint set, proof says false, and the visual evidence supports the proof for the catalogue criterion.

121323: dusk, marker left/centre; no visible route in the four-frame sheet or last native head image. Skill says waypoint set, proof says false, and the visual evidence supports the proof for the catalogue criterion.

121639: night, marker lower/left; no visible route in the four-frame sheet or last native head image. Skill says waypoint set, proof says false, and the visual evidence supports the proof for the catalogue criterion.

121713: night, marker uncertain in the small dark minimap; no visible route in the four-frame sheet or last native head image. Skill says waypoint set, proof says false, and the visual evidence supports the proof for the catalogue criterion.

121746: night, marker right/lower; no visible route in the four-frame sheet or last native head image. Skill says waypoint set, proof says false, and the visual evidence supports the proof for the catalogue criterion.

121821: night, marker left/middle; no visible route in the four-frame sheet or last native head image. Skill says waypoint set, proof says false, and the visual evidence supports the proof for the catalogue criterion.

121855: night, marker left; no visible route in the four-frame sheet or last native head image. Skill says waypoint set, proof says false, and the visual evidence supports the proof for the catalogue criterion.

121929: night, marker upper/left; no visible route in the four-frame sheet or last native head image. Skill says waypoint set, proof says false, and the visual evidence supports the proof for the catalogue criterion.

122003: night, marker right/upper; no visible route in the four-frame sheet or last native head image. Skill says waypoint set, proof says false, and the visual evidence supports the proof for the catalogue criterion.

122406: daylight, marker left/middle, quad-entry subtitle; no visible route in the four-frame sheet or last native head image. The actual final video frame shows the figure on foot, but the minimap reader switches to tilted at 6.764 seconds and records vehicle through 31.991 seconds. The head image is from about 6.8 seconds and is not itself final-frame proof. This is a reader/video mode disagreement, so the ledger end_mode=vehicle is uncertain. Both the final image and logged route support the narrower no-visible-route failure; the mode reading must not be promoted to a claim that the figure actually entered a vehicle.

The runner is operationally untested against the console by design. It starts only with explicit session_up=true, human_input=false and recording=false. A controller takeover stops the pilot and excludes the try. The wait probe has camera levelling disabled. Missing start state is produced by foot.enter, map.place or car.leave as separately judged ledger attempts; the observed resulting state, not an unsupported proof pass, determines whether setup succeeded. Unavailable start-state producers stop safely. Three consecutive tech failures of one capability stop the loop. Objective text or a yellow route blocks movement by default; --allow-mission explicitly lifts this guard. Purple routes and generic blips alone cannot establish mission activity. The output directory is a recording parent, and the runner discovers the recorder-created session child before judging it.

The reviewer can reproduce the offline import without touching recordings using the following commands from the repository root. An already imported session/capability is not imported twice. ffmpeg and ffprobe are required for new four-frame sheets; the HTML embeds the generated JPEGs and needs no outside assets.

```sh
cd pilot
env -u PS5_HOST .venv/bin/python tools/bench.py --ledger ../lab/bench/rebuilt.jsonl import ../lab/bench/import-source.tsv
env -u PS5_HOST .venv/bin/python tools/bench.py --ledger ../lab/bench/rebuilt.jsonl board
```

The first authorized console round uses the existing configured bridge session, with the physical controller released and bridge recording stopped. Run from pilot/. These commands were not executed during this task. The first line covers the runnable isolated foot, vehicle and map capabilities; incident capabilities are harvested automatically. car.free, car.turn, foot.roadside and goal.keep cannot be staged as standalone plans and remain visible in the catalogue. Walk-to must be run separately after a yellow blip has been visually established; no catalogue capability safely produces it. The mission target round and chain are separate so the default mission guard can stop safely when an objective appears.

```sh
.venv/bin/python tools/bench.py run foot.view foot.walk foot.enter car.follow car.arrive car.leave map.open_close map.place --tries 10
.venv/bin/python tools/bench.py board
.venv/bin/python tools/bench.py run foot.walk_to --tries 10 --allow-mission
.venv/bin/python tools/bench.py run map.mission --tries 10 --allow-mission
.venv/bin/python tools/bench.py run chain.basic --tries 10
.venv/bin/python tools/bench.py board
```

To rejudge a recorded attempt, use .venv/bin/python tools/bench.py judge /absolute/session --capability map.place. To record a reviewed correction, use .venv/bin/python tools/bench.py mark /absolute/session --capability map.place --outcome failed --cause see --note "Reviewed the final minimap; reader classification was wrong" and regenerate the board. These commands use the default recordings ledger only when the reviewer intentionally runs them.

Validation: the final focused suite passes all 30 tests with `env -u PS5_HOST .venv/bin/python -m pytest -q tests/test_bench.py`. It covers the four-way outcome table, proof independence, partial proofs, start exclusion, target-bound blip proof, arrival declarations, sparse HUD evidence, reason mapping, append-only revisions and marks, ranking, actual head-plan validation, recorder-created child directories, preflight rejection, controller takeover, setup producers, consecutive technical failures, mission blocking/override and incident harvesting. Ruff lint and formatting checks pass.

The required `env -u PS5_HOST .venv/bin/python tools/gate.py --full` was run from pilot/. Its result was 3248 passed, 3 skipped, 236 expected failures, 5 failed and 5 setup errors in 778.70 seconds. The full matrix started before the final additions to the bench-only tests; those final changes were verified by the 30-test focused suite and final lint/format checks. Every unexpected full-matrix result is within the card's allowed socket/CoreML sandbox exception. The final output is preserved in [gate-full.txt](../../lab/bench/gate-full.txt). No protection was bypassed and no live console endpoint was contacted to resolve these environment errors.

Socket binding returned `PermissionError: [Errno 1] Operation not permitted` in `tests/test_commentator.py::test_twitch_local_irc_handshake_ping_fragmented_chat_and_filter`, `tests/test_overlay.py::test_http_growing_log_updates_within_one_second_and_reconnects`, `tests/test_overlay.py::test_partial_malformed_and_replaced_logs_remain_usable`, `tests/test_overlay.py::test_missing_root_new_session_and_idle_end`, and `tests/test_overlay.py::test_local_assets_served_without_external_dependencies`.

CoreML model compilation could not create its working directory under the sandboxed temporary URL. This affected `tests/test_objects.py::test_real_traffic_and_player_exclusion`, `tests/test_objects.py::test_bad_frames_are_rejected[None]`, `tests/test_objects.py::test_bad_frames_are_rejected[bad1]`, `tests/test_objects.py::test_bad_frames_are_rejected[bad2]`, and `tests/test_objects.py::test_reports_below_the_confidence_floor_are_left_out`. These tests failed during detector fixture setup, before their assertions.

The Done when criteria are met under that documented environment exception. The live console round remains deliberately unexecuted. The local bench artifacts occupy less than 2 MB, below the 5 MB limit.

The work is left on the existing feat/pilot-bench branch for integration. docs/tasks/README.md says: "Git cannot write here: no commit, stash, checkout or reset. Leave your changes in the working tree; the reviewer commits them." This worktree also exposes Git metadata as read-only. That task handoff differs from the normal global branch-and-PR workflow in ~/.codex/AGENTS.md; no commit, push or pull request was attempted. Only the five owned paths were changed.
