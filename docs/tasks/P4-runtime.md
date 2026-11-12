# P4: the runtime that connects bridge, reader and driver, and records every run

Package: `pilot/`. Your files: `pilot/src/pilot/bridge.py`, `pilot/src/pilot/loop.py`, `pilot/src/pilot/replay.py`, `pilot/src/pilot/cli.py`, `pilot/tests/test_bridge.py`, `pilot/tests/test_loop.py`, `pilot/tests/test_replay.py`. The reader (`minimap.read`), the motion estimate (`motion.map_motion`, `motion.MOVING_PX`) and the driver (`drive.Driver`) are built by other workers at the same time. In your worktree they are placeholders that raise `NotImplementedError`: code against their signatures in `minimap.py`, `motion.py`, `drive.py` and `contract.py`, do not edit those files, and inject fakes in your tests.

## The bridge

The daemon in `remoteplay/` listens on `http://127.0.0.1:9395`. You never talk to the real one; tests use `httpx.MockTransport`. What it offers:

`GET /frame.raw?after=<id>&wait_ms=<0..1000>&x=&y=&w=&h=&step=` returns the newest frame, or a rectangle of it, as raw RGB bytes with the headers `X-Frame-Id`, `X-Frame-Age-Ms`, `X-Width`, `X-Height`. With `after` it waits up to `wait_ms` for a frame newer than that id and answers 204 when none came.

`POST /pad` with `{"buttons": [], "left": [x, y], "right": [x, y], "l2": 0..1, "r2": 0..1, "ttl_ms": 1..1000}` sets the whole controller state of the agent. It expires after `ttl_ms` (default 250) unless renewed. y = -1 is up. It answers 409 when the human is on the gamepad, the stream is not live or a button sequence is running. An empty object is the neutral state.

`POST /record` with `{"action": "start", "dir": "<absolute path>", "note": "..."}` or `{"action": "stop"}` controls the recorder, which writes `video.mp4`, `frames.jsonl` (`i`, `frame_id`, `t` in seconds since the start), `pad.jsonl` (one object per controller change: `t`, `src` "human" or "agent", `buttons`, `left`, `right`, `l2`, `r2`) and `meta.json` into that directory. `GET /status` returns the state of the session as JSON, among it `session_up`, `fps`, `frame_age_s` and `recording`.

`bridge.py` is a small synchronous client for these four calls on `httpx`, with short timeouts, that turns the frame answer into a numpy array plus id and age.

## The loop

`pilot drive` runs until the time given with `--seconds` is over, the driver reports that the route is gone and the car stands, or the process is interrupted.

Each tick it waits for a frame newer than the last one (`wait_ms` 100), asking only for the HUD rectangle `HUD_RECT`, reads it, decides `moving` by comparing the crop with the one from about 0.2 s earlier through `map_motion` (None stays None), and calls the driver with the time of the frame, which is the monotonic time of receipt minus the age the bridge reported. It maps the command to the pad (left stick x is the steering, R2 the throttle, L2 the brake) and posts it with a `ttl_ms` of 250. At 60 fps it takes the newest frame and does not try to process every one; about 30 ticks a second are enough.

Safety rules, each with a test. When no new frame arrives for 300 ms it posts the neutral state once and waits; the throttle is never held on a frozen picture. When `/pad` answers 409 it stops sending at once, because the human has taken the controller or the stream is down; it keeps reading and logging, tries the neutral state again after a second, and resumes only when that is accepted. On every way out, normal end, exception, SIGINT and SIGTERM, it posts the neutral state and then stops the recorder. With `--shadow` it never posts to `/pad` at all: the human drives and the loop only logs what it would have done.

Every run is recorded. Unless `--no-record` is given the loop starts the recorder into `<dir>/<YYYYMMDD-HHMMSS>` (the directory from `--record-dir`, an absolute path, default `recordings` under the repository root) with a note that says "pilot drive" or "pilot shadow", and writes its own log `pilot.jsonl` into the same directory: one JSON object per tick with the frame id, the frame age, the time, every field of the reading, `moving`, the command, whether it was sent and the status of the answer. Its time `t` is in seconds since the first tick; store the frame id so the log can be lined up with `frames.jsonl`. At the end it prints a short summary: ticks, tick rate, how often each driver state occurred, how many frames were damaged, how many answers were 409.

## Replay

`pilot replay <recording>` runs the same reader, motion estimate and driver offline over a recording and writes the same kind of log to `--out` (default `pilot-replay.jsonl` in the recording directory). Decode `video.mp4` with `cv2.VideoCapture`, convert BGR to RGB and cut `HUD_RECT`; never import `av`, it clashes with cv2. Take the frame times from `frames.jsonl`.

It then compares what the driver would have steered with what the human steered, from the `left` stick x in `pad.jsonl`: over the ticks where a route was read on a tilted map and the human steered harder than 0.4, the share where both have the same sign, and the time shift between the two series at which their correlation is highest. Print both with the number of ticks behind them. This is the offline shadow mode; its numbers only mean something on recordings made over the wired connection, say so in the output when `meta.json` has a note mentioning Wi-Fi.

Tests build a tiny recording in `tmp_path` with `cv2.VideoWriter` and hand-written JSON lines, and use a fake reader and driver.

## Done when

`.venv/bin/python tools/gate.py` in `pilot/` prints "gate passed". The tests cover the three safety rules, the shadow mode never posting, the neutral state on every way out, the log format, and the replay comparison on a constructed case where the expected agreement and shift are known. The report lists the commands with an example of each output and anything about the bridge's behaviour you had to assume.
