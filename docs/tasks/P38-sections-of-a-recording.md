# P38: Sections of a recording

## Why

Kerim plays GTA V himself with the recorder running, so that the pilot can learn from what he does; the plan calls this the launch-day workflow and wants its frames labelled automatically. On the afternoon of 11 November he played 53 minutes over Wi-Fi with his controller on the Mac: `/Users/kerim/recordings/kerim/20261111-164039`, `20261111-165543`, `20261111-171046` and `20261111-172549`, fifteen minutes each and eight for the last, every folder with `video.mp4`, `frames.jsonl`, `pad.jsonl` and `meta.json`. Nobody knows what is in such a folder without watching it: every analysis so far picked its seconds by hand from contact sheets. Notes on missions (P39), his driving as the measure for the driver (P40), pictures of the screens after a mission and a data set for a model that learns to drive all start with the same question: from when to when does a recording show what.

Read `PLAN.md`, in `docs/LOG.md` the entries of 11 November (the midday entry says why the minimap alone cannot tell on foot from in a vehicle), `pilot/src/pilot/loop.py` (`Pipeline`), `hud.py`, `minimap.py`, `replay.py`, and `lab/judge/README.md` with `lab/judge/sample.json` and `truth.json`.

## What to build

A module `pilot/src/pilot/sections.py` and a command `pilot/tools/sections.py <recording>... --out DIR` that runs the readers the pilot already has over a recording and writes `DIR/<recording name>/sections.json` and a contact sheet `sections.jpg` with one frame from the middle of every section, its kind and its times.

A section is a stretch of at least one second of one kind: `drive` (the figure sits in a vehicle), `foot`, `cutscene` (the game plays without its HUD), `menu` (pause menu, map, interaction menu, phone, weapon wheel; the class the screen reader gives goes into `screen`), `banner` (mission passed or failed, dead, arrested), `loading` and `unknown`. This file is the contract for P39 and P40, which are built at the same time, so keep exactly these fields:

```json
{
  "recording": "/Users/kerim/recordings/kerim/20261111-164039",
  "seconds": 901.5,
  "sample_hz": 10,
  "has_pad": true,
  "sections": [
    {"start": 0.0, "end": 14.9, "first_frame": 0, "last_frame": 893, "kind": "foot", "screen": "game",
     "wanted": 0, "route": [], "damaged": 0.02, "human": 0.61, "route_share": null, "speed": null}
  ]
}
```

`start` and `end` are seconds on the clock of `frames.jsonl`, `wanted` the highest level read in the section, `route` the colours of route seen on the minimap, `damaged` the share of sampled frames the minimap reader called damaged, `human` the share of the section in which the controller reported anything but neutral (null without a controller), `route_share` and `speed` the share of a drive with a route and its mean speed in metres a second where the game prints a distance.

How the figure moves is the hard part. A flat minimap means on foot and a tilted one a vehicle, except that with stars the game tilts the map on foot as well, and the judge that gets this right is a model on another machine that you cannot reach. Use what is in the recording: the readers, the wanted level, and the controller where there is one, since a held R2 or L2 with a steering stick is a car and a pushed stick with Cross is a run. Where the evidence does not decide, the section is `unknown` and not a guess. Take the decision through one function that can be replaced, so that the reviewer can hand in the judge's answers later.

A recording has to be read at about ten frames a second, by the times in `frames.jsonl` and never by an assumed frame rate; over Wi-Fi fewer than sixty frames a second arrive. One odd reading decides nothing: the minimap reader calls two or three frames in a hundred damaged and on foot calls the map a vehicle's for up to 0.83 s, so a change counts when it has lasted a second. `pad.jsonl` holds his controller only when it was on the Mac; a recording made with the controller on the console has one line there and is picture only, and both kinds have to work. An hour of recording has to be done in ten minutes in one process, without the object detector and without text recognition.

## Judging it

Run it over the four folders of the afternoon, over `/Users/kerim/recordings/kerim/20261111-065022` (375 s over the cable), `/Users/kerim/Documents/ChatGPT/gta/recordings/20261110-093238` (696 s over Wi-Fi, whose course `docs/tasks/README.md` describes), `/Users/kerim/recordings/pilot/20261110-231512` (240 s, on foot throughout) and `/Users/kerim/recordings/kerim/20261111-135510` (eighteen minutes of a standing car, picture only). For `20261111-164039` and `20261110-093238` write the true sections down by hand from contact sheets at one frame a second, in `lab/sections/truth.json`, before you look at what the tool says, and say in the report how you made them.

The targets: every true section of three seconds or more is found with its kind, its ends within two seconds; at most one section that is not there per five minutes; and for the frames of `lab/judge/truth.json` that come from these recordings, the kind at that time agrees with the hand label on nine of ten, `unknown` counted as a miss and listed apart. Give the numbers as they are.

Tests work on sequences of reader output, not on video, and pin: a flip of 0.8 s makes no section, damaged readings decide nothing, a recording without controller lines, times taken from `frames.jsonl` with gaps, neighbours of one kind merged, and the replaceable decision.

## Your files

`pilot/src/pilot/sections.py`, `pilot/tools/sections.py`, `pilot/tests/test_sections.py`, `lab/sections/` and your report. Not `hud.py`, `minimap.py`, `scene.py`, `flow.py`, `loop.py` or `replay.py`: where a reader costs you sections, show it in the report with frames. Nothing under `/Users/kerim/recordings/` or `recordings/` is written, moved or deleted; a folder whose `meta.json` has no `seconds` is still being recorded and is left alone. Write the output for the eight recordings to `lab/sections/out/`.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green, and the report shows for each recording the table of sections, for the two labelled ones next to the truth, the numbers against the targets, the minutes per kind over Kerim's 53 minutes, the time the tool took per minute of recording, and what a section's kind cannot be trusted for.
