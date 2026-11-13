"""get_away: driving off with stars lit, in a small world with a drawn minimap, and on recorded crops."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pytest

from pilot import terrain
from pilot.contract import Blip, Command, Detection, Hud, Observation, Pad, Reading
from pilot.getaway import GetAway
from pilot.minimap import ACX, ACY, MX0, MX1, MY0, MY1
from pilot.sim import SimConfig, Simulator

FIXTURES = Path(__file__).resolve().parents[2] / "lab" / "getaway" / "crops.npz"
DRIVING = {"left", "r2", "l2"}  # the only parts of the pad a drive may touch
TICK = 0.1


# ---------------------------------------------------------------- a world with a minimap
@dataclass
class Car:
    x: float
    y: float
    heading: float  # degrees clockwise from north
    speed: float

    def move(self, dt: float) -> None:
        self.x += self.speed * math.sin(math.radians(self.heading)) * dt
        self.y += self.speed * math.cos(math.radians(self.heading)) * dt

    def outline(self) -> tuple:
        # The car's box grown by half the own car, since the simulator sweeps only the own car's centre.
        h, (half_l, half_w) = math.radians(self.heading), (3.2, 1.9)
        fx, fy, rx, ry = math.sin(h), math.cos(h), math.cos(h), -math.sin(h)
        corners = [
            (self.x + a * half_l * fx + b * half_w * rx, self.y + a * half_l * fy + b * half_w * ry)
            for a, b in ((1, 1), (1, -1), (-1, -1), (-1, 1))
        ]
        return tuple((corners[i], corners[(i + 1) % 4]) for i in range(4))


@dataclass
class World:
    """Metres, x east and y north. Roads are polylines with a width, water and rocks polygons."""

    start: tuple[float, float] = (0.0, 0.0)
    heading: float = 0.0
    roads: list = field(default_factory=list)  # (points, width)
    water: list = field(default_factory=list)  # polygons
    walls: tuple = ()
    traffic: list = field(default_factory=list)  # Car
    police: list = field(default_factory=list)  # Car, chasing
    wanted_until: float = 1e9  # stars go out at this time
    seed: int = 0


def inside(polygon, x: float, y: float) -> bool:
    hit = False
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def edges(polygon) -> tuple:
    return tuple((polygon[i], polygon[(i + 1) % len(polygon)]) for i in range(len(polygon)))


def base_crop() -> np.ndarray:
    crop = np.full((170, 260, 3), 30, np.uint8)
    crop[MY0:MY1, MX0:MX1] = (104, 108, 104)  # land
    crop[146:150, 38:118] = (60, 165, 70)  # health
    crop[146:150, 128:164] = (60, 110, 200)  # armour
    crop[146:150, 174:210] = (205, 180, 40)  # special
    return crop


BASE = base_crop()


def render(world: World, x: float, y: float, camera: float, scale: float) -> np.ndarray:
    """The radar as the game draws it, flat: up is where the camera looks, `scale` metres a pixel."""
    crop = BASE.copy()
    c, s = math.cos(math.radians(camera)), math.sin(math.radians(camera))

    def px(point):
        dx, dy = point[0] - x, point[1] - y
        right, ahead = dx * c - dy * s, dx * s + dy * c
        return [round((ACX + right / scale) * 4), round((ACY - ahead / scale) * 4)]

    canvas = crop[MY0:MY1, MX0:MX1]
    view = crop.copy()
    for polygon in world.water:
        cv2.fillPoly(view, [np.array([px(p) for p in polygon], np.int32)], (226, 232, 236), cv2.LINE_AA, 2)
    for points, width in world.roads:
        line = np.array([px(p) for p in points], np.int32)
        thick = max(2, round(width / scale))
        cv2.polylines(view, [line], False, (238, 238, 238), thick, cv2.LINE_AA, 2)
    # The stream softens every edge; a crisp one on a 16 px border would pass for codec damage.
    canvas[:] = cv2.GaussianBlur(view, (5, 5), 1.2)[MY0:MY1, MX0:MX1]
    return crop


class Run:
    """One drive of `get_away` in a world, at the pilot's tick of a tenth of a second."""

    def __init__(
        self, world: World, minimap: str = "on", seconds: float = 60.0, car: SimConfig | None = None
    ):
        self.world = world
        config = car or SimConfig(damage_probability=0.0, outlier_probability=0.0)
        static = tuple(world.walls)
        self.static = static
        self.sim = Simulator(
            ((0.0, -1e5), (0.0, -1e5 + 1)),
            position=world.start,
            heading=world.heading,
            walls=static,
            config=config,
            seed=world.seed,
        )
        self.skill = GetAway({"duration": seconds + 30, "minimap": minimap})
        self.seconds = seconds
        self.rng = np.random.default_rng(world.seed)
        self.frame = np.zeros((720, 1280, 3), np.uint8)
        self.pads: list[Pad] = []
        self.results = []
        self.track: list[tuple[float, float, float]] = []  # time, x, y
        self.speeds: list[tuple[float, float]] = []
        self.in_water = False
        self.min_water = math.inf
        self.on_road = 0
        self.headings: list[str] = []

    def objects(self, now: float):
        sim, found = self.sim, []
        cam = self.sim.camera_heading
        for car in self.world.traffic:
            dx, dy = car.x - sim.x, car.y - sim.y
            ahead = dx * math.sin(cam) + dy * math.cos(cam) + 6.0  # the camera sits 6 m behind
            right = dx * math.cos(cam) - dy * math.sin(cam)
            if ahead < 3.0 or ahead > 60.0:
                continue
            focal = 0.24 * 6.0 / 1.8  # the own car, 1.8 m wide, fills 0.24 of the picture at 6 m
            wide = focal * 1.8 / ahead * 1280
            centre = 640 + focal * right / ahead * 1280
            if abs(centre - 640) > 700:
                continue
            high = wide / 1.25
            found.append(Detection("car", (centre - wide / 2, 380 - high, centre + wide / 2, 380), 0.8))
        return tuple(found), now - 0.25

    def blips(self, now: float, scale: float):
        out = []
        cam = self.sim.camera_heading
        for car in self.world.police:
            if int(now / 0.5) % 2:  # the police's markers flash
                continue
            dx, dy = car.x - self.sim.x, car.y - self.sim.y
            right = (dx * math.cos(cam) - dy * math.sin(cam)) / scale
            up = (dx * math.sin(cam) + dy * math.cos(cam)) / scale
            far = max(abs(right) / 88.0, up / 88.0, -up / 24.0, 1.0)  # far ones sit on the map's rim
            out.append(Blip("red", right / far, up / far, far > 1.0))
        return tuple(out)

    def go(self) -> Run:
        sim, now = self.sim, 0.0
        while now < self.seconds:
            for car in self.world.traffic:
                car.move(TICK)
            for car in self.world.police:
                # Chasers come on at 9 m/s and keep 25 m off.
                gap = math.hypot(sim.x - car.x, sim.y - car.y)
                car.heading = math.degrees(math.atan2(sim.x - car.x, sim.y - car.y))
                car.speed = 9.0 if gap > 25 else 0.0
                car.move(TICK)
            sim.walls = self.static + tuple(e for car in self.world.traffic for e in car.outline())
            scale = sim.map_scale
            camera = math.degrees(sim.camera_heading)
            arrow = math.degrees(sim.heading - sim.camera_heading) + self.rng.normal(0, 1.5)
            crop = render(self.world, sim.x, sim.y, camera, scale)
            self.frame[530:700, 30:290] = crop
            old = [s for t, s in self.speeds if t <= now - 0.2]
            speed = abs(old[-1]) if old else abs(sim.speed)
            moving = True if speed > 0.6 else False if speed < 0.3 else None
            objects, seen = self.objects(now)
            reading = Reading(
                "tilted",
                "none",
                None,
                None,
                (arrow + 180) % 360 - 180,
                False,
                0.9,
                blips=self.blips(now, scale),
            )
            hud = Hud(wanted=2 if now < self.world.wanted_until else 0)
            obs = Observation(
                reading,
                moving,
                now,
                frame=self.frame,
                objects=objects,
                objects_time=seen,
                hud=hud,
                mode="vehicle",
            )
            result = self.skill.step(obs)
            self.results.append(result)
            self.pads.append(result.pad)
            self.headings.append(self.skill.state)
            if result.status != "running":
                break
            pad = result.pad
            command = Command(pad.left[0], pad.r2, pad.l2, self.skill.state)
            for _ in range(3):
                sim.advance(command)
            now = round(now + TICK, 6)
            self.track.append((now, sim.x, sim.y))
            self.speeds.append((now, sim.speed))
            for polygon in self.world.water:
                self.in_water |= inside(polygon, sim.x, sim.y)
                self.min_water = min(self.min_water, distance_to(polygon, sim.x, sim.y))
            self.on_road += any(near_road(points, width, sim.x, sim.y) for points, width in self.world.roads)
        return self

    @property
    def held(self) -> float:
        """The longest stretch with the car standing, seconds."""
        longest = run = 0.0
        for _, speed in self.speeds:
            run = run + TICK if abs(speed) < 0.5 else 0.0
            longest = max(longest, run)
        return longest

    @property
    def travelled(self) -> float:
        return sum(math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in itertools.pairwise(self.track))

    @property
    def straight_line(self) -> float:
        return math.hypot(self.track[-1][1] - self.track[0][1], self.track[-1][2] - self.track[0][2])


