# P25: The wanted level and the death screen

## Why

Getting away from the police is one of the things Kerim asked for by name. The head already knows what to do with stars: its prompt says to get into a car, set a waypoint far away and drive. But it only learns of them when it happens to be asked and sees them in the picture, because `Hud.wanted` is always `None`. The conductor is ready for the number: it turns a change of `hud.wanted` that has lasted half a second into a `wanted_changed` event, which asks the head at once, and the commentator has lines for it.

P15 left the stars out because it found no footage. There is some. In `recordings/20261110-093238` the top right corner shows one star from about 536 s of the capture clock, three stars from about 590 s, five outlines with some of them lit and some blue around 576 s and 624 s, and the end of it: the character is shot at about 628 s, the picture turns black and white with the red banner "AUSSER GEFECHT" from about 630 s to 635 s, then black, and at about 642 s he stands in front of the hospital with "$412 -$20" in the corner. The HUD reader calls the frames with the banner `game` today. The flow reflex already knows what to do with a `wasted` screen (wait, press nothing, count a failure and tell the head when the game is back); it never hears of one.

Read `docs/reports/P15-hud-and-screens.md` and `lab/hud/README.md` for how the reader and its labelled evaluation are built, and `docs/reports/P22-wiring.md` for what the conductor does with what the reader returns.

## What to build

In `pilot/src/pilot/hud.py`, the two fields that are empty today and one screen.

`wanted`: the number of lit stars, 0 to 5, read from the top right corner. `None` when the corner cannot be read: a damaged frame, a screen that is not the game, something bright behind the stars that makes the count a guess. 0 only when the corner clearly holds no star. The same corner also shows the ammunition of the weapon in hand ("133 12", "32 7", right under the stars when both are there), the money when it changes ("$432 +$80"), and whatever the world puts there: sky, sun, white walls, signs with stars and letters on them. None of that is a star.

`wanted_flashing`: the stars blink while the police have lost sight of the character. Say what the footage shows of it (the blue stars at 576 s and 624 s may be this, or something else: find out from the frames around them), and build the field only as far as the footage carries. A single frame cannot blink; if the reader has to stay without memory to say it, report the colour or state it sees per frame and say in the report what a caller would have to do with it.

`screen == "wasted"` for the death banner. The German banner reads "AUSSER GEFECHT", the picture under it is black and white. As with the failure and the pass, the screen text may confirm a banner the pixels already point to and never decides alone.

The reader stays what it is: pure, without memory, without OCR of its own, under a millisecond.

## Judging it

Label first, then build. Go through the recording from 500 s to 650 s frame by frame on contact sheets and label the number of lit stars, or unreadable, for at least 300 frames across the whole stretch, with the boundaries where the level changes. Add at least 600 frames without stars: from the rest of that recording (it has the ammunition and the money in the corner, the shootout, the pass banner, the pause map with its own text in the corner) and from the two clean sessions `/Users/kerim/recordings/pilot/20261110-230229` and `20261110-231512`, which never have a star and are what the stream will look like. About a third of the frames of the Wi-Fi recording are damaged; label what a person can read and mark the rest unreadable.

Report, against those labels: how often the count is right, how often the reader abstains, and the two errors that cost something. A star seen where there is none sends the pilot fleeing from nobody, so count every frame without stars on which the reader returns one or more, over all labelled frames and over every frame of the two clean sessions (about 28,700 frames); the conductor acts on a value that has lasted half a second, so also report the longest run of such frames. A missed star delays the getaway: report the longest run of frames with stars on which the reader returns 0 or `None`. For the death screen: on which frames between 626 s and 642 s the reader says `wasted`, and that it says it on no frame anywhere else in the three recordings.

There is no footage of four or five lit stars, of an arrest ("VERHAFTET"), or of stars over a night sky. Say what the reader does there by construction and do not claim it was measured.

## Your files

`pilot/src/pilot/hud.py`, `pilot/tests/test_hud.py` with fixtures under `pilot/tests/fixtures/`, `pilot/tools/evaluate_hud.py`, `lab/hud/` and a new `lab/wanted/`, `.gitignore`, and your report. Not `conductor.py`, `flow.py`, `contract.py`, the commentator or the head prompt; if the contract lacks something, say so in the report.

## Done when

Tests on real frames pin: one star and three stars read as one and three; the corner with ammunition, with money and with neither reads 0; a damaged corner and a screen that is not the game read `None`; the frames with the death banner read `wasted` and the black-and-white frames before the banner do not need to; everything P15's tests pin still holds, including zero false stops on ordinary play. The report has the numbers above, the contact sheets it was labelled from, and the frames it gets wrong. The default gate passes in under 90 seconds.
