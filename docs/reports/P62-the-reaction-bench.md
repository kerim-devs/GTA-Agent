P62 is implemented and locally verified. The final run contains 84 serial realtime trials across seven variants and twelve scenes, plus 24 explicitly modelled trials for reflex and pilot. No approach errors were recorded in the final realtime run. Reflex answers four of nine threats within three seconds; the existing cached-text pilot answers one. The remaining pilot cases are failures to answer, not evidence that a 74 ms median generalizes. The nine-threat/three-control sample falls below the target and is unsuitable for a broad quality ranking.

The [standalone board](../../lab/reaction/board.html), [Markdown board](../../lab/reaction/board.md), [append-only ledger](../../lab/reaction/ledger.jsonl) and [measured cost table](../../lab/reaction/costs.json) retain the evidence. The board was opened at localhost and visually checked at 1920 by 1080, including the [scene timelines](../../lab/reaction/timeline.png). Its only browser console error was the local server's missing favicon. The table below is copied from the generated final board. Each number inherits its row's mode. Reaction medians, p90 and worst use non-void answered trials, including answers later than three seconds; the share column separately applies the three-second limit. The head's 3277 ms answer and modelled pilot's 3971 ms answer therefore affect reaction statistics but not the answered share. Decision time is the median of scene medians. For pilot/head it measures the current skill-input frame, not the model request's duration; the request-to-plan chain is retained separately.

| Approach | Mode | Threat/calm trials | Answer ≤3s | Median / p90 / worst ms | With link ms | False alarms | Calm / scene / min | Decision ms | Hz |
|---|---|---:|---:|---|---|---:|---|---:|---:|
| Kerim | recorded-human-estimated | 9/3 | 11.1% | 784.6 / 784.6 / 784.6 | 919.6 / 919.6 / 919.6 | 16 | 0.0 / 0.0 | n/a | n/a |
| head (delayed-stub) | realtime | 9/3 | 11.1% | 1791.0 / 2979.8 / 3277.0 | 1926.0 / 3114.8 / 3412.0 | 0 | 0.0 / 0.0 | 13.6 | 24.2 |
| judge (delayed-stub) | realtime | 9/3 | 22.2% | 569.2 / 703.4 / 737.0 | 704.2 / 838.4 / 872.0 | 1 | 0.0 / 0.0 | 403.0 | 30.0 |
| judge-second (delayed-stub) | realtime | 9/3 | 22.2% | 952.2 / 1151.1 / 1200.9 | 1087.2 / 1286.1 / 1335.9 | 1 | 0.0 / 0.0 | 396.9 | 30.0 |
| pilot | modelled | 9/3 | 11.1% | 2020.7 / 3580.7 / 3970.7 | 2155.7 / 3715.7 / 4105.7 | 0 | 0.0 / 0.0 | 13.6 | 30.0 |
| pilot | realtime | 9/3 | 11.1% | 74.2 / 74.2 / 74.2 | 209.2 / 209.2 / 209.2 | 0 | 0.0 / 0.0 | 12.8 | 29.9 |
| policy (delayed-stub) | realtime | 9/3 | 22.2% | 402.1 / 403.1 / 403.3 | 537.1 / 538.1 / 538.3 | 1 | 0.0 / 0.0 | 401.1 | 30.0 |
| reflex | modelled | 9/3 | 44.4% | 53.1 / 606.4 / 836.4 | 188.1 / 741.4 / 971.4 | 2 | 0.0 / 0.0 | 12.7 | 30.0 |
| reflex | realtime | 9/3 | 44.4% | 38.7 / 609.1 / 839.1 | 173.7 / 744.1 / 974.1 | 2 | 0.0 / 0.0 | 12.4 | 29.7 |
| reflex+judge (delayed-stub) | realtime | 9/3 | 33.3% | 5.5 / 326.1 / 406.2 | 140.5 / 461.1 / 541.2 | 2 | 0.0 / 0.0 | 388.8 | 30.0 |


![Verified local board](../../lab/reaction/board.png)

All seven realtime variants precede Kerim on wanted-02, the only scene with a valid human reference. None is after him on that valid subset. The other eight human trials are void and have no defensible before/after ranking. The table gives onset-to-input times and their difference from Kerim's aligned 784.6 ms, without adding the shared 135 ms link. In particular, a few milliseconds of reflex latency is a capture-aligned reader/input result, not evidence of successful protection.

| wanted-02, realtime | Reaction, ms | Before Kerim, ms |
|---|---:|---:|
| reflex | 3.3 | 781.3 |
| pilot | 74.2 | 710.4 |
| judge | 401.5 | 383.1 |
| judge-second | 703.5 | 81.1 |
| head | 305.1 | 479.5 |
| reflex+judge | 4.8 | 779.8 |
| policy | 403.3 | 381.3 |

The final P62 suite passed all 13 tests in 7.09 seconds with the task-authorized local socket available. It covers timing, the pre-onset veto, calm false alarms, real and modelled delays, second-answer confirmation, hybrid withdrawal/staleness, registry extension, human clock alignment, pilot cleanup, ledger/board modes and real local HTTP paths for judge, head and policy. Ruff check and format check passed for all four Python files. The required full gate's sandbox-only failures are named individually below. Commands were run from pilot:

```sh
env -u PS5_HOST .venv/bin/python -m pytest tests/test_reaction.py -q
env -u PS5_HOST .venv/bin/ruff check src/pilot/reaction.py src/pilot/approaches.py tools/reaction.py tests/test_reaction.py
env -u PS5_HOST .venv/bin/ruff format --check src/pilot/reaction.py src/pilot/approaches.py tools/reaction.py tests/test_reaction.py
env -u PS5_HOST .venv/bin/python tools/gate.py --full
env -u PS5_HOST .venv/bin/python tools/reaction.py run reflex pilot --mode modelled --cost-table ../lab/reaction/costs.json
```

Fast mode uses the median measured step cost for each approach, cited to the final ledger revision and machine in costs.json. It cannot reproduce all wall-clock scheduling and image-processing interactions. Its extra late pilot answer on wanted-01 is modelled, not a measured improvement; no cross-mode ranking is made. The final implementation SHA-256 is `f4e0a1a16dcf905cb52114fed45550ccdf2915c7f4bde2904e636e18a88fbc36`. The ledger also records the base commit, dirty tree, scene hash and machine for each trial.

P62 adds an offline first-reaction runner, seven registered variants covering the six requested approaches, data-driven answer sets, native-frame contact sheets, an append-only ledger and a standalone Markdown/HTML board. The implementation stays within the card's file list. It does not change the conductor, skills, judge, CLI or P58 bench.

The reviewed dataset contains nine threats, three of each requested kind, and three playable on-foot controls. The thirty-plus-thirty target was not reached. Nine threats were verified, not a claim that the recordings contain only nine. Twenty-one further independent, frame-verified threat onsets and twenty-seven usable controls remain missing from this curated set. Thirty initially plausible calm label windows were rejected after looking at their sheets: most were cutscenes with stale health labels and no playable HUD. A strict search across integer-second centers in the seven retained recordings yielded three disjoint flat-map control windows without aim/fire. Vehicle controls were excluded because R2 means throttle there; they need context-specific answer definitions. This is a small diagnostic set, not a representative performance ranking.

