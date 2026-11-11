## Second round

P35 now recognises the Pacific Bluffs map movement that caused the 13:35 failure, approaches visible land when that movement leaves the cursor over sea, and recognises the cinematic gameplay HUD after the map closes. Native map, OCR, HUD and minimap readers were run on actual captured frames from both `20261111-133505` and `20261111-132729`. The evidence is `lab/waypoint/p35-second-round.json`; its 34 unannotated PNGs are retained under `pilot/tests/fixtures/waypoint/live/`, with exact native OCR results in that folder's `second-round.json` manifest and the lab evidence file. The two source recordings were not modified.

The exact first command/settled pair in 133505 is frame 41468 to 41563. Only 113 of 250 corner tracks pass forward/backward verification, below the 65% requirement, so the numeric shift is refused despite visibly translated streets. The next two pairs have only 3/213 and 2/165 valid tracks. The first-round fallback also fails on the third pair: its whole-scene gradient responses are 0.277 and 0.289, below 0.45, and its fixed upper strip contains only 30 changed road pixels. Most of that strip is the paused cinematic car scene or sea, not map. The westward second push in 132729 similarly has zero changed road pixels in that upper strip even though the visible road network moves about 59 pixels.

The corrected fallback correlates only bright neutral road pixels in both existing windows, requires agreement within two pixels and response at least 0.4, and requires at least 100 changed road pixels spread across 100 pixels horizontally and 80 vertically. It still refuses random damage, a stationary map, unsupported texture and incoherent motion. All 14 exact second-round push pairs pass the movement test. Their correlation offsets below are diagnostic coherence measurements, never credited as exact travel distance or a new stick polarity. Supported corner shifts remain subject to the original geometric checks. Near/far unmeasured travel remains 0.8/2.0 seconds of successful commanded holds.

The recording actually contains three northward hold groups in the 13:35 attempt, beginning at 5.048, 6.663 and 8.672 seconds and released at 5.371, 7.352 and 9.375. The third settled frame has the cursor over sea, so simply admitting the motion must not issue Cross. When sufficient observed travel ends there, the skill chooses a visible land patch with a unique local template and uses the existing bounded aiming and progress checks to bring it under the cursor. Cross requires a fresh land check at that final cursor, no existing waypoint, and an interactive map. A failed or ambiguous land target backs out; the existing 16-move and 45-second limits still apply. If no unique patch is available, the original single reverse look remains bounded. The original decision sequence through frame 41805 now reaches this inland aim without Cross or a shift failure; it does not pretend that the old recording contains the consequence of the new aiming input.

The map visit table compares actual reader results with the visible map. Every listed frame is an interactive map with cursor `(640, 360)`, no uniquely readable player marker, no waypoint under the cursor and no waypoint/route proof. The visible legend and centre crosshair are present throughout. The S badge moves out of the reader's map region in the rows marked absent; the underlying car changes camera angle between visits. Land means supported local map detail, so `false` also covers an unsupported sparse coastal area rather than proving ocean geographically.

| Visit | First / last captured frame | S badge at start / end | Land at start / end | Visible comparison |
|---|---|---|---|---|
| 133505 north | 133505-41468 / 133505-41805 | [[940.0, 465.0]] / absent | True / False | Cursor leaves the supported road/land patch; no Cross is justified |
| 132729 north 1 | 132729-14356 / 132729-14566 | [[940.0, 465.0]] / [[940.0, 546.0]] | True / False | Cursor leaves the supported road/land patch; no Cross is justified |
| 132729 east | 132729-14961 / 132729-15164 | [[940.0, 465.0]] / [[863.0, 465.0]] | True / True | Roads remain under the cursor |
| 132729 south | 132729-15555 / 132729-15877 | [[940.0, 465.0]] / [[940.0, 315.0]] | True / False | Cursor leaves the supported road/land patch; no Cross is justified |
| 132729 west | 132729-16269 / 132729-16474 | [[940.0, 465.0]] / absent | True / False | Cursor leaves the supported road/land patch; no Cross is justified |
| 132729 north 2 | 132729-16876 / 132729-17087 | [[940.0, 465.0]] / [[940.0, 539.0]] | True / False | Cursor leaves the supported road/land patch; no Cross is justified |

