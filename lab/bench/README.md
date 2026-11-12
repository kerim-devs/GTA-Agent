# The bench in one page

`pilot/tools/bench.py` tries the pilot's capabilities one at a time, judges each try from the session's own record and not from what the skill said, writes one line per try into an append-only ledger and shows where it hurts. The code is `pilot/src/pilot/bench.py` (catalogue, outcome table, causes, ledger, board), `bench_proofs.py` (the named proof pieces and the readers they use on a stored session) and `bench_run.py` (the loop, the report, the dry run). Run everything from `pilot/` and always as `env -u PS5_HOST .venv/bin/python tools/bench.py ...`.

## Looking and running

`bench.py catalogue` lists every capability with its proof. `bench.py board` prints the board and writes `bench.md` and `bench.html` beside the ledger (`--ledger` moves it; the default is `/Users/kerim/recordings/pilot/bench.jsonl`). `bench.py run all --minutes 90 --dry` prints what an unattended round would do, try by try with the start state each needs, and touches nothing. `bench.py run all --minutes 90` does it: it waits while a person is on the controller or a recording runs, ends a running try with SIGINT the moment the bridge reports `human_input` (and does not count it), makes a missing start state by trying the capability that produces it, and survives a failed try, a dead pilot, a bridge that does not answer and an error of its own. `--guard-mission` makes it wait while an objective is on the screen; by default it plays inside a mission and the ledger notes for every try whether one was shown. Beside the ledger, `bench.status.json` says what the loop does now and since when, and `runs/<run id>/report.md` (with `report.json` and the pictures) is written after every try: what was planned, ran and was skipped, the loop's own errors with their traceback apart from the pilot's failures, the board before and after, and for every failure its capability, cause, the skill's reason, the session, the second of the video where it went wrong and how that second was found, what the readers said then against what the proof saw, the picture, and one line on where to look first. Its last line is the summary with the worst capability and the most frequent cause.

## Adding a capability

One entry in `CATALOGUE` in `bench.py`: an id, a group, an English title, the German title of the board, the start states it needs (names in `START_STATES`), the plan of the scripted head that tries it (`step("name", arg=...)`), the seconds a try gets, and the proof as named pieces. `vary=((step index, argument, (values...)),)` changes an argument from try to try, as `map.place` does with the place so that no waypoint is set twice on the same spot. `ends=` says which start states a try leaves (the dry run reads it), `level=False` skips the camera levelling where the map is the subject, `scramble=True` presses the touchpad before a try, `done_reasons=` lists the skill's reasons that count as done, `opening=True` is for a capability that is the session's own opening, and `built=False` or `harvested=True` keep an entry on the board as not built or not stageable. Nothing else changes: the loop, the dry run, the board and `catalogue` read the entry.

## Adding a proof piece

A proof is a list of pieces, `P("name", argument=value)`, that all have to hold. A piece is one function in `bench_proofs.py` that takes the `Try` and returns `Evidence(ok, numbers, missing, moment)`: `ok` is True, False or None for not measurable (then `missing` says which field of which log would make it measurable), and `moment` is the second where it went wrong and how it was found. Decorate it with `@piece`. A piece reads the record (`run.session.ticks`, `.requests`, `.judgments`, `.mode_over`, `.frame` and the readers on it) and never the skill's verdict. Where it proves a thing that began at some second, register `@since("name")` so that a failure can point at it. `P("unmeasured", what=..., missing=...)` keeps a part of the card's "done when" that no log can show: a success then stays unverified while a no of another piece still counts.

## Adding a start state and a cause

A start state is an entry of `START_STATES`: `StartState(check, producer, text)`, where `check(session, t0, t1, end=False)` answers True, False or None and `producer` names the capability whose try makes the state, or None. A cause is a line of `CAUSE_RULES`: a prefix of the skill's reason and one of `see`, `decide`, `act`, `world`, `tech`, or None where the log has to decide. `tests/test_bench.py` reads the skills' code and fails on a reason no rule covers.

## A worked example

A capability that stands still on foot for ten seconds and counts when the figure is still on foot and the minimap reader never lost the map. First the piece, in `bench_proofs.py`:

```python
@piece
def map_stayed(run: Try, seconds: float = 2.0) -> Evidence:
    """The minimap was readable over the last `seconds`."""
    rows = run.session.ticks(run.session.end - seconds, run.session.end)
    shown = sum((r.get("reading") or {}).get("minimap") in ("flat", "tilted") for r in rows) / max(len(rows), 1)
    return Evidence(shown > 0.9, {"shown": shown}, "", None if shown > 0.9 else (run.session.end, "map lost"))
```

Then the entry, in `CATALOGUE` in `bench.py`:

```python
Capability(
    "foot.stand", "foot", "Stand still", "Stehen bleiben",
    ("foot",), (step("wait", duration=10),), 15,
    (P("on_foot_at_end"), P("map_stayed")),
),
```

`bench.py run foot.stand --dry` now shows it, `bench.py run foot.stand --tries 5` tries it, and the board has a row for it. `test_a_catalogue_entry_with_named_proofs_is_all_it_takes` in `tests/test_bench.py` does the same with a piece of its own.

## Rules

Everything under `/Users/kerim/recordings/` is read, never written, except what the pilot itself records while a try runs. A ledger only grows; a repaired proof is shown by `bench.py rejudge`, which appends revisions, and a person's correction by `bench.py mark`, which writes beside the ledger. `import-source.tsv`, `import-later.tsv` and `import-view.tsv` here are the lists of 12 November that `bench.py import` took over.
