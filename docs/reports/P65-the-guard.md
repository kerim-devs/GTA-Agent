# P65: the guard

With the guard the pilot notices a threat in the tick, whatever its head is doing. Behind a head modelled to answer after 8.5 s it noticed 18 of the 20 enemy onsets of the bench, median 0.046 s and at most 0.12 s after the marker showed, and the five star onsets from calm after 0.11 to 0.15 s; the same head without the guard noticed one enemy (after 2.5 s) and the stars after 0.51 s, and answered none of the 26 threat scenes within three seconds, where with the guard it answers 13. With the pilot's own rules behind it the guard is as fast (median 0.050 s on enemies). It is not wrong once on the 29 calm scenes, and the false flight before enemy-13 is gone. On eleven hard calm scenes, where the minimap reader takes red behind the map for a marker, it starts on 8 with the pilot and 9 with the slow head and holds the pad there for 11.5 s and 30 s in all, turning the camera towards the false red, but it never aimed or fired on one. Two bars of the card do not hold: on enemy-04 and enemy-05 the figure is hurt, and the low-health flight, which the card ranks above a marker, makes both onsets void (enemy-05 is one of the three edge onsets); and the head row answers a star onset 0.068 s after the pilot row, a millisecond over two ticks, because the pilot's own rules answer stars before the guard's 0.1 s confirmation counts. A replay never turns the camera, so the first run at the console with `pilot play --guard` has to measure what none can: the time from a marker to the first aimed shot while the camera turns (from a `guard_start` row's `seen` in play.jsonl to the first tick with L2 and R2), and whether pressing L2 before the turn is finished, so that the game's aim assist finishes it, is faster than turning first. It should also look for `guard_start` rows with rule `red` and no enemy in the picture.

## What was built

`pilot/src/pilot/guard.py` holds the rules as a table of data at its top, one `Rule` per rank with its signal, how it counts (`("seconds", s)`: the same reading held s seconds; `("ticks", n, m)`: on n of the last m ticks) and its answer, and a `Guard` that keeps the counters, says on every tick which rule holds the pad and why, and answers with the skills that exist: `Walk` with sprint for a flight, `Fight` for a marker inside the map, `Face` for a marker on its edge. The ranks are the card's:

