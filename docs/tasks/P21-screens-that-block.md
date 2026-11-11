# P21: Getting past the screens that stop the game

## Why

A playthrough is interrupted all the time by screens that wait for one button: the mission failed and the game asks whether to try again, a mission passed and shows its summary, something loads, and now and then the pilot itself opens the pause menu, the map, the weapon wheel or the phone by accident. Today each of these costs a full round through the head, ten seconds for one button press, and until the answer arrives the running skill keeps pushing sticks into a menu. These screens need a reflex: recognised, handled within a second, the head told afterwards.

P15 is building the reader that names the screen (`Hud.screen` in `contract.py`: game, pause, map, weapon_wheel, phone, failed, passed, loading), and the text reader of `scene.py` returns the words on it. This card builds what happens next and is written against those two results, not against their implementation.

## What is known

The long recording has a failed attempt at about 35 s of the shootout and Kerim trying again, with his controller in `pad.jsonl` (over Wi-Fi: his input leads the picture by 0.6 to 1.1 s). Go through that stretch frame by frame and write down what the game shows after a failure, which choices it offers, which button he pressed and what came after. Do the same for the end of the mission, around 330 to 350 s, and for the weapon wheel and the pause map further on. What the recording does not show is an assumption; mark it. In particular it is not known what the game shows when the character dies outside a mission or is arrested, and whether it offers to skip a part after several failures.

## What to build

`pilot/src/pilot/flow.py` with one object that is asked on every tick, before the running skill: given the observation (with `observation.hud` when a reader is attached) and the latest text, it returns nothing during ordinary play, and otherwise the pad for this tick and what it is doing. While it answers, the running plan is suspended, and it never returns a stick or trigger.

For each screen a small sequence with a check of the picture between two presses: after a failure, choose the retry; on the passed screen and while loading, a neutral pad until it is gone; a pause menu, a map, a phone or a weapon wheel that nobody asked for, back out. Another card's skill opens the map on purpose, so the object can be told that a screen is expected for a while and then leaves it alone. It presses only what the recording shows or what the screen itself names in its text, never L1 or R1 on a menu, never the same button more than a bounded number of times without the screen changing, and when a screen stays although it did what it knows, it stops and reports that the screen is stuck instead of trying other buttons.

It keeps count: how many failures in a row, when the last mission passed. It returns events for the head, a failure with its count, a pass, a stuck screen, so the head hears what happened once it is over.

## Judging it

On the recording: for the frames of the failure and of the mission's end, labelled with the screen by hand, what it would press and when, next to what Kerim pressed. In a simulation of your own: a small machine of screens that react to buttons with the 0.14 s delay, with a screen reading that is late by a few ticks and sometimes wrong for a tick, to show that every screen is left, that a wrong reading for one tick causes no press, and that a stuck screen ends in a report.

## Your files

`pilot/src/pilot/flow.py`, `pilot/tests/test_flow.py` with fixtures, `pilot/tools/sim_flow.py`, `pilot/tools/inspect_flow_clips.py`, `lab/flow/`, and your report. Not `conductor.py`, `skills.py`, `head.py`, `contract.py`, `hud.py` or `scene.py`. The reviewer wires the object into the conductor; describe in the report how it has to be called.

## Done when

The report describes each screen from the recording with frames. Tests pin: nothing is returned during ordinary play; no press on a screen read for a single tick; no stick or trigger ever; the retry after a failure; a neutral pad through the passed and loading screens; backing out of each accidental screen; an expected screen is left alone and taken over again when its time is up; the bounds; the stuck report; the events and the failure count. The simulation is reported. The default gate passes. The report lists what has to be confirmed live, in the order to try it.
