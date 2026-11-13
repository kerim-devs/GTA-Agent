"""A walk that is held up: Square first, then round on one side and further out, the other side only
when the first is closed, no leg judged by what was seen before it began, and no direction called
closed before the figure has jumped in it."""

import numpy as np
import pytest

import pilot.wayround as wayround
from pilot.ahead import View
from pilot.contract import Observation, Reading
from pilot.wayround import WayRound

FORWARD, RIGHT, LEFT = (0.0, -1.0), (1.0, 0.0), (-1.0, 0.0)
BACK_IN_RIGHT = (0.7071, -0.7071)


class Told(WayRound):
    """A guard that is told what the pictures would have shown, by the time and its own state."""

    def __init__(self, seen, **kwargs):
        super().__init__(**kwargs)
        self.seen = seen

    def _evidence(self, observation):
        return self.seen(observation.time, self)


def tick(time, *, moving=False, corrupt=False, arrow=0.0):
    return Observation(Reading("flat", "none", None, None, arrow, corrupt, 0.9), moving, time)


def run(guard, until, *, start=0.0, want=FORWARD):
    """A step every tenth of a second; what the guard steered, by the time."""
    steers = {}
    for index in range(round(start * 10), round(until * 10) + 1):
        steers[index / 10] = guard.step(tick(index / 10), want, sprint=True)
    return steers


def stretches(steers):
    """The guard's states in their order, each with the time it began."""
    found = []
    for time, steer in steers.items():
        if not found or found[-1][0] != steer.state:
            found.append((steer.state, time))
    return found


def went(steers, *expected):
    """The states are these in this order, each begun at about its time: a tick is a tenth of a second."""
    found = stretches(steers)
    return [state for state, _ in found] == [state for state, _ in expected] and all(
        abs(time - at) <= 0.15 for (_, time), (_, at) in zip(found, expected, strict=True)
    )


def still_unless_going_round(time, guard):
    return "going" if guard.state == "round" else "still"


def test_held_up_it_presses_square_once_and_pushes_on_where_it_wanted_to_go():
    guard = Told(lambda time, guard: "still")
    steers = run(guard, 2.9)
    assert went(steers, ("go", 0.0), ("climb", 1.5))
    pressed = [steer.buttons for steer in steers.values() if steer.buttons]
    assert pressed == [("square",)] * 2
    assert all(steer.left == FORWARD for steer in steers.values())


def test_a_climb_that_gets_the_figure_going_is_no_reason_to_go_round():
    # Over the fence of 13 November: going from 0.8 s after the press, then standing on top of it.
    guard = Told(lambda time, guard: "going" if 2.3 <= time < 3.0 else "still")
    steers = run(guard, 4.4)
    assert went(steers, ("go", 0.0), ("climb", 1.5), ("go", 3.1))
    # Standing on, it is held up again, and Square is not pressed a second time so soon.
    steers = run(guard, 6.2, start=4.5)
    assert steers[6.2].state == "round" and not any(steer.buttons for steer in steers.values())


def test_a_climb_that_frees_nothing_is_followed_by_a_way_round_at_right_angles_and_back_in():
    guard = Told(still_unless_going_round)
    steers = run(guard, 6.5)
    assert went(steers, ("go", 0.0), ("climb", 1.5), ("round", 3.1), ("go", 6.1))
    assert steers[3.5].left == pytest.approx(RIGHT) and steers[5.0].left == pytest.approx(RIGHT)
    assert steers[5.5].left == pytest.approx(BACK_IN_RIGHT, abs=1e-3)
    assert steers[6.5].left == FORWARD


def test_held_up_again_right_after_a_way_round_it_tries_square_and_goes_further_out_on_the_same_side():
    guard = Told(still_unless_going_round)
    steers = run(guard, 14.5)
    states = stretches(steers)
    assert [state for state, _ in states] == ["go", "climb", "round", "go", "climb", "round", "go"]
    # It may be another thing in the way now: Square once more, six seconds after the first press.
    pressed = [time for time, steer in steers.items() if steer.buttons]
    assert len(pressed) == 4 and pressed[2] - pressed[0] == pytest.approx(6.1, abs=0.15)
    # Then the same side, and three and a half seconds out instead of two.
    second, back = states[5][1], states[6][1]
    assert steers[second + 0.5].left == pytest.approx(RIGHT)
    assert back - second == pytest.approx(3.5 + 1.0, abs=0.15)
    assert guard.level == 1 and not guard.closed


