# P58: The bench: every capability named, tried in a loop, every failure sorted

## Why

Kerim's order of 12 November, afternoon: the pilot still plays badly, and from now on the work goes by single things with clean names, walking from one point to another, finding the way to a place, getting into a car, each of them tried in a loop by a script, so that it is known where it fails every time and exactly that is improved. "Very, very important."

The seed exists. `lab/live/basics.sh` runs five steps, each as a session of its own with a fixed plan and the scripted head (`pilot.cli play --head scripted --plan ...`), and `lab/live/basics.py` counts them from the sessions' logs; `/Users/kerim/recordings/pilot/basics.tsv` lists about sixty tries of 12 November (cycle, step, session folder). What it lacks is what Kerim asks for: a catalogue that names every capability and says what counts as done, a start state that is checked, a proof that does not take the skill's word (on 12 November `set_waypoint` reported a waypoint that a second press had removed again), a class for every failure that says which part of the pilot was at fault, one ledger over all tries with the version of the code, and a board that shows where it hurts.

Read `PLAN.md`, `docs/LOG.md` from "The basics, measured", `lab/live/basics.sh`, `lab/live/basics.py`, `lab/live/next_place.py`, the skills in `pilot/src/pilot/` with every reason they can end on, `pilot/src/pilot/goals.py`, and three or four session folders of 12 November under `/Users/kerim/recordings/pilot/` to see what a log holds (`play.jsonl`, `head.jsonl`, `judge.jsonl`, `frames.jsonl`, `video.mp4`).

## What to build

A module `pilot/src/pilot/bench.py` and a tool `pilot/tools/bench.py` beside the other tools, with these parts.

The catalogue, as data in one place. A capability has an id, a group, a title in English and one in German (the board is read by Kerim, whose language is German; these titles are the only German in the code), the start state it needs, the plan that tries it, the seconds a try gets, the proof, and the mark, nine of the last ten counted tries unless said otherwise. The first catalogue:

| id | German title | start | done when |
| --- | --- | --- | --- |
| `foot.view` | Sicht einstellen | on foot | the far view from behind the figure stands at the end |
| `foot.walk` | Laufen | on foot | walked along the road for 20 s, moving on most ticks, never held for 3 s |
| `foot.walk_to` | Zu einem Punkt laufen | on foot, a blip or waypoint on the minimap | within 10 m of it |
| `foot.roadside` | Am Straßenrand bleiben | on foot | never standing or waiting on the carriageway |
| `foot.enter` | Einsteigen | on foot | seated within 20 s in a vehicle that stood still and had no driver |
| `car.leave` | Aussteigen | seated | on foot at the end |
| `car.follow` | Der Route folgen | seated, a route | 100 m nearer within 30 s and never standing for 5 s |
| `car.arrive` | Ankommen | seated, a route | stopped within 30 m of the destination and said so |
| `car.free` | Sich befreien | harvested | moving again within 10 s of being held |
| `car.turn` | Wenden | seated, the route behind | heading along the route within 15 s |
| `map.open_close` | Karte auf und zu | the game | the map was open and the game is back, nothing left open |
| `map.place` | Ort aus der Liste wählen | the game | a waypoint on a real place of the legend, a route on the minimap afterwards |
| `map.mission` | Missionsziel wählen | the game | the same for a mission's entry |
| `goal.keep` | Ein Ziel halten | the game | a goal ends by its own condition or a listed event, not by a replaced plan |
| `incident.menu` | Fremdes Menü schließen | harvested | the game is back within 5 s |
| `incident.down` | Nach Tod oder Verhaftung weiter | harvested | playing again within 30 s of the respawn |
| `incident.wanted` | Sterne loswerden | harvested | no stars within 3 minutes |
| `chain.basic` | Grundkette | on foot | in a vehicle, a place chosen, driven there, arrived, out, in one session |

A capability whose skill does not exist yet, or whose proof the log cannot give, stays in the catalogue and shows on the board as not built or not measurable, with the reason; do not leave one out and do not invent a proof. "Harvested" means it cannot be staged: every drive, walk or free session in the ledger is searched for the moments that are tries of it (a car held, a menu opened, a death), and each is a try.

The start state and the way into it. What a try needs is read from the first second of its own session, as `basics.py` does for "on foot at the start"; a try that did not start in its state is not counted, and says so. The loop knows the state from the end of the session before, or from a short session that only waits, and where the state is missing it gets there by running the capabilities that produce it as tries of their own, which are judged and written to the ledger like any other: a vehicle by `foot.enter`, a route by `map.place`, on foot by `car.leave`.

The proof. A function of the session folder that answers whether the thing happened, with its numbers, from the readings in the log and not from the status the skill returned. Skill and proof together give the outcome: both say yes, `ok`; the skill says done and the proof says no, failed with the cause `proof` (a false success, the worst kind); the skill failed and the proof says it happened, failed with the cause `proof` as well (it worked and the pilot did not know); both no, failed with a cause from the list below. Say for each capability what the proof reads and how far it is independent of the skill; where the log lacks a field a proof needs, name the field and where it would be written, and leave the module that writes the log alone.

