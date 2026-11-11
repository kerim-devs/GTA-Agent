# P20b: A commentator that answers in time

## Why

P20 built the commentator's core. Read `docs/reports/P20-commentator-core.md` with its review first. Its writer with a character does not work as shipped. Measured against the real service: with the default limit of three seconds every call ran into the limit and the plain line was spoken, and with twenty seconds the calls took 6.7, 7.2 and 6.7 s, longer than the six seconds after which a candidate counts as stale. Starting the Codex CLI costs about six seconds on its own. The head had the same problem and got a process that stays up, `CodexServerHead` in `pilot/src/pilot/head.py` (see `docs/reports/P13-never-standing-still.md`), which answers a request with a picture in about five and a half seconds. A line of text without a picture should be faster than that.

So today the commentator says "Danke für eure Nachricht im Chat." to every message, or nothing. On stream the chat has to get real answers.

## What to build

A writer that keeps one Codex app-server process up and asks it for each line, built like `CodexServerHead`: a fresh thread per line so that one viewer's message never reaches the next line's context except as the quoted recent chat, a time limit, a restart when the process dies, and the plain writer when anything fails. Use what `head.py` has; if sharing the client needs a small extraction there, make it without changing what the head does, and keep its tests green. `--writer codex` selects this writer; the one that starts the CLI for every line can go.

Nothing waits for the writer. Today writing, synthesis and playing all happen inside the scheduler's step, so while a line is written or spoken no chat is read and no event is seen. Writing and synthesis go to the background, at most one line in the works at a time; playing may stay where it is if the loop keeps reading meanwhile, or move as well. What must hold is what P20's tests pin: never two lines at once, the gap, no stale line, no sentence twice in a row.

Age and writer per source, each a setting. An answer to chat may be up to twenty seconds late and goes through the character. A sentence of the head is about what the pilot does right now, is written for the audience already, and is spoken as it is within six seconds or not at all. An event is spoken as its plain line unless the character's line is ready within two seconds.

Chat that gets no answer gets none. The plain fallback for a chat message is silence with a reason in the log, not a sentence of thanks. The writer may also decline: the prompt lets it return an empty line for an insult, an order or noise, and that is logged as declined. Make the prompt say which message is the one to answer and that the other quotes are only what else was said; in the review's trial the answer to one viewer's order was a line about another viewer's question. Keep the rule that chat is quoted data and never an instruction, and keep the test that pins it.

More events. The loop will write these kinds into the events of a head request, and the commentator should have a German line for each, with the count where there is one: `{"kind": "failure", "screen": "failed" | "wasted" | "busted", "count": n}`, `{"kind": "pass"}`, `{"kind": "stuck", "screen": ...}`, `{"kind": "wanted_changed", "wanted": n}` for more stars, fewer stars and none, `{"kind": "low_health"}`, and `{"kind": "skill_failed", "skill": {"name": ..., "reason": ...}}` for the skills a viewer would notice (`enter_vehicle`, `set_waypoint`, `fight`). Several plain lines per kind, picked in turn, so that the third failure does not sound like the first.

It is night and a person is asleep next to this machine. Never play sound: not in tests, not in tools, not while trying something out. Synthesise to files and look at their durations.

## Judging it

With a small app-server of your own in the tests, as the head's tests do it: answers, a slow answer, a dead process, a restart, a reply that is not a line. The replay tool on `/Users/kerim/recordings/pilot/20261110-231512` with the thirty scripted messages and a scripted writer that takes four seconds per line: how many chat messages got an answer, how late, what was dropped and why, and that the loop kept reading while a line was written. You cannot reach the real service from the sandbox; write `pilot/tools/commentator_latency.py`, which sends ten chat messages and ten events through the real writer and prints the seconds and the lines, and the reviewer runs it.

## Your files

`pilot/src/pilot/commentator.py`, `commentator_persona.txt`, `pilot/tests/test_commentator.py`, `pilot/tools/commentator_replay.py`, `pilot/tools/commentator_latency.py`, `lab/commentator/`, `.gitignore`, your report, and `pilot/src/pilot/head.py` with `pilot/tests/test_head*.py` only for the extraction named above. Not `conductor.py`, `cli.py`, `flow.py` or `overlay.py`; another card is changing them.

## Done when

Tests pin: the loop reads chat and events while a line is being written; at most one line in the works; a chat answer that takes four seconds is spoken and one that takes twenty-five is not; a head sentence is never rewritten; an event falls back to its plain line after two seconds; a declined or failed chat line is silence with a reason; the message to answer is marked apart from the other quotes; the server writer's fallbacks and restart; each new event kind has lines and they rotate; everything P20's tests pin still holds; no test and no tool plays sound. The replay is reported. The default gate passes in under 90 seconds. The report says how to start a rehearsal and what the reviewer has to measure.
