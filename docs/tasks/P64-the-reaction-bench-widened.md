# P64: The reaction bench, widened: the real judge, scenes that start from calm, and why the readers miss

## Why

P62 built the reaction bench and its first round says three things that have to be made firm before anything is decided from it. On nine threats the readers alone answer four within three seconds and the pilot as it plays today answers one; the cause in the pilot is not a slow chain but that nothing in its rules acts on a threat. Kerim's own reaction is void on eight of the nine scenes, because he was already holding an answering input in the two seconds before the onset, so the row every way of control is read against rests on one scene. And every row with a model in it was run against a stub that answers after a set delay, so nothing is known yet about the real judge: neither how long it takes on these frames nor whether it is right.

Read `docs/tasks/P62-the-reaction-bench.md`, `docs/reports/P62-the-reaction-bench.md`, `lab/reaction/README.md`, and the code of P62: `pilot/src/pilot/reaction.py`, `pilot/src/pilot/approaches.py`, `pilot/tools/reaction.py`, `pilot/tests/test_reaction.py`. Then `pilot/src/pilot/judge.py` for how a question with fixed answers is asked and parsed, and `pilot/src/pilot/combat.py` for what `Fight` does before it aims.

## What to do, in this order

Write what each step gives into the report as soon as it is there, so that a run that is cut short leaves its numbers.

The real judge, on the twelve scenes that exist. The server is `http://192.168.0.248:1234` with `qwen/qwen3-vl-8b`; it is asked for answers and nothing else, and nothing else on that machine is touched. P62's question asks for JSON with a sentence of reasons, which costs tokens and time and was not what the card asked for. Write a second question in the style of `judge.py`: fixed answers, one letter, a token limit to match, at the frame width the pilot's judge uses (640). Run `judge`, `judge-second` and `reflex+judge` with both questions in real time. Report for each question the time per answer (median, ninth decile, worst), the reaction per scene, and whether the answer was right: on the threat scenes the share where it names the threat after the onset and how many answers that took, on the calm scenes and in the six seconds before each onset the share of answers that call a threat where there is none. If the server does not answer, say so and go on; do not start or change anything on that machine.

Two times for every try. Today an answer is a pad state from the scene's answer set. `Fight` first turns the camera towards the red blip and aims only once it is in front, and in a replay the picture never turns, so a way of control that saw the threat at once can still be counted as never answering. Record beside the answering pad the moment a way of control first decides anything because of the threat: a field on the decision that the approach sets itself, not a guess from the pad. The board shows both, "noticed" and "answered", and says which of the two a number is. For Kerim only the pad exists.

Why the readers miss. For every threat scene where `reflex` does not notice within a second: what the minimap reader and the HUD reader return on each frame from half a second before the onset to two seconds after it (the blips with colour and border, the health, the stars, the map class, damaged or not), beside what the frame shows. Name the cause per scene in one sentence and count the causes. Do not change a reader: `minimap.py`, `hud.py` and `camera.py` are open in other worktrees. The report says which reader would have to change and how.

Scenes that start from calm. The labels hold about a hundred beginnings of a fight in 26 recordings (in `actions.jsonl`, the first `aim`, `fire` or `melee` after ten seconds without one). Widen the set towards thirty threats and thirty calm scenes, on foot, and prefer onsets before which Kerim held no answering input for two seconds, so that his reaction counts; keep the rule that an input held before the onset voids a try, and report beside it his first newly pressed answering input after the onset, named as the looser reading that it is. Every onset is set from the frames as in P62 and a scene whose onset cannot be told within two frames is left out. Scenes in a vehicle stay out until they have an answer set of their own; say how many there would be. Say plainly how many scenes there are in the end and what footage would be needed for more.

The model head. Codex has no quota left today, so `head --codex` is not run. Model its delay from what real sessions logged (`head.jsonl` under `/Users/kerim/recordings/pilot/`, request to response) and mark the row as modelled with the source of the delay.

Then run every way of control over the whole set in real time, one try at a time, rebuild the board with Kerim's row, and rewrite the report's summary so that its first paragraph answers: how fast is each way of control at noticing and at answering, how often is it wrong, and what holds the pilot back today.

## Your files

`pilot/src/pilot/reaction.py`, `pilot/src/pilot/approaches.py`, `pilot/tools/reaction.py`, `pilot/tests/test_reaction.py`, `lab/reaction/` and `docs/reports/P62-the-reaction-bench.md`, which you continue under a heading of its own. Nothing else. The rules of `docs/tasks/README.md` hold: no git writes, never the daemon on port 9395, no `ps5rp`, no `PS5_HOST`, recordings are read and never written. Somebody is playing on the console while you work and this Mac records it: run one replay at a time, nothing in parallel, and do not run the full gate; the reviewer runs it afterwards. Keep `lab/reaction/` under 5 MB and remove what you put under `/tmp`.

## Done when

`env -u PS5_HOST .venv/bin/python -m pytest tests/test_reaction.py -q` and ruff pass in `pilot/`, with tests for the two times, for the fixed-answer question's parsing and for Kerim's looser reading; the board holds the real judge's rows; and the report has the judge's times and how often it was right, the causes of the readers' misses with their counts, the size of the scene set, and the summary described above.
