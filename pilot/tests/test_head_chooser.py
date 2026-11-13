"""The local model behind the rules: it picks an errand among those offered, and may say nothing."""

import time

from pilot import chooser
from pilot.head import HeadRequest
from pilot.localhead import ErrandChooser
from pilot.mission import MissionHead


def request(t=0.0):
    return HeadRequest(
        events=[],
        help="",
        objective="",
        subtitle="",
        banner="",
        minimap={"minimap": "flat", "route": "none", "blips": []},
        last_skill=None,
        notebook="",
        jpeg_path="unused.jpg",
        time=t,
        hud={"screen": "game", "health": 1, "wanted": 0},
        judgment={"mode": "foot"},
        objects=[{"kind": "car"}, {"kind": "person"}],
    )


class Picks:
    """A chooser as the rules see one: offers in, one of them or nothing out."""

    def __init__(self, name):
        self.name, self.seen, self.offers, self.recorded = name, [], [], []

    def observe(self, request):
        self.seen.append(request)

    def record(self, candidate):
        self.recorded.append(candidate["name"])

    def __call__(self, offers):
        self.offers.append([offer["name"] for offer in offers])
        return next((offer for offer in offers if offer["name"] == self.name), None)


def test_the_errand_the_chooser_picks_is_the_one_begun():
    for name in ("cruise", "mayhem", "shop"):
        picks = Picks(name)
        head = MissionHead(goal_seed=1, chooser=picks)
        head.decide(request())
        assert head.goals.active.name == name
        assert picks.seen and name in picks.offers[0]
        assert picks.recorded == []  # the chooser keeps its own choices itself


def test_a_chooser_that_says_nothing_leaves_the_seeded_draw_and_is_told_what_it_drew():
    picks = Picks(None)
    head = MissionHead(goal_seed=1, chooser=picks)
    head.decide(request())
    plain = MissionHead(goal_seed=1)
    plain.decide(request())
    assert head.goals.active.name == plain.goals.active.name
    assert picks.recorded == [plain.goals.active.name]


def test_a_name_that_was_not_offered_is_not_begun():
    class Wrong(Picks):
        def __call__(self, offers):
            return {"name": "buy_a_house"}

    head = MissionHead(goal_seed=1, chooser=Wrong(None))
    head.decide(request())
    assert head.goals.active.name in {"story", "shop", "mayhem", "cruise", "home"}


def test_the_errand_chooser_of_the_local_model_fits_the_rules(monkeypatch):
    asked = []

    def choose(question, options, image, *, timeout, prior=None):
        asked.append(tuple(options))
        return chooser.Selection("cruise", {"cruise": 0.9}, 0.1)

    monkeypatch.setattr(chooser, "choose", choose)
    head = MissionHead(goal_seed=1, chooser=ErrandChooser())
    head.decide(request())
    assert asked and head.goals.active.name == "cruise"


def test_a_server_that_is_silent_twice_is_left_alone_for_a_minute(monkeypatch):
    calls = []

    def post(url, model, encoded, text, tokens, *, timeout):
        calls.append(timeout)
        raise OSError("no route to host")

    monkeypatch.setattr(chooser.judge, "post", post)
    one = chooser.Chooser(["http://127.0.0.1:9=model"])
    image = __import__("numpy").zeros((60, 100, 3), dtype="uint8")
    options = {"road": "Walk along the road", "look": "Look around"}
    question = "What should the player do next?"
    for _ in range(2):
        assert one.choose(question, options, image, timeout=0.5) is None
    assert len(calls) == 2
    started = time.monotonic()
    for _ in range(5):
        assert one.choose(question, options, image, timeout=0.5) is None
    assert len(calls) == 2  # nothing was sent, and nothing was waited for
    assert time.monotonic() - started < 0.1
    one._skip_until = 0.0
    one.choose(question, options, image, timeout=0.5)
    assert len(calls) == 3


def test_the_command_line_builds_the_local_head_on_the_rules(monkeypatch):
    from pilot import cli
    from pilot.localhead import LocalHead

    class Bridge:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    calls, servers = [], []
    monkeypatch.setattr(cli, "Bridge", Bridge)
    monkeypatch.setattr(cli, "Pipeline", lambda **kwargs: None)
    monkeypatch.setattr(cli, "ObjectReader", lambda: "detector")
    monkeypatch.setattr(cli, "run_play", lambda *args, **kwargs: calls.append(kwargs))
    monkeypatch.setattr(cli.chooser, "use", servers.append)
    cli.main(["play", "--no-record", "--no-ocr", "--head", "local"])
    head = calls[0]["head"]
    assert isinstance(head, MissionHead) and isinstance(head.fallback, LocalHead)
    assert isinstance(head.chooser, ErrandChooser)
    assert servers == [[]]  # no --judge given: the rules play alone
