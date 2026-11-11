# Looking at a live session

Small tools from the live rounds of 11 November. Each takes the folder of a session under `/Users/kerim/recordings/pilot/` and is run with `pilot/.venv/bin/python`.

`log.py` prints the skills of a session in order with how each ended, what went to the console and what the judge said. `drivelog.py` prints pedals, route readings, the distance to the waypoint over time and what the head was asked. `sheet.py <session> <out.jpg> <seconds>...` puts the frames at those seconds side by side. `boxes.py <session> <seconds>...` prints the boxes the object detector finds there. `yaw.py <session> <from> <to>...` measures from the picture how far the camera turned in each span; the first span has to be more than a full circle unless `CIRCLE` gives the pixels of one (2244 at a width of 640 with the far camera).

`record-kerim.sh` runs beside the bridge and records Kerim's own play to `/Users/kerim/recordings/kerim/`: it starts when his controller reports input through the bridge and stops after two quiet minutes.

A round at the console: the bridge runs as `remoteplay/.venv/bin/ps5rp --host <console> --fps 60 daemon`; before every run the picture is looked at (`ps5rp snapshot`) and `/status` on port 9395 must say that nobody is on the controller and nothing records. Then `pilot play --seconds N --judge http://<server>:1234=qwen/qwen3-vl-8b` with `--plan '<json>'` for one plan or `--head rules-only` for the rules.
