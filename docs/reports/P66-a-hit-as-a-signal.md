# P66: a health bar read as it is, and a hit as a signal

The hit signal was never wrong on the frames it was measured on: no signal in the 29 calm scenes, none in the six seconds before the 26 onsets (the old reader would have given three there), none on the eleven false falls the reaction bench named, and the 61 further signals in 123 fight stretches all show the bar shorter on the frames after them. It signals 44 of 47 real hits within six ticks of the first frame on which the bar is visibly shorter, 42 of them two ticks after it (0.07 s at 30 ticks a second, the third of three agreeing readings) and two after three; the three it does not signal in time lose three or four columns of the track's 90, under its threshold of four. A rule for a hit without a marker can rest on this signal for the fact of the hit. For its direction the game does draw something: a red half-disc near the edge of the picture on the attacker's side, seen in 16 of 24 hits looked at but not in brawls, and the minimap flashes red at every hit. Nothing reads either yet, so today the direction can only come from the people the object detector sees.

## Where the bars stand

No hit is signalled in the calm scenes or before the onsets: holds, 0 and 0. The reflex's one-frame test still finds one fall in one calm scene and three in three onset windows with the new reader (single frames the signal stands out), against six in four and sixteen in five with the old one. On the frames of a fading HUD the reader returns no health, not 0.0: holds; of 58563 frames the old reader read health under 0.1 on 151 and the new one on none, and on the eight fades in the windows it returns nothing or the bar's true level (enemy-15 and enemy-16 fade in at their onsets, after the counted six seconds, and give no signal in the 1.5 s read after them either). At least 18 of 20 real hits within six ticks: holds, 44 of 47, the misses named under "How it was measured". The reader's time per frame has not grown by more than a tenth: holds, 0.424 ms against 0.396 ms, 7 per cent. `pytest tests/test_hud.py tests/test_hits.py` and ruff pass, with tests on the fixtures for every kind of false fall, for the real hits, for ticks without a value and for the first second after the HUD returns.

What does not hold in full: the card wants the reader to stay right where it was right, and on P15's 73 labelled health frames it is within 0.05 on 66 against the old reader's 68. It abstains on four frames the old one read correctly (wifi-06611, wifi-06636, wifi-11128 and clean1-07402: a bright background behind the empty track makes the end a slow ramp, or a step no larger than the one a darker background makes inside the fill) and is right on two the old one got wrong (wifi-03248, where it read 0.0, and wifi-06660). Where it reads, its mean error is 0.006 against 0.021, and P15's own evaluation still passes. One assertion of `test_hud.py` was changed, for wifi-02869 (see "Tests"). The new reader reads health on 46245 of the 58563 frames, the old one on 47975. It can still read a bar too long: on four frames of enemy-17 white stripes of light behind the empty track make a bar at 0.51 read 0.66 to 0.74; the signal stands them out, but a lit stretch that lasted longer than about 0.75 s would become its level. The special bar still reads 0.0 on one to three frames late in a fade, where the health fill is no longer dim enough to blank the band.

Files: `pilot/src/pilot/hud.py` (the health reader `_health` and its use in `_bars`), `pilot/src/pilot/hits.py` and `pilot/tests/test_hits.py` (new), `pilot/tests/test_hud.py`, `lab/health/` (`cases.json`, 58 strip images, `cut.py`, `measure.py`, 1.93 MB) and this report. Nothing else was changed. A reviewer should look first at the rule for a full bar at the end of `_health` (it decides most false full readings and most lost readings), then at the changed wifi-02869 test, then at `Hits.update`.

## How it was measured

From `pilot/`, with the old reader saved from git (`git show 974d9a0:pilot/src/pilot/hud.py > /tmp/hud_old.py`):

