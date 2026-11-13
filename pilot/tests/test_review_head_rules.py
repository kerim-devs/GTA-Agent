"""What a review of 13 November broke in the head's rules, each case as it was reproduced, and the
two things the offline run over Kerim's recordings showed: stars the reader misses for a moment, and
a seat the tilted map under stars cannot show."""

from pilot.head import HeadRequest
from pilot.mission import SAME_FAILED, SEAT_HOLD, STARS_HOLD, MissionHead


def request(t=0.0, *, shape="flat", wanted=0, last=None, cars=False, blips=(), judged=None, **kwargs):
    """A request as the conductor builds it with no judge: the map and the HUD are all there is."""
    return HeadRequest(
        kwargs.pop("events", []),
        "",
        kwargs.pop("objective", ""),
        "",
        "",
        {"minimap": shape, "route": kwargs.pop("route", "none"), "blips": list(blips)},
        last,
        "",
        "unused.jpg",
        time=t,
        hud={"screen": "game", "health": 1, "wanted": wanted},
        judgment=None if judged is None else {"mode": judged},
        objects=[{"kind": "car"}] if cars else [],
        **kwargs,
    )


def failed(name, reason):
    return {"name": name, "status": "failed", "reason": reason, "queue": []}


def names(answer):
    return [call.name for call in answer.plan]


def test_place_precedes_roam_and_standing_without_an_errand():
    for place, skill, duration, rule in (
        ("room", "leave_building", 60, "room_leave"),
        ("landing", "descend", 40, "landing_descend"),
    ):
        head = MissionHead()
        answer = head.decide(request(place=place, events=[{"kind": "standing", "count": 3}]))
        assert names(answer) == [skill]
        assert answer.plan[0].args == {"duration": duration}
        assert head.last_rule == rule
        assert head.goals.active is None

        head = MissionHead()
        head.goals.mapless_until = float("inf")
        assert "walk_road" in names(head.decide(request()))
        assert head.goals.active.name == "roam"
        assert names(head.decide(request(1, place=place))) == [skill]


def test_place_leaves_missions_and_urgent_rules_unchanged():
    from dataclasses import replace

    situations = [
        request(objective="Gehe zum gelben Punkt."),
        request(wanted=2, cars=True),
        request(judged="none"),
        replace(request(), hud={"screen": "game", "health": 0.2, "wanted": 0}),
        *[
            replace(request(), hud={"screen": screen, "health": 1, "wanted": 0})
            for screen in ("phone", "pause", "dead", "cutscene")
        ],
    ]
    for situation in situations:
        expected = MissionHead(goal_seed=1).decide(situation)
        for place in ("room", "landing", "unknown"):
            actual = MissionHead(goal_seed=1).decide(replace(situation, place=place))
            assert actual.plan == expected.plan


def test_place_failure_retries_rest_and_return_for_both_rules():
    for place, skill, angle in (("room", "leave_building", 180), ("landing", "descend", 120)):
        head = MissionHead(goal_seed=1)
        assert names(head.decide(request(place=place))) == [skill]
        result = failed(skill, "timeout")
        for time in (1, 2):
            answer = head.decide(
                request(time, place=place, last=result, events=[{"kind": "skill_failed", "skill": result}])
            )
            assert names(answer) == ["look", skill]
            assert answer.plan[0].args["angle"] == angle
        answer = head.decide(
            request(3, place=place, last=result, events=[{"kind": "skill_failed", "skill": result}])
        )
        baseline = MissionHead(goal_seed=1).decide(request(3, last=result))
        assert answer.plan == baseline.plan
        assert head.place_failures == 3
        assert head.place_rest_until == 123
        head.decide(request(122, place=place, last=result))
        assert head.last_rule not in {"room_leave", "landing_descend"}
        assert head.place_failures == 3
        assert names(head.decide(request(123, place=place, last=result))) == [skill]
        assert head.place_failures == 0


def test_repeated_failure_snapshot_is_not_another_failed_call():
    head = MissionHead()
    result = failed("leave_building", "timeout")
    head.decide(request(place="room"))
    head.decide(request(1, place="room", last=result, events=[{"kind": "skill_failed", "skill": result}]))
    head.decide(request(2, place="room", last=result))
    assert head.place_failures == 1
    running = {
        "name": "look",
        "status": "running",
        "args": {"duration": 1, "angle": 180},
        "queue": ["leave_building"],
    }
    answer = head.decide(request(3, place="room", last=running))
    assert answer.action == "go_on"
    assert not answer.plan


