"""Safe fallback, grounded menus and the future P70 errand seam."""

import time
from dataclasses import replace

import cv2
import numpy as np
import pytest
from test_chooser import answer

from pilot import chooser
from pilot.head import HeadRequest, parse_response
from pilot.localhead import ErrandChooser, LocalHead


@pytest.fixture
def request_frame(tmp_path):
    image = tmp_path / "frame.jpg"
    cv2.imwrite(str(image), np.zeros((60, 100, 3), dtype=np.uint8))
    return HeadRequest(
        events=[],
        help="",
        objective="",
        subtitle="",
        banner="",
        minimap={"minimap": "flat", "route": "none", "blips": []},
        last_skill=None,
        notebook="",
        jpeg_path=str(image),
        hud={"wanted": 0, "health": 1},
    )


@pytest.fixture(autouse=True)
def reset_chooser():
    chooser.use([])
    yield
    chooser.use([])


def test_selected_model_action_is_used_and_explained(request_frame, monkeypatch):
    chooser.use(["http://127.0.0.1:1=fake"])
    monkeypatch.setattr(chooser.judge, "post", lambda *a, **kw: (answer(), 0.001))
    response = LocalHead().decide(request_frame)
    assert [call.name for call in response.plan] == ["look", "walk"]
    assert "model chose look" in response.reason
    assert '"look": 0.9' in response.reason
    assert response.goal is None


@pytest.mark.parametrize("mode", ["absent", "refused", "timeout", "nonsense", "low", "no_probability"])
def test_all_abstentions_take_first_safe_choice(request_frame, monkeypatch, mode):
    def post(*args, **kwargs):
        if mode == "refused":
            raise ConnectionRefusedError()
        if mode == "timeout":
            time.sleep(0.15)
            raise TimeoutError()
        if mode == "nonsense":
            return answer("Not a letter"), 0
        if mode == "no_probability":
            return {"message": {"content": "B"}}, 0
        return answer("B", {"A": 0.8, "B": 0.2}), 0

    if mode != "absent":
        chooser.use(["http://127.0.0.1:1=fake"])
    monkeypatch.setattr(chooser.judge, "post", post)
    head = LocalHead(timeout=0.03)
    first = head.candidates(request_frame)[0]
    started = time.monotonic()
    response = head.decide(request_frame)
    assert time.monotonic() - started < 0.13
    assert response.plan == first.response.plan
    assert "fallback" in response.reason
    assert ('"look": 0.2' if mode == "low" else "probabilities=unavailable") in response.reason


@pytest.mark.parametrize("event", [False, True])
def test_no_repeat_after_actual_skill_failure(request_frame, event):
    head = LocalHead()
    first = head.decide(request_frame)
    failed = {"name": first.plan[0].name, "args": first.plan[0].args, "status": "failed"}
    request = replace(
        request_frame,
        events=[{"kind": "skill_failed", "skill": failed}] if event else [],
        last_skill=None if event else failed,
    )
    next_response = head.decide(request)
    assert next_response.plan != first.plan
    assert all(call.name != failed["name"] for call in next_response.plan)
    # A past failure is not a permanent global ban after new observations.
    assert head.decide(request_frame).plan == first.plan


@pytest.mark.parametrize("wanted", [1, 2, 5, None])
def test_wanted_never_offers_waypoint(request_frame, wanted):
    request = replace(request_frame, judgment={"mode": "vehicle"}, hud={"wanted": wanted})
    assert all(
        call.name != "set_waypoint"
        for candidate in LocalHead().candidates(request)
        for call in candidate.response.plan
    )