def test_a_side_that_is_closed_itself_sends_it_round_the_other():
    guard = Told(lambda time, guard: "going" if guard.state == "round" and guard.side < 0 else "still")
    steers = run(guard, 10.5)
    # Two seconds of the right side, a jump at it, and only then the left.
    assert went(
        steers, ("go", 0.0), ("climb", 1.5), ("round", 3.1), ("climb", 5.1), ("round", 6.7), ("go", 9.7)
    )
    assert steers[4.0].left == pytest.approx(RIGHT) and steers[6.0].left == pytest.approx(RIGHT)
    assert steers[8.0].left == pytest.approx(LEFT)
    assert guard.closed == {1} and guard.jumped == {1}


def test_no_direction_is_called_closed_before_the_figure_has_jumped_in_it():
    # Kerim, 13 November: stuck, try Square as well, the jump, it helps. Here it does: eight tenths
    # of a second after the press to the right the figure is going.
    def seen(time, guard):
        jumping = guard.state == "round" and guard.leg_jump is not None
        return "going" if jumping and time - guard.leg_jump >= 0.8 else "still"

    guard = Told(seen)
    steers = run(guard, 10.5)
    assert went(
        steers, ("go", 0.0), ("climb", 1.5), ("round", 3.1), ("climb", 5.1), ("round", 6.7), ("go", 9.7)
    )
    pressed = [time for time, steer in steers.items() if steer.buttons]
    assert pressed == pytest.approx([1.5, 1.6, 5.1, 5.2]) and steers[5.1].buttons == ("square",)
    # The jump is in the leg's direction, and the leg goes on from where it landed.
    assert all(steers[time / 10].left == pytest.approx(RIGHT) for time in range(32, 86))
    assert steers[9.0].left == pytest.approx(BACK_IN_RIGHT, abs=1e-3) and not guard.closed
    # Without Square the guard does not jump either.
    guard = Told(lambda time, guard: "still", climb=False)
    steers = run(guard, 9.0)
    assert not any(steer.buttons for steer in steers.values()) and steers[9.0].failed == "stuck"


def test_with_both_sides_closed_it_walks_back_out_of_the_pocket_and_tries_them_again_further_out():
    # The porch of 13 November: wall ahead, window to the right, posts to the left, open behind.
    guard = Told(lambda time, guard: "going" if guard.state == "round" and guard.backed else "still")
    steers = run(guard, 18.0)
    # Each side for two seconds and a jump at it.
    states = ["go", "climb", "round", "climb", "round", "climb", "round", "go"]
    assert [state for state, _ in stretches(steers)] == states
    assert steers[4.0].left == pytest.approx(RIGHT) and steers[8.0].left == pytest.approx(LEFT)
    # Back for two and a half seconds, then out to the first side for three and a half, and in.
    assert all(steers[time / 10].left == pytest.approx((0.0, 1.0)) for time in range(106, 129))
    assert all(steers[time / 10].left == pytest.approx(RIGHT) for time in range(131, 164))
    assert steers[17.0].left == pytest.approx(BACK_IN_RIGHT, abs=1e-3) and steers[18.0].left == FORWARD
    assert guard.backed and not guard.closed


