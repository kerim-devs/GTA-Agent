"""Exercise resend timing without the supervisor, sockets or wall-clock sleeps."""

import asyncio
from itertools import pairwise
from types import SimpleNamespace

import pytest

from ps5_remoteplay_mcp import daemon as daemon_module
from ps5_remoteplay_mcp.backend import fake as fake_module
from ps5_remoteplay_mcp.backend.base import RESEND_SETTLE_S
from ps5_remoteplay_mcp.daemon import Daemon


async def run_resender(monkeypatch, fake, frames, states=None):
    """Advance only the resend loop, with a frame age for each 50 ms tick."""
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(daemon_module, "time", SimpleNamespace(monotonic=lambda: clock.now))
    monkeypatch.setattr(fake_module, "time", SimpleNamespace(monotonic=lambda: clock.now))
    daemon = Daemon.__new__(Daemon)
    daemon.backend = fake
    daemon.state = "up"
    fake.connected = True
    fake._input_at = 0.0
    counts = []
    ticks = iter(enumerate(frames, start=1))

    async def tick(delay):
        assert delay == 0.05
        counts.append(fake.resends)
        try:
            index, age = next(ticks)
        except StopIteration:
            raise asyncio.CancelledError from None
        clock.now = 100.0 + index * delay
        fake.stall_s = age if isinstance(age, float) else 0.0

        def frame_ts():
            if age == "error":
                raise RuntimeError("receiver gone")
            return None if age is None else clock.now - age

        monkeypatch.setattr(fake, "frame_ts", frame_ts, raising=False)
        if states is not None:
            daemon.state = states[index - 1]

    monkeypatch.setattr(daemon_module, "asyncio", SimpleNamespace(sleep=tick))
    with pytest.raises(asyncio.CancelledError):
        await daemon._resend_input()
    return [after - before for before, after in pairwise(counts)]


async def test_short_freeze_repeats_idle_input_then_returns_to_heartbeat(monkeypatch, fake):
    # All frozen frames are below the supervisor's two-second threshold.
    frozen = [0.4 + tick * 0.05 for tick in range(20)]
    repeats = await run_resender(monkeypatch, fake, frozen + [0.0] * 30)
    assert sum(repeats[:20]) == 20
    assert sum(repeats[20:28]) == 8  # the release keeps healing after video resumes
    assert RESEND_SETTLE_S == 0.5
    assert 3 <= sum(repeats[30:]) <= 4


async def test_a_failing_frame_timestamp_does_not_end_the_resender(monkeypatch, fake):
    repeats = await run_resender(monkeypatch, fake, ["error"] * 3 + [None] * 5)
    assert repeats == [0, 0, 0, 1, 1, 1, 1, 1]


async def test_fresh_idle_input_has_a_slow_heartbeat(monkeypatch, fake):
    repeats = await run_resender(monkeypatch, fake, [0.0] * 40)
    sent_at = [tick for tick, sent in enumerate(repeats) if sent]
    assert 6 <= len(sent_at) <= 8
    assert all(5 <= right - left <= 6 for left, right in pairwise(sent_at))


@pytest.mark.parametrize("state, age", [("up", None), ("stalled", 0.0)])
async def test_missing_frame_or_stalled_state_keeps_healing(monkeypatch, fake, state, age):
    repeats = await run_resender(monkeypatch, fake, [age] * 20, [state] * 20)
    assert sum(repeats) == 20


async def test_resender_skips_sessions_that_are_not_up(monkeypatch, fake):
    states = ["starting", "connecting", "reconnecting", "standby", "unreachable", "not_set_up"]
    repeats = await run_resender(monkeypatch, fake, [None] * len(states), states)
    assert repeats == [0] * len(states)


def test_fake_exposes_the_current_frame_timestamp(monkeypatch, fake):
    monkeypatch.setattr(fake_module, "time", SimpleNamespace(monotonic=lambda: 100.0))
    fake.connected = False
    assert fake.frame_ts() is None
    fake.connected = True
    fake.stall_s = 0.7
    assert fake.frame_ts() == 99.3
