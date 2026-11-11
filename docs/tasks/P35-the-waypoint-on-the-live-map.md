# P35: The waypoint on the live map

## Why

The measure for the stream is that the story moves forward, and it moves when the pilot drives to a mission letter. On 11 November `set_waypoint` met the console's map for the first time. Once the pause menu was recognised and the presses lasted their time (see the log, "The first live rounds"), it opened the map every time and then failed in both of its ways.

To a mission letter it failed at once with `player-marker-unreadable; centre the map manually`: session `/Users/kerim/recordings/pilot/20261111-124637`, the map is open from about 1.9 s to 3.3 s after the first tick. The map was at the zoom the game opened it with, the whole city in view and the scale bar at 1007 m, with mission letters and the legend on screen.

Away from here it set a waypoint once, in session `20261111-123334` (0.1 s to 16.7 s), on a day when every push was cut to a single tick by a fault that is now mended. Since the pushes last what the skill asks for, the first push measures a shift of 18.70 pixels, the same number in two sessions, and the second measures nothing, and the skill ends with `map-shift-unverified; damaged or ambiguous map pair`: sessions `20261111-123938` (set_waypoint from 25.4 s, from 39.3 s, from 59.5 s and later) and `20261111-125537` (0.2 s to 9.6 s). At this zoom the city is a fine, regular grid of streets, and a shift measured by following street corners may be a multiple of the grid and not the truth; find out whether it is.

Each session folder has `video.mp4`, `frames.jsonl` with the capture time of every frame, and `play.jsonl` with the pad sent on every tick and its time `t`. Ticks and frames are matched by `frame_id`.

Read `PLAN.md`, in `docs/LOG.md` the entries of 11 November, `pilot/src/pilot/waypoint.py` with its tests, `pilot/tools/sim_waypoint.py` and `lab/waypoint`.

## What to build

`set_waypoint` works on the map as the console shows it, at the zoom it opens with.

To a mission letter: the game opens the map with the cursor on the player, so where the player's marker cannot be read the cursor's place stands for it. The skill finds the mission letters the map shows, takes the nearest, moves the cursor onto it and sets the waypoint. Say in the report what kept the marker from being read on the live picture and whether the letters and the cursor are read there; if a reader of the map has to change for the live picture, change it, with the live frames as evidence.

Away: the purpose is a destination a good way off in a direction, on land, and not a measured distance. Replace what cannot be measured at this zoom by what can be seen: that the map moved after a push, that the cursor is on land, that no waypoint sits under it. If a true shift can be measured robustly on the recorded pairs, use it; if not, say so and do without. The two distances stay as two clearly different amounts of travel.

For both: after the press that sets the waypoint, the map's legend names it ("Wegpunkt" with a distance in brackets) and the map draws its route; one of the two is the proof the skill reports, read from the map before it is closed. What the skill refuses today it still refuses: no press on a screen it has not read, cross only on the map with the cursor known, a waypoint that exists is not toggled off, circle is the only way out, and the time limit holds.

Extend `tools/sim_waypoint.py` so that it also shows the map as the console did on 11 November, at that zoom and with the pan speed you measure from the recordings, and so that the tests run against both.

## Judging it

From the recordings, cut the frames of every map visit named above and run the map's readers over them: report for each visit what was read (screen, cursor, player, letters, waypoint, land at the cursor) next to what a person sees on the frame. For the pushes, report the shift between the frame before and the frame after each push by your method next to the shift by the old one. Then replay: feed the skill the recorded frames of a visit where that is possible, and for the rest use the simulation at the live zoom. Report how each of the two ways ends there, with the presses it made.

Pin with tests: the map readers on live frames kept as small fixtures; a waypoint to a letter with an unreadable player marker; away in both distances at the live zoom ending in a verified waypoint; every refusal named above, each with the press that must not happen.

This card changes what the skill sends to the console. Run the full gate, and write down for the reviewer the three presses that would do the most harm on the console if they went out wrongly, with the test that guards each.

## Your files

`pilot/src/pilot/waypoint.py`, `pilot/tools/sim_waypoint.py`, their tests and fixtures, `lab/waypoint`, and your report. Not `hud.py`, `flow.py`, `conductor.py`, `mission.py`, `minimap.py`, `profile.py` or another skill.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green, and the report holds the tables of the map visits and of the pushes, the cause of each of the two failures, how each way ends in replay, and the three presses with their guards.

## Second round, after the first live try

The first round's change was tried on the console from this worktree on 11 November at 13:35 and `away` still fails. The car stood on the coast road at Pacific Bluffs, sea to the west, by day. Session `/Users/kerim/recordings/pilot/20261111-133505`: one push of the stick (0, -0.65) for about a second, then `map-shift-unverified; damaged or ambiguous map pair; gameplay not observed after 3 exits`. A snapshot right after the run showed the game, so the exits did work and the skill did not see it. Session `20261111-132729` is the same place a few minutes earlier with the code before this card: five tries in a row, each ending in `map-shift-unverified; damaged or ambiguous map pair`, the fourth also with `gameplay not observed after 3 exits`.

Find from these two recordings, with the real readers on the real frames and not on the procedural model, why the pair before and after the push is refused here, and why gameplay is not seen after the exits. Both recordings start with the game's idle camera on the standing car (cinematic angles, the HUD stays), which a first stick input ends; the skill has to cope with whatever angle the game shows when the map closes. Then make `away` set a waypoint from this place: the proof that counts stays the waypoint legend with a distance or the drawn route after Cross. A refused shift measurement on a map that visibly moved must not end the skill when the waypoint can still be proven that way. Add frames from these sessions as fixtures and put what you found at the top of the report under "Second round". The full gate has to be green again.