```
env -u PS5_HOST .venv/bin/python ../lab/health/measure.py run out.jsonl --part K/8 --old /tmp/hud_old.py   # K = 1..8, 11 s each
env -u PS5_HOST .venv/bin/python ../lab/health/measure.py summary out.jsonl
stretches 174 frames 58563
[new] health read on 46245 frames, under 0.1 on 0
[old] health read on 47975 frames, under 0.1 on 151
[new] real hits signalled within six ticks: 44 of 47; delays [2 x 42, 3, 3, 14, 25]
  late by 25 ticks hit-164039-40903 a hit in a fight, 0.99 to 0.96; 2 red markers on the map; three columns
  late by 14 ticks hit-185323-46473 a hit in a fight, 0.52 to 0.49; 4 red markers on the map; three columns
  missed hit-190825-4744 a hit in a fight, 0.41 to 0.37; 4 red markers on the map; four columns
[new] hit signals in the 29 calm scenes: 0 []
[new] hit signals in the six seconds before the 26 onsets: 0 []
[new] one-frame falls: calm 1 in 1 scenes, before onsets 3 in 3 scenes
[new] enemy-17-after: []
[new] p62-hit-01: []
[new] p62-hit-02: [(211.795, 0.8, 0.622)]
[new] p62-hit-03: [(567.569, 0.989, 0.933)]
[new] signals in the fight stretches that match no labelled hit: 61, 51 with the orange of a hit on the frames after; the others: (ten, listed)
[old] real hits signalled within six ticks: 10 of 47
[old] hit signals in the 29 calm scenes: 0 []
[old] hit signals in the six seconds before the 26 onsets: 3 [('enemy-18', 200.2305), ('enemy-18', 201.1715), ('wanted-07', 654.5133)]
[old] one-frame falls: calm 6 in 4 scenes, before onsets 16 in 5 scenes
env -u PS5_HOST .venv/bin/python ../lab/health/measure.py time --old /tmp/hud_old.py   # three runs
old: 35 frames, mean 0.3965 ms, median 0.3708 ms   new: mean 0.4238 ms, median 0.3902 ms   new / old 1.069
old: 35 frames, mean 0.3938 ms, median 0.3647 ms   new: mean 0.4237 ms, median 0.3910 ms   new / old 1.076
old: 35 frames, mean 0.3975 ms, median 0.3753 ms   new: mean 0.4251 ms, median 0.3886 ms   new / old 1.069
env -u PS5_HOST .venv/bin/python tools/evaluate_hud.py --output p15.json
health_labels 73, health_within_005 66, health_abstentions 7, health_mae_when_read 0.0056, passed true
(old reader, the first worker's run: 68, 3, 0.0211, passed true)
```

`measure.py run` decodes every native frame of the scene windows (seven seconds before each onset, the first second to let the signal settle, the other six counted; calm scenes to four seconds after), of 2.5 s before to 1.2 s after each labelled hit, of the 123 fight stretches and of the four extra windows in `cases.json`, merging windows that overlap. The frames a loop at 30 ticks a second would read go through the reader, and a fresh `Hits` per stretch gets their readings. The "one-frame falls" are the reflex's own test from P62 and P64, one reading lower than the last by more than 0.03. The three hits not signalled in time: 164039-40903 and 185323-46473 lose three columns and are not signalled at all (the late signal is the next, larger hit 0.9 and 0.5 s later); 190825-4744 drops from 0.41 to 0.37, but the signal's level is the median 0.40 of readings that alternate between 0.40 and 0.41, so the step it sees is three columns. Timing runs `read` on the 35 full frames of `lab/hud/fixtures` and `pilot/tests/fixtures/screens`, old and new interleaved, 200 times each.

## The cases before any change

The false falls named by P62 and P64, with the old reader (`hud.read` as on `feat/pilot` at 974d9a0) run over every native frame of the bench's window; times are picture seconds of the recording.