| Rank | Rule | Counts once | Answer | Lets go |
|---|---|---|---|---|
| 1 | `screen` | a screen other than the game, the judge's mode none, the flow reflex holding the tick, or a minimap read as none, on two ticks in a row | silence; whatever the guard held it lets go of | the game is back |
| 2 | `low_health` | health under a third for half a second, counted only once the HUD has been back for a second | sprint away from the nearest red marker, straight ahead without one | health read at 0.45 or more, or four seconds |
| 3 | `stars` | the same number of stars read again 0.1 s after the first reading, no other number between | the same flight, never a shot | the head's plan has been put in the runner since, or four seconds |
| 4 | `red` | a red marker inside the map (the reader's border flag unset) on two of the last three ticks | `Fight`; a flight instead when the objective's class is escape | the fight ends by itself (two seconds without red, its time limit, an unreadable map) |
| 5 | `red_edge` | red only on the map's edge on two of the last three ticks | `Face` turns the camera to the marker while no skill of the plan moves the figure; while one does, the head is told and the pad is the plan's | a marker comes inside (rank 4 takes over) or two seconds without red |

A rule of higher rank takes over from a lower one on the tick it counts. A rule that has let go is spent until its signal has been gone for two seconds (as long as `Fight` waits without red), and while a spent rule still counts nothing of lower rank starts: its threat is the head's rules' from then on. That keeps the guard from taking the stars back from the head's escape on the next tick, and from fighting while the head's low-health rules flee. A damaged picture or a reader that abstains stands out: it neither confirms a signal nor breaks one. While stars are lit, red markers do not count at all, and a single reading of a star clears the triggers of a running fight on that tick, before the stars count. Until the HUD has been back for a second, neither a rule nor the skill it runs sees the health bar, so that a fight started as the picture returns is not ended by the bar fading in.

Where the figure is comes from the judge's mode when there is one, else from the map: flat is on foot, tilted is a vehicle, but a tilted map with stars lit says nothing (docs/LOG.md, 11 November) and the figure stays where it was. In a vehicle, or where nothing is known, the guard puts nothing on the pad: the rule that counts is told to the head once, as `guard_news`, and the head's request in flight is abandoned so that its rules are asked at once.

`conductor.py` takes a `guard` and is unchanged without one. With one, it asks the guard on every tick after `_flow_tick` and before `_finish_head`. On the guard's start it stops the runner with the reason `guard_<rule>`, raises the epoch, abandons the head request in flight, drops the carry-on and queues the `guard_start` event, so the head is asked on the same tick. While the guard holds the pad the runner is not ticked and what the head answers meanwhile waits in the queue; no `plan_ending` request goes out. On the tick it lets go the pad is neutral and `guard_end` is queued without raising the epoch: an answer on its way was asked with the start in view, and a model head would need eight more seconds for another. On a screen of the flow reflex the guard is asked with the flow's tick and lets go once the screen counts; its `guard_end` then reaches the head with the flow's own events. With a guard the head is not shown a health reading the guard does not trust yet (the HUD back for less than a second), and the conductor's own `low_health` event waits for the same second: the false flight before enemy-13 came from the head reading a bar fading in as empty. `pilot play --guard` gives the conductor a guard; without the flag nothing at the console changes.

`mission.py`: a skill the guard stopped is passed on to the rules as stopped, not failed, so neither the rules nor the goals retry it with a look round first; the guard's events need no rule of their own.

## The guard in play.jsonl

`run_play` writes a row of its own for each of the guard's events, before the tick's row and on the play log's clock (`t` is seconds since the session started, as in every row of play.jsonl), so that a live run can be timed from play.jsonl alone:

```json
{"type": "guard_start", "t": 12.345, "rule": "red", "seen": 12.312, "bearing": -27.9, "answer": "fight"}
{"type": "guard_end", "t": 15.678, "rule": "red", "reason": "no-red-blips"}
{"type": "guard_news", "t": 20.001, "rule": "red", "seen": 19.968, "bearing": 12.5, "where": "vehicle"}
```

`t` is the tick on which the guard took the pad, let go of it or told the head. `seen` is the first tick on which the rule's signal was read, before it counted: for `red` and `red_edge` the first tick of the two of three, for `stars` the first reading of the number, for `low_health` the first low reading after the HUD had been back a second. `bearing` is the nearest red marker's direction in picture degrees (0 straight ahead, positive to the right) where a marker gives one, else null. `rule` is one of `low_health`, `stars`, `red`, `red_edge`; `reason` on the end row is why it let go (`no-red-blips`, `time`, `health back`, `head plan started`, `no red left`, `screen`, `vehicle`, a skill's own failure such as `stuck`, or `<rule> is left to the head`). A rule of higher rank that takes over writes only its start row, with `"after"` naming the rule it replaced, which writes no end row. The tick row of a tick the guard holds names the skill `guard` with its rule and why. `guard_news` is written when the guard only tells the head (in a vehicle, or `red_edge` while a skill moves the figure).

## Hard calm scenes

The 29 calm scenes were chosen where the labels show no red, so they cannot show what a false red does to the guard. P64's search had thrown out twelve enemy onset proposals in which the reader took red behind the translucent map for a marker (`scenes.json`, `selection.rejected`). For each I ran the minimap and HUD readers on every native frame from six seconds before the proposal to four after (map shape, damage, red blips with their border flag, stars, health, screen), and looked at the minimap, magnified 2x, on six frames with red and at the scene at -6, -3, 0, +2 and +3.9 s. Eleven are kept in `lab/reaction/scenes-hard.json` (`hard-01` to `hard-11`), each a calm window of ten seconds with its own ledger, `ledger-hard.jsonl`, and board, `board-hard.md`:

| Scene | Recording, centre | What the reader takes for red | Red frames, inside |
|---|---|---|---:|
| hard-01 | 172549, 185.67 | red bird-of-paradise flowers; the figure walks in view | 56, 26 |
| hard-02 | 172549, 195.72 | red roof tiles while the figure climbs a roof | 21, 9 |
| hard-03 | 194609, 603.22 | a red piece of furniture indoors; the room, not the figure, in view | 6, 0 |
| hard-04 | 205309, 313.04 | a red-painted curb at night and the map's red district tint | 9, 2 |
| hard-05 | 210812, 405.78 | red objects on a dresser; the room in view | 11, 7 |
| hard-06 | 210812, 328.40 | a red tin on the same dresser, the longest false red | 94, 38 |
| hard-07 | 114541, 601.75 | a red and white barrier in the desert; the yard in view | 7, 3 |
| hard-08 | 114541, 615.63 | reddish sand behind the map; the yard in view | 17, 14 |
| hard-09 | 175312, 216.60 | a red-painted curb at dusk, the figure running | 6, 1 (from 212.57 on) |
| hard-10 | 175312, 823.39 | a jogger's pink and red clothes during a beach race | 3, 0 |
| hard-11 | 193105, 790.99 | a red mural indoors; the reader also calls the indoor map tilted on 86 frames | 12, 1 |

Red frames are those of the readers' pass over the proposal's window. One proposal is not used: 205309 at 336.30 is a brawl over a car in which the health bar falls into red, no calm scene. hard-09 is centred 1.97 s before its proposal (218.57), because stars light up at 221.65 and a real marker shows at 222.1. Five of the eleven (hard-03, 05, 06, 07, 08) show a room or a yard instead of the figure, an idle or first-person camera; P64 left such windows out of the calm set, here they stay because the false red is what is measured.

`reflex`, `pilot+guard` and `head+guard` ran over them in real time, one replay at a time, the head with its delay modelled at 8.4685 s. The guard rows were run a second time after the change to the guard described under the 55 scenes, and those are the rows in `ledger-hard.jsonl`; the reflex rows and Kerim's are the first run's:

```sh
env -u PS5_HOST .venv/bin/python tools/reaction.py run reflex pilot+guard head+guard --scenes ../lab/reaction/scenes-hard.json --ledger <scratch>/hard-full-1.jsonl --head-delay 8.4685 --head-delay-source "median of 20 Codex answers, request to response, in head.jsonl of /Users/kerim/recordings/pilot/20261110-223934, 20261110-230229, 20261110-231512 and 20261112-100713 (5.748 to 12.598 s, ninth decile 11.273 s)"
env -u PS5_HOST .venv/bin/python tools/reaction.py run pilot+guard head+guard --scenes ../lab/reaction/scenes-hard.json --only hard-01 hard-02 hard-03 --ledger <scratch>/hard-full-2.jsonl --head-delay 8.4685 --head-delay-source "<as above>"   # and so on, three scenes at a time
env -u PS5_HOST .venv/bin/python tools/reaction.py board --scenes ../lab/reaction/scenes-hard.json --ledger ../lab/reaction/ledger-hard.jsonl
```

No row fired a shot or aimed on any of the eleven, in either run, and none put an answer from the answer set on the pad (false answers 0 for all three). What the guard did in the second run:

| Scene | pilot+guard | head+guard |
|---|---|---|
| hard-01 | Fight from +0.40 s to the end of the scene (3.60 s), turning on 30 of 109 ticks | Fight from +0.40 s to the end (3.60 s), turning on 29 of 108 |
| hard-02 | told the head of red on the edge at +0.03 s while the plan walked | turned to the edge from +0.03 s to the end (3.97 s), 8 of 119 ticks |
| hard-03 | nothing | turned from +0.07 s for 2.03 s, 1 tick |
| hard-04 | told the head at -1.11 s | turned from -1.13 s for 4.97 s, 5 ticks |
| hard-05 | nothing | nothing |
| hard-06 | told the head at +0.04 s; Fight from +0.47 s to the end (3.53 s), turning on 29 of 106 | turned from +0.07 s for 2.23 s (24 ticks), then Fight from +2.30 s to the end (1.70 s), turning on 17 of 51 |
| hard-07 | told the head at -2.94 s; Fight from +0.06 s for 2.20 s, turning on 5 of 66 | turned from -2.96 s for 2.03 s and from +0.20 s for 2.07 s (2 ticks each) |
| hard-08 | Fight from +0.04 s for 2.20 s (2 ticks of turning) | Fight from +0.04 s for 2.20 s (2 ticks) |
| hard-09 | told the head at +2.00 s | turned from +2.00 s to the end (2 ticks) |
| hard-10 | nothing | nothing |
| hard-11 | told the head at +0.17 s | turned from +0.17 s for 3.17 s (4 ticks) |

So the guard starts on 8 of the 11 hard scenes with the pilot's rules behind it and on 9 with the slow head. With the pilot it takes the pad on 4 (11.5 s in all) and only tells the head on 4 more, because the plan is walking; with the slow head the figure stands, and it takes the pad on 9 (30.0 s in all). On the pad it puts a turn of the right stick, on 66 and 96 ticks, and neutral pads otherwise: `Fight` turns towards the false red and aims only once it is within 5 degrees ahead, which no false red was long enough in a replay that never turns. False notices: the reflex 38 on 10 scenes, pilot+guard 10 on 8, head+guard 10 on 9; two of three ticks cut them to about a third but do not remove them. The first run, before the change, gave the same picture with different details (pilot+guard 9.6 s on 4 scenes and 15 false notices on 9, head+guard 29.2 s on 9 and 11 on 9, 53 and 99 ticks of turning): no episode on a hard scene ended on health in either run, so the change decided none of them, and the differences are those of two real-time replays, in which a tick sees a frame a few milliseconds earlier or later. Since no shot was fired, the confirmation was not tightened. What this does not show: at the console the turn does happen, and a false red that stays behind the map while the camera turns towards it would be aimed at and fired on once ahead. Most false reds here are background seen through the map, which a turn of the camera moves away, but that is not measured; the first live run should watch for it (the play log's `guard_start` rows with rule `red` and no enemy in the picture).

## The 55 scenes

First run, 22:23 to 23:09 on 12 November, with the code as described above (implementation `26ecdb1d…`), into a full ledger outside the repository:

```sh
env -u PS5_HOST .venv/bin/python tools/reaction.py run reflex pilot pilot+guard head head+guard --ledger <scratch>/main-full.jsonl --head-delay 8.4685 --head-delay-source "median of 20 Codex answers, ..."
```

Measured, before anything below was changed: with the guard both rows notice 18 of the 20 enemy onsets, none more than 0.053 s after the reflex row of P64 or this run; the two they miss, enemy-04 and enemy-05, are void because the figure's health is low throughout (the scene's note) and the guard's low-health flight holds the pad from 4.5 s before the onset. enemy-06 and enemy-09 are noticed within 0.08 s, enemy-05 is void. The five star onsets from calm are noticed within 0.106 to 0.150 s. No false notice and no false answer on the 29 calm scenes, and enemy-13 has none. The head row with the guard notices no more than 0.033 s after the pilot row with the guard, but answers 0.081 s and 0.074 s after it on wanted-02 and wanted-06. On enemy-19 and enemy-20 the guard's fight ended on its second tick with `health-depleted`: both scenes start as the HUD comes back after a black screen, and `Fight` read the bar fading in as empty, which the guard itself waits out for a second but did not hide from the skill.