The push table uses each real command frame and the first settled decision frame. Full frame times, OCR lines and reader fields for both ends are in the JSON. All five earlier map visits are represented, including north, east, south and west. The numeric tracker is unchanged; the last column is the new observed-motion fallback.

| Command / settled frame | Valid tracks | Old numeric shift (px) | New road phase (px, not distance) |
|---|---:|---|---|
| 133505-41468 / 133505-41563 | 113/250 (45.2%) | refused | (0.00, 21.80) |
| 133505-41565 / 133505-41683 | 3/213 (1.4%) | refused | (-0.00, 77.92) |
| 133505-41685 / 133505-41805 | 2/165 (1.2%) | refused | (0.07, 81.11) |
| 132729-14356 / 132729-14455 | 219/250 (87.6%) | (-0.00, 18.69) | (0.01, 18.72) |
| 132729-14457 / 132729-14566 | 94/250 (37.6%) | refused | (-0.03, 62.36) |
| 132729-14961 / 132729-15056 | 199/250 (79.6%) | (-22.29, 0.01) | (-22.27, 0.02) |
| 132729-15058 / 132729-15164 | 144/250 (57.6%) | refused | (-54.02, -0.03) |
| 132729-15555 / 132729-15650 | 226/250 (90.4%) | (0.00, -19.06) | (0.02, -19.01) |
| 132729-15652 / 132729-15760 | 166/250 (66.4%) | (0.00, -63.51) | (-0.02, -63.52) |
| 132729-15762 / 132729-15877 | 149/250 (59.6%) | refused | (0.02, -66.75) |
| 132729-16269 / 132729-16365 | 240/250 (96.0%) | (18.69, 0.00) | (18.74, 0.05) |
| 132729-16367 / 132729-16474 | 162/250 (64.8%) | refused | (59.17, 0.02) |
| 132729-16876 / 132729-16978 | 207/250 (82.8%) | (0.00, 21.76) | (0.01, 21.82) |
| 132729-16980 / 132729-17087 | 124/250 (49.6%) | refused | (-0.02, 53.07) |

After the exits, the car and all three status bars are visible. The minimap corruption result is a false negative for whole-screen gameplay: a cinematic angle changes minimap geometry while the actual health, armour and special bars remain readable. The old `_game` predicate required a clean high-confidence minimap and therefore sent an unnecessary third Circle. The fresh HUD fallback now applies only at opening/exit, rereads the current frame's bars rather than trusting older HUD values, requires at least two readable bars and a game screen, and waits at least 0.15 seconds. `screen="game"` alone is insufficient because it is the HUD reader's default. Missing, changed-to-pause, damaged-anchor and unchanged-command pictures cannot authorise Options or success. Existing failures stay failures, and returning to gameplay without map proof never becomes `done`.

| Captured gameplay frame | Minimap / corrupt / confidence | Health / armour / special | New decision |
|---|---|---|---|
| 133505-42111 | tilted / True / 0.35 | 0.489 / 0.000 / 1.000 | Observe gameplay after persistence; no extra Circle |
| 133505-42193 | tilted / True / 0.35 | 0.489 / 0.000 / 1.000 | Observe gameplay after persistence; no extra Circle |
| 132729-17393 | tilted / True / 0.35 | 0.500 / 0.000 / 1.000 | Observe gameplay after persistence; no extra Circle |
| 132729-17478 | tilted / True / 0.35 | 0.500 / 0.000 / 1.000 | Observe gameplay after persistence; no extra Circle |

The cinematic unit tests deliberately hold a real image for the persistence interval; they prove the temporal rule, not independent captures. The additional captured exit frames above establish the same reader result at different real times. The input-safety review checked the final diff, including the inland move cap and learned reverse pan polarity, and found no remaining blocking input-safety issue.

