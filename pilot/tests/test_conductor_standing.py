"""The conductor tells the head when the figure stands, and puts the plan down while the pad is refused."""

from concurrent.futures import Future
from dataclasses import replace

import numpy as np

from pilot.conductor import Conductor
from pilot.contract import NEUTRAL_PAD, Hud, Reading
from pilot.head import parse_response
from pilot.scene import SceneText
from pilot.skills import Observation

RGB = np.zeros((720, 1280, 3), dtype=np.uint8)
FLAT = Reading("flat", "none", None, None, 0.0, False, 1.0)
TICK = 1 / 30


class NoEvents:
    def update(self, *args, **kwargs):
        return ()


class Answers:
    """A head that answers every request at once with the same plan, and keeps what it was asked."""

    def __init__(self, *calls):
        self.calls = calls or (("wait", {"duration": 60}),)
        self.requests = []

    def __call__(self, function, *args):
        future = Future()
        self.requests.append(args[0])
        plan = [{"name": name, "args": args} for name, args in self.calls]
        future.set_result(parse_response({"plan": plan, "sentence": "Weiter."}))
        return future

    def events(self):
        return [event for request in self.requests for event in request.events]


def see(t, *, moving=False, reading=FLAT, screen="game", mode=None):
    return Observation(reading, moving, t, hud=Hud(wanted=0, health=1.0, screen=screen), mode=mode)


def run(conductor, t, seconds, **picture):
    results = []
    for _ in range(round(seconds / TICK)):
        results.append(conductor.tick(see(t, **picture), RGB))
        t += TICK
    return t, results


def standing(head):
    return [event for event in head.events() if event["kind"] == "standing"]


def make(tmp_path, *calls, **options):
    head = Answers(*calls)
    conductor = Conductor(
        tmp_path, submit=head, detector=NoEvents(), quiet_seconds=10_000, standing=12.0, **options
    )
    return conductor, head


def test_twelve_still_seconds_tell_the_head_and_the_next_twelve_count_two(tmp_path):
    conductor, head = make(tmp_path)
    try:
        t, _ = run(conductor, 0.0, 11.5)
        assert not standing(head)
        t, _ = run(conductor, t, 1.0)
        assert [event["count"] for event in standing(head)] == [1]
        assert standing(head)[0]["seconds"] >= 12.0
        t, _ = run(conductor, t, 12.5)
        assert [event["count"] for event in standing(head)] == [1, 2]
    finally:
        conductor.close()


def test_without_the_switch_nothing_is_told(tmp_path):
    head = Answers()
    conductor = Conductor(tmp_path, submit=head, detector=NoEvents(), quiet_seconds=10_000)
    try:
        run(conductor, 0.0, 30.0)
        assert not standing(head)
    finally:
        conductor.close()


def test_a_touch_of_the_camera_does_not_start_the_count_again_and_real_movement_does(tmp_path):
    conductor, head = make(tmp_path)
    try:
        t, _ = run(conductor, 0.0, 8.0)
        t, _ = run(conductor, t, 0.3, moving=True)  # the nudge that keeps the game's own view
        t, _ = run(conductor, t, 4.5)
        assert len(standing(head)) == 1
        # Three seconds under way: what stands after that is counted as the first again.
        t, _ = run(conductor, t, 3.5, moving=True)
        t, _ = run(conductor, t, 12.5)
        assert [event["count"] for event in standing(head)] == [1, 1]
    finally:
        conductor.close()


def test_a_scene_a_screen_a_damaged_picture_and_an_order_to_wait_are_not_standing(tmp_path):
    for number, picture in enumerate(
        (
            {"reading": replace(FLAT, minimap="none")},
            {"reading": replace(FLAT, corrupt=True)},
            {"screen": "pause"},
            {"mode": "none"},
            {"moving": None},
        )
    ):
        conductor, head = make(tmp_path / str(number))
        try:
            run(conductor, 0.0, 30.0, **picture)
            assert not standing(head), picture
        finally:
            conductor.close()
    conductor, head = make(tmp_path / "wait")
    try:
        conductor.text = SceneText(objective="Warte auf Lamar.")
        run(conductor, 0.0, 30.0)
        assert not standing(head)
    finally:
        conductor.close()


def test_a_fight_from_one_spot_is_not_standing(tmp_path):
    shots = ("shoot", {"duration": 1, "count": 5})
    conductor, head = make(tmp_path, shots, shots, shots, shots, shots)
    try:
        run(conductor, 0.0, 30.0)
        assert not standing(head)
    finally:
        conductor.close()


def test_a_refused_pad_puts_the_plan_down_and_its_return_asks_the_head_afresh(tmp_path):
    conductor, head = make(tmp_path, ("walk", {"duration": 10, "y": -1}))
    try:
        t, results = run(conductor, 0.0, 0.5, moving=True)
        assert results[-1].pad.left[1] < 0
        asked = len(head.requests)

        conductor.refuse(t, True)
        assert conductor.runner.last["reason"] == "pad_refused" and not conductor.runner.has_plan
        t, results = run(conductor, t, 20.0)
        assert all(result.pad == NEUTRAL_PAD and result.reason == "pad-refused" for result in results)
        assert len(head.requests) == asked  # nobody is asked while a hand is on the controller
        assert not standing(head)

        conductor.refuse(t, False)
        t, results = run(conductor, t, 0.5, moving=True)
        assert len(head.requests) == asked + 1
        assert head.requests[-1].events[0]["kind"] == "pad_returned"
        assert head.requests[-1].events[0]["seconds"] >= 19.9
        assert results[-1].pad.left[1] < 0  # and the plan it answers with runs
    finally:
        conductor.close()
