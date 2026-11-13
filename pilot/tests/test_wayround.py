"""A walk that is held up: Square first, then round on one side and further out, the other side only
when the first is closed, and no leg judged by what was seen before it began."""

import numpy as np
import pytest

import pilot.wayround as wayround
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


def tick(time, *, moving=False, corrupt=False):
    return Observation(Reading("flat", "none", None, None, 0.0, corrupt, 0.9), moving, time)


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
    steers = run(guard, 8.5)
    assert went(steers, ("go", 0.0), ("climb", 1.5), ("round", 3.1), ("go", 8.1))
    assert steers[4.0].left == pytest.approx(RIGHT) and steers[6.0].left == pytest.approx(LEFT)
    assert guard.closed == {1}


def test_with_both_sides_closed_it_walks_back_out_of_the_pocket_and_tries_them_again_further_out():
    # The porch of 13 November: wall ahead, window to the right, posts to the left, open behind.
    guard = Told(lambda time, guard: "going" if guard.state == "round" and guard.backed else "still")
    steers = run(guard, 15.0)
    assert went(steers, ("go", 0.0), ("climb", 1.5), ("round", 3.1), ("go", 14.1))
    assert steers[4.0].left == pytest.approx(RIGHT) and steers[6.0].left == pytest.approx(LEFT)
    # Back for two and a half seconds, then out to the first side for three and a half, and in.
    assert all(steers[time / 10].left == pytest.approx((0.0, 1.0)) for time in range(72, 96))
    assert all(steers[time / 10].left == pytest.approx(RIGHT) for time in range(98, 130))
    assert steers[13.5].left == pytest.approx(BACK_IN_RIGHT, abs=1e-3) and steers[14.5].left == FORWARD
    assert guard.backed and not guard.closed


def test_a_figure_that_cannot_get_back_out_either_or_finds_the_sides_closed_again_is_stuck():
    guard = Told(lambda time, guard: "still")
    steers = run(guard, 10.5)
    failed = [time for time, steer in steers.items() if steer.failed]
    assert steers[failed[0]].failed == "stuck" and steers[failed[0]].left == (0.0, 0.0)
    assert failed[0] == pytest.approx(9.1, abs=0.15) and guard.phase == "back"
    # And it stays stuck: a guard that has given up is not stepped back to life.
    assert all(steers[time].failed == "stuck" for time in failed) and failed[-1] == 10.5

    guard = Told(lambda time, guard: "going" if guard.state == "round" and guard.phase == "back" else "still")
    steers = run(guard, 16.0)
    failed = [time for time, steer in steers.items() if steer.failed]
    assert failed and failed[0] == pytest.approx(7.1 + 2.5 + 2.0 + 2.0, abs=0.3) and guard.closed == {1, -1}


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
