# P66: A health bar that is read as it is, and a hit as a signal

## Why

The guard of P65 answers what the game draws: a red marker, lit stars, low health. Kerim's objection on the evening of 12 November is right: red markers are mostly a mission's. In free roam a brawl, a stray attacker or a shot from somewhere shows no marker at all, and the only thing the game draws is the health bar getting shorter at the first hit. That makes the falling bar the one signal a rule can have for a fight without a marker, and today it cannot be used.

The reaction bench found why (report `docs/reports/P62-the-reaction-bench.md`, "Why the reflex misses" and "Scenes that start from calm"). `hud._bars` reads health from the brightness of the band and `_fraction` takes the first long dark stretch for the bar's end. So the reader reads a fall whenever a map icon (the N, a race flag, a question mark, a car, a target, the running figure) passes over the bar, reads 0.0 for a third of a second while the HUD fades in after a black screen although the bar is full, and reads a shorter bar against bright sand behind the translucent band. Seven of the reflex's nine false notices are such falls, one of the pilot's false flights is, and of 61 proposals for a hit from calm not one could be confirmed on the frames.

Read the two sections of the report named above with `lab/reaction/misses.json`, then `pilot/src/pilot/hud.py`, `pilot/tests/test_hud.py`, `contract.py` for `Hud`, and `docs/reports/P15-*.md` for how the reader was built and measured.

## What to do, in this order

Write what each step gives into the report as soon as it is there.

The cases, before any change. The false falls the report names, each with its recording and time: before enemy-13 and at enemy-15 and enemy-16 (the HUD fading in), at wanted-07, calm-walk-20 and calm-walk-26 (an icon on the bar), calm-walk-13 (bright sand), enemy-17 (a fall from 0.51 to 0.31 that is undone within 0.2 s), and P62's three hit scenes that turned out false (their times are in `lab/reaction/ledger-p62.jsonl.gz` and the P62 half of the report). And real hits: find at least twenty moments in Kerim's recordings at which the bar really gets shorter, in fights and brawls, with and without a red marker on the map, by looking at the frames before and after; say for each the first frame on which the bar is visibly shorter. Keep them as fixtures under `lab/health/`: the HUD strip cut out of a few frames around each moment, not whole frames, with a small file that says what each shows. The scenes file of the reaction bench is not changed.

The reader. Health and armour are read as they are drawn. While the HUD fades in or the band is dim as a whole, the reader returns no value instead of 0.0. An icon or any shape on the bar does not end it: where bar colour continues beyond the shape, the bar does, and where the shape covers the end, the value is the last one that could be read or none, never a guess. A bright or coloured background behind the translucent band does not shorten the bar. What the reader gets right today stays right: its tests pass, and on the frames it is measured on in P15's report it gives the same values within its stated error.

The signal. A small module of its own, `pilot/src/pilot/hits.py`: it is fed the HUD reading of every tick and says when the figure has been hit and by how much. One odd tick decides nothing, a tick without a value is stood out, and nothing counts in the first second after the HUD has come back from a screen without it. It knows nothing of the guard; wiring it into the guard as a rule is the reviewer's step after P65 is merged, and the report says in a paragraph what that rule needs from it.

Measure it without the bench's replays, by running the reader and the signal over the frames themselves: all 29 calm scenes and the six seconds before each of the 26 onsets of `lab/reaction/scenes.json`, and the fixtures. Report the count of hit signals where there is no hit, the count of real hits signalled with the delay in ticks from the first frame on which the bar is visibly shorter, and the reader's time per frame before and after.

## Your files

`pilot/src/pilot/hud.py`, `pilot/tests/test_hud.py`, `pilot/src/pilot/hits.py` and `pilot/tests/test_hits.py` (both new), `lab/health/`, and `docs/reports/P66-a-hit-as-a-signal.md`. Nothing else: `contract.py`, `minimap.py` and `legend.py` are open in other worktrees, and `conductor.py`, `guard.py`, `approaches.py`, `reaction.py`, `tools/reaction.py` and `lab/reaction/` belong to P65, which is being built at the same time.

The rules of `docs/tasks/README.md` hold: no git writes, never the daemon on port 9395, no `ps5rp`, no `PS5_HOST`, recordings are read and never written. Another worker replays scenes in real time on this Mac and somebody may be playing on the console: run nothing that keeps the machine busy for minutes in one go, decode only the stretches you need, and not the full gate, which the reviewer runs. Keep `lab/health/` under 2 MB and remove what you put under `/tmp`.

## Done when

No hit is signalled on the 29 calm scenes or in the six seconds before the onsets that start from calm, where today's reading gives seven false falls in five scenes. On the frames of a fading HUD the reader returns no health, not 0.0. At least 18 of the 20 real hits are signalled within six ticks of the first frame on which the bar is visibly shorter, and the report names the ones that are not, with the cause. The reader's time per frame has not grown by more than a tenth.

`env -u PS5_HOST .venv/bin/python -m pytest tests/test_hud.py tests/test_hits.py -q` and ruff pass in `pilot/`, with tests on the fixtures for each kind of false fall, for a real hit, for a tick without a value and for the first second after the HUD returns.

The report says in its first paragraph how often the signal is wrong and how late it is, and what a rule for a hit without a marker can rest on: whether the direction of the attacker can be told from anything the game draws, or only from the people the object detector sees.
