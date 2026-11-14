import json
from pathlib import Path

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
FIXTURE = Path(__file__).parent / "fixtures" / "p96_traffic.json"


def approach(avoider=None, *others, t0=0.0, grow=1.5, **spec):
    """Step an avoider through a second of a thing that grows by `grow` in the picture; the last answer.

    `spec` is the arguments of `box` for the thing's last size, `others` are boxes that stand still."""
    avoider = avoider or Avoider()
    around = CLEAR
    for tick in range(6):
        size = spec["height"] / grow ** (1 - tick / 5)
        now = t0 + tick * 0.2
        around = avoider.step((box(**{**spec, "height": size}), *others), now, now)
    return around


def keeping(avoider=None, *others, t0=0.0, seconds=1.0, **spec):
    """The same for a thing that keeps its size; returns every answer."""
    avoider = avoider or Avoider()
    answers = []
    for tick in range(round(seconds / 0.2) + 1):
        now = t0 + tick * 0.2
        answers.append(avoider.step((box(**spec), *others), now, now))
    return answers


def test_a_clear_road_changes_nothing():
    assert Avoider().step((), 0.0, 0.0) == CLEAR
    assert Avoider().step((NEXT_LANE, FAR_AWAY), 0.0, 0.0) == CLEAR


def test_a_car_that_comes_closer_pushes_to_the_other_side_and_lifts_the_pedal():
    around = approach(centre=0.52, bottom=0.55, height=0.08)
    assert around.steer < 0 and around.pedal < 1
    mirrored = approach(centre=0.48, bottom=0.55, height=0.08)
    assert mirrored.steer == -around.steer


def test_the_closer_the_harder_the_push_but_a_short_contact_time_brakes_at_both_distances():
    far = approach(centre=0.5, bottom=0.5, height=0.05)
    close = approach(centre=0.5, bottom=0.6, height=0.14)
    assert abs(close.steer) > abs(far.steer) > 0
    assert close.pedal == far.pedal == 0
    assert close.brake == far.brake == 1


def test_the_side_is_kept_while_the_thing_is_in_the_way():
    avoider = Avoider()
    first = approach(avoider, centre=0.52, bottom=0.55, height=0.08)
    # Mid-swerve the car ahead has moved across the picture's middle; the push must not flip.
    second = avoider.step((box(0.47, 0.55, 0.09),), 1.2, 1.2)
    assert first.steer < 0 and second.steer < 0
    later = approach(avoider, t0=1.2 + HOLD + 0.5, centre=0.47, bottom=0.55, height=0.09)
    assert later.steer > 0


def test_a_taken_lane_sends_the_push_to_the_other_side_and_two_keep_the_car_behind():
    left_taken = box(0.34, 0.6, 0.09)
    around = approach(None, left_taken, centre=0.48, bottom=0.55, height=0.08)
    assert around.steer > 0  # away from the centre would be right anyway
    around = approach(None, left_taken, centre=0.52, bottom=0.55, height=0.08)
    assert around.steer > 0  # left is taken, so right although the car ahead sits a little right
    boxed_in = approach(None, left_taken, box(0.68, 0.6, 0.09), centre=0.52, bottom=0.55, height=0.08)
    assert boxed_in.steer == 0 and boxed_in.pedal < 1


def test_old_boxes_and_the_minimap_say_nothing():
    assert Avoider().step((AHEAD,), 0.0, STALE + 0.1) == CLEAR
    assert Avoider().step((AHEAD,), None, 0.0) == CLEAR
    minimap = Detection("car", (40, 590, 200, 700), 0.9)
    assert Avoider().step((minimap,), 0.0, 0.0) == CLEAR


def test_a_person_and_a_lorry_count_by_their_height():
    person = approach(centre=0.5, bottom=0.6, height=0.12, kind="person", aspect=0.4)
    assert person.pedal < 1
    lorry_next_lane = box(0.75, 0.6, 0.2, kind="truck", aspect=1.0)
    assert Avoider().step((lorry_next_lane,), 0.0, 0.0) == CLEAR


