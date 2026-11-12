# P60: The eye for the roadside and the parked car

## Why

Two of the eighteen capabilities Kerim accepted on 12 November are "stays at the roadside" and "gets into a parked, empty vehicle within twenty seconds", and neither holds on the console. P57 built both on the minimap, and the minimap tells lane from side on one tick in nine; for the rest the pilot does not know where the figure stands, and it tells a driver in a car on three occasions of eight.

What that looks like, all on 12 November under `/Users/kerim/recordings/pilot/` (`play.jsonl`, `frames.jsonl`, `video.mp4`): in `20261112-143714` the figure stands on the pavement at Sandy Shores by day in the far view, presses at 8.9 s for a pickup with a boat trailer that drives past, walks down the carriageway after it from 17 s, presses at 35.8 s beside it where it waits at the junction, presses at 44.5 s at a car that drives towards it, ends `failed vehicle out of reach; saw 42 vehicles (rejected 0, avoided 0, moving 5)` and is left standing in the middle of the junction. In `20261112-143128` it looks for a vehicle on a highway at night and is killed by traffic, and the skill reports `entered vehicle`. In `20261112-142428` it gets out on the highway at 240 s to find somebody to fight and is run over at 277 s. In `20261112-143929` the same skill sat in a car 3.7 s after one press.

The project has an eye that is not used for this: the judge, a small vision model on a gaming PC (`http://192.168.0.248:1234`, model `qwen/qwen3-vl-8b`, the OpenAI-compatible API of LM Studio, asked as `pilot/src/pilot/judge.py` asks it), which answers a fixed question with one of a few fixed answers in about a quarter of a second and already tells the skills how the figure moves. Whether it can tell where the figure stands and which vehicle is parked is not known. Measure it, and if it can, let it.

Read `PLAN.md` on the judge, `docs/LOG.md` on the judge and from "The basics, measured", the reports of P29, P33, P53 and P57, `pilot/src/pilot/judge.py`, `foot.py`, `vehicle_entry.py`, and how an answer of the judge reaches a skill.

## What to build

First the measurement. A set of frames with labels by eye, kept small and stored under `lab/where/`: about 300 on foot for where the figure stands (on the carriageway; on a pavement, verge or roadside; on open ground or a yard; inside), taken from today's sessions of the pilot and from Kerim's recordings (`/Users/kerim/recordings/kerim/`, sections in `/Users/kerim/recordings/derived/kerim/*/sections.json`), by day and by night, in town and in the country, in the far view and in the others; and about 200 vehicles as the detector boxes them, labelled parked and empty, standing in traffic (in a lane, at a light, a driver in it), or driving. Ask the judge both questions on them: wordings, the whole frame against a crop around the figure or the vehicle with some of its surroundings, one question or two. Give for each the confusion table, the time an answer takes, and how the probability the judge returns relates to being right. The marks: carriageway against not carriageway right on nine frames of ten, and at most one frame in twenty on the carriageway called safe; a vehicle in traffic or driving called parked at most once in ten. Try a third question the skills need as well: on which side the nearer edge of the road lies (left, right, cannot tell). If the judge misses a mark, say by how much and where, try the smaller model on the Mac that `judge.py` falls back to, and say what else in the picture could tell it; do not wire in an eye that does not see.

Then, for what met its mark, the wiring. The judge is asked these questions beside the loop while the figure is on foot, never waited for, as its other questions are, and the answers reach `walk_road` and `enter_vehicle` as evidence with their age. Where the map is silent, the judge's word decides; where both speak and disagree, the figure is treated as on the carriageway. What the skills do with it:

- On the carriageway and not on the way to a vehicle it may take, the figure leaves it first, towards the nearer edge, before it looks, waits or presses anything.
- It walks onto the carriageway only to a vehicle that stands, and with `occupied: avoid` only to one called parked. A vehicle that drives or waits in traffic is never followed down the road: the search goes on along the roadside.
- A press is made beside a vehicle within reach as now. After three presses without a seat the skill does not go on pressing at traffic.
- Whatever way the skill ends, done, failed or out of time, it does not leave the figure standing on the carriageway: it steps to the edge first, within its time, and its reason says where the figure stands at the end.
- With no judge answering, the behaviour is the present one, and the reason says that the eye was missing.

The proof of `enter_vehicle` gets a second look: in `20261112-143128` it reported a seat while the figure died. Find what it took for a seat and repair it.

## Judging it

The tables above. The changed skills in the model game the tests of `vehicle_entry.py` and `foot.py` use, extended by a judge that answers as measured, wrong as often as measured and late: the pickup that drives past and waits at the junction (not followed), a parked car across the road (crossed to and taken), a start in the middle of the road (left first), an ending out of time on the road (the edge first), no judge. Replay the entry stretch of `20261112-143714` with the recorded detections and the judge's real answers on its frames, and say tick by tick where the new skill would have decided differently; the recorded figure does not follow, say that. The automated tests never ask the server: they use stored answers.

## Your files

`pilot/src/pilot/judge.py` for the questions and how they are carried, a new `pilot/src/pilot/where.py` if the evidence wants a home, `pilot/src/pilot/foot.py`, `pilot/src/pilot/vehicle_entry.py`, their tests, `lab/where/` (under 6 MB) and your report. Not `drive.py`, `skills.py`, `goals.py`, `mission.py`, `conductor.py`, `camera.py`, `minimap.py` or `bench.py`, which others are changing right now; if an answer of the judge cannot reach a skill without one of them, describe the change exactly and leave it. You have the network for one thing only, the judge at `192.168.0.248:1234`: nothing else is fetched, installed or sent anywhere. The console is in use: the rules of `docs/tasks/README.md` about the daemon hold without exception, and nothing under `/Users/kerim/recordings/` is written, moved or deleted.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green or fails only where your sandbox refuses sockets, Vision or CoreML, which you then name test by test, and the report shows the labelled sets, the judge's tables and timings for the three questions, what was wired in and what was not and why, the model game's cases, the replay of the entry stretch, and what the try on the console should look at first.