def test_place_change_and_done_reset_failures_and_discard_restores_state():
    head = MissionHead()
    result = failed("leave_building", "timeout")
    head.decide(request(place="room"))
    head.decide(request(1, place="room", last=result))
    assert head.place_failures == 1
    head.discard()
    assert head.place_failures == 0
    head.decide(request(2, place="room", last=result))
    head.decide(
        request(3, place="room", last={"name": "leave_building", "status": "done", "reason": "outdoors"})
    )
    assert head.place_failures == 0
    head.decide(request(4, place="room", last=result))
    assert head.place_failures == 1
    assert names(head.decide(request(5, place="landing", last=result))) == ["descend"]
    assert head.place_failures == 0


def test_unknown_place_waits_only_at_session_start():
    head = MissionHead(goal_seed=1)
    for time in (1000, 1005.99):
        answer = head.decide(request(time, place="unknown"))
        assert names(answer) == ["wait"]
        assert answer.plan[0].args == {"duration": 1}
        assert head.last_rule == "place_wait"
    baseline = MissionHead(goal_seed=1).decide(request(1006))
    assert head.decide(request(1006, place="unknown")).plan == baseline.plan


def test_last_place_is_held_for_ten_seconds_without_refreshing_unknown():
    head = MissionHead()
    head.decide(request(0, place="room"))
    for time in (5, 10):
        assert names(head.decide(request(time, place="unknown"))) == ["leave_building"]
    head.decide(request(10.01, place="unknown"))
    assert head.last_rule != "room_leave"
    head.decide(request(11, place="street"))
    assert head._held(request(12, place="unknown")).place == "street"
    assert head._held(request(12, place=None)).place is None


def test_scripted_place_replays_first_forty_seconds():
    from dataclasses import replace

    from pilot.where import Sense

    class ScriptedSense(Sense):
        def step(self, observation):
            self.verdict = "room" if observation.time < 22 or observation.time > 30 else "landing"
            self.confirmed_at = observation.time

    sense = ScriptedSense(object())
    head = MissionHead()
    head.goals.mapless_until = float("inf")
    planned = []
    for time in range(40):
        current = request(time)
        sense.step(current)
        answer = head.decide(replace(current, place=sense.place))
        planned.append(names(answer))
        assert "walk_road" not in names(answer)
        if 22 <= time <= 30:
            assert names(answer) == ["descend"]
    assert planned[0] == ["leave_building"]
    assert planned[31] == ["leave_building"]


def test_an_errand_at_its_place_is_not_pulled_out_of_a_room_or_off_a_landing():
    from pilot.errands import Errand

    # A story marker can lie in a house and a shop's counter is in a room: an errand that has
    # arrived keeps its own plan there, and only one still on its way out leaves the room first.
    for step in ("approach", "await_story", "use", "leave", "switch"):
        for place in ("room", "landing"):
            head = MissionHead()
            head.goals.active = Errand("shop", started=0, seed=1, direction="north", step=step, wait_since=0)
            answer = head.decide(request(place=place))
            assert head.last_rule not in ("room_leave", "landing_descend"), (step, place)
            assert "descend" not in names(answer), (step, place)
    for step, place, plan in (("travel", "room", "leave_building"), ("waypoint", "landing", "descend")):
        head = MissionHead()
        head.goals.active = Errand("shop", started=0, seed=1, direction="north", step=step)
        assert names(head.decide(request(place=place))) == [plan]


def test_place_change_and_success_cancel_cooldown():
    for reset in ("done", "landing"):
        head = MissionHead()
        result = failed("leave_building", "timeout")
        head.decide(request(place="room"))
        for time in (1, 2, 3):
            head.decide(
                request(time, place="room", last=result, events=[{"kind": "skill_failed", "skill": result}])
            )
        assert head.place_rest_until == 123
        if reset == "done":
            head.decide(request(4, place="room", last={"name": "leave_building", "status": "done"}))
        else:
            head.decide(request(4, place="landing", last=result))
            head.decide(request(5, place="room", last=result))
        assert head.place_failures == 0
        assert head.place_rest_until == 0


def test_under_stars_a_car_that_could_not_be_entered_is_not_asked_for_again_at_once():
    """Review C, 1: enter_vehicle failing under stars was answered with enter_vehicle for ever."""
    head = MissionHead(goal_seed=0)
    first = head.decide(request(0, wanted=1, cars=True))
    assert names(first) == ["enter_vehicle", "get_away"]
    second = head.decide(request(3, wanted=1, cars=True, last=failed("enter_vehicle", "no-vehicle")))
    assert names(second) == ["walk"] and second.plan[0].args["sprint"] is True
    # After the run the next car in view is another try.
    ran = {"name": "walk", "status": "done", "reason": "time-limit", "queue": []}
    third = head.decide(request(9, wanted=1, cars=True, last=ran))
    assert names(third) == ["enter_vehicle", "get_away"]


