"""Read-only, loopback-only OBS view of conductor recordings."""

from __future__ import annotations

import argparse
import json
import math
import threading
import time
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class JsonlTail:
    """Keep partial lines until complete, and recover after replacement/truncation."""

    def __init__(self, path: Path):
        self.path = path
        self.identity = None
        self.offset = 0
        self.pending = b""
        self.discarding = False
        self.anchor = b""

    def read(self) -> list[dict]:
        try:
            with self.path.open("rb") as stream:
                stat = self.path.stat()
                identity = (stat.st_dev, stat.st_ino)
                stream.seek(max(0, self.offset - len(self.anchor)))
                replaced = stream.read(len(self.anchor)) != self.anchor
                if identity != self.identity or stat.st_size < self.offset or replaced:
                    self.offset = 0
                    self.pending = b""
                    self.discarding = False
                self.identity = identity
                stream.seek(self.offset)
                data = stream.read(1024 * 1024)
                self.offset = stream.tell()
                stream.seek(max(0, self.offset - 64))
                self.anchor = stream.read(min(self.offset, 64))
        except OSError:
            return []
        parts = (self.pending + data).split(b"\n")
        self.pending = parts.pop()
        rows = []
        for line in parts:
            if self.discarding:
                self.discarding = False
                continue
            if len(line) > 1024 * 1024:
                continue
            try:
                row = json.loads(line)
            except (ValueError, UnicodeDecodeError, RecursionError):
                continue
            if isinstance(row, dict):
                rows.append(row)
        if len(self.pending) > 1024 * 1024 or self.discarding:
            self.pending = b""
            self.discarding = True
        return rows


def _empty() -> dict:
    return {
        "session": None,
        "mode": "live",
        "status": "waiting",
        "thinking": False,
        "sentence": "",
        "plan": [],
        "skill": None,
        "objective": "",
        "help": "",
        "speed_kmh": None,
        "distance_m": None,
        "takeover": False,
        "shadow": None,
    }