Every accepted onset was proposed from label changes and nearby human actions, refined on native decoded RGB frames, then confirmed or moved by inspecting adjacent-frame sheets. The maximum declared uncertainty is one native frame. The enemy candidates in recording 164039 at 632.986, 648.6848 and 670.8731 were discarded because red was already visibly present before the reader changed. The 065022 candidate at 197.497 was also discarded because red was already beneath the player marker. The 092019 health candidate at 547.7011 was a transparent moving vehicle map, not a sufficiently clear hit. Full source recordings were neither copied nor modified. The source clock is frames.jsonl, never MP4 nominal FPS; capture batches and gaps remain visible in the timings.

Kerim's raw pad states are held between changes and placed on picture time as pad.t + labels.lead. The existing action labeller samples hand windows at frame.t - lead, so adding the lead is the matching inverse. All retained leads are estimated, ranging from 0.14 to 0.18 seconds. The 20 ms estimator grid is a resolution, not a confidence interval; residual systematic offset, capture batching and controller sampling remain uncalibrated. The strict pre-onset rule voids eight of his nine threat trials because an accepted state was already held in the preceding two seconds. His one valid sample supplies the displayed median and p90; they cannot support a population comparison. Raw first post-onset inputs are still shown in the sheets and scene metadata. A frame marked as a held input or a void reference is not a new deliberate response to the onset.

The benchmark releases the latest captured frame according to wall time and asks for a complete pad at 30 Hz. Compute and decode time are spent for real, and missed ticks are skipped. A model answer records its own source capture separately from the latest available frame. Detection age is unavailable here because the object Reader is disabled; it is not replaced with a cheap minimap timestamp. The 135 ms addition is LINK_SECONDS, sourced to docs/LOG.md:15: the median of ten camera measurements at a 60 fps stream. It was not measured again by this replay.

The pilot variant runs the existing Pipeline, EventDetector, MissionHead with the offline ScriptedHead fallback, Conductor and SkillRunner. Timestamped derived OCR is released after its stored processing duration and passed into both HUD classification and the conductor. This is a cached-text, no-object-reader configuration. The wall-clock rule/plan/skill measurements are real, but fresh Vision/CoreML processing and the live judge-assisted configuration were not benchmarked. The head variant additionally requests on changed minimap threat, health or wanted readings. Its HTTP mode and all other model-labelled results use the local delayed pixel-reader stub. No gaming-PC vision model, Codex inference or policy model was run, and no model-quality conclusion follows from the stub scores.

The recording does not react to the emitted inputs. These results cover first answers and initial false alarms only. They do not prove survival, aim accuracy, successful escape, successful combat or any console capability. A response matching an allowed input can also coincide with an existing plan; the chain trace, rather than the pad alone, is needed before claiming that the threat caused it.

To reproduce the local run, start the delayed server in one terminal and run the benchmark from pilot in another. No PS5_HOST value is needed or set.

```sh
env -u PS5_HOST .venv/bin/python tools/reaction.py stub --delay 0.25 --action pixels
env -u PS5_HOST .venv/bin/python tools/reaction.py scenes --sheets
env -u PS5_HOST .venv/bin/python tools/reaction.py run reflex pilot judge judge-second head reflex+judge policy --endpoint http://127.0.0.1:18762 --model delayed-stub
env -u PS5_HOST .venv/bin/python tools/reaction.py board --comparisons
```

The ledger retains the aborted and superseded trials. The board selects the current scene and implementation hashes, keeps repeated completed trials on that revision, separates model names and modes, and deduplicates the human reference. Every row carries the measured/modelled distinction; estimated human alignment is labelled separately. Missing answers are not zero. False alarms are contiguous active episodes, with matching tick counts retained separately.

The reviewer can run the actual model variants with these commands from pilot. They were prepared but not executed.

```sh
env -u PS5_HOST .venv/bin/python tools/reaction.py run judge judge-second reflex+judge --endpoint http://192.168.0.248:1234 --model qwen/qwen3-vl-8b
env -u PS5_HOST .venv/bin/python tools/reaction.py run head --endpoint http://192.168.0.248:1234 --model qwen/qwen3-vl-8b
env -u PS5_HOST .venv/bin/python tools/reaction.py run head --codex
env -u PS5_HOST .venv/bin/python tools/reaction.py board --comparisons
```

P63 receives the documented POST /policy request/reply contract and delayed stub. A real policy server, its model, deployment and console transport remain outside P62. The worked registry extension and complete protocol are in lab/reaction/README.md.

For live measurement, current play.jsonl rows contain t, frame_id, fresh, reading, skill, result, sent_pad, sent and status. run_play computes received - frame.age internally but does not write capture time or frame age into those rows. frame_id can be joined to the recording frame metadata. Missing fields are the capture and reader-source times, OCR availability, event/onset evidence, request/response/apply times, plan activation, first answering decision time and precise send time. head.jsonl has request/response t and response duration, but no capture identifier for an end-to-end join. The reviewer should add those fields in the owning modules, preserving monotonic clocks and distinguishing compute, queue, acceptance and link delay.

A future P58 threat capability needs a repeatable manually staged on-foot gameplay state with a usable far camera, a known nearby hostile encounter, full health, no wanted stars and a released human controller. The start proof must show playable HUD and no threat during the pre-onset window. The success proof must contain the first native threat frame and its predecessor, the first matching sent_pad and sent result, plus video through the expected 135 ms link interval. A threat that never appears, a held pre-onset answer or a human interruption invalidates the try. The existing P58 catalogue has no threat/fight entry, start state or corresponding proof; this task does not add one.

The first reviewer console round can use the existing commands below. The first command only prints the existing foot.view rehearsal. Before the second, the reviewer must inspect the actual gameplay picture, stage the on-foot threat, and verify that bridge /pad is clear. The second command performs a standalone twelve-second Fight recording; it is not an integrated reaction-bench result. These commands were not executed.

```sh
env -u PS5_HOST .venv/bin/python tools/bench.py run foot.view --tries 1 --minutes 3 --dry
env -u PS5_HOST .venv/bin/python -m pilot.cli play --no-level --head scripted --plan '[{"name":"fight","args":{"duration":12,"cover":"no"}}]' --seconds 12 --judge 'http://192.168.0.248:1234=qwen/qwen3-vl-8b' --record-dir /Users/kerim/recordings/pilot
```

There is no approach switch in pilot play yet. The reviewer can add an explicit approach selector in the owning CLI/conductor code and route each approach through the existing observation and pad-safety boundaries. The selector must preserve logging, neutral release, human takeover and the capability proof. Adding a benchmark name to REGISTRY alone does not wire live control.

No git mutation or PR was performed. docs/tasks/README.md explicitly says: “Git cannot write here: no commit, stash, checkout or reset. Leave your changes in the working tree; the reviewer commits them.” The direct worker instruction makes that task restriction binding. No daemon, ps5rp, console endpoint, remoteplay credentials, paid service or real model server was contacted.

The required full gate completed with 3,534 passed, 3 skipped, 236 xfailed, seven failures and six setup errors. The complete output is retained in [gate-full.log](../../lab/reaction/gate-full.log). Each failure was a sandbox refusal to bind a local socket (`PermissionError: [Errno 1] Operation not permitted`): `tests/test_bench.py::test_the_bridge_door_reads_the_status_and_posts_pad_states`, `tests/test_commentator.py::test_twitch_local_irc_handshake_ping_fragmented_chat_and_filter`, `tests/test_overlay.py::test_http_growing_log_updates_within_one_second_and_reconnects`, `tests/test_overlay.py::test_partial_malformed_and_replaced_logs_remain_usable`, `tests/test_overlay.py::test_missing_root_new_session_and_idle_end`, `tests/test_overlay.py::test_local_assets_served_without_external_dependencies`, and `tests/test_reaction.py::test_local_delayed_http_judge_policy_and_head`.

