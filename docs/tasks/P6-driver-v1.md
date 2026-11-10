# P6: Driver v1, tuned against the human recordings

## Why

The reader is good and the driver throws its signal away. Replaying the long human recording (`20261110-093238`) through reader, motion and driver v0 gives this on the 495 ticks where Kerim holds the stick beyond 0.4 while the reader sees a route on a vehicle map: the driver steers zero on 341 of them, the same way as Kerim on 84 and the opposite way on 70. In the `follow` state alone it is 179 zero, 52 same, 53 opposite out of 284, with a median commanded stick of 0.0 against Kerim's 1.0. On the same recording the raw route error (`bearing - arrow`) has the sign of Kerim's stick on 97.3% of the clean ticks with an error above 10 degrees, at zero time shift. So `replay` printing "sign agreement=0.170" is the driver's fault, not the reader's.

Two causes are already known. The `corner_bias` rule cancels the steering whenever the far bearing bends the same way as the near one, which is every steady curve; the simulator shows the same thing as curves run 4 to 14.5 m wide at 1 m per pixel and 13 to 27 m at 2 m per pixel, where the block scenario fails. And the reader now caps the confidence of damaged frames at 0.35, below the driver's threshold, so the driver lets go on 207 of those 495 ticks. The Wi-Fi recordings are full of damage (4291 of 14214 frames); the wired link is far cleaner, but the driver must not fall apart when a few frames are bad.

The real scale of the vehicle map in metres per pixel is still unknown and the map is drawn in perspective, so the driver has to work across the whole plausible range instead of being tuned to one guess.

## What to build

A driver that steers the way a person does when the map shows where to go, and holds a car on its route in the simulator at every scale. How you get there is yours to decide; measure before and after every change and keep what the numbers support. You have several hours and nobody is waiting on an early result, so spend them on evidence, not on code volume.

Start by making `replay` tell the truth: count zero, same and opposite separately, split by driver state, for the command and for the raw error, at zero shift and at the best shift. A released stick is not a disagreement of sign, it is its own failure.

Then rework the driver. If two bearings at fixed radii are not enough to place a turn, extend the reader: `_trace` in `minimap.py` already follows the route outward from the arrow, so it can hand over the points it found. Extend `Reading` only with new fields at the end that have defaults, so every existing constructor keeps working, and make the simulator produce the same fields from its route geometry. Damaged frames need a rule that keeps a route which agrees with what the driver saw a moment ago and drops one that does not. Decide from the recordings and the simulator whether the driver should brake before sharp turns; v0 only lifts the throttle. The stream wants a car that arrives, not a fast one.

If the recordings let you estimate the map scale, for instance from how fast the map moves under full throttle on a straight, give the estimate with its uncertainty. Do not build on it.

## Your files

`pilot/src/pilot/drive.py`, `sim.py`, `replay.py`, `minimap.py`, `contract.py` (additions only), their tests and fixtures under `pilot/tests/`, new evaluation scripts under `pilot/tools/`, and your report. In `loop.py` you may change only what a contract addition forces. `bridge.py`, `cli.py`, `motion.py` and everything under `remoteplay/` are not yours. `cli.py` builds `DriveConfig(command_delay=0.14, **overrides)` from `--set name=value`, so `command_delay` keeps its name and every tunable stays a numeric field of `DriveConfig`.

The recordings are in `/Users/kerim/Documents/ChatGPT/gta/recordings/` and are read-only for you; write replay output into your worktree with `--out`. Read each `meta.json` first: the long one was driven over Wi-Fi with the controller on the Mac, so the stick takes 0.6 to 1.1 s to show in the picture and Kerim was steering on an old picture. He is evidence of the right direction, not of the right timing. Decode video with `cv2`, never with `av`. The labelled crops are in `lab/minimap/data/crops.npy` and the harness is run as `cd lab/minimap && /Users/kerim/Documents/ChatGPT/gta/lab/minimap/.venv/bin/python harness.py impl_pilot/minimap.py --split dev` (and `held`).

## What must stay true

The driver never steers on anything but a vehicle map. It lets go when it has no trustworthy route, stops with bounded braking when the route is gone, backs out when it is stuck, and gives up after repeated failed attempts. `loop.py` ends a run when the state is `route-gone` or `failed-recovery` with throttle and brake at zero, so those two state names and that meaning stay. Unknown motion never counts as standing still. The existing tests for these behaviours keep passing or are replaced by ones that assert the same thing.

The reader must not get worse: on both splits no false route, every labelled route found, near bearing within 45 degrees on all of them, and a mean time per reading under 3 ms. Map accuracy today is 95.8% on dev and 93.8% on held.

## Done when

On the recordings that contain driving, on the ticks where the human holds the stick beyond 0.4 and the reader gives a route on a vehicle map, the driver is in `follow` on at least 80% (v0: 57% on the long recording), and within `follow` it steers the human's way on at least 85% and the opposite way on at most 8% (v0: 18% and 19%). Report the same table for v0 so the change is visible, and say at which time shift each number holds.

In the simulator every scenario reaches its goal at 0.5, 1 and 2 m per pixel with command delays of 0.14, 0.21 and 0.3 s, with a largest distance from the route of at most 4 m at 0.5 and 1 m per pixel and 6 m at 2 m per pixel, and without the steering flipping more than twice a second. The pinned list of known failures in `tests/test_sim.py` is re-pinned for v1 and each entry that remains is explained. The simulator draws the map flat while the game draws it in perspective; say what that leaves untested.

The gate passes. The report has the two tables, the notebook of what you tried and what it did, the estimate of the map scale if you got one, and a short list of the `DriveConfig` fields to touch first on the real car with careful starting values. Where a target is missed, say so with the number.