| Offline execution | Observed ending and presses |
|---|---|
| 133505 input-matched replay | Neutral divergence at 2.132 s, frame 41293: the newly decoded cinematic image requires HUD persistence, while the old run immediately sent Options using its earlier minimap reading. No counterfactual live outcome is claimed. |
| 132729 input-matched replay | Options, Cross to enter, two north pushes match the recorded prefix. At 9.255 s, frame 14568, the new skill requests another checked north push while the old run is neutral before aborting. Replay stops neutral there. |
| 133505 real-map decision sequence | Frames 41468, 41565, 41685, 41805 enter observed-only travel, then aim toward a uniquely visible land patch. No map-setting Cross occurs over sea. This is a decision regression, not an input-matched continuation. |
| Live-zoom coastal model, near | At delays 0.14/0.6/1.1 s: done at 22.70 s, nine pan/aim holds, one Options, one entry Cross, one map-setting Cross, map route proof, two Circle exits and neutral pad. |
| Live-zoom coastal model, far | At delays 0.14/0.6/1.1 s: done at 27.80 s, twelve pan/aim holds, the same verified button sequence and neutral terminal pad. |

The coastal model deliberately injects numeric-shift refusal while retaining real road-motion reading; its map is procedural and its gameplay return uses the actual 133505 cinematic frame. The real 14-pair tests separately establish that this refusal and the replacement motion evidence occur in the recordings. This separation avoids presenting synthetic road layout or a generated route as live proof. Existing mission and away simulations still run at both zooms. The three harmful-input guards below remain covered, with added checks that Cross is absent on the coastal sea picture and that a stale/default game HUD cannot authorise input.

Validation: `env -u PS5_HOST .venv/bin/python tools/gate.py --full` passed on the final production and test changes: `2780 passed, 1 skipped, 236 xfailed in 704.86s (0:11:44)` and `gate passed in 705.15s (full)`. Ruff check and format passed. The complete waypoint suite now contains 338 tests. The transcript is `lab/waypoint/p35-gate-second-round.txt`; the 189-case simulation matrix and evidence-script Ruff checks also passed. `git diff --check` is clean. P35 meets its offline Done-when requirements; no revised-code live success is claimed. Reproduction commands from `pilot/` are `env -u PS5_HOST .venv/bin/python ../lab/waypoint/p35_second_round.py`, `env -u PS5_HOST .venv/bin/python ../lab/waypoint/p35_replay.py`, `env -u PS5_HOST .venv/bin/python tools/sim_waypoint.py --output ../lab/waypoint/p35-simulation.json`, and `env -u PS5_HOST .venv/bin/python tools/gate.py --full`. Native OCR and the full gate require the normal macOS environment outside the sandbox.

## First-round evidence and retained guards

P35 implements waypoint selection on the opening live map. Mission selection uses the verified centre cursor when the player marker cannot be identified, recognises the outlined Simeon badge, and tolerates OCR splitting the legend name and letter. Aiming estimates pan gain from observed progress and adjusts each bounded hold. Away retains measured travel when the road tracker is supported; when it is not, it requires coherent visible movement and counts successful commanded hold time instead of inventing displacement. Near and far require 0.8 and 2.0 seconds in that mode. Both paths require a waypoint legend with a numeric distance or a drawn route before exiting, reject unchanged pre-existing proof, and require confirmation to persist for at least 0.15 seconds.

The first-round baseline gate was green: `2750 passed, 1 skipped, 236 xfailed in 674.93s`, retained in `lab/waypoint/p35-gate.txt`. The final second-round validation is reported above; this baseline is not evidence for later changes.

The mission failure had three causes. The old acquisition branch refused an unreadable player marker instead of using the cursor supplied by the opening map. The selected Spieler legend renders a small dark hollow triangle on a white strip; the map marker sits amid the centre crosshair and road strokes with different contrast. Its 15 by 17 legend crop yields no unique accepted map match on any of the 20 live samples. This is a failure of the marker template, not evidence that the player is absent. The legend's small plain S is not the outlined badge drawn on the map, so its template did not match the live image. Native Vision sometimes emits the name and letter as separate lines. The new 25 by 25 grayscale badge template comes from recording 20261111-124637, frame index 155, centre (750, 207), and is enabled only by a recognised Simeon legend name. Other named mission letters retain their existing reader. At the measured live speed the previous fixed 0.10-second mission holds also exhausted the 16-move limit; the new gain estimate fixes that without raising either the move limit or the 45-second deadline.

