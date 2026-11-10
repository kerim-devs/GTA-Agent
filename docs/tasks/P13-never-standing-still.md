# P13: Never standing still

## Why

The pilot played live for the first time on 10 November and the result is in `/Users/kerim/recordings/pilot/20261110-231512`: 240 s on foot, ten answers from the head, all applied, 26.5 ticks a second, every input accepted. It looks like a player who freezes every fifteen seconds. Each answer took 7.4 to 12.6 s, the conductor asks only when the plan has run out, and so the pad was neutral on 37.5 per cent of the ticks after the first plan. A viewer sees the character stop, stand, and walk on.

The model is not the slow part. A `codex exec` call that answers the single word OK takes 5.5 to 6.4 s on this machine before any thinking, and `gpt-6-luna` as the head was no faster than the default (9.2 to 9.8 s on three saved requests). The time goes into starting the CLI for every request.

The second reason for this card is the wave of skills that is being built next to you (P14 to P19). Today a skill is a branch in one class in `skills.py`, its limits are repeated in `head.py` and its description a third time in `head_prompt.txt`. Read `docs/tasks/README.md`, section "A new skill": that is the shape the other cards deliver, and you build the place they plug into.

## What to build

Ask ahead. The conductor asks the head before the running plan ends, not after. The runner can say how long the queued plan can still take at most; the conductor keeps an estimate of the head's latency from its last answers (start with 9 s) and sends the request when the remaining time drops under that estimate. The request says that the plan is about to end, how long it still runs and which steps remain, and the prompt explains that the new plan starts where the old one ends, so the picture will have moved on. The answer is appended behind the remaining steps instead of replacing them. A scene event still invalidates an answer in flight and replaces the plan as today; the end of the very plan an ask-ahead was made for is not such an event and must not throw its answer away. A failed skill still asks at once. At most one request is in flight, as today.

Carry on. When the queue is empty and an answer is on its way, the character does not freeze if it was walking: on a flat map, after a walk or `walk_to` that ended normally, it keeps going forward at a moderate stick without sprinting, for at most four seconds, visible in the logs under a name of its own. In every other case it stays neutral. In a vehicle it stays neutral: `drive_route` runs long enough.

A head that stays up. A second head keeps one Codex process alive for the session and sends each request as a turn with the picture attached, so the start-up is paid once. `codex app-server` is that process; `codex app-server generate-json-schema` prints its protocol and works without network. Every request must be independent of the ones before it, because the head has to decide from the request alone. The answer goes through `parse_response` exactly like today. A protocol error, a timeout or a dead process falls back to the existing `CodexHead` for that request and restarts the server in the background, and shutdown never waits for it. On the command line it is `--head codex-server`. You cannot reach the real service from your sandbox: build against the generated schema and a fake server in the tests, and add `tools/head_latency.py <session dir> [--head codex|codex-server] [--model M] [--effort E]`, which sends the saved requests of a session to a real head and prints each latency and answer, so the reviewer can run it.

The registry. Skills become classes of the shape the README describes, registered in one place, and `head.py` builds its names, limits, response schema and the skill part of the prompt from that registry. The eight existing skills behave exactly as before and their tests pass unchanged apart from imports. Adding a skill afterwards is one import and one line.

Feeding the observation. `Observation` has new optional fields (frame, objects, hud). `run_play` and the conductor pass the frame on every tick and accept two optional sources: `objects`, a poller with `poll(frame, t)` that returns the newest finished `(capture_time, detections)` or None and has `close()`, like `gps.Reader`; and `hud`, an object with `read(frame, text=None) -> Hud` that is cheap enough for every tick. Both may be absent. Changes of the HUD become events for the head: the wanted level changed and stayed for half a second, health fell under 0.3, the screen changed. The request to the head gains the HUD state and a short list of the detections, added at the end with defaults so that `head.jsonl` stays readable by the overlay.

The overlay shows the last sentence of a session for ever after the session has ended, which on stream is a stale thought over a paused game. When the newest session has not grown for five seconds, the page goes quiet.

## Judging it

Replay `20261110-231512` through the conductor with a scripted head that answers after 9 s of the recording's clock with a four step plan of walking and looking, as the live head did. Report the share of ticks with a neutral pad after the first plan, before and after: 37.5 per cent live, and the target is under 5 per cent. Replay the long Wi-Fi recording the same way and report how many answers were appended, replaced and thrown away.

## Your files

`pilot/src/pilot/conductor.py`, `skills.py` (it may become a package as long as `pilot.skills` keeps its names), `head.py`, `head_prompt.txt`, `cli.py`, `overlay.py`, `overlay_web/`, `pilot/tools/conductor_replay.py`, `pilot/tools/head_latency.py`, the tests of these files, and your report. Not yours: `contract.py`, `loop.py`, `minimap.py`, `drive.py`, `gps.py`, `scene.py`, `motion.py`, `bridge.py`, and every new module the other cards write (`objects.py`, `hud.py`, `vehicle_entry.py`, `roam.py`, `combat.py`, `waypoint.py`).

## Done when

The replay shows the dead time under the target and the report has the numbers. Tests pin: an ask-ahead answer is appended and survives the end of its plan; a scene event still throws an answer in flight away; carry-on never lasts longer than its limit, never sprints, never happens in a vehicle and ends with a neutral pad; the persistent head falls back on a broken reply, a timeout and a dead process and never blocks shutdown; a skill registered through the registry appears in the schema and the prompt and runs. Every safety test of P10 still passes. The default gate passes, and the full gate once at the end. The report says what the reviewer has to run against the real service and what to look for.
