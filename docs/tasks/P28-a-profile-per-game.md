# P28: A profile per game

## Why

The stream starts with GTA V on 17 November and switches to GTA VI on the 19th. What a button does is written into the skills today, as the name of the button: `walk` and `walk_to` tap `cross` to sprint, `enter_vehicle` presses `triangle`, `fight` and `punch` press `circle` and `r1`, the waypoint skill and the screen reflex press `options`, `cross` and `circle`. Previews of GTA VI report sprint on L3, and nobody knows the rest before launch day. On that day the change has to be one table, not a search through eight modules.

The second reason is measured. On the console the camera does not move at a right stick of 0.1, 0.15 or 0.2 and moves at 0.3, by about 130 image pixels a second (`docs/LOG.md`, 11 November, the first calibration). `face` asks for `min(0.65, angle * 0.01)`, so every turn below 30 degrees is lost in the dead zone, and so are the slow turns of `look`, of the scan in `enter_vehicle` and of the aiming in `fight` and `punch`. The left stick has not been measured.

## What to build

A module `pilot/src/pilot/profile.py` that holds what differs from game to game, and the skills reading it instead of naming buttons.

A profile names the button for each action the skills perform: sprinting, getting into a vehicle, the melee attack, taking cover, opening the pause menu, confirming and going back in a menu, and the retry after a failed mission. Find the complete list by reading the modules below; an action is what the figure does, never the name of a button. Sprinting also has a way of being pressed: GTA V wants the button tapped, which is what the skills do today at four taps a second, and the profile for GTA VI assumes it is held. Build both ways and no third.

Two profiles exist: `gta5`, which reproduces today's behaviour exactly, and `gta6`, a draft that differs only in what the previews report (sprint on `l3`, held) and says in a comment that nothing in it is confirmed. One profile is active for the whole process, `gta5` unless `profile.use(name)` was called before the first skill is built; the reviewer adds the command-line flag. A skill built under one profile keeps it.

The `press` skill keeps taking a raw button from the head. The triggers stay where they are: `l2` and `r2` are fields of the pad, not buttons, and no report says they change.

The dead zones are applied in one place, where a pad leaves for the console: `ControllerRuntime.tick` in `loop.py`. A stick component that a skill asked for and that lies inside the dead zone of the active profile is raised to the edge of the zone, and the range above it is compressed so that 1 stays 1 and the order of two requests never flips. A component of exactly zero stays zero, and so does anything smaller than a noise floor of 0.02. For `gta5` the right stick's zone is 0.3 on both axes and the left stick's is 0, because it is unmeasured and the driver's steering must not change. What the log line of a tick records is what was sent, with the skill's own request beside it.

Nothing else changes. No skill gets new behaviour, no reader moves into the profile, `HUD_RECT` stays in `contract.py`.

## Judging it

Every existing test passes unchanged; that is the proof that `gta5` reproduces today's pads. Where a test names a button the profile now supplies, leave the test alone.

For the profile: under `gta6` the same `walk` with sprint holds `l3` on every tick and never presses `cross`; under `gta5` it taps `cross` as before. The other profile-dependent presses are pinned the same way through one action each.

For the dead zone, on the real pads: replay the session `/Users/kerim/recordings/pilot/20261110-231512`, whose `play.jsonl` holds what the pilot sent on every tick, and report how many ticks asked the right stick for something inside the zone before, and that none does after. Pin with tests: a request of 0.1 leaves as at least 0.3; 0.3 and 0.65 keep their order and 1 stays 1; zero stays zero on both sticks; the left stick leaves as it came; the neutral pad stays the neutral pad, also at the end of a skill, on a stop and on a release.

This card changes the path that sends inputs to a console. Run the full gate, `.venv/bin/python tools/gate.py --full`, and say in the report what you tried in order to make the shaping hold an input it should have released.

## Your files

`pilot/src/pilot/profile.py` (new), `pilot/src/pilot/skills.py`, `combat.py`, `punch.py`, `vehicle_entry.py`, `waypoint.py`, `flow.py`, `loop.py`, the tests beside them and a new `pilot/tests/test_profile.py`, and your report. Not `cli.py`, `conductor.py`, `head.py`, `head_prompt.txt`, `contract.py` or `calibrate.py`.

## Done when

The tests above pass, the full gate is green, the report lists every action with its button under both profiles and the numbers of the replay, and no module in your files other than `profile.py` names a button for an action the profile holds.
