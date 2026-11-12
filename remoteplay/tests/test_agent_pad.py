import argparse
import asyncio

import httpx
import numpy as np
import pytest

from ps5_remoteplay_mcp import agent_pad, cli
from ps5_remoteplay_mcp.backend import Button, Side
from ps5_remoteplay_mcp.backend.base import RESEND_SETTLE_S
from ps5_remoteplay_mcp.client import DaemonClient, DaemonError
from ps5_remoteplay_mcp.gamepad import IDLE, PadState

from .conftest import wait_until as until


@pytest.fixture
async def client(cfg, daemon):
    c = DaemonClient(cfg, autostart=False)
    yield c
    await c.aclose()


async def test_state_is_sent_as_a_diff_and_expires_when_the_loop_goes_silent(client, daemon, fake):
    await client.pad(left=[0.3, 0], r2=0.6, buttons=["r1"], ttl_ms=400)
    assert fake.sticks[Side.LEFT] == (0.3, 0.0)
    assert fake.triggers[Side.RIGHT] == 0.6 and fake.pressed == {Button.R1}
    assert (await client.status())["agent_pad"] is True
    sent = len(fake.log)
    await client.pad(left=[0.3, 0], r2=0.6, buttons=["r1"], ttl_ms=400)
    assert len(fake.log) == sent  # a refresh of the same state sends nothing to the console
    await client.pad(left=[-0.2, 0], r2=0.6, buttons=["r1"], ttl_ms=150)
    assert [op for _, op, _ in fake.log[sent:]] == ["stick"]
    await until(lambda: fake.idle)
    assert daemon.agent_pad.expired == 1
    assert (await client.status())["agent_pad"] is False


async def test_human_takes_the_controller_from_the_loop(client, daemon, fake):
    await client.pad(left=[1, 0], r2=1.0, ttl_ms=1000)
    daemon.pad.submit(PadState(frozenset({Button.CIRCLE})))
    await until(lambda: fake.pressed == {Button.CIRCLE})
    assert fake.triggers[Side.RIGHT] == 0 and fake.sticks[Side.LEFT] == (0.0, 0.0)
    with pytest.raises(DaemonError, match="computer gamepad"):
        await client.pad(r2=1.0)
    assert fake.triggers[Side.RIGHT] == 0
    daemon.pad.submit(IDLE)
    await until(lambda: fake.idle)
    async with asyncio.timeout(3):
        while daemon.pad.active:  # noqa: ASYNC110 — exercise the real grace deadline
            await asyncio.sleep(0.02)
    await client.pad(r2=0.5, ttl_ms=1000)
    assert fake.triggers[Side.RIGHT] == 0.5


async def test_stalled_stream_releases_the_loop(client, daemon, fake):
    await client.pad(r2=1.0, ttl_ms=1000)
    fake.stall_s = 5
    await until(lambda: daemon.state == "stalled" and fake.idle)
    with pytest.raises(DaemonError, match="not live"):
        await client.pad(r2=1.0)
    fake.stall_s = 0


async def test_session_loss_makes_the_loop_send_its_state_in_full_again(client, daemon, fake):
    await client.pad(r2=1.0, ttl_ms=1000)
    fake.connected = False
    await until(lambda: daemon.session_epoch == 1 and fake.connected and daemon.state == "up")
    assert fake.idle and not daemon.agent_pad.active
    await client.pad(r2=1.0, ttl_ms=1000)
    assert fake.triggers[Side.RIGHT] == 1.0


async def test_button_sequence_takes_over_from_the_loop(client, daemon, fake):
    await client.pad(left=[0.5, 0], r2=1.0, ttl_ms=1000)
    await client.input("press", button="right", duration_ms=1)
    assert fake.idle and fake.index == 1
    await client.pad(r2=1.0, ttl_ms=1000)
    assert fake.triggers[Side.RIGHT] == 1.0


async def test_loop_is_refused_while_a_sequence_runs(client, daemon, fake):
    task = asyncio.create_task(client.input("hold", button="cross", duration_ms=600))
    await until(lambda: Button.CROSS in fake.pressed)
    with pytest.raises(DaemonError, match="another input"):
        await client.pad(r2=1.0)
    await task
    assert fake.idle


@pytest.mark.parametrize(
    "body",
    [
        {"left": [2, 0]},
        {"left": [0]},
        {"left": 1},
        {"r2": 1.5},
        {"buttons": ["nope"]},
        {"ttl_ms": 5000},
        {"ttl_ms": None},
        {"buttons": None},
        {"buttons": 5},
        ["r1"],
    ],
)
async def test_bad_state_is_rejected(cfg, daemon, fake, body):
    async with httpx.AsyncClient(base_url=cfg.daemon_url) as http:
        reply = await http.post("/pad", json=body)
    assert reply.status_code == 400 and fake.idle


