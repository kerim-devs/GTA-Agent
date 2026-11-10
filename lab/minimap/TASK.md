# Minimap reader for GTA V

Goal: a fast, dependable function that reads the minimap of GTA V from a video frame, so that a 30-60 Hz
control loop can steer a car along the GPS route. It is the first building block of an agent that plays the
game through a video stream. Everything here is an experiment folder; work only inside it.

## Data (read-only)

- `data/crops.npy`: 2768 crops, 170 x 260 x 3 uint8 RGB, memory-mapped by `tools.load()`. Each is the
  bottom-left HUD corner (x 30..290, y 530..700 of a 1280x720 frame), every 6th frame (0.2 s apart) of two
  recordings of a human playing: on foot, shoot-outs, cutscenes, driving a car and a motorcycle, with and
  without a GPS route. The stream came over Wi-Fi, so many frames are damaged (smeared blocks).
- `data/meta.json`: per crop `k`, `rec`, frame index `i`, time `t`, and what the human did with the
  controller around that time: `steer` (left stick x, mean over t-0.1..t+0.5 s, -1 = left), `r2` (throttle),
  `l2` (brake). `yellow`/`purple` are crude pixel counts used only to pick the label sample.
- `data/golden.json`: 168 crops picked for labelling: `id`, `sheet`, `tile`, `k`, `split` (`dev` or `held`).
- `data/sheets/G00.jpg` .. `G13.jpg`: those crops as numbered tiles, 3x enlarged.
- `data/labels/<sheet>.json`: the labels (see below). Sheets G02, G05, G09, G12 are the held-out split:
  implementers must not read their labels or tune on them.

## What is in a crop

The map itself spans about x 34..214, y 28..141 of the crop; it is half transparent, so the game world shines
through. Below it, at about y 146..151, lie three bars: green (health), blue (armour), yellow (special ability).
The player arrow (white arrowhead, dark outline) sits at about (123, 117). On foot the map is drawn top-down
("flat"); in a vehicle it is drawn in perspective ("tilted") and may show a distance readout such as
"↑ 1.09km" at the bottom-left. A mission route is a solid yellow line along roads from the arrow to a yellow
blip; a waypoint route is purple. Other things on the map: an "N" blip on the border, blue/red/yellow blips,
icons, red areas. Yellow road markings of the game world shine through the map and are not a route.

## Contract

`contract.py` defines `Reading` and the meaning of every field. An implementation is one self-contained
module (numpy and cv2 only, no other dependencies, no files read at run time) with

    def read(crop: np.ndarray) -> Reading

It must be pure (no state between calls), must never raise on any 170x260x3 uint8 input, and should take
under 3 ms on average (p95 under 6 ms) on this machine.

## Tools

    .venv/bin/python harness.py impl_x/minimap.py --split dev --json impl_x/dev.json
    .venv/bin/python tools.py overlay impl_x/minimap.py impl_x/look.jpg 12 400 1933   # look at the result
    .venv/bin/python tools.py sheet some.jpg 12 400 1933                               # plain tiles

Read the produced JPEGs with the Read tool to look at them. Never import `av` together with `cv2`.

## Labels

Per tile: `id` ("G03-07"), `minimap` ("none" | "flat" | "tilted"), `route` ("none" | "yellow" | "purple"),
`near_clock`, `far_clock`, `arrow_clock` (clock hours, 12 = up, 3 = right, 6 = down, 9 = left, halves
allowed, or null), `corrupt` (true/false), optional `note`. The near circle has the radius of the distance
from the arrow down to the bars (30 px in the crop), the far circle twice that. The harness turns clock hours
into degrees. Labels were made by looking at the tiles, so single labels can be wrong.
