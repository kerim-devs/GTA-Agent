# P10: The conductor, the head and the first skills

## Why

The pilot can follow a GPS route and it can say when something happens on screen, and nothing connects the two. `pilot drive` runs one driver until the route is gone and exits. A stream needs a process that keeps running for two hours, lets a slow strong model decide what to do when the game asks for something new, and carries those decisions out with small behaviours at 30 Hz. This card builds that process. It is the skeleton of phase 2 in `PLAN.md`; read the plan and `docs/LOG.md` first.

The head is the local Codex CLI. One call with a picture takes about seven seconds, so the head never sits in the loop: while it thinks, the current skill keeps running or the pad rests.

## What to build

A conductor in `pilot/src/pilot/conductor.py`: the top-level loop of a session. On every fresh frame it reads the minimap as today, a few times a second it reads the screen text from a full frame (`scene.TextReader`, about 45 ms per frame, so not on every tick and not in the way of the 30 Hz loop), it feeds `scene.EventDetector`, it runs the current skill to get the pad state, and it sends that through the bridge. When an event arrives, or a skill ends, or a skill has run for a configurable time without either, it asks the head in the background. Events that arrive while the head is thinking are collected and go into the next question together. A decision that comes back is applied only if nothing has overtaken it.

The safety rules of `run_drive` in `loop.py` hold for every skill and live in one place: neutral once when no fresh frame has come for 300 ms, stop sending after a 409 and resume only after an accepted neutral, never post in shadow mode, neutral and recorder stop on every way out, a lease of 250 ms on every pad state. Do not copy that loop; turn it into a core that both `pilot drive` and the conductor use, with the existing tests still passing against it.

Skills in `pilot/src/pilot/skills.py`. A skill gets the observation of the tick (reading, moving, time) and returns a whole pad state plus whether it is still running, done or failed. A whole pad state needs buttons and both sticks, which `contract.Command` does not have; add a `Pad` next to it and let `Bridge.pad` take either. The first skills are deliberately simple and open-loop, because the head sees the picture and composes them:

- `drive_route` wraps the existing `Driver` and ends when it reports `route-gone` (arrived or lost) or `failed-recovery`.
- `wait` rests the pad for a number of seconds, for cutscenes and loading screens.
- `press` taps or holds one button, for the prompts the help text gives ("Drücke …"), for entering a vehicle with triangle, for skipping.
- `walk` pushes the left stick in a direction relative to the camera for a number of seconds, optionally sprinting.
- `look` turns the camera with the right stick by a rough angle.
- `shoot` holds L2 so the game's aim assist locks on, taps R2 for a number of seconds, lets go, and repeats a given number of times.

Every skill has a hard upper time limit, and none may leave a button or trigger held when it ends or is replaced. Durations and counts the head asks for are clamped to sane ranges.

A head in `pilot/src/pilot/head.py` behind a small interface: it gets a request (the events, the current help, objective, subtitle and banner text, the minimap summary including the printed distance and turn arrow, what the last skill did and how it ended, the notebook, and the path of a JPEG of the current frame) and returns a decision: a short plan of at most five skill calls with their arguments, one sentence in German for the commentator about what it is doing and why, and optionally a lesson for the notebook. Two implementations. A scripted one for tests and offline runs. And one that calls `codex exec` as a subprocess with the request as the prompt on stdin, the frame via `-i`, the answer constrained by `--output-schema` and read from `-o`; model and reasoning effort are settings, effort defaults to `low`, and the call has a timeout after which the conductor carries on without an answer. A malformed or unknown answer is rejected as a whole and logged, never half executed. You will not be able to run Codex from inside your sandbox; build it against the documented options (`codex exec --help` works offline), cover the parsing and the failure paths with a fake executable in the tests, and say plainly that the real call is untested.

The prompt for the head is part of this work and belongs in the repository as a text file the code loads: what the game is, what the skills do and cost, that it is asked rarely and answers in the schema, that it should prefer `drive_route` whenever a route is on the map, let cutscenes play, and say `wait` when it does not know. Keep it short enough to read in one go.

A notebook: a plain text file of lessons that is given to the head with every request and to which accepted lessons are appended with the date. Its path is a setting; the default lives next to the recordings and is not in the repository.

A decision log: `head.jsonl` in the recording directory with one line per request and per answer (what was asked, the frame's file name, the plan, the sentence, how long it took, whether it was applied or overtaken). The commentator and the overlay will read this file later, so its fields are a contract; describe them in the report.

`pilot play` as a new subcommand next to `drive` and `replay`: `--shadow`, `--seconds`, `--head scripted|codex`, the notebook path and `--set name=value` for the driver as today. In shadow mode nothing is posted, the head is still asked and everything is logged.

An offline run: the conductor fed from a recording instead of the bridge (video, `frames.jsonl`), with the scripted head, writing the same logs, and a tool that for every head request of such a run saves the JPEG and the exact prompt, so that the real head can be tried on them afterwards outside the sandbox.

## Your files

New: `conductor.py`, `skills.py`, `head.py`, the prompt file, their tests, `pilot/tools/` scripts for the offline run. Changed: `contract.py` (additions), `bridge.py` (take a `Pad`; fetch a full frame), `loop.py` (the shared core), `cli.py` (the subcommand). Not yours: `drive.py`, `sim.py`, `minimap.py`, `gps.py`, `scene.py`, `motion.py`, `replay.py`, everything under `remoteplay/`; import from them as they are. The bridge's HTTP interface is fixed: `POST /pad` takes `{"buttons": [...], "left": [x, y], "right": [x, y], "l2": 0..1, "r2": 0..1, "ttl_ms": 250}` with `{}` as neutral, and `GET /frame.raw` without a rectangle returns the full 1280x720 frame. Button names are those of `remoteplay/src/ps5_remoteplay_mcp`; read them there and do not guess.

The recordings in `/Users/kerim/Documents/ChatGPT/gta/recordings/` are read-only; decode with `cv2`. The text recognition does not run inside the sandbox, so the offline run must work with the recognition switched off and with texts injected by the test, and you should say what could not be exercised.

## What must stay true

Nothing reaches the console that a person did not allow: the conductor in shadow mode posts nothing, and no test talks to a real bridge. A crash, a signal, a head that hangs, a recogniser that hangs and a skill that raises all end with the pad neutral. The 30 Hz loop does not wait for the head or for the text. Everything `pilot drive` does today it still does.

## Done when

Tests show, with a fake bridge and the scripted head: an event leads to one head request and the returned plan runs skill by skill; a slow head does not stall the loop and its late answer is dropped when a newer event has arrived; events during a head call are batched into the next request; every skill releases everything when it ends, is replaced, or the run is interrupted; durations are clamped; the frozen-stream and 409 rules hold while a skill other than driving is active; a malformed answer changes nothing; shadow mode posts nothing and still logs.

The offline run over the long recording (`20261110-093238`) completes with the recognition off and reports how many head requests it would have made and their spacing. The spacing matters: a request every few seconds would exhaust the head, so state the number per minute and what throttles it.

The default gate passes in under 90 seconds and the full one passes. The report describes the log contract, the prompt, what was not run for real, and what the next person needs to know to connect the real head and a real console.
