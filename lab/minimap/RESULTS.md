# Minimap reader results

Three readers were built against the labels in `data/labels/`, one per approach: `impl_trace` segments the route colour and traces it from the player arrow, `impl_rings` scans concentric rings around the arrow, and `impl_model` uses a colour table learnt from the dev labels. The workflow that produced the labels and the readers is kept in `workflow.js`. It stopped after the implementation phase, so there is no merged `final/` reader, no test suite and no adversarial pass yet.

On the held-out sheets (48 tiles, 11 with a route) all three report no route where there is none and find all 11 routes. `impl_trace` is the one to use for now: its near bearing is off by 5.1 degrees in the median with every route tile within 45 degrees, it gets the minimap class right on 94 percent of the tiles and takes about 1 ms per crop. The full numbers are in each folder's `dev.json` and `held.json`. The sample is small and comes from a Wi-Fi stream in which roughly a third of the frames are damaged, so the numbers should be measured again on recordings made over a wired connection.

To reproduce, rebuild `data/crops.npy` with `prep.py` as described in `TASK.md` and run `harness.py impl_trace/minimap.py --split held`.
