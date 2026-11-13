"""Defensive path following with a noisy GPS distance speed sensor."""

import os
from collections import deque
from dataclasses import dataclass
from math import atan2, degrees, hypot, isfinite, sqrt

from pilot.contract import NEUTRAL, Command, Reading

# Metres a second taken for a car that moves with its speed unread: the mean of the first town drives
# (docs/LOG.md, 11 November).
ASSUMED_SPEED = 4.0


@dataclass(frozen=True)
class DriveConfig:
    """Controller timing and gains; validate changes against replay and simulation."""

    steer_gain: float = 0.02  # Heading error to stick deflection per degree.
    steer_zero: float = 0.005  # Snap a decayed stick to zero below this magnitude.
    max_step_time: float = 0.5  # Bound feedback integration after a scheduling pause.
    steer_smoothing: float = 0.05  # Low-pass time constant for stick output.
    bearing_smoothing: float = 0.1  # Reject rapid angle noise before feedback.
    steer_deadband: float = 8.0  # Band of a straight for the pedal, and no prediction inside it.
    # Measured on the console drive of 13 November, 17:20 (197 s of straights, the heading against
    # the route 0.35 s after the stick): under 0.3 of the stick the car turns by 0 to 1 degree a
    # second, at 0.36 by 6, at 0.47 by 15, at 0.67 by 29. With 0.25 and a band of 8 degrees the car was
    # left alone up to 11 degrees of error and swung by 20 degrees around the route; Kerim's swings by 3.
    steer_rest: float = 3.0  # Filtered heading error that is not steered against.
    steering_bias: float = 0.29  # The stick's dead zone in a car: the first degree of error starts here.
    command_delay: float = 0.21  # Capture-to-control latency used for prediction.
    prediction_limit: float = 8.0  # Maximum angle extrapolation across the delay.
    cruise_throttle: float = 0.58  # Pedal on a straight, legible route.
    bend_throttle: float = 0.22  # Minimum pedal while following a bend.
    bend_gain: float = 0.013  # Pedal reduction per degree of upcoming bend.
    lookahead_px: float = 8.0  # First visible route target, in crop pixels.
    # Where the way from the car keeps its direction over twice this length, the aim lies this far
    # out. On the country road of 13 November, 18:10, at 30 to 50 km/h, the aim at 8 px stood 50 to 70
    # degrees to the side while the car's heading was 30 off: three or four pixels beside the route
    # are 25 degrees at 8 px and 10 at 20, and the car swung across the line every 2.7 s with the
    # stick at its stop. The short aim stays wherever the way bends: it keeps the car out of the corner.
    straight_lookahead_px: float = 20.0
    straight_bend: float = (
        15.0  # Degrees between two stretches of that length under which the way is straight.
    )
    speed_limit: float = 7.0  # Straight-line limit in metres per second.
    slow_speed: float = 2.0  # Lowest planned corner speed, in metres per second.
    lateral_acceleration: float = 1.2  # Conservative m/s^2 cornering budget.
    planned_deceleration: float = 2.0  # Metres/s^2 used to lift ahead of a bend.
    speed_smoothing: float = 0.25  # Suppress frame-pair sensor noise before pedal feedback.
    speed_gain: float = 0.18  # Throttle feedback per m/s below the target.
    brake_gain: float = 0.18  # Brake feedback per m/s above the target.
    brake_margin: float = 1.0  # Sensor-error allowance before applying L2.
    motion_speed: float = 0.5  # Filtered m/s evidence of motion, below the L2 safety threshold.
    rolling_speed: float = 1.0  # Never use L2 below this measured m/s speed.
    unknown_throttle: float = 0.18  # Slow pedal fallback when the sensor abstains.
    gps_interval: float = 0.25  # One optional OCR job at most every quarter second.
    gps_window: float = 3.0  # Robust distance slope window in seconds.
    gps_stale: float = 1.5  # Expired GPS cannot authorize braking.
    gps_max_speed: float = 50.0  # Reject impossible distance changes, m/s.
    gps_tolerance: float = 8.0  # Metres of OCR scatter around a consistent trend.
    gps_acceleration: float = 8.0  # Plausible m/s^2 change before quarantining a jump.
    map_scale_min: float = 0.35  # Low-speed 0.7 m/px with a factor-of-two safety band.
    arrival_distance: float = 8.0  # Enter the approach speed in the last metres.
    arrival_speed: float = 1.5  # Approach at walking pace; route loss ends the run.
    damage_hold: float = 0.5  # Conservative bound below replay gap p90 .555s; damage cannot renew it.
    damage_angle: float = 25.0  # Reject direction changes beyond recent clean evidence.
    confidence_min: float = 0.5  # Lowest accepted perception confidence.
    hold_time: float = 0.3  # Last follow command survives only this long without evidence.
    route_gone_time: float = 2.0  # Time of observed route absence before stopping.
    stuck_time: float = 2.0  # Throttle plus explicitly absent movement before escape.
    reverse_time: float = 1.25  # Duration of the reverse pedal phase.
    forward_time: float = 4.0  # Forward escape observation window.
    recovery_clear_time: float = 2.0  # Sustained forward motion clears failed-attempt count.
    recovery_clear_distance: float = 0.0  # Optional measured forward metres before forgetting failures.
    recovery_steer: float = 0.8  # Stick magnitude used to reverse away from the route.
    recovery_throttle: float = 0.45  # Forward pedal during escape.
    max_recoveries: int = 3  # Consecutive failed escapes before a latched stop.
    manoeuvres: float = 0.0
    bypass_reverse_time: float = 0.9
    turn_reverse_time: float = 3.6
    queue_wait: float = 30.0  # Longest a stop close behind a vehicle is waited out before it counts as stuck.
    damage_lasting: float = 1.0  # A damage flag that stays this long is no stream damage, which lasts frames.
    damage_steady: float = 20.0  # Widest spread of the route bearing, in degrees, of a flag driven on.
    flagged_speed: float = 4.0  # Speed limit on a map the reader flags, in metres per second.
    unreadable_time: float = 3.0  # A stopped car that cannot use the picture this long gives the drive up.
    unreadable_max: float = 10.0  # Longest an unusable picture is coasted on, whether the car stands or not.
    outlier_angle: float = 60.0  # Abrupt jumps larger than this require persistence.
    outlier_window: float = 0.3  # Accept a persistent new direction after this interval.
    stop_brake_time: float = 0.7  # Bound L2 use so a stop cannot become indefinite reverse.
    far_bend: float = (
        1.0  # Weight of the far bearing in the speed limit; at zero only the route's shape slows.
    )
    curve_step: int = 1  # Path points between the three of a curvature estimate; neighbours are pixel noise.
    curve_trim: int = 0  # Far path points left out of the curvature; the trace bends along the rim.
    hold_throttle: float = 0.0  # Pedal that about keeps the speed at the limit; the feedback works around it.
    straight_hold_throttle: float = 0.0  # Extra pedal only where the path permits the straight limit.
    brake_floor: float = 0.0  # No L2 for speed below this measured m/s.
    brake_pulse: float = 0.0  # Longest unbroken L2 for speed in seconds; zero does not bound it.
    brake_rest: float = 1.0  # Seconds without L2 after a pulse, for the speed reading to catch up.

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                raise ValueError(f"{name} must be finite")
            if value < 0:
                raise ValueError(f"{name} must be nonnegative")
        for name in (
            "unknown_throttle",
            "cruise_throttle",
            "bend_throttle",
            "confidence_min",
            "recovery_steer",
            "recovery_throttle",
            "steering_bias",
        ):
            if getattr(self, name) > 1:
                raise ValueError(f"{name} must be at most one")
        if self.max_recoveries < 1 or not isinstance(self.max_recoveries, int):
            raise ValueError("max_recoveries must be a positive integer")
        if self.curve_step < 1 or not isinstance(self.curve_step, int):
            raise ValueError("curve_step must be a positive integer")
        if not isinstance(self.curve_trim, int):
            raise ValueError("curve_trim must be an integer")