def test_a_figure_that_cannot_get_back_out_either_or_finds_the_sides_closed_again_is_stuck():
    guard = Told(lambda time, guard: "still")
    steers = run(guard, 15.5)
    failed = [time for time, steer in steers.items() if steer.failed]
    assert steers[failed[0]].failed == "stuck" and steers[failed[0]].left == (0.0, 0.0)
    # Forward, right, left and back, two seconds each and a jump of 1.6 s in each: fourteen seconds.
    assert failed[0] == pytest.approx(14.1, abs=0.2) and guard.phase == "back"
    assert sum(bool(steer.buttons) for steer in steers.values()) == 8 and guard.jumped == {1, -1, "back"}
    # And it stays stuck: a guard that has given up is not stepped back to life.
    assert all(steers[time].failed == "stuck" for time in failed) and failed[-1] == 15.5

    guard = Told(lambda time, guard: "going" if guard.state == "round" and guard.phase == "back" else "still")
    steers = run(guard, 18.0)
    failed = [time for time, steer in steers.items() if steer.failed]
    # From further back the sides are tried again, and not jumped at a second time.
    assert failed and failed[0] == pytest.approx(10.5 + 2.5 + 2.0 + 2.0, abs=0.3) and guard.closed == {1, -1}


def test_a_leg_is_not_judged_by_the_stand_it_began_from():
    # The fence of 13 November, 00:22: the figure stood while it was held up and for the first
    # moments of the leg, then ran along the fence. That side is open.
    begun = {}

    def seen(time, guard):
        if guard.state != "round":
            return "still"
        return "still" if time - begun.setdefault("at", time) < 0.9 else "going"

    guard = Told(seen)
    steers = run(guard, 6.5)
    assert went(steers, ("go", 0.0), ("climb", 1.5), ("round", 3.1), ("go", 6.1))
    assert steers[5.0].left == pytest.approx(RIGHT) and not guard.closed


def test_three_seconds_of_going_free_forget_the_obstacle():
    guard = Told(lambda time, guard: "going" if guard.state == "round" or time > 6.1 else "still")
    run(guard, 6.0)
    assert guard.rounds == 1
    run(guard, 10.0, start=6.1)
    assert guard.state == "go" and guard.rounds == 0 and guard.round_ended is None


def test_ways_round_that_never_end_in_going_free_are_given_up():
    guard = Told(still_unless_going_round)
    steers = run(guard, 90.0)
    failed = [time for time, steer in steers.items() if steer.failed]
    assert failed and steers[failed[0]].failed == "stuck"
    assert guard.rounds == WayRound.GIVE_UP + 1 and guard.level == len(WayRound.LEGS) - 1


def test_a_walk_that_wants_to_stand_ends_whatever_the_guard_was_doing():
    guard = Told(lambda time, guard: "still")
    run(guard, 3.5)
    assert guard.state == "round"
    steer = guard.step(tick(3.6), (0.0, 0.0), sprint=True)
    assert steer.state == "go" and steer.left == (0.0, 0.0) and guard.state == "go"


def test_the_way_round_turns_with_where_the_walk_wants_to_go():
    guard = Told(still_unless_going_round)
    run(guard, 3.5)
    # The camera has swung: the same way is now to the right of the picture.
    steer = guard.step(tick(3.6), RIGHT, sprint=True)
    assert steer.state == "round" and steer.left == pytest.approx((0.0, 1.0))


class Asked:
    """The model's word about the two sides, there from `ready` on."""

    def __init__(self, left, right, ready=0.0):
        self.reply, self.ready, self.frames, self.now = (left, right), ready, [], 0.0

    def ask(self, frame, capture):
        self.frames.append(capture)
        return True

    def answer(self, since):
        return self.reply if self.now >= self.ready else None


def hinted(asked, until, *, want=FORWARD):
    guard = Told(still_unless_going_round, sides=asked)
    steers = {}
    for index in range(round(until * 10) + 1):
        asked.now = index / 10
        steers[index / 10] = guard.step(tick(index / 10), want, sprint=True)
    return guard, steers


def test_the_side_the_model_calls_open_is_taken_first():
    asked = Asked(0.95, 0.03)
    guard, steers = hinted(asked, 4.0)
    assert asked.frames == [1.5]
    assert steers[3.5].left == pytest.approx(LEFT)
    assert guard.diagnostic().endswith(";side=left;leg=0;out;open=0.95/0.03")


def test_a_word_that_comes_in_the_first_second_of_a_way_round_still_turns_it_and_a_later_one_does_not():
    _, steers = hinted(Asked(0.95, 0.03, ready=3.6), 4.5)
    assert steers[3.3].left == pytest.approx(RIGHT) and steers[4.5].left == pytest.approx(LEFT)
    _, steers = hinted(Asked(0.95, 0.03, ready=4.4), 5.0)
    assert steers[5.0].left == pytest.approx(RIGHT)


