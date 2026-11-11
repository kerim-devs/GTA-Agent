P15 implements the pure `pilot.hud.read(frame, text=None) -> Hud` reader, real-frame regression tests and a reproducible labelled-video evaluator. The recorded-data acceptance thresholds pass: 192/200 screens correct (96.0%), zero false stops among 110 ordinary-game frames, and 68/73 numerical health labels within 0.05 (93.15%). Mean runtime without OCR is 0.304 ms per call; the 95th percentile of per-frame means is 0.417 ms. The default gate result is recorded below.

The balanced sample contains 100 fixed-seed random frames (60 long Wi-Fi, 20 from each clean session) and 100 visually selected rare-screen frames including boundaries. Random-screen accuracy is 99/100 and rare-screen accuracy is 93/100. Twenty additional shootout observations preserve low-health and full-health fixture evidence outside the balanced screen score. All source identities, capture-relative timestamps and decoded-RGB hashes are in [labels.json](../../lab/hud/labels.json); review contact sheets and reproduction instructions are in [the evidence README](../../lab/hud/README.md). Calibration and evaluation use the same recordings, with correlated rare frames; the score is a local acceptance result, not an independent generalisation benchmark.

The confusion matrix below uses true classes as rows and predictions as columns.

| True / predicted | game | pause | map | weapon_wheel | phone | failed | passed | loading |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| game | 110 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| pause | 4 | 7 | 0 | 0 | 0 | 0 | 0 | 0 |
| map | 0 | 0 | 14 | 0 | 0 | 0 | 0 | 0 |
| weapon_wheel | 1 | 0 | 0 | 18 | 0 | 0 | 0 | 0 |
| phone | 1 | 0 | 0 | 0 | 12 | 0 | 0 | 0 |
| failed | 0 | 0 | 0 | 0 | 0 | 15 | 0 | 0 |
| passed | 2 | 0 | 0 | 0 | 0 | 0 | 8 | 0 |
| loading | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 8 |

Every screen miss conservatively returns `game`. The early phone and wheel have changed/transitioning anchors, the initial passed banner is heavily tinted, and the four pause frames contain codec damage in the title and tab strip. These frames remain visible failures; no text-only override hides them.

| Source frame | Capture seconds | Label | Reader |
| --- | ---: | --- | --- |
| [wifi-03422](../../lab/hud/fixtures/wifi-03422.png) | 153.7323 | phone | game |
| [wifi-10961](../../lab/hud/fixtures/wifi-10961.png) | 539.2213 | weapon_wheel | game |
| [wifi-07277](../../lab/hud/fixtures/wifi-07277.png) | 338.8176 | passed | game |
| [wifi-07279](../../lab/hud/misses/wifi-07279.png) | 339.1331 | passed | game |
| [wifi-08221](../../lab/hud/fixtures/wifi-08221.png) | 387.0318 | pause | game |
| [wifi-08224](../../lab/hud/misses/wifi-08224.png) | 387.3534 | pause | game |
| [wifi-08230](../../lab/hud/misses/wifi-08230.png) | 387.4617 | pause | game |
| [wifi-08237](../../lab/hud/misses/wifi-08237.png) | 388.1795 | pause | game |

Health mean absolute error over the 70 returned numerical readings is 0.0211. Three abstentions count as failures, so the 68/73 accuracy does not discard them. Unreadable or absent ground-truth bars are explicitly null and excluded from the numerical denominator. The two large numerical errors read zero on dim or corrupted green tracks; the other three misses abstain where minimap symbols or scene bleed interfere. These are recorded limitations, including a possible false low-health trigger.

| Source frame | Capture seconds | Label | Reader | Absolute error |
| --- | ---: | ---: | ---: | ---: |
| [wifi-03248](../../lab/hud/misses/wifi-03248.png) | 144.4780 | 0.43 | 0.0 | 0.43 |
| [wifi-04876](../../lab/hud/misses/wifi-04876.png) | 223.2659 | 0.50 | 0.0 | 0.50 |
| [wifi-06660](../../lab/hud/misses/wifi-06660.png) | 308.7334 | 0.50 | None | abstained |
| [wifi-07584](../../lab/hud/misses/wifi-07584.png) | 354.0662 | 0.50 | None | abstained |
| [wifi-07871](../../lab/hud/misses/wifi-07871.png) | 368.2327 | 0.50 | None | abstained |