Changed after it: until the HUD has been back for a second, the guard's rule and its skill see no health at all (`Guard._step`), and `test_a_fight_is_not_ended_by_a_bar_fading_in` fails without that. `guard.py` is not part of the bench's implementation hash, so the rows of `pilot+guard` and `head+guard` were run again, on the 55 scenes and on the eleven hard ones, three scenes at a time with the console checked before each piece, and replace the first run's guard rows in both ledgers. The rows of `reflex`, `pilot` and `head` and Kerim's are the first run's. The second run over the 55 scenes was cut once, by a restart of the machine's session at calm-walk-16, and went on from the first scene without both rows into the same ledger.

```sh
env -u PS5_HOST .venv/bin/python tools/reaction.py run pilot+guard head+guard --only enemy-01 enemy-02 enemy-03 --ledger <scratch>/main-guard-2.jsonl --head-delay 8.4685 --head-delay-source "<as above>"   # and so on, three scenes at a time, 23:22 to 23:43
env -u PS5_HOST .venv/bin/python tools/reaction.py board
```

The board's rows (`lab/reaction/board.md`): noticed and answered on the 26 threat scenes, in milliseconds as median / ninth decile / worst, and the false notices and answers on all 55 (the reflex has 3 of its 11 false notices on calm scenes, every other row none):

