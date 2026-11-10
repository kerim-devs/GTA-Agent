"""Records every decoded frame and every controller state on one clock, to build and test a control
loop offline. Frames come straight from the decoder, so a burst after lost packets is kept in full.
Encoding and disk writes run on a worker thread: nothing here may slow down input or decoding.

A recording is a folder: `video.mp4`, `frames.jsonl` (one line per video frame: its index, the stream's
frame id, seconds since the start), `pad.jsonl` (every change of the human's and the control loop's
controller state, same clock) and `meta.json`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from .backend import ConsoleError
from .gamepad import PadState

if TYPE_CHECKING:
    from .daemon import Daemon

_LOG = logging.getLogger(__name__)
QUEUE_FRAMES = 64  # about two seconds of picture; beyond that frames are dropped, never input
STOP_TIMEOUT_S = 15.0
# first one this build of FFmpeg has; x264 is the smallest file at a speed far above the stream's
ENCODERS = (("libx264", {"preset": "veryfast", "crf": "20"}), ("h264_videotoolbox", {}), ("mpeg4", {}))


class Recorder:
    def __init__(self, daemon: Daemon) -> None:
        self.daemon = daemon
        self.dir: Path | None = None
        self.frames = self.dropped = self.pad_events = 0
        self.codec = ""
        self.error = ""
        self._t0 = 0.0
        self._seconds = 0.0
        self._meta: dict = {}
        self._frames: queue.Queue = queue.Queue(maxsize=QUEUE_FRAMES)
        self._pad: deque[tuple[float, str, PadState]] = deque()
        self._last_pad: dict[str, PadState] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._stop_task: asyncio.Task[dict] | None = None
        self._failed = False  # the writer died: nothing is taken any more, `stop` only closes the books

    @property
    def active(self) -> bool:
        return self._thread is not None and not self._failed

    def status(self) -> dict:
        return {
            "recording": self.active,
            "dir": str(self.dir) if self.dir else None,
            "seconds": round(time.monotonic() - self._t0 if self.active else self._seconds, 1),
            "frames": self.frames,
            "dropped": self.dropped,
            "pad_events": self.pad_events,
            "codec": self.codec,
            "error": self.error,
        }

    async def start(self, directory: str | None = None, note: str = "") -> dict:
        """Start a recording in a new time-stamped folder under `directory`."""
        if self.active:
            raise ConsoleError(f"already recording to {self.dir}")
        if self._thread is not None:
            await self.stop()  # a recording whose writer died: close its books first
            if self._thread is not None:
                raise ConsoleError(f"already recording to {self.dir}")
        first = self.daemon.backend.latest_frame()
        if first is None:
            raise ConsoleError("nothing to record: there is no picture yet")
        self.dir = self._make_dir(directory)  # one mkdir: not worth a thread, and no second start in between
        self.frames = self.dropped = self.pad_events = 0
        self.codec = self.error = ""
        self._failed = False
        self._frames = queue.Queue(maxsize=QUEUE_FRAMES)
        self._pad.clear()
        self._last_pad = {}
        self._stop.clear()
        self._stop_task = None
        self._t0 = time.monotonic()
        self._meta = {
            "started": datetime.now().astimezone().isoformat(timespec="seconds"),
            "resolution": self.daemon.cfg.resolution,
            "fps": self.daemon.cfg.fps,
            "note": note,
        }
        self._write_meta()
        self._thread = threading.Thread(target=self._write, name="recorder", daemon=True)
        self._thread.start()
        self._on_frame(first.frame_id, first.ts, lambda: first.rgb)  # a still screen is a recording too
        self.daemon.backend.set_frame_tap(self._on_frame)
        if self._failed:
            self._abandon()
        _LOG.info("recording to %s", self.dir)
        return self.status()

    async def stop(self) -> dict:
        thread = self._thread
        if thread is None:
            return self.status()
        self.daemon.backend.set_frame_tap(None)
        self._stop.set()
        if self._stop_task is None:
            self._stop_task = asyncio.create_task(self._finish_stop(thread))
        return await asyncio.shield(self._stop_task)

    async def _finish_stop(self, thread: threading.Thread) -> dict:
        await asyncio.to_thread(thread.join, STOP_TIMEOUT_S)
        if self._thread is not thread:  # a second stop came in meanwhile and has finished the job
            return self.status()
        if thread.is_alive():
            self.error = self.error or "the video writer did not finish in time"
        self._thread = None
        if not self._failed:
            self._seconds = time.monotonic() - self._t0
        summary = self.status()
        keys = ("seconds", "frames", "dropped", "pad_events", "codec", "error")
        self._meta.update({k: summary[k] for k in keys})
        try:
            self._write_meta()
        except OSError as err:  # the folder is gone or the disk full: still a stopped recording
            summary["error"] = self.error = self.error or f"meta.json not written: {err}"
        _LOG.info("recording stopped: %d frames, %d dropped", self.frames, self.dropped)
        return summary

    def on_pad(self, source: str, state: PadState, ts: float) -> None:
        """Called from the input paths: only remembers a change, the worker thread writes it."""
        if not self.active or self._last_pad.get(source) == state:
            return
        self._last_pad[source] = state
        self._pad.append((ts, source, state))

    def _make_dir(self, directory: str | None) -> Path:
        if directory is not None:
            base = Path(directory).expanduser()
            if not base.is_absolute():  # it would land wherever the daemon happened to be started
                raise ValueError(f"dir must be an absolute path, not {directory!r}")
        else:
            base = (self.daemon.cfg.config_dir.expanduser() / "recordings").resolve()
        folder = base / datetime.now().strftime("%Y%m%d-%H%M%S")
        folder.mkdir(parents=True, exist_ok=False)
        return folder

    def _write_meta(self) -> None:
        (self.dir / "meta.json").write_text(json.dumps(self._meta, indent=2) + "\n")

    def _on_frame(self, frame_id: int, ts: float, rgb: Callable[[], np.ndarray]) -> None:
        """The backend's frame tap, on the decoder's thread: only queues, the worker converts."""
        try:
            self._frames.put_nowait((rgb, frame_id, ts))
        except queue.Full:
            self.dropped += 1

    # --- worker thread ---------------------------------------------------
    def _write(self) -> None:
        import av

        container = stream = None
        try:
            with (
                open(self.dir / "frames.jsonl", "w") as frames_log,
                open(self.dir / "pad.jsonl", "w") as pad_log,
            ):
                while True:
                    try:
                        item = self._frames.get(timeout=0.05)
                    except queue.Empty:
                        item = None
                    if item is not None:
                        rgb, frame_id, ts = item[0](), item[1], item[2]
                        if stream is None:
                            container, stream = self._open(av, rgb.shape[1], rgb.shape[0])
                        picture = av.VideoFrame.from_ndarray(np.ascontiguousarray(rgb), format="rgb24")
                        if (picture.width, picture.height) != (stream.width, stream.height):
                            picture = picture.reformat(stream.width, stream.height)  # resolution changed
                        picture.pts = self.frames
                        for packet in stream.encode(picture):
                            container.mux(packet)
                        line = {"i": self.frames, "frame_id": frame_id, "t": round(ts - self._t0, 4)}
                        frames_log.write(json.dumps(line) + "\n")
                        self.frames += 1
                    while self._pad:
                        ts, source, state = self._pad.popleft()
                        line = {"t": round(ts - self._t0, 4), "src": source, **state.as_dict()}
                        pad_log.write(json.dumps(line) + "\n")
                        self.pad_events += 1
                    if item is None and self._stop.is_set():
                        break
        except Exception as err:
            self.error = f"{type(err).__name__}: {err}"
            _LOG.exception("recording failed")
            self._abandon()
        finally:
            if container is not None:
                with contextlib.suppress(Exception):
                    for packet in stream.encode():
                        container.mux(packet)
                with contextlib.suppress(Exception):
                    container.close()

    def _abandon(self) -> None:
        """The writer died: stop taking frames and input, or they would pile up in memory unseen."""
        self._seconds = time.monotonic() - self._t0
        self._failed = True
        self.daemon.backend.set_frame_tap(None)
        self._pad.clear()
        with contextlib.suppress(queue.Empty):
            while True:
                self._frames.get_nowait()

    def _open(self, av, width: int, height: int):
        for name, options in ENCODERS:
            try:
                av.codec.Codec(name, "w")
            except Exception:
                continue
            container = av.open(str(self.dir / "video.mp4"), "w")
            stream = container.add_stream(name, rate=self.daemon.cfg.fps)
            stream.width, stream.height, stream.pix_fmt = width, height, "yuv420p"
            if options:
                stream.options = options
            self.codec = name
            return container, stream
        raise ConsoleError("no video encoder available")