# States in which the driver has given the car up: they last, and the skill ends on them.
LATCHED = frozenset({"failed-recovery", "dead-or-held", "map-unreadable"})


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return float(value) if isfinite(value) else None
    except (OverflowError, ValueError):
        return None


def _angle(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def _clip(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class Driver:
    """Clock-driven state machine; step is total over malformed scalar fields."""

    def __init__(self, config: DriveConfig | None = None) -> None:
        self.config = config if config is not None else DriveConfig()
        self._time: float | None = None
        self._speed: float | None = None
        self._speed_at: float | None = None
        self._measured_speed: float | None = None
        self._stationary = False
        self._last_good: float | None = None
        self._missing_duration = 0.0
        self._missing_observed_at: float | None = None
        self._route_stop_time: float | None = None
        self._route_stopped = False
        self._error: float | None = None
        self._far = False  # whether the aim of the last tick was the far one
        self.aim_px = self.config.lookahead_px  # the aim's distance of the last tick, for the log
        # A comparison within one drive, for the console: with PILOT_AIM_AB set to a number of seconds
        # the far aim is allowed in every other stretch of that length on the session's clock, the
        # first one included, and the short aim alone steers in between. Unset, nothing alternates.
        try:
            self._aim_ab = max(0.0, float(os.environ.get("PILOT_AIM_AB", "") or 0.0))
        except ValueError:
            self._aim_ab = 0.0
        self._outlier_since: float | None = None
        self._filtered_error: float | None = None
        self._filtered_far: float | None = None
        self._moving_since: float | None = None
        self._steer = 0.0
        self._last = NEUTRAL
        self._stuck_since: float | None = None
        self._phase: str | None = None
        self._phase_since = 0.0
        self._attempts = 0
        self._recovery_distance = 0.0
        self._escape = 0.0
        self._recovery_moved = False
        self._recovery_still = 0.0
        self._reverse_duration = self.config.reverse_time
        self._bypass_attempts = 0
        self._manoeuvre_side = 0
        self._manoeuvre_moved = False
        self._manoeuvre_still_since = None
        self._turns = 0
        self._queue_spent = 0.0
        self._queue_free: float | None = None
        self._flag_since: float | None = None
        self._flag_route: str | None = None
        self._flag_bearings: deque[tuple[float, float]] = deque()
        self.flagged_time = 0.0  # Seconds driven on a map the reader flagged, which the skill reports.
        self._unusable_since: float | None = None
        self._unusable_still: float | None = None
        self._trusted_route: str | None = None
        self._trusted_error: float | None = None
        self._brake_since: float | None = None

    @property
    def bypassing(self) -> bool:
        """The close vehicle has used up this style's stationary queue allowance."""
        return self._queue_spent >= self.config.queue_wait

    def _emit(self, steer: float, throttle: float, brake: float, state: str) -> Command:
        if (
            state in {"follow", "coast", "route-gone"}
            and self._measured_speed is not None
            and self._measured_speed <= self.config.rolling_speed
        ):
            brake = 0
        if state in {"follow", "coast"} and (self._measured_speed is None or self._stationary):
            brake = 0
        self._last = Command(_clip(steer), _clip(throttle, 0), _clip(brake, 0), state)
        return self._last

    def _idle(self) -> Command:
        self._trusted_route = self._trusted_error = None
        self._last_good = self._missing_observed_at = self._route_stop_time = None
        self._missing_duration = 0.0
        self._route_stopped = False
        self._error = self._outlier_since = None
        self._filtered_error = self._filtered_far = self._moving_since = None
        self._stuck_since = None
        self._steer = 0.0
        self._speed = None
        self._unusable_since = self._unusable_still = self._flag_since = None
        self._flag_bearings.clear()
        if self._phase not in LATCHED:
            self._phase = None
        return self._emit(0, 0, 0, "idle")

    def _coast(self, now: float) -> Command:
        if self._phase is not None and self._phase.startswith(("bypass-", "turn-")):
            return self._emit(0, 0, 0, "coast")
        if self._last_good is not None and now - self._last_good <= self.config.hold_time:
            if self._last.state in {"follow", "coast", "recovery-reverse", "recovery-forward"}:
                return self._emit(self._last.steer, self._last.throttle, self._last.brake, "coast")
        self._steer = 0.0
        self._stuck_since = None
        if self._phase not in LATCHED:
            self._phase = None
        return self._emit(0, 0, 0, "coast")

    def step(
        self,
        reading: Reading,
        t: float,
        moving: bool | None = None,
        speed: float | None = None,
        ahead: bool = False,
        bypass_side=None,
        boxes_fresh=True,
    ) -> Command:
        """Return bounded controls; invalid/backwards clocks release and reset timers.

        Unknown motion never means stuck. A failure latch survives clock changes.
        Picture angles minus the arrow give camera-independent heading errors.
        `ahead` says that a vehicle stands close ahead in the car's own track (avoid.waits_behind): a
        stop behind it is waited out for `queue_wait` seconds and counts neither towards a recovery
        nor towards a dead or held car. Without detections it stays False and nothing changes.
        """
        speed = _number(speed)
        speed = speed if speed is not None and speed >= 0 else None
        self._measured_speed = speed
        moving = moving if isinstance(moving, bool) else None
        map_moving = moving
        self._stationary = moving is False
        now = _number(t)
        if now is None or (self._time is not None and now < self._time):
            self._time = now
            return self._idle()
        dt = 0.0 if self._time is None else min(now - self._time, self.config.max_step_time)
        self._time = now
        if speed is not None:
            fresh = self._speed_at is None or now - self._speed_at > self.config.max_step_time
            alpha_speed = (
                1.0 if self._speed is None or fresh else dt / max(dt + self.config.speed_smoothing, 1e-9)
            )
            self._speed_at = now
            self._speed = speed if self._speed is None else self._speed + alpha_speed * (speed - self._speed)
            speed = self._speed
            if moving is not None and speed > self.config.motion_speed:
                moving = True
        if moving is False:
            self._moving_since = None
        elif moving is None and self._moving_since is not None:
            self._moving_since += dt
        if (
            not isinstance(reading, Reading)
            or not isinstance(reading.minimap, str)
            or reading.minimap != "tilted"
        ):
            return self._idle()
        if self._phase in LATCHED:
            return self._emit(0, 0, 0, self._phase)
        if moving is True and self._last.throttle > 0:
            # With the speed unread the car still moves: counted at the town's walking pace of a
            # drive, so that a stop passed long ago is not held against the next one for ever.
            self._recovery_distance += (ASSUMED_SPEED if speed is None else speed) * dt
        confidence = _number(reading.confidence)
        damaged = self._damage_agrees(reading, now, confidence)
        flagged = self._flag_lasts(reading, now, confidence)
        if (
            not damaged
            and not flagged
            and (
                reading.corrupt is not False
                or confidence is None
                or not self.config.confidence_min <= confidence <= 1
            )
        ):
            self._missing_observed_at = None
            return self._unusable(now, dt, moving, speed)
        if not isinstance(reading.route, str):
            return self._unusable(now, dt, moving, speed)
        if flagged:
            # A flagged picture is driven on, and a car that stays standing under it has not been helped.
            wait = self.config.unreadable_time + (self.config.queue_wait if ahead is True else 0.0)
            if self._standing(now, dt, moving, speed, stuck_logic=True) >= wait:
                self._phase = "map-unreadable"
                return self._emit(0, 0, 0, self._phase)
        else:
            self._unusable_since = self._unusable_still = None
        if reading.route == "none":
            if self._missing_observed_at is not None:
                self._missing_duration += now - self._missing_observed_at
            self._missing_observed_at = now
            if self._missing_duration >= self.config.route_gone_time:
                self._stuck_since = None
                self._phase = None
                if self._route_stop_time is None:
                    self._route_stop_time = now
                if moving is False or now - self._route_stop_time >= self.config.stop_brake_time:
                    self._route_stopped = True
                return self._emit(0, 0, int(not self._route_stopped), "route-gone")
            return self._coast(now)
        self._missing_observed_at = self._route_stop_time = None
        self._missing_duration = 0.0
        self._route_stopped = False
        near, far, arrow = (_number(reading.bearing), _number(reading.far_bearing), _number(reading.arrow))
        if reading.route not in ("yellow", "purple") or near is None or arrow is None:
            return self._unusable(now, dt, moving, speed)
        error = _angle(_angle(near) - _angle(arrow))
        far_error = error if far is None else _angle(_angle(far) - _angle(arrow))
        path = _path(reading.path)
        if path:
            allowed = self._aim_ab <= 0 or int(now // self._aim_ab) % 2 == 0
            self._far = allowed and _straight(path, self.config, self._far)
            self.aim_px = self.config.straight_lookahead_px if self._far else self.config.lookahead_px
            target = _target(
                path, self.config.straight_lookahead_px if self._far else self.config.lookahead_px
            )
            error = _angle(degrees(atan2(target[0], target[1])) - arrow)
            far_error = _angle(degrees(atan2(path[-1][0], path[-1][1])) - arrow)
        if self._error is not None and abs(_angle(error - self._error)) > self.config.outlier_angle:
            if self._outlier_since is None:
                self._outlier_since = now
            if now - self._outlier_since < self.config.outlier_window:
                return self._coast(now)
        self._outlier_since = None
        if not damaged:
            self._last_good = now
            self._trusted_route = reading.route
            self._trusted_error = _angle(_angle(_number(reading.bearing)) - _angle(arrow))

        queued = self._queue(ahead is True, moving, now, dt)
        if self.config.manoeuvres:
            manoeuvre = self._manoeuvre(
                now,
                error,
                far_error,
                map_moving,
                speed,
                ahead,
                bypass_side,
                reading.corrupt is False and boxes_fresh,
            )
            if manoeuvre is not None:
                self._error = error
                return manoeuvre

        if self._phase in {"recovery-reverse", "recovery-forward"} and (not reading.corrupt or flagged):
            # GPS slope lags a collision; only the map can prove a completely held car.
            self._recovery_moved |= map_moving is True
            if map_moving is False and not queued:
                self._recovery_still += dt
        if self._phase == "recovery-reverse":
            if now - self._phase_since < self._reverse_duration:
                return self._emit(self._escape, 0, 1, "recovery-reverse")
            self._phase, self._phase_since = "recovery-forward", now
        if self._phase == "recovery-forward":
            if moving is True:
                if self._moving_since is None:
                    self._moving_since = now
                if now - self._moving_since >= self.config.recovery_clear_time:
                    if self._recovery_distance >= self.config.recovery_clear_distance:
                        self._attempts = 0
                    self._phase = None
                    self._stuck_since = None
            if self._phase is not None:
                if now - self._phase_since < self.config.forward_time:
                    return self._emit(
                        _clip(
                            self.config.steer_gain * error,
                            -self.config.recovery_steer,
                            self.config.recovery_steer,
                        )
                        if self._attempts == 1 and not (self.config.queue_wait <= 2.0 and self.bypassing)
                        else -self._escape,
                        min(self.config.recovery_throttle, self.config.unknown_throttle)
                        if speed is None
                        else min(
                            self.config.recovery_throttle,
                            max(
                                0,
                                self.config.speed_gain
                                * (self._speed_limit(path, max(abs(error), abs(far_error)), speed) - speed),
                            ),
                        ),
                        0,
                        "recovery-forward",
                    )
                if not self._recovery_moved and self._recovery_still >= 0.8 * (
                    self._reverse_duration + self.config.forward_time
                ):
                    self._phase = "dead-or-held"
                    return self._emit(0, 0, 0, self._phase)
                if moving is not False or queued:
                    self._phase = None
                elif self._attempts >= self.config.max_recoveries:
                    self._phase = "failed-recovery"
                    return self._emit(0, 0, 0, "failed-recovery")
                else:
                    return self._recover(now, error)

        if queued:
            self._stuck_since = None  # Waiting behind a vehicle is not being stuck.
        elif moving is False and self._last.throttle > 0:
            if ahead is True and self.config.queue_wait <= 2.0 and self.bypassing:
                # The queue allowance already proved this standstill. Spending
                # another stuck interval against the same bumper cannot free it.
                self._stuck_since = now - self.config.stuck_time
            if self._stuck_since is None:
                self._stuck_since = now
            if now - self._stuck_since >= self.config.stuck_time:
                if self._attempts >= self.config.max_recoveries:
                    self._phase = "failed-recovery"
                    return self._emit(0, 0, 0, "failed-recovery")
                return self._recover(now, error)
        elif moving is None and self._stuck_since is not None:
            self._stuck_since += dt  # Missing evidence pauses, rather than proves, a standstill.
        else:
            self._stuck_since = None

        if moving is True and self._last.throttle > 0:
            if self._moving_since is None:
                self._moving_since = now
            if now - self._moving_since >= self.config.recovery_clear_time:
                if self._recovery_distance >= self.config.recovery_clear_distance:
                    self._attempts = 0
        elif moving is False or self._last.throttle <= 0:
            self._moving_since = None
        previous = self._filtered_error
        alpha = (
            1.0
            if previous is None
            else dt
            / max(
                dt + self.config.bearing_smoothing,
                1e-9,
            )
        )
        self._filtered_error = (
            error if previous is None else _angle(previous + alpha * _angle(error - previous))
        )
        self._filtered_far = (
            far_error
            if self._filtered_far is None
            else _angle(self._filtered_far + alpha * _angle(far_error - self._filtered_far))
        )
        rate = 0.0 if previous is None or dt <= 0 else _angle(self._filtered_error - previous) / dt
        correction = _clip(
            rate * self.config.command_delay, -self.config.prediction_limit, self.config.prediction_limit
        )
        # Predict turns only outside the neutral band; differentiated map jitter
        # otherwise caused up to 7.7 steering sign changes per second in the grid.
        if abs(self._filtered_error) <= self.config.steer_deadband:
            correction = 0.0
        adjusted = self._filtered_error + correction
        bend_delta = _angle(self._filtered_far - self._filtered_error)
        adjusted = (1 if adjusted >= 0 else -1) * max(0.0, abs(adjusted) - self.config.steer_rest)
        target = _clip(self.config.steer_gain * adjusted)
        if target:
            target = (1 if target > 0 else -1) * (
                self.config.steering_bias + (1 - self.config.steering_bias) * abs(target)
            )
        alpha = (
            1.0
            if self._error is None
            else dt
            / max(
                dt + self.config.steer_smoothing,
                1e-9,
            )
        )
        self._steer += alpha * (target - self._steer)
        if abs(self._steer) < self.config.steer_zero and target == 0:
            self._steer = 0.0
        bend = max(
            abs(self._filtered_error),
            self.config.far_bend * abs(self._filtered_far),
            self.config.far_bend * abs(bend_delta),
        )
        throttle = max(self.config.bend_throttle, self.config.cruise_throttle - self.config.bend_gain * bend)
        limit = self._speed_limit(path, bend, speed)
        if flagged:
            limit = min(limit, self.config.flagged_speed)
            self.flagged_time += dt
        distance = _number(reading.gps_distance)
        if distance is not None and 0 <= distance <= self.config.arrival_distance:
            limit = min(limit, self.config.arrival_speed)
        brake = 0.0
        if speed is None:
            throttle *= self.config.unknown_throttle / max(self.config.cruise_throttle, 1e-9)
        else:
            hold = self.config.hold_throttle
            if bend <= self.config.steer_deadband and abs(bend_delta) <= self.config.steer_deadband:
                hold = max(hold, self.config.straight_hold_throttle)
            throttle = _clip(
                hold + self.config.speed_gain * (limit - speed),
                0,
                self.config.cruise_throttle,
            )
            if speed > self.config.rolling_speed and speed > limit + self.config.brake_margin:
                brake = _clip(self.config.brake_gain * (speed - limit - self.config.brake_margin), 0, 0.7)
                brake = self._pulsed(brake, speed, now)
        self._error = error
        return self._emit(self._steer, throttle, brake, "follow")

    def _speed_limit(self, path, bend: float, speed: float | None) -> float:
        cfg = self.config
        limit = max(min(cfg.slow_speed, cfg.speed_limit), cfg.speed_limit / (1 + bend / 15))
        step = cfg.curve_step
        path = path[: len(path) - cfg.curve_trim]
        if len(path) < 2 * step + 1:
            return limit
        travel = hypot(*path[0])
        for index in range(len(path) - 2 * step):
            a, b, c = path[index], path[index + step], path[index + 2 * step]
            ab, bc = hypot(b[0] - a[0], b[1] - a[1]), hypot(c[0] - b[0], c[1] - b[1])
            if min(ab, bc) < 1:
                continue
            cross = abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
            curvature = 2 * cross / max(ab * bc * hypot(c[0] - a[0], c[1] - a[1]), 1e-6)
            corner = max(
                min(cfg.slow_speed, cfg.speed_limit),
                sqrt(cfg.lateral_acceleration * cfg.map_scale_min / max(curvature, 1e-6)),
            )
            # Reserve the hidden near-arrow section and the command delay for turning in.
            remaining = max(
                0,
                (travel - cfg.lookahead_px) * cfg.map_scale_min
                - (speed or 0) * (cfg.command_delay + cfg.gps_window / 2),
            )
            limit = min(limit, sqrt(corner * corner + 2 * cfg.planned_deceleration * remaining))
            travel += hypot(path[index + 1][0] - a[0], path[index + 1][1] - a[1])
        return limit

    def _pulsed(self, brake: float, speed: float, now: float) -> float:
        """L2 for speed in bounded pulses: the reading lags, and a brake held too long ends in reverse."""
        cfg = self.config
        if not brake or not cfg.brake_pulse:
            return brake
        if speed < cfg.brake_floor:
            return 0.0
        if self._brake_since is None or not 0 <= now - self._brake_since < cfg.brake_pulse + cfg.brake_rest:
            self._brake_since = now
        return brake if now - self._brake_since < cfg.brake_pulse else 0.0

    def _damage_agrees(self, reading: Reading, now: float, confidence: float | None) -> bool:
        if (
            reading.corrupt is not True
            or confidence is None
            or not 0.3 <= confidence <= 1
            or self._last_good is None
            or now - self._last_good > self.config.damage_hold
            or not isinstance(reading.route, str)
            or reading.route != self._trusted_route
            or self._trusted_error is None
        ):
            return False
        near, arrow = _number(reading.bearing), _number(reading.arrow)
        if near is None or arrow is None:
            return False
        error = _angle(_angle(near) - _angle(arrow))
        return (
            abs(error) > 5
            and error * self._trusted_error > 0
            and abs(_angle(error - self._trusted_error)) <= self.config.damage_angle
        )

    def _flag_lasts(self, reading: Reading, now: float, confidence: float | None) -> bool:
        """The reader's damage flag has stood for `damage_lasting` seconds on the same route, with a
        confidence in the range of damage and a bearing that holds still: that is a picture it
        misjudges, not damage from the cable, which lasts a few frames and scrambles the bearing."""
        route = reading.route
        near, arrow = _number(reading.bearing), _number(reading.arrow)
        if (
            reading.corrupt is not True
            or route not in ("yellow", "purple")
            or confidence is None
            or not 0.3 <= confidence <= 1
            or near is None
            or arrow is None
        ):
            self._flag_since = self._flag_route = None
            self._flag_bearings.clear()
            return False
        if self._flag_since is None or route != self._flag_route:
            self._flag_since, self._flag_route = now, route
            self._flag_bearings.clear()
        self._flag_bearings.append((now, near))
        while self._flag_bearings and now - self._flag_bearings[0][0] > self.config.damage_lasting:
            self._flag_bearings.popleft()
        if now - self._flag_since < self.config.damage_lasting:
            return False
        spread = max(abs(_angle(bearing - near)) for _, bearing in self._flag_bearings)
        return spread <= self.config.damage_steady

    def _standing(
        self, now: float, dt: float, moving: bool | None, speed: float | None, *, stuck_logic: bool = False
    ) -> float:
        """Seconds the car has stood still on evidence, 0 once it moves; missing evidence pauses the count.

        Where the drive goes on (`stuck_logic`), a map that says the car stands is left to the recovery
        that stands for it: only the speed counts here, for the car whose map says nothing."""
        if stuck_logic and moving is False:
            moving, speed = None, None
        if moving is False or (moving is None and speed is not None and speed <= self.config.motion_speed):
            if self._unusable_still is None:
                self._unusable_still = now
        elif moving is None and speed is None:
            if self._unusable_still is not None:
                self._unusable_still += dt
        else:
            self._unusable_still = None
        return 0.0 if self._unusable_still is None else now - self._unusable_still

    def _unusable(self, now: float, dt: float, moving: bool | None, speed: float | None) -> Command:
        """A picture the driver cannot use: it coasts, and gives the car up when that has left it standing."""
        if self._unusable_since is None:
            self._unusable_since = now
        standing = self._standing(now, dt, moving, speed)
        if (
            standing >= self.config.unreadable_time
            or now - self._unusable_since >= self.config.unreadable_max
        ):
            self._phase = "map-unreadable"
            return self._emit(0, 0, 0, self._phase)
        return self._coast(now)

    def _manoeuvre(self, now, near_error, error, moving, speed, ahead, side, clean):
        active = self._phase is not None and self._phase.startswith(("bypass-", "turn-"))
        if not clean:
            if active:
                return self._emit(0, 0, 0, "coast")
            return None
        if not active:
            if self._phase is not None:
                return None
            slow = moving is False if speed is None else speed < 1.5
            if ahead and side is not None and moving is False and slow:
                if not self.bypassing:
                    return self._emit(0, 0, 0, "bypass-wait")
                if self._attempts >= self.config.max_recoveries:
                    self._phase = "failed-recovery"
                    return self._emit(0, 0, 0, self._phase)
                if self._attempts == 0:
                    self._bypass_attempts = 0
                self._attempts += 1
                chosen = side or (1 if error >= 0 else -1)
                self._manoeuvre_side = chosen if self._bypass_attempts % 2 == 0 else -self._manoeuvre_side
                self._bypass_attempts += 1
                self._phase = "bypass-reverse"
            elif abs(near_error) > 120 and slow and not ahead:
                if self._attempts >= self.config.max_recoveries or self._turns >= 3:
                    self._phase = "failed-recovery"
                    return self._emit(0, 0, 0, self._phase)
                self._attempts += 1
                self._turns += 1
                self._manoeuvre_side = 1 if error >= 0 else -1
                self._phase = "turn-reverse"
            else:
                return None
            self._phase_since = now
            self._manoeuvre_moved = False
            self._recovery_distance = 0.0
        elapsed = now - self._phase_since
        settling = 1.5 if self._phase.endswith("forward") else 0.6
        if elapsed > settling:
            self._manoeuvre_moved |= moving is True
        no_motion_limit = 2.5 if self._phase.endswith("forward") else 1.5
        stopped = (
            elapsed > settling and moving is False and (self._manoeuvre_moved or elapsed >= no_motion_limit)
        )
        if stopped:
            if self._manoeuvre_still_since is None:
                self._manoeuvre_still_since = now
        else:
            self._manoeuvre_still_since = None
        blocked = stopped and now - self._manoeuvre_still_since >= 0.1
        if stopped and not blocked:
            bound = (
                self.config.bypass_reverse_time
                if self._phase == "bypass-reverse"
                else self.config.turn_reverse_time
            )
            if not self._phase.endswith("reverse") or elapsed < bound:
                return self._emit(0, 0, 0, self._phase)
        if self._phase == "bypass-reverse":
            if elapsed < self.config.bypass_reverse_time and not blocked:
                return self._emit(0, 0, 1, self._phase)
            self._phase, self._phase_since = "bypass-forward", now
            self._manoeuvre_moved = False
            self._manoeuvre_still_since = None
            elapsed, blocked = 0.0, False
        elif self._phase == "turn-reverse":
            if abs(error) > 60 and elapsed < self.config.turn_reverse_time and not blocked:
                return self._emit(-self._manoeuvre_side, 0, 1, self._phase)
            self._phase, self._phase_since = "turn-forward", now
            self._manoeuvre_moved = False
            self._manoeuvre_still_since = None
            elapsed, blocked = 0.0, False
        if self._phase == "bypass-forward":
            if (not ahead and elapsed > 0.5) or elapsed >= 4.5 or blocked:
                self._end_manoeuvre()
                return self._emit(0, 0.8, 0, "follow")
            return self._emit(self._manoeuvre_side, 1, 0, self._phase)
        if self._phase == "turn-forward":
            # Use the far route heading while turning; the nearest path point can
            # be beside the reversing car well before its nose faces the road.
            elapsed = now - self._phase_since
            if abs(error) < 25 and elapsed >= 1.0:
                self._turns = 0
                self._end_manoeuvre()
                return None
            if elapsed >= 4.0 or blocked:
                if self._turns >= 3 or self._attempts >= self.config.max_recoveries:
                    self._phase = "failed-recovery"
                    return self._emit(0, 0, 0, self._phase)
                self._turns += 1
                self._attempts += 1
                self._phase, self._phase_since = "turn-reverse", now
                self._manoeuvre_moved = False
                return self._emit(-self._manoeuvre_side, 0, 1, self._phase)
            # Keep the reverse lock during the short R2 gear change, then use
            # the opposite lock once forward motion can take over.
            steer = -self._manoeuvre_side if elapsed < 0.55 else self._manoeuvre_side
            return self._emit(steer, 1 if elapsed < 1.5 else 0.55, 0, self._phase)
        return None

    def _end_manoeuvre(self):
        self._phase = None
        self._stuck_since = self._moving_since = None
        self._error = self._filtered_error = self._filtered_far = None
        self._steer = 0.0

    def _queue(self, ahead: bool, moving: bool | None, now: float, dt: float) -> bool:
        """Whether this stop is being waited out behind a vehicle, and for how long it has been."""
        if ahead and moving is False:
            self._queue_free = None
            queued = self._queue_spent < self.config.queue_wait
            self._queue_spent += dt
            return queued
        if not ahead or moving is True:
            # The road ahead cleared or the car rolled on: a new queue gets its whole wait again,
            # but not at once, so that a recovery that backs off a parked car does not start one.
            if self._queue_free is None:
                self._queue_free = now
            elif now - self._queue_free >= self.config.recovery_clear_time:
                self._queue_spent = 0.0
        return False

    def _recover(self, now: float, error: float) -> Command:
        self._attempts += 1
        self._recovery_distance = 0.0
        self._phase, self._phase_since = "recovery-reverse", now
        # Extend the retreat and change the turning side after a failed exit.
        side = -1 if error >= 0 else 1
        self._escape = side * self.config.recovery_steer if self._attempts == 1 else -self._escape
        # Longer each time up to the third; further back than that is into what stands behind.
        self._reverse_duration = self.config.reverse_time * (1 + 0.5 * (min(self._attempts, 3) - 1))
        self._recovery_moved, self._recovery_still = False, 0.0
        self._stuck_since = self._moving_since = None
        return self._emit(self._escape, 0, 1, "recovery-reverse")


def _path(value: object) -> tuple[tuple[float, float], ...]:
    """Reject malformed paths as a whole, preserving the legacy bearing fallback."""
    if not isinstance(value, (tuple, list)) or len(value) > 256:
        return ()
    points = []
    for point in value:
        if not isinstance(point, (tuple, list)) or len(point) != 2:
            return ()
        x, y = (_number(v) for v in point)
        if x is None or y is None or not 10 <= hypot(x, y) <= 240:
            return ()
        if points and hypot(x - points[-1][0], y - points[-1][1]) < 0.5:
            continue
        points.append((x, y))
    return tuple(points)


def _straight(path, config, was: bool) -> bool:
    """Whether the way from the car keeps its direction far enough for the far aim.

    Measured from the car and not from the path's first point: that lies 11 px out and more, and a
    corner between the car and it, or just behind it, would be aimed across. The way is the line to
    that point and then the path, in two stretches of the far aim's length. A car that stands well
    beside the route bends that way too and gets the short aim, which pulls harder: far off the line
    that is what it should do. Once far, the aim stays far until the way bends by half as much again,
    so that a reading that wavers round the limit does not swap the aims from frame to frame.
    """
    span = config.straight_lookahead_px
    if span <= config.lookahead_px or not path:
        return False
    marks, travelled, previous = [(0.0, 0.0)], 0.0, (0.0, 0.0)
    for point in path:
        step = hypot(point[0] - previous[0], point[1] - previous[1])
        while len(marks) < 3 and step > 0 and travelled + step >= span * len(marks):
            fraction = (span * len(marks) - travelled) / step
            marks.append(tuple(a + fraction * (b - a) for a, b in zip(previous, point, strict=True)))
        travelled, previous = travelled + step, point
    if len(marks) < 3:
        return False
    first = degrees(atan2(marks[1][0], marks[1][1]))
    second = degrees(atan2(marks[2][0] - marks[1][0], marks[2][1] - marks[1][1]))
    return abs(_angle(second - first)) < config.straight_bend * (1.5 if was else 1.0)


def _target(path, radius: float):
    previous = path[0]
    if len(path) >= 2 and hypot(*previous) > radius:
        # Continue only the first visible straight segment under the arrow.
        # This short aiming point avoids cutting a wide corner as the map zooms.
        x, y = previous
        dx, dy = path[1][0] - x, path[1][1] - y
        length = hypot(dx, dy)
        if length > 0:
            dx, dy = dx / length, dy / length
            projection = x * dx + y * dy
            discriminant = projection * projection - x * x - y * y + radius * radius
            if discriminant < 0 and projection > 0:
                # Aim at the line's nearest point until the short circle reaches
                # it; the first visible point would start cutting the corner.
                return x - projection * dx, y - projection * dy
            if discriminant >= 0:
                along = -projection + sqrt(discriminant)
                if along < 0:
                    return x + along * dx, y + along * dy
    for point in path[1:]:
        before, after = hypot(*previous), hypot(*point)
        if before <= radius <= after and after > before:
            fraction = (radius - before) / (after - before)
            return tuple(a + fraction * (b - a) for a, b in zip(previous, point, strict=True))
        if before >= radius:
            return previous
        previous = point
    return previous