The six setup errors came from the shared CoreML detector fixture, which could not create its compiled-model working directory under `/var/folders/`. The affected tests were `tests/test_objects.py::test_real_traffic_and_player_exclusion`, `tests/test_objects.py::test_bad_frames_are_rejected[None]`, `tests/test_objects.py::test_bad_frames_are_rejected[bad1]`, `tests/test_objects.py::test_bad_frames_are_rejected[bad2]`, `tests/test_objects.py::test_reports_below_the_confidence_floor_are_left_out`, and `tests/test_objects.py::test_the_real_detector_gives_the_cut_out_figure_beside_the_filtered_list`. These are the socket/CoreML exceptions explicitly allowed by the card's Done when clause. The full gate preceded the final localized instrumentation and board corrections; the final P62 suite and lint checks are reported with the measured results above.

The wanted-01 recording is in a vehicle. Its answer is scored against the card's shared nominal input set. In particular, an R2 response there would be throttle, and an on-foot sprint pad does not establish a successful vehicle escape. That scene can diagnose detection and input latency but cannot establish tactical correctness. Future scene sets should carry action-context-specific answer definitions before comparing controller quality.

Only one pilot trial has a valid reaction, so a ranking of three finite slowest reactions does not exist. The three enemy scenes are tied censored failures through the four-second post-onset window. Their traced links below explain the missing response. Event and request times are relative to onset; differences are elapsed wall time, while CPU medians are reported separately and must not be added to the elapsed chain a second time.

| Pilot scene, realtime | Onset to first post-onset event | Event to request | Request to head completion | Completion to plan acceptance | Plan to answering pad |
|---|---:|---:|---:|---:|---|
| enemy-01 | 2106.169 ms | 2.357 ms | 0.159 ms | 29.358 ms | No answer through 4000 ms after onset |
| enemy-02 | 1571.086 ms | 2.761 ms | 0.148 ms | 29.477 ms | No answer through 4000 ms after onset |
| enemy-03 | No post-onset event | No request | No new head result | No new plan | No answer through 4000 ms after onset |

In enemy-01, the first event is HUD-present, not enemy detection. The head chooses wait for sixty seconds. In enemy-02, HUD-present eventually reaches the head, which chooses a shop waypoint and drive route, then another route attempt. Neither plan answers the threat. In enemy-03, a pre-onset walk-road plan continues without a threat event or a new request. The dominant failure in these scenes is absent threat handling, with additional HUD acceptance delay in the first two, rather than expensive rule-head computation. These findings apply to the cached-text, no-object configuration measured here.

| Realtime median CPU per stage, ms | Readers | Events | HUD events | Head when called | Plan when accepted | Skill |
|---|---:|---:|---:|---:|---:|---:|
| enemy-01 | 0.822 | 0.012 | 0.001 | 0.127 | 0.021 | 0.002 |
| enemy-02 | 0.815 | 0.009 | 0.001 | 0.087 | 0.061 | 0.002 |
| enemy-03 | 2.056 | 0.197 | 0.001 | 0.072 | 0.013 | 1.490 |

For the successful wanted-02 trial, the complete elapsed chain is onset to request 8.526 ms, request to head completion 0.169 ms, completion to accepted plan 32.330 ms, and plan acceptance to first matching pad 33.202 ms: 74.228 ms total, or 209.228 ms with the historical link median added. The head's CPU call itself takes 0.111 ms. At the answering tick, reader CPU is 3.973 ms, events 0.042 ms, HUD events 0.003 ms, skill 0.404 ms, and total step compute 5.353 ms. The latest frame is 6.328 ms old; detection and judgment ages are unavailable. Goal arbitration requests the escape plan before the debounced wanted-changed event at 509.157 ms. Tick-level plan acceptance and the following skill tick account for most of this successful reaction.

The scene inventory below gives picture-clock seconds within each original recording. All threat sheets contain adjacent native frames around the selected onset; each has one-frame declared uncertainty. The control time is only a window center and is not a threat onset. The `notes` field preserves rejected reader proposals and the visual correction where applicable.

| Scene | Recording | Onset / center, s | Lead, s | Human reference | Visual onset evidence |
|---|---|---:|---:|---|---|
| enemy-01 | 20261111-172549 | 412.4980 | 0.18 | void: held answer before onset | Replaced 065022 candidate: red was already present under player arrow. First readable red with HUD appearing at native frame 24610, preceding frame 24609 has no HUD. |
| enemy-02 | 20261112-092019 | 395.9990 | 0.18 | void: held answer before onset | Moved from reader proposal 396.100: native frame 23428 first visible red blips, frame 23427 has map but no red. |
| enemy-03 | 20261111-185323 | 356.2190 | 0.16 | void: held answer before onset | Native frame 21301 first red blips and muzzle flash, frame 21300 has neither. |
| hit-01 | 20261111-190825 | 396.3643 | 0.18 | void: held answer before onset | Label proposal 396.3980; native reader initial=0.6222222222222222; first change=396.3821. |
| hit-02 | 20261111-065022 | 210.8304 | 0.16 | void: held answer before onset | Label proposal 210.8982; native first change 210.8304. |
| hit-03 | 20261112-092019 | 565.0997 | 0.18 | void: held answer before onset | Label proposal 565.0997; native reader initial=None; first change=565.0997. |
| wanted-01 | 20261112-085011 | 161.6769 | 0.14 | void: held answer before onset | Label proposal 161.7632; native reader initial=0; first change=161.6769. |
| wanted-02 | 20261111-182316 | 391.3316 | 0.16 | valid | Label proposal 391.3316; native reader initial=0; first change=391.3316. |
| wanted-03 | 20261111-065022 | 209.4257 | 0.16 | void: held answer before onset | Label proposal 209.4917; native reader initial=0; first change=209.4257. |
| calm-walk-01 | 20261111-065022 | 12.0000 | 0.16 | calm control | Ordinary on-foot idle/look/walk. Null wanted samples allowed only with continuous flat HUD. No vehicle controls scored as combat inputs. |
| calm-walk-02 | 20261111-172549 | 489.0000 | 0.18 | calm control | Ordinary on-foot idle/look/walk. Null wanted samples allowed only with continuous flat HUD. No vehicle controls scored as combat inputs. |
| calm-walk-03 | 20261111-172549 | 499.0000 | 0.18 | calm control | Ordinary on-foot idle/look/walk. Null wanted samples allowed only with continuous flat HUD. No vehicle controls scored as combat inputs. |

The nine comparison panels below show the onset, frames around Kerim's aligned first input (150 ms before and after), his answer-time frame, and one answer frame for every realtime approach. A missing or void answer gets an explicit blank tile; no substitute frame is presented as an answer. The human raw input remains visible even where the pre-onset rule voids it. These panels contain realtime trials only.

![enemy-01: onset and realtime answer frames](../../lab/reaction/sheets/compare-enemy-01.jpg)