| Way | Noticed within 3 s | Noticed | Answered within 3 s | Answered | False notices, false answers |
|---|---:|---|---:|---|---|
| reflex | 22 | 36.7 / 1344.0 / 1672.9 | 14 | 470.5 / 3073.6 / 3904.0 | 11, 0 |
| pilot | 9 | 10.3 / 815.0 / 1913.0 | 8 | 74.7 / 689.1 / 1979.8 | 2, 19 |
| pilot+guard | 23 | 62.4 / 123.7 / 175.7 | 13 | 125.8 / 3475.9 / 3911.4 | 3, 17 |
| head | 7 | 508.4 / 1310.7 / 2509.6 | 0 | none | 1, 0 |
| head+guard | 23 | 48.8 / 138.3 / 146.6 | 13 | 145.8 / 3200.7 / 3915.3 | 3, 12 |

Noticed and answered per threat scene, seconds after the onset; one number where both are the same, `void` where the way of control did the same thing in the two seconds before the onset, `none` where it did not within the scene. P64's reflex row is beside this run's for comparison:

| Scene | Reflex (P64) | Reflex | Pilot | Pilot+guard | Head | Head+guard |
|---|---:|---:|---:|---:|---:|---:|
| enemy-01 | 0.057 / none | 0.066 / none | none | 0.094 / none | none | 0.112 / none |
| enemy-02 | 0.074 / none | 0.107 / none | none | 0.108 / none | none | 0.120 / none |
| enemy-03 | 0.008 / none | 0.011 / none | none | 0.039 / none | none | 0.039 / none |
| wanted-02 | 0.006 | 0.004 | 0.006 / 0.070 | 0.123 / 0.090 | 0.509 / none | 0.111 |
| wanted-03 | void / 0.809 | void / 0.903 | 0.540 / none | void / 0.153 | 0.511 / none | void / 0.111 |
| enemy-04 | 0.036 / none | 0.041 / none | void | void | void / none | void |
| enemy-05 | 1.405 / 1.708 | 1.411 / 1.707 | none / void | void | none | void |
| enemy-06 | 1.671 / 3.904 | 1.673 / 3.904 | none | 0.074 / 3.911 | none | 0.083 / 3.915 |
| enemy-07 | 0.009 / 2.439 | 0.004 / 2.439 | none | 0.047 / 2.442 | none | 0.048 / 2.442 |
| enemy-08 | 0.038 / none | 0.037 / none | none | 0.100 / 3.256 | none | 0.076 / none |
| enemy-09 | 1.440 / 2.109 | 1.441 / 2.108 | none | 0.048 / 2.107 | 2.510 / none | 0.049 / 2.110 |
| enemy-10 | 0.003 / none | 0.004 / none | none | 0.039 / none | none | 0.041 / none |
| enemy-11 | 0.006 / none | 0.005 / none | none | 0.052 / none | none | 0.047 / none |
| enemy-12 | 0.004 | 0.007 | none | 0.043 | none | 0.054 |
| enemy-13 | void / 2.408 | void / 2.405 | void | 0.045 / 2.415 | none | 0.039 / 2.414 |
| enemy-14 | 0.008 / 1.541 | 0.006 / 1.541 | none | 0.060 / 1.553 | none | 0.043 / 1.538 |
| enemy-15 | 0.705 / none | 0.740 / none | 0.076 / 0.136 | 0.038 / none | none | 0.044 / none |
| enemy-16 | 0.706 / none | 0.703 / none | 0.007 / 0.070 | 0.039 / none | none | 0.041 / none |
| enemy-17 | 0.006 | 0.007 | 1.913 / 1.980 | 0.062 | none | 0.039 |
| enemy-18 | 0.037 | 0.038 | none | 0.042 | none | 0.043 |
| enemy-19 | 0.038 / none | 0.037 / none | none | 0.077 / none | none | 0.074 / none |
| enemy-20 | 0.038 / 3.705 | 0.036 / 3.709 | none | 0.087 / 3.696 | none | 0.046 / 3.706 |
| wanted-04 | 0.008 | 0.005 | 0.010 / 0.075 | 0.142 / 0.079 | 0.505 / none | 0.122 |
| wanted-05 | 0.008 | 0.007 | 0.006 / 0.075 | 0.115 / 0.080 | 0.508 / none | 0.147 |
| wanted-06 | 0.005 | void / 0.007 | 0.012 / 0.076 | 0.176 / 0.098 | 0.507 / none | 0.146 |
| wanted-07 | void / 0.008 | void / 0.003 | 0.008 / 0.072 | 0.124 / 0.074 | 0.507 / none | 0.142 |