def test_the_model_is_not_followed_where_it_names_no_side_or_the_camera_is_not_behind_the_figure():
    # Both sides open, as it said of a building's wall by night: the first side stays.
    _, steers = hinted(Asked(1.0, 0.97), 4.0)
    assert steers[3.5].left == pytest.approx(RIGHT)
    # The figure walks to the right of the picture: the picture's left is not its left.
    _, steers = hinted(Asked(0.95, 0.03), 4.0, want=RIGHT)
    assert steers[3.5].left == pytest.approx((0.0, 1.0))


@pytest.mark.parametrize(
    ("world", "over_map", "kind"),
    [
        (0.5, 3.0, "still"),  # wedged between two boulders: the map moves, the world does not
        (2.0, 0.4, "going"),
        (1.4, 3.0, None),
        (None, 0.9, "still"),  # against a rock with the world unread
        (None, 2.0, "going"),
        (None, 1.5, None),
    ],
)
def test_under_a_sprint_the_figure_is_measured_by_a_sprints_pace_and_by_the_world_first(
    monkeypatch, world, over_map, kind
):
    picture = np.zeros((2, 2), np.uint8)
    monkeypatch.setattr(wayround, "hud_crop", lambda frame: picture)
    monkeypatch.setattr(wayround, "world_view", lambda frame: None if world is None else picture)
    monkeypatch.setattr(wayround, "map_shift", lambda before, now: over_map)
    monkeypatch.setattr(wayround, "world_shift", lambda before, now: world)
    guard = WayRound()
    for time in (0.0, 0.5):
        guard.step(tick(time, moving=None), FORWARD, sprint=True)
    assert guard.evidence[-1] == (0.5, kind)


def test_a_walking_figure_is_measured_as_before(monkeypatch):
    import pilot.foot as foot

    picture = np.zeros((2, 2), np.uint8)
    monkeypatch.setattr(foot, "hud_crop", lambda frame: picture)
    monkeypatch.setattr(foot, "world_view", lambda frame: None)
    monkeypatch.setattr(foot, "map_shift", lambda before, now: 0.9)
    guard = WayRound()
    for time in (0.0, 0.5):
        guard.step(tick(time, moving=None), FORWARD)
    # 0.9 crop pixels in half a second is a walk, and under a sprint a figure against a rock.
    assert guard.evidence[-1] == (0.5, "going")


def test_a_damaged_tick_and_a_figure_off_its_feet_decide_nothing():
    guard = Told(lambda time, guard: "still")
    run(guard, 1.4)
    steer = guard.step(tick(1.5, corrupt=True), FORWARD, sprint=True)
    assert steer.state == "odd" and steer.left == (0.0, 0.0) and not steer.buttons
    vehicle = Observation(Reading("tilted", "none", None, None, 0.0, False, 0.9), False, 1.6, mode="vehicle")
    steer = guard.step(vehicle, FORWARD, sprint=True)
    assert steer.state == "idle" and steer.left == FORWARD and not guard.evidence


def test_a_press_of_square_cut_by_a_tick_that_says_nothing_is_not_pressed_again():
    guard = Told(lambda time, guard: "still")
    pressed = []
    for index in range(0, 75):
        time = index / 30
        # One damaged tick falls into the press.
        steer = guard.step(tick(time, corrupt=index == 47), FORWARD, sprint=True)
        pressed.append(bool(steer.buttons))
    runs = sum(1 for before, now in zip([False, *pressed], pressed, strict=False) if now and not before)
    assert runs == 1 and sum(pressed) <= 2
    # Uncut, the press is held for its fifteen hundredths of a second: five ticks.
    guard = Told(lambda time, guard: "still")
    assert sum(bool(guard.step(tick(index / 30), FORWARD, sprint=True).buttons) for index in range(75)) == 5


