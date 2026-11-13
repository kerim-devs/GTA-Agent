import runpy
from dataclasses import replace

from pilot.contract import Command, Observation
from pilot.gps import Speedometer
from pilot.sim import SimConfig, Simulator
from pilot.skills import DriveRoute

helpers = runpy.run_path("pilot/tests/test_drive_queue.py")
box = helpers["box"]
world = helpers["world"]


def parked(start):
    sim = world(start=start, seconds=15)
    sim.walls = (((-0.9, 8.0), (0.9, 8.0)),)
    skill = DriveRoute({"duration": 120, "style": "bold"})
    first_stationary = passed = None
    result = None
    while sim.time < 15:
        reading, moving = sim.observe()
        result = skill.step(
            Observation(
                reading, moving, sim.time, objects=box(sim, 8.0), objects_time=sim.time
            )
        )
        if first_stationary is None and moving is False:
            first_stationary = sim.time
        if passed is None and sim.y > 10.0:
            passed = sim.time
        sim.advance(
            Command(
                result.pad.left[0],
                result.pad.r2,
                result.pad.l2,
                skill.driver._last.state,
            )
        )
        if result.status != "running" and passed is not None:
            break
    print(
        "PARKED",
        {
            "start": start,
            "elapsed": sim.time,
            "passed_at": passed,
            "first_stationary": first_stationary,
            "stationary_to_pass": None
            if first_stationary is None or passed is None
            else passed - first_stationary,
            "y": sim.y,
            "x": sim.x,
            "speed": sim.speed,
            "collisions": sim.collisions,
            "result": (result.status, result.reason),
        },
    )


def arrival():
    cfg = SimConfig(
        noise_degrees=0,
        noise_tail_probability=0,
        outlier_probability=0,
        damage_probability=0,
        path_noise=0,
        path_missing=0,
        speed_noise=0,
        speed_missing=0,
        gps_wrong=0,
        gps_dropout=0,
        max_time=60,
    )
    sim = Simulator([(0, 0), (0, 100)], config=cfg)
    skill = DriveRoute({"duration": 60, "style": "bold"})
    sim._speedometer = Speedometer(
        skill.driver.config.gps_window,
        skill.driver.config.gps_stale,
        skill.driver.config.gps_max_speed,
        skill.driver.config.gps_tolerance,
        skill.driver.config.gps_acceleration,
    )
    route_loss_at = terminal_at = None
    speed_terminal = None
    crossings = {0.5: None, 0.1: None, 0.01: None}
    min_speed = max_speed = 0.0
    result = None
    while sim.time < 60:
        reading, moving = sim.observe()
        if ((sim.x) ** 2 + (sim.y - 100) ** 2) ** 0.5 <= 3:
            if route_loss_at is None:
                route_loss_at = sim.time
            reading = replace(
                reading, route="none", bearing=None, far_bearing=None, path=()
            )
        result = skill.step(Observation(reading, moving, sim.time))
        if terminal_at is None and result.status != "running":
            terminal_at, speed_terminal = sim.time, sim.speed
        min_speed, max_speed = min(min_speed, sim.speed), max(max_speed, sim.speed)
        sim.advance(
            Command(
                result.pad.left[0],
                result.pad.r2,
                result.pad.l2,
                skill.driver._last.state,
            )
        )
        if route_loss_at is not None:
            for threshold, crossing in crossings.items():
                if crossing is None and abs(sim.speed) <= threshold:
                    crossings[threshold] = sim.time
        if (
            all(value is not None for value in crossings.values())
            and terminal_at is not None
        ):
            break
    print(
        "ARRIVAL",
        {
            "route_loss_at": route_loss_at,
            "terminal_at": terminal_at,
            "speed_terminal": speed_terminal,
            "crossings": crossings,
            "after_route_loss": {
                threshold: None if when is None else when - route_loss_at
                for threshold, when in crossings.items()
            },
            "min_speed": min_speed,
            "max_speed": max_speed,
            "position": (sim.x, sim.y),
            "destination_distance": ((sim.x) ** 2 + (sim.y - 100) ** 2) ** 0.5,
            "result": (result.status, result.reason),
            "neutral": result.pad.buttons == ()
            and result.pad.left == (0.0, 0.0)
            and result.pad.right == (0.0, 0.0)
            and result.pad.l2 == 0.0
            and result.pad.r2 == 0.0,
        },
    )


if __name__ == "__main__":
    parked(0.0)
    parked(7.0)
    arrival()
