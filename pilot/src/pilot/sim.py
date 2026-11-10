"""Seeded planar bicycle simulator, deliberately independent of image processing.

Coordinates are metres (x right/east, y up/north), headings clockwise radians from
north. Map scale is metres per pixel. Route readings use the contract's 30/60 pixel
rings; they are not privileged cross-track errors. Brake decelerates forward motion
before reversing. Walls are zero-thickness segments swept by the vehicle centre.
This model cannot establish real-game handling or perception accuracy.
"""

from collections import deque
from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, isfinite, radians, sin, sqrt, tan
from random import Random

from pilot.contract import NEUTRAL, Command, Reading
from pilot.drive import Driver

Point = tuple[float, float]
Wall = tuple[Point, Point]


@dataclass(frozen=True)
class SimConfig:
    dt: float = 1 / 30
    delay: float = 0.21
    map_scale: float = 1.0
    dead_zone: float = 0.0
    wheelbase: float = 2.7
    max_wheel_angle: float = 35.0
    acceleration: float = 4.5
    drag: float = 0.45
    top_speed: float = 12.0
    reverse_speed: float = 3.0
    brake_acceleration: float = 8.0
    camera_lag: float = 0.3
    noise_degrees: float = 3.0
    noise_tail_multiplier: float = 16 / 3
    noise_tail_probability: float = 0.15
    outlier_probability: float = 0.01
    damage_probability: float = 0.05
    arrival_radius: float = 3.0
    progress_distance: float = 0.5
    max_time: float = 240.0

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        for name in ("dt", "map_scale", "wheelbase", "top_speed", "arrival_radius", "max_time"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.dead_zone >= 1 or self.max_wheel_angle >= 89:
            raise ValueError("invalid steering geometry")
        if max(self.outlier_probability, self.damage_probability, self.noise_tail_probability) > 1:
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

    def observe(self) -> tuple[Reading, bool | None]:
        """Noisy picture-angle readings and an independent short motion estimate."""
        cfg = self.config
        near, far = self._target(30 * cfg.map_scale), self._target(60 * cfg.map_scale)
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
        )
        moving = abs(self.speed) > 0.15
        return reading, moving

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
        yaw = self.speed / cfg.wheelbase * tan(radians(cfg.max_wheel_angle) * steer) * dt
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
        self._queue.append((self.time + self.config.delay, command))
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
        distances = [distance]
        best_progress, last_progress = progress, self.time
        max_gap = 0.0
        flips, last_sign = 0, 0
        reached = False
        while self.time < self.config.max_time:
            reading, moving = self.observe()
            command = driver.step(reading, self.time, moving)
            sign = 1 if command.steer > 0 else -1 if command.steer < 0 else 0
            if sign:
                flips += int(last_sign != 0 and sign != last_sign)
                last_sign = sign
            self.advance(command)
            distance, progress = self._route_position()
            distances.append(distance)
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
            sum(distances) / len(distances),
            max(distances),
            max_gap,
            flips / max(self.time, self.config.dt),
            self._recoveries,
            self.collisions,
            (self.x, self.y),
        )