| Case | Recording | What the old reader returns | What the frame shows |
|---|---|---|---|
| enemy-13, before the onset | 20261111-164039 | 0.00 on 12 frames from 626.347 to 626.588 (native 36360 to 36371), then 0.98 | the whole picture fading in from black after a cutscene; the bar is full and its green rises from 87 to 193 |
| wanted-07 | 20261111-200111 | 0.99, then 0.93, 0.89, 0.84, 0.79, 0.77, 0.73 and 0.71 on the frames 654.932 to 655.146 (native 39119 to 39132) | the N icon sliding from the bar's right end to 0.62 of it; the bar stays full, beyond the icon the fill is still there |
| calm-walk-13 | 20261111-175312 | 0.49, one frame of 0.42 at 730.054 (native 32893) | a damaged frame in front of bright sand: the fill is as long as before (to 0.53 on that frame), but the reader's surround correction pulls its brightness under the fixed threshold |
| calm-walk-20 | 20261111-205309 | 0.66 and 0.67, one frame of 0.63 at 105.200 (native 6302) | the running-figure icon sitting on the bar's end at 0.66 |
| enemy-15, at the onset | 20261111-201615 | 0.00 on 21 frames from 539.944 to 540.281, then 0.99 | the HUD fading in after a black screen; the bar is full |
| enemy-16, at the onset | 20261111-201615 | 0.00 on 22 frames from 621.694 to 622.053, then 0.99 | the same |
| calm-walk-26 | 20261111-213150 | 0.57 on four frames from 158.65 s, and 0.79 sliding to 0.56 from 159.60 to 159.69 s, over a bar at 0.80 | map icons passing over the bar, as P64 names them |
| enemy-17, 1.9 s after the onset | 20261112-090514 | 0.31 at 155.899, 0.38 to 0.42 at 156.08, 0.37 to 0.39 from 156.739 to 156.788, 0.51 between | white stripes of light behind the empty track of a bar at 0.51 |
| P62's hit-01 | 20261111-190825 | 0.62 falling to 0.46 from 396.36 to 396.41 s | the N icon over the bar's end at a camera cut (P64) |
| P62's hit-02 | 20261111-065022 | 0.74 to 0.66 from 210.26 to 210.30 s and 0.77 to 0.63 from 210.83 to 210.90 s, over a bar at 0.80 | the bar keeps its length; the real hit to 0.62 comes at 211.78 s |
| P62's hit-03 | 20261112-092019 | 0.70 at 564.83 s and 0.78 from 565.10 to 565.13 s, over a full bar | a full bar in front of bright sand |
| 20261111-065022, a real hit at 199.684 | 20261111-065022 | 0.99, then no value for 20 frames (199.684 to 199.981), then 0.80 | the first hit of a fight: for a third of a second the game draws the fill pale yellow and the lost part orange, fading to the empty track's dark green; the old reader calls none of it green |

## Taking over

The first worker's session was cut after the reader and the signal were written and measured once; no fixtures were kept. Its claims were checked on freshly decoded frames before anything was built on them: calm-walk-20 native 6302 reads 0.633 with the old reader and none with the new one, the hit in 065022 at 199.684 (native 11963) reads none with the old reader and 0.800 with the new one from its first frame, enemy-13 native 36360 to 36371 read 0.000 with the old reader and none with the new one, and wanted-07 native 39119 to 39132 fall from 0.933 to 0.711 with the old reader while the new one reads 0.989 or none. All four agree with the table above.

State as taken over, measured on the cached HUD strips of 67019 native frames (the scenes, 123 fight stretches and 47 hand-labelled hits): no hit signal in the 29 calm scenes or in the six seconds before the 26 onsets, 44 of 47 labelled hits signalled within six ticks, `test_hud.py` one failure (wifi-02869 reads 0.40 where the test wants none) and ruff seven findings. On P15's labelled frames the new reader had 64 of 73 within 0.05 against the old one's 68, with nine abstentions: six of them frames the old reader got right, all with a bright background behind the empty track or a Wi-Fi blurred end. Looking further, the new reader read a full bar on a bar at 0.93 whenever the empty part was short and lit by sand behind it (092019 from 569.6 s on), because its rule for a track of one level left out the four darkest columns, which were the whole empty part.

## The reader, step by step after taking over

Each change below was measured with the same run over the HUD strips the first worker had cut into its scratch folder (the scenes, the fight stretches and the labelled hits, 67019 frames counted per window, so frames in two windows twice; ticks at 30 Hz) and over P15's 73 labelled health frames, eleven seconds a run. The final numbers above come from `lab/health/measure.py`, which decodes the recordings again and reads overlapping windows once.

The rule for a track of one level now looks at the columns by position and leaves out only the first four, and it also wants the last four columns as bright as the track's median within a third of `HEALTH_FLAT`. The false full readings on the bar at 0.93 in 092019 and on the bar at 0.94 behind the N in wanted-05 are gone, and with them two of the reflex's three one-frame falls in wanted-05. The sharpness test spans three columns before and two after the end instead of two and one, since a Wi-Fi frame blurs an end over four columns (wifi-03060 reads 0.40 again, labelled 0.43). Columns beyond the end count as wrong only when they are within a quarter of the step of the fill, so a background that lightens towards the far right of the empty track no longer voids an end that is sharp (clean2-00345 reads 0.56, labelled 0.55). With these P15's frames give 66 of 73 within 0.05, against 68 for the old reader and 64 as taken over. A wider empty share (0.86 instead of 0.85) would have brought wifi-11128 back as well, but it made the new reader read 0.61 on one frame of a full bar in enemy-18, so it stays at 0.85.