![enemy-02: onset and realtime answer frames](../../lab/reaction/sheets/compare-enemy-02.jpg)

![enemy-03: onset and realtime answer frames](../../lab/reaction/sheets/compare-enemy-03.jpg)

![hit-01: onset and realtime answer frames](../../lab/reaction/sheets/compare-hit-01.jpg)

![hit-02: onset and realtime answer frames](../../lab/reaction/sheets/compare-hit-02.jpg)

![hit-03: onset and realtime answer frames](../../lab/reaction/sheets/compare-hit-03.jpg)

![wanted-01: onset and realtime answer frames](../../lab/reaction/sheets/compare-wanted-01.jpg)

![wanted-02: onset and realtime answer frames](../../lab/reaction/sheets/compare-wanted-02.jpg)

![wanted-03: onset and realtime answer frames](../../lab/reaction/sheets/compare-wanted-03.jpg)


The retained lab/reaction artifacts total 4,144,889 bytes, below the 5 MB limit. All nine comparison panels and the final board were visually inspected. The local stub, browser session and temporary static server were closed. No source recordings were changed.

# P64: the bench widened

On 26 threat scenes on foot and 29 calm ones, each replayed once in real time, the reflex notices a threat after a median of 36 ms (ninth decile 1.27 s, worst 1.67 s; 23 scenes, 3 void) and answers after a median of 0.42 s (ninth decile 3.07 s, worst 3.90 s), but in only 16 scenes, because its Fight turns towards the marker before it aims and a replay does not turn with it. The real judge, qwen3-vl-8b, gives an answer in 0.17 s with the new letter question and 0.31 s with P62's JSON question, but it names the threat after the onset in only 13 and 15 of the 26 scenes; as a way of control it answers 6 and 7 scenes, at a median of 2.64 and 2.04 s (ninth decile 3.11 and 3.22 s), and judge-second 5 and 5 (2.33 and 1.34 s). reflex+judge notices as fast as the reflex (13 and 25 ms) but answers fewer scenes within three seconds than the reflex alone (11 and 10 against 14). The pilot notices 9 scenes (median 14 ms) and answers 8 (median 75 ms, ninth decile 0.69 s, worst 1.97 s; 3 of them void), all of them star onsets or false low-health readings and never an enemy marker. The head, with Codex's delay modelled at 8.47 s from head.jsonl, notices the six star onsets after about 0.54 s through the conductor's event and answers nothing within four seconds. NitroGen, asked as a policy through P63's server, takes 0.22 s an answer and presses whatever the scene shows: an answering input is on its pad on every one of the 29 calm scenes and in the two seconds before 22 of the 26 onsets, so 22 tries are void and its four answers (median 0.62 s) are presses that happened to fall after an onset. Kerim answers 12 scenes by P62's strict reading (median 0.879 s, ninth decile 2.114 s, worst 3.651 s; 13 void) and 23 by the looser one (median 1.261 s, ninth decile 3.509 s, worst 3.996 s). Wrong calls: on the calm scenes no way of control but the policy gave a false answer (the policy 157, on all 29), and none of the judge's 6,548 answers there named a threat. Before the onsets the reflex's 9 false notices are 7 health falls that the HUD reader makes up and 2 real markers, the pilot's 19 false answers are its low-health flight before three onsets, and the judge names a threat in about 15 % of its answers in the six seconds before an onset (armed allies in a mission, black screens), which voids 8 to 11 of its 26 tries. What holds the pilot back today is not compute: it has no rule that takes a red map marker for a threat, its HUD reader reads a health fall whenever an icon crosses the bar or the HUD fades in after a black screen, a model head that needs eight seconds answers after the window has closed, and the judge, though fast, names only 11 or 12 of the 20 enemy onsets and the police in 1 of 6 star onsets.

The numbers above are measured on this Mac, one try at a time, except the head's delay, which is modelled and marked so in every row. Times run from the onset frame to the decision, without the 135 ms link; the board gives them with the link too. On a threat scene a false answer or notice is an episode in the two seconds before the onset (P62's veto window), on a calm scene an episode anywhere in it.

## Two times per try

Every way of control now says on its decision why it acts (`Decision.noticed`), and the bench keeps the first such tick after the onset as "noticed", next to "answered", the first pad from the scene's answer set. The reflex says "red blip", "health fell" or "wanted stars"; the pilot passes on the conductor's threat events (stars changed, low health) and the head rules that act on a threat (`take_out_fight`, `wanted_`, `low_health`); the head and the judges say which threat the model named. The same veto as for answers applies: a notice held in the two seconds before the onset voids the notice time and counts as false. Kerim has the pad only, so his rows show answered and leave noticed empty.

The two times differ most for the reflex: it notices a marker within 0.04 s in most scenes but aims only once the marker lies ahead, and the replay's camera turns only when Kerim turned it. Its answered time on enemy scenes therefore measures when Kerim's own turning or the enemy's path put the marker in front, and the ten enemy scenes without a reflex answer are turns that the open-loop replay cannot finish. Its noticed time is the measure of the reflex; the time a live turn takes is not measured here.

| Scene | Kerim | Kerim looser | Reflex noticed | Reflex answered | Pilot noticed | Pilot answered | Head noticed |
|---|---:|---:|---:|---:|---:|---:|---:|
| enemy-01 | void | none | 0.057 | none | none | none | none |
| enemy-02 | void | 1.420 | 0.074 | none | none | none | none |
| enemy-03 | void | 0.185 | 0.008 | none | none | none | none |
| wanted-02 | 0.785 | 0.785 | 0.006 | 0.006 | 0.009 | 0.072 | 0.537 |
| wanted-03 | void | 1.132 | void | 0.809 | 0.544 | none | 0.538 |
| enemy-04 | 1.645 | 1.645 | 0.036 | none | void | void | 3.475 |
| enemy-05 | 0.669 | 0.669 | 1.405 | 1.708 | none | void | none |
| enemy-06 | void | 0.981 | 1.671 | 3.904 | none | none | none |
| enemy-07 | void | 1.809 | 0.009 | 2.439 | none | none | none |
| enemy-08 | none | none | 0.038 | none | none | none | none |
| enemy-09 | void | 3.755 | 1.440 | 2.109 | none | none | 2.488 |
| enemy-10 | void | 2.940 | 0.003 | none | none | none | none |
| enemy-11 | 3.651 | 3.651 | 0.006 | none | none | none | none |
| enemy-12 | 0.651 | 0.651 | 0.004 | 0.004 | none | none | none |
| enemy-13 | 2.101 | 2.101 | void | 2.408 | void | void | none |
| enemy-14 | 0.334 | 0.334 | 0.008 | 1.541 | none | none | none |
| enemy-15 | void | 3.996 | 0.705 | none | 0.078 | 0.140 | none |
| enemy-16 | 0.541 | 0.541 | 0.706 | none | 0.008 | 0.075 | none |
| enemy-17 | 1.461 | 1.461 | 0.006 | 0.006 | 1.900 | 1.971 | none |
| enemy-18 | 0.682 | 0.682 | 0.037 | 0.037 | none | none | none |
| enemy-19 | 2.116 | 2.116 | 0.038 | none | none | none | none |
| enemy-20 | 0.974 | 0.974 | 0.038 | 3.705 | none | none | none |
| wanted-04 | void | none | 0.008 | 0.008 | 0.011 | 0.076 | 0.541 |
| wanted-05 | void | 1.261 | 0.008 | 0.008 | 0.010 | 0.072 | 0.509 |
| wanted-06 | void | 2.150 | 0.005 | 0.005 | 0.016 | 0.078 | 0.542 |
| wanted-07 | void | 0.196 | void | 0.008 | 0.014 | 0.073 | 0.536 |

