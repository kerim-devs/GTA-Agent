"""Offline scripted worlds: progress must come from skill and HUD observations."""

from dataclasses import replace
from itertools import pairwise

import pytest

from pilot.errands import ERRANDS, LIMITS, SHOPS
from pilot.goals import Goals
from pilot.head import HeadRequest, parse_response, response_data
from pilot.mission import MissionHead


def request(t=0, *, mode="foot", wanted=0, last=None, events=None, objective="", help="", route="none"):
    return HeadRequest(
        events=events or [],
        help=help,
        objective=objective,
        subtitle="",
        banner="",
        minimap={"minimap": "flat" if mode == "foot" else "tilted", "route": route, "blips": []},
        last_skill=last,
        notebook="",
        jpeg_path="unused.jpg",
        time=t,
        hud={"screen": "game", "health": 1, "wanted": wanted},
        judgment={"mode": mode},
        objects=[{"kind": "car"}, {"kind": "person"}],
    )


def result(name, reason, status="done", **extra):
    return {"name": name, "status": status, "reason": reason, "queue": [], **extra}


def names(answer):
    return [item.name for item in answer.plan]


def head_for(name, seed=7):
    head = MissionHead(goal_seed=seed)
    head.goals.chooser = lambda offers: name if any(o["name"] == name for o in offers) else None
    return head


class World:
    """A skill-completion script, not a fake renderer or a live-console claim."""

    def __init__(self, head, distance=200):
        self.head = head
        self.distance = distance
        self.t = 0
        self.mode = "foot"
        self.wanted = 0
        self.route = "none"
        self.last = None
        self.objective = ""
        self.calls = []

    def tick(self):
        req = request(
            self.t,
            mode=self.mode,
            wanted=self.wanted,
            route=self.route,
            last=self.last,
            objective=self.objective,
        )
        answer = self.head.decide(req)
        assert parse_response(response_data(answer)) == answer
        if self.wanted:
            assert "set_waypoint" not in names(answer)
        for item in answer.plan:
            self.calls.append(item)
            name, args = item.name, item.args
            reason = "time-limit"
            if name == "set_waypoint":
                place = args.get("place", "Franklin" if args.get("target") == "mission" else "Away")
                reason = f"waypoint set: {place} ({self.distance}m); gameplay observed"
                self.route = "purple"
            elif name == "enter_vehicle":
                self.mode, reason = "vehicle", "entered vehicle"
            elif name == "press" and args.get("button") == "triangle":
                self.mode = "foot"
            elif name == "drive_route":
                reason, self.route = "arrived", "none"
            elif name == "walk_to_point":
                reason = "entered" if args.get("enter") else "arrived; at/on symbol under waypoint"
            elif name == "use_place":
                reason = "used: wardrobe" if self.head.goals.active.name == "home" else "used: shop"
            elif name == "leave_building":
                reason = "outdoors"
            elif name == "punch":
                reason, self.wanted = "delivered 3 punch pulses in reach", 1
            elif name == "get_away":
                reason, self.wanted = "wanted cleared", 0
            elif name == "switch_character":
                reason = "switched: franklin"
            self.last = result(name, reason, args=args, route_seen=name == "drive_route")
        self.t += 3
        return answer

    def finish(self, name, *, story_starts=True):
        for _ in range(80):
            answer = self.tick()
            goal = self.head.goals.active
            if goal and goal.name == "story" and goal.step == "await_story" and story_starts:
                self.objective = "Fahre zum Treffpunkt."
            ended = [h for h in self.head.goals.history if h["name"] == name and h["outcome"] != "started"]
            if ended:
                return ended[-1], answer
        pytest.fail(f"{name} never ended")


@pytest.mark.parametrize("name", ERRANDS)
@pytest.mark.parametrize("distance", [200, 700])
def test_scripted_world_completes_each_errand_only_after_its_observed_end(name, distance):
    world = World(head_for(name), distance)
    ended, _ = world.finish(name)
    assert ended["outcome"] == "reached"
    calls = [c.name for c in world.calls]
    if name in {"story", "shop", "home", "cruise"}:
        assert calls[0] == "set_waypoint"
        if distance <= 250:
            assert "drive_route" not in calls and "enter_vehicle" not in calls
        else:
            assert "drive_route" in calls
    if name in {"shop", "home"}:
        assert calls.index("use_place") < calls.index("leave_building")
        door = next(c for c in world.calls if c.name == "walk_to_point" and c.args.get("exact"))
        assert door.args["enter"] is True
        assert not any(c.name == "press" and c.args.get("button") != "triangle" for c in world.calls)
    if name == "mayhem":
        assert calls.index("punch") < calls.index("get_away")


