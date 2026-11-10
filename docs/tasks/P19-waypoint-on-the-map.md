# P19: Setting a waypoint on the map

## Why

The pilot drives a route when the game draws one, and the game draws one only during a mission or after the player has set a waypoint on the pause map. Between missions there is no route, and the next mission starts at a marker that can be kilometres away. A skill that opens the map, puts a waypoint on a chosen kind of place and comes back is what turns "play the story" from a wish into a loop: set the waypoint, get into a car, drive the purple route, walk into the marker.

It is also the most dangerous thing the pilot does. The pause menu has more than the map: settings, the online mode and a store that sells things for real money sit a shoulder button away. A skill that presses buttons on a screen it has misread could change the game's settings or open the store on stream.

## What is known

One clip. In the long recording, around 385 to 395 s, Kerim opens the pause map, moves and sets a waypoint; the text reader found the hint line "Markierung wählen", "Zoomen L2", "Wenig Details R3", "Interessanter Ort" there, and afterwards he drives a purple route. Go through that stretch frame by frame with his controller from `pad.jsonl` next to it (his inputs lead the picture by 0.6 to 1.1 s, it was recorded over Wi-Fi) and find out how the screen works: which button opens it and what shows first, whether the cursor moves over the map or the map under the cursor, what the stick and the triggers do, what the legend at the side offers and whether it can jump to a kind of marker, how a set waypoint looks, and how he gets back into the game. Write that down in the report as what the clip shows and what it does not show. Everything the clip does not show is an assumption; mark it as one.

## What to build

`pilot/src/pilot/waypoint.py` with a skill `set_waypoint`: a target and a time limit up to 45 s. Offer the targets the map lets you recognise. Wanted are at least the nearest mission start, which the game marks with a letter, and "away": a point on a road far from the player in any direction, for getting out of an area.

The skill is a sequence of steps, and each step ends with a check of the picture before the next button is pressed: the map is open and it is the map and not another page of the menu; the cursor is where it should be; the waypoint is set; the game is back. When a check fails it does not continue. It backs out with a bounded number of circle presses, checks that the game is back, and fails with a reason. It never presses L1 or R1, which change the page of the pause menu, never presses cross on anything but the map, and never presses `options` a second time before it has seen what the first press did. It is done only when it has seen the game again and the waypoint has been set as far as the picture can show it.

Where a step needs text, it may run the text reader of `scene.py` on the part of the frame it needs, in the skill's own tick; that takes tens of milliseconds, which is fine on a paused game.

## Judging it

The checks against the clip and against frames of ordinary play, the weapon wheel, the failed screen and cutscenes from both recordings: the check for "the map is open" must hold on the clip's map frames and on none of the others. A simulation of the map screen as far as you understood it, with the delay between command and picture, to show that the cursor reaches a marker, that every wrong screen injected at any step leads to backing out, and that the limits hold.

## Your files

`pilot/src/pilot/waypoint.py`, `pilot/tests/test_waypoint.py` with fixtures, `pilot/tools/sim_waypoint.py`, `pilot/tools/inspect_map_clip.py`, `lab/waypoint/`, and your report. Not `skills.py`, `head.py`, `head_prompt.txt`, `conductor.py`, `contract.py`, `scene.py` or `hud.py`.

## Done when

The report describes the map screen from the clip with frames to show it. The check for the open map is right on every labelled map frame and wrong on none of at least 300 frames of everything else. Tests pin: no button after a failed check except backing out; never L1, R1 or a second `options`; a wrong screen at each step ends in a bounded failure with a neutral pad; the time limit. The simulation is reported. The default gate passes. The report lists, in the order to try them on the real console with a person watching, the steps whose behaviour is assumed.
