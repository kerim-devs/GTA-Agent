Incidents of the recordings below, as written by pilot/tools/incidents.py. Times are seconds on the clock of each recording's frames.jsonl, play is the time of its foot and drive sections. A death in a mission is counted twice, as the death and as the failed mission.

## Counts per recording

| Recording | Play min | death | arrest | mission_failed | mission_passed | retry | wanted | collision | car_change | standstill | reverse | turn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 20261111-164039 | 14.3 | 1 | 0 | 1 | 0 | 1 | 1 | 1 | 2 | 4 | 0 | 1 |
| 20261111-165543 | 14.5 | 0 | 0 | 0 | 2 | 0 | 1 | 7 | 3 | 6 | 2 | 2 |
| 20261111-171046 | 14.7 | 0 | 0 | 0 | 1 | 0 | 0 | 4 | 1 | 0 | 1 | 0 |
| 20261111-172549 | 7.5 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 1 | 1 | 1 | 2 |
| 20261111-175312 | 10.3 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | 2 | 1 | 2 | 0 |
| 20261111-180814 | 11.5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 1 | 0 | 0 |
| 20261111-182316 | 9.7 | 3 | 0 | 0 | 1 | 0 | 3 | 2 | 0 | 1 | 0 | 1 |
| 20261111-183820 | 11.6 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | 0 | 0 |
| 20261111-185323 | 10.2 | 0 | 0 | 1 | 0 | 1 | 1 | 1 | 0 | 4 | 0 | 0 |
| 20261111-190825 | 8.4 | 2 | 0 | 2 | 1 | 2 | 2 | 2 | 0 | 4 | 0 | 1 |
| 20261111-192328 | 1.4 | 0 | 0 | 0 | 1 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| all | 114.1 | 7 | 0 | 4 | 8 | 4 | 10 | 20 | 14 | 23 | 6 | 7 |
| per hour of play | | 3.7 | 0.0 | 2.1 | 4.2 | 2.1 | 5.3 | 10.5 | 7.4 | 12.1 | 3.2 | 3.7 |

## Counts per cause

| Class | Cause | Count | Per hour of play |
| --- | --- | --- | --- |
| death | police | 5 | 2.6 |
| death | fight | 2 | 1.1 |
| mission_failed | player_died | 3 | 1.6 |
| mission_failed | other | 1 | 0.5 |
| mission_passed | passed | 8 | 4.2 |
| retry | checkpoint | 1 | 0.5 |
| retry | mission_start | 1 | 0.5 |
| retry | unknown | 2 | 1.1 |
| wanted | lost | 4 | 2.1 |
| wanted | death | 5 | 2.6 |
| wanted | recording_end | 1 | 0.5 |
| collision | carried_on | 13 | 6.8 |
| collision | reversed | 1 | 0.5 |
| collision | unknown | 6 | 3.2 |
| car_change | mission | 3 | 1.6 |
| car_change | other | 11 | 5.8 |
| standstill | stuck_vehicle | 2 | 1.1 |
| standstill | stuck_foot | 5 | 2.6 |
| standstill | fight | 9 | 4.7 |
| standstill | waiting | 7 | 3.7 |
| reverse | reverse | 6 | 3.2 |
| turn | turn | 7 | 3.7 |

## Missions

### 20261111-164039

"Begib dich nach Vespucci Beach.", 1 try: try 1, 435 to 513 s, ended without a banner (silence); incidents none.

"Folge Lamar.", 1 try: try 1, 546 to 608 s, ended without a banner (silence); incidents none.

"Sammle elne Waffe auf.", 2 tries: try 1, 628 to 683 s, ended failed, player_died ("Franklin ist tot."), then retry; incidents 1 death, 1 mission_failed, 1 standstill; try 2, 692 to 754 s, ended without a banner (silence); incidents 1 standstill.

"Steig auf das Motorrad.", 1 try: try 1, 877 to 902 s, ended without a banner (recording ended); incidents none.

Outside any mission: 2 car_change, 1 collision, 1 retry, 2 standstill, 1 turn, 1 wanted.

### 20261111-165543

"Beglb dlch zum Abschleppwagen.", 1 try: try 1, 221 to 285 s, ended without a banner (silence); incidents 1 collision, 2 standstill.

"Warte auf Tonya.", 1 try: try 1, 316 to 508 s, ended passed; incidents 3 collision, 1 mission_passed, 2 standstill.

Outside any mission: 3 car_change, 3 collision, 1 mission_passed, 2 reverse, 2 standstill, 2 turn, 1 wanted.

### 20261111-171046

"Stelg In den Liefemagen.", 1 try: try 1, 154 to 214 s, ended without a banner (silence); incidents 1 collision.

"Steig wieder in den Lieferwagen.", 1 try: try 1, 329 to 391 s, ended without a banner (silence); incidents none.