@pytest.mark.parametrize("name", [name for name in ERRANDS if name != "story"])
def test_each_errand_failure_and_deadline_selects_a_following_errand(name):
    head = head_for(name)
    first = head.decide(request())
    failure = result(first.plan[0].name, "not-built", "failed")
    head.decide(request(2, last=failure))
    assert any(h["name"] == name and h["outcome"] == "gave_up" for h in head.goals.history)
    head = head_for(name)
    head.decide(request())
    head.decide(request(LIMITS[name][0] + 1))
    assert any(h["name"] == name and h["reason"] == "limit" for h in head.goals.history)


def test_sixty_completed_errands_obey_selection_policy_and_validate_every_call():
    head = MissionHead(goal_seed=70)
    world = World(head)
    sequence = []
    for _ in range(5000):
        world.tick()
        active = head.goals.active
        if active and active.name == "story" and active.step == "await_story":
            world.objective = "Fahre zum Treffpunkt."
        elif world.objective:
            world.objective = ""
            # Intent stabilization needs two objective-free observations.
        finished = [h for h in head.goals.history if h["name"] in ERRANDS and h["outcome"] == "reached"]
        if len(finished) >= 60:
            sequence = [h["name"] for h in finished[:60]]
            break
    assert len(sequence) == 60
    assert all(a != b or a == "story" for a, b in pairwise(sequence))
    starts = [h for h in head.goals.history if h["outcome"] == "started"]
    for name, seconds in (("home", 3600), ("mayhem", 600)):
        times = [h["time"] for h in starts if h["name"] == name]
        assert all(b - a >= seconds for a, b in pairwise(times))
    for place in SHOPS:
        times = [h["time"] for h in starts if h["name"] == "shop" and h["place"] == place]
        assert all(b - a >= 1800 for a, b in pairwise(times))


def test_chooser_offers_descriptions_weights_and_seeded_fallback():
    offers_seen = []

    def chooser(offers):
        offers_seen.append(offers)
        return None

    left, right = Goals(seed=71, chooser=chooser), Goals(seed=71)
    assert [left.choose(request()) for _ in range(60)] == [right.choose(request()) for _ in range(60)]
    assert {o["name"]: o["weight"] for o in offers_seen[0]} == ERRANDS
    assert all(o["description"] for o in offers_seen[0])
    left.story_dampened = True
    left.choose(request())
    assert next(o["weight"] for o in offers_seen[-1] if o["name"] == "story") == 2.5


def test_two_nonstarting_letters_are_remembered_and_switch_once_before_next():
    head = head_for("story")
    world = World(head)
    for _ in range(60):
        world.tick()
        if any(c.name == "switch_character" for c in world.calls):
            break
    assert head.goals.story_instance == 2
    assert head.goals.story_dampened
    assert sum(c.name == "switch_character" for c in world.calls) == 1
    instances = [c.args.get("instance") for c in world.calls if c.name == "set_waypoint"]
    assert instances[:2] == [0, 1]
    world.finish("story")


@pytest.mark.parametrize("failure", ["no-prompt", "menu-unread", "too-dear", "time-limit", "not-built"])
def test_failed_use_always_leaves_and_does_not_claim_success(failure):
    head = head_for("shop")
    world = World(head)
    while not world.last or world.last["name"] != "use_place":
        world.tick()
    world.last = result("use_place", failure, "failed")
    answer = world.tick()
    assert names(answer) == ["leave_building"]
    world.tick()
    assert any(h["name"] == "shop" and h["outcome"] == "gave_up" for h in head.goals.history)


@pytest.mark.parametrize("name", ["shop", "home"])
@pytest.mark.parametrize("reason", ["arrived; no door found", "arrived; on the symbol under the waypoint"])
def test_a_visit_without_an_observed_entrance_never_uses_the_place(name, reason):
    head = head_for(name)
    world = World(head)
    for _ in range(10):
        world.tick()
        if world.last["name"] == "walk_to_point" and world.last["args"].get("enter"):
            break
    else:
        pytest.fail("visit never approached its entrance")
    world.last = result("walk_to_point", reason)
    answer = world.tick()
    assert "use_place" not in names(answer)
    assert any(
        row["name"] == name and row["outcome"] == "gave_up" and row["reason"] == "entrance not observed"
        for row in head.goals.history
    )


