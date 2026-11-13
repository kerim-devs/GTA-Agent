from dataclasses import replace

import numpy as np

from pilot.ahead import View
from pilot.contract import Hud, Observation, Reading
from pilot.where import Sense

FRAME = np.zeros((720, 1280, 3), dtype=np.uint8)
READING = Reading("flat", "none", None, None, 0.0, False, 1.0)


def observation(t, *, mode="foot", screen="game", frame=FRAME, corrupt=False, minimap="flat"):
    return Observation(
        replace(READING, corrupt=corrupt, minimap=minimap),
        True,
        t,
        frame=frame,
        hud=Hud(screen=screen),
        mode=mode,
    )


class Asked:
    def __init__(self):
        self.calls = []
        self.reply = None

    def ask(self, frame, capture, **kwargs):
        assert frame is FRAME
        assert kwargs == {"where": True}
        self.calls.append(capture)
        return True

    def answer(self, since):
        return None if self.reply is None or self.reply[0] < since else self.reply[1]

    def say(self, capture, shares=(0.9, 0.05, 0.05), *, error=None):
        self.reply = (capture, View(where=shares, error=error))


def confirmed():
    asker = Asked()
    sense = Sense(asker)
    sense.step(observation(0))
    asker.say(0)
    sense.step(observation(0.1))
    assert sense.verdict is None
    sense.step(observation(1))
    asker.say(1)
    sense.step(observation(1.1))
    assert sense.verdict == "room"
    return sense, asker


def test_two_distinct_frames_and_five_second_expiry():
    sense, asker = confirmed()
    assert asker.calls == [0, 1]
    assert sense.confirmed_at == 1.1
    sense.step(observation(1.2))
    assert sense.confirmed_at == 1.1
    sense.step(observation(6.1, frame=None))
    assert sense.verdict is None
    assert sense.confirmed_at is None


def test_forgets_after_two_seconds_away_in_car_or_menu():
    for kwargs in ({"mode": "vehicle"}, {"screen": "pause"}, {"mode": "none"}):
        sense, _ = confirmed()
        sense.step(observation(2, **kwargs))
        assert sense.verdict == "room"
        sense.step(observation(4, **kwargs))
        assert sense.verdict is None


def test_invalid_answers_break_agreement():
    for shares, error, delay in (
        ((0.59, 0.21, 0.2), None, 0.1),
        ((0.9, 0.05, 0.05), "offline", 0.1),
        ((0.9, 0.05, 0.05), None, 2.01),
        (None, None, 0.1),
    ):
        asker, sense = Asked(), None
        sense = Sense(asker)
        sense.step(observation(0))
        asker.say(0)
        sense.step(observation(0.1))
        sense.step(observation(1))
        asker.say(1, shares, error=error)
        sense.step(observation(1 + delay, frame=None))
        next_time = 2 + delay
        sense.step(observation(next_time))
        asker.say(next_time)
        sense.step(observation(next_time + 0.1))
        assert sense.verdict is None


def test_only_one_frame_at_a_time_and_at_most_once_per_second():
    asker = Asked()
    sense = Sense(asker)
    sense.step(observation(0))
    sense.step(observation(0.5))
    sense.step(observation(1))
    assert asker.calls == [0]
    asker.say(0)
    sense.step(observation(1.5))
    assert asker.calls == [0, 1.5]
    asker.say(1.5)
    sense.step(observation(1.6))
    sense.step(observation(2.4))
    assert asker.calls == [0, 1.5]


def test_asks_only_for_valid_foot_game_frames():
    for kwargs in (
        {"mode": "vehicle"},
        {"mode": "none"},
        {"screen": "pause"},
        {"frame": None},
        {"frame": np.zeros((2, 2, 3))},
        {"corrupt": True, "mode": None},
        {"frame": np.zeros((720, 1280, 3), dtype=np.float32)},
        # No radar is no game screen: the pause map of an apartment was called the street.
        {"minimap": "none"},
    ):
        asker = Asked()
        Sense(asker).step(observation(0, **kwargs))
        assert asker.calls == []
    asker = Asked()
    Sense(asker).step(replace(observation(0), hud=None))
    assert asker.calls == [0]
    # A map misread as damaged or tilted says nothing once the judge has seen the figure on foot.
    for kwargs in ({"corrupt": True}, {"minimap": "tilted"}):
        asker = Asked()
        Sense(asker).step(observation(0, **kwargs))
        assert asker.calls == [0]