"Folge Chop.", 1 try: try 1, 482 to 542 s, ended without a banner (silence); incidents none.

"Begib dlch zu Chop und. zieh ihn von d", 1 try: try 1, 592 to 652 s, ended without a banner (silence); incidents none.

"Bring D zu Lamars Haus.", 1 try: try 1, 689 to 750 s, ended passed; incidents 1 mission_passed.

Outside any mission: 1 car_change, 3 collision, 1 reverse.

### 20261111-172549

"Schalte den Gartne", 1 try: try 1, 133 to 194 s, ended without a banner (silence); incidents 1 standstill.

"Hol das Auto zurück.", 1 try: try 1, 206 to 330 s, ended passed; incidents 1 mission_passed.

Outside any mission: 1 car_change, 1 reverse, 2 turn.

### 20261111-175312

No objective was read in this recording.

Outside any mission: 2 car_change, 1 collision, 1 mission_passed, 2 reverse, 1 standstill, 1 wanted.

### 20261111-180814

"Begib dich nach Pacific Bluffs.", 1 try: try 1, 223 to 289 s, ended without a banner (silence); incidents 1 car_change.

"Bring Franklin nahe an die Yacht.", 1 try: try 1, 311 to 376 s, ended without a banner (silence); incidents 1 car_change.

"Verfolge die Yacht.", 1 try: try 1, 394 to 456 s, ended without a banner (silence); incidents 1 car_change.

Outside any mission: 1 car_change, 1 standstill.

### 20261111-182316

"Begib dich zu Michaels H", 1 try: try 1, 45 to 105 s, ended passed; incidents 1 collision, 1 mission_passed.

Outside any mission: 1 collision, 3 death, 1 standstill, 1 turn, 3 wanted.

### 20261111-183820

"Begib dich zu Ammu-Nation.", 1 try: try 1, 882 to 900 s, ended without a banner (recording ended); incidents none.

Outside any mission: 1 car_change, 1 death, 1 standstill, 1 wanted.

### 20261111-185323

"Begib dich zu dem Treffen bei der Recycling-Anlage.", 1 try: try 1, 168 to 234 s, ended without a banner (silence); incidents 1 collision, 1 standstill.

"Kehr zurück zu Lamar und Stretch.", 1 try: try 1, 678 to 745 s, ended without a banner (silence); incidents none.

"Kehr zurück zu Lamar und Stretch.", 1 try: try 1, 775 to 841 s, ended without a banner (silence); incidents none.

Outside any mission: 1 mission_failed, 1 retry, 3 standstill, 1 wanted.

### 20261111-190825

"Begib dich wieder zu Franklins Haus.", 1 try: try 1, 268 to 335 s, ended passed; incidents 1 collision, 1 mission_passed.

"Steig in den Pickup.", 1 try: try 1, 520 to 642 s, ended without a banner (silence); incidents 1 collision.

"Steig in den Pickup.", 1 try: try 1, 685 to 747 s, ended without a banner (silence); incidents 1 standstill.

"Kehr zurück zu Michaels Haus.", 2 tries: try 1, 753 to 820 s, ended failed, player_died ("Franklin ist tot."), then retry; incidents 1 death, 1 mission_failed; try 2, 840 to 900 s, ended without a banner (recording ended); incidents 1 standstill, 1 turn.

Outside any mission: 1 death, 1 mission_failed, 2 retry, 2 standstill, 2 wanted.

### 20261111-192328

No objective was read in this recording.

Outside any mission: 2 collision, 1 mission_passed.

## Deaths, arrests and failures

| Recording | Time | Frame | Class | Cause | Text as read |
| --- | --- | --- | --- | --- | --- |
| 20261111-164039 | 677.8 | 39436 | death | fight | Franklin ist tot. |
| 20261111-164039 | 682.0 | 39684 | mission_failed | player_died | Franklin ist tot. |
| 20261111-182316 | 349.7 | 20860 | death | police |  |
| 20261111-182316 | 472.6 | 28216 | death | police |  |
| 20261111-182316 | 878.6 | 52503 | death | police |  |
| 20261111-183820 | 271.4 | 16246 | death | police |  |
| 20261111-185323 | 118.1 | 7053 | mission_failed | other | Franklin hatte nicht genug Geld, um die Pump-Action-Schrotflinte und das taktlsche Llcht zu kaufen. |
| 20261111-190825 | 82.1 | 4891 | death | police | Franklin ist tot. |
| 20261111-190825 | 84.9 | 5056 | mission_failed | player_died | Franklin ist tot. |
| 20261111-190825 | 829.1 | 48318 | death | fight | Franklin ist tot. |
| 20261111-190825 | 831.9 | 48485 | mission_failed | player_died | Franklin ist tot. |
