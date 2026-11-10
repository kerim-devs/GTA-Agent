P12 offline evidence

This directory contains the frozen 80-crop blip regression set, manual labels, source context, camera-assumption measurements and delayed-controller simulation results. Nothing here demonstrates live console operation.

Sampling used NumPy seed 12026 and a permutation of the existing 2,768 minimap crops. `sampling.json` preserves the candidate order. Candidate pools contained the first 80 readable flat and 80 readable tilted crops, without filtering for detected blips. Manual review selected 20 positive and 20 negative examples for each mode. Full recording frames were checked because a tilted reader classification does not always mean the player is in a vehicle. The vehicle group includes a vehicle-exit transition in crop 759. `flat-scenes-0.jpg` through `flat-scenes-9.jpg` and the corresponding `vehicle-scenes-*` files show this context; they are rebuilt by the commands below and are not kept in git.

`flat-labels.json` and `vehicle-labels.json` contain crop IDs and manually marked color/center coordinates in original crop pixels. `crops.npz` freezes the selected images and their IDs, so the reader regression test does not need the original recording archive. `sources.json` retains source metadata and border annotations. The public reader instead returns coordinates relative to the player arrow, with positive y pointing up, and a boolean border flag.

Labels count visible isolated yellow, blue and red markers, including pinned markers. They do not infer a person, vehicle or mission identity from color. Yellow circles attached to the painted route are route ends and are excluded; crops 908, 909, 1000, 1019 and 1085 exercise this distinction. The player halo, health bars, north marker and ordinary map icons are excluded. Overlapping markers are counted only where a separate colored center is visible. Labels were corrected after enlarged-image and source-context review. This set was used while tuning the reader and is a development/regression set, not an independent unseen accuracy estimate.

`scored-crops.json` records one-to-one matches of the same color within five pixels. `scores.json` reports recall as found divided by found plus missed, and invented fraction as invented divided by found plus invented. `overlay-00.jpg` through `overlay-19.jpg` show all 80 crops at twice their original size: white crosses mark manual centers and green circles mark reader output. Known disagreements remain in crops 2087, 2092, 2485 and 287; see the task report for their interpretation.

Run the following commands from `pilot` to reproduce evaluation and source-context sheets. The evaluation and scene tools use the original local crop/recording archive; the unit test uses the frozen fixture.

```sh
.venv/bin/python tools/evaluate_blips.py
.venv/bin/python tools/inspect_blip_frames.py --group flat
.venv/bin/python tools/inspect_blip_frames.py --group vehicle
```

`sample_blip_labels.py` regenerates candidate manifests and review sheets, not the manual labels. `blip_sheets.py` generates exploratory sheets and the camera review frames. They are preparation tools and do not establish scores by themselves.

The camera check compares robust map translation against stable human left-stick input across candidate delays from 0.6 to 1.1 seconds. Its quality filter excludes corruption, large rotation/scale changes and weak optical-flow fits. Only 49 distinct frame pairs survive, and almost all retained inputs point forward. The overlapping delay samples are correlated. These measurements support the forward direction assumption but do not calibrate arbitrary movement or the right stick.

```sh
.venv/bin/python tools/check_blip_camera.py
.venv/bin/python tools/summarize_blip_camera.py
.venv/bin/python tools/sim_blip_skills.py
```

The simulator runs 20 seeds at 30 Hz, with 0.14 seconds of configured picture delay, position noise, random missing observations, a burst dropout and wall collisions. Frame quantization can increase the effective observation age. `skill-summary.json` contains aggregate outcomes; `skill-simulation.json` with the individual runs and traces is rebuilt by the simulator and is not kept in git. Its movement and camera gains are synthetic; real-game gains, axis signs and arrival distances still need a controlled trial.
