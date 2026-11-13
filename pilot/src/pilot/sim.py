"""Seeded planar bicycle simulator, deliberately independent of image processing.

Coordinates are metres (x right/east, y up/north), headings clockwise radians from
north. Map scale is metres per pixel. Route readings use the contract's 30/60 pixel
rings; they are not privileged cross-track errors. Brake decelerates forward motion
before reversing. Walls are zero-thickness segments swept by the vehicle centre.
This model cannot establish real-game handling or perception accuracy.
"""

from collections import deque
from dataclasses import dataclass, replace
from math import atan2, cos, degrees, hypot, isfinite, radians, sin, sqrt, tan
from random import Random

from pilot.contract import NEUTRAL, Command, Reading
from pilot.drive import Driver
from pilot.gps import Fix, Speedometer
from pilot.motion import motion_state

Point = tuple[float, float]
Wall = tuple[Point, Point]


@dataclass(frozen=True)
class SimConfig:
    dt: float = 1 / 30
    delay: float = 0.21
    map_scale: float = 1.0
    gps_interval: float = 0.25
    gps_delay: float = 0.15
    gps_wrong: float = 0.30
    gps_dropout: float = 2.0  # Missing readout at the start of each twelve-second interval.
    scale_with_speed: float = 1.0
    dead_zone: float = 0.0
    wheelbase: float = 2.7
    max_wheel_angle: float = 35.0
    acceleration: float = 4.5
    drag: float = 0.45
    top_speed: float = 12.0
    reverse_speed: float = 3.0
    brake_acceleration: float = 8.0
    grip: float = 4.0  # Maximum lateral acceleration in m/s^2.
    sensor_delay: float = 0.06  # Part of the total capture-to-command delay.
    speed_window: float = 0.2
    speed_noise: float = 0.5  # Pixels/s, with an additional rotation component.
    speed_missing: float = 0.08
    path_noise: float = 0.25  # Pixels, shared offset plus per-sample noise.
    path_missing: float = 0.03
    path_hidden: float = 11.0  # Arrow occlusion radius in pixels.
    camera_lag: float = 0.3
    noise_degrees: float = 3.0
    noise_tail_multiplier: float = 16 / 3
    noise_tail_probability: float = 0.15
    outlier_probability: float = 0.01
    damage_probability: float = 0.05
    arrival_radius: float = 3.0
    progress_distance: float = 0.5
    max_time: float = 600.0

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        for name in (
            "dt",
            "map_scale",
            "wheelbase",
            "top_speed",
            "arrival_radius",
            "max_time",
            "speed_window",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.dead_zone >= 1 or self.max_wheel_angle >= 89:
            raise ValueError("invalid steering geometry")
        if (
            max(
                self.outlier_probability,
                self.damage_probability,
                self.noise_tail_probability,
                self.speed_missing,
                self.gps_wrong,
                self.path_missing,
            )
            > 1
        ):
            raise ValueError("probabilities must be at most one")


@dataclass(frozen=True)
class SimResult:
    reached: bool
    elapsed: float
    mean_distance: float
    max_distance: float
    max_no_progress: float
    steering_flips_per_second: float
    recoveries: int
    collisions: int
    max_overspeed_time: float
    max_bend_speed: float
    max_speed: float
    final_position: Point


class Simulator:
    """A reusable in-memory world; run one Driver on a fresh instance per trial."""

    def __init__(
        self,
        route: tuple[Point, ...] | list[Point],
        *,
        position: Point | None = None,
        heading: float = 0.0,
        walls: tuple[Wall, ...] = (),
        config: SimConfig | None = None,
        seed: int = 0,
    ) -> None:
        self.config = config or SimConfig()
        if len(route) < 2 or any(not all(isfinite(v) for v in point) for point in route):
            raise ValueError("route needs at least two finite points")
        self.route = tuple(route)
        self._segments = []
        total = 0.0
        for a, b in zip(self.route, self.route[1:], strict=False):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = hypot(dx, dy)
            if length == 0:
                raise ValueError("adjacent route points must differ")
            self._segments.append((a[0], a[1], dx, dy, length, total))
            total += length
        self.length = total
        self.x, self.y = self.route[0] if position is None else position
        if not all(isfinite(v) for v in (self.x, self.y, heading)):
            raise ValueError("pose must be finite")
        if any(not all(isfinite(v) for point in wall for v in point) for wall in walls):
            raise ValueError("walls must be finite")
        self.heading = radians(heading)
        self.camera_heading = self.heading
        self.walls = walls
        self.speed = 0.0
        self.time = 0.0
        self.applied = NEUTRAL
        self._queue: deque[tuple[float, Command]] = deque()
        self._rng = Random(seed)
        self._sensor_rng = Random(seed + 10000)
        self._poses = deque()
        self._observations = deque()
        self.observed_speed = None
        self._gps_rng = Random(seed + 20000)
        self._gps_queue = deque()
        self._gps_at = -float("inf")
        self._gps_fix = None
        self._gps_sample_time = None
        self._speedometer = None
        self._segment = 0
        self.collisions = 0
        self._recoveries = 0
        self._last_state = "idle"

    def _projection(self, index: int) -> tuple[float, float]:
        ax, ay, dx, dy, length, start = self._segments[index]
        u = max(0.0, min(1.0, ((self.x - ax) * dx + (self.y - ay) * dy) / (length * length)))
        return hypot(self.x - ax - u * dx, self.y - ay - u * dy), start + u * length

    def _route_position(self) -> tuple[float, float]:
        # Recalculate from the actual nearest polyline point. Prefer the current
        # segment on exact ties, so a closed loop does not jump to its end at start.
        projections = [self._projection(i) for i in range(len(self._segments))]
        self._segment = min(
            range(len(projections)), key=lambda i: (round(projections[i][0], 9), abs(i - self._segment))
        )
        return projections[self._segment]

    def _target(self, radius: float) -> Point:
        # First forward intersection of the route with a reader sampling ring.
        distance, progress = self._route_position()
        if distance > radius:
            ax, ay, dx, dy, length, start = self._segments[self._segment]
            u = (progress - start) / length
            return ax + u * dx, ay + u * dy
        for index in range(self._segment, len(self._segments)):
            ax, ay, dx, dy, length, start = self._segments[index]
            ox, oy = ax - self.x, ay - self.y
            b = 2 * (ox * dx + oy * dy)
            c = ox * ox + oy * oy - radius * radius
            discriminant = b * b - 4 * length * length * c
            if discriminant < 0:
                continue
            root = sqrt(discriminant)
            for u in ((-b - root) / (2 * length * length), (-b + root) / (2 * length * length)):
                if 0 <= u <= 1 and start + u * length > progress + 1e-6:
                    return ax + u * dx, ay + u * dy
        return self.route[-1]

    @property
    def map_scale(self):
        speed = abs(self.speed)
        table = 0.7 if speed < 6 else 1.0 if speed < 12 else 2.1 if speed < 18 else 3.6 if speed < 24 else 3.7
        return self.config.map_scale * (table if self.config.scale_with_speed else 1.0)

    def _gps_reading(self):
        cfg = self.config
        if self.time - self._gps_at >= cfg.gps_interval:
            self._gps_at = self.time
            _, progress = self._route_position()
            remaining = max(0, self.length - progress)
            quantum = 10 if remaining >= 1000 else 1
            value = round(remaining / quantum) * quantum
            fix = None
            if self.time % 12 >= cfg.gps_dropout:
                if self._gps_rng.random() < cfg.gps_wrong:
                    value = max(0, value + self._gps_rng.choice((-200, -50, 30, 100, 1000)))
                fix = Fix(value, "straight", quantum)
            self._gps_queue.append((self.time + cfg.gps_delay, self.time, fix))
        result = None
        while self._gps_queue and self._gps_queue[0][0] <= self.time:
            _, sampled_at, fix = self._gps_queue.popleft()
            result = (sampled_at, fix)
        if self._speedometer is None:
            self._speedometer = Speedometer()
        at, fix = result if result is not None else (self.time, None)
        self.observed_speed = self._speedometer.update(self.time, fix, sampled_at=at)
        fresh = (
            self._speedometer.time is not None
            and self.time - self._speedometer.time <= self._speedometer.stale
        )
        self._gps_fix = self._speedometer.fix if fresh else None
        self._gps_sample_time = self._speedometer.time if fresh else None

    def observe(self) -> tuple[Reading, bool | None]:
        """Noisy picture-angle readings and an independent short motion estimate."""
        cfg = self.config
        scale = self.map_scale
        near, far = self._target(30 * scale), self._target(60 * scale)
        noise = self._rng.gauss
        bearing = degrees(atan2(near[0] - self.x, near[1] - self.y) - self.camera_heading)
        far_bearing = degrees(atan2(far[0] - self.x, far[1] - self.y) - self.camera_heading)
        arrow = degrees(self.heading - self.camera_heading)
        # A fixed heavy-tail mixture approximates the observed temporal jitter.
        sigma = cfg.noise_degrees * (
            cfg.noise_tail_multiplier if self._rng.random() < cfg.noise_tail_probability else 1
        )
        bearing += noise(0, sigma)
        far_bearing += noise(0, sigma)
        arrow += noise(0, cfg.noise_degrees * 0.5)
        if self._rng.random() < cfg.outlier_probability:
            bearing += self._rng.choice((-1, 1)) * self._rng.uniform(80, 170)
        damaged = self._rng.random() < cfg.damage_probability
        reading = Reading(
            minimap="tilted",
            route="none" if damaged else "yellow",
            bearing=None if damaged else (bearing + 180) % 360 - 180,
            far_bearing=None if damaged else (far_bearing + 180) % 360 - 180,
            arrow=None if damaged else (arrow + 180) % 360 - 180,
            corrupt=damaged,
            confidence=0.0 if damaged else 0.95,
            path=() if damaged else self._path_reading(),
        )
        self._poses.append((self.time, self.x, self.y, self.camera_heading))
        while len(self._poses) > 1 and self._poses[1][0] <= self.time - 1.2:
            self._poses.popleft()
        speed = None
        old_t, old_x, old_y, old_camera = min(
            self._poses, key=lambda p: abs(self.time - p[0] - cfg.speed_window)
        )
        elapsed = self.time - old_t
        if (
            elapsed >= cfg.speed_window * 0.75
            and not damaged
            and self._sensor_rng.random() >= cfg.speed_missing
        ):
            translation = hypot(self.x - old_x, self.y - old_y) / scale / elapsed
            rotation = (
                abs(
                    (self.camera_heading - old_camera + 3.141592653589793) % (2 * 3.141592653589793)
                    - 3.141592653589793
                )
                / elapsed
            )
            speed = max(0, translation + rotation * 2 + self._sensor_rng.gauss(0, cfg.speed_noise))
        moving = motion_state(None if speed is None else speed * cfg.speed_window)
        if moving is not True and speed is not None and self.time - self._poses[0][0] >= 0.8:
            _, x, y, _ = self._poses[0]
            moving = motion_state(
                max(
                    0,
                    hypot(self.x - x, self.y - y) / scale
                    + self._sensor_rng.gauss(0, cfg.speed_noise * cfg.speed_window),
                )
            )
        self._observations.append((self.time, reading, moving, speed))
        while len(self._observations) > 1 and self._observations[1][0] <= self.time - cfg.sensor_delay:
            self._observations.popleft()
        _, observed, moving, _ = self._observations[0]
        self._gps_reading()
        observed = replace(
            observed,
            gps_distance=None if self._gps_fix is None else self._gps_fix.distance,
            gps_arrow=None if self._gps_fix is None else self._gps_fix.arrow,
            gps_speed=self.observed_speed,
            gps_time=self._gps_sample_time,
        )
        return observed, moving

    def _path_reading(self):
        cfg = self.config
        rng = self._sensor_rng
        scale = self.map_scale
        if rng.random() < cfg.path_missing:
            return ()
        _, progress = self._route_position()
        path = []
        offset_x, offset_y = rng.gauss(0, cfg.path_noise), rng.gauss(0, cfg.path_noise)
        for ax, ay, dx, dy, length, start in self._segments[self._segment :]:
            travel = max(0, progress - start)
            samples = []
            while travel < length:
                samples.append(travel)
                travel += 3 * scale
            samples.append(length)
            for along in samples:
                rx = (ax + dx * along / length - self.x) / scale
                ry = (ay + dy * along / length - self.y) / scale
                x = rx * cos(self.camera_heading) - ry * sin(self.camera_heading)
                y = rx * sin(self.camera_heading) + ry * cos(self.camera_heading)
                if hypot(x, y) < cfg.path_hidden:
                    continue
                if abs(x) > 85 or y > 105 or y < -20:
                    return tuple(path)
                point = (
                    x + offset_x + rng.gauss(0, cfg.path_noise * 0.2),
                    y + offset_y + rng.gauss(0, cfg.path_noise * 0.2),
                )
                if not path or hypot(point[0] - path[-1][0], point[1] - path[-1][1]) >= 3 or along == length:
                    path.append(point)
        return tuple(path)

    @staticmethod
    def _cross(a: Point, b: Point) -> float:
        return a[0] * b[1] - a[1] * b[0]

    def _hits_wall(self, x: float, y: float) -> bool:
        travel = x - self.x, y - self.y
        for a, b in self.walls:
            edge = b[0] - a[0], b[1] - a[1]
            offset = a[0] - self.x, a[1] - self.y
            denominator = self._cross(travel, edge)
            if abs(denominator) < 1e-12:
                continue
            t = self._cross(offset, edge) / denominator
            u = self._cross(offset, travel) / denominator
            if 0 <= t <= 1 and 0 <= u <= 1:
                return True
        return False

    def _integrate(self, dt: float) -> None:
        if dt <= 0:
            return
        cfg, command = self.config, self.applied
        if command.brake > 0:
            acceleration = (
                -cfg.brake_acceleration * command.brake
                if self.speed > 0
                else -cfg.acceleration * command.brake
            )
        else:
            acceleration = cfg.acceleration * command.throttle
        self.speed += (acceleration - cfg.drag * self.speed) * dt
        self.speed = max(-cfg.reverse_speed, min(cfg.top_speed, self.speed))
        steer = max(0.0, abs(command.steer) - cfg.dead_zone) / (1 - cfg.dead_zone)
        steer = steer if command.steer >= 0 else -steer
        yaw_rate = self.speed / cfg.wheelbase * tan(radians(cfg.max_wheel_angle) * steer)
        grip_rate = cfg.grip / max(abs(self.speed), 0.01)
        yaw = max(-grip_rate, min(grip_rate, yaw_rate)) * dt
        x = self.x + self.speed * sin(self.heading + yaw / 2) * dt
        y = self.y + self.speed * cos(self.heading + yaw / 2) * dt
        if self._hits_wall(x, y):
            self.speed = 0.0
            self.collisions += 1
        else:
            self.x, self.y = x, y
            self.heading = (self.heading + yaw + 3.141592653589793) % (
                2 * 3.141592653589793
            ) - 3.141592653589793
        camera_delta = (self.heading - self.camera_heading + 3.141592653589793) % (
            2 * 3.141592653589793
        ) - 3.141592653589793
        self.camera_heading += camera_delta * dt / max(dt + cfg.camera_lag, 1e-9)

    def advance(self, command: Command) -> None:
        """Apply queued controls at exact timestamps, including fractional delays."""
        self._queue.append((self.time + max(0, self.config.delay - self.config.sensor_delay), command))
        if command.state == "recovery-reverse" and self._last_state != command.state:
            self._recoveries += 1
        if command.state != "coast":
            self._last_state = command.state
        end = self.time + self.config.dt
        while self._queue and self._queue[0][0] <= end + 1e-12:
            apply_at, next_command = self._queue.popleft()
            self._integrate(max(0.0, apply_at - self.time))
            self.time = max(self.time, apply_at)
            self.applied = next_command
        self._integrate(max(0.0, end - self.time))
        self.time = end

    def run(self, driver: Driver) -> SimResult:
        distance, progress = self._route_position()
        distances = []
        on_route = distance <= 1.0
        overspeed = max_overspeed = max_bend_speed = max_speed = 0.0
        self._speedometer = Speedometer(
            driver.config.gps_window,
            driver.config.gps_stale,
            driver.config.gps_max_speed,
            driver.config.gps_tolerance,
            driver.config.gps_acceleration,
        )
        best_progress, last_progress = progress, self.time
        max_gap = 0.0
        flips, last_sign = 0, 0
        reached = False
        while self.time < self.config.max_time:
            reading, moving = self.observe()
            command = driver.step(reading, self.time, moving, speed=self.observed_speed)
            sign = 1 if command.steer > 0 else -1 if command.steer < 0 else 0
            if sign:
                flips += int(last_sign != 0 and sign != last_sign)
                last_sign = sign
            previous_segment = self._segment
            self.advance(command)
            distance, progress = self._route_position()
            on_route = on_route or distance <= 1.0
            if on_route:
                distances.append(distance)
            max_speed = max(max_speed, self.speed)
            overspeed = overspeed + self.config.dt if self.speed > driver.config.speed_limit + 2 else 0.0
            max_overspeed = max(max_overspeed, overspeed)
            for index, vertex in enumerate(self.route[1:-1], start=1):
                if (self._segment <= index and hypot(self.x - vertex[0], self.y - vertex[1]) <= 5) or (
                    previous_segment < index <= self._segment
                ):
                    max_bend_speed = max(max_bend_speed, self.speed)
            if progress >= best_progress + self.config.progress_distance:
                max_gap = max(max_gap, self.time - last_progress)
                best_progress, last_progress = progress, self.time
            max_gap = max(max_gap, self.time - last_progress)
            if (
                self._segment == len(self._segments) - 1
                and hypot(self.x - self.route[-1][0], self.y - self.route[-1][1])
                <= self.config.arrival_radius
            ):
                reached = True
                break
        return SimResult(
            reached,
            self.time,
            sum(distances) / len(distances) if distances else distance,
            max(distances) if distances else distance,
            max_gap,
            flips / max(self.time, self.config.dt),
            self._recoveries,
            self.collisions,
            max_overspeed,
            max_bend_speed,
            max_speed,
            (self.x, self.y),
        )


# Pairwise three-level design: every pair of unknown car parameters spans its 3x3 grid.
CAR_PROFILES = {"nominal": {}}
for _i in range(3):
    for _j in range(3):
        CAR_PROFILES[f"range-{_i}{_j}"] = dict(
            grip=(2.0, 4.0, 7.0)[_i],
            acceleration=(3.0, 4.5, 7.0)[_j],
            brake_acceleration=(4.0, 8.0, 12.0)[(_i + _j) % 3],
            top_speed=(8.0, 12.0, 18.0)[(_i + 2 * _j) % 3],
        )

# The joint fast-car/weak-brake/low-grip corner is not covered by pairwise rows alone.
CAR_PROFILES["fast-low-grip"] = dict(grip=2.0, acceleration=7.0, brake_acceleration=4.0, top_speed=18.0)


def drive_through_roads():
    """P98's kilometre, human-scale arcs and the recorded highway exit.

    Arc radii bracket the 59/118 m medians of the day drive's bend/straight
    curvature proxies. The exit is the path at 205.01 s of 20261113-225006,
    at an estimated 2.1 m/px, with a 300 m approach and an extended outgoing road.
    This is the route centreline, not the barrier that the recorded car hit.
    """
    roads = {"kilometre": ((0.0, 0.0), (0.0, 1000.0))}
    for radius in (60, 120):
        arc = [(radius * (1 - cos(radians(a))), 200 + radius * sin(radians(a))) for a in range(0, 91, 5)]
        roads[f"bend-{radius}"] = ((0.0, 0.0), *arc, (radius + 200.0, 200.0 + radius))
    pixels = (
        (0, 13),
        (0, 19),
        (2, 25),
        (3, 31),
        (5, 37),
        (7, 43),
        (9, 48),
        (7, 54),
        (-1, 56),
        (-7, 57),
        (-13, 57),
        (-19, 57),
        (-25, 57),
        (-31, 57),
        (-37, 57),
        (-43, 57),
        (-49, 57),
        (-55, 57),
    )
    roads["exit"] = (
        (0.0, 0.0),
        (0.0, 300.0),
        *((x * 2.1, 300 + y * 2.1) for x, y in pixels),
        (-350.0, 419.7),
    )
    return roads
