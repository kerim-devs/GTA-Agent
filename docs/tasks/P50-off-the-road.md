# P50: Off the road

## Why

On 12 November the pilot was started twice with Trevor at a viewpoint on a hill in the country, by day, far camera, nothing asked: sessions `/Users/kerim/recordings/pilot/20261112-100318` (180 s) and `/Users/kerim/recordings/pilot/20261112-100713` (300 s), each with `play.jsonl`, `head.jsonl`, `judge.jsonl` and `video.mp4`. It ran with P45 and P46, and what they were built for held: an appended `walk_road` started when the one before it ran out of time (20.9 s of the first session, the queue is in `play.jsonl`). The figure still got nowhere. After eight minutes of walking it stood at the fence of the same viewpoint again.

Three things are in the logs.

There is no road on the minimap for most of the time. `walk_road` took the figure off the plateau for fifteen seconds and then ended with `no-road`, 11 times in the first session and 15 times in the second. The rules answer each of these with a look of 55 degrees to the left, five seconds of walking, a look of 20 degrees to the right and five more seconds: 35 degrees to the left every round, which is a circle. A road is in the picture more than once, a winding one in the valley at 112 s of the second session, and nothing uses it.

The guard is blind there. Its evidence of whether the figure gets anywhere comes from the minimap moving, and on a map without roads it says `motion=unknown` on 3640 of 4054 walking ticks in the first session and on 5726 of 6628 in the second. Had the figure stood against a rock, nothing would have noticed.

The reader sees blips that are not there, or that mean nothing. With nothing asked, a yellow blip inside the map made the rules walk to it at 58.6 s of the first session and at 30.5, 41.0 and 245.6 s of the second; each was gone within seconds (`blip-gone`) or never reached. Red blips inside the map appear at 101.7, 255.7 and 282.6 s of the second. The first of these requests lists more than ten yellow blips at once. And the minimap is read as tilted on 11 of 26 and on 23 of 38 requests although the figure is on foot.

Read `PLAN.md`, in `docs/LOG.md` the entries "On foot" and what follows them, the reports of P44, P45 and P46, `pilot/src/pilot/foot.py`, `pilot/src/pilot/mission.py` with its tests, `pilot/src/pilot/skills.py` (`walk_road`, `walk`, `look`), `pilot/src/pilot/minimap.py` for how a blip and the map's shape are read, and `lab/foot/` for the replays that exist.

## What to build

First show, from the two sessions: what `find_road` saw in the first twenty seconds and why the road was lost; the frames and minimap crops of the yellow and red blips, and what they really are; and why the map reads as tilted on foot here.

Then, with no road on the map, a way of going that leads somewhere. At the least: the looks no longer add up to a turn, the figure keeps the heading in which a road was last seen and otherwise one heading by the compass of the minimap, for long enough to cross a hillside, and a round that brought nothing changes the heading by a fixed step instead of drifting. Beyond that, say what would find a road from far away and what it needs: the road in the picture, the enlarged radar the game shows on a press of the pad down, or the pause map the waypoint skill already reads. Build what you can show on recorded frames; describe the rest with the evidence you would need from the console. Kerim's own recordings of that morning, `/Users/kerim/recordings/kerim/20261112-09*` and later, show him with the same character in the same country and are there to read.

The guard needs evidence that does not depend on the map: something in the picture that tells walking from standing against a thing, cheap enough for every tick, used when the map says nothing. Show on the frames of both sessions that it says going while the figure walks, and on the corner of the hospital session of that morning (`/Users/kerim/recordings/pilot/20261112-082524`, from 120 s) and the railing of the pier (`/Users/kerim/recordings/pilot/20261111-204712`) that it says still.

A blip that is no blip must not be walked to. If the fault is in the reading, repair it there, with the crops as cases; if the blips are real things the game draws, say what they are and let the rules, with nothing asked, wait until a blip has stood for a moment before they walk to it. Red inside the map with nothing asked stays what it is today.

## Judging it

Replay both sessions through the changed rules and skills, request by request with the real readers as `lab/foot/p45_replay.py` does, and through the changed guard tick by tick: no `walk_to` to a blip that the frames do not show, the heading held over each stretch without a road, and the share of walking ticks with evidence of motion before and after. Run the rules over the cases of `lab/mission/`, `lab/take-out/` and the recorded requests of P45 and list every case whose decision changes, with the reason. The corpus of the minimap reader keeps every reading unless you show the old one was wrong. Tests pin the heading, the evidence from the picture on walking and on standing frames, and the blips.

## Your files

`pilot/src/pilot/foot.py`, `pilot/src/pilot/mission.py`, `pilot/src/pilot/skills.py` (`walk_road`, `walk`, `look` and what the guard needs), in `pilot/src/pilot/minimap.py` the reading of blips and of the map's shape only, their tests, `lab/foot/` and your report. Not `conductor.py`, `scene.py`, `notes.py`, `waypoint.py`, `drive.py` or `cli.py`; what one of them would need is described exactly and left. The console is in use by others while you work: the rules of `docs/tasks/README.md` about the daemon hold without exception, and nothing under `/Users/kerim/recordings/` is written, moved or deleted. Write nothing large: the disk has little room left.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green or fails only where your sandbox refuses sockets, Vision or CoreML, which you then name test by test, and the report shows the three findings with their pictures, the replays, the changed cases and what the next try on the console should look at first.