class Looks:
    """A model that answers at once. The view the figure is held up in is called outdoors, or a room;
    of the views after it the model says what is given here, in the order they are asked about."""

    def __init__(self, *views, room=False, silent=False, told=False):
        first = View(indoors=1.0, exit=0.01) if room else View(indoors=0.02)
        later = [view if isinstance(view, View) else View(open=view) for view in views]
        # A guard that has been told the place does not ask for it: the views given are all there is.
        self.views, self.silent, self.asked, self.how = later if told else [first, *later], silent, [], []

    def ask(self, frame, capture, *, indoors=None, ahead=True):
        self.asked.append(capture)
        self.how.append((indoors, ahead))
        return True

    def answer(self, since):
        if self.silent:
            return None
        return self.views[len(self.asked) - 1] if len(self.asked) <= len(self.views) else View(open=0.0)


def running_where_the_model_said(time, guard):
    return "going" if guard.state == "round" and guard.phase == "run" else "still"


def filmed(guard, until, *, start=0.0, want=FORWARD, arrow=0.0, rate=100.0, fresh=True):
    """Steps with a camera that turns as the right stick says, `rate` degrees a second, and an arrow
    that shows a standing figure's facing against it."""
    steers = {}
    for index in range(round(start * 10), round(until * 10) + 1):
        steer = guard.step(tick(index / 10, arrow=arrow), want, sprint=True, fresh=fresh)
        steers[index / 10] = steer
        arrow = (arrow - steer.right[0] * rate * 0.1 + 180.0) % 360.0 - 180.0
    return steers


def test_outdoors_a_side_is_felt_for_first_and_the_look_comes_when_it_is_closed():
    # Kerim, 13 November: stuck, the model is to look and say where the way goes on. And of the
    # looks at every hold-up, the same night: it stands and turns in circles.
    model = Looks(0.05, 0.97)
    guard = Told(running_where_the_model_said, ahead=model)
    steers = run(guard, 11.5)
    assert went(
        steers,
        ("go", 0.0),
        ("climb", 1.5),
        ("look", 3.1),
        ("round", 3.5),
        ("climb", 5.5),
        ("look", 7.2),
        ("round", 8.9),
        ("go", 10.9),
    )
    looking = [steer for time, steer in steers.items() if steer.state == "look"]
    assert all(steer.left == (0.0, 0.0) and not steer.buttons for steer in looking)
    # First the view as it stands, of which only the place is asked: the feet have judged it.
    assert all(steers[time / 10].right == (0.0, 0.0) for time in range(31, 35))
    assert guard.views[0] == "out" and model.how[0] == (None, False)
    # Outdoors: out to the right, running, and a jump at what closes that side.
    assert steers[3.6].left == pytest.approx(RIGHT) and steers[5.5].buttons == ("square",)
    # Closed: now a look. The camera goes right for half a second, and the picture settles.
    assert [steers[time / 10].right for time in range(72, 80)] == [(1.0, 0.0)] * 5 + [(0.0, 0.0)] * 3
    assert model.asked == pytest.approx([3.5, 8.1, 8.9]) and guard.views == ["out", "0.05", "0.97"]
    assert model.how[1:] == [(False, True)] * 2
    # Into the view it called open the figure runs straight, for as long as a leg sideways.
    assert all(steers[time / 10].left == (0.0, -1.0) for time in range(89, 109))
    assert all(steers[time / 10].right == (0.0, 0.0) for time in range(89, 115))
    assert steers[11.2].left == FORWARD and guard.round_ended == pytest.approx(10.9)
    assert ";views=out/0.05/0.97" in guard.diagnostic()


def test_a_side_that_is_free_is_run_without_a_look_and_a_guard_told_the_place_does_not_ask_for_it():
    def seen(time, guard):
        return "going" if guard.state == "round" else "still"

    model = Looks(0.05, 0.97)
    guard = Told(seen, ahead=model)
    steers = run(guard, 7.0)
    assert went(steers, ("go", 0.0), ("climb", 1.5), ("look", 3.1), ("round", 3.5), ("go", 6.5))
    assert model.asked == pytest.approx([3.5]) and all(steer.right == (0.0, 0.0) for steer in steers.values())
    # The walk asks for the place once a second and tells the guard: then the figure never stands.
    model = Looks(0.05, 0.97, told=True)
    guard = Told(seen, ahead=model)
    guard.place = guard.indoors = False
    steers = run(guard, 7.0)
    assert went(steers, ("go", 0.0), ("climb", 1.5), ("round", 3.1), ("go", 6.1))
    assert model.asked == [] and all(steer.left != (0.0, 0.0) for steer in steers.values())


