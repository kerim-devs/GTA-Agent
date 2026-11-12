"""RemotePlayBackend input paths against a stub of the vendored library's device/session/controller."""

from collections import deque
from types import SimpleNamespace

import pytest

from ps5_remoteplay_mcp.backend import Button, ConsoleError, Side
from ps5_remoteplay_mcp.backend.remoteplay import RemotePlayBackend
from ps5_remoteplay_mcp.config import Config
from ps5_remoteplay_mcp.vendor.pyremoteplay.controller import Controller
from ps5_remoteplay_mcp.vendor.pyremoteplay.stream_packets import FeedbackHeader


class StubController:
    def __init__(self) -> None:
        self.sent: list[tuple] = []
        self.fail = False
        self.stick_state = "sticks"
        self._event_buf: deque[bytes] = deque(maxlen=5)
        self._sequence_event = self._sequence_state = 0

    def button(self, name: str, action: str) -> None:
        if self.fail:
            raise AttributeError("'NoneType' object has no attribute 'append'")
        self.sent.append(("button", name, action))

    def stick(self, side: str, point) -> None:
        self.sent.append(("stick", side, tuple(point)))

    def update_sticks(self) -> None:
        self.sent.append(("update_sticks",))

    def _add_event_buffer(self, event) -> None:
        self._event_buf.appendleft(bytes([event.state]))

    def _send_event(self) -> None:
        self.sent.append(("event",))
        self._sequence_event += 1

    def stop(self) -> None:
        pass


class StubDevice:
    def __init__(self) -> None:
        self.transport = SimpleNamespace(closing=False)
        self.transport.is_closing = lambda: self.transport.closing
        stream = SimpleNamespace(_protocol=SimpleNamespace(transport=self.transport))
        self.session = SimpleNamespace(is_ready=True, is_stopped=False, stream=stream)
        self.controller = StubController()
        self.controller._session = self.session
        stream.send_feedback = lambda kind, sequence, data=b"", state=None: self.controller.sent.append(
            ("resend", kind.name, sequence, data or state)
        )

    def disconnect(self) -> None:
        self.session = None


@pytest.fixture
def backend(tmp_path) -> RemotePlayBackend:
    b = RemotePlayBackend(Config(config_dir=tmp_path))
    b.device = StubDevice()
    return b


async def test_release_all_releases_only_what_was_pressed(backend):
    await backend.set_buttons({Button.CROSS})
    backend.device.controller.sent.clear()
    await backend.release_all()
    buttons = [s for s in backend.device.controller.sent if s[0] == "button"]
    assert buttons == [("button", "CROSS", "release")]
    assert ("update_sticks",) in backend.device.controller.sent  # centering sent now, not by a thread


async def test_failed_send_drops_the_session(backend):
    backend.device.controller.fail = True
    with pytest.raises(ConsoleError, match="session lost"):
        await backend.set_buttons({Button.CROSS})
    assert backend.device.session is None and backend._pressed == set()
    assert not backend._session_up


async def test_closed_stream_counts_as_no_session(backend):
    backend.device.transport.closing = True
    assert not backend._session_up
    with pytest.raises(ConsoleError):
        await backend.set_stick(Side.LEFT, 0.5, 0.0)
    assert backend.device.controller.sent == []


async def test_held_input_is_repeated_and_events_keep_their_sequence_number(backend):
    controller = backend.device.controller
    await backend.set_trigger(Side.RIGHT, 0.6)
    controller.sent.clear()
    await backend.resend_input()
    await backend.resend_input()
    assert controller.sent == [
        ("resend", "STATE", 0, "sticks"),
        ("resend", "EVENT", 0, bytes([153])),  # the number it was first sent with, so it is no new event
        ("resend", "STATE", 1, "sticks"),
        ("resend", "EVENT", 0, bytes([153])),
    ]


async def test_a_release_is_repeated_for_a_moment_and_then_nothing_is(backend):
    controller = backend.device.controller
    await backend.set_buttons({Button.CROSS})
    await backend.set_buttons(set())
    controller.sent.clear()
    await backend.resend_input()
    assert controller.sent  # a lost release would leave the button held on the console
    backend._input_at -= 5
    controller.sent.clear()
    await backend.resend_input()
    assert controller.sent == []


def test_the_feedback_sequence_number_wraps_at_16_bits():
    def packed(sequence: int) -> bytes:
        buf = bytearray(FeedbackHeader.LENGTH)
        FeedbackHeader(FeedbackHeader.Type.STATE, sequence=sequence).pack(buf)
        return bytes(buf)

    # 20 repeats a second reach 65536 within an hour: that must not end the session
    assert packed(65536) == packed(0) and packed(65538) == packed(2) and packed(65535) != packed(0)


async def test_release_all_keeps_all_five_releases_in_the_resend_window(backend):
    device = backend.device
    device.controller = Controller(device.session)
    controller = device.controller
    controller.sent = []
    await backend.set_buttons({Button.CROSS, Button.CIRCLE, Button.SQUARE, Button.TRIANGLE})
    await backend.set_trigger(Side.RIGHT, 1.0)
    controller.sent.clear()

    await backend.release_all()

    events = [s for s in controller.sent if s[:2] == ("resend", "EVENT")]
    assert len(events) == 5
    expected = {bytes([0x80, button_id, 0]) for button_id in (0x87, 0x88, 0x89, 0x8A, 0x8B)}
    assert {bytes(event) for event in controller._event_buf} == expected
    buffered = b"".join(controller._event_buf)
    sequence = controller._sequence_event - 1
    controller.sent.clear()
    await backend.resend_input(force=True)
    assert ("resend", "EVENT", sequence, buffered) in controller.sent


async def test_release_all_does_not_emit_an_unpressed_trigger(backend):
    await backend.set_buttons({Button.CROSS})
    backend.device.controller.sent.clear()
    await backend.release_all()
    assert not [s for s in backend.device.controller.sent if s[0] == "event"]


async def test_force_resends_after_a_long_quiet_period(backend):
    controller = backend.device.controller
    await backend.set_trigger(Side.RIGHT, 1.0)
    await backend.release_all()
    backend._input_at -= 5
    controller.sent.clear()
    await backend.resend_input()
    assert controller.sent == []
    await backend.resend_input(force=True)
    assert [s[1] for s in controller.sent] == ["STATE", "EVENT"]


def test_frame_timestamp_is_absent_without_a_decoded_frame(backend):
    assert backend.frame_ts() is None
    backend.receiver = SimpleNamespace(frame_id=0, frame_ts=0.0)
    assert backend.frame_ts() is None
    backend.receiver.frame_id = 1
    backend.receiver.frame_ts = 42.5
    assert backend.frame_ts() == 42.5
