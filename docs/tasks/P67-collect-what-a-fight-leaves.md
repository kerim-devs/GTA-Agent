# P67: Collect what a fight leaves: money and weapons on the ground

## Why

On the evening of 12 November the pilot knocked a man down at the console for the first time (session `/Users/kerim/recordings/pilot/20261112-220332`), and then stood beside him. Kerim, watching: the man dropped money, and a player picks that up, and weapons too where there are any. He gave the rule with it. When nobody is left to fight, collect. In a shootout a weapon on the ground is worth some damage but not much: with little health nothing is collected until every enemy is down.

Nothing in the pilot knows that something lies on the ground. A first blind try, walking the figure over the place where the man fell (session `20261112-220803`), collected nothing: the game shows the money in the top right corner when it changes, and it never showed. In the night picture the money cannot be told from the ground by eye at the size of a contact sheet.

Read `pilot/src/pilot/punch.py` and `combat.py` for how a skill follows what the detector sees and ends, `foot.py` for walking to a point in the picture, `hud.py` and `legend.py` for how a reader is built and measured, and `docs/tasks/README.md`, whose rules for a new skill hold.

## What to do, in this order

Write what each step gives into the report as soon as it is there.

What a pickup looks like. Find in Kerim's recordings (`/Users/kerim/recordings/kerim/`, labels under `derived/kerim/`) at least thirty moments at which he collects money or a weapon on foot: the moment is where the game shows the money in the top right corner, or the weapon's name and ammunition, right after he walked over something. Look at the frames of the two seconds before: what marks the thing on the ground by day and by night (its glow, its colour, its size at three, two and one step away), and what the game shows when it is taken. Say plainly if a pickup cannot be told from the ground in the picture at some time of day. The two sessions named above are the night case with the pilot's own camera.

The reader, in a module of its own. From a frame it returns the pickups it sees, each with where it lies in the picture and what kind it is as far as that can be told (money, weapon, unknown), and nothing where it is not sure. And a second small reading for the proof: the money figure in the top right corner, which is there only while it changes, and the weapon line where the game shows one.

The skill, `collect`, as one class in a module of its own under the rules for a new skill. It walks to the nearest pickup and over it and goes on to the next within reach until none is left or its time is up. It reports done only for what it has observed: the money figure appeared and rose, or the weapon line appeared; a pickup that is gone from the picture without either is said to be gone, not collected. Where the reader sees nothing but a person the figure has just knocked down lies in view, it walks over the place beside that person once, since that is where the game drops the money.

The rule for when, as a function the guard and the head's rules can ask, not wired in by this card: with nobody left to fight (no red marker for two seconds, no stars, the last opponent down) always; with enemies still up only when health is above one half and the pickup is no more than a few steps away; with health under one third never before every enemy is down; with stars lit only what lies on the way out. The numbers are Kerim's rule in figures of our own and are constants at the top of the module with that said beside them.

## Your files

A reader module and a skill module of your own under `pilot/src/pilot/` with their tests, fixtures under `lab/pickups/` (crops, not whole frames, under 2 MB), and `docs/reports/P67-collect-what-a-fight-leaves.md`. Not `skills.py`, `head.py`, `head_prompt.txt`, `conductor.py`, `guard.py`, `mission.py`, `contract.py` or any existing reader; the reviewer wires the skill in.

The rules of `docs/tasks/README.md` hold: no git writes, never the daemon on port 9395, no `ps5rp`, no `PS5_HOST`, recordings are read and never written. Nothing that keeps this Mac busy for minutes in one go, and not the full gate.

## Done when

The report shows what a pickup looks like by day and by night with the frames it was read from, and says where it cannot be seen. On the moments found in the recordings the reader sees the pickup before Kerim reaches it in at least 24 of 30, and on thirty stretches of ten seconds each on foot without a pickup it reports none in at least 28. The reading of the money figure is right on every one of the moments where money was taken. The skill's tests cover: walking over a seen pickup, done only on the observed proof, a pickup that vanishes without proof, nothing in view, the time limit, the neutral pad at every end, and the rule for when with each of its four cases. `env -u PS5_HOST .venv/bin/python -m pytest` on your tests and ruff pass in `pilot/`.

What stays open after this card is the console: the first run of `collect` beside a man the pilot has knocked down, by night and by day.
