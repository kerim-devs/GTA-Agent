"""P78 closed-loop worlds. Distances are simulator metres, marker gaps are pixels."""

import itertools
import math
from dataclasses import replace
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from test_getaway import TICK, Car, Run, World, inside, render

from pilot.contract import Blip, Command, Hud, Observation, Reading
from pilot.pursuit import DriveToBlip
from pilot.sim import CAR_PROFILES, SimConfig, Simulator


@pytest.fixture(scope="module", autouse=True)
def bounded_opencv_threads():
    previous = cv2.getNumThreads()
    cv2.setNumThreads(1)
    yield
    cv2.setNumThreads(previous)


def path_position(points, progress):
    for start, end in itertools.pairwise(points):
        length = math.dist(start, end)
        if progress <= length:
            f = progress / length
            return (
                start[0] + f * (end[0] - start[0]),
                start[1] + f * (end[1] - start[1]),
                math.degrees(math.atan2(end[0] - start[0], end[1] - start[1])),
            )
        progress -= length
    return (*points[-1], 0.0)


def path_progress(points, x, y):
    best, along, walked = float("inf"), 0.0, 0.0
    for start, end in itertools.pairwise(points):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        u = max(0.0, min(1.0, ((x - start[0]) * dx + (y - start[1]) * dy) / length**2))
        distance = math.hypot(x - start[0] - u * dx, y - start[1] - u * dy)
        if distance < best:
            best, along = distance, walked + u * length
        walked += length
    return along


