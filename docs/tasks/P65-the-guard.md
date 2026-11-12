# P65: The guard: rules that answer a threat on the same tick, without waiting for a model

## Why

The reaction bench says what holds the pilot back when a scene turns fast (log of 12 November, "Ways of control, measured on 55 scenes"; report `docs/reports/P62-the-reaction-bench.md` from "P64" on). It is not the time a decision takes. Readers and rules see a red marker or a star 36 ms after it is on the screen. The pilot as it plays notices the six star onsets and none of the twenty enemies, because nothing in it takes a red marker for a threat; the judge names a threat in half of the scenes and seconds late; a model head answers after eight seconds. Decided from it: reactions belong to readers and rules, the judge may confirm or withdraw, the head plans.

Today a threat reaches the pilot only as news for the head. `conductor._hud_events` reports stars and low health after half a second each, and the head's rules in `mission.py` answer them (`wanted_*`, `low_health_*`); `take_out_fight` fights a red marker only when the objective says take out. All of it waits in line behind a head request that is already in flight, which with a model as the head is eight seconds. Screens already have what threats lack: the flow reflex answers a menu by itself, in the tick, and the head hears of it afterwards. The guard is the same for threats.

Read the log entry and the report named above, then `pilot/src/pilot/conductor.py` (the tick, `_flow_tick`, `_hud_events`, `_abandon_head`), `flow.py` for how a reflex takes and returns the pad, `combat.py`, `mission.py` from `_intent_rule` down, `contract.py`, and P64's code: `approaches.py`, `reaction.py`, `tools/reaction.py`, `lab/reaction/README.md`.

## The rules

A rule is started only by what the game itself draws and a reader reads exactly: the screen, the stars, the health bar, a red marker on the minimap. No answer of a model starts one. The guard is asked on every tick, after the flow reflex and before the plan, and its answer is on the pad of that tick whatever the head is doing. One rule holds the pad at a time, the one of the highest rank that counts.

| Rank | What the readers show, on foot | Counts once it | The guard's answer | It lets go when |
|---|---|---|---|---|
| 1 | a screen that takes no ordinary input, or the judge's mode is none | is read as today | none: the flow reflex has the screen, and a cutscene, a black picture or a dead figure is not answered | the game is back |
| 2 | health under one third | has held for half a second, as today, and the HUD has been back for a second | break off whatever runs and sprint away from the nearest red marker, straight ahead when there is none | health is back at 0.45, or after four seconds; the head's `low_health` rules go on from there |
| 3 | wanted stars lit | has shown the same number on two readings 0.1 s apart | flee and never fire: sprint away from the nearest red marker; the head's `wanted` rules bring the car and the route | the head's plan has started, or after four seconds |
| 4 | a red marker inside the map | is there on two of three ticks in a row | fight as `Fight` does: turn towards the nearest, aim, fire; when the objective's class is escape, flee as in rank 3 instead | `Fight` ends by itself, two seconds without red |
| 5 | a red marker on the map's edge and none inside | is there on two of three ticks in a row | turn the camera to the marker's bearing while no skill moves the figure, and no pad of its own while one does; the head hears of it either way | a marker comes inside (rank 4) or none is left |

In a vehicle the guard puts nothing on the pad. Markers and stars are news for the head there, the head's rules for a vehicle stay as they are, and a head request in flight is abandoned so that the rules are asked at once.

When the guard takes the pad it stops the running skill with a reason of its own, voids the head's pending answer and tells the head with an event that names the rule and the marker's bearing. When it lets go, the tick carries the neutral pad, and the head hears an event with the reason and plans from there. Both are rows in `play.jsonl`.

What the guard never does: fire while stars are lit, press anything on a screen other than the game, open the map, the weapon wheel, the phone or a menu, or act on one odd tick. The rules of `docs/tasks/README.md` for a skill hold for it as well.

What the rules leave out, and the report says so again. A hit without a marker is not answered: a falling health bar is no signal while the HUD reader reads a fall whenever an icon crosses the bar or the HUD fades in, and the reader is another card. Whether a weapon is in the hand is not known, since no reader says so; `Fight` assumes one, as it does today. Nothing is answered with a pad in a vehicle. The judge's second opinion on a marker, asked on a crop of the map, is a later card.

## What to do, in this order

Write what each step gives into the report as soon as it is there.