Seconds after the onset; "none" is no notice or answer within four seconds, "void" a matching state held in the two seconds before. The pilot's notices in enemy-15, 16 and 17 are its `low_health_on_foot` rule, not the enemy: in enemy-15 and 16 the HUD returns from a black screen at the onset and the health reader reads the fading-in bar as 0.0 for about 0.35 s although it is full, and in enemy-17 it reads a fall from 0.51 to 0.31 at +1.88 s that is undone within 0.2 s. The head's enemy-04 notice is a low-health event (the bar is red before and after the onset), and its enemy-09 notice is the modelled answer to the frame at the scene's start, 6.0 s before the onset, on which the stub read the last red marker of an earlier encounter. Counting only notices of the threat itself, the pilot and the head notice the six star onsets and none of the twenty enemy onsets.

## Why the reflex misses

Six threat scenes have no reflex notice within one second. For each, `reaction.py misses` wrote what the minimap and HUD readers return on every frame from 0.5 s before the onset to 2 s after it, as runs of frames with the same reading, to [misses.json](../../lab/reaction/misses.json); the frames around the HUD readings were looked at.

| Scene | Reflex noticed | What the readers return | What the frame shows | Cause |
|---|---:|---|---|---|
| enemy-05 | 1.405 s | `red-border` at the map's edge from +0.000 s; the first red away from the edge at +1.375 s | an enemy just outside the map's range, its marker pinned to the edge | border marker ignored |
| enemy-06 | 1.671 s | only `red-border` markers from +0.018 s to past +2 s; the notice is a health reading flickering between 0.50 and 0.39 at +1.65 s; red inside the map first at +2.49 s | two enemies pinned to the map's edge | border marker ignored |
| enemy-09 | 1.440 s | `red-border` at the map's lower edge from +0.000 s; the first red inside at +1.412 s | an enemy behind the figure, pinned to the lower edge | border marker ignored |
| enemy-13 | void | red beside the arrow from +0.000 s, read at once; before it, health 0.0 from −0.77 to −0.53 s, then 0.99 | the HUD fading in after a black screen with a full bar | false health fall before the onset |
| wanted-07 | void | stars from +0.000 s, read at once; before it, health falling 0.99, 0.93, 0.84 to 0.71 from −1.0 to −0.3 s, back to 0.99 at +1.6 s | the N icon sliding along a full bar | false health fall before the onset |
| wanted-03 | void | red at the player's arrow throughout the half second before | a fight already running; the scene does not start from calm (0.018 s) | real threat before the onset |

Counted: the reflex ignores a red marker on the map's edge in 3 scenes, a false health fall before the onset voids 2, and 1 is not a scene from calm. Of the reflex's 9 false notices, 7 are the same false falls: enemy-13 once and wanted-07 three times, and once each on calm-walk-13 (bright sand behind the translucent bar, 0.49 to 0.42), calm-walk-20 (the running-figure icon on the bar) and calm-walk-26 (the N icon on the bar, 0.79 to 0.69). The other 2 are wanted-03's real markers.

What would have to change, none of it done here. The minimap reader is right in all three border scenes: it returns the marker with its border flag. The rule that drops it is the reflex's own (`red and not blip.border` in `approaches.Reflex.step` and `stub_answer`), and `Fight` aims at the nearest red; the reflex should take a red border marker as a notice and turn towards its bearing, and aim only once a marker lies inside the map. The false falls come from the HUD reader: `hud._bars` reads health from the band's brightness and `_fraction` takes the first long dark stretch for the bar's end. It should return no health, not 0.0, while the track's colour is there but the whole band is dim (the HUD fading in), and it should not end the bar at a round icon or a white or black shape with bar colour on both sides of it, but read the empty track's tone beyond the icon instead. A bright background behind the translucent bar needs the surround correction to be measured beside the band rather than above and below it. The reflex's own fall test compares one frame with the last (a drop of 0.03) and keeps the last health across a black screen; forgetting the last health while the HUD is gone would have stopped enemy-13's false fall without touching a reader, but the icon cases hold for many frames and need the reader change.

## The modelled head

Codex had no quota, so the head ran in real time with its answer held back by a modelled delay: the readers' stub answers at once, and the head waits until 8.4685 s after the request before the conductor sees the plan. The source is the median of 20 Codex answers, request to response, in head.jsonl of /Users/kerim/recordings/pilot/20261110-223934, 20261110-230229, 20261110-231512 and 20261112-100713 (5.748 to 12.598 s, ninth decile 11.273 s). Every head row says `realtime, head delay modelled` and the model `codex-delay-modelled`, and carries the source. Even the fastest of the 20 answers is longer than the four seconds the bench waits for an answer, so the head answers no scene; what it notices comes from the conductor's events, which do not wait for it.

## The judge

The real judge at `http://192.168.0.248:1234` did not answer at the start of the work (`curl -s -m 4 http://192.168.0.248:1234/v1/models` timed out, exit 28; this Mac was on another network) and answered at the end, listing qwen/qwen3-vl-8b. Four probe answers through the bench's own request path came back at once (letter 0.58 s cold and 0.14 s warm, JSON 0.29 to 0.35 s). Then judge, judge-second and reflex+judge ran over all 55 scenes with each question, one scene at a time in real time, in the order judge letter, judge JSON, judge-second letter, judge-second JSON, reflex+judge letter, reflex+judge JSON: 13,194 model answers, none of them failed.

The fixed-answer question is built in the style of `judge.py`: the pilot judge's system prompt, its 640 px JPEG frame and its HTTP path, with the question "Is the player character in danger right now?" and the answers A no, B enemies, C police, D under fire; the reply is one letter in at most four tokens and maps to neutral, fight, flee or cover. Any other reply is a failure, logged and not guessed; there was none. `--question json` keeps P62's JSON question. The letter path is also tested against a local HTTP server of the test's own: the request carries the system prompt, the question, a 640 by 360 JPEG and `max_tokens` 4.

What the model said, answer by answer. "Named" counts the threat scenes in which an answer about a frame from the onset on is anything but A (or neutral), with the number of answers from the onset that took; on the six seconds before an onset (or the calm part of them, `calm_before_s`) and on calm scenes, every such answer is a false call.

| Run | Answers | Per answer median / p90 / worst ms | Threat named after the onset | Answers to name it, median | False calls, calm scenes | False calls, six seconds before onsets |
|---|---:|---|---|---:|---:|---:|
| judge, letter | 2,830 | 166 / 255 / 487 | 13 of 26 (12 of 20 enemies, 1 of 6 star onsets) | 11 | 0 of 1,413 | 14.9 % of 851 |
| judge, JSON | 1,595 | 312 / 417 / 763 | 15 of 26 (11 enemies, 4 star onsets) | 5 | 0 of 789 | 16.0 % of 470 |
| judge-second, letter | 2,825 | 168 / 258 / 464 | 13 of 26 (12, 1) | 12 | 0 of 1,403 | 15.2 % of 848 |
| judge-second, JSON | 1,571 | 321 / 417 / 751 | 12 of 26 (11, 1) | 1 | 0 of 777 | 15.0 % of 460 |
| reflex+judge, letter | 2,784 | 169 / 262 / 488 | 13 of 26 (11, 2) | 10 | 0 of 1,375 | 14.5 % of 848 |
| reflex+judge, JSON | 1,589 | 316 / 413 / 887 | 13 of 26 (11, 2) | 3 | 0 of 791 | 14.7 % of 469 |

