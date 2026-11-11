# P24: Measuring the console in three minutes

## Why

Every skill of the last two days rests on numbers nobody has measured: how long a press has to last for the game to take it, where the dead zone of a stick ends, how fast the camera turns, how late the picture is, how long it takes to sit in a car after Triangle, which way the map moves under the stick. Each report marks them as guesses, and each lists what has to be tried on the console. Time on the console is the scarcest thing in this project: inputs to it are only sent while Kerim is there, and he starts every such run himself. One command that runs a fixed series of short, harmless experiments and writes the numbers down turns a week of guessing into three minutes.

Read `docs/reports/P10-conductor-head-and-skills.md` for how `pilot play` sends a pad and records a session, and the "open" paragraphs of the reviews in `docs/reports/` of P16, P18, P19b, P21 and P22 for the numbers that are wanted.

## What to build

`pilot calibrate`, a subcommand next to `pilot play`, in `pilot/src/pilot/calibrate.py`. It runs a list of named checks one after the other. A check reads its precondition from the picture, sends a short fixed sequence of inputs through the same runtime `run_play` uses (neutral at the end whatever happens, the interrupt handlers, the conflict when a person touches the controller), measures the answer on the frames, and returns numbers. The whole session is recorded like a play session, with a `calibration.json` beside it that holds every number, every raw series it was computed from, and for each check whether it ran, was skipped or was aborted and why.

The checks, in this order, each selectable with `--only` and `--skip`:

`delay`: the time from a command to the picture. A short pulse on the right stick, the time until the picture starts to move, three times, alternating sides so the camera ends where it began.

`camera`: the right stick sideways at 0.1, 0.15, 0.2, 0.3, 0.45, 0.65 and 1.0 for a little over half a second each, alternating sides. How fast the picture moves at each, and the smallest deflection that moves it at all.

`walk`: the left stick forward at 0.2, 0.3, 0.45, 0.65 and 1.0 for a little over half a second each. Whether the minimap reader sees movement at each, and the smallest deflection that walks.

`press`: the shortest press the game takes. Options for one tick of the loop, then two, three, four, until the HUD reader says the pause screen is there, then Circle the same way until the game is back. Twice.

`map`: Options, Cross onto the map, one pulse of the left stick to the right and one down, the shift of the map measured with `waypoint.map_shift`, then Circle until the game is back. Which way the map moves for each direction and how far per second of pulse. No waypoint is set: Cross is pressed once, on the pause screen, and never on the map.

`wheel`: L1 held for a little over half a second, whether the reader says weapon wheel while it is held and game after it is let go.

`phone`: up on the directional pad, whether the reader says phone, Circle, game again.

`car`, only when asked for with `--car`, with the character standing next to a parked car: Triangle, a neutral pad, and the seconds until the minimap has been tilted for half a second. Then Triangle again and the seconds until it is flat.

`detector` and `head`, without any input: the object detector's results per second next to the running loop over five seconds, and one request to the head with the current picture and its seconds.

Nothing else is ever pressed: no PS, no Create, no R2, no sprint. A check whose precondition is not met is skipped with the reason, a screen that is not the expected one ends the check with the back-out the screen needs (Circle on pause, map and phone; nothing elsewhere) and the run goes on with the next check. The run as a whole has a time limit of four minutes.

Before the first input it prints, in German as the overlay speaks, what it is about to do and what the character should be doing (standing on foot, somewhere open, nobody around), and waits for Enter; `--yes` skips the wait. At the end it prints one line per check with the numbers. `--shadow` sends nothing and runs only the reading side of each check, to see that the readers work on the live picture.

## Judging it

Nothing here can touch the console, and neither can the reviewer; Kerim runs it. So it is judged on a console of your own: a small simulated game behind the bridge's interface, with a picture that answers the pad after a delay, a camera with a dead zone and a turn rate, a walker, screens that open and close on presses of a minimum length, a map that moves under the stick, a car that takes its seconds. For each check, run it against several true values (a delay of 0.14 and of 0.6 s, a dead zone of 0.12 and of 0.25, a shortest press of one tick and of three, a map that runs either way, a door of two and of five seconds) and report what it measured next to what was true. And against the things that go wrong: a picture that never moves, a pause screen that does not open, a screen that is not the expected one in the middle of a check, a person on the controller.

The pictures of the simulated game have to be good enough for the real readers: use frames from the recordings as the base wherever a reader has to recognise something (`recordings/20261110-093238` has the pause screen, the map, the phone and the weapon wheel; `docs/reports/P21-screens-that-block.md` and `docs/reports/P19-waypoint-on-the-map.md` say where), and move or blend them rather than drawing your own.

## Your files

`pilot/src/pilot/calibrate.py`, the `calibrate` subcommand in `pilot/src/pilot/cli.py`, `pilot/tests/test_calibrate.py` with fixtures, `pilot/tools/sim_console.py`, `lab/calibrate/`, `.gitignore`, and your report. Not `conductor.py`, `flow.py`, `skills.py`, `loop.py`, `bridge.py` or any reader; if the runtime lacks something you need, say so in the report and work around it in your own file.

## Done when

Tests pin, on the simulated console: each check recovers the true values above within a tolerance you state; every check ends with a neutral pad, also when it is aborted, interrupted or runs out of time; nothing outside the buttons named above is ever sent, in any check and any failure; Cross is never sent while the map is on screen; a precondition that is not met skips the check without an input; an unexpected screen is backed out of and the next check runs; `--shadow` sends nothing; the time limit of the run; `calibration.json` holds the numbers and the raw series. The default gate passes in under 90 seconds. The report has the table of measured against true, and one paragraph for Kerim in plain words: the command to type, what the character has to be doing before, what he will see, and how long it takes. It also says, per number, which constant in which file it should replace.
