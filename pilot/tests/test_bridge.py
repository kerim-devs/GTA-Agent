import json

import httpx
import numpy as np
import pytest

from pilot.bridge import Bridge
from pilot.contract import HUD_RECT, Command


def test_raw_frame_crop_timing_and_no_new_frame():
    pixels = np.arange(18, dtype=np.uint8).reshape(2, 3, 3)
    calls = []

    def respond(request):
        calls.append(request)
        if len(calls) == 2:
            assert request.url.params["after"] == "42"
            return httpx.Response(204)
        assert dict(request.url.params) == {"x": "30", "y": "530", "w": "260", "h": "170", "wait_ms": "100"}
        return httpx.Response(
            200,
            content=pixels.tobytes(),
            headers={"X-Frame-Id": "42", "X-Frame-Age-Ms": "12.5", "X-Width": "3", "X-Height": "2"},
        )

    with Bridge(transport=httpx.MockTransport(respond)) as bridge:
        frame = bridge.frame(HUD_RECT)
        np.testing.assert_array_equal(frame.rgb, pixels)
        assert frame.id == 42
        assert frame.age == 0.0125
        assert bridge.frame(HUD_RECT, after=frame.id) is None


def test_pad_neutral_conflict_status_and_recorder_directory(tmp_path):
    calls = []
    destination = tmp_path / "20261110-120000"

    def respond(request):
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        if request.url.path == "/status":
            return httpx.Response(200, json={"session_up": True, "fps": 60})
        if request.url.path == "/pad":
            return httpx.Response(200 if body else 409, json={"ok": bool(body)})
        if body["action"] == "start":
            return httpx.Response(200, json={"dir": str(destination), "recording": True})
        return httpx.Response(200, json={"recording": False})

    with Bridge(transport=httpx.MockTransport(respond)) as bridge:
        assert bridge.status()["fps"] == 60
        assert bridge.pad(Command(-0.5, 0.6, 0.1, "follow")) == 200
        assert calls[-1][2] == {
            "buttons": [],
            "left": [-0.5, 0],
            "right": [0, 0],
            "l2": 0.1,
            "r2": 0.6,
            "ttl_ms": 250,
        }
        assert bridge.pad() == 409
        assert calls[-1][2] == {}
        for shadow in (False, True):
            assert bridge.record_start(tmp_path, shadow=shadow) == destination
            assert calls[-1][2] == {
                "action": "start",
                "dir": str(tmp_path),
                "note": "pilot shadow" if shadow else "pilot drive",
            }
        bridge.record_stop()
        assert calls[-1] == ("POST", "/record", {"action": "stop"})


def test_http_failure_is_not_misreported_as_human_takeover():
    with Bridge(transport=httpx.MockTransport(lambda request: httpx.Response(500))) as bridge:
        with pytest.raises(httpx.HTTPStatusError):
            bridge.pad()


def test_short_timeout_is_set_on_requests():
    def respond(request):
        assert all(0 < value <= 0.5 for value in request.extensions["timeout"].values())
        raise httpx.ReadTimeout("simulated", request=request)

    with Bridge(transport=httpx.MockTransport(respond)) as bridge:
        with pytest.raises(httpx.ReadTimeout):
            bridge.frame(HUD_RECT)


def test_recorder_calls_wait_long_enough_for_the_writer_to_finish(tmp_path):
    def respond(request):
        assert all(value >= 10 for value in request.extensions["timeout"].values())
        return httpx.Response(200, json={"dir": str(tmp_path)})

    with Bridge(transport=httpx.MockTransport(respond)) as bridge:
        bridge.record_start(tmp_path, shadow=True)
        bridge.record_stop()