def test_configured_state_and_label_change_need_two_answers():
    assert Sense(None).place is None
    assert Sense(Asked()).place == "unknown"
    sense, asker = confirmed()
    assert sense.place == "room"
    for capture in (2, 3):
        sense.step(observation(capture))
        asker.say(capture, (0.1, 0.8, 0.1))
        sense.step(observation(capture + 0.1))
        assert sense.verdict == ("room" if capture == 2 else "landing")


def test_conductor_steps_sense_and_request_carries_all_three_states(tmp_path, monkeypatch):
    import json
    from concurrent.futures import Future

    from pilot import ahead
    from pilot.conductor import Conductor

    pending = []

    def submit(function, *args):
        pending.append(args[0])
        return Future()

    monkeypatch.setattr(ahead, "where", lambda: None)
    with_model = Asked()
    for configured in (None, with_model):
        monkeypatch.setattr(ahead, "where", lambda configured=configured: configured)
        directory = tmp_path / ("none" if configured is None else "model")
        directory.mkdir()
        conductor = Conductor(directory, submit=submit)
        try:
            conductor.tick(observation(0), FRAME)
            conductor._request(observation(0), FRAME)
            assert pending[-1].place == (None if configured is None else "unknown")
            if configured is not None:
                configured.say(0)
                conductor.tick(observation(0.1), FRAME)
                conductor.tick(observation(1), FRAME)
                configured.say(1)
                conductor.tick(observation(1.1), FRAME)
                conductor._request(observation(1.1), FRAME)
                assert pending[-1].place == "room"
        finally:
            conductor.close()
        rows = [json.loads(line) for line in (directory / "head.jsonl").read_text().splitlines()]
        requests = [row["request"] for row in rows if row["type"] == "request"]
        assert requests[-1]["place"] == (None if configured is None else "room")


def test_prompt_names_only_known_place():
    from pilot.head import HeadRequest, build_prompt

    request = HeadRequest([], "", "", "", "", {}, None, "", "unused.jpg")
    for place in (None, "unknown", "room", "landing", "street"):
        prompt = build_prompt(replace(request, place=place))
        assert (f"\n\nPlace: {place}" in prompt) == (place in {"room", "landing", "street"})


def test_tick_log_contains_place_with_and_without_model(tmp_path, monkeypatch):
    import json

    from test_conductor import Clock, FakeBridge, FakePipeline, configured_conductor

    from pilot import ahead
    from pilot.conductor import run_play

    for configured in (None, Asked()):
        monkeypatch.setattr(ahead, "where", lambda configured=configured: configured)
        directory = tmp_path / ("none" if configured is None else "model")
        directory.mkdir()
        clock = Clock()
        bridge = FakeBridge(directory, clock)
        run_play(
            bridge,
            seconds=0.11,
            pipeline=FakePipeline(),
            ocr=False,
            clock=clock,
            sleep=clock.sleep,
            conductor_factory=configured_conductor,
        )
        rows = [json.loads(line) for line in (directory / "play.jsonl").read_text().splitlines()]
        ticks = [row for row in rows if "fresh" in row]
        assert ticks
        assert all(row["place"] == (None if configured is None else "unknown") for row in ticks)


def test_a_figure_that_stands_has_not_changed_its_place():
    # 13 November, 16:08: on the landing the camera turned, looked back through the open door, and
    # the picture of the room was taken for the figure's place.
    sense, asker = confirmed()
    for capture in (2, 3):
        sense.step(observation(capture), walked=False)
        asker.say(capture, (0.02, 0.96, 0.02))
        sense.step(observation(capture + 0.1), walked=False)
    assert sense.verdict == "room"
    for capture in (4, 5):
        sense.step(observation(capture), walked=True)
        asker.say(capture, (0.02, 0.96, 0.02))
        sense.step(observation(capture + 0.1), walked=True)
    assert sense.verdict == "landing"
