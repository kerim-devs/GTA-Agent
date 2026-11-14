import cv2
import numpy as np
import pytest

from pilot import chooser, simple, skills
from pilot.chooser import Selection
from pilot.head import HeadRequest, parse_response


def request(tmp_path, *, seat="foot", route="none", last=None):
    image = tmp_path / "frame.jpg"
    cv2.imwrite(str(image), np.zeros((60, 100, 3), dtype=np.uint8))
    return HeadRequest(
        events=[],
        help="",
        objective="",
        subtitle="",
        banner="",
        minimap={"minimap": "tilted" if seat == "vehicle" else "flat", "route": route, "blips": []},
        last_skill=last,
        notebook="",
        jpeg_path=str(image),
        hud={"wanted": 0, "health": 1},
        judgment={"mode": seat},
    )


@pytest.fixture
def model(monkeypatch):
    """The model's answers by question, and what it was asked."""
    asked, answers = [], {}

    def choose(question, options, image, *, timeout, prior=None):
        asked.append((question, dict(options), prior))
        name = answers.get(question)
        return None if name is None else Selection(name, {name: 0.9}, 0.2)

    monkeypatch.setattr(simple.chooser, "choose", choose)
    monkeypatch.setattr(simple.chooser, "probabilities", lambda: {})
    return asked, answers


def names(response):
    return [call.name for call in response.plan]


def test_the_step_the_model_chooses_is_the_step_taken_even_against_the_plain_order(tmp_path, model):
    asked, answers = model
    answers["What should the player do next?"] = "mark"
    answers["What would be fun for the player to do next?"] = "Autowaschanlage"
    response = simple.SimpleHead().decide(request(tmp_path, seat="foot"))
    assert names(response) == ["set_waypoint"]
    assert response.plan[0].args["place"] == "Autowaschanlage"
    assert "model chose mark" in response.reason
    assert "on foot" in asked[0][2]["state"]


def test_a_model_that_does_not_answer_leaves_the_plain_order(tmp_path, model):
    head = simple.SimpleHead()
    assert names(head.decide(request(tmp_path, seat="foot"))) == ["enter_vehicle"]
    marked = head.decide(request(tmp_path, seat="vehicle"))
    assert names(marked) == ["set_waypoint"]
    assert marked.plan[0].args["place"] in simple.PLACES
    assert names(head.decide(request(tmp_path, seat="vehicle", route="purple"))) == ["drive_route"]
    assert "plain order" in marked.reason


def test_a_step_that_runs_is_not_begun_again(tmp_path, model):
    asked, _ = model
    running = {"name": "drive_route", "status": "running", "reason": None}
    response = simple.SimpleHead().decide(request(tmp_path, seat="vehicle", route="purple", last=running))
    assert response.action == "go_on"
    assert not response.plan
    assert not asked


def test_a_step_that_has_just_succeeded_is_not_offered_again(tmp_path, model):
    asked, _ = model
    arrived = {"name": "drive_route", "status": "done", "reason": "arrived"}
    response = simple.SimpleHead().decide(request(tmp_path, seat="vehicle", last=arrived))
    assert set(asked[0][1]) == {"car", "mark"}
    assert names(response) == ["set_waypoint"]


def test_a_place_the_map_did_not_have_is_left_out_of_the_next_choice(tmp_path, model):
    asked, answers = model
    answers["What should the player do next?"] = "mark"
    answers["What would be fun for the player to do next?"] = "Kino"
    head = simple.SimpleHead()
    head.decide(request(tmp_path, seat="vehicle"))
    answers["What would be fun for the player to do next?"] = None
    failed = {"name": "set_waypoint", "status": "failed", "reason": "place-not-in-legend: Kino; places: Golf"}
    again = head.decide(request(tmp_path, seat="vehicle", last=failed))
    assert "Kino" not in asked[-1][1]
    assert again.plan[0].args["place"] != "Kino"


def test_no_car_in_reach_turns_the_camera_and_then_goes_to_the_road(tmp_path, model):
    head = simple.SimpleHead()
    missed = {"name": "enter_vehicle", "status": "failed", "reason": "no car in reach"}
    plans = [names(head.decide(request(tmp_path, last=missed))) for _ in range(simple.LOOKS + 1)]
    assert plans[0] == ["look", "enter_vehicle"]
    assert plans[-1] == ["walk_road", "enter_vehicle"]


