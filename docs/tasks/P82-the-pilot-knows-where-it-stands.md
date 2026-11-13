# P82: The pilot knows whether it stands in a room, on a landing or on the street

## Why

On 13 November, 12:15, a session began with the figure standing in an apartment (recording `/Users/kerim/recordings/pilot/20261113-121513`, read-only). The pilot did not know it. For thirty minutes it planned what belongs to the street: `walk_road` failed `stuck` 76 times, `set_waypoint` failed nine times. Once, between 20 and 31 s, the figure pushed the front door open and stood on the landing outside, with the stairs down to the street in front of it, and walked back in. Kerim, watching: it was outside already and went back in; it has to walk down the stairs; it needs a sense of where it is.

The model can tell. Asked the question `ahead.WHERE` (in this worktree's `pilot/src/pilot/ahead.py`, measured in `lab/models/bench.py scene` on 333 labelled frames), the 4B model named the room in 133 of 133 frames, that landing in 31 of 31 and the street in 162 of 169, in 0.11 to 0.19 s an answer. The pilot never asks: `leave_building` asks whether it is indoors, but no rule starts `leave_building` for a figure that simply is in a room, and `walk_road` asks nothing.

This card gives the pilot a standing sense of the place and the rules that act on it. A second card, P83, builds the skill `descend` that walks down from a landing; this card plans it by name and does not build it.

Read `PLAN.md`, `docs/tasks/README.md`, then `pilot/src/pilot/ahead.py` (the question, `View.where`, `ahead.where()` are already there, do not change them), `indoors.py`, `leave.py`, `conductor.py` where the judge is polled and the `HeadRequest` is built, `head.py`, `mission.py` (`decide`, `_rule`, `_standing_rule`, `_held`, the rule for the third identical failure around `SAME_FAILED`), `errands.py` (`plan`, the roam errand), and the tests `tests/test_ahead.py`, `tests/test_buildings.py`, `tests/test_mission.py`, `tests/test_review_head_rules.py`.

## What to do

The decisions below are made; where one turns out not to work, say so in the report and do the nearest thing that keeps its purpose.

### The sense

A new module `pilot/src/pilot/where.py` with one class, `Sense`, that the conductor owns and steps on every tick with the observation. It asks through `ahead.where()` with `ask(frame, time, where=True)`, never through the other two askers, so that it holds up neither a guard nor a walk, and it never blocks a tick.

It asks only while the figure is on foot on the game's own screen with a valid frame (`player_mode(observation) == "foot"`, the HUD's screen `game` where a HUD is read), at most once a second and one frame at a time. An answer counts when it came within two seconds of its frame, carries no error, and gives its strongest place a share of at least 0.6; any other answer counts as none. The verdict is one of `room`, `landing`, `street`, and it changes only when two counted answers in a row, of different frames, name the same place. A verdict is forgotten five seconds after the last answer that confirmed it, and at once when the figure has not been on foot for two seconds (a car, a cutscene, a menu). The sense exposes the verdict and the time it was last confirmed.

The conductor puts it into the request: `HeadRequest` gets a last field `place: str | None = None`, which is `None` when no place model is configured (`ahead.where()` is `None`), `"unknown"` when one is configured and there is no verdict, and otherwise the verdict. The row the conductor logs for every tick gets the same value under `place`, so that a session can be read afterwards. `build_prompt` shows the place to the language head in one line where it is known.

### The rules

They live in `MissionHead` and hold in free play only: no objective text and the objective's class none or unknown, as `_standing_rule` already defines `free`. During a mission a room can be where the mission wants the figure.

Out of a room first. On foot, the place `room`, and the errand's step is not one that works inside (`use`): the head plans `leave_building` with duration 60 and names the rule `room_leave`. It outranks the errands' own plans and the intent rules, and nothing that needs the open (`walk_road`, `walk_to` a map marker, `set_waypoint`, `enter_vehicle`) is planned from a room. It does not outrank what is urgent today: menus, the phone, death, stars, low health.

Down from a landing. On foot, the place `landing`: the head plans `descend` with duration 40 and names the rule `landing_descend`. From a landing `leave_building` is never planned, and no step that walks to a door. (`descend` is P83's; here the plan is a call by name, and the tests check the plan.)

The third time differently, for both. `leave_building` failed and the place is still `room`: the next plan turns the view by 180 degrees with `look` and tries again. `descend` failed and the place is still `landing`: `look` by 120 degrees and again. After the third failure in a row of either, its rule rests for 120 seconds and the head decides as it did before this card, so that one skill cannot be planned without end; the count starts anew when the place changes or the skill ends done.

Not walking off blind. At the start of a session the first decision comes before the sense has two answers. While the place is `"unknown"`, the figure is on foot in free play and the session is younger than six seconds, the head waits one second instead of planning a walk (rule `place_wait`). After six seconds an unknown place is treated as it was before this card.

A verdict the head reads is held the way stars and the seat are (`_held`): a decision that arrives in the moment the sense has forgotten its verdict uses the last one, if it is not older than ten seconds.

### Leaving reports where it came out

`leave_building` ends `done` with reason `outdoors` as before. No change to the skill is needed for this card; if you find that it walks back through the door it came out of because a remembered entrance pulls it, say so in the report and leave it.

## Your files

`pilot/src/pilot/where.py` (new), `conductor.py` (stepping the sense, the request, the logged row), `head.py` (the field and the prompt line), `mission.py`, `errands.py` only where a plan of the roam errand has to give way to the rule, `bench.py` only for rules in `CAUSE_RULES` if you add a failure reason, their tests (`tests/test_where.py` new, additions to the tests of the head), and `docs/reports/P82-the-pilot-knows-where-it-stands.md`. Not `ahead.py`, `indoors.py`, `leave.py`, `wayround.py`, `walkto.py`, `skills.py`: P83 works beside you and the reviewer wires the new skill in.

Tests never contact a model server: the sense takes its asker as an argument, and a scripted one answers.

## Done when

A test for each of these fails before the change and passes after it: the sense needs two agreeing answers of different frames, forgets after five seconds, forgets when the figure sits in a car, ignores an answer below 0.6 and one that came late; the request carries `None`, `"unknown"` or the verdict; in free play on foot a room plans `leave_building` and not `walk_road`, also for the roam errand and with no errand at all; a room during a mission (an objective text) changes nothing; a landing plans `descend` and never `leave_building`; the second and third failure turn the view first, the fourth decision after three failures is what the head decided before this card, and the rule is back after 120 seconds; an unknown place in the first six seconds waits. One test replays the head's decisions over the first forty seconds of the recording's situation with a scripted sense (room until 21 s, landing from 22 to 30 s, room after) and shows: `leave_building` first, `descend` on the landing, never `walk_road`. The gate passes in `pilot/`: run the tests of your own files while you work and the whole gate once at the very end, because the machine is shared and a measurement is running on it.