The frame a request carries is 9 to 10 ms old when it is sent (median; ninth decile 50 to 70 ms), and the reply arrives 0.20 s after the frame's capture with the letter question and 0.34 to 0.35 s with the JSON one. The letter question halves the time per answer and asks almost twice as often, but it does not name more threats: what makes the judge slow as a way of control is not the answer's latency but that it calls a frame calm for seconds while the threat is on the map. When it names a threat, the letter judge says B (enemies) 9 times and D (under fire) 3 times for an enemy and C (police) once for a star onset; the JSON judge says fight for 10 enemies, flee for one and fight for all 4 star onsets it names. At 640 px the stars are hardly seen. A count of 1 answer to name the threat (judge-second, JSON) means the call began before the onset and went on after it.

The false calls before onsets are not spread evenly: most fall in a few scenes. Three seconds before enemy-04, 07, 08 and 03, all in one mission in recording 185323, armed allies crouch with shotguns, a body lies on the floor or the figure walks with a drawn gun; before enemy-12 and enemy-20 the screen is black (the HUD returns at the onset) and the letter judge answers D on a black frame. The bench's calm is calm on the minimap: a mission scene with drawn guns is not calm in the picture, so some of these calls are not wrong, but the black frames are. On calm scenes on foot, none of the 6,548 answers named a threat.

As ways of control (seconds from the onset; a void try is one where the judge already named a threat in the two seconds before):

| Way of control | Noticed: scenes, median / p90 / worst s, void | Answered: scenes, median / p90 / worst s, void, within 3 s | False answers before onsets / on calm scenes |
|---|---|---|---|
| judge, letter | 6, 2.640 / 3.106 / 3.271, 8 void | 6, 2.640 / 3.106 / 3.271, 8 void, 5 | 12 / 0 |
| judge, JSON | 7, 2.044 / 3.217 / 3.277, 11 void | 7, 2.044 / 3.217 / 3.277, 11 void, 4 | 15 / 0 |
| judge-second, letter | 6, 2.867 / 3.285 / 3.333, 8 void | 5, 2.334 / 3.528 / 3.542, 6 void, 3 | 6 / 0 |
| judge-second, JSON | 4, 1.428 / 3.097 / 3.375, 11 void | 5, 1.339 / 2.560 / 2.705, 6 void, 5 | 7 / 0 |
| reflex+judge, letter | 15, 0.013 / 1.128 / 1.436, 11 void | 12, 0.013 / 2.921 / 3.576, 7 void, 11 | 10 / 0 |
| reflex+judge, JSON | 16, 0.025 / 1.421 / 1.812, 10 void | 13, 0.539 / 3.330 / 3.714, 8 void, 10 | 11 / 0 |

A judge notices when an answer names a threat, so for the judge noticed and answered fall on the same tick; judge-second notices at the first naming answer and answers at the second agreeing one, which halves its false answers before onsets and delays its answers. reflex+judge notices through the reflex, but the judge's calls before the onsets void 10 or 11 of its notices, and it answers fewer scenes within three seconds than the reflex alone (11 and 10 against 14). In this bench the judge makes the reflex worse, not better.

Per threat scene, seconds from the onset, "noticed / answered" where the two differ:

| Scene | judge, letter | judge, JSON | judge-second, letter | judge-second, JSON | reflex+judge, letter | reflex+judge, JSON |
|---|---:|---:|---:|---:|---:|---:|
| enemy-01 | 2.438 | void | 2.868 / none | void / 0.973 | 0.058 / none | void |
| enemy-02 | none | none | none | none | 0.076 / none | 0.109 / none |
| enemy-03 | void | void | void | void | void | void |
| wanted-02 | none | void | none | void | 0.010 | 0.006 |
| wanted-03 | none | void | none | void | void / 0.809 | void |
| enemy-04 | void | void | void | void | void | void |
| enemy-05 | 2.036 | 1.875 | 2.144 / 2.334 | 2.447 / 2.705 | 1.404 / 1.803 | 1.406 / 1.713 |
| enemy-06 | void | void | void / 3.509 | void / none | void | 1.812 / 2.747 |
| enemy-07 | void | void | void | void | void | void |
| enemy-08 | void | void | void | void | void | void |
| enemy-09 | none | void | none | void / none | 1.436 / none | 1.436 / none |
| enemy-10 | 3.271 | 3.277 | 3.333 / 3.542 | 0.277 / 0.511 | 0.004 / 3.576 | 0.011 / 0.539 |
| enemy-11 | none | none | none | none | 0.005 / none | 0.013 / none |
| enemy-12 | 2.842 | none | none | none | 0.007 | 0.002 |
| enemy-13 | none | none | none | none | void / none | void / none |
| enemy-14 | void | none | void | none | void | 0.004 / 1.672 |
| enemy-15 | none | 3.068 | 2.867 / none | none | 0.713 / 2.708 | 0.713 / 3.370 |
| enemy-16 | none | none | none | none | 0.702 / none | 0.709 / none |
| enemy-17 | void | void | void | void / 2.343 | void | 0.010 |
| enemy-18 | 0.944 | 1.734 | 1.280 / 1.540 | 0.409 / 1.339 | 0.008 | 0.046 |
| enemy-19 | 2.940 | 3.178 | 3.236 / none | 3.375 / none | 0.041 / 2.945 | 0.038 / 3.170 |
| enemy-20 | none | none | none | none | 0.012 / none | 0.013 / 3.714 |
| wanted-04 | none | none | none | none | 0.013 | void |
| wanted-05 | none | 2.044 | none | none | 0.003 | 0.004 |
| wanted-06 | void | 1.734 | void / 0.444 | none | void / 0.014 | void / 0.005 |
| wanted-07 | none | void | none | void / none | void / 0.012 | void |

Room in lab/reaction. Six runs at this answer rate would not fit under 5 MB beside the rest, so three things were done, and the rows say so in `model_answers_slimmed`. P62's ledger rows (the whole committed ledger, 1,067,083 bytes, of scene sets the board no longer shows) moved byte for byte into `ledger-p62.jsonl.gz` beside the ledger (133,750 bytes; `gunzip -c ledger-p62.jsonl.gz` gives them back). Each run first wrote its full rows to a scratch ledger, and only slimmed rows were appended to the lab ledger: without transitions, which the board does not read; the judge rows with each answer's capture time, duration, action and any error (the letter follows from the action); the judge-second and reflex+judge rows with a `model_answer_summary` instead of the answer list, since they ask the same model with the same question and request loop. Their per-answer numbers in the tables above come from the full scratch rows, which were deleted afterwards; the board's model table therefore holds the two judge rows only.

The commands that run the judge step again, from pilot; they write full rows into the lab ledger, so make room first:

```sh
curl -s -m 4 http://192.168.0.248:1234/v1/models
env -u PS5_HOST .venv/bin/python tools/reaction.py run judge judge-second reflex+judge --question letter --endpoint http://192.168.0.248:1234 --model qwen/qwen3-vl-8b
env -u PS5_HOST .venv/bin/python tools/reaction.py run judge judge-second reflex+judge --question json --endpoint http://192.168.0.248:1234 --model qwen/qwen3-vl-8b
env -u PS5_HOST .venv/bin/python tools/reaction.py board
```

Each way of control replays 9.2 minutes of scenes; a run over all 55 took about twelve minutes.

## The policy

NitroGen ran last, through P63's server on the gaming PC (`lab/policy/serve.ps1`, reached over the forwarded port at `http://[::1]:18763`), with the judge loaded beside it and nothing asking either. The bench sends the whole frame, takes the first pad of each chunk and holds it until the next answer; it does not play the chunk's eighteen steps. 2,328 answers, none of them failed, took a median of 217 ms from request to reply (ninth decile 277 ms, worst 390 ms), and the pad it holds comes from a frame that is 0.35 s old at the median.

As a way of control it does not react, it presses. An input from the answer sets is on its pad on 19 % of the ticks of the calm scenes (1,662 of 8,700), in 157 episodes on all 29 of them, and in the two seconds before 22 of the 26 onsets, which voids those tries. The four tries left give an answer after 0.135, 0.546, 0.701 and 1.711 s (median 0.623 s): a sprint forward in three and R2 in one, the same inputs it presses when nothing threatens. A policy says nothing about what it saw, so it has no noticed time. This is the model as it comes, which P63 already found not to steer or aim with Kerim; the row says the same from the side of reactions and says nothing about a policy trained on this game.

The reviewer ran this row after the worker's hand-back, with the same implementation and scene file. Its rows are in the ledger with a summary instead of the answer list, like judge-second's. The first three scenes were replayed a second time, because the scratch file that held their rows was removed while the run was going; every row is from one whole replay of its scene. To run it again, from pilot, with the server started by `lab/policy/pc.sh -L 18790 lab/policy/serve.ps1`:

```sh
env -u PS5_HOST .venv/bin/python tools/reaction.py run policy --endpoint http://127.0.0.1:18790 --model nitrogen
```

## The board

The [board](../../lab/reaction/board.md) ([HTML](../../lab/reaction/board.html)) shows rows of implementation SHA-256 `7f28da3db54e8dfc56b57906b7d3e873c847f4e918eb46ed9d18d68fb8006d34` and scenes SHA-256 `7b083561b41e90c4e3d9820f4fc7a070fae3322283c42a0b8e709e24eb2e642d`. Its tables, copied:

| Approach | Mode | Threat/calm trials | Noticed ≤3s | Noticed median / p90 / worst ms | Answered ≤3s | Answered median / p90 / worst ms | Answered with link ms | False notices | False answers | Calm / scene / min | Decision ms | Hz |
|---|---|---:|---:|---|---:|---|---|---:|---:|---|---:|---:|
| Kerim | recorded-human-default | 8/9 | n/a | n/a | 50.0% | 682.2 / 2775.5 / 3651.5 | 817.2 / 2910.5 / 3786.5 | n/a | 98 | 10.6 / 71.2 | n/a | n/a |
| Kerim, looser reading: first new press after the onset | recorded-human-default | 8/9 | n/a | n/a | 62.5% | 2200.9 / 3827.2 / 3996.0 | 2335.9 / 3962.2 / 4131.0 | n/a | 98 | 10.6 / 71.2 | n/a | n/a |
| Kerim | recorded-human-estimated | 18/20 | n/a | n/a | 38.9% | 973.9 / 2106.6 / 2115.7 | 1108.9 / 2241.6 / 2250.7 | n/a | 98 | 3.9 / 25.7 | n/a | n/a |
| Kerim, looser reading: first new press after the onset | recorded-human-estimated | 18/20 | n/a | n/a | 83.3% | 1132.3 / 2109.7 / 2149.7 | 1267.3 / 2244.7 / 2284.7 | n/a | 98 | 3.9 / 25.7 | n/a | n/a |
| head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 26/29 | 26.9% | 539.9 / 2784.4 / 3475.3 | 0.0% | n/a / n/a / n/a | n/a / n/a / n/a | 0 | 0 | 0.0 / 0.0 | 12.9 | 30.0 |
| judge (qwen/qwen3-vl-8b, json question) | realtime | 26/29 | 15.4% | 2044.2 / 3217.5 / 3277.2 | 15.4% | 2044.2 / 3217.5 / 3277.2 | 2179.2 / 3352.5 / 3412.2 | 15 | 15 | 0.0 / 0.0 | 516.2 | 30.0 |
| judge (qwen/qwen3-vl-8b, letter question) | realtime | 26/29 | 19.2% | 2639.9 / 3105.5 / 3271.1 | 19.2% | 2639.9 / 3105.5 / 3271.1 | 2774.9 / 3240.5 / 3406.1 | 12 | 12 | 0.0 / 0.0 | 298.8 | 30.0 |
| judge-second (qwen/qwen3-vl-8b, json question) | realtime | 26/29 | 11.5% | 1427.8 / 3096.7 / 3375.3 | 19.2% | 1339.1 / 2560.4 / 2705.0 | 1474.1 / 2695.4 / 2840.0 | 15 | 7 | 0.0 / 0.0 | 531.9 | 30.0 |
| judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 26/29 | 15.4% | 2867.2 / 3285.0 / 3333.5 | 11.5% | 2334.3 / 3528.4 / 3541.5 | 2469.3 / 3663.4 / 3676.5 | 13 | 6 | 0.0 / 0.0 | 298.0 | 30.0 |
| pilot | realtime | 26/29 | 34.6% | 14.3 / 815.3 / 1900.2 | 30.8% | 75.4 / 689.1 / 1971.3 | 210.4 / 824.1 / 2106.3 | 2 | 19 | 0.0 / 0.0 | 14.0 | 29.9 |
| policy (nitrogen) | realtime | 26/29 | n/a | n/a | 15.4% | 623.3 / 1408.2 / 1711.3 | 758.3 / 1543.2 / 1846.3 | n/a | 200 | 5.4 / 32.5 | 348.4 | 30.0 |
| reflex | realtime | 26/29 | 88.5% | 36.5 / 1265.6 / 1671.0 | 53.8% | 422.8 / 3072.0 / 3904.2 | 557.8 / 3207.0 / 4039.2 | 9 | 0 | 0.0 / 0.0 | 13.1 | 30.0 |
| reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 26/29 | 61.5% | 25.4 / 1421.1 / 1812.4 | 38.5% | 538.5 / 3330.3 / 3714.1 | 673.5 / 3465.3 / 3849.1 | 20 | 11 | 0.0 / 0.0 | 514.9 | 30.0 |
| reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 26/29 | 57.7% | 12.6 / 1127.5 / 1436.2 | 42.3% | 13.4 / 2921.2 / 3576.1 | 148.4 / 3056.2 / 3711.1 | 20 | 10 | 0.0 / 0.0 | 297.7 | 30.0 |

| Approach | Mode | Answers (errors) | Per answer median / p90 / worst ms | Threat named | Answers to name it | False calls calm | False calls before onset |
|---|---|---:|---|---:|---:|---:|---:|
| judge (qwen/qwen3-vl-8b, json question) | realtime | 1595 (0) | 311.6 / 417.1 / 763.2 | 57.7% | 5.0 | 0.0% of 789 | 16.0% of 470 |
| judge (qwen/qwen3-vl-8b, letter question) | realtime | 2830 (0) | 166.4 / 254.9 / 487.3 | 50.0% | 11.0 | 0.0% of 1413 | 14.9% of 851 |