def test_a_way_the_model_calls_open_is_judged_by_the_feet_like_any_other():
    # Open by the model's word and closed in fact, as a chain-link fence is: a jump at it, and the
    # camera goes on round.
    model = Looks(0.99, 0.99)

    def seen(time, guard):
        return "going" if guard.state == "round" and guard.phase == "run" and guard.looked == 3 else "still"

    guard = Told(seen, ahead=model)
    steers = run(guard, 15.0)
    states = [state for state, _ in stretches(steers)]
    assert states == [
        "go",
        "climb",
        "look",
        "round",
        "climb",
        "look",
        "round",
        "climb",
        "look",
        "round",
        "go",
    ]
    assert guard.looked == 3 and model.asked == pytest.approx([3.5, 8.1, 12.7])
    pressed = [time for time, steer in steers.items() if steer.buttons]
    assert len(pressed) == 6 and steers[pressed[4]].left == (0.0, -1.0)


def test_with_every_view_called_blocked_or_no_answer_the_other_side_is_felt_for():
    def left_is_free(time, guard):
        return (
            "going"
            if guard.state == "round" and guard.phase in ("out", "in") and guard.side == -1
            else "still"
        )

    guard = Told(left_is_free, ahead=Looks(0.1, 0.2, 0.0, 0.3))
    steers = run(guard, 14.0)
    # The right side felt for and closed, four looks of eight tenths of a second, and out to the left.
    assert went(
        steers,
        ("go", 0.0),
        ("climb", 1.5),
        ("look", 3.1),
        ("round", 3.5),
        ("climb", 5.5),
        ("look", 7.2),
        ("round", 10.7),
        ("go", 13.7),
    )
    assert len(guard.ahead.asked) == 5 and steers[11.0].left == pytest.approx(LEFT)

    # A model that does not answer costs a second of waiting, at this obstacle.
    def a_side_is_free(time, guard):
        return "going" if guard.state == "round" and guard.phase in ("out", "in") else "still"

    silent = Looks(silent=True)
    guard = Told(a_side_is_free, ahead=silent)
    steers = run(guard, 8.0)
    assert went(steers, ("go", 0.0), ("climb", 1.5), ("look", 3.1), ("round", 4.4), ("go", 7.4))
    assert len(silent.asked) == 1 and guard.views == ["none"]
    assert all(steer.left == (0.0, 0.0) for steer in steers.values() if steer.state == "look")


def test_a_look_goes_on_until_the_arrow_says_the_camera_is_round():
    # In the barber's half a second of the stick took the camera 40 degrees round and not 72.
    def turned(rate):
        model = Looks(0.97, told=True)
        guard = Told(lambda time, guard: "still", ahead=model)
        guard.place = guard.indoors = False
        steers = filmed(guard, 9.0, rate=rate)
        return [time for time, steer in steers.items() if steer.right != (0.0, 0.0)]

    # An arrow that stays where it is says nothing, and the turn is the clock's as before.
    assert turned(0.0) == pytest.approx([6.7, 6.8, 6.9, 7.0, 7.1])
    # A slow camera is turned for longer, a fast one let go sooner: what goes on after the stick
    # is let go is left out.
    assert len(turned(70.0)) == 8 and len(turned(148.0)) == 4


