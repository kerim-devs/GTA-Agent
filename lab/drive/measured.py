"""The closed loop with the car as measured on 13 November; no console connection.

The planar simulator's car turns at once and as its speed and grip allow. The game's car turns by
77 degrees a second per unit of the stick past a dead zone of 0.29, and the turn shows on the map
between 0.2 and 0.7 s after the stick (yaw regressed on the stick of the last 1.2 s: Kerim's hand on
16 minutes of straights with a route, and three drives of the pilot). This loop keeps the lab's
reading of the route (points 6 px apart from 11 px on, each wandering by 1.2 px), asks the driver
as unevenly as the console does (two ticks of three 33 ms apart, the others 67 or 100), and drives
at the speeds of the country road. Its use: the short aim swings in it as it did at the console,
which the planar simulator never showed, so a change to the steering can be tried against that.

    pilot/.venv/bin/python lab/drive/measured.py
"""

import sys
from collections import deque
from dataclasses import replace
from math import cos, pi, radians, sin
from pathlib import Path
from random import Random

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pilot" / "src"))
from pilot.cli import drive_config
from pilot.drive import Driver
from simulate import RecordedNoise, configuration


class MeasuredCar(RecordedNoise):
    dead, gain, first, last = 0.29, 77.0, 0.2, 0.7

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sticks = deque()

    def _integrate(self, dt):
        if dt <= 0:
            return
        cfg, command = self.config, self.applied
        if command.brake > 0:
            pull = -(cfg.brake_acceleration if self.speed > 0 else cfg.acceleration) * command.brake
        else:
            pull = cfg.acceleration * command.throttle
        self.speed += (pull - cfg.drag * self.speed) * dt
        self.speed = max(-cfg.reverse_speed, min(cfg.top_speed, self.speed))
        past = max(0.0, abs(command.steer) - self.dead) * (1 if command.steer >= 0 else -1)
        self.sticks.append((self.time, dt, past))
        while self.sticks[0][0] < self.time - self.last - 0.1:
            self.sticks.popleft()
        area = sum(d * v for t, d, v in self.sticks if self.time - self.last <= t < self.time - self.first)
        rolling = min(1.0, abs(self.speed) / 3.0) * (1 if self.speed >= 0 else -1)
        yaw = radians(self.gain * area / (self.last - self.first)) * rolling * dt
        x = self.x + self.speed * sin(self.heading + yaw / 2) * dt
        y = self.y + self.speed * cos(self.heading + yaw / 2) * dt
        if self._hits_wall(x, y):
            self.speed = 0.0
            self.collisions += 1
        else:
            self.x, self.y = x, y
            self.heading = (self.heading + yaw + pi) % (2 * pi) - pi
        delta = (self.heading - self.camera_heading + pi) % (2 * pi) - pi
        self.camera_heading += delta * dt / max(dt + cfg.camera_lag, 1e-9)


class Uneven:
    """A driver asked as the console asks it; between two ticks the pad keeps what it was sent."""

    def __init__(self, driver, seed):
        self.driver, self.rng, self.next, self.last = driver, Random(seed), 0.0, None

    def step(self, reading, t, moving, speed=None):
        if self.last is None or t >= self.next - 1e-9:
            self.last = self.driver.step(reading, t, moving, speed=speed)
            self.next = t + self.rng.choices((1 / 30, 2 / 30, 3 / 30), (0.70, 0.17, 0.13))[0]
        return self.last


def straight(config, seed, speed, *, scale=1.5, seconds=70, gain=77.0, first=0.2, last=0.7):
    """Spread of the true heading in degrees and furthest metres from the route, after ten seconds."""
    world = configuration(
        delay=0.06,
        sensor_delay=0.06,
        map_scale=scale,
        top_speed=speed,
        max_time=seconds,
        grip=50.0,
        drag=0.05,
        acceleration=6.0,
    )
    sim = MeasuredCar(((0, 0), (0, 4000)), config=world, seed=seed)
    sim.gain, sim.first, sim.last, sim.unknown_speed = gain, first, last, True
    driver, track = Uneven(Driver(config), seed), []
    while sim.time < seconds:
        reading, moving = sim.observe()
        command = driver.step(reading, sim.time, moving, speed=sim.observed_speed)
        sim.advance(command)
        if sim.time > 10:
            track.append((sim.x, np.degrees(sim.heading), command.steer))
    track = np.array(track)
    return float(track[:, 1].std()), float(np.abs(track[:, 0]).max()), float(np.sqrt(np.mean(track[:, 2] ** 2)))