The away failure was loss of supported corner tracking on later pushes. The repeated first shift around 18.7 pixels is corroborated by broad and right-side gradient correlation; the recordings do not establish that number as a street-grid alias. On seven of the 24 sampled pairs, however, the old method returns no shift while both gradient regions show coherent movement. Periodic texture is still insufficient evidence for treating the correlation peak as a precise signed displacement. The first-round fallback used this only as a coherence check and required changed neutral road strokes in two fixed strips. The second round replaces those empty-strip and paused-background assumptions as described above. It never adds that peak to displacement or infers a new stick polarity from it. Existing supported-shift direction checks, one alternate at a stationary edge, one inland retry, land checks, and the existing-waypoint refusal remain in place. In observed-only mode a uniquely visible land patch can now be approached with checked aiming before the bounded reverse-look fallback.

The live model uses a fine procedural city grid, the recorded outlined badge, a 1007 m scale annotation, and gain 165 pixels per second at full stick, about 107 pixels per second at the .65 pan command. Complete recorded push groups give approximately 107 to 116 pixels per second; 125537 gives about 81. The mission tests also exercise gain 125, corresponding to 81 pixels per second. This model reproduces zoom density, marker appearance, and observed pan speed; it is not a reconstruction of every road or the translucent paused scene. Eight unannotated full-resolution PNG fixtures retain the actual readers' evidence. No recording was modified.

The table below reports all sampled visits and both post-Cross confirmation pictures. Native Vision OCR text, capture index, capture time, and frame ID are retained in `lab/waypoint/p35-visits-evidence.json`. Human inspection sees the fixed centre cursor, visible S badge, and detailed city land in all 20 interactive-map samples. The Spieler legend is visible, but the marker on the map is not uniquely readable. The readers now report the cursor and S in 20 of 20 interactive samples, no player in 20 of 20, and the four pause overviews as overviews. Waypoint means the local purple mark/route test; proof records the independently read legend. The two 123334 post-Cross frames show the newly visible purple waypoint and route and the legend Wegpunkt (1531m).