What the guard did on them (`seen` is the first tick its signal was read, `at` the tick it took the pad or told the head; turn, aim, fire and sprint count ticks of the episode):

| Scene | Pilot+guard | Head+guard |
|---|---|---|
| enemy-01 | red fight at +0.09, seen +0.05, to the end (turn 118 of 118 ticks) | red fight at +0.10, seen +0.07, to the end (turn 116 of 117 ticks) |
| enemy-02 | red: told the head (vehicle) at +0.10 | red: told the head (vehicle) at +0.10 |
| enemy-03 | red fight at +0.03, seen +0.00, to the end (turn 60 of 119 ticks) | red fight at +0.03, seen +0.00, to the end (turn 60 of 119 ticks) |
| wanted-02 | stars flee at +0.12, seen +0.02, 0.07 s (sprint 2 of 2 ticks), head plan started | stars flee at +0.11, seen +0.00, to the end (sprint 60 of 117 ticks) |
| wanted-03 | red fight at -5.80, seen -5.83, 5.93 s (aim 4, turn 165 of 178 ticks), stars took over; stars flee at +0.14, seen +0.00, 0.07 s (sprint 2 of 2 ticks), head plan started | red fight at -5.80, seen -5.83, 5.90 s (aim 4, turn 165 of 177 ticks), stars took over; stars flee at +0.10, seen +0.00, to the end (sprint 59 of 117 ticks) |
| enemy-04 | low_health flee at -4.50, seen -5.00, 4.00 s (sprint 61 of 120 ticks), time; red_edge: told the head (moving) at +2.23 | low_health flee at -4.46, seen -5.00, 4.03 s (sprint 59 of 121 ticks), time; red fight at +2.10, seen +2.04, 1.03 s (turn 4 of 31 ticks), low_health is left to the head |
| enemy-05 | low_health flee at -4.47, seen -4.97, 4.03 s (sprint 57 of 121 ticks), time; red fight at +2.63, seen +2.56, to the end (turn 35 of 42 ticks) | low_health flee at -4.46, seen -5.00, 4.03 s (sprint 58 of 121 ticks), time; red fight at +2.64, seen +2.57, to the end (turn 32 of 41 ticks) |
| enemy-06 | red_edge: told the head (moving) at +0.07; red fight at +2.54, seen +2.50, to the end (aim 3, turn 40 of 44 ticks) | red_edge turn at +0.07, seen +0.04, 2.46 s (turn 58 of 74 ticks), red took over; red fight at +2.53, seen +2.50, to the end (aim 3, turn 40 of 44 ticks) |
| enemy-07 | red fight at +0.03, seen +0.00, to the end (aim 44, fire 17, turn 71 of 119 ticks) | red fight at +0.04, seen +0.00, to the end (aim 44, fire 17, turn 71 of 119 ticks) |
| enemy-08 | red fight at +0.09, seen +0.05, to the end (aim 4, turn 110 of 118 ticks) | red fight at +0.07, seen +0.03, to the end (turn 116 of 118 ticks) |
| enemy-09 | red_edge turn at +0.04, seen +0.00, 1.43 s (turn 36 of 43 ticks), red took over; red fight at +1.47, seen +1.43, to the end (aim 11, fire 1, turn 65 of 76 ticks) | red_edge turn at +0.04, seen +0.00, 1.43 s (turn 36 of 43 ticks), red took over; red fight at +1.47, seen +1.44, to the end (aim 11, fire 1, turn 65 of 76 ticks) |
| enemy-10 | red fight at +0.03, seen +0.00, to the end (turn 118 of 119 ticks) | red fight at +0.03, seen +0.00, to the end (turn 117 of 119 ticks) |
| enemy-11 | red fight at +0.05, seen +0.01, to the end (turn 57 of 119 ticks) | red fight at +0.04, seen +0.00, to the end (turn 58 of 119 ticks) |
| enemy-12 | red fight at +0.04, seen +0.00, to the end (aim 93, fire 35 of 119 ticks) | red fight at +0.04, seen +0.01, to the end (aim 93, fire 34 of 119 ticks) |
| enemy-13 | red fight at +0.04, seen +0.00, 3.90 s (aim 3, turn 93 of 117 ticks), screen | red fight at +0.03, seen +0.00, 3.90 s (aim 3, turn 93 of 117 ticks), screen |
| enemy-14 | red fight at +0.05, seen +0.02, to the end (aim 6, turn 94 of 119 ticks) | red fight at +0.04, seen +0.00, to the end (aim 4, turn 95 of 119 ticks) |
| enemy-15 | red_edge turn at +0.03, seen +0.00, 0.73 s (turn 11 of 22 ticks), red took over; red fight at +0.77, seen +0.73, 0.07 s (turn 2 of 2 ticks), vehicle; red: told the head (vehicle) at +0.84; red_edge: told the head (vehicle) at +1.40 | red_edge turn at +0.04, seen +0.00, 0.70 s (turn 10 of 21 ticks), red took over; red fight at +0.73, seen +0.70, 0.10 s (turn 3 of 3 ticks), vehicle; red: told the head (vehicle) at +0.84; red_edge: told the head (vehicle) at +1.40 |
| enemy-16 | red_edge turn at +0.03, seen +0.00, 0.70 s (turn 11 of 21 ticks), vehicle; red: told the head (vehicle) at +0.74 | red_edge turn at +0.04, seen +0.00, 0.70 s (turn 11 of 21 ticks), vehicle; red: told the head (vehicle) at +0.74 |
| enemy-17 | red fight at +0.06, seen +0.02, 3.76 s (aim 36, fire 9, turn 71 of 113 ticks), vehicle; red_edge: told the head (vehicle) at +3.82 | red fight at +0.03, seen +0.00, 3.77 s (aim 37, fire 12, turn 65 of 113 ticks), vehicle; red_edge: told the head (vehicle) at +3.81 |
| enemy-18 | red fight at +0.04, seen +0.00, 0.90 s (aim 7, turn 19 of 27 ticks), vehicle; red: told the head (vehicle) at +0.93 | red fight at +0.04, seen +0.00, 0.90 s (aim 7, turn 19 of 27 ticks), vehicle; red: told the head (vehicle) at +0.94 |
| enemy-19 | red fight at +0.07, seen +0.03, to the end (turn 101 of 118 ticks) | red fight at +0.07, seen +0.04, to the end (turn 102 of 118 ticks) |
| enemy-20 | red fight at +0.08, seen +0.02, to the end (aim 10, turn 89 of 118 ticks) | red fight at +0.04, seen +0.00, to the end (aim 9, turn 93 of 119 ticks) |
| wanted-04 | stars flee at +0.14, seen +0.01, 0.07 s (sprint 2 of 2 ticks), head plan started | stars flee at +0.11, seen +0.00, to the end (sprint 57 of 117 ticks) |
| wanted-05 | stars flee at +0.11, seen +0.01, 0.06 s (sprint 2 of 2 ticks), head plan started | stars flee at +0.13, seen +0.00, to the end (sprint 61 of 116 ticks) |
| wanted-06 | stars flee at +0.16, seen +0.02, 0.07 s (sprint 2 of 2 ticks), head plan started | stars flee at +0.14, seen +0.01, to the end (sprint 58 of 116 ticks) |
| wanted-07 | stars flee at +0.11, seen +0.00, 0.06 s (sprint 2 of 2 ticks), head plan started | stars flee at +0.14, seen +0.00, to the end (sprint 60 of 116 ticks) |

