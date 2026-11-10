import argparse
import asyncio
import json
import time
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import av
import numpy as np
import pytest

from ps5_remoteplay_mcp import cli
from ps5_remoteplay_mcp.backend import Button
from ps5_remoteplay_mcp.backend.remoteplay import _make_receiver
from ps5_remoteplay_mcp.client import DaemonClient, DaemonError
from ps5_remoteplay_mcp.gamepad import IDLE, PadState

from .conftest import wait_until as until


@pytest.fixture
async def client(cfg, daemon):
    c = DaemonClient(cfg, autostart=False)
    yield c
    await c.aclose()


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


async def test_recording_keeps_picture_and_both_controllers_on_one_clock(client, daemon, fake, tmp_path):
    started = await client.record("start", directory=str(tmp_path / "rec"), note="first drive")
    folder = Path(started["dir"])
    assert started["recording"] and folder.parent == tmp_path / "rec"
    assert (await client.status())["recording"] is True
    for step in range(1, 5):  # the fake console shows a new picture for every d-pad step
        await client.pad(buttons=["right"], ttl_ms=1000)
        await client.pad(ttl_ms=1000)
        await until(lambda step=step: daemon.recorder.frames > step)
    daemon.pad.submit(PadState(frozenset({Button.CROSS})))
    await until(lambda: fake.pressed == {Button.CROSS})
    daemon.pad.submit(IDLE)
    await until(lambda: fake.idle)
    summary = await client.record("stop")

    assert summary["recording"] is False and summary["frames"] == 5
    assert summary["dropped"] == 0 and not summary["error"]
    frames = _lines(folder / "frames.jsonl")
    assert [f["i"] for f in frames] == list(range(5))
    assert all(a["t"] <= b["t"] for a, b in pairwise(frames))
    with av.open(str(folder / "video.mp4")) as video:
        assert sum(1 for _ in video.decode(video=0)) == 5
    pad = _lines(folder / "pad.jsonl")
    assert all(a["t"] <= b["t"] for a, b in pairwise(pad))
    assert sum(e["src"] == "agent" and e["buttons"] == ["right"] for e in pad) == 4
    assert any(e["src"] == "human" and e["buttons"] == ["cross"] for e in pad)
    assert pad[-1] == {"t": pad[-1]["t"], "src": "human", "buttons": [], **IDLE.as_dict()}
    meta = json.loads((folder / "meta.json").read_text())
    assert meta["note"] == "first drive" and meta["frames"] == 5 and meta["codec"]


async def test_one_recording_at_a_time_and_stop_is_safe_when_idle(client, daemon, fake, tmp_path):
    assert (await client.record("stop"))["recording"] is False
    await client.record("start", directory=str(tmp_path))
    with pytest.raises(DaemonError, match="already recording"):
        await client.record("start", directory=str(tmp_path))
    assert (await client.record_status())["recording"] is True
    await daemon.stop()  # a daemon that shuts down closes the file properly
    assert not daemon.recorder.active and not daemon.recorder.error


async def test_a_burst_of_frames_is_recorded_in_full(client, daemon, fake, tmp_path):
    started = await client.record("start", directory=str(tmp_path))
    fake.burst(12)  # all decoded before the event loop runs again, like a stream catching up
    await until(lambda: daemon.recorder.frames == 13)
    summary = await client.record("stop")
    assert summary["frames"] == 13 and summary["dropped"] == 0
    ids = [f["frame_id"] for f in _lines(Path(started["dir"]) / "frames.jsonl")]
    assert ids == list(range(ids[0], ids[0] + 13))
    fake.burst(3)  # a stopped recording no longer listens
    assert daemon.recorder.frames == 13


async def test_frames_beyond_the_queue_are_counted(client, daemon, fake, tmp_path):
    await client.record("start", directory=str(tmp_path))
    fake.burst(300)  # far more than the worker can take at once
    summary = await client.record("stop")
    assert summary["dropped"] > 0 and summary["frames"] + summary["dropped"] == 301


def test_the_remote_play_receiver_hands_every_decoded_frame_to_the_tap():
    seen = []
    taps = [lambda frame_id, ts, rgb: seen.append((frame_id, rgb))]
    receiver = _make_receiver(lambda: taps[0])
    receiver._session = SimpleNamespace(events=SimpleNamespace(emit=lambda *args: None))
    shades = (10, 120, 240)
    for shade in shades:
        picture = av.VideoFrame.from_ndarray(np.full((72, 128, 3), shade, np.uint8), format="rgb24")
        receiver.handle_video(picture.reformat(format="yuv420p"))
    assert [frame_id for frame_id, _ in seen] == [1, 2, 3]
    assert [rgb().shape for _, rgb in seen] == [(72, 128, 3)] * 3
    assert all(abs(int(rgb()[0, 0, 0]) - shade) <= 3 for (_, rgb), shade in zip(seen, shades, strict=True))
    taps[0] = lambda *args: 1 / 0  # a failing tap must not stop the decoder
    receiver.handle_video(picture.reformat(format="yuv420p"))
    assert receiver.newest()[0] == 4


async def test_a_recording_whose_writer_dies_ends_itself_and_takes_nothing_more(
    client, daemon, fake, tmp_path
):
    started = await client.record("start", directory=str(tmp_path / "one"))
    daemon.recorder._on_frame(999, time.monotonic(), lambda: 1 / 0)  # a picture that cannot be converted
    await until(lambda: not daemon.recorder.active)
    assert fake._frame_tap is None
    daemon.pad.submit(PadState(frozenset({Button.CROSS})))
    await until(lambda: fake.pressed == {Button.CROSS})
    fake.burst(5)
    assert not daemon.recorder._pad and daemon.recorder._frames.empty()  # nothing piles up unseen
    status = await client.record_status()
    assert status["recording"] is False and "ZeroDivisionError" in status["error"]
    again = await client.record("start", directory=str(tmp_path / "two"))  # closes the dead one first
    assert again["recording"] is True and not again["error"]
    meta = json.loads((Path(started["dir"]) / "meta.json").read_text())
    assert "ZeroDivisionError" in meta["error"] and meta["frames"] == 1


async def test_stop_can_be_called_twice_at_once_and_a_lost_folder_does_not_block_shutdown(
    client, daemon, fake, tmp_path, monkeypatch
):
    await client.record("start", directory=str(tmp_path))
    first, second = await asyncio.gather(daemon.recorder.stop(), daemon.recorder.stop())
    assert not first["recording"] and not second["recording"] and not daemon.recorder.error

    await client.record("start", directory=str(tmp_path / "gone"))
    monkeypatch.setattr(daemon.recorder, "_write_meta", lambda: (_ for _ in ()).throw(OSError("disk full")))
    summary = await daemon.recorder.stop()
    assert not summary["recording"] and "disk full" in summary["error"]

    await client.pad(r2=1.0, ttl_ms=1000)
    monkeypatch.setattr(daemon.recorder, "stop", lambda: 1 / 0)
    await daemon.stop()  # whatever the recorder does, the input is released
    assert fake.idle


async def test_a_relative_folder_is_refused_by_the_daemon_and_resolved_by_the_cli(
    cfg, client, daemon, fake, tmp_path, monkeypatch
):
    with pytest.raises(DaemonError, match="absolute"):
        await client.record("start", directory="recordings")
    assert not daemon.recorder.active
    monkeypatch.chdir(tmp_path)
    args = argparse.Namespace(action="start", output="mine", note=None)
    await asyncio.to_thread(cli.cmd_record, cfg, args)
    assert daemon.recorder.active and daemon.recorder.dir.parent == (tmp_path / "mine").resolve()
