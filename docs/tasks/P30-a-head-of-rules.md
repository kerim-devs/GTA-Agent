# P30: A head of rules

## Why

The measure for the stream is that the story moves forward, and the head that decides what to do next takes five and a half to nine seconds per answer. Most of its answers are not hard. With a route on the minimap and the figure in a car it says `drive_route`; with stars it says get away; on foot with nothing to do it says get into a car, set a waypoint and drive. `pilot/src/pilot/head_prompt.txt` spells these rules out in prose, and a model then takes seconds to apply them.

This card writes the rules down as code, so that the plain cases are decided at once and the model is asked only where the rules do not know. The rules are about the game's loop and not about one mission: read what the game asks for, follow the marker or the route, fight what is red, lose the police, try again after a failure. No mission is named anywhere, because on 19 November the same loop has to carry GTA VI.

Read `PLAN.md`, `head.py` (the request the head gets and the response it gives), `head_prompt.txt`, `conductor.py` (when the head is asked and which events it is told), and in `docs/LOG.md` the entries of 11 November, where the paragraph "The head knows the new skills" lists what the model planned on recorded moments.

## What to build

A module `pilot/src/pilot/mission.py` with a head that satisfies the `Head` protocol: `decide(request)` returns a `HeadResponse` that passes `parse_response`.

It holds an ordered list of rules. A rule looks at the request only: the events, the texts on screen, the minimap reading, the HUD, the objects, the last skill and how it ended. The first rule that applies gives the plan and a short German sentence for the commentator that says what the pilot is doing and never claims what was not observed. When no rule applies the head asks a fallback head it was given, which is the Codex head in a session, and returns its answer; without a fallback it returns a plan that keeps the figure moving.

A rule decides only what the request can show. Where two readings of the request would lead to opposite presses, the rule does not apply and the fallback is asked. The case that matters most: with stars the game shows a vehicle's minimap on foot as well (the log, "What the measurement showed besides"), and `enter_vehicle` on a figure that already sits in a car makes it get out. So how the figure moves is answered by one function in your module, from the minimap class today, and it answers "unknown" for a tilted map with stars; the reviewer points that function at the judge once P29 is merged.

The rules to write are the ones the prompt states and the ones the recorded answers of the model show, among them: let a cutscene or a loading screen run; with stars get away and never fight, by the means that fit how the figure moves; with low health stop fighting and get away; follow a route in a vehicle; make a route when there is none; on foot go to what the game marks; fight red blips only when the game asks for it; do not repeat the call that just failed, change something first; after a failed mission and its retry, plan afresh. The objective, help and subtitle texts are German and come from text recognition with its errors; find the wordings in the recordings rather than guessing them, and match them tolerantly.

Say for every rule in a comment where it comes from: the line of the prompt, a recorded answer, or a recorded moment.

## Judging it

Build the cases from what is recorded, in a new folder `lab/mission/`. Every request the head was ever asked is saved with the model's answer in the `head.jsonl` of the sessions under `/Users/kerim/recordings/pilot/`, with the frame beside it. The Wi-Fi recording `/Users/kerim/Documents/ChatGPT/gta/recordings/20261110-093238` holds a whole mission with a failed attempt and a retry, a chase with stars, a drive along a route and a death; `lab/wiring/` has its screen text over time, and the readers of the package give the rest of a request for any of its frames. Kerim's recording `/Users/kerim/recordings/kerim/20261111-065022` has a stolen car, a chase with one and two stars and fist fights.

Report for every case which rule applied and its plan, next to what the model planned where its answer is recorded, and look at each difference: say whether the rule or the model is right, and change the rule or leave the case to the fallback. Report on how many of the cases a rule decides and on how many the fallback is asked.

Pin with tests: each rule on a real request from the cases; that a request no rule knows reaches the fallback unchanged and its answer comes back; that every plan a rule can give passes `parse_response`; that the stars rule never plans `enter_vehicle` when the request does not show the figure on foot, and never plans `fight`, `melee`, `punch` or `shoot`; that the same failing call is not planned twice in a row; that `decide` returns within a few milliseconds when a rule applies.

## Your files

`pilot/src/pilot/mission.py` (new), `pilot/tests/test_mission.py` (new), `lab/mission/` (new), and your report. Not `head.py`, `head_prompt.txt`, `conductor.py`, `cli.py`, `contract.py` or any skill; the reviewer adds the command-line choice.

## Done when

The tests pass and the default gate is green. The report lists the rules in their order with where each comes from, the table of cases, and the situations you met in the recordings for which no rule could be written and why.