@pytest.mark.parametrize("name", ["shop", "home"])
def test_confirmed_visit_stages_are_available_in_the_next_session(tmp_path, monkeypatch, name):
    from pilot import memory

    path = tmp_path / "memory.json"
    first = memory.Memory(path, clock=lambda: 1000.0)
    monkeypatch.setattr(memory, "_active", first)
    head = head_for(name)
    world = World(head)
    ended, _ = world.finish(name)
    first.close()
    second = memory.Memory(path, clock=lambda: 1060.0)
    entry = second.get(memory.PLACES, ended["place"])
    assert {key: entry[key] for key in ("entered", "used", "left", "reached")} == {
        "entered": 1,
        "used": 1,
        "left": 1,
        "reached": 1,
    }


def test_no_entrance_is_learnt_once_and_the_next_session_chooses_another_shop(tmp_path, monkeypatch):
    from pilot import memory

    path = tmp_path / "memory.json"
    first = memory.Memory(path, clock=lambda: 1000.0)
    monkeypatch.setattr(memory, "_active", first)
    head = head_for("shop")
    world = World(head)
    for _ in range(10):
        world.tick()
        if world.last["name"] == "walk_to_point" and world.last["args"].get("enter"):
            break
    else:
        pytest.fail("shop never approached its entrance")
    place = head.goals.active.place
    observed = request(world.t, last=result("walk_to_point", "arrived; no door found"), route="purple")
    head.decide(observed)
    head.discard()
    head.decide(observed)
    first.close()

    second = memory.Memory(path, clock=lambda: 1060.0)
    monkeypatch.setattr(memory, "_active", second)
    entry = second.get(memory.PLACES, place)
    assert entry["entry_failed"] == entry["failed"] == 1
    assert not any(entry.get(key) for key in ("entered", "used", "left", "reached"))
    next_head = head_for("shop")
    next_head.decide(request())
    assert next_head.goals.active.name == "shop"
    assert next_head.goals.active.place != place


@pytest.mark.parametrize(
    "count,expected", [(1, ["press", "walk"]), (2, ["look", "walk"]), (3, ["walk", "look", "walk_road"])]
)
def test_standing_uses_sender_count_even_with_intervening_nonstanding_requests(count, expected):
    head = head_for("shop")
    head.decide(request())
    answer = head.decide(request(12, events=[{"kind": "standing", "seconds": 12, "count": count}]))
    assert names(answer) == expected


def test_fourth_standing_abandons_running_goal_and_indoors_leaves_from_second():
    head = head_for("shop")
    head.decide(request())
    last = result("walk_to_point", "entered")
    answer = head.decide(request(12, last=last, events=[{"kind": "standing", "count": 2}]))
    assert names(answer) == ["leave_building"]
    answer = head.decide(
        request(24, last=result("leave_building", "", "running"), events=[{"kind": "standing", "count": 4}])
    )
    assert answer.plan
    assert head.goals.history[-2]["reason"] == "standing four times"


@pytest.mark.parametrize(
    "event", [None, "failure", "skill_failed", "screen", "standing", "guard", "guard_stars"]
)
def test_identical_running_call_kept_except_explicit_interruptions(event):
    head = MissionHead()
    req = request(objective="Warte hier.")
    initial = head.decide(req)
    first = initial.plan[0]
    last = result(first.name, "", "running", args=first.args)
    req = replace(req, last_skill=last, events=[] if event is None else [{"kind": event, "count": 1}])
    answer = head.decide(req)
    assert (answer.action == "go_on") is (event is None)


def test_objective_prompt_precedes_other_rules_once_per_exact_text():
    head = MissionHead()
    req = request(objective="Benutze den Schalter.", help="Drücke X zum Öffnen.")
    assert names(head.decide(req)) == ["do_prompt"]
    assert "do_prompt" not in names(head.decide(req))
    assert names(head.decide(replace(req, help="Halte X zum Öffnen."))) == ["do_prompt"]


@pytest.mark.parametrize("mode", ["foot", "vehicle"])
@pytest.mark.parametrize("route", ["none", "purple", "yellow"])
def test_stars_never_open_map_and_use_get_away(mode, route):
    head = MissionHead()
    answer = head.decide(request(mode=mode, wanted=2, route=route))
    assert "set_waypoint" not in names(answer)
    assert "get_away" in names(answer)


@pytest.mark.parametrize("reason", ["vehicle-held", "water", "on-foot"])
def test_get_away_failures_recover_by_observed_reason(reason):
    head = MissionHead()
    head.decide(request(mode="vehicle", wanted=2))
    answer = head.decide(request(10, mode="vehicle", wanted=2, last=result("get_away", reason, "failed")))
    assert "set_waypoint" not in names(answer)
    if reason == "vehicle-held":
        assert names(answer) == ["press", "wait", "walk_road"]
    else:
        assert names(answer)[0] == "enter_vehicle"