The 63 signals in the fight stretches that match none of the 47 labelled hits in that run (61 in the final one) were checked: 51 have the orange the game paints over the lost part on the frames right after them, and the other twelve were looked at on the strips. All twelve show the bar shorter after than before; four are on a red bar at low health, where no orange is drawn, and the rest show the pale yellow fill and an orange patch narrower than three columns or a step before the orange shows. One of them is in P62's hit-03 window: the bar is full against sand until 567.43 s and 0.93 from 567.55 s on, behind the weapon wheel, two and a half seconds after P62's false onset at 565.10.

`_health` also says when the track is green but dim as a whole, and then `_bars` returns no health, armour or special: while the HUD fades in, the armour and special tracks read 0.0 too (the special bar reads 0.0 on enemy-15's fade and 1.0 after it). Over the 67019 frames the old reader read under 0.1 on 148 frames and the new one on none. On the 134 frames of eight fades (enemy-11, 12, 13, 15, 16, 19, 20 and 130333 at 1677 s) that the old reader read as 0.0, the new one returns none on 101 and the full or true level on the other 33, the late frames of each fade where the fill is bright again. The 114 frames flagged dim are those fades and two scenes (enemy-01 at 408.7 s, calm-walk-17 at 766.0 s) where a brown picture with no HUD at all covers the corner. None of the counts above changed with this rule.

## The fixtures

`lab/health/` holds 58 cases, 926 frames, 1.93 MB with its two scripts: 47 real hits and the eleven false falls named above (three fades, three icons, the sand frame, enemy-17's stripes and P62's three hit scenes). Each `<name>.png` stacks the 13 by 180 pixel HUD strip (rows 670 to 682, columns 64 to 243, all that `_bars` looks at) of the frames a loop at 30 ticks a second reads in the case's window, and `cases.json` says for each case what it shows, its recording and window, the native index and capture time of every frame, and for a hit the first frame on which the bar is visibly shorter and the levels before and after. `lab/health/cut.py` cuts them again from the recordings (`cd pilot && .venv/bin/python ../lab/health/cut.py`, 7 s). A hit's window is 0.2 s before the first shorter frame to 0.35 s after it; a fade's runs from the last black frame to 1.3 to 1.5 s after the HUD is back.

The 47 hits were found by the first worker from the 10 Hz labels of Kerim's recordings (a step of 0.06 or more between two calm stretches of readings during aiming, firing, melee or cover) and placed on the native frames by looking at them; I looked again at three of them frame by frame (065022 native 11963, 164039 native 36895 and 205309 native 20037: on each the frame before shows the old length and the named frame the new one, with the pale yellow fill and the orange lost part). They come from ten recordings, run from 0.99 down to a red bar at 0.24, and 43 have one to six red markers on the map in the two seconds before while four (201615 at 603.2, 603.7 and 604.9 s and 205309 at 334.5 s) have none. The first shorter frame of each is in `cases.json` under `first`; the list with levels and notes is in the table at the end of this report.

The fixture tests found one more false full reading: in hit 164039-40903, a three-column hit, the lost part fades from orange to a khaki as bright as the fill, and on two frames the reader called the bar full again. A full bar now also needs its last four columns as green as the rest of the track (green minus red within `HEALTH_TINT`, 20, of the track's median; a true full bar's last columns are 11 to 15 below it where the armour track's blue bleeds into them, the fading lost part 30 below). Coverage over the 67019 frames went from 54757 readings to 54221, against 55322 for the old reader; none of the other counts changed.

## Tests

`test_hud.py` reads the fixtures with `read` on a real game frame whose HUD strip is replaced by the fixture's: the three fades read no health or the full bar and never anything lower, a band dimmed to 45 per cent reads no health, armour or special, the icon cases and P62's three scenes read nothing or the true level within 0.03, the sand and stripes cases never read shorter than the level less 0.03, and on each of the 47 hits every reading before the first shorter frame is the level before, the new level is read on one of the first three frames from it, and no reading after it is as long as any before. The test that wanted wifi-02869 to abstain now wants 0.40: P15 left the frame unlabelled because a cyan streak of damage crosses the empty track, but the fill ends sharply left of it, and the 41 frames 2850 to 2890 of the recording read 0.40 or nothing with the new reader (0.38 to 0.42 with the old one). That is the one existing assertion changed; the marker occlusion half of the old test stays as it was.

`test_hits.py` feeds the readings of the fixtures, after two seconds of a settled level, to `Hits`: the 45 hits of four columns or more are signalled within six ticks of their first shorter frame with the new level within 0.03, the two of three columns are not, the two hits with frames without a value between the first shorter frame and the confirming one (065022-15123 and 185323-23660) are signalled through them, none of the eleven false falls gives a signal from a signal settled at the bar's true level, and on the three real fades nothing counts in the first second after the first frame with bars, after which the level is the full bar. With the old reader put back (`git show HEAD:pilot/src/pilot/hud.py`) 93 of the 247 tests in the two files fail, among them five of the eleven false falls and 33 of the 45 hits.

```
cd pilot && env -u PS5_HOST .venv/bin/python -m pytest tests/test_hud.py tests/test_hits.py -q
247 passed in 5.26s
.venv/bin/ruff check src/pilot/hud.py src/pilot/hits.py tests/test_hud.py tests/test_hits.py ../lab/health/
All checks passed!
.venv/bin/ruff format --check src/pilot/hud.py src/pilot/hits.py tests/test_hud.py tests/test_hits.py ../lab/health/*.py
6 files already formatted
```

## What else the game draws at a hit

Full frames of 24 of the 47 hits were looked at, six and ten frames after the first shorter one (sheets of twelve each, decoded from the recordings). Besides the shorter bar the game draws two things. The whole minimap flashes red, in all 24. And in 16 of them a red half-disc sits near the edge of the picture, on an ellipse around its centre, sometimes two or three at once: top left, left, top or top right. Where the attacker can be seen, the mark is on his side of the picture (205309 at 334.5 s: the man at the car door to the left, the mark at the left; 200111 at 102.7 s: a policeman to the right, the mark at the top right). The marks are missing in the two brawls (065022 at 199.7 and 251.5 s, fists) and in six other hits at the frames looked at; they may come later or not at all. This was looked at, not measured: how often a mark comes and how well its angle gives the attacker's bearing needs a reader and labels of its own. Neither is read by anything in the pilot yet.

## What the guard's rule needs from the signal

The rule is the reviewer's to wire once P65 is merged. It needs `Hits.update(capture_time, hud)` called on every fresh frame with the `Hud` the conductor already reads, also when `hud` is None or carries no bars, since the signal tells a screen without the HUD from a moment without a value by how long the bars stay away. `update` returns a `Hit` on the tick that confirms it, two ticks after the first shorter frame for 42 of the 47 labelled hits and three for two more; `since` is the capture time of that first frame, `before`, `after` and `drop` say how much was lost, and `level` is the health the signal holds meanwhile. The signal says nothing about the cause: a fall from a height, a crash or fire take health as a shot does, and only the 47 hits in fights were labelled, so the rule should want a hit together with the absence of a red marker and, until the marks above are read, take the direction from the people the object detector sees or turn to look. A drop of three columns or less is not signalled, by design.

## The 47 hits

The first frame on which the bar is visibly shorter, the levels before and after as read on the frames, the red markers on the map in the two seconds before (from the 10 Hz labels), and the ticks from that frame to the signal with each reader ("none": not signalled within a second).

| Recording | First shorter frame (native, s) | Before, after | Red markers | Ticks to the signal, new reader | Old reader | Note |
|---|---|---|---|---|---|---|
| 20261111-065022 | 11963, 199.684 | 0.99, 0.80 | 2 | 2 | 12 |  |
| 20261111-065022 | 12688, 211.780 | 0.80, 0.62 | 5 | 2 | 12 |  |
| 20261111-065022 | 15056, 251.470 | 0.62, 0.44 | 3 | 2 | none | sand behind the bar |
| 20261111-065022 | 15123, 252.589 | 0.46, 0.29 | 3 | 2 | none | washed-out bright frames before it |
| 20261111-164039 | 36895, 635.268 | 0.99, 0.91 | 2 | 2 | none |  |
| 20261111-164039 | 36913, 635.568 | 0.91, 0.82 | 2 | 2 | none |  |
| 20261111-164039 | 37522, 645.731 | 0.82, 0.74 | 1 | 2 | 8 |  |
| 20261111-164039 | 38346, 659.478 | 0.74, 0.66 | 1 | 2 | 5 |  |
| 20261111-164039 | 38816, 667.317 | 0.66, 0.58 | 1 | 2 | 6 |  |
| 20261111-164039 | 38837, 667.671 | 0.58, 0.49 | 1 | 2 | 7 |  |
| 20261111-164039 | 39084, 671.791 | 0.49, 0.40 | 1 | 2 | 7 |  |
| 20261111-164039 | 40903, 702.338 | 0.99, 0.96 | 2 | 25 | none | three columns |
| 20261111-164039 | 40956, 703.221 | 0.96, 0.88 | 2 | 2 | 8 |  |
| 20261111-175312 | 3564, 239.745 | 0.99, 0.62 | 3 | 2 | 11 | a red blip on the bar's start |
| 20261111-182316 | 18577, 311.450 | 0.93, 0.74 | 3 | 2 | 10 |  |
| 20261111-182316 | 25809, 432.556 | 0.99, 0.91 | 3 | 2 | 6 |  |
| 20261111-182316 | 26245, 439.746 | 0.91, 0.80 | 4 | 3 | 12 | two falls 50 ms apart, 0.89 first |
| 20261111-185323 | 22083, 369.267 | 0.97, 0.88 | 3 | 2 | 9 |  |
| 20261111-185323 | 22105, 369.635 | 0.88, 0.80 | 3 | 2 | none |  |
| 20261111-185323 | 23660, 395.663 | 0.32, 0.24 | 2 | 3 | 3 | red bar at low health |
| 20261111-185323 | 28102, 469.885 | 0.50, 0.31 | 6 | 2 | 8 | two falls inside one capture batch |
| 20261111-185323 | 28777, 481.064 | 0.50, 0.40 | 4 | 2 | 8 |  |
| 20261111-185323 | 32816, 548.526 | 0.96, 0.86 | 2 | 2 | 10 |  |
| 20261111-185323 | 46473, 777.205 | 0.52, 0.49 | 4 | 14 | none | three columns |
| 20261111-185323 | 46502, 777.691 | 0.49, 0.26 | 4 | 2 | 14 |  |
| 20261111-190825 | 4710, 79.085 | 0.50, 0.40 | 4 | 2 | 9 |  |
| 20261111-190825 | 4744, 79.653 | 0.41, 0.37 | 4 | none | 3 | four columns |
| 20261111-190825 | 51895, 888.896 | 0.99, 0.91 | 2 | 2 | 7 |  |
| 20261111-190825 | 51914, 889.200 | 0.91, 0.82 | 2 | 2 | none |  |
| 20261111-200111 | 6132, 102.672 | 0.70, 0.48 | 4 | 2 | 14 |  |
| 20261111-200111 | 6181, 103.454 | 0.48, 0.40 | 4 | 2 | 8 |  |
| 20261111-201615 | 26411, 442.732 | 0.99, 0.91 | 2 | 2 | 4 | the end under a red blip |
| 20261111-201615 | 28823, 483.099 | 0.34, 0.27 | 2 | 2 | 14 | bright sky behind the bar |
| 20261111-201615 | 29363, 492.115 | 0.41, 0.32 | 2 | 2 | none |  |
| 20261111-201615 | 31143, 521.894 | 0.50, 0.41 | 1 | 2 | 3 |  |
| 20261111-201615 | 31159, 522.116 | 0.41, 0.32 | 1 | 2 | 7 |  |
| 20261111-201615 | 35404, 593.302 | 0.99, 0.91 | 1 | 2 | 8 |  |
| 20261111-201615 | 35428, 593.724 | 0.90, 0.81 | 1 | 2 | none |  |
| 20261111-201615 | 35998, 603.225 | 0.81, 0.73 | 0 | 2 | 8 |  |
| 20261111-201615 | 36022, 603.682 | 0.73, 0.64 | 0 | 2 | 6 |  |
| 20261111-201615 | 36100, 604.923 | 0.64, 0.51 | 0 | 2 | 7 |  |
| 20261111-201615 | 36124, 605.325 | 0.51, 0.39 | 1 | 2 | 7 |  |
| 20261111-201615 | 36182, 606.311 | 0.39, 0.31 | 1 | 2 | 6 |  |
| 20261111-205309 | 20037, 334.528 | 0.46, 0.27 | 0 | 2 | 11 | the running-figure icon beside the end |
| 20261112-085011 | 6032, 100.730 | 0.99, 0.92 | 3 | 2 | 9 |  |
| 20261112-085011 | 6072, 101.370 | 0.92, 0.86 | 3 | 2 | 6 |  |
| 20261112-085011 | 9952, 166.256 | 0.99, 0.92 | 2 | 2 | 8 |  |