| Recording | time | frame id | screen | cursor | player | missions | waypoint | proof | land | visible evidence |
|---|---:|---:|---|---|---|---|---|---|---|---|
| 20261111-124637 | 2.6052 | 118921 | map | yes | no | (750,207) | yes | waypoint legend: Wegpunkt (1600m) | yes | Spieler legend, Simeon S legend, Wegpunkt distance, fixed centre cursor |
| 20261111-123334 | 3.0016 | 72067 | map | yes | no | (741,217) | no | - | yes | Spieler legend, Simeon S legend, fixed centre cursor |
| 20261111-123334 | 5.4043 | 72211 | map | yes | no | (741,292) | no | - | yes | Spieler legend, Simeon S legend, fixed centre cursor |
| 20261111-123334 | 8.9570 | 72424 | map | yes | no | (741,404) | no | - | yes | Spieler legend, Simeon S legend, fixed centre cursor |
| 20261111-123334 | 11.9435 | 72603 | map | yes | no | (741,438) | no | - | yes | Spieler legend, Simeon S legend, fixed centre cursor |
| 20261111-123334 | 12.7946 | 72654 | map | yes | no | (741,438) | yes | waypoint legend: Wegpunkt (1531m) | yes | Spieler legend, Simeon S legend, Wegpunkt distance, fixed centre cursor |
| 20261111-123334 | 13.0950 | 72672 | map | yes | no | (741,438) | yes | waypoint legend: Wegpunkt (1531m) | yes | Spieler legend, Simeon S legend, Wegpunkt distance, fixed centre cursor |
| 20261111-123938 | 22.9567 | 95065 | overview | no | no | - | no | - | n/a | pause overview |
| 20261111-123938 | 28.1446 | 95376 | map | yes | no | (745,208) | yes | waypoint legend: Wegpunkt (1590m) | yes | Spieler legend, Simeon S legend, Wegpunkt distance, fixed centre cursor |
| 20261111-123938 | 29.7464 | 95472 | map | yes | no | (745,227) | yes | waypoint legend: Wegpunkt (1590m) | yes | Spieler legend, Simeon S legend, Wegpunkt distance, fixed centre cursor |
| 20261111-123938 | 40.8073 | 96134 | overview | no | no | - | no | - | n/a | pause overview |
| 20261111-123938 | 42.0425 | 96208 | map | yes | no | (745,208) | yes | waypoint legend: Wegpunkt (1590m) | yes | Spieler legend, Simeon S legend, Wegpunkt distance, fixed centre cursor |
| 20261111-123938 | 43.6431 | 96304 | map | yes | no | (745,186) | yes | waypoint legend: Wegpunkt (1590m) | yes | Spieler legend, Simeon S legend, Wegpunkt distance, fixed centre cursor |
| 20261111-123938 | 57.1071 | 97110 | overview | no | no | - | no | - | n/a | pause overview |
| 20261111-123938 | 62.1955 | 97414 | map | yes | no | (745,210) | yes | waypoint legend: Wegpunkt (1581m) | yes | Spieler legend, Simeon S legend, Wegpunkt distance, fixed centre cursor |
| 20261111-123938 | 63.9970 | 97522 | map | yes | no | (745,231) | yes | waypoint legend: Wegpunkt (1581m) | yes | Spieler legend, Simeon S legend, Wegpunkt distance, fixed centre cursor |
| 20261111-123938 | 79.1955 | 98430 | overview | no | no | - | no | - | n/a | pause overview |
| 20261111-123938 | 89.8052 | 99063 | map | yes | no | (745,210) | yes | waypoint legend: Wegpunkt (1581m) | yes | Spieler legend, Simeon S legend, Wegpunkt distance, fixed centre cursor |
| 20261111-123938 | 93.3924 | 99278 | map | yes | no | (826,210) | yes | waypoint legend: Wegpunkt (1581m) | yes | Spieler legend, Simeon S legend, Wegpunkt distance, fixed centre cursor |
| 20261111-123938 | 105.1044 | 99978 | map | yes | no | (745,210) | yes | waypoint legend: Wegpunkt (1581m) | yes | Spieler legend, Simeon S legend, Wegpunkt distance, fixed centre cursor |
| 20261111-123938 | 121.0030 | 100929 | map | yes | no | (745,209) | yes | waypoint legend: Wegpunkt (1582m) | yes | Spieler legend, Simeon S legend, Wegpunkt distance, fixed centre cursor |
| 20261111-123938 | 133.0983 | 101653 | map | yes | no | (745,209) | yes | waypoint legend: Wegpunkt (1582m) | yes | Spieler legend, Simeon S legend, Wegpunkt distance, fixed centre cursor |
| 20261111-125537 | 3.0064 | 151314 | map | yes | no | (750,216) | yes | waypoint legend: Wegpunkt (1537m) * | yes | Spieler legend, Simeon S legend, Wegpunkt distance, fixed centre cursor |
| 20261111-125537 | 4.6913 | 151415 | map | yes | no | (750,235) | yes | waypoint legend: Wegpunkt (1537m) # | yes | Spieler legend, Simeon S legend, Wegpunkt distance, fixed centre cursor |

Each push is sampled from the closest capture 0.18 seconds before the first held-pad tick and 0.23 seconds after the last held-pad tick. The frame IDs below identify those exact comparisons. The duration between the first and last held ticks is a lower estimate of delivered hold duration by up to one tick. The broad and right phase windows overlap; their agreement is a coherence diagnostic, not two independent distance measurements. The production fallback separately checks visible road change in disjoint strips.

