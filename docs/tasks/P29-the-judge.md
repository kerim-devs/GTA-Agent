# P29: The judge

## Why

The head answers in five and a half to nine seconds. Between two of its answers nothing decides, and what the readers cannot tell stays untold. A small vision model on a gaming PC in the same network answers six fixed questions about a frame in a quarter of a second (`docs/LOG.md`, 11 November, "The judge, measured", and `lab/judge/`). This card puts that model beside the loop: asked about four frames a second, never waited for.

Its first job is one the pilot gets wrong today. The pilot takes a flat minimap for "on foot" and a tilted one for "in a vehicle", and with stars the game shows the tilted map on foot as well. On foot with the police after it the pilot believes it sits in a car: the scene detector reports `vehicle_enter`, `enter_vehicle` stands still until its time is up, `punch` refuses with "player is in a vehicle". The model names how the figure moves correctly on 99.4 percent of 181 hand-labelled frames, every one of the tilted ones among them.

Read `lab/judge/README.md` and the log entry first, then `objects.py`, whose `Reader` is the pattern for a model that runs beside the loop.

## What to build

A module `pilot/src/pilot/judge.py`. It owns the questions, the request and the parsing, word for word as `lab/judge/questions.py` has them today, because asked together questions change each other's answers and only this exact request has been measured: the system prompt, the six questions in one user message after the picture, the frame scaled to a width of 640 as a JPEG of quality 90, temperature 0, log-probabilities on. The scripts in `lab/judge/` then import all of that from the package, and `questions.py` goes.

A judge is polled once per tick with the frame and its capture time, as the object reader is. It starts a request when none is running and a quarter of a second has passed since the last one began, and hands back each answer once. It never makes the tick wait: encoding and the request run in its own thread, and a server that hangs holds up nothing. An answer is a `Judgment`: the capture time of the frame it is about, for every question the answer's value and its probability (the share of the answer's letter among the letters that question allows, from the log-probabilities), the seconds the request took and which server answered.

The servers are given in order of preference, each a base URL with a model name. A request that fails or takes longer than a second is dropped, the next server is tried, and a server that failed is left alone for two seconds. The judge sends frames only to addresses it was given, and it refuses at construction any address that is not this machine or a private network address written as numbers. With no server given there is no judge and the pilot behaves as today.

How the figure moves becomes a fact the pilot can use. `Observation` gets the newest `judgment` and an accepted `mode`: `"foot"`, `"vehicle"`, `"none"` or `None`. A mode is accepted when two judgments in a row name it, or one names it with a probability you choose from the recorded sequences, and it lapses to `None` when the newest judgment is about a frame older than a second. `None` means "ask the minimap as before". One function in `contract.py` answers how the figure moves for everyone: the accepted mode where there is one, the minimap class otherwise.

The conductor uses that function where it asks today whether the figure is on foot (the carry between two plans), tells the head when the accepted mode changes, with an event `mode_changed` that carries the old and the new mode, and hands the head the newest judgment with its age. `head_prompt.txt` says in two sentences what the judgment is and that its `mode` outranks the minimap class. The skills are not touched in this card: `skills.py`, `level.py`, `vehicle_entry.py`, `punch.py`, `combat.py` and `scene.py` follow in a card of their own once this one is merged.

Every judgment is a row in `judge.jsonl` in the session's directory: the time, the frame's capture time, the answers with their probabilities, the seconds, the server and the accepted mode after it. A failed request is a row too.

`pilot play` takes `--judge URL=MODEL`, given once per server in order of preference.

## Judging it

There is no network in your sandbox and no sockets, so no test starts a server: the judge takes its transport the way `Bridge` does, and the tests hand it one.

Real answers are recorded for you. `lab/judge/sequences/` holds four stretches of Kerim's recording `/Users/kerim/recordings/kerim/20261111-065022`, asked every fifteenth frame, with the server's reply as it came in every row: on foot, pulling a driver out of a car and driving off (frames 1300 to 2600), getting out again (9700 to 10200), a police car he does not get into (14900 to 15300), and on foot with a star and the tilted map (15600 to 17400). `lab/judge/results/` holds the answers to the 210 sampled frames.

Report from the sequences: how often the raw answer for the mode changes from one judgment to the next and how often the accepted mode does; how many seconds after the first frame on which a person would say "now he drives" and "now he is on foot" the accepted mode says so (look at the frames); and on how many of the asked frames the accepted mode differs from what `minimap.read` says about the same frame, with the stretch from 15600 to 17400 on its own. Choose the probability for accepting a single judgment from these numbers and say why.

Pin with tests, on the recorded replies: a reply becomes the six answers with probabilities that sum to one over each question's letters; a reply with a letter missing or a letter the question does not allow yields no answer for that question and no accepted mode; the stretch with the tilted map is accepted as on foot throughout. And on a fake transport: a request that hangs holds up no poll and is dropped after a second; a failing first server hands over to the second and is left alone for two seconds; nothing is sent after `close`; an address outside this machine and the private ranges is refused. On the conductor: a change of the accepted mode reaches the head as one event and one flicker of a single judgment does not; without a judge every existing test passes unchanged.

## Your files

`pilot/src/pilot/judge.py` (new), `contract.py`, `conductor.py`, `cli.py`, `head.py`, `head_prompt.txt`, `pilot/tests/test_judge.py` (new) and the tests of the files you change, `lab/judge/`, and your report. Not the skills named above, not `loop.py`, `flow.py` or `hud.py`.

## Done when

The tests above pass and the default gate is green. The report has the numbers from the sequences, the probability you chose, and what a session with `--judge` writes into `judge.jsonl`. It also says what you could not verify without the server; the reviewer repeats the measurement of `lab/judge/measure.py` through the moved code and runs the judge against the live server.
