"""Offline: Daemon object + FakeBackend, no HTTP server, no port, no console.
Is the release that a stalled stream triggers ever repeated?"""
import asyncio
import tempfile
import time
from pathlib import Path

from ps5_remoteplay_mcp import config
from ps5_remoteplay_mcp.agent_pad import parse_state
from ps5_remoteplay_mcp.backend.fake import FakeBackend
from ps5_remoteplay_mcp.config import Config
from ps5_remoteplay_mcp.daemon import Daemon

tmp = Path(tempfile.mkdtemp())
config.CONFIG_BASE = tmp  # keep the default config folder out of the real home, like tests/conftest.py


async def until(pred, timeout=8.0):
    end = time.monotonic() + timeout
    while not pred():
        assert time.monotonic() < end, "condition not reached"
        await asyncio.sleep(0.005)


async def main():
    fake = FakeBackend()
    d = Daemon(Config(backend="fake", daemon_port=1, max_hold_ms=2000, config_dir=tmp), fake)
    await d.start()
    await until(lambda: fake.connected and d.state == "up")
    await d.agent_pad.set(parse_state({"r2": 0.6, "left": [0.3, 0]}), 1000)
    await asyncio.sleep(0.3)
    print("resends while held and up:", fake.resends)
    fake.stall_s = 3  # newest frame 3 s old: stalled, but not yet the 10 s reconnect
    await until(lambda: d.state == "stalled" and fake.idle)
    base = fake.resends
    print("release sent on the stall:", [op for _, op, _ in fake.log][-1])
    await asyncio.sleep(1.0)
    print("resends in the 1 s after that release (stalled):", fake.resends - base)
    fake.stall_s = 0
    await until(lambda: d.state == "up")
    await asyncio.sleep(1.0)
    print("resends in the 1 s after the stream is live again:", fake.resends - base)
    await d.stop()


asyncio.run(main())
