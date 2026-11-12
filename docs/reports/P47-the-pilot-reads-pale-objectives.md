P47 puts pale objective recognition in `pilot.scene`, where the running pilot already reads its objectives. `tools/texts.py` now uses `TextReader.read()` directly. The notes module no longer contains a second instruction or colour classifier. The shared decision accepts the recorded pale cyan and yellow targets and preserves the old saturated colour thresholds and exact instructions, including short and long instructions.

An arbitrary one-character verb correction was unsafe. During replay, frame 52238 at 872.5034 seconds in `20261111-183820` contained dialogue visibly saying “Geschäfte, Nigga.”, but OCR produced `hafte, Nlgg`. Treating that as a misspelling of `halte` promoted dialogue to an objective. The final reader permits only one `i/l` or `b/8` glyph confusion in a sufficiently long instruction. This retains recorded `Beglb`, `Stelg` and `8egib` objectives and rejects that dialogue. Exact listed verbs still need a coloured target inside their own OCR box. This remains a bounded German/English heuristic, not a guarantee for every unseen conversation.

The offline comparison covers 17,739 stored OCR readings and 10,849 stored bottom-text lines in the eleven P39 recording outputs in `lab/notes/out`, their stored OCR text and boxes, and frames decoded from `/Users/kerim/recordings/kerim`. Those outputs contain 37 known objective steps. The derived directory does not contain complete raw readings for all eleven recordings, so the complete P39 outputs are used consistently. The old pilot decision is loaded from commit `926a473` and compared with the new shared decision on the same pixels. Stored labels already include P39's offline repair and are not mistaken for the old pilot's labels. Each known objective is matched within its displayed `start` to `last` interval with 0.6 seconds of sampling tolerance and a normalized text similarity of at least 0.8. The saved evidence includes the actual matching time, frame and score for every step.

`lab/notes/p47/replay.py` records every changed label, grouped by exact text and transition, with counts and first/last frame and time. It also records disagreements with stored P39 labels and objective decisions for candidate bottom text in labelled cutscene intervals. Stored subtitle promotions are candidates for manual review, not independent dialogue ground truth. Section labels come from `/Users/kerim/recordings/derived/kerim/<recording>/sections.json` when present, otherwise from `lab/notes/sections/<recording>/sections.json`; each evidence file records the path used. These selected sections yield 12 cutscene readings with candidate bottom text: two in `20261111-164039`, five in `20261111-190825` and five in `20261111-192328`. None is classified as an objective. Readings without bottom text need no objective decision and are omitted from that count. Dialogue elsewhere is checked by manual inspection of changed labels and the explicit regression above, not by a complete independently labelled dialogue corpus. No separate scene classification corpus with source boxes and pixels exists in the checkout; the saved `lab/mission` cases contain downstream scene fields and cannot establish changed OCR labels. The replay output is the reproducible recorded-label comparison, and the scene tests cover synthetic colour and wording regressions.

The final replay finds 37 of 37 known objective steps; the original pilot finds 14. Counts below refer to objective steps, not unique text strings.

`20261111-164039`: 8/8 found after the change, versus 5/8 before it.

`20261111-165543`: 6/6 found after the change, versus 0/6 before it.

`20261111-171046`: 5/5 found after the change, versus 1/5 before it.

`20261111-172549`: 3/3 found after the change, versus 2/3 before it.

`20261111-175312`: 0/0 found after the change, versus 0/0 before it.

`20261111-180814`: 3/3 found after the change, versus 1/3 before it.

`20261111-182316`: 1/1 found after the change, versus 1/1 before it.

`20261111-183820`: 1/1 found after the change, versus 1/1 before it.

`20261111-185323`: 3/3 found after the change, versus 1/3 before it.

`20261111-190825`: 7/7 found after the change, versus 2/7 before it.

`20261111-192328`: 0/0 found after the change, versus 0/0 before it.

Compared with the original pilot, 206 line labels change in 76 recording/text groups, all detailed in `lab/notes/p47/20261111-*.json`. There are 0 objective-to-subtitle changes. The final output has 0 newly promoted stored subtitle readings and 0 positive objective readings in the labelled cutscene. There are 0 line-level disagreements with the repaired P39 labels. Manual inspection of all 76 changed text forms found mission instructions and no dialogue. The fixed `hafte` case is absent from the final promotions. These comparisons do not substitute for independent dialogue ground truth.

For recording `20261111-165543` at 72.8317 seconds (frame 4308), classifier median/p95 changed from 0.000334/0.000375 ms to 0.002208/0.002333 ms. The median increment is 0.001874 ms.

For recording `20261111-165543` at 221.0052 seconds (frame 13193), classifier median/p95 changed from 0.000459/0.001377 ms to 0.075042/0.165965 ms. The median increment is 0.074583 ms.