The cause, one of seven, the same for every capability, because the question is which part to repair: `see` (a reader, the detector or the judge had the picture wrong or had nothing), `decide` (the wrong target or skill, a plan replaced, a start nobody checked), `act` (seen and decided rightly, and the movement did not do it: held, past the target, a press without effect, out of time while trying), `proof` (above), `world` (the game came between: run over, attacked, stars, a mission's event, a death), `tech` (the bridge, the stream, gaps in the frames) and `unclear`. List every reason each skill can end on, from the code, and map it; where one reason covers several causes, such as a time limit, decide by what the log shows (no vehicle ever detected is `see`, a target approached and never reached is `act`), and say `unclear` rather than guess. `world` is told from the log where it can be: health falling, stars appearing, the banners for a death, an arrest and a failed mission. The share of `unclear` is shown on the board; aim below one in ten on the tries of 12 November.

The ledger: one line per try in a file that only grows, by default `/Users/kerim/recordings/pilot/bench.jsonl`, with the capability, the time, the commit of the code and whether the tree was dirty, the session folder, whether the start state held, the outcome (`ok`, `failed`, `not_counted`), the cause, the skill's reason, the seconds and the proof's numbers. `bench.py judge <session> --capability <id>` judges a session that exists, so the ledger can be rebuilt when a proof changes, and `bench.py import <basics.tsv>` takes over the tries of 12 November. A person or a reviewer can overrule a line: `bench.py mark <session> --outcome ... --cause ... --note ...` writes to a second file beside the ledger, and the board applies it and shows that it was marked.

The loop: `bench.py run <id>... --tries 10` replaces `basics.sh`. It starts a try only when the bridge reports the session up, no human input and no recording, ends a running try at once when a controller reports input and does not count it, gets into the start state as described, runs the plan as `basics.sh` does, judges the session and appends the line. A capability that failed three times in a row for a cause of `tech` stops the loop with a message. By default it does not run while a mission is active: say what the log offers for telling that (the objective text, the mission's route or blip), build the guard if it can be told and a flag that lifts it, and if it cannot be told say what is missing. Everything that talks to the bridge or starts the pilot goes through two small functions that the tests replace; you cannot run them and must not try.

The board: `bench.py board` prints, and writes as one Markdown file and one HTML file without outside assets, per capability its state (green at the mark, red below it, too few tries, not built, not measurable), the rate over the last ten counted tries and over all, the median seconds, the causes of its failures with counts, the three most frequent reasons, and the folders of its newest failures; under it one ranking over everything, (capability, cause, reason) by count, which is the list of what to repair next; and the rates by commit, so that a repair shows as before and after. The HTML shows for each failure a small sheet of four frames of its session, the last among them, which `bench.py` cuts from the video into a folder beside the ledger, so that a failure can be judged at a glance.

## Added at 14:20, after the worker had started

Kerim accepted the catalogue and added three demands; the reviewer builds them on top of the worker's result. The pilot may also play inside a running mission now, so the mission guard is off by default and becomes a flag, and the ledger notes for every try whether an objective was on the screen.

Easy to extend. A new capability is one entry in the catalogue and, where none of the existing proofs fits, one small proof function; nothing else changes, and a test adds an entry that way. The proofs are built from a few named pieces (seated at the end, on foot at the end, the distance fell, a route is there, the game's screen is back) that an entry combines. `lab/bench/README.md` says in a page how to add a capability, a start state, a proof and a cause, with one worked example.

Runs by itself. `bench.py run all --minutes 90` goes through the catalogue in the order of the chain without anyone watching: a try that fails, a pilot process that dies, a bridge that does not answer and a person who takes the controller do not end the loop; it waits, goes on, and stops when the minutes are used up. Before every try a small input ends the game's idle camera, which shows the figure from somewhere else after half a minute without input and misleads every reader. A status file beside the ledger says at any moment what the loop is doing, since when, and its last line, so that one look tells whether it lives or hangs.

Leaves a report that points. Every run of the loop writes a report of its own beside the ledger, as Markdown and JSON: what was planned, what ran, what was skipped and why; the loop's own errors apart from the pilot's failures, with the traceback, so that "the loop did not work there" is never mistaken for "the pilot failed"; the board before and after the run; and for every failure a pointer that saves the search: the capability, the cause, the skill's reason, the session folder, the second of the video at which it went wrong and how that second was found, what the readers said at that moment against what the proof saw, the picture of that moment, and one line that says where to look first. The run's last line is its summary in a sentence, with the worst capability and its most frequent cause.

## Judging it

Import the tries of 12 November with the ledger and the sheets written under `lab/bench/` in your worktree (the sessions are read, never written), and show the board they give. Compare your outcome with what `basics.py` says for the same tries and with the log's account of that day; look at every try where your proof and the skill disagree, by its frames, and say which was right. Give the share of `unclear` and what would lower it. Tests for the proofs on small logs written in the test, for the outcome table, for the mapping of causes, for the loop against a model of the bridge and the pilot (a person takes the controller in the middle of a try, the start state is missing and gets made, three `tech` failures stop it, a mission is active), and for the board's ranking.

## Your files

`pilot/src/pilot/bench.py`, `pilot/tools/bench.py`, `pilot/tests/test_bench.py`, `lab/bench/` and your report. Nothing else: not `cli.py`, not the skills, not the conductor or the loop, which others are changing; what you need from one of them is described exactly and left. `lab/live/basics.sh` and `basics.py` stay as they are. The console is in use while you work: the rules of `docs/tasks/README.md` about the daemon hold without exception, and nothing under `/Users/kerim/recordings/` is written, moved or deleted, the ledger's default path included. Keep `lab/bench/` under 5 MB.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green or fails only where your sandbox refuses sockets, Vision or CoreML, which you then name test by test, and the report shows the catalogue with what each proof reads, the mapping of every skill's reasons to causes, the board from the tries of 12 November, the disagreements between proof and skill, and the exact commands the reviewer runs on the console for the first full round.