def distance_to(polygon, x: float, y: float) -> float:
    if inside(polygon, x, y):
        return 0.0
    best = math.inf
    for (x0, y0), (x1, y1) in edges(polygon):
        dx, dy = x1 - x0, y1 - y0
        u = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / max(dx * dx + dy * dy, 1e-9)))
        best = min(best, math.hypot(x - x0 - u * dx, y - y0 - u * dy))
    return best


def near_road(points, width: float, x: float, y: float) -> bool:
    for (x0, y0), (x1, y1) in itertools.pairwise(points):
        dx, dy = x1 - x0, y1 - y0
        u = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / max(dx * dx + dy * dy, 1e-9)))
        if math.hypot(x - x0 - u * dx, y - y0 - u * dy) <= width / 2 + 1.0:
            return True
    return False


def open_ground(seed: int = 0) -> World:
    rng = np.random.default_rng(seed)
    rocks = []
    for _ in range(60):
        cx, cy = rng.uniform(-500, 500), rng.uniform(20, 900)
        rocks += edges(
            [(cx - 1.5, cy - 1.5), (cx + 1.5, cy - 1.5), (cx + 1.5, cy + 1.5), (cx - 1.5, cy + 1.5)]
        )
    return World(
        walls=tuple(rocks), police=[Car(-10.0, -60.0, 0.0, 0.0), Car(15.0, -70.0, 0.0, 0.0)], seed=seed
    )