| Recording / visit | Held pad interval (s) | Before / after frame | Old LK (dx, dy) px | Broad phase (dx, dy) px | Right phase (dx, dy) px | Responses |
|---|---|---|---|---|---|---|
| 123334 / 1 | 3.170 to 3.420 (0.0, -0.65) | 72066 / 72106 | (-0.0, 24.98) | (-0.01, 25.0) | (0.02, 25.03) | 0.563 / 0.641 |
| 123334 / 1 | 4.769 to 5.161 (0.0, -0.65) | 72162 / 72210 | (0.0, 49.82) | (-0.0, 49.89) | (-0.02, 49.92) | 0.568 / 0.709 |
| 123334 / 1 | 6.488 to 6.935 (0.0, -0.65) | 72265 / 72317 | (-0.0, 59.22) | (0.01, 59.12) | (0.0, 59.12) | 0.681 / 0.759 |
| 123334 / 1 | 8.246 to 8.684 (0.0, -0.65) | 72371 / 72421 | (0.0, 53.01) | (0.01, 52.99) | (-0.01, 53.02) | 0.691 / 0.732 |
| 123334 / 1 | 10.037 to 10.453 (0.0, -0.65) | 72478 / 72527 | (-0.0, 34.29) | (0.02, 34.2) | (0.01, 34.17) | 0.647 / 0.664 |
| 123938 / 2 | 28.325 to 28.581 (0.0, -0.65) | 95376 / 95416 | (0.0, 18.67) | (-0.0, 18.76) | (0.0, 18.78) | 0.679 / 0.741 |
| 123938 / 2 | 29.918 to 30.418 (0.0, -0.65) | 95471 / 95526 | unverified | (-0.03, 68.71) | (0.03, 68.72) | 0.613 / 0.754 |
| 123938 / 3 | 42.222 to 42.488 (0.0, 0.65) | 96208 / 96248 | (0.0, -22.27) | (-0.03, -22.17) | (0.0, -22.18) | 0.596 / 0.673 |
| 123938 / 3 | 43.831 to 44.277 (0.0, 0.65) | 96304 / 96356 | unverified | (-0.07, -54.03) | (-0.06, -54.05) | 0.477 / 0.585 |
| 123938 / 5 | 62.431 to 62.702 (0.0, -0.65) | 97417 / 97458 | (0.0, 21.76) | (0.0, 21.9) | (0.01, 21.88) | 0.616 / 0.758 |
| 123938 / 5 | 64.031 to 64.470 (0.0, -0.65) | 97513 / 97564 | (0.0, 56.11) | (0.02, 56.02) | (0.02, 56.06) | 0.592 / 0.790 |
| 123938 / 5 | 65.807 to 66.365 (0.0, -0.65) | 97620 / 97678 | (-0.0, 59.24) | (0.01, 59.15) | (-0.01, 59.14) | 0.759 / 0.916 |
| 123938 / 5 | 67.697 to 68.186 (0.0, -0.65) | 97733 / 97787 | (0.0, 62.39) | (0.01, 62.28) | (0.0, 62.23) | 0.786 / 0.904 |
| 123938 / 5 | 69.500 to 69.864 (0.0, -0.65) | 97841 / 97887 | (0.0, 28.09) | (0.01, 28.03) | (0.01, 28.03) | 0.722 / 0.811 |
| 123938 / 6 | 89.939 to 90.222 (-0.65, 0.0) | 99060 / 99102 | (18.67, 0.0) | (18.86, -0.0) | (18.84, -0.01) | 0.779 / 0.787 |
| 123938 / 6 | 91.580 to 92.067 (-0.65, 0.0) | 99159 / 99212 | (62.35, -0.0) | (62.22, -0.01) | (62.19, -0.01) | 0.665 / 0.592 |
| 123938 / 6 | 93.427 to 93.947 (-0.65, 0.0) | 99269 / 99325 | unverified | (59.1, 0.02) | (59.1, -0.0) | 0.663 / 0.674 |
| 123938 / 6 | 105.239 to 105.516 (0.0, -0.65) | 99975 / 100016 | (-0.0, 21.77) | (-0.0, 21.88) | (0.02, 21.84) | 0.622 / 0.660 |
| 123938 / 6 | 106.872 to 107.351 (0.0, -0.65) | 100073 / 100126 | unverified | (-0.01, 52.97) | (0.01, 53.0) | 0.600 / 0.712 |
| 123938 / 8 | 121.022 to 121.401 (0.0, 0.65) | 100919 / 100967 | unverified | (-0.05, -22.23) | (-0.01, -22.23) | 0.530 / 0.626 |
| 123938 / 9 | 133.222 to 133.501 (0.0, -0.65) | 101650 / 101691 | (-0.0, 18.69) | (0.01, 18.79) | (0.01, 18.78) | 0.606 / 0.701 |
| 123938 / 9 | 134.838 to 135.359 (0.0, -0.65) | 101747 / 101802 | unverified | (0.07, 62.2) | (0.01, 62.2) | 0.576 / 0.738 |
| 125537 / 1 | 3.183 to 3.541 (0.0, -0.65) | 151314 / 151360 | (-0.0, 18.71) | (0.03, 18.78) | (0.02, 18.82) | 0.506 / 0.627 |
| 125537 / 1 | 4.874 to 5.212 (0.0, -0.65) | 151415 / 151460 | unverified | (0.04, 37.42) | (0.01, 37.37) | 0.539 / 0.706 |

