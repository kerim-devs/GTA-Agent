# P23: Hitting whoever stands in front

## Why

The two fighting skills of P18 turn to the red blips of the minimap, and those are the enemies of a mission. A person on the street has no blip, so outside missions the pilot cannot start or answer a fight, and that is one of the things a viewer asks for first. The object detector reports people as boxes (`pilot/src/pilot/objects.py`, read `docs/reports/P14b-objects-that-are-found.md` with its review), and P16 has a skill that walks to a detected vehicle (`pilot/src/pilot/vehicle_entry.py`, read `docs/reports/P16-enter-vehicle.md` with its review). This card is the same walk to a detected person, with fists at the end.

## What is known and what is not

`Detection.box` is `x0, y0, x1, y1` in pixels of the 1280x720 frame, as `contract.py` says and as the detector delivers it. P16 took boxes as fractions of the picture, its simulation did the same, and every test passed on a skill that would never have found a vehicle; the review found it. Feed your tests and your simulation the pixels the detector returns.

The detector's result is late by a few hundred milliseconds, misses a person for several results in a row, and its boxes jitter. The player's own character is filtered out before the skill sees the list, but not always. How well it finds people is not known: the labelled frames have few, most of them half behind cover.

In this game an unarmed character locks onto the person in front with L2 and hits with Circle; R2 fires a gun when one is in the hand. None of the recordings shows a fist fight, so the reach, the cadence and what the other person does are assumptions. Mark them.

## What to build

`pilot/src/pilot/punch.py` with a skill named `punch`, written against the skill interface in `docs/tasks/README.md`, with the arguments `duration` (up to 20 seconds, 15 by default) and `hits` (1 to 6, 3 by default).

It picks the person who is nearest by the look of the box, with a preference for the middle of the picture, and keeps that person from tick to tick like P16 keeps its vehicle; use P16's selection and association where they fit, by importing or by copying, without changing that file. It turns the camera until the person is in the middle and walks up, without sprinting. When the box is tall enough to be in reach and centred, it lets go of the left stick, holds L2 and presses Circle in short pulses, and counts each pulse as a hit attempt. A person who walks off is followed, and the attack starts again when in reach. It ends as done after the asked number of attempts with the person in reach, or earlier when the person is clearly down (a box that has become much wider than tall and stays so). It fails, with a reason the head can act on, when no person is found within a few seconds, when the person is lost, when the detector delivers nothing, and when time runs out.

It never presses R2 and never anything but L2 and Circle. It releases everything at once when the minimap is damaged or tilted (in a vehicle), when `observation.hud` names a screen that is not the game, and when it is stopped. When `observation.hud.health` is below 0.3 for half a second it fails with that as its reason, so the head can decide to run.

## Judging it

A simulation in the manner of `tools/sim_vehicle_entry.py`: a walker with a camera behind him, people as boxes through a pinhole camera in pixels, the detector's period, delay, jitter, misses and false boxes, the 0.14 s between command and picture. People who stand, who walk at 1.4 m/s, who run away at 4 m/s once the first hit lands, two people next to each other, nobody at all, and a second character box that is the player leaking through the filter (large, low, in the middle). Vary the field of view and the camera's turn rate by half and double as P16 did. Report per case how often the asked hits were delivered in reach, the time, and the reasons of the failures.

## Your files

`pilot/src/pilot/punch.py`, `pilot/tests/test_punch.py`, `pilot/tools/sim_punch.py`, `lab/punch/`, and your report. Not `skills.py`, `vehicle_entry.py`, `combat.py`, `objects.py`, `conductor.py` or `head.py`; the reviewer registers the skill. Write the sentence for the head into the report (at most 400 characters).

## Done when

Tests pin, all with pixel boxes: the nearest central person is chosen and kept while a larger one passes; no attack before the person is centred and in reach; the left stick is neutral while attacking; R2 is never pressed, in any state; Circle comes in pulses and is not held; a person who moves off is followed and attacked again; the count of attempts and the early end for a person on the ground; the box of the player leaking through is not walked into; stale, missing and future detections, a damaged or tilted minimap and a screen that is not the game release everything; low health for half a second fails and a single low reading does not; every end is neutral and stays neutral; the arguments are validated and `limit` is exposed like the other skills do. In the simulation, standing and walking people get their hits in at least 8 of 10 runs across the variations, and every other case ends within its time with a neutral pad and a reason. The default gate passes in under 90 seconds. The report lists what has to be measured on the console, in the order to try it.
