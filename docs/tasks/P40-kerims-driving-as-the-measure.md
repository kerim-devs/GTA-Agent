# P40: Kerim's driving as the measure

## Why

The driver's limits were set on 11 November from three drives of its own: 22 m/s and 7 m/s² through a bend hold the road, 26 and 9 put the car on a parapet. How fast a bend can be taken, when to lift and when to brake is what Kerim shows whenever he drives with the recorder on and his controller on the Mac, because his stick, R2 and L2 are in `pad.jsonl` on the clock of the frames. On the afternoon of 11 November he played 53 minutes that way over Wi-Fi: `/Users/kerim/recordings/kerim/20261111-164039`, `20261111-165543`, `20261111-171046` and `20261111-172549`. `pilot/src/pilot/replay.py` already sets the driver's steering against his on a recording, but it was built on 10 November, before the driver planned its speed and before the live settings in `cli.LIVE`. The plan measures NitroGen by his direction on eight of ten clear steering moments, and our own driver has never been given that number.

Read `PLAN.md`, in `docs/LOG.md` the entries of 11 November from "The first drive to a waypoint" on, `pilot/src/pilot/drive.py`, `pilot/src/pilot/replay.py`, `pilot/src/pilot/cli.py` for `LIVE` and `MEASURED_DELAY_S`, and `lab/live/replay_drive.py`, which runs the driver again over the readings of a session with the live settings.

## What to build

A module `pilot/src/pilot/humandrive.py` and a command `pilot/tools/human_drive.py <recording>... --out DIR [--sections DIR]`. For every stretch in which he drives along a route on the minimap it takes, thirty times a second by the times in `frames.jsonl`, the reading of the minimap with its path and bearing, the speed where the game prints a distance, his controller at the moment his hand caused that picture, and the command the driver gives for the same reading with the live settings. The stretches come from the sections of P38 when `--sections` is given; P38 is built at the same time and its format is in `docs/tasks/P38-sections-of-a-recording.md`. Without it a stretch is a tilted minimap with a route and a controller that steers or holds a pedal.

His hand leads the picture: by about 0.14 s over the cable and by 0.6 to 1.1 s in the Wi-Fi recording of 10 November. Estimate the lead for each recording from the recording itself and print it. A recording without controller lines is named as such and skipped, never counted as a hand at rest.

It writes `drive.json` per recording and one `summary.md` over all of them with: the share of clear steering moments, his stick at 0.3 or more for 0.3 s, on which the driver steers the same way, and how hard against how hard; his speed against the curvature of the path ahead, so the sideways acceleration he drives through bends at the median and at nine in ten, and his speed on straights, each next to the limit the driver sets for the same reading; his pedals, the share at full R2, lifted and on L2, how long before a bend he lifts and whether he brakes at speed; the twenty moments at which the driver and he differ most, as contact sheets with both commands written on the frame; and the stretches he drives with no route on the minimap, with their times, because driving along a road without a route (P17) is parked for want of exactly that footage.

Propose values for `cli.LIVE` in the report with what supports them. Do not change `cli.py` or `drive.py`.

## Judging it

Run it over the four folders of the afternoon, over `/Users/kerim/recordings/kerim/20261111-065022` (375 s over the cable with his controller) and `/Users/kerim/Documents/ChatGPT/gta/recordings/20261110-093238` (Wi-Fi, drives along the yellow route from 228 s and the purple one after 395 s). As a check of the alignment run it over the pilot's own drive `/Users/kerim/recordings/pilot/20261111-134217`, taking the lines of `pad.jsonl` whose `src` is `agent` for the hand: the driver has to agree with itself on nearly every moment and the lead has to come out near the command delay. `/Users/kerim/recordings/kerim/20261111-132247` is picture only and has to be skipped with a line that says why.

Look at the twenty moments yourself and sort them in the report: he leaves the line on purpose, the reading is wrong, or the driver is wrong. Give the numbers as they are, and say how many seconds of driving along a route with a controller the recordings hold at all, since every number above stands on that.

Tests work on sequences of readings and controller lines, not on video, and pin: a known lead is found again within one tick, a recording without a hand gives no numbers, agreement is counted only on clear moments, and times come from `frames.jsonl` with gaps.

## Your files

`pilot/src/pilot/humandrive.py`, `pilot/tools/human_drive.py`, `pilot/tests/test_humandrive.py`, `lab/human-drive/` and your report. Not `drive.py`, `avoid.py`, `cli.py`, `replay.py` or `minimap.py`. The object detector is not run over whole recordings. Nothing under `/Users/kerim/recordings/` or `recordings/` is written, moved or deleted. Write the output to `lab/human-drive/out/`.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green, and the report shows the summary over all recordings, the check on the pilot's own drive, the twenty moments sorted by cause, and the values you propose.