The calm scenes: no false notice and no false answer in either guard row, and the guard did not start once on any of the 29. The false answers on threat scenes are all in the two seconds before the onset of enemy-04 and enemy-05 (9 and 8 with the pilot, 6 and 6 with the head): the sprint of the guard's low-health flight, the health bar being red throughout both. The three false notices are those two flights and the fight against the red markers of the shootout before wanted-03's stars light up, which the scene file marks as not from calm. Shots were fired on enemy-07, 09, 12 and 17 only, the scenes where a real marker comes within 5 degrees ahead, and never while stars were lit. The change made after the first run did what it was for: on enemy-19 and enemy-20 the fight now lasts to the end of the scene, and on enemy-20 it aims on 9 and 10 ticks and answers at 3.70 s, where the reflex answers at 3.71 s.

What the answered times do not say: in a replay the camera never turns, so `Fight` aims only where a marker happens to be within 5 degrees ahead already, and most enemy onsets end with a turn of the right stick and no answer from the answer set. How long from the marker to the first aimed shot at the console is not measured here.

One thing the next person should know about stars with the pilot's own rules behind the guard: those rules have already put their escape in the runner at 0.07 to 0.10 s when the guard's stars rule counts, and the guard still takes the pad, stops that plan and flees for two ticks until the rules' next plan starts (the `head plan started` endings above). It costs two ticks of the same sprint and nothing else on the bench, and a stars rule that does not start when the head's plan was put in after the first star reading would avoid it; it was left as the card describes it.