def test_in_a_room_the_model_is_asked_for_the_way_out_and_the_figure_runs_through_it():
    # Inside the barber's on 13 November every way was open for a few steps, and the walk that had
    # run in through the door did not find it again in a minute.
    model = Looks(
        View(exit=0.0),
        View(exit=1.0, parts=(1.0, 0.02, 0.0)),
        View(indoors=1.0, exit=1.0, parts=(0.0, 0.1, 0.9)),
        View(indoors=0.02),
        room=True,
    )
    guard = Told(running_where_the_model_said, ahead=model)
    steers = run(guard, 9.0)
    assert went(steers, ("go", 0.0), ("climb", 1.5), ("look", 3.1), ("round", 5.5), ("go", 8.3))
    assert guard.views == ["room0.01", "room0.00", "exitL", "outside"] and guard.indoors is False
    assert model.how == [(None, False), (True, True), (True, True), (None, False), (None, False)]
    # The door is in the left part of the picture: the camera goes left a little, and then the
    # figure runs straight at it, for longer than round an obstacle.
    assert steers[5.3].right == (-1.0, 0.0) and steers[5.4].right == (-1.0, 0.0)
    assert steers[5.3].left == (0.0, 0.0) and steers[5.4].state == "look"
    assert all(steers[time / 10].left == (0.0, -1.0) for time in range(55, 83))
    # On the way the door is looked at again: it has come to the right of the picture, and the
    # camera, which the stick goes by, is turned to it. Called outdoors, the figure runs straight
    # on for a second and a half more, a few steps before any turn, and the guard is done.
    turned = [time for time, steer in steers.items() if time > 5.45 and steer.right != (0.0, 0.0)]
    assert turned == pytest.approx([6.0, 6.1]) and steers[6.0].right == (1.0, 0.0)
    assert guard.outside == pytest.approx(6.8) and steers[8.5].left == FORWARD
    assert guard.outside + WayRound.CLEAR == pytest.approx(8.3)
    # A door in the middle of the picture is run at as it is.
    model = Looks(View(exit=0.95, parts=(0.1, 0.9, 0.3)), room=True)
    guard = Told(running_where_the_model_said, ahead=model)
    steers = run(guard, 5.0)
    assert guard.views == ["room0.01", "exitM"] and steers[4.5].left == (0.0, -1.0)
    assert steers[4.5].right == (0.0, 0.0) and steers[4.5].state == "round"


def test_out_of_a_building_it_ran_into_the_figure_goes_back_the_way_it_came():
    # Kerim, 13 November: use the way out you came in by; and once out, a few steps straight on
    # before you turn left or right.
    model = Looks(View(indoors=1.0, exit=0.2), View(indoors=0.02), told=True)
    guard = Told(lambda time, guard: "going", ahead=model)
    guard.step(tick(0.0, arrow=5.0), FORWARD, sprint=True)
    guard.back_out(tick(0.1, arrow=5.0))
    # The marker is behind the camera and not read: the direction the walk hands on is an old one.
    steers = filmed(guard, 11.0, start=0.1, arrow=5.0, fresh=False)
    assert went(steers, ("look", 0.1), ("round", 1.8), ("look", 4.2), ("round", 5.0), ("go", 10.0))
    # Standing, the camera goes round until the figure faces it: by the arrow, half a circle less
    # what it goes on by, and round the side the figure is turned to already.
    about = [steers[time / 10] for time in range(1, 18)]
    assert all(steer.left == (0.0, 0.0) and steer.right == (-1.0, 0.0) for steer in about)
    # Then into the picture, where it came from, with the model asked on the way where it is.
    assert all(steers[time / 10].left == (0.0, -1.0) for time in range(18, 42))
    assert model.how == [(None, False)] * 2 and guard.views == ["back", "outside"]
    # Outdoors: a second and a half straight on. The target lies behind, through the building:
    # a quarter turn of the camera and along the front, as far as the longest leg sideways.
    assert guard.outside == pytest.approx(2.6)
    assert all(steers[time / 10].right == (1.0, 0.0) for time in range(42, 50))
    assert all(steers[time / 10].left == (0.0, -1.0) for time in range(50, 100))
    assert not any(steer.buttons for steer in steers.values())