async def test_pad_state_can_be_read_back(cfg, client, daemon, fake):
    await client.pad(right=[0, -0.5], l2=0.25, ttl_ms=1000)
    async with httpx.AsyncClient(base_url=cfg.daemon_url) as http:
        state = (await http.get("/pad")).json()
    assert state["agent"] == {"buttons": [], "left": [0.0, 0.0], "right": [0.0, -0.5], "l2": 0.25, "r2": 0.0}
    assert state["human"]["buttons"] == [] and state["human_input"] is False


async def test_raw_frame_returns_the_requested_crop(cfg, daemon, fake):
    frame = fake.latest_frame()
    async with httpx.AsyncClient(base_url=cfg.daemon_url) as http:
        reply = await http.get("/frame.raw", params={"x": 100, "y": 50, "w": 64, "h": 32})
        assert reply.status_code == 200 and int(reply.headers["x-frame-id"]) == frame.frame_id
        crop = np.frombuffer(reply.content, np.uint8).reshape(32, 64, 3)
        assert (crop == frame.rgb[50:82, 100:164]).all()
        halved = await http.get("/frame.raw", params={"step": 2})
        assert (halved.headers["x-width"], halved.headers["x-height"]) == ("640", "360")
        assert len(halved.content) == 640 * 360 * 3
        assert (await http.get("/frame.raw", params={"after": frame.frame_id})).status_code == 204
        assert (await http.get("/frame.raw", params={"x": 5000})).status_code == 400


async def test_held_state_is_repeated_to_the_console_until_shortly_after_release(client, daemon, fake):
    await client.pad(r2=0.6, ttl_ms=1000)
    await until(lambda: fake.resends >= 3)  # one lost packet must not leave the car standing
    await client.input("release_all")
    assert fake.idle
    before = fake.resends
    await asyncio.sleep(RESEND_SETTLE_S + 0.3)
    assert fake.resends > before  # the release is repeated too
    settled = fake.resends
    await asyncio.sleep(0.3)
    assert 1 <= fake.resends - settled <= 2  # only the slow idle heartbeat remains


async def test_a_frozen_stream_keeps_repeating_the_release_until_the_picture_is_back(client, daemon, fake):
    await client.pad(r2=1.0, ttl_ms=1000)
    fake.stall_s = 5
    await until(lambda: daemon.state == "stalled" and fake.idle)
    await asyncio.sleep(RESEND_SETTLE_S + 0.2)  # long past the time a release is repeated on a live stream
    frozen = fake.resends
    await asyncio.sleep(0.2)
    assert fake.resends > frozen  # the packets of the last seconds were lost, the release maybe too
    fake.stall_s = 0
    await until(lambda: daemon.state == "up")
    await asyncio.sleep(RESEND_SETTLE_S + 0.2)
    settled = fake.resends
    await asyncio.sleep(0.2)
    assert fake.resends - settled <= 1  # healing ended; at most one slow heartbeat


async def test_a_sequence_drops_a_loop_state_that_slipped_in_while_it_waited(
    client, daemon, fake, monkeypatch
):
    monkeypatch.setattr(agent_pad, "BUSY_WAIT_S", 2.0)
    first = asyncio.create_task(client.input("hold", button="square", duration_ms=300))
    await until(lambda: Button.SQUARE in fake.pressed)
    loop_state = asyncio.create_task(client.pad(r2=1.0, ttl_ms=200))  # first in line behind the hold ...
    await asyncio.sleep(0.05)
    second = asyncio.create_task(client.input("hold", button="cross", duration_ms=600))  # ... then this
    await first
    await loop_state
    await until(lambda: Button.CROSS in fake.pressed)
    assert fake.triggers[Side.RIGHT] == 0  # the sequence owns the controller now
    await asyncio.sleep(0.35)  # past the loop state's lifetime: its expiry must not cut the hold
    assert Button.CROSS in fake.pressed and daemon.agent_pad.expired == 0
    await second
    assert fake.idle


async def test_a_sweep_ends_released_and_leaves_a_human_who_took_over_alone(cfg, daemon, fake):
    args = argparse.Namespace(seconds=0.4, throttle=0.5, steer=0.6, period=3.0)
    await asyncio.to_thread(cli.cmd_sweep, cfg, args)
    assert fake.idle  # a sweep that runs to its end holds nothing afterwards

    def stopped_sweep() -> str:
        try:
            cli.cmd_sweep(cfg, argparse.Namespace(seconds=30.0, throttle=0.5, steer=0.6, period=3.0))
        except SystemExit as stop:  # must not reach the event loop
            return str(stop)
        return "ran to its end"

    sweep = asyncio.create_task(asyncio.to_thread(stopped_sweep))
    await until(lambda: fake.triggers[Side.RIGHT] == 0.5)
    daemon.pad.submit(PadState(frozenset({Button.CIRCLE})))  # the human grabs the controller
    assert "computer gamepad" in await sweep
    assert fake.pressed == {Button.CIRCLE} and fake.triggers[Side.RIGHT] == 0
    assert daemon.pad.active  # still the human's turn: the sweep's cleanup did not reset it
