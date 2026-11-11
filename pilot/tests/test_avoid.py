from pilot.avoid import CLEAR, HOLD, STALE, Avoider
from pilot.contract import Detection


def box(centre, bottom, height, kind="car", aspect=1.25):
    """A thing seen from behind: centre and bottom as shares of the picture, height of its width."""
    h = height * 1280
    w = aspect * h
    x, y = centre * 1280, bottom * 720
    return Detection(kind, (x - w / 2, y - h, x + w / 2, y), 0.9)


AHEAD = box(0.52, 0.55, 0.08)  # a car some lengths ahead, a little right of the own track's middle
NEXT_LANE = box(0.72, 0.55, 0.08)
FAR_AWAY = box(0.5, 0.45, 0.02)


def test_a_clear_road_changes_nothing():
    assert Avoider().step((), 0.0, 0.0) == CLEAR
    assert Avoider().step((NEXT_LANE, FAR_AWAY), 0.0, 0.0) == CLEAR


def test_a_car_ahead_pushes_to_the_other_side_and_lifts_the_pedal():
    around = Avoider().step((AHEAD,), 0.0, 0.0)
    assert around.steer < 0 and around.pedal < 1
    mirrored = Avoider().step((box(0.48, 0.55, 0.08),), 0.0, 0.0)
    assert mirrored.steer == -around.steer


def test_the_closer_the_harder_and_close_ahead_is_urgent():
    far = Avoider().step((box(0.5, 0.5, 0.05),), 0.0, 0.0)
    close = Avoider().step((box(0.5, 0.6, 0.14),), 0.0, 0.0)
    assert abs(close.steer) > abs(far.steer) > 0 and close.pedal < far.pedal
    assert close.urgent and not far.urgent


def test_the_side_is_kept_while_the_thing_is_in_the_way():
    avoider = Avoider()
    first = avoider.step((AHEAD,), 0.0, 0.0)
    # Mid-swerve the car ahead has moved across the picture's middle; the push must not flip.
    second = avoider.step((box(0.47, 0.55, 0.09),), 0.3, 0.3)
    assert first.steer < 0 and second.steer < 0
    later = avoider.step((box(0.47, 0.55, 0.09),), 0.3 + HOLD + 0.5, 0.3 + HOLD + 0.5)
    assert later.steer > 0


def test_a_taken_lane_sends_the_push_to_the_other_side_and_two_keep_the_car_behind():
    left_taken = box(0.34, 0.6, 0.09)
    around = Avoider().step((box(0.48, 0.55, 0.08), left_taken), 0.0, 0.0)
    assert around.steer > 0  # away from the centre would be right anyway
    around = Avoider().step((AHEAD, left_taken), 0.0, 0.0)
    assert around.steer > 0  # left is taken, so right although the car ahead sits a little right
    boxed_in = Avoider().step((AHEAD, left_taken, box(0.68, 0.6, 0.09)), 0.0, 0.0)
    assert boxed_in.steer == 0 and boxed_in.pedal < 1


def test_old_boxes_and_the_minimap_say_nothing():
    assert Avoider().step((AHEAD,), 0.0, STALE + 0.1) == CLEAR
    assert Avoider().step((AHEAD,), None, 0.0) == CLEAR
    minimap = Detection("car", (40, 590, 200, 700), 0.9)
    assert Avoider().step((minimap,), 0.0, 0.0) == CLEAR


def test_a_person_and_a_lorry_count_by_their_height():
    person = box(0.5, 0.6, 0.12, kind="person", aspect=0.4)
    assert Avoider().step((person,), 0.0, 0.0).pedal < 1
    lorry_next_lane = box(0.75, 0.6, 0.2, kind="truck", aspect=1.0)
    assert Avoider().step((lorry_next_lane,), 0.0, 0.0) == CLEAR