def test_with_the_registry_cut_down_no_other_skill_can_be_planned(monkeypatch):
    monkeypatch.setattr(skills, "REGISTRY", dict(skills.REGISTRY))
    monkeypatch.setattr("pilot.head.REGISTRY", skills.REGISTRY, raising=False)
    simple.only()
    assert set(skills.REGISTRY) == set(simple.SKILLS)
    with pytest.raises((ValueError, KeyError)):
        parse_response({"plan": [{"name": "punch", "args": {}}], "sentence": "Schlag."})
    parse_response({"plan": [{"name": "drive_route", "args": {"duration": 60}}], "sentence": "Fahrt."})


def test_the_state_is_part_of_the_question_put_to_the_model():
    text = chooser._prompt(
        "What should the player do next?", {"car": "Get into a car"}, {"state": "On foot."}
    )
    lines = text.splitlines()
    assert lines[1] == "Known: On foot."
    assert lines.index("A: Get into a car") > 1


def test_a_destination_is_kept_until_it_is_reached_and_another_is_chosen_then(tmp_path, model):
    asked, answers = model
    answers["What should the player do next?"] = "mark"
    answers["What would be fun for the player to do next?"] = "Kino"
    head = simple.SimpleHead()
    head.decide(request(tmp_path, seat="vehicle"))
    answers["What would be fun for the player to do next?"] = "Golf"
    late = {"name": "set_waypoint", "status": "failed", "reason": "timeout"}
    again = head.decide(request(tmp_path, seat="vehicle", last=late))
    assert again.plan[0].args["place"] == "Kino"
    answers["What would be fun for the player to do next?"] = None
    arrived = {"name": "drive_route", "status": "done", "reason": "arrived"}
    head.decide(request(tmp_path, seat="vehicle", last=arrived))
    assert "Kino" not in asked[-1][1]


def test_a_route_lost_far_from_its_end_is_driven_on_for_and_the_map_stays_shut(tmp_path, model):
    asked, _ = model
    head = simple.SimpleHead()
    lost = {"name": "drive_route", "status": "failed", "reason": "route-lost-far"}
    for _ in range(simple.HIDDEN):
        response = head.decide(request(tmp_path, seat="vehicle", last=lost))
        assert names(response) == ["drive_on", "drive_route"]
        assert "mark" not in asked[-1][1]
        assert "tunnel" in asked[-1][2]["state"]
    # A route that stays away that long has gone: the map is asked.
    assert names(head.decide(request(tmp_path, seat="vehicle", last=lost))) == ["set_waypoint"]
    # And one that came back in between counts from the start again.
    head.decide(request(tmp_path, seat="vehicle", route="purple"))
    assert names(head.decide(request(tmp_path, seat="vehicle", last=lost))) == ["drive_on", "drive_route"]


def test_a_drive_that_ran_out_of_its_time_is_driven_on_with(tmp_path, model):
    asked, _ = model
    late = {"name": "drive_route", "status": "done", "reason": "time-limit"}
    response = simple.SimpleHead().decide(request(tmp_path, seat="vehicle", route="purple", last=late))
    assert "drive" in asked[0][1]
    assert names(response) == ["drive_route"]


def test_without_a_game_picture_nothing_is_chosen(tmp_path, model):
    asked, _ = model
    scene = request(tmp_path, seat="foot")
    scene.minimap["minimap"] = "none"
    assert names(simple.SimpleHead().decide(scene)) == ["wait"]
    menu = request(tmp_path, seat="vehicle")
    menu.hud["screen"] = "cutscene"
    assert names(simple.SimpleHead().decide(menu)) == ["wait"]
    assert not asked


def test_a_walk_to_the_road_that_fails_is_not_begun_again_at_once(tmp_path, model):
    head = simple.SimpleHead()
    missed = {"name": "enter_vehicle", "status": "failed", "reason": "no car in reach"}
    for _ in range(simple.LOOKS + 1):
        plan = names(head.decide(request(tmp_path, last=missed)))
    assert plan[0] == "walk_road"
    failed = {"name": "walk_road", "status": "failed", "reason": "map-unreadable"}
    assert names(head.decide(request(tmp_path, last=failed))) == ["look", "enter_vehicle"]


@pytest.mark.usefixtures("model")
def test_a_single_named_place_is_marked_without_asking_and_again_after_it_is_reached(tmp_path):
    head = simple.SimpleHead(places={"Ammu-Nation": "Drive to the marked place"})
    first = head.decide(request(tmp_path, seat="vehicle"))
    assert first.plan[0].args["place"] == "Ammu-Nation"
    arrived = {"name": "drive_route", "status": "done", "reason": "arrived"}
    again = head.decide(request(tmp_path, seat="vehicle", last=arrived))
    assert again.plan[0].args["place"] == "Ammu-Nation"