@pytest.mark.parametrize("situation", ["foot", "objective", "vehicle", "stuck"])
def test_all_candidates_are_registry_valid(request_frame, situation):
    changes = {
        "foot": {
            "help": "Press X",
            "objects": [{"kind": "truck"}],
            "minimap": {"minimap": "flat", "blips": [{"color": "blue", "border": False}]},
        },
        "objective": {
            "objective": "Take out the enemies",
            "help": "Press square",
            "objects": [{"kind": "car"}],
            "minimap": {"minimap": "flat", "blips": [{"color": "red"}, {"color": "yellow"}]},
        },
        "vehicle": {"judgment": {"mode": "vehicle"}, "minimap": {"route": "purple"}},
        "stuck": {
            "events": [{"kind": "stuck", "screen": "map", "seconds": 10}],
            "help": "X Kreis dpad_down L3 touchpad",
        },
    }[situation]
    choices = LocalHead().candidates(replace(request_frame, **changes))
    assert 1 <= len(choices) <= 6
    for candidate in choices:
        response = candidate.response
        parsed = parse_response(
            {"plan": [{"name": c.name, "args": c.args} for c in response.plan], "sentence": response.sentence}
        )
        assert parsed.plan == response.plan
    if situation == "stuck":
        assert choices[0].response.plan[0].args["button"] == "circle"
        assert all(c.response.plan[0].args["count"] == 1 for c in choices)


def test_grounded_order_no_route_and_arrival(request_frame):
    foot = replace(
        request_frame,
        help="Press X",
        objects=[{"kind": "car"}],
        minimap={"minimap": "flat", "blips": [{"color": "blue", "border": False}]},
    )
    assert [c.name for c in LocalHead().candidates(foot)] == ["road", "target", "vehicle", "prompt", "look"]
    mission = replace(foot, objective="Go to the marker")
    assert [c.name for c in LocalHead().candidates(mission)] == ["target", "prompt", "vehicle"]
    border = replace(
        request_frame, minimap={"minimap": "flat", "blips": [{"color": "yellow", "border": True}]}
    )
    assert "target" not in [c.name for c in LocalHead().candidates(border)]
    vehicle = replace(request_frame, judgment={"mode": "vehicle"})
    assert "route" not in [c.name for c in LocalHead().candidates(vehicle)]
    arrival = replace(vehicle, last_skill={"name": "drive_route", "status": "done", "reason": "arrived"})
    assert LocalHead().candidates(arrival)[0].name == "exit"


def test_scene_wait_and_health_drop(request_frame):
    scene = replace(request_frame, hud={"screen": "cutscene"})
    assert LocalHead().candidates(scene)[0].response.plan[0].args == {"duration": 3}
    request = replace(request_frame, minimap={"minimap": "flat", "blips": [{"color": "red"}]})
    head = LocalHead()
    head.decide(request)
    assert "fight" not in [c.name for c in head.candidates(request)]
    hurt = replace(request, hud={"wanted": 0, "health": 0.8})
    head.decide(hurt)
    assert "fight" in [c.name for c in head.candidates(hurt)]


def test_errand_threshold_and_two_of_three_filter(request_frame, monkeypatch):
    errands = [
        {"name": name, "description": desc, "weight": weight}
        for name, desc, weight in [
            ("road", "Explore a road", 3),
            ("shop", "Visit a shop", 1),
            ("hill", "Visit a hill", 2),
        ]
    ]
    adapter = ErrandChooser()
    adapter.observe(request_frame)
    for entry in [errands[0], errands[1], errands[0]]:
        adapter.record(entry)
    seen = []

    def choose(question, options, image, **kwargs):
        seen.append((question, options))
        assert "road" not in options
        return chooser.Selection("hill", {"shop": 0.2, "hill": 0.8}, 0.01)

    monkeypatch.setattr(chooser, "choose", choose)
    assert adapter(errands) is errands[2]
    assert seen[0][0] == "What would be fun for the player to do next?"
    assert list(adapter.recent) == ["shop", "road", "hill"]
    monkeypatch.setattr(chooser, "choose", lambda *a, **kw: None)
    assert adapter(errands) is None
    assert list(adapter.recent) == ["shop", "road", "hill"]
    assert ErrandChooser()(errands) is None


def test_head_caps_requested_timeout(request_frame, monkeypatch):
    seen = []
    monkeypatch.setattr(chooser, "choose", lambda *a, **kw: seen.append(kw["timeout"]))
    LocalHead(timeout=20).decide(request_frame)
    assert 0 < seen[0] <= 1.5


def test_stuck_footer_uses_observed_subtitle_buttons(request_frame):
    request = replace(
        request_frame,
        events=[{"kind": "stuck", "screen": "map"}],
        subtitle="Cross Select  Circle Back  L1 Zoom",
        help="",
    )
    assert [candidate.name for candidate in LocalHead().candidates(request)] == [
        "press_circle",
        "press_cross",
        "press_l1",
    ]