def road_with_traffic(seed: int = 0) -> World:
    """A town street north with cross streets every 150 m, houses beside it, traffic both ways."""
    roads = [([(0.0, -100.0), (0.0, 1500.0)], 12.0)]
    walls = []
    for k in range(10):
        y0 = -100.0 + 150.0 * k
        roads.append(([(-300.0, y0 + 75.0), (300.0, y0 + 75.0)], 10.0))
        for side in (-1, 1):
            # A block from y0 to the cross street, its front 7 m off the middle of the street.
            walls += edges(
                [(side * 7.5, y0 + 6), (side * 140, y0 + 6), (side * 140, y0 + 69), (side * 7.5, y0 + 69)]
            )
    traffic = [Car(3.0, 40.0 + 70.0 * k, 0.0, 6.0) for k in range(8)]
    traffic += [Car(-3.0, 120.0 + 90.0 * k, 180.0, 8.0) for k in range(8)]
    return World(start=(3.0, 0.0), roads=roads, walls=tuple(walls), traffic=traffic, seed=seed)


def towards_water(seed: int = 0) -> World:
    """Open ground running north into the sea 120 m off, the police behind: away from them is the water."""
    sea = [(-2000.0, 120.0), (2000.0, 120.0), (2000.0, 3000.0), (-2000.0, 3000.0)]
    return World(water=[sea], police=[Car(0.0, -60.0, 0.0, 0.0)], seed=seed)