def winding(config, seed, speed, *, scale=1.5, seconds=70, gain=77.0, first=0.2, last=0.7):
    """A road of arcs of 80 m, 60 degrees to the left and to the right in turn.

    A car that follows it turns all the time, so the swing is what the heading does beside its own
    mean of the last two seconds, in degrees; with it the furthest metres from the road, the stick
    by root mean square, the changes of the stick's side a second and the share of ticks by aim.
    """
    from math import atan2, degrees

    points, x, y, course = [(0.0, 0.0)], 0.0, 0.0, 0.0
    for arc in range(40):
        for _ in range(17):
            course += (1 if arc % 2 else -1) * radians(60 / 17)
            x, y = x + 5 * sin(course), y + 5 * cos(course)
            points.append((x, y))
    world = configuration(
        delay=0.06,
        sensor_delay=0.06,
        map_scale=scale,
        top_speed=speed,
        max_time=seconds,
        grip=50.0,
        drag=0.05,
        acceleration=6.0,
    )
    sim = MeasuredCar(tuple(points), config=world, seed=seed)
    sim.gain, sim.first, sim.last, sim.unknown_speed = gain, first, last, True
    inner = Driver(config)
    driver, track = Uneven(inner, seed), []
    while sim.time < seconds:
        reading, moving = sim.observe()
        command = driver.step(reading, sim.time, moving, speed=sim.observed_speed)
        sim.advance(command)
        if sim.time > 10:
            track.append((sim._route_position()[0], degrees(sim.heading), command.steer, inner.aim_px))
    track = np.array(track)
    heading = np.degrees(np.unwrap(np.radians(track[:, 1])))
    window = int(2 / world.dt)
    mean = np.convolve(heading, np.ones(window) / window, mode="valid")
    swing = heading[window // 2 : window // 2 + len(mean)] - mean
    sides = np.sign(track[:, 2][np.abs(track[:, 2]) >= 0.3])
    return (
        float(swing.std()),
        float(track[:, 0].max()),
        float(np.sqrt(np.mean(track[:, 2] ** 2))),
        float(np.sum(sides[1:] != sides[:-1]) / (seconds - 10)),
        float(np.mean(track[:, 3] < 10)),
        float(np.mean((track[:, 3] >= 10) & (track[:, 3] < 18))),
    )


def main():
    base = drive_config(["style=bold"])
    short = replace(base, straight_lookahead_px=base.lookahead_px, bend_lookahead_px=base.lookahead_px)
    laws = {
        "short aim": replace(short, yaw_memory=0.0),
        "short aim, turn minded": short,
        "middle aim, turn minded": replace(base, straight_lookahead_px=base.lookahead_px),
        "far aim": replace(base, yaw_memory=0.0),
        "far aim, turn minded": base,
    }
    print(
        "a winding road, four seeds: swing of the heading in degrees (worst) | furthest from the road in metres |"
        " stick rms | changes of side a second | ticks at 8 px | at the middle aim"
    )
    before = replace(base, bend_lookahead_px=base.lookahead_px)
    for speed in (8.0, 12.0, 16.0):
        for name, config in (("the aims of before", before), ("the aims as they are", base)):
            runs = [winding(config, seed, speed) for seed in range(4)]
            sd, off, rms, flips, short_share, middle = (np.array(c) for c in zip(*runs, strict=True))
            print(
                f"  {speed:4.0f} m/s  {name:22s} {sd.mean():5.1f} ({sd.max():5.1f}) | {off.mean():4.1f} ({off.max():4.1f}) |"
                f" {rms.mean():.2f} | {flips.mean():.2f} | {100 * short_share.mean():3.0f}% | {100 * middle.mean():3.0f}%"
            )
    cars = {
        "as measured": {},
        "turns half as much again": {"gain": 115.0},
        "turns half as much": {"gain": 40.0},
        "answers later, 0.35 to 0.95 s": {"first": 0.35, "last": 0.95},
        "map of 1 m to the pixel": {"scale": 1.0},
    }
    print("a straight, four seeds: spread of the heading in degrees (worst) | furthest from the route in metres | stick rms")
    for car, changed in cars.items():
        for speed in (8.0, 12.0, 16.0) if not changed else (14.0,):
            for name, config in laws.items():
                runs = [straight(config, seed, speed, **changed) for seed in range(4)]
                sd, off, rms = (np.array(column) for column in zip(*runs, strict=True))
                print(
                    f"  {car:30s} {speed:4.0f} m/s  {name:24s} {sd.mean():5.1f} ({sd.max():5.1f}) |"
                    f" {off.mean():4.1f} ({off.max():4.1f}) | {rms.mean():.2f}"
                )


if __name__ == "__main__":
    main()