def test_mark_undo_restores_choice_cooldown_and_history():
    goals = Goals(seed=5)
    goals.mark()
    first = goals.decide(request(), "on_foot")
    goals.undo()
    assert goals.decide(request(), "on_foot") == first


@pytest.mark.parametrize("name", ERRANDS)
def test_attempt_limit_really_abandons_the_current_errand(name):
    head = head_for(name)
    first = head.decide(request())
    for tick in range(1, LIMITS[name][1] + 1):
        head.decide(request(tick))
    assert any(
        h["name"] == name
        and h["started"] == first.goal["started"]
        and h["outcome"] == "gave_up"
        and h["reason"] == "limit"
        for h in head.goals.history
    )


@pytest.mark.parametrize("distance,skill", [(250, "walk_to_point"), (251, "enter_vehicle")])
def test_distance_boundary_decides_the_trip_after_waypoint_observation(distance, skill):
    world = World(head_for("story"), distance)
    world.tick()
    assert names(world.tick()) == [skill]


@pytest.mark.parametrize("name", ["story", "shop", "home", "cruise"])
@pytest.mark.parametrize("skill", ["set_waypoint", "walk_to_point", "enter_vehicle", "drive_route"])
def test_trip_failures_are_bounded_and_eventually_begin_another_errand(name, skill):
    head = head_for(name)
    world = World(head, 700 if skill in {"enter_vehicle", "drive_route"} else 200)
    for _ in range(20):
        world.tick()
        if world.last and world.last["name"] == skill:
            break
    else:
        pytest.fail(f"did not reach {skill}")
    started = head.goals.active.started
    world.last = result(skill, "blocked", "failed")
    world.tick()
    if head.goals.active and head.goals.active.started == started:
        # Seeking a usable car/road can retry, but never beyond its errand's deadline.
        world.t = started + LIMITS[name][0]
        world.tick()
    assert any(
        h["name"] == name and h["started"] == started and h["outcome"] == "gave_up"
        for h in head.goals.history
    )


def test_twice_abandoned_place_is_excluded_and_shop_cooldown_expires():
    goals = Goals(seed=70, chooser=lambda offers: "shop")
    first = goals.decide(request(), "on_foot")
    place = first.goal["place"]
    goals.end(request(1), "blocked")
    assert place not in goals.shops(1799)
    assert place in goals.shops(1800)
    goals.abandonments[place] += 1
    assert place not in goals.shops(99999)


def test_mission_success_restores_story_weight_and_cutscene_is_observed():
    head = head_for("story")
    world = World(head)
    head.goals.story_dampened = True
    while not head.goals.active or head.goals.active.step != "await_story":
        world.tick()
    head.decide(request(world.t, events=[{"kind": "screen", "screen": "cutscene"}]))
    assert head.goals.history[-1]["outcome"] == "reached"
    assert not head.goals.story_dampened


def test_objective_before_arrival_does_not_claim_story_completion():
    head = head_for("story")
    head.decide(request())
    head.decide(request(2, objective="Fahre zum Treffpunkt."))
    assert not any(h["outcome"] == "reached" for h in head.goals.history)


def test_shop_exit_without_outdoors_is_not_success_and_failed_exit_moves_on():
    for status in ("done", "failed"):
        head = head_for("shop")
        world = World(head)
        while not world.last or world.last["name"] != "leave_building":
            world.tick()
        world.last = result("leave_building", "time-limit", status)
        world.tick()
        assert any(h["name"] == "shop" and h["outcome"] == "gave_up" for h in head.goals.history)


def test_discarded_prompt_can_be_planned_again():
    head = MissionHead()
    req = request(objective="Benutze den Schalter.", help="Drücke X.")
    first = head.decide(req)
    head.discard()
    assert head.decide(req) == first


def test_held_escape_walks_away_before_another_car_and_never_opens_map():
    head = MissionHead()
    head.decide(request(mode="vehicle", wanted=2))
    head.decide(request(10, mode="vehicle", wanted=2, last=result("get_away", "vehicle-held", "failed")))
    early = head.decide(request(13, wanted=2, last=result("walk_road", "time-limit")))
    assert names(early) == ["walk_road"]
    later = head.decide(request(23, wanted=2, last=result("walk_road", "time-limit 2")))
    assert names(later) == ["enter_vehicle"]
    seated = head.decide(
        request(30, mode="vehicle", wanted=2, last=result("enter_vehicle", "entered vehicle"))
    )
    assert names(seated) == ["get_away"]


