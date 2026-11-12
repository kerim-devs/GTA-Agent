# P18: Fighting

## Why

Story missions have shootouts and fist fights, and the pilot's only weapon skill is `shoot`: it holds L2 for a fifth of a second and taps R2, facing wherever the camera happens to point. It does not turn to an enemy, does not notice that it is being hit and does not know when the fight is over. This card builds the closed loop. It may lose fights; it must look like it is fighting.

Read `docs/tasks/README.md`, sections "A new skill" and "Recordings", and `docs/reports/P12-blips-walk-and-face.md`: the reader reports red, blue and yellow blips relative to the player, the map's up is where the camera looks, and `face` already turns the camera to a blip.

## What the game does, as far as known

Enemies in a mission are red blips on the minimap. With the game's targeting set to assisted aim, which Kerim will set, holding L2 snaps the aim onto the nearest enemy in front of the camera and holds it there while he lives; letting go and pressing again takes the next one. R2 fires. The weapon reloads by itself when it is empty. R1 takes cover behind what is near, and from cover L2 aims out. Below half, health comes back to half by itself after a few seconds without being hit. Without a weapon, circle punches the locked target. Kerim's own shootout is in the long recording between 0 and 130 s with his controller in `pad.jsonl`, including an attempt that failed at about 35 s; over Wi-Fi, so damaged frames and a stick that leads the picture. Take the rhythm from it: how long he holds L2, how long his bursts are, when he lets go. Treat every button and timing here as an estimate until that recording or a live trial confirms it, keep them as named constants, and list the unconfirmed ones in the report.

## What to build

`pilot/src/pilot/combat.py` with two skills.

`fight`, with a time limit up to 30 s and an option to use cover. It turns the camera to the nearest red blip, holds L2, fires in bursts with gaps, lets go of L2 for a moment so that the next press finds a living target, and starts over. It is done when no red blip has been visible for two seconds on a readable map, and says so; that the map is unreadable or absent is not the same as no enemies, and then it stops firing and fails after a bounded wait. When `observation.hud` reports health under a threshold it stops firing, and with the cover option presses R1 once and waits for a bounded time before it goes on. Without a HUD reading it fights on. It never fires without a red blip in front of the camera, and it never holds L2 or R2 across a tick in which the reading is missing or damaged for longer than a short grace period.

`melee`, with a time limit up to 10 s: the same loop with circle instead of R2, for a target close by.

## Judging it

On the recording: for the frames of the shootout on which the reader sees red blips, compare the direction `fight` would turn with where the nearest blip is, and report how often red blips are visible at all during the fight, since that bounds what the skill can do. Report Kerim's rhythm with numbers and how the constants follow from it.

In a simulation of your own: enemies on a plane who shoot back, a camera with the map fixed to it, a lock-on that takes the nearest enemy inside a cone, health that falls and recovers as in the game, the 0.14 s delay, and blips that jitter and drop out. Show over many seeds that it clears three enemies more often than not, how it behaves when it is being killed, and that it always ends within its limit with a neutral pad.

## Your files

`pilot/src/pilot/combat.py`, `pilot/tests/test_combat.py`, `pilot/tools/sim_combat.py`, `pilot/tools/evaluate_combat.py`, `lab/combat/`, and your report. Not `skills.py`, `head.py`, `head_prompt.txt`, `conductor.py`, `contract.py` or `minimap.py`.

## Done when

Tests pin the rules of the README and: no shot without a red blip in front, nothing held through missing readings beyond the grace period, the pause on low health, the difference between no enemies and no map, and a neutral pad at every end. The simulation and the recording comparison are reported with their numbers. The default gate passes. The report gives the constants with where each comes from, the text for the head, the game setting the skill depends on, and what has to be tried live.