The replay uses the original RGB frames matched to play ticks by frame_id, the real minimap crop reader, native Vision OCR, and the real HUD reader. It stops neutral at the first proposed input that differs from the recorded one. This prevents treating old footage as the consequence of an input that was never delivered. All five replay endings are intentional divergence stops, not completed waypoint runs. The two paths complete in the live-zoom simulation described below.

| Recorded visit | Matched input prefix | First divergence | Replay ending |
|---|---|---|---|
| 124637 mission | Options 0.125 s, release 0.360; Cross 1.647, release 1.842 | 3.160 s, frame 118954: new aiming stick (0.3794, -0.5278), recorded neutral | Failed/neutral, recorded-input-diverged; the new reader now selects the visible S |
| 123334 away | Options 0.129, Cross 1.663; north pushes begin 3.170, 4.769, 6.488 | 6.816 s, frame 72295: new neutral release while recorded north is still held | Failed/neutral, recorded-input-diverged; the adjusted hold differs |
| 125537 away | Options 0.240, Cross 1.661; north pushes begin 3.183 and 4.874 | 5.247 s, frame 151447: new north hold while recorded pad is neutral | Failed/neutral, recorded-input-diverged; the new movement path requests a different hold |

`lab/waypoint/p35-replay.json` retains each common-prefix tick, proposed and recorded pads, phase, capture ID, divergence, and the final neutral result. The remaining 123938 visits are represented by their real-reader and push-pair evidence and the live-zoom simulator; no closed-loop outcome is claimed from incompatible prerecorded input.

The final simulator command completed 189 cases: 45 successful paths and 144 expected refusals or injected wrong-screen cases, including the six new coastal cases above. Its 12 live-zoom cases all complete with a map route proof and neutral terminal pad. At delays 0.14, 0.6, and 1.1 seconds, mission ends at 22.60 seconds after nine bounded aiming holds; away near ends at 12.15 seconds after three holds, and away far at 17.45 seconds after six. Each successful run has one Cross to enter the map, one Cross to set the waypoint, and two Circle exits. The map-setting Cross lasts two or three simulated 50 ms ticks. The extra forced-fallback tests exercise both distances when numeric shifts are unavailable and assert that far has at least 1.6 times the delivered stick travel of near. The full simulator trace is stored in `lab/waypoint/p35-simulation.json` at a 0.05-second tick period.

The three most harmful incorrect presses and their guards are recorded here.

