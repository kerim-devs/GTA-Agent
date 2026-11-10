# P15: Health, armour and which screen this is

## Why

The pilot does not know how much health the character has left and does not know when the game has stopped taking ordinary input. In the first live sessions nothing went wrong only because nothing happened. In a shootout it has to notice that it is dying, and after a failed mission, on the pause map, in the weapon wheel or on a loading screen, walking and shooting inputs do the wrong thing or select menu entries. `contract.py` has a new `Hud` dataclass for this; you build the reader that fills it.

## What to build

`pilot/src/pilot/hud.py` with `read(frame, text=None) -> Hud`. `frame` is the 1280x720 RGB frame. `text` is the latest `SceneText` of `scene.py` when the caller has one; the conductor recognises text twice a second in the background, so it can be up to a second old and is often absent. The function is pure, never raises, and takes under 2 ms on average without doing any text recognition itself.

The bars. Under the minimap the game draws three bars: health in green on the left, armour in blue in the middle, the special ability in yellow on the right. `minimap.py` already looks at them to decide that a HUD is present (`_bars`); read it first. Return the filled fraction of each, None when the HUD is absent or the frame is damaged there. Find out how the bars look when they are empty, when health is low (the game changes its colour) and when the map is the vehicle map.

The screen. Decide which of these the frame shows: the game, the pause menu, the pause map, the weapon wheel, the phone, the mission failed screen, the mission passed screen, a loading or black screen. The long recording has each of them at least once; find the spans. The failed banner is at about 35 s, the weapon wheel between 95 and 110 s, the pause map around 385 to 395 s, and there are cutscenes and black frames. Use what is cheap and stable in the pixels first, and `text` to confirm when it is there. A frame of ordinary play that is called anything but "game" stops the pilot, so this error is the expensive one; when in doubt between the game and something else during fast motion or a damaged frame, it is the game.

The wanted level and the wasted and busted screens have no footage yet. Leave `wanted` as None and do not guess their look; structure the module so a star reader can be added when the recording exists, and say in the report what footage you need.

## Judging it

Label by eye at least 150 frames from the long recording and the two clean sessions, half drawn with a fixed seed and half picked from the spans of the rare screens, with the screen class, and the health fraction on 60 of them including the shootout, where it falls. Save them under `lab/hud/`. Report a confusion table for the screens and the error of the health reading, and the time per call.

## Your files

`pilot/src/pilot/hud.py`, `pilot/tests/test_hud.py` with fixtures, `pilot/tools/evaluate_hud.py`, `lab/hud/`, and your report. Not `contract.py`, `minimap.py`, `scene.py`, `conductor.py` or `skills.py`; import what you need from them.

## Done when

The screen is right on at least 95 in 100 labelled frames and fewer than 1 in 100 frames of ordinary play are called something else. Health is within 0.05 of the labelled value on at least 9 in 10 frames. The mean time is under 2 ms and the function survives a black frame, a frame of the wrong size and a damaged frame. Tests use real frames for every screen class and for a low and a full health bar. The default gate passes. The report shows the table, the misses with their frames, and what footage is missing.