# ---------------------------------------------------------------- the simulation
@pytest.mark.parametrize("make", [open_ground, road_with_traffic, towards_water])
def test_keeps_moving_for_a_minute_and_never_into_water(make):
    run = Run(make()).go()
    assert run.results[-1].status == "running", run.results[-1]
    assert len(run.speeds) >= 599
    assert run.held <= 5.0
    assert not run.in_water
    assert run.travelled > 300


@pytest.mark.parametrize("make", [open_ground, road_with_traffic])
def test_drives_with_the_minimap_readings_off(make):
    run = Run(make(), minimap="off").go()
    assert run.results[-1].status == "running", run.results[-1]
    assert run.held <= 5.0
    assert run.travelled > 300
    assert all(state.startswith(("drive-straight", "recovery")) for state in run.headings)


def test_turns_away_from_water_before_reaching_it():
    run = Run(towards_water(), seconds=30).go()
    assert not run.in_water
    assert 10.0 < run.min_water < 80.0  # it went towards the sea, away from the police, and turned off
    assert any(state == "drive-water" for state in run.headings)


def test_along_the_road_through_traffic():
    run = Run(road_with_traffic()).go()
    assert run.on_road / len(run.speeds) > 0.9
    assert run.track[-1][2] > 300  # on up the street, past the traffic


def test_only_the_driving_parts_of_the_pad_and_from_the_first_tick():
    for make in (open_ground, road_with_traffic, towards_water):
        run = Run(make(), seconds=20).go()
        assert run.pads[0].r2 > 0.5
        for pad in run.pads:
            assert pad.buttons == ()
            assert pad.right == (0.0, 0.0)
            assert pad.left[1] == 0.0


# ---------------------------------------------------------------- the ends
def observation(t: float, wanted=2, screen="game", mode="vehicle", frame=None, arrow=0.0, moving=True):
    reading = Reading("tilted", "none", None, None, arrow, False, 0.9)
    return Observation(reading, moving, t, frame=frame, hud=Hud(wanted=wanted, screen=screen), mode=mode)


def drive(skill, ticks, **kw):
    t0 = skill.last_time + TICK if skill.last_time is not None else 0.0
    out = []
    for k in range(ticks):
        out.append(skill.step(observation(round(t0 + k * TICK, 6), **kw)))
        if out[-1].status != "running":
            break
    return out


def test_done_only_after_three_seconds_without_a_star():
    skill = GetAway({})
    drive(skill, 20)
    results = drive(skill, 40, wanted=0)
    first_done = next(i for i, r in enumerate(results) if r.status == "done")
    assert 30 <= first_done <= 31  # three seconds after the first tick that read no star
    assert results[first_done].reason == "stars-gone"
    assert results[first_done].pad == Pad()


def test_a_star_or_an_unread_row_in_between_does_not_finish():
    skill = GetAway({})
    drive(skill, 5)
    drive(skill, 20, wanted=0)
    drive(skill, 1, wanted=1)  # relit
    drive(skill, 20, wanted=0)
    assert skill.finished is None
    drive(skill, 10, wanted=None)  # unread rows neither clear nor relight
    assert skill.finished is None
    results = drive(skill, 40, wanted=0)
    assert results[-1].status == "done"


@pytest.mark.parametrize(
    ("kw", "ticks", "reason"),
    [
        ({"mode": "foot"}, 20, "on-foot"),
        ({"screen": "wasted"}, 10, "wasted"),
        ({"screen": "busted"}, 10, "busted"),
        ({"screen": "map"}, 15, "screen-map"),
    ],
)
def test_each_failure_with_its_reason_and_a_neutral_pad(kw, ticks, reason):
    skill = GetAway({})
    drive(skill, 10)
    results = drive(skill, ticks, **kw)
    assert results[-1].status == "failed"
    assert results[-1].reason == reason
    assert results[-1].pad == Pad()
    assert all(r.pad.r2 == 0.0 for r in results)  # nothing pressed on foot or under a screen