## The bars of the card

Every enemy onset the reflex notices, none more than two ticks later: holds on 17 of the 19 the reflex notices (all but enemy-13, void for the reflex), the latest 0.063 s after this run's reflex row and 0.062 s after P64's (both pilot+guard on enemy-08), two ticks being 0.067 s. It does not hold on enemy-04 and enemy-05: both are void for both guard rows. Health is low throughout both scenes, so the low-health rule, which outranks a marker, flees from 4.5 s before the onset into the two seconds before it, and once it has let go after four seconds the threat is the head's low-health rules' and nothing of lower rank starts while the bar stays low; a marker is answered only from +2.1 s and +2.6 s, once the low-health rule stops counting for a moment. The card's ranks and this bar disagree on a figure that is hurt when an enemy shows; the ranks were kept.

The three onsets with a marker on the edge within 0.2 s: enemy-06 (0.074 s with the pilot, 0.083 s with the head) and enemy-09 (0.048 s, 0.049 s) hold. enemy-05 does not, for the reason above. With the pilot on enemy-06 the guard only tells the head, because the pilot's plan is walking; with the standing head it turns.

Every star onset from calm within 0.2 s: holds. wanted-02, 04, 05, 06 and 07 are noticed after 0.115 to 0.176 s with the pilot and 0.111 to 0.147 s with the head, and answered after 0.074 to 0.098 s and 0.111 to 0.147 s. wanted-03 is not from calm.

