"""Replay the recorded detections of the pilot's own sessions through SetFarView; no console.

    pilot/.venv/bin/python lab/camera/replay.py

lab/camera/sessions holds the detector's output of the pilot's own sessions of 12 November, about ten
times a second, and what the skill did at the time. A press of the replayed skill does not act on a
recording, so the replay lets it step through the pictures the recorded presses made: the recorded
presses cut a session into stretches, one picture of the camera after each, and when the stretches
cover the four views the replayed skill's j-th press shows the stretch of the view j steps on. A
stretch is played from its press on, so the camera's own pace (the picture needs more than a second to
follow) is the recorded one. Only a session whose stretches are a round of four different views can
be replayed.
"""

import itertools
import json
from pathlib import Path

from pilot.camera import SetFarView, alike, look_at, read_view
from pilot.contract import Detection, Hud, Observation, Reading
from pilot.objects import split_player

HERE = Path(__file__).resolve().parent
SHAPE = (720, 1280)
FLAT = Reading("flat", "none", None, None, 0.0, False, 0.9)
ROUND = 4


def reading(dets):
    raw = tuple(Detection(d[0], tuple(d[1:5]), d[5]) for d in dets)
    kept, figure, vehicle = split_player(raw)
    vehicles = tuple(d for d in kept if d.kind != "person") + ((vehicle,) if vehicle else ())
    others = tuple(d for d in kept if d.kind == "person")
    return read_view(figure, SHAPE, vehicles=vehicles, others=others)


def cycle(session):
    """The recorded stretches: the one it began in, the four views the camera went through, and which
    of them it began in; None unless the last four stretches show four different views. A stretch
    ends where the next press was recorded, the last where the skill ended: after that the camera
    was levelled."""
    presses = session["recorded_presses"]
    ended = session["recorded_result"][0] if session["recorded_result"] else float("inf")
    edges = [0.0, *presses, ended]
    stretches = []
    for start, stop in itertools.pairwise(edges):
        stretches.append([(s["t"] - start, s["dets"]) for s in session["samples"] if start <= s["t"] < stop])
    if len(stretches) < ROUND or any(len(s) < 4 for s in stretches):
        return None
    looks = []
    for stretch in stretches[-ROUND:]:
        settled = [dets for o, dets in stretch if o >= 1.5][:10] or [dets for _, dets in stretch][-10:]
        looks.append(look_at([reading(dets) for dets in settled]))
    if any(alike(a, b) for i, a in enumerate(looks) for b in looks[i + 1 :]):
        return None
    return stretches[0], stretches[-ROUND:], (-(len(stretches) - ROUND)) % ROUND


def observation(t, stamp, dets):
    raw = tuple(Detection(d[0], tuple(d[1:5]), d[5]) for d in dets)
    kept, figure, vehicle = split_player(raw)
    return Observation(
        FLAT,
        False,
        t,
        objects=kept,
        objects_time=stamp,
        hud=Hud(),
        mode="foot",
        figure=figure,
        figure_vehicle=vehicle,
    )


def replay(session, skill=None, hz=30, seconds=60):
    """(end time, result, press times) of the skill, ticked at `hz`, on the session's own pictures;
    None for a session whose stretches are not a round of the four views."""
    found = cycle(session)
    if found is None:
        return None
    start, views, begin = found
    skill = SetFarView({}) if skill is None else skill
    presses, held = [], False
    for i in range(int(seconds * hz)):
        t = i / hz
        view = views[(begin + len(presses)) % ROUND] if presses else start
        offset = t - (presses[-1] if presses else 0.0)
        # the last detection of the stretch from before now; a stretch that ends holds its last picture,
        # and the detector goes on stamping it ten times a second
        shown = [d for o, d in view if o <= max(offset - 0.1, 0.0)] or [view[0][1]]
        result = skill.step(observation(t, max(0.0, int(t * 10) / 10 - 0.05), shown[-1]))
        down = result.pad.buttons == ("touchpad",)
        if down and not held:
            presses.append(t)
        held = down
        if result.status != "running":
            return t, result, presses
    return None, None, presses


def main():
    sessions = json.loads((HERE / "sessions/pilot-sessions.json").read_text())
    for name, session in sessions.items():
        out = replay(session)
        print(name, "recorded", session["recorded_result"], session["recorded_presses"])
        if out is None:
            print("  the stretches are not a round of four different views")
            continue
        end, result, presses = out
        print("  replayed", end, result and (result.status, result.reason), [round(p, 1) for p in presses])


if __name__ == "__main__":
    main()
