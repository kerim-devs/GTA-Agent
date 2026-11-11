# P39: What a mission asks for

## Why

The head of rules (P30) decides the plain cases from the objective the game prints and from what the readers see. On 173 recorded cases it decides 94, and the corpus it was built on, `lab/mission/`, says of itself that it holds no failed skill, no German order to fight and no instruction to walk to a mission letter. What the game asks for in a mission, in which words and in which order, and what a player then does, is in Kerim's own play: on the afternoon of 11 November he played 53 minutes with the recorder running and his controller on the Mac, in `/Users/kerim/recordings/kerim/20261111-164039`, `20261111-165543`, `20261111-171046` and `20261111-172549`. The plan forbids rehearsing a mission by hand. This card does not rehearse: it turns recordings into every text the game printed, what he did under each objective, and where the rules would have done something else.

Read `PLAN.md`, in `docs/LOG.md` the entries of 11 November, `pilot/src/pilot/scene.py` (`TextReader`, `EventDetector`), `pilot/src/pilot/mission.py`, `pilot/src/pilot/head.py` (`HeadRequest`), and `lab/mission/README.md` with `read_frames.py`, which already builds requests for the rules from frames of a recording.

## What to build

`pilot/tools/texts.py <recording>... --out DIR` reads the screen text of a recording twice a second and writes `DIR/<recording name>/texts.jsonl`: one line for every text for as long as it stands, with its kind (objective, help, subtitle, banner), the text, and the first and last second on the clock of `frames.jsonl`. The same text read slightly differently on the next sample is the same text; `scene.py` has the comparison. An hour of recording has to be read in twenty minutes in one process. The text reader needs the native macOS frameworks. If your sandbox refuses them, say so in the report at once, with the error, and build and test the rest against the cached readings you can make or find; do not replace the reader with another.

`pilot/tools/mission_notes.py` joins the texts with the sections of P38 and writes `missions.json`. P38 is built at the same time, so its file may not exist: its format is in `docs/tasks/P38-sections-of-a-recording.md`, and where you need sections write them by hand in exactly that format and say so. A mission runs from its first objective to the banner that ends it or to a minute without an objective. Each step holds the objective's words, how long it stood, what he did under it (the kinds of the sections, the colours of route and blips on the minimap, the highest wanted level, and from the controller whether he drove, ran, aimed or fired), and how it ended: the next objective, passed, failed, dead. Each mission also carries `notes`, at most 600 characters of plain English that a head can be given: the steps in order in the game's own words.

Then the cases. For every step build the request the head would have got a few seconds into it, as `lab/mission/read_frames.py` does, ask `MissionHead` with rules only and no model, and set the first skill of its plan against what Kerim did. Write `cases.md` with one line per step and the counts: decided as he did, decided differently, left to the model. The steps of the last two kinds, with their German objective, are what this card is for. Do not change `mission.py`: propose rules in the report, objective pattern and plan, in the order of how often the recordings ask for them.

## Judging it

Run it over the four folders of the afternoon and over `/Users/kerim/Documents/ChatGPT/gta/recordings/20261110-093238`, 696 s over Wi-Fi with a shootout that fails and is retried and a drive along the yellow route. For `20261111-164039` and `20261110-093238` check the texts by hand against a contact sheet of the frame at every change, which goes into `lab/notes/`: every objective that stood two seconds or more is found once, its start within a second, and at most one text in ten is a second reading of the one before. Give the counts of the cases as they are; a low share decided as he did is a result, not a failure of the card.

Tests work on sequences of read text and of sections, not on video, and pin: one text read with small differences stays one line, a text that returns after a cutscene is a new line, a mission ends on its banner and on a minute of silence, a step without a controller says so and does not claim he stood still, and a missing `sections.json` is an error with a reason.

## Your files

`pilot/src/pilot/notes.py`, `pilot/tools/texts.py`, `pilot/tools/mission_notes.py`, `pilot/tests/test_notes.py`, `lab/notes/` and your report. Not `mission.py`, `scene.py`, `hud.py`, `head.py`, `head_prompt.txt` or anything in `lab/mission/`. Nothing under `/Users/kerim/recordings/` or `recordings/` is written, moved or deleted. Write the output for the five recordings to `lab/notes/out/`.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green, and the report shows the missions found in Kerim's 53 minutes with their steps, the check of the texts against the sheets, the table of cases with its counts, the rules you propose with the recordings that ask for them, and the minutes the text reader took per minute of recording.