class OverlayState:
    def __init__(self, root: Path, demo: Path | None = None, clock=time.monotonic, shadow: bool = False):
        self.root = Path(root)
        self.demo = Path(demo) if demo is not None else None
        self.clock = clock
        self.shadow = shadow
        self.lock = threading.Lock()
        self.session = None
        self.tails = {}
        self.state = _empty()
        self.pending_id = None
        self.updated_at = None
        self.demo_events = []
        self.demo_index = 0
        self.demo_started = None

    def _latest(self) -> Path | None:
        if self.demo is not None:
            return self.demo if self.demo.is_dir() else None
        try:
            candidates = [
                path
                for path in self.root.iterdir()
                if path.is_dir() and any((path / name).is_file() for name in ("head.jsonl", "play.jsonl"))
            ]
            return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name), default=None)
        except OSError:
            return self.session

    def _select(self, session: Path) -> None:
        self.session = session
        self.state = _empty()
        self.state.update(session=session.name, mode="demo" if self.demo else "live", shadow=self.shadow)
        self.pending_id = None
        self.updated_at = None
        self.tails = {name: JsonlTail(session / f"{name}.jsonl") for name in ("head", "play")}
        if self.demo is not None:
            self._load_demo()

    def _load_demo(self) -> None:
        rows = {}
        for name, tail in self.tails.items():
            rows[name] = []
            while True:
                before = tail.offset
                rows[name].extend(tail.read())
                if before == tail.offset:
                    break
        self.demo_events = self._timeline(rows)
        self.demo_index = 0
        self.demo_started = self.clock()

    @staticmethod
    def _timeline(rows: dict) -> list:
        # Head observations use monotonic timestamps; play ticks use elapsed time.
        head_times = [
            row["t"] for row in rows["head"] if row.get("type") == "request" and _number(row.get("t"))
        ]
        play_times = [row["t"] for row in rows["play"] if row.get("fresh") is True and _number(row.get("t"))]
        # The startup request and the first fresh play tick share an observation.
        # Legacy/incomplete recordings without that pair start the head at zero.
        offset = (play_times[0] if play_times else 0) - (head_times[0] if head_times else 0)
        events = []
        for name in ("head", "play"):
            for row in rows[name]:
                timestamp = row.get("t")
                if not _number(timestamp):
                    continue
                when = max(0, timestamp + offset) if name == "head" else max(0, timestamp)
                events.append((when, name, row))
        return sorted(events, key=lambda event: event[0])

    def _apply(self, source: str, row: dict) -> None:
        if source == "head":
            kind = row.get("type")
            if kind == "request":
                self.pending_id = row.get("id")
                self.state["thinking"] = True
                request = row.get("request")
                if isinstance(request, dict):
                    for key in ("objective", "help"):
                        value = request.get(key)
                        self.state[key] = value[:2000] if isinstance(value, str) else ""
            elif kind == "response":
                if row.get("id") == self.pending_id:
                    self.state["thinking"] = False
                if row.get("applied") is True and row.get("overtaken") is not True:
                    sentence = row.get("sentence")
                    self.state["sentence"] = sentence[:4000] if isinstance(sentence, str) else ""
                    plan = row.get("plan")
                    self.state["plan"] = [
                        {"name": step["name"][:100]}
                        for step in (plan[:20] if isinstance(plan, list) else [])
                        if isinstance(step, dict) and isinstance(step.get("name"), str)
                    ]
            else:
                return
        else:
            skill = row.get("skill")
            self.state["skill"] = (
                {key: str(skill.get(key, ""))[:100] for key in ("name", "status")}
                if isinstance(skill, dict)
                else None
            )
            reading = row.get("reading")
            reading = reading if isinstance(reading, dict) else {}
            for field, key, factor in (("gps_speed", "speed_kmh", 3.6), ("gps_distance", "distance_m", 1)):
                value = reading.get(field)
                converted = value * factor if _number(value) and value >= 0 else None
                self.state[key] = converted if _number(converted) else None
            if row.get("status") == 409:
                self.state["takeover"] = True
            elif row.get("status") == 200 and row.get("sent") is True:
                self.state["takeover"] = False
            # Absence of a send is not evidence of shadow mode.
            self.state["shadow"] = row.get("shadow") if isinstance(row.get("shadow"), bool) else self.shadow
        self.updated_at = self.clock()

    def snapshot(self) -> dict:
        with self.lock:
            session = self._latest()
            if session is not None and session != self.session:
                self._select(session)
            if self.session is not None:
                if self.demo is not None:
                    elapsed = self.clock() - self.demo_started
                    while self.demo_index < len(self.demo_events):
                        when, source, row = self.demo_events[self.demo_index]
                        if when > elapsed:
                            break
                        self._apply(source, row)
                        self.demo_index += 1
                    self.state["status"] = "ended" if self.demo_index == len(self.demo_events) else "playing"
                else:
                    for source, tail in self.tails.items():
                        for row in tail.read():
                            self._apply(source, row)
                    self.state["status"] = (
                        "waiting"
                        if self.updated_at is None
                        else "stale"
                        if self.clock() - self.updated_at >= 5
                        else "live"
                    )
            return deepcopy(self.state)


def make_server(state: OverlayState, port: int = 9396) -> ThreadingHTTPServer:
    assets = files("pilot").joinpath("overlay_web")
    routes = {
        "/": ("index.html", "text/html; charset=utf-8"),
        "/overlay.css": ("overlay.css", "text/css; charset=utf-8"),
        "/overlay.js": ("overlay.js", "text/javascript; charset=utf-8"),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.connection.settimeout(2)
                try:
                    while not self.server.stopping.is_set():
                        payload = json.dumps(state.snapshot(), ensure_ascii=False, allow_nan=False)
                        self.wfile.write(f"data: {payload}\n\n".encode())
                        self.wfile.flush()
                        self.server.stopping.wait(0.2)
                except (ConnectionError, TimeoutError):
                    pass
                return
            if path == "/api/state":
                body = json.dumps(state.snapshot(), ensure_ascii=False, allow_nan=False).encode()
                content_type = "application/json; charset=utf-8"
            elif path in routes:
                asset, content_type = routes[path]
                body = assets.joinpath(asset).read_bytes()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; connect-src 'self'; frame-ancestors 'self'; object-src 'none'",
            )
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format, *args):
            pass

    class Server(ThreadingHTTPServer):
        def __init__(self):
            self.stopping = threading.Event()
            super().__init__(("127.0.0.1", port), Handler)

        def server_close(self):
            self.stopping.set()
            super().server_close()

    server = Server()
    server.daemon_threads = True
    return server


def overlay_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def run_overlay(root: Path, port: int = 9396, demo: Path | None = None, shadow: bool = False) -> None:
    state = OverlayState(root, demo, shadow=shadow)
    with make_server(state, port) as server:
        print(f"Overlay: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