def standing(t, count, **kwargs):
    return request(t, events=[{"kind": "standing", "count": count, "seconds": 12}], **kwargs)


def test_standing_in_a_mission_starts_no_errand_and_never_a_switch():
    """Review C, 2: the fourth report of standing ended "the errand" and drew a new one with an
    objective on screen, a switch of the character among them."""
    head = MissionHead(goal_seed=3)
    head.goals.switch_due = True
    seen = []
    for count in range(1, 9):
        answer = head.decide(standing(12.0 * count, count, objective="Fahre zum Treffpunkt."))
        seen.append((head.last_rule, tuple(names(answer))))
        assert head.goals.active is None and answer.goal is None
        assert "switch_character" not in names(answer) and "set_waypoint" not in names(answer)
    assert {rule for rule, _ in seen} == {"standing_recovery"}


def test_standing_in_free_roam_gives_the_errand_up_every_fourth_time_only():
    head = MissionHead(goal_seed=3)
    rules = []
    for count in range(1, 9):
        head.decide(standing(12.0 * count, count))
        rules.append(head.last_rule)
    assert [i + 1 for i, rule in enumerate(rules) if rule == "standing_abandon"] == [4, 8]
    assert rules[4:7] == ["standing_recovery"] * 3  # the errand begun at four is given its tries


def test_standing_on_the_letter_while_the_mission_starts_is_left_alone():
    """Review C, 5: twelve seconds on the marker, inside the errand's twenty, and the recovery walked
    the figure off it."""
    head = MissionHead(goal_seed=5)
    head.goals.chooser = lambda offers: "story"
    head.decide(request(0))
    goal = head.goals.active
    assert goal.name == "story"
    goal.step, goal.arrived, goal.wait_since, goal.attempts = "await_story", True, 24.0, 3
    waiting = {"name": "wait", "status": "running", "reason": None, "queue": []}
    answer = head.decide(standing(36.0, 1, last=waiting))
    assert head.last_rule != "standing_recovery"
    assert "walk" not in names(answer) and "press" not in names(answer)
    assert head.goals.active is goal and goal.step == "await_story"


def test_a_menu_reported_while_the_errand_at_home_runs_spends_nothing():
    """Review C, 6a."""
    menu = [{"kind": "stuck", "screen": "shop_menu", "seconds": 1.3}]
    head = MissionHead(goal_seed=2)
    head.goals.chooser = lambda offers: "home"
    head.decide(request(0))
    assert head.goals.active.name == "home"
    answer = head.decide(request(5, events=menu))
    assert [(call.name, call.args["spend"]) for call in answer.plan] == [("use_place", "no")]
    # In a mission, with no errand, the menu is the mission's and is used.
    answer = MissionHead(goal_seed=2).decide(request(5, events=menu, objective="Kauf einen Anzug."))
    assert [(call.name, call.args["spend"]) for call in answer.plan] == [("use_place", "yes")]


def test_a_dropped_answer_leaves_nothing_behind():
    """Review C, 7: the same request after a discard was answered differently, because the objective
    read by the dropped answer still counted."""
    asked = request(4, objective="Warte auf Michael.")
    fresh = MissionHead(goal_seed=1)
    fresh.decide(request(0))
    expected = fresh.decide(asked)
    head = MissionHead(goal_seed=1)
    head.decide(request(0))
    kept = {name: getattr(head, name) for name in head.KEPT}
    counts = head.counts.copy()
    head.decide(asked)
    head.discard()
    assert {name: getattr(head, name) for name in head.KEPT} == kept and head.counts == counts
    again = head.decide(asked)
    assert (names(again), again.action) == (names(expected), expected.action)
    assert head.last_rule == fresh.last_rule


def test_requests_that_change_nothing_do_not_use_up_the_routes_before_the_map_is_asked_again():
    """Review C, 8: three unchanged requests counted `letterless` down and the fourth replaced the
    set_waypoint that was running."""
    head = MissionHead(goal_seed=1)
    asked = dict(shape="tilted", objective="Fahre zum Treffpunkt.")
    head.decide(request(0, **asked))
    assert head.sought_mission
    answer = head.decide(request(5, last=failed("set_waypoint", "no-visible-mission-target"), **asked))
    assert answer.plan[-2].args["target"] == "away"
    left = head.letterless
    running = {
        "name": answer.plan[-2].name,
        "status": "running",
        "reason": None,
        "args": dict(answer.plan[-2].args),
        "queue": ["drive_route"],
    }
    for step in range(6):
        again = head.decide(request(6 + step, last=running, **asked))
        assert again.action == "go_on", step
    assert head.letterless == left