def run_world(mode, profile="nominal", *, water=False, held=False, traffic=False, seconds=60.0):
    config = replace(SimConfig(damage_probability=0, outlier_probability=0), **CAR_PROFILES[profile])
    points = [(0.0, 0.0), (0.0, 120.0), (70.0, 120.0), (70.0, 700.0)]
    if mode == "reach":
        points = [(0.0, 0.0), (0.0, 300.0)]
    # Match the existing P68 main-road width; wider junctions are retained
    # separately as a terrain-classification negative receipt.
    world = World(roads=[(points, 12.0)])
    if mode == "reach":
        world.roads += [([(-150.0, y), (150.0, y)], 12.0) for y in (100.0, 200.0)]
    else:
        world.roads += [
            ([(0.0, -100.0), (0.0, 500.0)], 12.0),
            ([(-150.0, 120.0), (200.0, 120.0)], 12.0),
            ([(70.0, -100.0), (70.0, 500.0)], 12.0),
        ]
    if water:
        world.water = [[(-70, 60), (40, 60), (40, 100), (-70, 100)]]
        world.roads = []
    if held:
        world.walls = (((-12.0, 12.0), (12.0, 12.0)),)
    if traffic:
        world.traffic = [Car(-3.5, 45.0, 0.0, 2.0)]
    sim = Simulator(
        ((0, -1e5), (0, -1e5 + 1)),
        position=world.start,
        heading=world.heading,
        walls=world.walls,
        config=config,
        seed=7,
    )
    skill = DriveToBlip({"color": "blue", "mode": mode, "duration": seconds + 1})
    frame = np.zeros((720, 1280, 3), np.uint8)
    progress = 19.0 if mode == "follow" else 60.0
    target = Car(0.0, progress, 0.0, 0.0)
    rows = []
    first_catch = None
    passed = False
    wet = False
    longest_held = held_time = 0.0
    no_buttons = True
    result = None
    for tick in range(round(seconds / TICK)):
        now = tick * TICK
        for car in world.traffic:
            car.move(TICK)
        sim.walls = world.walls + tuple(edge for car in world.traffic for edge in car.outline())
        if mode == "reach":
            target.x, target.y = points[-1]
        else:
            # The target turns twice and pauses twice. The fleeing car is matchable by every profile.
            target.speed = min(4.0 if mode == "follow" else 4.5, config.top_speed * 0.55)
            if mode == "follow" and (35 <= now < 40 or 52 <= now < 56):
                target.speed = 0.0
            progress += target.speed * TICK
            target.x, target.y, target.heading = path_position(points, progress)
        scale, cam = sim.map_scale, sim.camera_heading
        dx, dy = target.x - sim.x, target.y - sim.y
        right, up = (
            (dx * math.cos(cam) - dy * math.sin(cam)) / scale,
            (dx * math.sin(cam) + dy * math.cos(cam)) / scale,
        )
        far = max(abs(right) / 88.0, up / 88.0, -up / 24.0, 1.0)
        blip = Blip("blue", right / far, up / far, far > 1.0)
        crop = render(world, sim.x, sim.y, math.degrees(cam), scale)
        # Draw the target too; geometric blips are supplied as in test_getaway.Run.
        cv2.circle(crop, (round(130 + blip.x), round(120 - blip.y)), 3, (255, 100, 20), -1)
        frame[530:700, 30:290] = crop
        arrow = (math.degrees(sim.heading - cam) + 180) % 360 - 180
        reading = Reading("tilted", "none", None, None, arrow, False, 0.9, blips=(blip,))
        speed = abs(sim.speed)
        objects, seen = Run.objects(SimpleNamespace(sim=sim, world=world), now)
        result = skill.step(
            Observation(
                reading,
                True if speed > 0.6 else False if speed < 0.3 else None,
                now,
                frame=frame,
                objects=objects,
                objects_time=seen,
                hud=Hud(),
                mode="vehicle",
            )
        )
        gap = math.hypot(dx, dy)
        pixel_gap = math.hypot(right, up)
        passed |= mode == "follow" and path_progress(points, sim.x, sim.y) > progress
        wet |= any(inside(p, sim.x, sim.y) for p in world.water)
        if mode == "catch" and gap <= 10 and first_catch is None:
            first_catch = now
        # Count every stationary interval, including brakes, recovery and intentional waiting.
        held_time = held_time + TICK if speed < 0.5 else 0.0
        longest_held = max(longest_held, held_time)
        no_buttons &= not result.pad.buttons and result.pad.right == (0.0, 0.0)
        rows.append(
            {
                "t": now,
                "gap_m": gap,
                "gap_px": pixel_gap,
                "x": sim.x,
                "y": sim.y,
                "target_x": target.x,
                "target_y": target.y,
                "speed": sim.speed,
                "pedal": result.pad.r2,
                "brake": result.pad.l2,
                "state": skill.state,
            }
        )
        if result.status != "running":
            break
        command = Command(result.pad.left[0], result.pad.r2, result.pad.l2, skill.state)
        for _ in range(3):
            sim.advance(command)
    low, high = skill.FOLLOW_BAND
    return {
        "mode": mode,
        "profile": profile,
        "seconds": rows[-1]["t"],
        "follow_share": sum(low <= r["gap_px"] <= high for r in rows) / len(rows),
        "passed": passed,
        "lost": result.reason == "blip-gone",
        "catch_time": first_catch,
        "close_share": sum(r["gap_m"] <= 10 for r in rows) / len(rows),
        "final_gap": rows[-1]["gap_m"],
        "final_speed": sim.speed,
        "end": result.status,
        "reason": result.reason,
        "water": wet,
        "held": longest_held,
        "no_buttons": no_buttons,
        "junctions_crossed": sum(any(row["y"] >= y for row in rows) for y in (100.0, 200.0))
        if mode == "reach"
        else None,
        "rows": rows,
    }


@pytest.mark.parametrize("mode", ("follow", "catch", "reach"))
def test_pursuit_profile(mode):
    assert_world(run_world(mode))


def assert_world(result):
    """Shared acceptance checks; the lab runner applies these to EVERY car profile."""
    mode = result["mode"]
    assert result["no_buttons"]
    assert not result["water"]
    assert result["held"] <= 5.0
    if mode == "follow":
        assert result["follow_share"] >= 0.8, result
        assert not result["passed"], result
        assert not result["lost"], result
    elif mode == "catch":
        assert result["catch_time"] is not None and result["catch_time"] <= 40, result
    else:
        assert result["end"] == "done" and result["reason"] == "reached", result
        assert result["final_gap"] <= 15, result
        assert abs(result["final_speed"]) < 0.5, result
        assert result["junctions_crossed"] == 2, result


def test_pursuit_water_and_wall():
    for settings in ({"water": True}, {"held": True}, {"traffic": True}):
        result = run_world("catch", seconds=30, **settings)
        assert not result["water"]
        assert result["held"] <= 5
        assert result["no_buttons"]
