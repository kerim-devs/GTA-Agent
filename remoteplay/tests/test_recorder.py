import argparse
import asyncio
import json
import os
import threading
import time
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

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
    recorder = daemon.recorder
    thread = recorder._thread
    await until(lambda: recorder.frames == 1)
    await asyncio.sleep(0.15)
    entered, release = threading.Event(), threading.Event()

    def broken_frame():
        entered.set()
        assert release.wait(5)
        return 1 / 0

    recorder._on_frame(999, time.monotonic(), broken_frame)
    try:
        await until(entered.is_set)
        recorder.on_pad("agent", PadState(frozenset({Button.CROSS})), time.monotonic())
        fake.burst(5)
        assert recorder._pad and not recorder._frames.empty()
        before_death = time.monotonic() - recorder._t0
    finally:
        release.set()
    await until(lambda: not thread.is_alive())
    after_death = time.monotonic() - recorder._t0
    assert before_death <= recorder._seconds <= after_death
    death_seconds = recorder._seconds
    assert not recorder._pad and recorder._frames.empty()
    assert fake._frame_tap is None
    daemon.pad.submit(PadState(frozenset({Button.CROSS})))
    await until(lambda: fake.pressed == {Button.CROSS})
    fake.burst(5)
    assert not daemon.recorder._pad and daemon.recorder._frames.empty()  # nothing piles up unseen
    status = await client.record_status()
    assert status["recording"] is False and "ZeroDivisionError" in status["error"]
    await asyncio.sleep(0.15)
    again = await client.record("start", directory=str(tmp_path / "two"))  # closes the dead one first
    assert again["recording"] is True and not again["error"]
    meta = json.loads((Path(started["dir"]) / "meta.json").read_text())
    assert "ZeroDivisionError" in meta["error"] and meta["frames"] == 1
    assert meta["seconds"] == round(death_seconds, 1) > 0


async def test_stop_can_be_called_twice_at_once_and_a_lost_folder_does_not_block_shutdown(
    client, daemon, fake, tmp_path, monkeypatch
):
    await client.record("start", directory=str(tmp_path))
    write_meta = Mock(wraps=daemon.recorder._write_meta)
    monkeypatch.setattr(daemon.recorder, "_write_meta", write_meta)
    first, second = await asyncio.gather(daemon.recorder.stop(), daemon.recorder.stop())
    assert not first["recording"] and not second["recording"] and not daemon.recorder.error
    write_meta.assert_called_once_with()

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


async def test_concurrent_starts_after_writer_failure_allow_only_one_recording(
    client, daemon, tmp_path, monkeypatch
):
    recorder = daemon.recorder
    await client.record("start", directory=str(tmp_path / "failed"))
    thread = recorder._thread
    recorder._on_frame(999, time.monotonic(), lambda: 1 / 0)
    await until(lambda: not thread.is_alive())
    stop = recorder.stop
    both_stopping = asyncio.Event()
    calls = 0

    async def synchronized_stop():
        nonlocal calls
        calls += 1
        if calls == 2:
            both_stopping.set()
        await asyncio.wait_for(both_stopping.wait(), timeout=2)
        return await stop()

    with monkeypatch.context() as patch:
        patch.setattr(recorder, "stop", synchronized_stop)
        results = await asyncio.gather(
            client._http.post("/record", json={"action": "start", "dir": str(tmp_path / "first")}),
            client._http.post("/record", json={"action": "start", "dir": str(tmp_path / "second")}),
        )
    assert sorted(result.status_code for result in results) == [200, 409]
    success = next(result.json() for result in results if result.status_code == 200)
    error = next(result.json() for result in results if result.status_code == 409)
    assert success["recording"] and "already recording" in error["error"]
    assert recorder._thread.is_alive()


async def test_writer_failure_before_tap_installation_leaves_no_tap_or_backlog(
    daemon, fake, tmp_path, monkeypatch
):
    recorder = daemon.recorder
    write_meta, on_frame = recorder._write_meta, recorder._on_frame

    def read_only_after_meta():
        write_meta()
        recorder.dir.chmod(0o500)

    def first_frame_after_writer_dies(*args):
        recorder._thread.join(timeout=2)
        assert not recorder._thread.is_alive() and recorder._failed
        on_frame(*args)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(recorder, "_write_meta", read_only_after_meta)
            patch.setattr(recorder, "_on_frame", first_frame_after_writer_dies)
            status = await recorder.start(str(tmp_path))
        assert not status["recording"] and "PermissionError" in status["error"]
        assert fake._frame_tap is None and recorder._frames.empty()
        fake.burst(5)
        assert recorder._frames.empty()
    finally:
        if recorder.dir is not None:
            recorder.dir.chmod(0o700)


async def test_cancelled_stop_still_finalizes_once_without_another_request(
    client, daemon, tmp_path, monkeypatch
):
    recorder = daemon.recorder
    started = await client.record("start", directory=str(tmp_path / "cancelled"))
    thread = recorder._thread
    join = thread.join
    entered, release = threading.Event(), threading.Event()
    write_meta = Mock(wraps=recorder._write_meta)
    monkeypatch.setattr(recorder, "_write_meta", write_meta)

    def blocked_join(timeout):
        entered.set()
        assert release.wait(5)
        join(timeout)

    monkeypatch.setattr(thread, "join", blocked_join)
    stopping = asyncio.create_task(recorder.stop())
    try:
        await until(entered.is_set)
        stopping.cancel()
        with pytest.raises(asyncio.CancelledError):
            await stopping
        assert recorder._thread is thread
    finally:
        release.set()
    await until(lambda: recorder._thread is None)
    assert not recorder.active and not thread.is_alive()
    write_meta.assert_called_once_with()
    meta = json.loads((Path(started["dir"]) / "meta.json").read_text())
    assert meta["frames"] == recorder.frames and not meta["error"]
    await recorder.start(str(tmp_path / "next"))
    await recorder.stop()
    assert write_meta.call_count == 3 and not recorder.active


@pytest.mark.parametrize("config_dir", ["relative-config", "~/tilde-config"])
async def test_default_recording_directory_resolves_relative_and_tilde_config(
    config_dir, daemon, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    if config_dir.startswith("~/"):
        relative = await asyncio.to_thread(os.path.relpath, tmp_path, Path.home())
        config_dir = f"~/{relative}/tilde-config"
    expected = await asyncio.to_thread(lambda: Path(config_dir).expanduser().resolve() / "recordings")
    monkeypatch.setattr(daemon, "cfg", replace(daemon.cfg, config_dir=Path(config_dir)))
    started = await daemon.recorder.start()
    folder = Path(started["dir"])
    assert folder.is_absolute()
    assert folder.parent == expected
    await daemon.recorder.stop()


async def test_latency_drops_the_state_held_by_the_agent_loop(daemon, fake, monkeypatch):
    await daemon.agent_pad.set(PadState(frozenset({Button.CROSS})), ttl_ms=1000)
    # Expiry must not hide a missing release while latency waits for its sample.
    monkeypatch.setattr(daemon.agent_pad, "_deadline", float("inf"))
    assert daemon.agent_pad.active and fake.pressed == {Button.CROSS}
    await daemon.latency(samples=1)
    assert not daemon.agent_pad.active and fake.idle
