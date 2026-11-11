# P27: The screens on the cable

## Why

On the morning of 11 November the console was on the cable for the first time since the HUD reader was built, and the reader does not know the game's menus there. `pilot calibrate` opened the pause menu, never read it as one, gave up on four checks and left the menu open. The flow reflex would not have closed it either, and `set_waypoint` would wait for a map it cannot see.

A recorded tour shows how far this goes: `/Users/kerim/recordings/screen-tour/20261111-070239`, 4,052 frames at 60 frames a second, with `tour.jsonl` holding for every tick the name of the step, the pad that was sent and what the readers said. The pause menu is open for 127 ticks and reads `game` on every one. The map is open for 84 ticks and reads `game`. The weapon wheel is held open for 71 ticks and reads `game`. The phone reads `phone` on 60 of 84 ticks, the others while it slides in. The interaction menu, which a long press of the touchpad opens ("INTERAKTIONSMENÜ" under the character's name at the top left), reads `game` because the reader has no class for it.

The reason is the way the classes were built. Their templates were cut from the Wi-Fi recording of 10 November and are correlated as grey values, picture behind the letters included. On the cable the title of the pause menu scores 0.58 against a threshold of 0.86, with the letters exactly where they are expected. The picture behind them is simply another one.

The banners for a failed and a passed mission and for the death are built the same way, and no cable footage of them exists. Whatever is done for the menus should be done for them where the Wi-Fi frames can show that it loses nothing; say plainly what was not measured.

Read `docs/reports/P15-hud-and-screens.md` and `docs/reports/P25-wanted-and-wasted.md` with their reviews first, and `lab/hud/README.md`.

## What to build

In `pilot/src/pilot/hud.py`: screen classes that hold on the cable and on the Wi-Fi footage alike. `pause`, `map`, `weapon_wheel` and `phone` as they are named today, and a class for the interaction menu. A class is decided by what the menu itself draws, its letters, lines and shapes at their fixed places, and not by the picture behind it; the tour shows each menu over one background only, so show on the frames themselves that the decision does not lean on that background, for instance by reading the same menu pasted over frames of ordinary play.

The reader stays what it is: pure, without memory, without OCR of its own, under a millisecond on average. A frame of ordinary play is never called anything but `game`; a menu that is half faded in may be called `game` for those few frames.

The contract lists the screens in a comment and the flow reflex decides what to press on each. Both are outside your files. Give the new class a name, say in the report what the flow reflex should do on it (the picture shows "Zurück" on Circle), and the reviewer wires it.

## Judging it

Label first. Go through the tour on contact sheets and mark, for each screen, the first and the last frame on which a person would call it open; the step names in `tour.jsonl` say when the button went out, not when the menu was drawn. The second calibration run, `/Users/kerim/recordings/calibrate/20261111-065642` (3,303 frames), has the pause menu open over another background from the moment its `press` check began: find that stretch and label it too.

Report for each class: on how many of its open frames the reader names it, and how long after the first open frame it first does.

No false stop is the number that matters most, on every frame of ordinary play there is: the two clean sessions of 10 November (`/Users/kerim/recordings/pilot/20261110-230229` and `20261110-231512`, 28,701 frames), Kerim's own play on the cable (`/Users/kerim/recordings/kerim/20261111-065022`, 22,479 frames: a stolen car, a police chase with one and two stars, fist fights; look through it on contact sheets first and label any menu he opened), the camera probe (`/Users/kerim/recordings/camera-probe/20261111-065904`, 831 frames), the first calibration run (`/Users/kerim/recordings/calibrate/20261111-063233`, 1,631 frames) and the stretches of the tour between the menus. Report the count of frames called anything but `game` on each, and list every one.

Everything the existing evaluations and tests pin still holds: the labelled Wi-Fi set of P15 with its zero false stops, the death banner and the star counts of P25.

## Your files

`pilot/src/pilot/hud.py`, `pilot/tests/test_hud.py` with at most twelve new full frames as fixtures under `pilot/tests/fixtures/screens/`, `pilot/tools/evaluate_hud.py`, `lab/hud/` and a new `lab/screens/`, `.gitignore`, and your report. Not `contract.py`, `flow.py`, `conductor.py` or `calibrate.py`.

## Done when

Tests on real cable frames pin: the pause menu over both backgrounds, the map, the weapon wheel, the phone and the interaction menu each read as their class; the same menus pasted over other frames of play still do; frames of ordinary play from Kerim's recording with a car, with stars and in a fight read `game`; every test of P15 and P25 passes unchanged, or the report says which had to change and why. The report has the numbers above and the contact sheets the labels come from. The default gate passes in under 90 seconds.
