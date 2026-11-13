"""The left stick of Kerim's controller jumps to the left by itself; this counts it and takes it out.

    lab/sticks/spikes.py count [RECORDING ...]     a line per recording; all of Kerim's without one
    lab/sticks/spikes.py clean RECORDING ...       what would be taken out of each controller log
    lab/sticks/spikes.py clean --apply RECORDING ...   takes it out

What was measured on 13 November, on the four recordings of that night (80 minutes): an excursion
of the left stick's x, from the first event past half way until it is back within a fifth, lasted
under 80 ms 1128 times to the left and 5 times to the right, and began with a step of more than
half the stick's way between two events, ten milliseconds apart, 1091 times to the left and twice
to the right among those under a quarter of a second. Most go to the full -1.0 from a stick at
rest or held forward, with y not moving. A hand does neither: to the right, which is the hand
alone, a tap lasts 120 ms and more and climbs over three to six events. The rate has risen from
one or two a minute on 11 November to ten to eighteen on the 13th; the right stick shows none.

So an excursion to the left is the stick's own, and not Kerim's, when it is shorter than SHORT, or
shorter than LONG and begun with a step of more than STEP. `clean --apply` writes the controller
log without them: the x of those events is put back to what it was before the excursion, every
other field and every line stays, the log as recorded is kept beside it as `pad.raw.jsonl`, and
what was taken out is listed in `pad.spikes.json`. Longer pulls to the left that begin with such a
step are listed there as doubtful and left in: a glitch at the start of a real turn looks the same.
The picture is not changed: the game answered what it was sent.
"""

import json
import os
import sys
import time
from pathlib import Path

RECORDINGS = Path("/Users/kerim/recordings/kerim")
PAST, BACK = 0.5, 0.2  # an excursion: from past half way until back within a fifth
SHORT, LONG, STEP = 0.08, 0.25, 0.5


def events(path):
    """The lines of a controller log; a last line cut off by a recording still running is left out."""
    rows = []
    for line in Path(path).read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            break
    return rows


def excursions(rows, sign, stick="left"):
    """Excursions of a stick's x to one side among the human's events: each as the positions of
    its first event, of the first event back, and of the last event before it began."""
    human = [index for index, row in enumerate(rows) if row.get("src") == "human"]

    def x(position):
        return rows[human[position]][stick][0] * sign

    found, at = [], 1
    while at < len(human):
        if x(at) > PAST and x(at - 1) <= PAST:
            end = at
            while end < len(human) and x(end) > BACK:
                end += 1
            before = at - 1
            while before > 0 and x(before) > BACK:
                before -= 1
            if end < len(human):
                first, back = rows[human[at]], rows[human[end]]
                found.append(
                    {
                        "t": first["t"],
                        "seconds": round(back["t"] - first["t"], 4),
                        "step": round(
                            max(x(k + 1) - x(k) for k in range(before, at)), 2
                        ),
                        "peak": round(max(x(k) for k in range(at, end)), 2),
                        "rows": [human[k] for k in range(before + 1, end)],
                        "before": rows[human[before]][stick][0],
                    }
                )
            at = max(end, at + 1)
        else:
            at += 1
    return found


def own(excursion) -> bool:
    """The stick's own and not a hand's."""
    return excursion["seconds"] < SHORT or (
        excursion["seconds"] < LONG and excursion["step"] > STEP
    )


def count(folders):
    print(
        "recording         minutes   left stick: its own to the left, to the right | right stick: left, right"
    )
    for folder in folders:
        rows = events(folder / "pad.jsonl")
        human = [row for row in rows if row.get("src") == "human"]
        if len(human) < 500:
            continue
        minutes = (human[-1]["t"] - human[0]["t"]) / 60
        tally = [
            sum(own(e) for e in excursions(rows, sign, stick))
            for stick in ("left", "right")
            for sign in (-1, 1)
        ]
        agent = sum(row.get("src") == "agent" for row in rows)
        print(
            f"{folder.name}  {minutes:6.1f}   {tally[0]:5d} ({tally[0] / minutes:4.1f} a minute)  {tally[1]:3d}"
            f"   | {tally[2]:3d} {tally[3]:3d}"
            + (f"   agent events {agent}" if agent else "")
        )


def clean(folder, apply):
    raw, log = folder / "pad.raw.jsonl", folder / "pad.jsonl"
    source = raw if raw.exists() else log
    video = folder / "video.mp4"
    if (
        not (folder / "meta.json").exists()
        or not video.exists()
        or time.time() - video.stat().st_mtime < 120
    ):
        print(f"{folder.name}: still being recorded, left alone")
        return
    lines = source.read_text().splitlines()
    rows = events(source)
    if len(rows) != len(lines):
        print(f"{folder.name}: a line of the log cannot be read, left alone")
        return
    left = excursions(rows, -1)
    taken = [e for e in left if own(e)]
    doubtful = [e for e in left if not own(e) and e["step"] > STEP]
    cleaned = [dict(row) for row in rows]
    for excursion in taken:
        for index in excursion["rows"]:
            cleaned[index]["left"] = [excursion["before"], rows[index]["left"][1]]
    seconds = sum(e["seconds"] for e in taken)
    print(
        f"{folder.name}: {len(taken)} excursions to the left that are the stick's own, {seconds:.1f} s in all; "
        f"{len(doubtful)} longer ones that begin with a jump are left in"
    )
    if not apply:
        return
    # Nothing but the x of the left stick on those events is another, and nothing is the stick's own after it.
    touched = {index for e in taken for index in e["rows"]}
    for index, (old, new) in enumerate(zip(rows, cleaned, strict=True)):
        same = {**old, "left": None} == {**new, "left": None} and old["left"][1] == new[
            "left"
        ][1]
        assert same and (index in touched or old == new), (folder.name, index)
    assert not [e for e in excursions(cleaned, -1) if e["seconds"] < SHORT], folder.name
    # To the right nothing is added; a push to the right that a jump to the left had cut in two is one again.
    assert {e["t"] for e in excursions(cleaned, 1)} <= {
        e["t"] for e in excursions(rows, 1)
    }, folder.name
    if not raw.exists():
        os.link(
            log, raw
        )  # the log as recorded, under its second name before the first is given away
    fresh = folder / "pad.jsonl.new"
    fresh.write_text("".join(json.dumps(row) + "\n" for row in cleaned))
    os.replace(fresh, log)
    assert events(raw) == rows and events(log) == cleaned
    note = {
        "tool": "lab/sticks/spikes.py",
        "rule": {
            "short": SHORT,
            "long": LONG,
            "step": STEP,
            "past": PAST,
            "back": BACK,
        },
        "taken_out": [
            {k: e[k] for k in ("t", "seconds", "step", "peak")} for e in taken
        ],
        "doubtful_left_in": [
            {k: e[k] for k in ("t", "seconds", "step", "peak")} for e in doubtful
        ],
        "agent_events": [row["t"] for row in rows if row.get("src") == "agent"],
    }
    (folder / "pad.spikes.json").write_text(json.dumps(note, indent=1) + "\n")


if __name__ == "__main__":
    command, *rest = sys.argv[1:] or ["count"]
    apply = "--apply" in rest
    named = [Path(name) for name in rest if name != "--apply"]
    folders = named or sorted(
        path for path in RECORDINGS.glob("2026*") if (path / "pad.jsonl").exists()
    )
    if command == "count":
        count(folders)
    elif command == "clean" and named:
        for folder in folders:
            clean(folder, apply)
    else:
        sys.exit(__doc__)
