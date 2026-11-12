"""What the fast path and the survey would have seen in the pilot's own sessions of 12 November.

    pilot/.venv/bin/python lab/camera/survey.py

For every session of lab/camera/sessions: the opening seconds as the bands read them (what `Watch` would
have named, and when), then every stretch the recorded presses left, measured as the survey measures a
window (the second after the picture settled): a whole figure of some height, one cut by the lower
edge, none, or unclear. The presses are the recorded ones; nothing here presses anything.
"""

import json
from pathlib import Path

from pilot.camera import SetFarView, Watch, far_of, look_at, read_view
from pilot.contract import Detection
from pilot.objects import split_player

HERE = Path(__file__).resolve().parent
SHAPE = (720, 1280)


def readings(samples):
    """(time, ViewReading) of every stored sample, the figure cut out as the conductor does."""
    out = []
    for sample in samples:
        raw = tuple(Detection(d[0], tuple(d[1:5]), d[5]) for d in sample["dets"])
        kept, figure, vehicle = split_player(raw)
        vehicles = tuple(d for d in kept if d.kind != "person") + ((vehicle,) if vehicle else ())
        others = tuple(d for d in kept if d.kind == "person")
        out.append((sample["t"], read_view(figure, SHAPE, vehicles=vehicles, others=others)))
    return out


def opening(seen, seconds=SetFarView.FAST):
    """What the bands name within the first seconds: (view, time) of the first far, or what stood."""
    watch, named = Watch(), []
    for t, reading in seen:
        if t > seconds:
            break
        watch.add(t, reading)
        view = watch.view()
        if view is not None:
            named.append((view, t))
    return named


def stretches(seen, presses, settle=SetFarView.SETTLE):
    """The measurement of the second after each settle: before the first press, and after each."""
    edges = [0.0, *presses]
    looks = []
    for i, start in enumerate(edges):
        stop = edges[i + 1] if i + 1 < len(edges) else float("inf")
        first = start + (settle if i else 0.0)
        window = [r for t, r in seen if first <= t <= first + 1.0 and t <= stop]
        looks.append((first, look_at(window) if len(window) >= 4 else None))
    return looks


def main():
    sessions = json.loads((HERE / "sessions/pilot-sessions.json").read_text())
    for name, session in sessions.items():
        seen = readings(session["samples"])
        print(name, "recorded", session["recorded_result"], "presses", session["recorded_presses"])
        named = opening(seen)
        print(
            "  the first two seconds name:",
            named[:1] or "nothing",
            "far at",
            next((t for v, t in named if v == "far"), None),
        )
        looks = stretches(seen, session["recorded_presses"])
        print("  stretches:", [(round(t, 1), look.text() if look else "-") for t, look in looks])
        if len(looks) >= 4 and all(look for _, look in looks[:4]):
            print("  round of four:", far_of([look for _, look in looks[:4]]))


if __name__ == "__main__":
    main()