The reader uses small authentic UI anchors and fixed bar geometry. Colour locates a track, brightness distinguishes its bright fill from the still-coloured empty part, and a prefix fit rejects scattered pixels. The observed empty armour returns 0 rather than 1; special and health return fractions when readable. Damaged red tracks have no stable boundary and return None rather than invented zero. A low green bar around 0.27 and full health are covered by real-frame tests. Absent HUDs, black frames, wrong shapes/dtypes, noise, destroyed bar pixels, read-only inputs and stale contradictory text are covered. Text only relaxes an already matching banner shape; it cannot classify an ordinary frame by itself. Wanted remains None and wanted_flashing remains false.

Gate verification passed with `.venv/bin/python tools/gate.py` from `pilot/`: ruff check passed, 51 files passed formatting, and pytest reported 447 passed, 1376 deselected and 4 xfailed in 21.40 seconds. The default gate completed in 21.61 seconds. The focused HUD suite passed all 37 tests. The complete output is in [gate.txt](../../lab/hud/gate.txt). The initial sandboxed attempt passed lint/format and the HUD tests but four existing overlay HTTP tests could not bind 127.0.0.1:0 (PermissionError). The exact default gate was rerun with local loopback access; no tests or source outside the owned scope were changed.

Decisions made without questions: `pause` means the title/tab screen including its map preview; `map` means the expanded interactive map. Uncertain transitions and cutscenes remain game, while wholly black frames are loading. Capture timestamps come from frames.jsonl, not nominal video seconds. The card's approximate 95–110-second wheel span was wrong for capture time; verified spans are about 14.8–15.3 and 537.8–539.2 seconds. Full-resolution review corrected five initial thumbnail labels before final scoring; the correction history is preserved. Fixtures live under the explicitly owned lab/hud tree and tests load them there.

Missing evidence: wanted levels and flashing, Wasted/Busted, reliably readable red low-health fill, full and partially depleted armour, fully depleted special, other character phones, other menu tabs and alternative safe areas/resolutions. No appearance for these unsupported cases is claimed. This work does not connect to the PS5, run a daemon, modify secrets or config, wire the conductor, or claim live input verification. The next integration can import read(frame, text) directly and must treat None as unknown. Clear armour/red-health footage is needed before stronger reliability claims.

The deliverable stays uncommitted on feat/pilot-hud as required by docs/tasks/README.md: the reviewer owns commits and integration. No pull request was opened. Owned changes are hud.py, test_hud.py, evaluate_hud.py, lab/hud evidence and this report.

## Review

Checked in the night of 10 to 11 November. The default gate passes. The labelled set is also what the reader was tuned on, so I ran it over every third frame of the two clean sessions and every second frame of the long recording instead of trusting the 200 labels.

Ordinary play is never taken for something else: 4771 and 4797 frames of walking and standing over the cable, all read as the game. On the long recording the screens come out as coherent spans where the text reader had found them independently: the failed screen from 33.2 to 40.1 s followed by loading, the weapon wheel at 14, 45 and 538 s, the phone at 154 s, the passed banner at 339 s, the pause menu at 385 s and the map from 388 to 392 s. The mean time is 0.4 ms.

Health needs care by whoever uses it. In the session where the pilot sprints along roads and nothing hurts the character, 17 of 3683 readings fall under 0.3, single frames with a busy background behind the bar, and the report's own table has two readings of zero on a half-full bar. A single low reading must not count; the conductor has to look at several readings before it tells the head or a skill that the character is dying.

The contact sheets for labelling, 15 MB, are not committed; `lab/hud/prepare.py` rebuilds them. The fixtures are full frames and stay, 24 MB.