The head row with the guard no more than two ticks behind the pilot row with the guard: holds for the notice on every scene (at most 0.032 s behind, wanted-05). For the answer it does not hold on two scenes. On wanted-07 the head row answers 0.068 s after the pilot row, a millisecond over two ticks (in the first run wanted-02 and wanted-06, 0.081 s and 0.074 s): with the pilot the first answer to stars is not the guard's but the pilot's own rules', which answer at 0.07 to 0.10 s, before the guard's two readings 0.1 s apart count; the head row answers on the guard's tick. Nothing waits behind the head there, the pilot is simply faster than the guard's confirmation. On enemy-08 the pilot row aims on 4 ticks at the end of the scene (answered 3.26 s) and the head row does not aim at all; both fight the same marker from +0.07 to +0.09 s, and whether a replay that never turns brings it within 5 degrees in the last second differs from run to run (in the first run neither row aimed).

No false answer or false notice on the 29 calm scenes: holds for both rows, in both runs. The false flight before enemy-13 is gone: holds, no false answer and no void there for either guard row, where the pilot without a guard has 3 false answers and is void.

The hard calm scenes: the report says on how many the guard starts, for how long and what it puts on the pad (above), and no shot was fired or aimed on any of them in either run, so the confirmation was not tightened.

The tests and ruff: `env -u PS5_HOST .venv/bin/python -m pytest tests/test_guard.py tests/test_reaction.py -q` gives `42 passed in 2.80s`, and `ruff check .` and `ruff format --check .` pass in `pilot/`. `tests/test_conductor.py` and `tests/test_mission.py` were run as well after the change, `366 passed in 1.67s`; the full gate was not run. The tests the card names are in `test_guard.py`: the order of the ranks, one odd tick, no shot while stars are lit, silence on a screen and in mode none, nothing on the pad in a vehicle, the start voiding a head answer that arrives afterwards, the neutral pad on the tick it lets go, and a conductor without a guard.

## What the rules leave out

A hit without a marker is not answered: the HUD reader reads a fall of health whenever an icon crosses the bar or the HUD fades in, so a falling bar is no signal until that reader is changed (the next card of the plan). Whether a weapon is in the hand is not known, no reader says so, and `Fight` assumes one as it does today. Nothing is answered with a pad in a vehicle; the guard only tells the head there. The judge's second opinion on a marker, asked on a crop of the map, is a later card. From the readers the guard would want two things it does not have: a flag on a red blip that says the reader saw it as a marker's shape rather than a red area behind the map (the hard scenes), and the health bar's own fade-in, which the guard now waits out with a fixed second.

## The board, the hash and the size of lab/reaction

The bench's implementation hash covers `reaction.py`, `approaches.py` and `tools/reaction.py`, which this card had to change, so it changed from P64's `7f28da3db54e8dfc56b57906b7d3e873c847f4e918eb46ed9d18d68fb8006d34` to `26ecdb1d5decf7c08921e474a7c1759df348ab198e5bf142eb0453b2eacc9992`. The cheap rows (`reflex`, `pilot`, `head`) were run again under the new hash with the guard rows. The rows that ask the gaming PC's model, `judge`, `judge-second`, `reflex+judge` and `policy`, were not run (the card does not need the PC) and are no longer on the board; P64's numbers for them stand in its report and in `ledger-p64.jsonl.gz`. They come back on the board when they are run again under the new hash with the P64 commands and the model server, or by showing P64's board from the archive (`lab/reaction/README.md`).

P64's ledger moved byte for byte into `lab/reaction/ledger-p64.jsonl.gz` (159,681 bytes instead of 1,803,488), and `ledger.jsonl` starts again with this card's rows. What was slimmed: in the rows of `pilot`, `pilot+guard`, `head` and `head+guard`, here and in `ledger-hard.jsonl`, the conductor's trace (`chain`, every event, head answer and plan with its time) is kept as a count per stage, `chain_summary`, and the row says so under `slimmed`. Nothing the board reads was slimmed. The full rows are kept outside the repository for the review. `board` and `board --scenes ../lab/reaction/scenes-hard.json --ledger ../lab/reaction/ledger-hard.jsonl` were run on the final ledgers; `lab/reaction/` holds 4,396,625 bytes, `ledger.jsonl` 1,071,365 of them.
