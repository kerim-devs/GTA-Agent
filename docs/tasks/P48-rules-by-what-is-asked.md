# P48: Rules that decide by what is asked

## Why

P39 gave every objective a class out of fifteen (`notes.intent`: go_to, bring, enter_vehicle, take_out, follow, escape, steal, pick_up, wait, return_to, protect, destroy, use, sneak, unknown), with the wordings seen in Kerim's recordings and their synonyms, and no objective of 148 minutes of play is left unknown. The rules of the head in `mission.py` do not use it. They match single wordings of their own (`TAKE_OUT` is a pattern for "schalte ... aus"), and whatever they do not match falls to the rules for blips and routes. So an objective that says "Warte auf ..." is answered like any other with a route on the map: the pilot drives off, where Kerim stood still. The same holds for every wording the patterns do not know and the classes do.

Kerim's play now shows, objective by objective, what a person does when the game asks for each class: `/Users/kerim/recordings/derived/kerim/<name>/missions.json` holds the missions with their steps, class and times, `actions.jsonl` what he did second by second in eighteen labels, `sections.json` whether he drove, walked or watched.

Read `PLAN.md`, in `docs/LOG.md` the entries from 10 November on, the reports of P30, P39 (from line 53 for the classes), P41, P42 and P45, `pilot/src/pilot/mission.py` with its tests, `pilot/src/pilot/notes.py` (`intent` and its tables), `pilot/src/pilot/head_prompt.txt` and the cases under `lab/mission/` and `lab/take-out/`.

## What to build

First the measurement, from the derived data: for each class that occurs, what Kerim did in the first twenty seconds after the objective appeared and over the whole step, as shares of the action labels and of driving against walking, with the number of steps behind each figure. Say plainly where a class has too few steps to conclude anything.

Then the rules. The head decides on the class of the objective and no longer on a wording of its own: the class comes from `notes.intent`, the pattern `TAKE_OUT` and its like go, and a new wording is added in one place, the table. Per class the rule is what the measurement and the game's meaning support with the skills that exist: wait stays where it is and looks, without a route and without walking off, until the objective changes; take_out keeps what P41 built; go_to, return_to and bring keep the route; enter_vehicle goes to the vehicle; follow, steal, pick_up and use get the nearest fitting rule that exists and a sentence in the report on what skill is missing for them. An objective of class unknown reaches the fallback head as today. Stars and low health keep their precedence over every class.

A misread objective must not flip the class from one reading to the next: decide on the reading the consolidation of P39 would keep, or hold a class until a reading of another class has stood for a moment, and say which.

## Judging it

Run the changed rules over the 173 cases of `lab/mission/`, the cases of `lab/take-out/` and the recorded requests of P45 (`lab/foot/p45-decisions.json`), and list every case whose decision changes, with the reason; a change that is not explained by the class is a fault. Then, for every step of `missions.json`, build the request the pilot would have had at the moment the objective appeared (objective text, the section's mode; the minimap as far as the derived data has it, otherwise empty) and put the rule's first plan beside what Kerim did: one table, class by class, agreement in kind (stays, walks, drives, fights, enters). Tests pin one decision per class and the wait.

## Your files

`pilot/src/pilot/mission.py`, its tests, `lab/mission/` and your report. `notes.py` only to add a wording to the tables, with a test. Not `conductor.py`, `skills.py`, `foot.py`, `scene.py` or `cli.py`; a skill that is missing is described, not built. Nothing under `/Users/kerim/recordings/` is written, moved or deleted, and nothing large is written anywhere: the disk has little room left. The rules of `docs/tasks/README.md` about the daemon hold without exception.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green or fails only where your sandbox refuses sockets or CoreML, which you then name test by test, and the report shows the measurement, the changed cases, the table against Kerim's play and the skills that are missing, in the order in which they would help most.
