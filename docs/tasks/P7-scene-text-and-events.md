# P7: Scene text and events for the head

## Why

The head is a strong model that takes about seven seconds to answer, so it is asked only when something happens, and it should get words instead of having to read pixels. Nothing in the repository yet says when something has happened or what the screen says. This card builds both, offline, from the recordings. The game runs in German.

## What to build

`pilot/src/pilot/scene.py` with two things.

A text reader for a full 1280x720 RGB frame that returns what is written in the places the game uses: the help box in the top left, the subtitle and objective lines at the bottom centre, the large banners across the middle (mission passed, mission failed, the death and arrest screens), and the phone or a menu when one is open. Use the text recognition that ships with macOS (the Vision framework through `pyobjc`), set to German and English. No frame and no text may leave this machine, so no cloud service of any kind. Measure what a call costs for one region and for the whole frame, at the fast and at the accurate setting; the reader is called a few times a second at most and never from the 30 Hz loop.

An event detector that is fed cheap per-frame facts and says when the head should be asked. It gets the `Reading` of the minimap for each frame (map none, flat or tilted; route none, yellow or purple) and may look at the frame itself, and it emits events such as: the HUD went away for longer than a moment or came back (a cutscene started or ended), the player got into or out of a vehicle, a route appeared, changed colour or vanished, a banner appeared, the objective or help text changed. An event carries its kind, its time and the text that belongs to it. It must be quiet: a damaged frame, a one-frame flicker of the map class or a subtitle that is still being typed out must not fire a burst. Decide the debouncing from the recordings and state the numbers.

Find out from the recordings which texts and screens actually occur and what they are called in the German game; do not assume the English names. Look at frames yourself to establish the truth for a sample of events, and say how many you checked.

## Your files

`pilot/src/pilot/scene.py`, `pilot/tests/test_scene.py` with fixtures under `pilot/tests/fixtures/scene/` (keep them small: crops rather than whole frames where a crop is enough, a few megabytes in total at most), an evaluation script `pilot/tools/scene_eval.py`, `pilot/pyproject.toml` and `pilot/uv.lock` for the one new dependency, and your report. Nothing else: another worker is rewriting `drive.py`, `sim.py`, `replay.py`, `minimap.py` and `contract.py` right now. Import `read` from `pilot.minimap` and `HUD_RECT` from `pilot.contract` as they are and do not change them.

Unlike the other cards this one has network access, for a single purpose: installing the text recognition dependency with `uv add`. If the sandbox does not let Vision run, say so in the report with the error, build and test the event detector without it, and leave the text reader behind an interface with the measurements you could take.

The recordings are in `/Users/kerim/Documents/ChatGPT/gta/recordings/` and are read-only for you. Each has `video.mp4` (720p), `frames.jsonl` with the time of every frame, `pad.jsonl` and `meta.json`. They were made over Wi-Fi and about a third of the frames are visibly damaged; the live picture will be cleaner. Decode with `cv2`, never with `av`. Tests must not need the recordings or the Vision framework to pass on a machine without them; skip the recognition tests cleanly there.

## Done when

Run over every recording, the detector produces a timeline of events, and the report shows it for the long recording (`20261110-093238`) next to what really happens there, with the counts of events that were right, spurious and missed in the stretch you checked by eye. Between two real changes it fires nothing. The text reader returns the objective and help texts of the sampled frames well enough that a person would understand the instruction, and the report gives its error cases and its cost per call.

The gate passes. The report says what the head would receive at each event, what could not be verified, and what must be re-measured on the cleaner wired picture.
