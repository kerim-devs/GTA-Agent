"""Offline: the real RemotePlayBackend + the real vendored Controller and FeedbackPacket, against a
stub session whose stream only packs the packet (no socket, no daemon, no console)."""
import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

from ps5_remoteplay_mcp.backend import ConsoleError, Side
from ps5_remoteplay_mcp.backend.remoteplay import RemotePlayBackend
from ps5_remoteplay_mcp.config import Config
from ps5_remoteplay_mcp.vendor.pyremoteplay.const import TYPE_PS5
from ps5_remoteplay_mcp.vendor.pyremoteplay.controller import Controller
from ps5_remoteplay_mcp.vendor.pyremoteplay.stream_packets import FeedbackPacket


class Stream:
    def __init__(self):
        self._protocol = SimpleNamespace(transport=SimpleNamespace(is_closing=lambda: False))
        self.count = 0

    def send_feedback(self, feedback_type, sequence, data=b"", state=None):  # as RPStream.send_feedback
        FeedbackPacket(feedback_type, sequence=sequence, data=data, state=state, host_type=TYPE_PS5).bytes()
        self.count += 1


class Device:
    def __init__(self):
        self.stream = Stream()
        self.session = SimpleNamespace(is_ready=True, is_stopped=False, stream=self.stream)
        self.controller = Controller()
        self.controller._session = self.session

    def disconnect(self):
        self.session = None


async def main():
    backend = RemotePlayBackend(Config(config_dir=Path(tempfile.mkdtemp())))
    backend.device = Device()
    await backend.set_trigger(Side.RIGHT, 0.6)  # throttle held, nothing else ever changes
    n = 0
    try:
        while True:
            await backend.resend_input()
            n += 1
    except ConsoleError as err:
        print("resends that worked:", n, "-> minutes at 50 ms:", round(n * 0.05 / 60, 1))
        print("error:", err)
        print("session after:", backend.device.session, "| tracked triggers:", backend._triggers)


asyncio.run(main())