def test_behind_a_door_the_figure_turns_aside_only_where_the_target_lies_back_through_the_building():
    def left(want):
        model = Looks(View(indoors=0.02), told=True)
        guard = Told(lambda time, guard: "going", ahead=model)
        guard.step(tick(0.0, arrow=-5.0), FORWARD, sprint=True)
        guard.back_out(tick(0.1, arrow=-5.0))
        return guard, filmed(guard, 10.0, start=0.1, arrow=-5.0, want=want)

    # The marker is read and lies ahead: straight on and on to it.
    guard, steers = left(FORWARD)
    assert went(steers, ("look", 0.1), ("round", 1.8), ("go", 3.4))
    assert steers[0.5].right == (1.0, 0.0)  # the figure was turned a little to the left: round by the right
    # The marker is read and lies behind, to the left: along the front to the left.
    guard, steers = left((-0.8, 0.6))
    assert went(steers, ("look", 0.1), ("round", 1.8), ("look", 3.4), ("round", 4.2), ("go", 9.3))
    assert guard.side == -1 and steers[3.5].right == (-1.0, 0.0) and steers[5.0].left == (0.0, -1.0)


def test_a_walk_that_begins_in_a_room_has_the_way_out_looked_for_before_the_first_step():
    model = Looks(View(exit=0.0), told=True)
    guard = Told(lambda time, guard: "going", ahead=model)
    guard.step(tick(0.0), FORWARD, sprint=True)
    guard.leave(tick(0.1))
    steers = filmed(guard, 1.0, start=0.1)
    assert all(steer.state == "look" and steer.left == (0.0, 0.0) for steer in steers.values())
    assert model.how[0] == (True, False) and guard.views[0] == "room0.00"


def test_in_a_room_with_no_way_out_in_sight_the_figure_goes_round_along_the_walls():
    # Kerim, 13 November, of the worst case: run at every face once, all round the shop, until
    # you are out.
    rooms = [View(exit=0.0)] * 4 + [View(indoors=1.0, exit=0.0)] * 9 + [View(indoors=0.02)]
    model = Looks(*rooms, room=True)
    guard = Told(lambda time, guard: "going" if guard.outside is not None else "still", ahead=model)
    steers = filmed(guard, 18.0)
    found = stretches(steers)
    assert found[:4] == [("go", 0.0), ("climb", 1.5), ("look", 3.1), ("round", 7.9)]
    # Five views and no way out in any: an eighth turn of the camera, straight on until the
    # figure stands, the next turn, and so on, the model asked all the while where the figure is.
    assert guard.views[:6] == ["room0.01", "room0.00", "room0.00", "room0.00", "room0.00", "wall"]
    assert [steers[time / 10].right for time in range(74, 79)] == [(1.0, 0.0)] * 5
    assert all(steers[time / 10].left == (0.0, -1.0) for time in range(79, 99))
    assert found[4:8] == [("look", 9.9), ("round", 10.4), ("look", 12.4), ("round", 12.9)]
    assert not any(steer.buttons for time, steer in steers.items() if time > 2.0)
    # Called outdoors, it runs straight on for a second and a half and the guard is done.
    assert guard.views[-1] == "outside" and guard.outside == pytest.approx(15.5)
    assert found[-1] == ("go", 17.0)


def test_the_wall_round_ends_when_nothing_holds_the_figure_up_and_gives_up_after_three_times_round():
    # A model that is gone, in what the walk had called a room: running free for six seconds is out.
    model = Looks(silent=True)

    def seen(time, guard):
        return "going" if guard.state == "round" and guard.phase in ("wall", "run") else "still"

    guard = Told(seen, ahead=model)
    guard.place = guard.indoors = True
    steers = filmed(guard, 14.0)
    assert went(steers, ("go", 0.0), ("climb", 1.5), ("look", 3.1), ("round", 4.9), ("go", 13.4))
    assert guard.views == ["none", "wall", "free"]
    # Held up at every face, twenty-four turns and still in the room: stuck.
    rooms = [View(exit=0.0)] * 4 + [View(indoors=1.0, exit=0.0)] * 200
    guard = Told(lambda time, guard: "still", ahead=Looks(*rooms, room=True))
    steers = filmed(guard, 72.0)
    failed = [time for time, steer in steers.items() if steer.failed]
    assert failed[0] == pytest.approx(69.9) and steers[failed[0]].failed == "stuck"
    assert guard.wall_turns == WayRound.WALL_TURNS + 1