Kerim's rows are split by how his hand was put on the picture clock (an estimated lead, or the labeller's default of 0.2 s), as in P62; together they are the 12 strict and 23 loose answers above. Both of his groups happen to have 98 false answers: 172 on calm scenes, on 10 of the 29, every one a sprint forward, which the answer set cannot tell from "sprint away"; and 24 in the two seconds before onsets, in 11 scenes, of which the 21 that begin inside those two seconds are 11 sprints, 5 aims, 3 shots and 2 cover presses. The pilot's 19 are all its low-health flight before three onsets: in enemy-04 and enemy-05 the health really is low before the enemy shows, in enemy-13 the reader took the fading-in bar for an empty one. The false notices of reflex+judge are the reflex's 9 plus the judge's calls before onsets. The ways of control ran in the order reflex, pilot, head, then the six judge runs and the policy last, one scene at a time, with no errors. board.png and timeline.png in lab/reaction are still P62's pictures; the board itself was not rendered again.

## Scenes that start from calm

The set now holds 55 scenes: 26 threats on foot (20 enemies, 6 star onsets) and 29 calm scenes on foot, against the target of thirty and thirty. Of P62's twelve, eight stay (enemy-01 to 03, wanted-02 and 03, calm-walk-01 to 03); new are enemy-04 to 20, wanted-04 to 07 and calm-walk-04 to 29. 24 of the 26 threats start from at least six seconds in which the readers see no red marker and no stars (`calm_before_s` in `scenes.json`); wanted-06 has 2.509 s by the readers (a false red from a brick wall behind the map, the figure leaving a truck), and P62's wanted-03 is in the middle of a fight (0.018 s).

How they were found. The 109 fight beginnings in 22 labelled recordings (`actions.jsonl`: the first aim, fire or melee after ten seconds without one) are the starting point, but almost every one begins with red already on the map: only 4 of them have a threat reading after six calm seconds within the five seconds before Kerim engages. So the onsets were searched as the first red marker or lit star on foot after a calm stretch, where calm may run through a cutscene or a black screen and is broken by red, stars or a vehicle map. Each 10 Hz label proposal was refined on native frames with the readers (the first frame from which the reading holds on two of the next three, with the two before it clear), and then the minimap or the stars of the frames −2, −1, 0 and +1 were looked at, magnified 2.4 times. Six onsets were moved one frame earlier to where the marker is first visible (enemy-04, 06, 08, 18, 19 and 20). Every kept onset has an uncertainty of one frame; four lie inside a capture batch of frames a millisecond apart, which the notes name. Onsets were preferred where Kerim held no answering input for two seconds; that leaves 13 of 26 void under the strict reading, because he sprints a lot when nothing threatens (below).

What was rejected, by cause: red already under the player arrow before the reader saw it, 5; no red marker at all, the reader taking red behind the transparent map (flowers, bricks, red map areas, a red character) for one, 12; a marker already visible two frames earlier on a dimmed map, 3; grey stars already shown, 2. The calm windows come from the labels (a flat minimap on 98 % of samples, no red, no stars, no health fall, the game screen, no aim, fire or melee within 15 s); 35 were looked at and 26 kept. Rejected were 9 where the figure is not in view (idle scenery camera, a first-person view), 2 where it may sit in a parked car, and 2 where it swims.

Health falls. No health fall that starts from calm was confirmed, and P62's three hit scenes were false onsets. For every proposal I measured the right end of the bar's light-green part per frame, skipping icon pixels, from one second before to 1.5 s after: in hit-01 it stays at column 120 throughout (the reader's fall is the N icon sliding over the bar's end, at a camera cut), in hit-02 the bar reads 0.8 before and half a second after, in hit-03 it stays full against a bright sand background. Of 61 label proposals for a fall on foot after six calm seconds, 41 got a native onset; none shows a lasting fall that can be told within two frames: the bar keeps its length while a map icon (N, a race flag, a question mark, a car, a target) passes over its end, or the frames are damaged, or an icon covers the end so that a fall cannot be seen. P62's wanted-01 is in a vehicle. These four left the set.

Vehicles. The labels hold 162 threat onsets in a vehicle after at least two calm seconds (152 red, 10 stars; 121 after six seconds) in 29 recordings. None was looked at; on foot about one proposal in five survived the look, so a vehicle set of about thirty is an estimate. They wait for an answer set of their own. `selection.vehicles` in `scenes.json` stayed empty: the counts are here, because changing the scene file after the runs would have orphaned every row.

What footage would give more: Kerim on foot meeting enemies outside a mission cutscene, a police chase begun on foot, and being shot at from calm, recorded over the cable so that the stars and the health bar are clean, and with his hands off the sticks for a moment before. The recordings so far are mostly driving and missions whose enemies are already on the map when the HUD returns.

## Kerim's reference, under both readings

Strict reading (P62's rule: his first answering pad after the onset, void when an answering input was held in the two seconds before): 12 of the 26 threat scenes give a time, 13 are void and one (enemy-08) has no answering input within the four seconds after the onset. Median 0.879 s, ninth decile 2.114 s, worst 3.651 s (times from the onset, without the link). The void share fell from eight of nine to 13 of 26 because the new scenes start from calm, but it is still half: the answer set counts sprinting forward ("sprint away", Cross with the left stick forward) as an answer, and Kerim sprints a lot when nothing threatens.

Looser reading (his first answering input newly pressed after the onset, even while another is held; it says when his hand changed, not that the change answered the threat): 23 of 26 scenes, median 1.261 s, ninth decile 3.509 s, worst 3.996 s. The three without one are enemy-01, enemy-08 and wanted-04.

His hand is brought onto the picture clock with each recording's lead from `labels.json`; for 18 of the 26 threat scenes it is estimated (0.16 to 0.18 s), for the other 8 it is the labeller's default of 0.2 s, because no estimate was made for those recordings. The error of the default is unknown and can be a tenth of a second or more.

## What changed and how it was checked

`reaction.py` gained the notice time, Kerim's looser reading, the per-answer model statistics, the two-time board and smaller ledger rows (a slim scene snapshot, transitions from 2.5 s before the onset, numbers rounded to 0.1 ms); `approaches.py` the notices of every way of control, the letter question, the answer log and the modelled head delay; `tools/reaction.py` the `--question`, `--head-delay`, `--head-delay-source` and `--only` options, the `misses` command, `board --implementation` and smaller contact sheets. The P62 scene file is replaced by the widened one, and P62's ledger rows moved into `ledger-p62.jsonl.gz`. lab/reaction holds 4,941,795 bytes in 78 files. No reader, conductor, skill or judge module was changed, no git write was made, and nothing under /Users/kerim/recordings was written.

From pilot, `env -u PS5_HOST .venv/bin/python -m pytest tests/test_reaction.py -q` passes 21 tests in 2.57 s, eight of them new: the two times, a notice before the onset voiding and counting as false, the board showing both times, the second-answer judge noticing at its first answer and answering at its second, the letter parsing, the letter question going out as the pilot judge asks it, Kerim's looser reading and the model answer statistics. `ruff check` and `ruff format --check` pass on the four files.
