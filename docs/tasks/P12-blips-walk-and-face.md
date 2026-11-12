# P12: Blips on the map: walk to one, face one

## Why

On foot the agent is nearly blind. The head sees a picture every seven seconds at best and can only say "walk forward for two seconds" or "turn the camera by about forty degrees", both open-loop. But the game draws where things are on the minimap: a yellow disc for the destination, coloured dots for people and vehicles, letters for mission givers. A skill that walks towards one of those at 30 Hz, and one that turns the camera to one, would turn "get to the car", "go to the marker" and "aim at the enemy" from guesswork into something that closes its own loop. Read `docs/reports/P10-conductor-head-and-skills.md` and `P8-path-and-speed.md` first.

The idea rests on one assumption that you must check before building on it: the minimap turns with the camera, so "up" on the map is where the camera looks, and since the left stick moves the character relative to the camera, pushing the stick in the direction in which a blip lies on the map walks towards it. The long recording has minutes on foot with Kerim's stick in `pad.jsonl`; compare the direction of his stick with the direction in which the map moves. It was recorded over Wi-Fi, so the stick leads the picture by 0.6 to 1.1 s. If the assumption does not hold, say so and stop there; do not build the skills on it.

## What to build

The reader finds blips. `Reading` gets a new last field with a default, for instance `blips: tuple[Blip, ...] = ()`, each with a colour name, its position in map pixels relative to the arrow (x to the right, y up), and whether it sits on the border of the map, where the game pins things that are further away than the map shows. It works on the flat map and on the vehicle map. Find out from the recordings which blips occur and how they look; the crops in `lab/minimap/data/crops.npy` (2768 of them, with `meta.json`) are the material. Name only what you have seen. A blip is not a route: the yellow line, the yellow or purple route end, world colours shining through the translucent map, the player arrow, the north marker and the health bars must not be reported. The reader's speed and its results on the labelled splits must not get worse (the harness is `cd lab/minimap && /Users/kerim/Documents/ChatGPT/gta/lab/minimap/.venv/bin/python harness.py impl_pilot/minimap.py --split dev`, and `held`): no false route, every route found, under 3 ms on average with the blips.

Two skills in `skills.py`, known to the head through `head.py` and the prompt file.

`walk_to` takes a colour and a time limit and pushes the left stick towards the nearest blip of that colour. It is done when the blip is within a few pixels of the arrow, and it fails when the blip has been gone for two seconds or the time is up. When the map says the character has stopped moving while the stick is pushed, it sidesteps for a moment, alternating sides, and tries again; after a few such attempts it fails. It never sprints into something it cannot see: sprinting is an option the head sets.

`face` takes a colour and turns the camera with the right stick until the nearest blip of that colour is within about ten degrees of straight up on the map, with a bounded turn rate that slows as it gets close, and a time limit of five seconds. It reports whether it got there.

Both obey the rules of the other skills: a hard time limit, a complete pad state on every tick, nothing held when they end or are replaced, arguments clamped.

## Judging it

Label blips by eye on at least 80 crops, half flat and half vehicle maps, half of them with blips, picked at random with a fixed seed and saved with the labels under `lab/blips/` so the measurement can be repeated. Report, per colour, how many were found, missed and invented, and how far the found positions are from the labelled ones. Draw the found blips over a few enlarged crops and keep those sheets.

For the skills, a small simulation is enough: a walker on a plane with a camera-fixed map, a blip, walls, a delay of 0.14 s between command and picture, noise and dropouts in the blip. Show that `walk_to` arrives around a wall corner or gives up within its limits, and that `face` settles without swinging back and forth.

## Your files

`pilot/src/pilot/minimap.py`, `contract.py` (additions only), `skills.py`, `head.py`, `head_prompt.txt`, their tests and fixtures, `lab/blips/`, scripts under `pilot/tools/`, and your report. Not yours: `drive.py`, `sim.py`, `gps.py`, `scene.py`, `motion.py`, `loop.py`, `conductor.py`, `bridge.py`, `cli.py`, `replay.py`, everything under `remoteplay/`. If the skills need something the observation of a tick does not carry, say so in the report instead of changing the conductor. The recordings in `/Users/kerim/Documents/ChatGPT/gta/recordings/` are read-only; decode with `cv2`.

## Done when

The check of the assumption is reported with its numbers. On the labelled crops no colour has more invented blips than one in twenty of its reports, at least nine in ten labelled blips of the destination and of the colours used for people and vehicles are found, and the median position error is under three pixels. The reader's old numbers hold. In the simulation both skills behave as described across the delay and the noise. Both gates pass. The report shows the sheets, the table, what the head is told about the two skills, and what has to be tried on the real game before they are trusted.
