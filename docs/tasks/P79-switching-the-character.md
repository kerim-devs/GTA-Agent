# P79: Switching the character, with the Online slot out of reach by construction

## Why

The story is played by three characters, and a mission's letter on the map belongs to one of them. When the one being played has nothing to do (he waits for a call, his letters are gone), the game expects the player to switch. The pilot cannot: `switch_character` in `pilot/src/pilot/switch.py` fails `not-built` on every call. Card P75 measured the wheel and stopped before building it, for a reason that holds (`docs/reports/P75-the-way-into-a-mission.md`): the wheel's lower slot is GTA Online, the wheel is held open with the d-pad's Down and whatever is highlighted when Down is let go is chosen, and a skill that must let go of everything at its end cannot prove what was highlighted when its pictures are missing.

The pilot never enters GTA Online. That rule has no exception, and this card does not ask for one. It asks for a skill in which the lower slot cannot be highlighted at all, whatever the pictures show.

Read `PLAN.md`, `docs/tasks/README.md`, `docs/reports/P75-the-way-into-a-mission.md` (the measured wheel: `kerim/20261111-190825` at 427.0 to 438.0 s, a switch with the top and the left slot highlighted; `kerim/20261112-105402` at 202.2 s, a cancel with Circle while Down is held), `lab/story/frames.json`, `pilot/src/pilot/switch.py`, `place.py` (a finished skill written under the same rules: one press asked, one press sent, a neutral pad at every end), `contract.py`, `profile.py` and `flow.py` (which treats a screen it does not know as stuck).

## The rule the skill is built on

The wheel highlights the slot the right stick points at, and the figure being played when the stick is at rest. The stick is the only thing that moves the highlight. So:

The right stick never points into the lower half. Every pad the skill returns while Down is held has the right stick either at rest or on one of three fixed directions: left, up, right (the three story slots, as measured on the recordings; say which is whose from the frames). A stick value with a downward part is not in the code. A test goes through every pad of every scripted run, including runs with missing, damaged and wrong pictures, and asserts it.

Down is let go only with the stick held on a story slot, and the stick stays there for a quarter of a second after Down is up. That covers the pad's way to the console: the bridge sends a pad as a whole, and should the last one be lost the bridge lets go of everything after 250 ms, with the highlight still where the stick last put it.

The skill ends from every state through the same way out: stick on the story slot it last held (the current figure's own when none was chosen yet, read from the highlight when the wheel opened; the top slot when that reading failed), Down up, a quarter of a second, then the neutral pad. `stop()` called from outside in the middle of the wheel takes this way too and needs more than one tick for it: find out from `skills.py` and `conductor.py` how a skill can ask for the ticks of its own way out (the `closing` phase of `use_place` does it for a menu), and if the contract does not allow it, say so in the report and return, on the stop itself, the pad with the stick on the story slot and Down up, which is the one-tick form of the same rule.

With that, what happens when the pictures go missing in the middle is a switch to a story character, or none. Neither is Online.

## What to do, in this order

On frames. From the recordings named in P75's report and every other stretch in which Kerim holds Down for the wheel (`pad.jsonl` of his recordings under `/Users/kerim/recordings/kerim/`, the wheel is on screen while Down is held longer than a third of a second outside a menu): which slot is whose, where each slot's highlight is drawn, and a reading `wheel(frame)` that returns whether the wheel is on screen and which slot is highlighted (`left`, `top`, `right`, `bottom`, or none). Held against at least sixty frames with the wheel (as many per slot as the recordings give) and two hundred without, among them the weapon wheel, the pause menu, the map and bright scenes. The report gives the confusion table. A slot that is greyed out (a character the story has not opened, or one who cannot be switched to now) is told apart if the frames allow it.

The skill. `switch_character` with `to` (`next`, `michael`, `franklin`, `trevor`) and `duration`, as the stub declares them. It starts only on the game's screen with the minimap read, with no stars and no objective text, on foot or seated; otherwise it fails at once `switch-refused: <why>` with no input. It holds Down, waits for the wheel to be read, reads who is played, puts the stick on the wanted slot (`next` goes round the three in a fixed order, skipping what is greyed), waits for that slot's highlight to be read twice, and lets go by the rule above. Then it waits, with a neutral pad, for the game to come back: the camera flies for about ten seconds (8.5 to 10.5 s measured), and it ends done `switched: <name>` when the minimap has been read for a second, or failed `time-limit`. If the wanted slot's highlight is not read within three seconds it lets go on the current figure's own slot, which switches nothing, and fails `wheel-unread`. If the bottom slot is ever read as highlighted (it cannot be by this skill's stick: a hand on the controller, or a misreading) it does not let go of Down on that tick: it holds the stick on the top slot until a story slot is read as highlighted or two seconds have passed, then takes the way out, and fails `online-slot-seen`.

Who is played. The first reading of the highlight after the wheel opens says who was played. The skill reports it in its done reason (`switched: franklin; was: michael`) and in its failures where it was read, so that the rules can keep it.

## Your files

`pilot/src/pilot/switch.py`, a module of your own for the wheel's reading if it does not fit there, their tests, `lab/story/` for scripts, tables and small fixtures (under 3 MB added, the recordings' frames stay where they are) and `docs/reports/P79-switching-the-character.md`. Not `skills.py`, `flow.py`, `mission.py`, `goals.py`, `conductor.py`, `profile.py` or `bench.py`: the skill keeps its name and arguments, the reviewer adds the rules for its new reasons and writes the rules that plan it.

This is the path that sends inputs to the console and it cannot be tried there tonight. Nothing in this card is allowed to weaken the rule about the lower slot for the sake of another requirement: where two requirements cannot both be met, the Online slot wins and the report says what gave way.

## Done when

The reading's confusion table is in the report. The tests cover: no pad of any run has the right stick pointing down while Down is held or within a quarter of a second after it; Down is never let go with the stick at rest; every end (done, each failure, `stop()` from outside at each phase) goes through the way out; pictures missing, damaged or showing another screen at each phase; the bottom slot read as highlighted; a greyed slot; `next` going round; the refusals with no input; who was played in the reasons. A replay over the recorded switch of `kerim/20261111-190825` shows the skill's reading of the wheel agreeing with what Kerim chose. The gate passes in `pilot/`.

What stays open after this card is the console: one switch with Kerim watching, his hand next to the controller.