def test_a_car_that_keeps_its_size_ahead_is_followed_not_gone_round():
    far = keeping(centre=0.52, bottom=0.5, height=0.05)
    assert all(a.steer == 0 and a.pedal == 1 for a in far)  # far enough to ignore
    close = keeping(centre=0.52, bottom=0.6, height=0.12)
    assert all(a.steer == 0 for a in close)
    assert close[-1].pedal < 0.5  # the pedal is lifted so that the distance is kept
    assert close[-1].urgent  # and this close, straight ahead, it is braked for as before
    behind = keeping(centre=0.52, bottom=0.55, height=0.08)
    # At a distance the pedal is lifted and nothing else.
    assert all(a.steer == 0 and not a.urgent for a in behind) and behind[-1].pedal < 1
    # The same car straight away is not worth a push either: the first look says nothing of its speed.
    assert close[0].steer == 0


def test_a_thing_that_grows_in_the_picture_is_gone_round_as_before():
    standing = approach(centre=0.52, bottom=0.6, height=0.12, grow=1.6)
    assert standing.steer < 0 and standing.pedal < 0.5
    slow = approach(centre=0.52, bottom=0.6, height=0.12, grow=1.25)  # 25 percent in a second
    assert slow.steer < 0
    slower = approach(centre=0.52, bottom=0.6, height=0.12, grow=1.08)  # a lorry only a little slower
    assert slower.steer == 0 and slower.pedal < 1


def test_the_steadiness_holds_against_a_lost_frame_and_a_changed_label():
    names = ["car", "truck", "bus", "car", "truck", "truck", "bus", "car", "car", "truck"]
    # A car ahead that keeps its size is called a different thing in every other frame, and a frame is lost.
    avoider = Avoider()
    answers = []
    for tick, kind in enumerate(names):
        if tick == 4:
            continue  # the detector lost it for this frame
        now = tick * 0.15
        answers.append(avoider.step((box(0.52, 0.6, 0.12, kind=kind),), now, now))
    assert all(a.steer == 0 for a in answers)
    assert len(avoider.things) == 1  # the same thing throughout
    # And one that grows is still seen to grow through the same changes.
    avoider = Avoider()
    around = CLEAR
    for tick, kind in enumerate(names):
        if tick == 4:
            continue
        now = tick * 0.15
        size = 0.07 * 1.6 ** (now / 1.35)
        around = avoider.step((box(0.52, 0.6, size, kind=kind),), now, now)
    assert around.steer < 0
    assert len(avoider.things) == 1


def test_a_thing_lost_for_longer_starts_a_new_history():
    avoider = Avoider()
    keeping(avoider, centre=0.52, bottom=0.6, height=0.08)
    assert len(avoider.things) == 1
    avoider.step((box(0.52, 0.6, 0.12),), 3.0, 3.0)
    assert len(avoider.things) == 1 and len(avoider.things[0].heights) == 1


def test_a_vehicle_beside_the_car_is_not_pushed_away_from():
    # A lorry in the next lane, close and so big that its box covers half the picture: it has no say.
    lorry = Detection("truck", (0.0, 40.0, 440.0, 712.0), 0.9)
    avoider = Avoider()
    for tick in range(8):
        now = tick * 0.1
        grown = Detection("truck", (0.0, 40.0 - tick, 440.0 + 6 * tick, 712.0), 0.9)
        assert avoider.step((grown if tick else lorry,), now, now) == CLEAR


def test_a_stopped_queue_is_still_passed_on_the_bypass():
    avoider = Avoider()
    for tick in range(6):
        now = tick * 0.2
        around = avoider.step((box(0.52, 0.6, 0.12),), now, now, bypass=True)
    assert around.steer == -1.0  # the committed side, whatever the history says


def _replay():
    data = json.loads(FIXTURE.read_text())
    avoider = Avoider()
    for entry in data["boxes"]:
        objects = tuple(Detection(o["kind"], tuple(o["box"]), o["confidence"]) for o in entry["objects"])
        yield entry["t"], avoider.step(objects, entry["t"], entry["t"])


def test_the_recorded_drive_has_no_swerve_for_vehicles_driving_along_ahead_or_beside():
    # The avoider before this card pushed 0.3 to 0.45 on 130 of these ticks, for a lorry in the next lane,
    # a bus far ahead in the next lane and a lorry that drove beside the jeep, in every stretch.
    answers = list(_replay())
    assert len(answers) > 400
    assert max(abs(a.steer) for _, a in answers) <= 0.1


def test_the_recorded_drive_lifts_the_pedal_behind_the_lorry_that_is_followed():
    answers = {round(t, 1): a for t, a in _replay()}
    # 24.9 to 25.4 s: the cement lorry ahead of the jeep, a little left of the middle, drawing away.
    assert all(answers[t].pedal < 0.95 and answers[t].steer == 0 for t in (24.9, 25.1, 25.3))