For recording `20261111-165543` at 373.0324 seconds (frame 22288), classifier median/p95 changed from 0.043625/0.094008 ms to 0.076541/0.165252 ms. The median increment is 0.032917 ms.

For recording `20261111-165543` at 418.0083 seconds (frame 24987), classifier median/p95 changed from 0.000458/0.000625 ms to 0.082041/0.092642 ms. The median increment is 0.081583 ms.

The benchmark measures only classification of the bottom lines in each stored reading. Video decoding, OCR and other reader work are excluded, so no fresh end-to-end reader latency is claimed.

The focused command is `cd pilot && env -u PS5_HOST .venv/bin/python -m pytest tests/test_scene.py tests/test_notes.py -q`. It passes 128 tests and skips one native Vision test. The skip is explicit: `Vision runtime unavailable in this sandbox: Vision text recognition failed: None`. Fresh native OCR could therefore not be verified here. Stored OCR replay validates classification and its incremental cost; it does not measure fresh full-reader OCR latency or prove live console behavior.

The final `cd pilot && env -u PS5_HOST .venv/bin/python tools/gate.py --full` completed on the final code. Ruff check and format check passed for all 117 files. Pytest finished in 758.98 seconds with `5 failed, 2964 passed, 3 skipped, 236 xfailed, 5 errors`; the command returned exit 1. The only failures and errors are the sandbox exceptions allowed by the task card; the full gate is not claimed to have exited successfully. `git diff --check` also passed.

The five failures are `tests/test_commentator.py::test_twitch_local_irc_handshake_ping_fragmented_chat_and_filter` and `tests/test_overlay.py::test_http_growing_log_updates_within_one_second_and_reconnects`, `test_partial_malformed_and_replaced_logs_remain_usable`, `test_missing_root_new_session_and_idle_end`, and `test_local_assets_served_without_external_dependencies`. Each fails while binding a local test socket with `PermissionError: [Errno 1] Operation not permitted` at `socketserver.py:478`.

The five errors are in `tests/test_objects.py`: `test_real_traffic_and_player_exclusion`, `test_bad_frames_are_rejected[None]`, `test_bad_frames_are_rejected[bad1]`, `test_bad_frames_are_rejected[bad2]`, and `test_reports_below_the_confidence_floor_are_left_out`. All fail during fixture setup at `src/pilot/objects.py:75`, when ONNX Runtime constructs the CoreML inference session: `Error compiling model: Failed to create a working directory appropriate for URL: file:///var/folders/n1/_jxqq5494mg9m33y1c3xvkx00000gn/T/`. No other failing test or error remains. Native Vision OCR and these sandbox-blocked socket/CoreML checks still require the unrestricted commands below.

Reproduce the stored-reading comparison from the repository root with `cd pilot && env -u PS5_HOST .venv/bin/python ../lab/notes/p47/replay.py`. The isolated benchmark alternates the old and new classifiers over four real readings, discards 20 warmups and measures 500 iterations per reading, excluding video decoding and OCR.

Outside this sandbox, repeat the complete gate with `cd pilot && env -u PS5_HOST .venv/bin/python tools/gate.py --full`. Fresh OCR for the same eleven recordings can be run with `cd pilot && env -u PS5_HOST .venv/bin/python tools/texts.py /Users/kerim/recordings/kerim/20261111-164039 /Users/kerim/recordings/kerim/20261111-165543 /Users/kerim/recordings/kerim/20261111-171046 /Users/kerim/recordings/kerim/20261111-172549 /Users/kerim/recordings/kerim/20261111-175312 /Users/kerim/recordings/kerim/20261111-180814 /Users/kerim/recordings/kerim/20261111-182316 /Users/kerim/recordings/kerim/20261111-183820 /Users/kerim/recordings/kerim/20261111-185323 /Users/kerim/recordings/kerim/20261111-190825 /Users/kerim/recordings/kerim/20261111-192328 --out ../lab/notes/p47/native --level fast`.

Only the card's reader, notes cleanup, extraction tool, associated tests, notes evidence and this report were changed. Recordings and their derived source files were not modified. No daemon, console or network service was contacted. The existing task branch is retained. `docs/tasks/README.md` says: “Git cannot write here: no commit, stash, checkout or reset. Leave your changes in the working tree; the reviewer commits them.” That explicit worker instruction is followed instead of creating a commit or pull request. The reviewer must commit and integrate these changes.

## Review

Read and run outside the sandbox on 12 November. The tests of the reader and the notes pass with the native text recognition, 129 of them, the one the sandbox skipped included. `20261111-165543`, the recording in which the pilot's reader had found none of six objectives, was read afresh with `tools/texts.py` through the changed reader alone: its 275 lines are the same as those of the stored evaluation, kind, text and times, with all six objectives. The full gate passes on this branch merged with P46 and P48: 3035 tests, one skipped, 236 expected failures. The sandbox's gate output is not kept.
