"""Small synchronous client for the local recording and controller bridge."""

from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np

from pilot.contract import Command

# Stopping joins the recorder's writer thread, which can take seconds, and a client that hangs up in
# the middle leaves the daemon reporting "recording" for good.
RECORD_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class Frame:
    rgb: np.ndarray
    id: int
    age: float


class Bridge:
    def __init__(
        self,
        url: str = "http://127.0.0.1:9395",
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.client = httpx.Client(base_url=url, timeout=0.5, transport=transport)

    def frame(self, rect: tuple[int, int, int, int], after: int | None = None) -> Frame | None:
        x, y, width, height = rect
        params = {"x": x, "y": y, "w": width, "h": height, "wait_ms": 100}
        if after is not None:
            params["after"] = after
        response = self.client.get("/frame.raw", params=params)
        if response.status_code == 204:
            return None
        response.raise_for_status()
        width = int(response.headers["X-Width"])
        height = int(response.headers["X-Height"])
        rgb = np.frombuffer(response.content, dtype=np.uint8).reshape(height, width, 3)
        return Frame(
            rgb=rgb,
            id=int(response.headers["X-Frame-Id"]),
            age=float(response.headers["X-Frame-Age-Ms"]) / 1000,
        )

    def status(self) -> dict:
        response = self.client.get("/status")
        response.raise_for_status()
        return response.json()

    def pad(self, command: Command | None = None) -> int:
        payload = (
            {}
            if command is None
            else {
                "buttons": [],
                "left": [command.steer, 0],
                "right": [0, 0],
                "l2": command.brake,
                "r2": command.throttle,
                "ttl_ms": 250,
            }
        )
        response = self.client.post("/pad", json=payload)
        if response.status_code == 409:
            return 409
        response.raise_for_status()
        return response.status_code

    def record_start(self, directory: Path, *, shadow: bool) -> Path:
        response = self.client.post(
            "/record",
            json={
                "action": "start",
                "dir": str(directory.resolve()),
                "note": "pilot shadow" if shadow else "pilot drive",
            },
            timeout=RECORD_TIMEOUT_S,
        )
        response.raise_for_status()
        destination = Path(response.json()["dir"])
        if not destination.is_absolute():
            raise ValueError("Recorder returned a non-absolute directory")
        return destination

    def record_stop(self) -> None:
        response = self.client.post("/record", json={"action": "stop"}, timeout=RECORD_TIMEOUT_S)
        response.raise_for_status()

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "Bridge":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