| Incorrect press | Consequence | Guard and regression evidence |
|---|---|---|
| Cross on an unreadable or unrelated screen | Activates an unrelated menu action | `test_live_zoom_wrong_screen_preserves_forward_input_refusals` covers both targets and every listed wrong screen at entry, acquisition, confirmation, and exit. Existing cursor, missing-image, damaged-frame, and wrong-selected-tab tests also deny forward input. |
| Cross over an existing waypoint | Toggles the existing waypoint off | `test_a_waypoint_already_under_the_cursor_is_not_toggled_off` asserts no Cross; both mission and away paths retain the same guard. The live fixture records the existing mark and legend. |
| Circle from an unverified starting screen | Can leave a failed mission or act in gameplay | `test_nothing_is_pressed_when_it_does_not_start_from_the_game` asserts a neutral pad for failed, damaged, and missing initial screens. After opening, Circle is the only backout button and the existing three-exit and deadline tests bound it. |

Other retained refusals include no visible or uniquely trackable mission, lost target tracking, no cursor progress, move limits, no map texture, inconsistent or damaged motion pairs, wrong direction after calibrated polarity, a stationary map after the one alternate, and sea after the bounded inland recovery. They remain covered by the existing waypoint suite. New tests cover the real letter, split OCR legend, nearest mission with no player, live movement pairs, stationary live grid, distinct near/far travel, unchanged old proof, isolated proof, and observed-only inland recovery. The independent input-safety review found the inland retry still requiring numeric displacement in observed-only mode; that was corrected and its regression test passes without inventing displacement.

Commands are run from `pilot/` with `PS5_HOST` removed. `env -u PS5_HOST .venv/bin/python tools/sim_waypoint.py --output ../lab/waypoint/p35-simulation.json` produced the successful simulation matrix. `env -u PS5_HOST .venv/bin/python ../lab/waypoint/p35_visit_readers.py` and `env -u PS5_HOST .venv/bin/python ../lab/waypoint/p35_inventory.py` reproduce the native reader and push tables against the read-only recordings. `env -u PS5_HOST .venv/bin/python ../lab/waypoint/p35_replay.py` reproduces the bounded input-matched replays. Native Vision, CoreML compilation, and disposable loopback test servers require execution outside this sandbox. The initial gate in this run ended with `5 failed, 2738 passed, 3 skipped, 236 xfailed, 5 errors`; its failures were denied disposable loopback binds and CoreML temporary-directory access. The required command is therefore run outside the sandbox, with the final transcript in `lab/waypoint/p35-gate-second-round.txt`. No tests or platform requirements were disabled.

No additional live console run, daemon call, PS5 command, credential access, deployment, commit, or push was performed during this revision. The work remains on the supplied `feat/pilot-live-map` worktree for reviewer integration. The task README explicitly says "Git cannot write here" and "the reviewer commits them"; this task-specific read-only Git environment prevents the normal global commit/PR workflow. No pull request was opened. Native map readers are verified on the supplied S-bearing frames, not on unseen mission-giver badge styles or arbitrary zoom levels. The recorded 13:35 live trial exposed the second-round failures. The revised code has not been tried on the console; a later authorised trial must verify the newly chosen inland destination and post-Cross proof. The offline evidence does not establish live success.

## Review

Not merged yet; the work is committed on its branch and waits for a try on the console.

The first round passed the full gate and its own simulation and failed at the first live try, by day on the coast road (`20261111-133505`): the procedural map of the simulation had nothing of what the real map looks like there. The reviewer's own look at the open map afterwards showed why the pair is hard: the map is drawn over the paused scene, and with a bright daytime picture behind it the roads nearly vanish. The second round was run against the real frames of that session and of `20261111-132729`, and what it reports fits what the recordings show: too few corner tracks survive on the washed-out map, and the first fallback looked at a strip that held the paused scene and the sea instead of map.

Changed by the reviewer: the four live-map test matrices replay real frames and took the default gate from about a minute to well over ninety seconds; `tests/conftest.py` now keeps one case of each for the default gate and leaves the rest to `--full`, the way the driver's matrices are handled. With that the default gate passes in 103 seconds beside a running worker; the limit of ninety has to be checked again on a quiet machine before the merge.

Open before the merge: `away` set from the coast by day and in town by night, three times each, and the mission letter once. The bridge to the console stopped at its time limit before this could be tried.
