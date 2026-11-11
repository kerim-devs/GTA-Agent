# P34: A route that starts behind the car

## Why

On 11 November the pilot set a waypoint from a parked car for the first time and the game drew its purple route. The route began behind the car, as it does whenever the car does not already face the way it has to go, so on the minimap the only purple there was lay as a short piece along the lower edge, next to the distance the game prints there. The minimap reader said there was no route. The scene detector reported `route_vanished`, the head set a new waypoint over the one that was still there, and the drive never got further than the turn.

The session is `/Users/kerim/recordings/pilot/20261111-123938`. Its `play.jsonl` holds the reading of every tick with the time `t`; `frames.jsonl` holds the capture time of every frame of `video.mp4`. From 16.4 s after the first tick the route flickers between purple and none, and from 20.3 s it is none for good, while frames at 20.3 s, 20.8 s and 21.3 s show the purple piece plainly at the bottom of the minimap. Session `/Users/kerim/recordings/pilot/20261111-123334` has the same waypoint from 16.7 s on, with the car turning on the spot, and is a second place to look.

Read `PLAN.md`, in `docs/LOG.md` the entries of 11 November, and `pilot/src/pilot/minimap.py` with its tests and the lab folder it names.

## What to build

The minimap reader reports a route whenever the game shows one, also when all that is in view is a short piece at the lower edge of the map or beside the distance text, and gives the driver a bearing to it that points the right way: towards the lower edge means the route is behind, and the driver has to turn round. Find out first why the reader drops these frames. It may be the region it looks at, a least length or area, the path it needs before it believes a colour, or the text and the bars at the lower edge being taken for damage; say in the report which it was, with the numbers of one frame.

Whatever keeps the reader from seeing a route where there is none must stay. A purple or yellow blip, the purple special bar's neighbourhood, the pink of a cutscene or of the sky in the picture behind the map's edge, and a codec-damaged frame are not routes. The reader's present answers on its recorded evidence must not get worse.

## Judging it

Cut the evidence from the two sessions: every frame of the stretches named above, read through the reader before and after, with the count of frames that show a route by eye (label a sample of at least forty by hand, half with the piece at the lower edge, and keep the labels in the lab folder), the count the reader calls purple, and the bearing it gives. Report both counts before and after. Run the reader's existing evaluation over its recorded sets and report the numbers before and after next to each other; none may drop.

Pin with tests: frames from this evidence, kept as small crops in the repository the way the reader's other fixtures are, on which a route at the lower edge is reported with a bearing in the lower half; the frames on which the reader rightly says none stay none; the existing tests pass unchanged.

## Your files

`pilot/src/pilot/minimap.py`, its tests and fixtures, the reader's lab folder, and your report. Not `drive.py`, `scene.py`, `conductor.py`, `mission.py` or any skill: what the driver and the head do with a route behind the car is the reviewer's.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py` in `pilot/` is green, and the report names the cause, shows the counts before and after on the new evidence and on the old sets, and lists what you saw in these two sessions that the reader still gets wrong.
