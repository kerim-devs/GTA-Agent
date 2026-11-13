# P81: What a review broke in the fight, the character wheel and leaving a building

## Why

A review on 13 November drove `fight`, `switch_character` and `leave_building` with scripted observations until they did something wrong, and reproduced each case with a script. The scripts are in this worktree under `.review-d/` (not part of the repository, do not move them into it); `probe_combat*.py`, `probe_switch.py`, `fuzz_switch*.py`, `probe_build.py` and `fuzz_build.py` each print what they found. None of it has been seen at the console: these skills are untried there, and Kerim watches the first session. What is fixed here is what would look wrong to him or would press something the pilot must not press.

Read `PLAN.md`, `docs/tasks/README.md`, the reports P77, P79 and P72, then `pilot/src/pilot/combat.py`, `switch.py`, `wheel.py`, `leave.py`, `indoors.py`, the place in `walkto.py` that calls `indoors.remember`, and `tests/test_combat.py`, the tests of the switch and `tests/test_buildings.py`.

## What to do

The decisions below are made; where one turns out not to work, say so in the report and do the nearest thing that keeps its purpose.

### The fight

A clock that stands. A step whose time equals the last step's tells nothing new. Today the fight returns the same pad again, which can be R2 held, and its limit never comes because the limit is counted on that clock. From now on such a step returns the neutral pad and changes nothing but a counter, and after thirty of them in a row the skill fails `invalid-observation-time`. Melee shares the step and gets the same.

Stars not read. `fight` ends on stars, but only when it reads them: with no HUD, or with `hud.wanted` unread, it fires on. Not knowing is no permission to shoot. `fight` locks and fires only while the stars were read as zero on the game's screen within the last second (the reader does miss single frames; the script `stars_measure.py` in `.review-d/` counts how often on recordings, if you want the number). A step without that is handled like a step with the map unread: no L2, no R2, the lock dropped, and after the same two seconds the skill fails, with `hud-unread`. `tests/test_combat.py` builds its fights without a HUD; give its helper one, and keep one test that shows a fight without a HUD never pulls a trigger.

Another screen. Neither `fight` nor `melee` checks `hud.screen`. Where a HUD is given and its screen is not `game`, the step is such an unread step for both. Melee without any HUD object keeps working as it does.

A red on the rim. A marker pinned to the map's border is out of range at an unknown distance, and the fight turns to it and fires along its bearing at nothing, in a street with people in it. `fight` aims only at reds inside the map. While reds are seen and all of them are on the rim it holds the neutral pad, the two seconds that end it as done do not run, and after three seconds of that it fails `target-out-of-range`, so that the rules walk nearer. Melee's own rule for a far target stays.

### The wheel

The rule of P79 stays untouched and is the first thing every test checks: no pad with a downward part in the right stick, on any path, including every new one here.

A clock that stands or is not a number. A repeated time returns the last pad, which is right for a single repeated capture and wrong for ever: with Down held it holds Down without end, and no limit is checked. After fifteen repeats in a row the step is handled as a bad clock, `clock-stalled`, and takes the way the other bad clocks take. In the release phase a bad clock of any kind (not a number, reversed, standing) is counted, and after fifteen such steps the skill ends failed with that reason, so that no phase can last for ever. Before that count is reached the release pad is returned as now.

Where Down is let go when the skill reports failure. Today the paths `wheel-unread` (picture or screen lost in the middle), `time-limit` and `stop()` let go with the stick on the slot of the character that was wanted. The game then switches, and the skill says it failed. Every release that reports a failure lets go with the stick on the slot of the character who was playing when the wheel opened, as the three-second path in the selecting phase already does. While that character has not been read (the opening phase), the stick stays at rest: it was never moved, and the wheel opens on the one being played; today `stop()` and `wheel-unread` there let go on the top slot, which is Franklin's, and switch to him. The rescue (the wheel shows the lower slot or no slot highlighted) moves the stick to the slot of the character who was playing where that was read, and to the top slot otherwise, as now. A release after the wanted slot was confirmed is not a failure and stays as it is.

### Leaving a building

`stop()` overwrites a verdict the skill has already reached. A finished skill returns what it finished with.

No way to know. Without a place model, and with the picture reading not allowed to decide alone (`indoors.INDEPENDENT` is false), the skill can never learn where it is and stands at rest for its whole limit. It fails on its first valid step with `place-unread`. With a model that gives no confirmed answer, in or out, within eight seconds of valid steps from the start, it fails the same way.

An old way in. `indoors.remember` keeps the heading of the last doorway with no time, and `leave_building` turns to it whenever it finds one: after another building entered some other way, and, for a heading that is relative to the camera rather than to north, after the camera has turned. Keep the time with the entrance (`walkto.py` passes its observation's time). `leave_building` uses a remembered heading that is at most three minutes old, and one that is relative to the camera only when it is at most thirty seconds old; otherwise it looks for the way out as it does with nothing remembered.

Two things the review named are left as they are, say so in the report: an unsure answer of the place model does not cancel an outdoors reading that two answers confirmed, and a red marker that flickers keeps a fight going until its limit.

## Your files

`pilot/src/pilot/combat.py`, `switch.py`, `leave.py`, `indoors.py`, the one call in `walkto.py`, `bench.py` only for rules in `CAUSE_RULES` for the new reasons (`target-out-of-range`, `place-unread`, `clock-stalled` and any other you add; the keys are prefixes and carry no trailing space), their tests, and `docs/reports/P81-what-the-review-broke-in-fight-wheel-and-buildings.md`. Not `mission.py`, `errands.py`, `localhead.py`, `conductor.py`, `flow.py`, `skills.py`, `wheel.py` or `wayround.py`: somebody else is working in the first three right now.

Every step returns the whole pad. The timings P77 measured for the fight and the release P79 fixed for the wheel are not changed.

## Done when

One test for each item above fails before the change and passes after it; the review's scripts no longer show their findings (say for each script what it prints now); a test goes through every pad of every new path of the wheel and finds no downward stick; the existing tests of the three skills pass, changed only where they built a fight without a HUD. The gate passes in `pilot/`: run the tests of your own files while you work and the whole gate once at the very end, because the machine is shared.