def test_no_hud_reading_at_all_fails_after_two_seconds():
    skill = GetAway({})
    drive(skill, 10)
    reading = Reading("tilted", "none", None, None, 0.0, False, 0.9)
    results = [skill.step(Observation(reading, True, 1.0 + k * TICK, mode="vehicle")) for k in range(25)]
    assert results[18].status == "running"
    assert results[-1].reason == "no-hud; the stars cannot be read"
    assert results[-1].pad == Pad()


def test_one_odd_tick_decides_nothing():
    skill = GetAway({})
    drive(skill, 10)
    for kw in ({"mode": "foot"}, {"screen": "wasted"}, {"screen": "map"}):
        drive(skill, 2, **kw)
        drive(skill, 3)
    assert skill.finished is None


def test_time_limit():
    skill = GetAway({"duration": 10})
    results = drive(skill, 120)
    assert results[-1].status == "failed"
    assert results[-1].reason == "time-limit; stars still lit"
    assert results[-1].pad == Pad()
    assert 99 <= len(results) <= 101


def test_a_held_car_fails_after_the_drivers_recoveries():
    skill = GetAway({})
    results = drive(skill, 400, moving=False)
    assert results[-1].status == "failed"
    assert results[-1].reason == "vehicle-held"
    assert results[-1].pad == Pad()
    assert any(r.pad.l2 > 0 for r in results)  # it backed off before giving the car up


def test_water_under_the_car():
    world = World(water=[[(-50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0)]])
    frame = np.zeros((720, 1280, 3), np.uint8)
    frame[530:700, 30:290] = render(world, 0.0, 0.0, 0.0, 1.0)
    skill = GetAway({})
    results = drive(skill, 20, frame=frame)
    assert results[-1].reason == "water"
    assert results[-1].pad == Pad()


def test_stop_and_arguments():
    skill = GetAway({"duration": 1000, "minimap": "off"})
    assert skill.limit == 300 and not skill.use_minimap
    drive(skill, 5)
    assert skill.stop("replaced").pad == Pad()
    assert skill.step(observation(10.0)).status == "failed"
    for bad in ({"duration": "x"}, {"duration": math.nan}, {"minimap": "maybe"}, {"route": 1}, []):
        with pytest.raises(ValueError):
            GetAway(bad)
    assert len(GetAway.prompt) <= 400


# ---------------------------------------------------------------- on recorded crops
def recorded():
    if not FIXTURES.exists():
        pytest.skip("lab/getaway/crops.npz is missing")
    return np.load(FIXTURES)


def test_turns_off_where_the_recorded_map_shows_water_ahead():
    data = recorded()
    for crop, name in zip(data["water_ahead"], data["water_ahead_names"], strict=True):
        frame = np.zeros((720, 1280, 3), np.uint8)
        frame[530:700, 30:290] = crop
        skill = GetAway({})
        drive(skill, 3, frame=frame)
        land = terrain.read(crop)
        assert land is not None, name
        assert land.water_within(0.0, GetAway.WATER_SPREAD, GetAway.WATER_NEAR) is not None, name
        assert land.water_within(skill.heading, GetAway.WATER_SPREAD, GetAway.WATER_NEAR) is None, name


def test_the_recorded_road_readings():
    data = recorded()
    for crop, label, name in zip(data["roads"], data["road_labels"], data["road_names"], strict=True):
        land = terrain.read(crop)
        assert land is not None, name
        exits = land.exits
        for side, truth in zip(("ahead", "left", "right"), label, strict=True):
            if truth >= 0:
                assert exits[side] == bool(truth), (name, side)


def test_water_on_foot_and_none_at_a_crossing():
    data = recorded()
    for crop, name in zip(data["foot_water"], data["foot_water_names"], strict=True):
        mask = terrain.water_mask(crop, on_foot=True)
        assert mask is not None and mask.mean() > 0.2, name
        cells = terrain.water_cells(crop)
        assert cells.shape == (38, 60) and cells.any(), name
    for crop, name in zip(data["foot_dry"], data["foot_dry_names"], strict=True):
        mask = terrain.water_mask(crop, on_foot=True)
        assert mask is not None and not mask.any(), name
    assert terrain.water_mask(np.zeros((170, 260, 3), np.uint8)) is None
    assert terrain.water_mask(np.zeros((10, 10), np.uint8)) is None
