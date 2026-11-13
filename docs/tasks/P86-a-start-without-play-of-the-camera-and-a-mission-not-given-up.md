# P86: A start without play of the camera, and a mission that is not given up for a shop

## Why

On 13 November, 16:32, Kerim put the figure on the street and watched the pilot begin (recording `/Users/kerim/recordings/pilot/20261113-163218`, read-only, the first 45 s; `head.jsonl` has the head's decisions). Three things he asked about, in his words: why does it play with the camera so much, up once and then zooming in and out, that must not be; now it goes to the start page again and again, goes back, does something, clicks through; and: okay, Discount Store, it has put that in, and now?

The camera: every session begins with `set_far_view` and `level_camera` (`cli.py`, the startup plan). `level_camera` runs the camera to its upper stop and back by a fixed amount, six seconds with the figure standing, whether the view was level or not, because nothing reads the tilt. `set_far_view` presses the touchpad through the views; in the eight sessions of the same afternoon it also ended `view-unknown` and left the camera where it was.

The map: `set_waypoint` opened the pause map and failed twice with `player-marker-unreadable; centre the map` (10 to 31 s), opening and closing the map each time, before the third try set a waypoint from the legend.

The goal: the head's goal was the next mission (`goal=story`, `step=waypoint`). After the second failure of the map it took the goal `shop` and drove 1245 m to a Discount Store. A mission is what the pilot is there for; a shop is no substitute for it.

Kerim's order of the same afternoon: a sound base comes first, getting done what the pilot has set out to do, and it has to run smoothly.

Read `PLAN.md`, `docs/tasks/README.md`, then `pilot/src/pilot/cli.py` (the startup plan), `camera.py`, `level.py`, `waypoint.py` and its tests, `goals.py`, `errands.py`, and in `mission.py` how a goal is chosen and what a failed step does to it.

## What to do

A start that touches the camera only when it has to. Find what tells a level view from behind the figure from one that looks into the sky or at the ground, without a move: the figure's detection (where its box sits in the picture and how large), the horizon, or one question to the local model through `pilot.judge.post`, asked of frames you label from the recordings (the seconds before and after a `level_camera` in the pilot's sessions of 13 November give both kinds). Report how often it is right. `level_camera` then runs at the start only when the view is off, and `set_far_view` only when the view is not the far one. A session that begins with the camera right begins with the first decision.

A map that is read, or left alone. Find on the recordings why the player's marker was not read (the frames are in the video at 10 to 31 s; the first session of the day, `/Users/kerim/recordings/pilot/20261113-121513`, failed the same way nine times) and mend the reading or the centring. Where it still cannot be read, the skill ends without a second opening of the map inside the same call, and with a reason the head can tell from a wrong screen.

A mission that stays the goal. A failed step toward the mission is tried another way before any other goal is taken: once more after a short walk or drive that changes what the map shows, then by the mission's blip on the radar where one is in sight (`walk_to` or the drive at a marker, which exist), and only when the game shows no mission anywhere does the head turn to an errand. A shop is never chosen because a map could not be read. Say in the report what the head does in each case and what it did before.

## Your files

`pilot/src/pilot/cli.py` (the startup plan only), `camera.py`, `level.py`, `waypoint.py`, `goals.py`, `errands.py`, `mission.py` (the choice of the goal and the answer to a failed step toward it; not the rules of the place, `_place_rule`, and not the rule for `vehicle_exit`), their tests, a script under `lab/` for what you measure, and `docs/reports/P86-a-start-without-play-of-the-camera-and-a-mission-not-given-up.md`. Not `drive.py`, `scene.py`, `vehicle_entry.py`, `conductor.py`: two workers are in those beside you. Tests never contact a model server; a question to the model is measured by your script against the server named in `lab/live/story.sh` only if your sandbox reaches it, and otherwise you say that it is unmeasured and leave the check on the detection.

## Done when

A test shows a session that starts with a level far view planning neither camera skill, and one that starts looking at the sky planning `level_camera`; the report gives the share of labelled frames the check calls right. A test replays the map frames of the failed calls and reads the marker, or shows the single clean failure. A test replays the head's decisions of the first 45 s of the recording with the two map failures and shows the goal still `story` after them and no errand to a shop. The gate passes in `pilot/`: run the tests of your own files while you work and the whole gate once at the end, the machine is shared.
