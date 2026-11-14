# P104: The speed is known in town

## Why

The trip of P97 arrives in town now (six arrivals in the night of 14 November), and it is slow there for one reason more than any other: for a third of the drive the driver does not know how fast the car is. With no speed the speed law of P98 and P102 is not asked at all: `Driver._pedal` in `drive.py` returns `unknown_throttle` (0.18, a crawl) and calls the reason `unknown-speed`, whatever the road ahead is.

`/Users/kerim/recordings/pilot/20261114-024431`, the bold style, 1.66 km through the city in 221 s, arrived. Of 5408 ticks of `drive_route` 34 percent carry `gps_speed: null` in the reading of `play.jsonl`. Split by what the driver did, the drive's time goes like this: `follow` with `unknown-speed` 46 s at 3.8 m/s of route, `curve-exit` 49 s at 6.0, `curve` 48 s at 11.1, `visibility` 11 s at 13.3, `straight` 2 s. The stretches without a speed, with the reading before them: 29.6 s for 18.7 s (speed 0.3, 1500 m), 65.4 s for 11.6 s (12.7 m/s, 1120 m), 12.2 s for 7.5 s, 130.6 s for 5.0 s (17.6 m/s, 718 m), 189.2 s for 5.3 s, and a dozen shorter. In each of them `gps_distance` is null on 62 to 99 percent of the ticks: the speed is missing because the printed distance is not read. The print is there. At 32, 38, 44, 52, 68, 74, 118, 132, 191 and 199 s of the video the minimap shows "1.51km", "1.48km", "1.45km", "1.35km", "1.05km", "845m", "658m", "269m", "236m" in plain sight, most of them with a white road of the map behind the white digits.

The share differs from drive to drive, which is itself to be explained. Ticks of `drive_route` without a speed and without a distance: `20261114-015516` 66 and 59 percent, `20261114-005357` (Sandy Shores and the freeway into the city) 39 and 33, `20261114-024431` 34 and 30, `20261114-015901` 24 and 17, `20261114-014037` 14 and 10, `20261114-024817` 5 and 2. Where the print is read on the freeway the car is as fast as Kerim (`20261114-005357`, 400 to 520 s, 25 to 30 m/s).

I tried the obvious second source and it does not carry as it is: the map's motion between two crops 0.2 s apart (`motion.map_motion`, in px) against the speed from the print, over the whole of `024431`, gives a median of 2.7 px/s at 4 to 8 m/s, 4.4 at 12 to 16 and 7.3 at 16 to 20, with a p90 of 10 to 50 px/s in every band. The map zooms with the speed and turns with the car, and the measure does not take either out.

## What to do

Find out first, on the recordings, and write down: for every stretch of `024431` and `015901` without a distance, what the reader saw (`gps.py`: `Reader`, the crop it reads, what the text reader returned, why a reading was thrown away), and how the misses divide between a light road behind the digits, a route recalculation where the game prints nothing, a turn arrow or blip over the print, the consensus rules of `Speedometer` refusing readings that were right, and anything else. A print that is on the picture and not read is the reader's miss; a reading that is right and refused is the speedometer's.

Then make the speed known where a player sees it. In the order the evidence supports:

The print is read over a light road. Whatever recovers it on the frames you collected: the crop, a contrast step before the text reader, the digits' shadow, a second try with another preparation when the first returns nothing. Measured on a labelled set of frames from tonight's recordings that you build (the print's value by eye or from neighbouring readings), before and after, with the false readings counted as carefully as the misses: a wrong distance is worse than none.

The speedometer gives a speed sooner and keeps it longer where that is safe: say what it needs today before it gives one (samples, seconds), how long a car that accelerates from a standstill drives without a speed for that reason alone, and what can be relaxed without letting an OCR outlier through.

Where the print really is gone (the game prints nothing while it recalculates, a few seconds at most), a speed from the map's motion or from the last speed and the pedal since, if you can show on the recordings that its error stays within what the speed law tolerates; it must err to the fast side, since a speed read too low takes the car into a bend too fast. If you cannot show that, say so and leave it out.

Last, what the driver does with no speed at all: today a crawl whatever the road. Decide from the evidence whether the pedal there should follow the road ahead (a straight path allows more than a bend) and by how much, and prove in the simulator that it leaves no road it stays on today.

## Your files

`pilot/src/pilot/gps.py`; `pilot/src/pilot/motion.py` if you take a speed from the map's motion; in `pilot/src/pilot/loop.py` only `Pipeline.step` from the line `result = self.gps_reader.poll(...)` on (the method `_painted` and the lines above are being watched at the console tonight and stay as they are); in `pilot/src/pilot/drive.py` only the two early returns of `_pedal` for `unknown-path` and `unknown-speed` and the `DriveConfig` fields they read; `sim.py` where the simulator needs a sensor that abstains; new tests in `pilot/tests/test_speed_in_town.py`, existing tests only where a behaviour changes on purpose, each named in the report; frames you label and scripts with their output under `lab/gps/` with the prefix `p104`, small files only (crops of the minimap, not whole frames; the disk has 12 GB left); `docs/reports/P104-the-speed-is-known-in-town.md`. Not yours: the speed law itself (`_road_limit`, `_speed_limit`, `_map_scale`), the steering, `skills.py`, `errands.py`, `minimap.py`.

You work in `/private/tmp/gta-nearest-car` (branch `feat/pilot-speed-in-town`, from `4d7047f`; the environment is installed) and nowhere else. The rules of `docs/tasks/README.md` hold: no commit, no console, no `PS5_HOST`, nothing sent to `127.0.0.1:9395`. The pilot drives at the console all night on this machine and needs its tick rate: one process at a time with `nice -n 15`, the text reader over the frames you need and not over whole recordings (it takes 0.08 to 0.17 s a frame), the whole gate once at the end (`cd pilot && nice -n 15 .venv/bin/python tools/gate.py`; under this load it takes about 125 s and prints "default gate exceeded 90 seconds", which is known and not yours to fix). The reader must stay as cheap as it is in the live loop: one text reading in flight, none waited for; say what a tick costs before and after.

## Done when

The report has the table of the stretches without a distance, each with its cause and a frame.

On your labelled frames the print is read in a share you state, before and after, with the wrong readings counted, and the share of ticks with a speed over the drives of `024431` and `015901`, replayed through the reader and the speedometer, before and after. The replay runs the text reader at the live interval, not on every frame.

Tests that fail with the code as it is: a print over a light road (your crops) is read; an outlier among right readings still does not move the speed; and whatever you changed in the speedometer and the pedal, each by the behaviour that matters. The tests of P98, P102 and of the reader still pass, or the report says for each changed one what it asserted and why that is no longer wanted. The gate passes.

What the console has to show cannot be tried by you. Say in the report by which figures of `play.jsonl` the next town trips are to be judged: the share of drive ticks with `gps_speed`, the share of `unknown-speed`, and the metres of route per second where it was unknown before.