def test_short_cruise_started_in_a_car_walks_and_never_uses_a_place():
    world = World(head_for("cruise"), 200)
    world.mode = "vehicle"
    ended, _ = world.finish("cruise")
    assert ended["outcome"] == "reached"
    assert "use_place" not in [c.name for c in world.calls]
    assert next(c for c in world.calls if c.name == "walk_to_point").args["sprint"]


def test_story_twenty_second_timeout_can_interrupt_a_running_wait():
    head = head_for("story")
    world = World(head)
    while not head.goals.active or head.goals.active.step != "await_story":
        world.tick()
    since = head.goals.active.wait_since
    answer = head.decide(request(since + 20, last=result("wait", "", "running", args={"duration": 3})))
    assert names(answer) == ["set_waypoint"]
    assert answer.plan[0].args["instance"] == 1
    assert head.goals.history[-2]["reason"] == "letter did not start a mission"


def at_road_without_car():
    world = World(head_for("story"), 1000)
    world.tick()
    answer = world.head.decide(replace(request(3, last=world.last, route="purple"), objects=[]))
    assert names(answer) == ["walk_road"]
    return world.head


def test_roadside_no_car_waits_then_walks_before_waiting_again():
    head = at_road_without_car()
    side = result("walk_road", "road-side (map band; kerb unverified)")
    answer = head.decide(replace(request(20, last=side, route="purple"), objects=[]))
    assert names(answer) == ["enter_vehicle"]
    assert answer.plan[0].args["traffic"] is True
    assert parse_response(response_data(answer)) == answer
    timeout = result(
        "enter_vehicle", "nothing found; no stopped reachable car or motorcycle; traffic wait ended", "failed"
    )
    answer = head.decide(replace(request(46, last=timeout, route="purple"), objects=[]))
    assert names(answer) == ["walk_road"]
    assert answer.plan[0].args["duration"] == 8
    assert answer.plan[0].args["toward_waypoint"] is True
    answer = head.decide(replace(request(55, last=side, route="purple"), objects=[]))
    assert names(answer) == ["enter_vehicle"]
    assert answer.plan[0].args["traffic"] is True


def test_visible_parked_choice_precedes_traffic_wait_at_roadside():
    head = at_road_without_car()
    side = result("walk_road", "road-side (map band; kerb unverified)")
    answer = head.decide(request(20, last=side, route="purple"))
    assert names(answer) == ["enter_vehicle"]
    assert not answer.plan[0].args.get("traffic", False)
    failed = result(
        "enter_vehicle", "nothing found; saw 1 vehicle (rejected 0, avoided 0, moving 1)", "failed"
    )
    answer = head.decide(request(46, last=failed, route="purple"))
    assert answer.plan[0].args["traffic"] is True


def test_unknown_roadside_is_not_a_traffic_wait_location():
    head = at_road_without_car()
    unknown = result("walk_road", "side unknown")
    answer = head.decide(replace(request(20, last=unknown), objects=[]))
    assert names(answer) == ["walk_road"]


def test_replacement_car_uses_the_roadside_wait():
    head = at_road_without_car()
    head.goals.active.step = "replace_car"
    side = result("walk_road", "road-side (map band; kerb unverified)")
    answer = head.decide(replace(request(20, last=side), objects=[]))
    assert names(answer) == ["enter_vehicle"]
    assert answer.plan[0].args["traffic"] is True


def test_wanted_after_traffic_attempt_still_plans_escape():
    head = at_road_without_car()
    side = result("walk_road", "road-side (map band; kerb unverified)")
    head.decide(replace(request(20, last=side), objects=[]))
    entered = result("enter_vehicle", "entered vehicle; occupancy=occupied")
    answer = head.decide(request(28, mode="vehicle", wanted=1, last=entered))
    assert "get_away" in names(answer)
    assert "enter_vehicle" not in names(answer)
    assert "walk_road" not in names(answer)


def test_wanted_during_traffic_wait_still_plans_escape():
    head = at_road_without_car()
    side = result("walk_road", "road-side (map band; kerb unverified)")
    head.decide(replace(request(20, last=side), objects=[]))
    running = result("enter_vehicle", "waiting for stopped reachable traffic", "running")
    answer = head.decide(replace(request(22, wanted=1, last=running), objects=[]))
    assert answer.step == "escape"
    assert names(answer) == ["walk"]
    assert answer.plan[0].args["sprint"] is True
    assert "stars" in answer.reason
