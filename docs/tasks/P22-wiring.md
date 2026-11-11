# P22: Wiring the screens and the HUD into the loop

## Why

The second wave built its parts next to the loop and nothing calls them yet. The HUD reader (`pilot/src/pilot/hud.py`) is attached by nobody: `run_play` takes a `hud` source and the command line never passes one. The screen reflex (`pilot/src/pilot/flow.py`) is called by nobody. So a failed mission still costs a round through the head while the running skill pushes its sticks into a menu, which is the thing P21 was written to end. Read `docs/reports/P21-screens-that-block.md` with its review, in particular the paragraph on how the object has to be called, and `docs/reports/P15-hud-and-screens.md` and `docs/reports/P13-never-standing-still.md` for what the conductor does today.

## What to build

One `Flow` per session inside the conductor, asked on every tick after the text is updated and before the runner. When it returns something, that pad is the whole pad of the tick and the runner is not asked.

What happens to the plan. The first tick on which the flow takes over stops the running plan, so the skill lets go of everything, and no plan is run and no carry-on walks while the flow answers. A head answer that arrives in that time is thrown away. When the screen is gone and the game is back, the head is asked at once, with one event that says what happened: a failure with its count, a pass, or the menu that was closed and how long it took. A stuck screen is reported to the head immediately, while the pad stays neutral. This replaces the `screen_changed` event for the screens the flow handles; the head is not asked about a menu while the reflex is closing it. Stopping the plan was chosen over suspending it: after a screen that blocked the game the plan is old, and skills count their time on the observation's clock.

Skills that open a menu on purpose. `SetWaypoint` goes through the pause screen and the map. Give `RegisteredSkill` a class attribute `opens`, a tuple of screen names that is empty by default, set it on `SetWaypoint`, and have the conductor tell the flow when such a skill starts and for how long (its own time limit). `Flow.expect` takes one screen today and a second call overwrites the first; make it take several. When the skill ends, the expectation ends with it, whatever its deadline said, so that a menu the skill left open is closed by the reflex.

Text that is old. The flow reads the retry button from the text reader's result, and the conductor refreshes that twice a second in the background. Give the text its capture time and do not hand the flow a text that is older than a second and a half; the flow then waits, which it already does when it has no button.

The HUD. `pilot play` attaches the reader and the flow by default, with a switch to run without them. The reading is taken once per fresh frame.

Health. `low_health` fires today on a single reading under 0.3, and the reader has such readings while nothing hurts the character (17 of 3683 on the recordings). Require it for half a second, as the wanted level already does.

The registry. Add `set_waypoint` to `REGISTRY` in `skills.py`. The reviewer adds the skills of the cards that are still in review.

The logs and the overlay. One row in `head.jsonl` when the flow takes over and one when it lets go, with the screen, what was pressed and the seconds, not one per tick. In `play.jsonl` the tick's `skill` names the flow and its action while it answers. The overlay shows it in German like the skills (`overlay_web/overlay.js` has the names): the retry as "Neuer Versuch", backing out as "Menü schließen", waiting as "Warten", stuck as "Bildschirm hängt". Add the names for the skills that are coming, so they are there when the reviewer registers them: `set_waypoint` "Wegpunkt setzen", `enter_vehicle` "Einsteigen", `fight` "Schießen", `melee` "Zuschlagen".

## Judging it

In tests, with a small machine of screens that reacts to buttons after 0.14 s (the one in `tools/sim_flow.py` is a start) around the real conductor and a scripted head: a failure in the middle of a walking plan ends with the retry pressed once, the sticks neutral from the first tick of the takeover, and one failure event at the head after the game is back; a pause menu opened by accident is closed and the head is asked once afterwards; `set_waypoint` running is left alone on the pause screen and the map and taken over when it ends with the map still open; a head answer that arrives during a takeover is not run.

On the recording `recordings/20261110-093238`, replayed through the conductor with the HUD, the flow and real text (extend `tools/conductor_replay.py`; `frames.jsonl` has the capture clock): for every screen the recording has (the failure at 33 to 40 s, the weapon wheel at 14, 45 and 538 s, the phone at 154 s, the pass at 339 to 342 s, the pause screen at 385 s, the map at 388 to 392 s) when the flow took over, what it would have pressed and when, and what the head was told. Kerim's hands change the screens in that recording, so this shows decisions and not their effect; say where his press comes before the reflex's. Count the takeovers during ordinary play, which should be none, and show each one that is not.

## Your files

`pilot/src/pilot/conductor.py`, `flow.py`, `cli.py`, `skills.py` (the attribute and the registry entry, nothing else), `waypoint.py` (the one attribute line; another card is rewriting other parts of that file at the same time), `overlay_web/overlay.js`, `pilot/tools/conductor_replay.py`, `pilot/tools/sim_flow.py`, the tests of those modules and a new `pilot/tests/test_wiring.py`, `lab/wiring/`, `.gitignore`, and your report. Not `head_prompt.txt`, `head.py`, `hud.py`, `contract.py` or `scene.py`; if the head needs to be told something new about these events, write the sentences into the report and the reviewer puts them into the prompt.

## Done when

The tests above pass and each fails when its line is broken. Tests also pin: no carry-on and no skill pad on any tick the flow answers; the plan is stopped once and the skill's `stop` is called; `expect` with several screens and its end when the skill ends; old text is not handed over; `low_health` needs half a second; one row per takeover in `head.jsonl`; the command line attaches and detaches the reader and the flow; a conductor without a flow behaves as before. The replay is reported with a table of the screens. The default gate passes in under 90 seconds and `tools/gate.py --full` passes. The report lists what has to be confirmed on the console, in the order to try it.