The guard, as a module of its own, `pilot/src/pilot/guard.py`. The rules stand at its top as a table of data, one entry a rule with its rank, its signal, how long it must hold and its answer, so that a rule is changed in one place and a new one is one entry. It keeps its own counters for what counts, reuses `Fight` and the walk skill for its answers rather than writing pads of its own where a skill exists, and says on every tick which rule holds the pad and why.

The conductor asks it in the tick, after `_flow_tick` and before the head's answer is taken and the plan is run. It is off unless the conductor is given one: `pilot play --guard` turns it on, and without the flag nothing at the console changes. Starting, it stops the runner, raises the epoch, abandons the head request in flight and queues its event; ending, it queues the other. The head's rules must take both events without reading them as a failure.

The bench shows it beside what is there. `approaches.Pilot` and the modelled head run with and without the guard as rows of their own (`pilot`, `pilot+guard`, `head`, `head+guard`), and the guard's rule is the row's `noticed`. The scene file and the rows on the board stay as they are.

Hard calm scenes. The 29 calm scenes were chosen where the labels show no red, so they cannot show what a false red does to the guard, and P64 threw out twelve onset proposals in which the reader took red behind the translucent map for a marker (flowers, bricks, red map areas, a red character). Find such stretches again with P64's search, look at the frames, and put up to twelve where no marker is on the map into a scene file of their own, `lab/reaction/scenes-hard.json`, with a ledger of their own, so that the board's rows are not orphaned. Run `reflex`, `pilot+guard` and `head+guard` on them.

Then run `reflex`, `pilot`, `pilot+guard`, `head` and `head+guard` over the 55 scenes in real time, the head with the delay modelled as in P64, one replay at a time, rebuild the board, and write the report with the times per scene.

## Your files

`pilot/src/pilot/guard.py` and `pilot/tests/test_guard.py`, both new; `pilot/src/pilot/conductor.py`; `pilot/src/pilot/cli.py` for the flag; `pilot/src/pilot/mission.py` only as far as the head's rules must hear the guard's two events; `pilot/src/pilot/approaches.py`, `pilot/tools/reaction.py` and `pilot/tests/test_reaction.py`; the conductor's tests where its tick changes; `lab/reaction/`; and `docs/reports/P65-the-guard.md`. No reader is changed (`minimap.py`, `hud.py`, `camera.py`), and neither are `contract.py` and `legend.py`, which are open in other worktrees; if the guard needs something from one of them, the report says what.

The rules of `docs/tasks/README.md` hold: no git writes, never the daemon on port 9395, no `ps5rp`, no `PS5_HOST`, recordings are read and never written. Somebody may be playing on the console while you work and this Mac records it: one replay at a time, nothing heavy beside it, and not the full gate, which the reviewer runs. Keep `lab/reaction/` under 5 MB and remove what you put under `/tmp`. The gaming PC is not needed for this card and is not touched.

## Done when

With the guard on, the pilot and the modelled head notice every enemy onset that the reflex row notices today and none of them more than two ticks later than it, the three onsets with a marker on the edge (enemy-05, enemy-06, enemy-09) within 0.2 s, and every star onset that starts from calm within 0.2 s. The head row with the guard is on no scene more than two ticks behind the pilot row with the guard: that is the proof that nothing waits behind a head. No row with the guard has a false answer or a false notice on the 29 calm scenes, and the false flight before enemy-13 (a full health bar fading in) is gone. For the hard calm scenes the report says on how many the guard starts, for how long, and what it puts on the pad; a shot fired on one of them is a failure of this card, and the rule's confirmation is tightened until none is.

`env -u PS5_HOST .venv/bin/python -m pytest tests/test_guard.py tests/test_reaction.py -q` and ruff pass in `pilot/`, with tests for: the order of the ranks; one odd tick deciding nothing; no shot while stars are lit; silence on a screen and in mode none; nothing on the pad in a vehicle; the guard's start voiding a head answer that arrives afterwards; the neutral pad on the tick it lets go; and a conductor without a guard behaving as before.

The report says in its first paragraph how fast the pilot now notices and answers with a slow head behind it, how often it is wrong, and what the first run at the console has to measure: the time from a marker to the first aimed shot with the camera turning, which no replay can give, and whether pressing L2 before the turn is finished, so that the game's own aim assist finishes it, is faster than turning first.
