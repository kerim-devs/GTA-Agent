# P19b: A waypoint that needs no marker

## Why

P19 built the skill that opens the pause map, checks every picture, proves the waypoint and backs out. Read `docs/reports/P19-waypoint-on-the-map.md` with its review first. On the real frames of the recording it recognises the map, the fixed cursor and the purple waypoint, but neither the player's marker nor a mission letter, so both of its targets fail closed today and the pilot never gets a route.

The target "away" does not need a marker. The interactive map opens centred on the player, the cursor stays in the middle of the screen while the map moves under it, and the game leads a waypoint that is dropped anywhere to the nearest road. Pushing the map a known distance in one direction and pressing Cross is enough. With that the pilot can sit in a car, pick somewhere to go and follow the purple line with the driver that already exists, which is most of what free driving on stream needs.

## What is known and what is not

The recording `recordings/20261110-093238` has Kerim on the map between 386.1 and 391.9 s of the capture clock, with his left stick in `pad.jsonl` between 386.578 and 390.598 s; the frame indices are in the P19 report, and `frames.jsonl` maps capture time to frame index (seeking the video by time lands in the wrong scene). It was recorded over Wi-Fi: his input leads the picture by 0.6 to 1.1 s and about a third of the frames are damaged.

Not known: how fast the map moves for a given stick deflection, whether that is linear, and whether the first interactive picture really has the player under the cursor. P19 assumed a gain. Measure it: the shift of the map between two clean frames, with the fixed parts of the screen (legend, footer, tabs, cursor) left out, next to the stick over the same stretch, with the picture delay found by fitting and not assumed. Report pixels per second at full deflection, how well a straight line fits, and how many frame pairs the number rests on. If the clip cannot carry a number, say so and make the skill work without one, by measuring the shift it gets from its own first push.

## What to build

Replace what "away" does in `pilot/src/pilot/waypoint.py` and keep everything around it: the start from visible gameplay, the map check before each press, the proof of the waypoint, the bounded back-out, the time limit. Leave "mission" as it is.

"away" opens the map as now, pushes the map in one direction in short pushes with a look at the picture after each, until the map has moved the wanted distance as measured on the picture itself, presses Cross, and proves the waypoint under the cursor as now. It gets two new arguments: `direction` with north, east, south, west and any (the pause map has north at the top; any picks by the skill's own counter so that two calls in a row do not go the same way), and `distance` with near and far, in pixels of the map that you choose from what the measurement says is a useful drive. A push that does not move the map (the edge of the map, a stick that does nothing) is tried once in another direction and then fails. Do not drop the waypoint on open sea when the picture shows it: the sea has one colour on this map; a second look further inland is enough, no coastline logic.

A measured shift needs a picture before and one after that are both clean. Say how the skill tells a damaged picture from a moved one, and what it does when it cannot tell.

## Judging it

On the recording: the measured gain with its fit, and the shift your measurement reports for each of Kerim's pushes next to what the eye sees on a contact sheet of before and after. The existing checks on the real frames stay green: 125 of 125 map pictures, no false map among the 404 others, the waypoint seen at frame 8305 and not at 8286.

In `tools/sim_waypoint.py`: a map that moves under the stick with the measured gain and with half and double that gain, with picture delays of 0.14, 0.6 and 1.1 s, at the edge of the map, over sea, and with a damaged picture between two pushes. In every case the skill ends with a proved waypoint and gameplay, or fails closed with a neutral pad and nothing pressed but Circle.

## Your files

`pilot/src/pilot/waypoint.py`, `pilot/tests/test_waypoint.py` with its fixtures, `pilot/tools/sim_waypoint.py`, `pilot/tools/inspect_map_clip.py`, `lab/waypoint/`, `.gitignore`, and a report of your own, `docs/reports/P19b-a-waypoint-without-a-marker.md`. Another card adds one class attribute named `opens` to `SetWaypoint` at the same time; do not add, move or remove it. Fixtures stay small: add single frames only where a test needs the real picture.

## Done when

Tests pin: the pushes stop when the measured shift reaches the distance and not after a fixed time; a map that does not move gets one other direction and then a failure; no Cross while the last picture is damaged or unmoved; no Cross on sea; `any` does not repeat a direction; the arguments are validated; everything P19's tests pin still holds. The simulation is reported with every case above. The measurement is reported with its evidence. The default gate passes in under 90 seconds. The report lists what has to be confirmed on the console, in the order to try it.