def test_the_same_answer_to_the_same_failure_changes_from_the_third_time():
    """Review C, 9: with an objective on screen one failing plan was repeated for as long as it failed."""
    head = MissionHead(goal_seed=3)
    asked = dict(objective="Bring den Wagen zurück.")
    plans = []
    for step in range(SAME_FAILED + 3):
        answer = head.decide(request(10.0 * step, last=failed("walk_road", "stuck"), **asked))
        plans.append((head.last_rule, tuple((call.name, call.args.get("angle")) for call in answer.plan)))
    assert len({plan for _, plan in plans[: SAME_FAILED - 1]}) == 1
    later = plans[SAME_FAILED - 1 :]
    assert {rule for rule, _ in later} == {"failed_again"}
    assert len({plan for _, plan in later[:3]}) == 3  # another direction each time
    # Seated, the car that gets nowhere is left.
    head = MissionHead(goal_seed=3)
    drive = dict(shape="tilted", objective="Fahre zum Treffpunkt.")
    for step in range(SAME_FAILED):
        answer = head.decide(request(10.0 * step, last=failed("drive_route", "no-progress"), **drive))
    assert head.last_rule == "failed_again_leave_vehicle"
    assert (answer.plan[0].name, answer.plan[0].args["button"]) == ("press", "triangle")


def test_stars_the_reader_misses_for_a_moment_do_not_make_the_seat_unknown():
    """The offline run of 13 November: 3 to 4 % of the frames in a car have the stars unread, and
    each of them sent the head to a tenth of a second's wait."""
    head = MissionHead(goal_seed=1)
    drive = dict(shape="tilted", route="yellow", objective="Fahre zum Treffpunkt.")
    head.decide(request(0, **drive))
    assert head.last_rule == "vehicle_route"
    head.decide(request(STARS_HOLD - 0.5, wanted=None, **drive))
    assert head.last_rule == "vehicle_route"
    # Longer than the reader has been seen to miss them, and nothing is assumed any more.
    head = MissionHead(goal_seed=1)
    head.decide(request(0, **drive))
    head.seat = None
    head.decide(request(STARS_HOLD + 0.5, wanted=None, **drive))
    assert head.last_rule != "vehicle_route"


def test_under_stars_the_seat_is_the_one_last_known():
    """With stars the map is tilted on foot as well. A car that picked up stars stood still, because
    the escape planned for a figure on foot."""
    head = MissionHead(goal_seed=1)
    head.decide(request(0, shape="tilted"))  # seated, no stars
    answer = head.decide(request(2, shape="tilted", wanted=2))
    assert names(answer) == ["get_away"]
    # On foot before the stars: the map tilts, the figure is still on foot.
    head = MissionHead(goal_seed=1)
    head.decide(request(0, shape="flat"))
    answer = head.decide(request(2, shape="tilted", wanted=2))
    assert names(answer) == ["walk"] and answer.plan[0].args["sprint"] is True
    # Entering a car is known from the skill that did it, and getting out from the plan that does.
    entered = {"name": "enter_vehicle", "status": "done", "reason": "entered", "queue": []}
    answer = head.decide(request(9, shape="tilted", wanted=2, last=entered))
    assert names(answer) == ["get_away"]
    answer = head.decide(request(20, shape="tilted", wanted=2, last=failed("get_away", "vehicle-held")))
    assert (answer.plan[0].name, answer.plan[0].args.get("button")) == ("press", "triangle")
    assert head.seat[0] == "on_foot"
    # What was known is not kept for ever.
    head = MissionHead(goal_seed=1)
    head.decide(request(0, shape="tilted"))
    answer = head.decide(request(SEAT_HOLD + 5, shape="tilted", wanted=2))
    assert names(answer) != ["get_away"]
    # A judge's word outranks what is held.
    head = MissionHead(goal_seed=1)
    head.decide(request(0, shape="tilted"))
    answer = head.decide(request(2, shape="tilted", wanted=2, judged="foot"))
    assert names(answer) == ["walk"]


BLUE = [{"color": "blue", "x": 4.0, "y": 30.0, "border": False}]
RED_FAR = [{"color": "red", "x": 10.0, "y": 60.0, "border": False}]
RED_NEAR = [{"color": "red", "x": 3.0, "y": 6.0, "border": False}]


