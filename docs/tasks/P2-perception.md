# P2: package the minimap reader with tests, and tell from the minimap whether the car moves

Package: `pilot/`. Your files: `pilot/src/pilot/minimap.py`, `pilot/src/pilot/motion.py`, `pilot/tests/test_minimap.py`, `pilot/tests/test_motion.py`, everything under `pilot/tests/fixtures/`, and in the lab `lab/minimap/impl_pilot/`, `lab/minimap/data/labels/` and `lab/minimap/data/label_changes.md`. `pilot/src/pilot/contract.py` is fixed; do not edit it.

Read `lab/minimap/TASK.md`, `lab/minimap/RESULTS.md` and `lab/minimap/workflow.js` first. The workflow stopped after its implementation phase; this card is its judge, attack and repair phases plus one new function.

## The lab

`lab/minimap/data/crops.npy` in your worktree is a link to the 2768 crops. Run lab tools from `lab/minimap` with the lab's own interpreter: `/Users/kerim/Documents/ChatGPT/gta/lab/minimap/.venv/bin/python harness.py <module> --split dev|held` and `... tools.py overlay <module> <out.jpg> <k...>`. Look at the produced JPEGs. Never import `av` in a process that imports `cv2`. The package tests run with `pilot/.venv/bin/python`.

The harness loads a reader from a file path, and the packaged reader imports its contract relatively, so create a thin adapter `lab/minimap/impl_pilot/minimap.py` that puts `pilot/src` on `sys.path` and re-exports `read` from `pilot.minimap`. Score the packaged reader through it.

## Part 1: the reader

Start from `lab/minimap/impl_trace/minimap.py` and move it to `pilot/src/pilot/minimap.py`, importing `Reading`, `ARROW_XY`, `NEAR_R`, `FAR_R` from `.contract`. Keep it one self-contained module on numpy and cv2, readable, with each measured constant explained in a short comment. No special case for a single crop.

Then do what the judge would have done. Score all three lab readers on both splits. Where another reader is clearly better on one field (the minimap class of `impl_model`, an arrow reading, the corrupt flag), graft that part if the harness confirms the gain on dev and on held and nothing higher in the priority order gets worse. The order is: no false route, near bearing right when a route is there, minimap class, far bearing and arrow, corrupt flag, speed under 3 ms mean.

Labels were made by looking and can be wrong. Several tiles are called wrong in the same way by all three readers: G10-03, G11-05, G13-02 on dev and G02-07, G09-08, G12-02 on held, all on the minimap class, and G02-02 on the arrow. Look at each tile and decide who is right. Correct a label only when the picture clearly shows it is wrong, and log every change with its reason in `lab/minimap/data/label_changes.md`.

Then attack the reader on the unlabelled crops. Mine for suspects with code and look at them with `tools.py overlay`: a route reported although `yellow` and `purple` in the meta are 0, or none reported although they are high; the near bearing jumping by more than 60 degrees between crops 0.2 s apart in one recording; a route read against strong steering to the other side (meta `steer` beyond 0.4 with `r2` above 0.2); route or minimap class flickering within three consecutive crops; high confidence on a visibly damaged picture. Add two sheets of purely random crops for an unbiased estimate. Look at no fewer than 120 crops. Fix confirmed patterns with a principled change (a colour rule, a geometry check, a confidence rule) and re-run both splits after each: a change that makes dev or held worse in the first three priorities is not a fix.

Tests in `pilot/tests/test_minimap.py` with real crops saved as PNG in `pilot/tests/fixtures/` and one JSON file that says what must be read on each: a tilted map with a yellow route going straight, bending left and bending right; a purple route; a tilted map without a route but with yellow of the game world shining through; a flat map without a route; no minimap (black, a cutscene); a damaged tile; and one crop for every pattern the attack made you fix. The tests assert concrete readings (class, colour, bearing within a tolerance, no route where there is none) and that `read` never raises on random noise, all black and all white.

## Part 2: map motion

`map_motion(prev, cur)` in `pilot/src/pilot/motion.py` returns how far the map content moved between two HUD crops in crop pixels, or None when it cannot be told. The runtime calls it with crops 0.2 s apart, the spacing of the lab crops, and compares the result with `MOVING_PX` to decide whether the player is moving. The driver uses that to notice that the car is stuck: throttle held, map not moving.

The map is half transparent and the game world shines through, the route, the arrow, blips and the bars do not move with the map, and in a vehicle the map is drawn in perspective. Measure on real crop pairs before you choose a method, and keep it under 2 ms per call.

There are no labels for this. Validate against what the human did: the meta of each crop has `steer`, `r2` and `l2`, and the full controller log of a recording is `pad.jsonl` in `/Users/kerim/Documents/ChatGPT/gta/recordings/<rec>/` (one JSON object per change with `t`, `left`, `right`, `l2`, `r2`, on the same clock as `t` in the meta). Find stretches where the car clearly drives (throttle held for seconds on a tilted map) and stretches where the player clearly stands (no input for seconds, the picture not in a cutscene), look at a sample of both to make sure they are what you think, and report how well `MOVING_PX` separates them on clean pictures. Set `MOVING_PX` from that measurement. Tests use real crop pairs as fixtures: a driving pair, a standing pair in a vehicle, a standing pair on foot, a pair without a minimap.

## Done when

On held the packaged reader reports no false route, has the near bearing within 45 degrees on at least 90 percent of the route tiles with a clean picture, and averages under 3 ms. `.venv/bin/python tools/gate.py` in `pilot/` prints "gate passed". The report gives the dev and held numbers of the three lab readers and of the packaged one, the label changes, the attack with counts (looked at, failures by kind, fixed, left) and your estimate of the error rate on clean driving pictures, the separation `map_motion` reaches, and the limits a control loop must know before it trusts either function.