def test_seated_with_an_order_and_no_route_the_car_goes_at_the_orders_marker():
    def plan(objective, blips, **kwargs):
        head = MissionHead(goal_seed=1)
        head.decide(request(0, shape="tilted", objective=objective, blips=blips, **kwargs))
        answer = head.decide(request(1, shape="tilted", objective=objective, blips=blips, **kwargs))
        return head.last_rule, [(call.name, call.args) for call in answer.plan]

    assert plan("Folge dem Lieferwagen.", BLUE) == (
        "objective_blip_follow",
        [("drive_to_blip", {"color": "blue", "mode": "follow", "duration": 120})],
    )
    assert plan("Verfolge die Yacht.", BLUE)[1] == [
        ("drive_to_blip", {"color": "blue", "mode": "catch", "duration": 120})
    ]
    assert plan("Schalte den Biker aus.", RED_FAR)[1] == [
        ("drive_to_blip", {"color": "red", "mode": "catch", "duration": 20})
    ]
    # Beside the target the figure gets out, and on foot the order is a fight.
    rule, calls = plan("Schalte den Biker aus.", RED_NEAR)
    assert rule == "take_out_leave_vehicle" and calls[0] == ("press", {"button": "triangle", "duration": 0.1})
    # A route is followed as before, and stars are fled.
    assert plan("Folge dem Lieferwagen.", BLUE, route="yellow")[0] == "vehicle_route"
    head = MissionHead(goal_seed=1)
    head.decide(request(0, shape="tilted", objective="Folge dem Lieferwagen.", blips=BLUE))
    head.decide(request(1, shape="tilted", objective="Folge dem Lieferwagen.", blips=BLUE, wanted=2))
    assert head.last_rule.startswith("wanted")
    # No marker of the order's kind: the rules below decide as they did.
    assert plan("Folge dem Lieferwagen.", [])[0] == "vehicle_waypoint"


def test_a_chase_that_ran_out_its_time_goes_on_and_a_held_car_is_left():
    head = MissionHead(goal_seed=1)
    asked = dict(shape="tilted", objective="Folge dem Lieferwagen.", blips=BLUE)
    head.decide(request(0, **asked))
    for step in range(SAME_FAILED + 2):
        answer = head.decide(request(120.0 * (step + 1), last=failed("drive_to_blip", "time-limit"), **asked))
        # No look first and no leaving the car: following has no arrival, its time is how it ends.
        assert names(answer) == ["drive_to_blip"], step
    answer = head.decide(request(900, last=failed("drive_to_blip", "vehicle-held"), **asked))
    assert head.last_rule == "leave_held_vehicle"
    assert (answer.plan[0].name, answer.plan[0].args["button"]) == ("press", "triangle")


def test_on_foot_with_the_targets_out_of_range_the_figure_goes_towards_them():
    """fight ends `target-out-of-range` on a red pinned to the map's rim (review D): the rules walk
    nearer instead of leaving it to chance."""
    rim = [{"color": "red", "x": 0.0, "y": 60.0, "border": True}]
    head = MissionHead(goal_seed=1)
    asked = dict(objective="Schalte die Gangster aus.", blips=rim)
    head.decide(request(0, **asked))
    answer = head.decide(request(1, **asked))
    assert head.last_rule == "take_out_approach"
    assert [(call.name, call.args["color"]) for call in answer.plan] == [("walk_to", "red")]
    # In range it is the fight, as before.
    near = [{"color": "red", "x": 0.0, "y": 20.0, "border": False}]
    head = MissionHead(goal_seed=1)
    head.decide(request(0, objective="Schalte die Gangster aus.", blips=near))
    answer = head.decide(request(1, objective="Schalte die Gangster aus.", blips=near))
    assert names(answer) == ["fight"]


def test_a_skill_of_the_place_that_is_running_is_left_to_run():
    # The guard's news and a changed help text ask the head again while the figure is on its way
    # out: answering with the same skill would begin its search for the door from the start.
    for place, skill in (("room", "leave_building"), ("landing", "descend")):
        head = MissionHead()
        assert names(head.decide(request(place=place))) == [skill]
        running = {"name": skill, "status": "running", "reason": "foot:state=round", "queue": []}
        for time, kind in ((2.0, "guard_news"), (4.5, "help_changed"), (7.0, "guard_end")):
            answer = head.decide(request(time, place=place, last=running, events=[{"kind": kind}]))
            assert answer.action == "go_on" and names(answer) == [], (place, kind)
        # Ended by the guard, it is planned again.
        ended = {"name": skill, "status": "failed", "reason": "guard_red", "queue": []}
        assert names(head.decide(request(9.0, place=place, last=ended))) == [skill]
