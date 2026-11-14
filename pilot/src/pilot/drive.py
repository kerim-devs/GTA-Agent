"""Defensive path following with a noisy GPS distance speed sensor."""

import os
from collections import deque
from dataclasses import dataclass
from itertools import pairwise
from math import atan2, copysign, cos, degrees, hypot, isfinite, radians, sin, sqrt

from pilot.contract import NEUTRAL, Command, Reading

# Metres a second taken for a car that moves with its speed unread: the mean of the first town drives
# (docs/LOG.md, 11 November).
ASSUMED_SPEED = 4.0
# Metres a second above the straight limit up to which the holding pedal rests; beyond it the pedal
# falls with the excess, since the reading's noise on a straight stays inside this.
STRAIGHT_EXCESS = 3.0


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
    # What the car does with the stick, from Kerim's drives of 12 and 13 November (16 minutes of
    # straights with a route) and three of the pilot's: its yaw regressed on the stick of the last
    # 1.2 s gives 78 degrees a second per unit past the dead zone for his hand and 72 to 79 for the
    # pilot's, and the turn shows on the map between 0.2 and 0.7 s after the stick, a fifth of it
    # after 0.3 s and two thirds after 0.5. A stick held in proportion to an error that cannot have
    # changed yet is held for all of that time: the pilot's pulses lasted a second at the median and
    # Kerim's 0.17 s, with the stick at rest for 71 percent of his time on a straight. So the turn
    # that the stick of the last moments has still to bring is taken off the error before the stick
    # is set, and the stick is let go when enough has been given, not when it has shown.
    yaw_gain: float = 77.0  # Degrees a second the car turns per unit of the stick past its dead zone.
    yaw_first: float = 0.2  # Seconds after the stick at which its turn begins to show on the map,
    yaw_last: float = 0.7  # and at which all of it has.
    yaw_memory: float = 1.0  # Part of the turn still to show that is taken off the error; 0: none.
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
    # Where the way bends, the aim at 8 px is found by continuing the path's first segment, 5 to 6 px
    # long and a pixel of wander at each end, back under the arrow: in the closed loop with the car
    # as measured that alone swings the car by 8 degrees, and before the right turn of 13 November,
    # 18:32, at 210 s, it lay 6 to 28 degrees to the left while the route's beginning leaned to the
    # right. That continuation is there for a corner hidden under the arrow, where the path begins
    # round the corner. Where the path's beginning goes on in the direction in which its first point
    # lies from the car, nothing is hidden, and the aim is taken on the path itself, this far out.
    bend_lookahead_px: float = 14.0
    onward_bend: float = 25.0  # Degrees between the line to the path's first point and its beginning.
    drive_through: float = 0.0  # Plan bold speed from road shape, independently of heading correction.
    speed_limit: float = 7.0  # Straight-line limit in metres per second.
    slow_speed: float = 2.0  # Lowest planned corner speed, in metres per second.
    lateral_acceleration: float = 1.2  # Conservative m/s^2 cornering budget.
    planned_deceleration: float = 2.0  # Metres/s^2 used to lift ahead of a bend.
    braking_deceleration: float = 4.0  # Forward braking envelope; lift at planned_deceleration first.
    junction_speed: float = 6.0  # Tight junction target, below the measured human 14-21 m/s turns.
    turn_speed: float = 0.0  # Least speed planned for a turn of sixty degrees and more at a junction.
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
    coast_loss: float = 0.0  # m/s the car loses each second off the pedal; 0: the reading is taken as it is
    speed_lag: float = 0.7  # seconds the speed reading runs behind a car that slows
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
        self._onward = False  # whether, where the way bends, the path's beginning went on from the car
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
        self._filtered_near: float | None = None  # the short aim's error, for the pedal
        self._filtered_far: float | None = None
        self._moving_since: float | None = None
        self._steer = 0.0
        self._sticks: deque[tuple[float, float]] = deque()  # when each stick of the last moments began
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
        self._bypass_blind = False
        self._bypass_distance = 0.0
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
        self._off: deque[tuple[float, float]] = deque()  # ticks off the pedal: when, and for how long
        self._pedal_time: float | None = None
        self.speed_reason = "unknown-speed"
        self._turn_limit: float | None = None
        self._turn_junction = False  # whether the remembered corner is a right angle at a junction
        self._road_heading = 0.0
        self._turn_remaining = 0.0

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
        if state in {"follow", "coast"} and self._time is not None:
            self._sticks.append((self._time, self._last.steer))
            while self._sticks[0][0] < self._time - self.config.yaw_last - self.config.max_step_time:
                self._sticks.popleft()
        else:
            self._sticks.clear()  # a stop, a recovery or a lost map: what was steered before is over
        return self._last

    def _pending(self, now: float) -> float:
        """Degrees the car has still to turn, to the right positive, for the stick of the last moments."""
        cfg = self.config
        spread = max(cfg.yaw_last - cfg.yaw_first, 1e-9)
        ends = [*(start for start, _ in self._sticks), now][1:]
        total = 0.0
        for (start, steer), end in zip(self._sticks, ends, strict=True):
            past = abs(steer) - cfg.steering_bias
            if past <= 0:
                continue
            end = min(end, start + cfg.hold_time)  # a stick that nothing renews is let go
            shown = _clip((now - (start + end) / 2 - cfg.yaw_first) / spread, 0, 1)
            total += copysign(past, steer) * (end - start) * cfg.yaw_gain * (1 - shown)
        return total

    def _idle(self) -> Command:
        self._trusted_route = self._trusted_error = None
        self._last_good = self._missing_observed_at = self._route_stop_time = None
        self._missing_duration = 0.0
        self._route_stopped = False
        self._error = self._outlier_since = None
        self._filtered_error = self._filtered_near = self._filtered_far = self._moving_since = None
        self._stuck_since = None
        self._steer = 0.0
        self._speed = None
        self._turn_limit = None
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

        Missing motion alone never means stuck. Bold can also use fresh stationary
        GPS on a route ahead. A failure latch survives clock changes.
        Picture angles minus the arrow give camera-independent heading errors.
        `ahead` says that a vehicle stands close ahead in the car's own track (avoid.waits_behind): a
        stop behind it is waited out for `queue_wait` seconds and counts neither towards a recovery
        nor towards a dead or held car. Bold also clears an unreported obstruction
        after sustained stillness with the pedal down on a route ahead.
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
        self._turn_remaining -= (speed if speed is not None else ASSUMED_SPEED) * dt
        if self._turn_remaining <= 0:
            self._turn_limit = None
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
        self._road_heading = arrow
        path = _path(reading.path)
        # The pedal goes by the short aim as it always has: a bend shows there first, and with the far
        # aim alone the car came into a hidden bend 0.4 m/s too fast on a zoomed map.
        near_error = error
        if path:
            allowed = self._aim_ab <= 0 or int(now // self._aim_ab) % 2 == 0
            self._far = allowed and _straight(path, self.config, self._far)
            # In a stretch of the comparison that is the short aim's, the middle one does not steer either.
            self._onward = allowed and not self._far and _onward(path, self.config, self._onward, arrow)
            self.aim_px = (
                self.config.straight_lookahead_px
                if self._far
                else self.config.bend_lookahead_px
                if self._onward
                else self.config.lookahead_px
            )
            target = _target(path, self.aim_px, arrow)
            error = _angle(degrees(atan2(target[0], target[1])) - arrow)
            short = _target(path, self.config.lookahead_px)
            near_error = _angle(degrees(atan2(short[0], short[1])) - arrow)
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

        manoeuvre_motion = map_moving
        if self.config.manoeuvres:
            # At the van on 14 November the flow reader abstained for 80 s,
            # while fresh GPS fixes stayed at 52 m. Only an ahead route makes
            # its zero slope evidence of standing, rather than driving across it.
            gps_time = _number(reading.gps_time)
            if (
                map_moving is None
                and self._measured_speed is not None
                and self._measured_speed < 0.3
                and gps_time is not None
                and 0 <= now - gps_time <= self.config.gps_stale
                and abs(error) < 25
                and reading.corrupt is False
            ):
                manoeuvre_motion = False
            # The queue's old width-scaled geometry also includes a lorry
            # alongside. Only passing_side's lane-centre check permits a bypass.
            if ahead and bypass_side is None and not (self._phase or "").startswith("bypass-"):
                ahead = False
        queued = self._queue(ahead is True, manoeuvre_motion if self.config.manoeuvres else moving, now, dt)
        if self.config.manoeuvres:
            manoeuvre = self._manoeuvre(
                now,
                error,
                far_error,
                manoeuvre_motion,
                speed,
                ahead,
                bypass_side,
                reading.corrupt is False and boxes_fresh,
                path,
                arrow,
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
        elif (
            manoeuvre_motion is False if self.config.manoeuvres else moving is False
        ) and self._last.throttle > 0:
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
                if self.config.manoeuvres and abs(error) < 35 and reading.corrupt is False and boxes_fresh:
                    self._start_bypass(now, -1, blind=True)
                    return self._emit(0, 0, 1, "bypass-reverse")
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
        self._filtered_near = (
            near_error
            if self._filtered_near is None or previous is None
            else _angle(self._filtered_near + alpha * _angle(near_error - self._filtered_near))
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
        if self.config.yaw_memory:
            rolling = (
                (0.0 if map_moving is False else min(1.0, (4.0 if speed is None else speed) / 12.0))
                if self.config.drive_through
                else 1.0
            )
            adjusted = _angle(adjusted - rolling * self.config.yaw_memory * self._pending(now))
        bend_delta = _angle(self._filtered_far - self._filtered_near)
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
            abs(self._filtered_near),
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
        if self.config.drive_through:
            throttle, brake = self._pedal(limit, speed, now, flagged, distance)
        elif speed is None:
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
        if cfg.drive_through:
            return self._road_limit(path, speed)
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

    def _road_limit(self, path, speed):
        cfg = self.config
        limit = cfg.speed_limit
        self._brake_limit = cfg.speed_limit
        self.speed_reason = "straight"
        if len(path) < 3:
            self.speed_reason = "unknown-path"
            return cfg.slow_speed
        scale = self._map_scale(speed)
        travel = [hypot(*path[0])]
        for a, b in pairwise(path):
            travel.append(travel[-1] + hypot(b[0] - a[0], b[1] - a[1]))
        reserve = cfg.lookahead_px * scale + (speed or 0) * (cfg.command_delay + cfg.gps_window / 2)
        # A clipped straight proves only the distance in view, not an open kilometre.
        remaining = max(0.0, travel[-1] * scale - reserve)
        horizon = sqrt(cfg.junction_speed**2 + 2 * cfg.planned_deceleration * remaining)
        if horizon < limit:
            limit, self.speed_reason = horizon, "visibility"
        self._brake_limit = min(
            self._brake_limit, sqrt(cfg.junction_speed**2 + 2 * cfg.braking_deceleration * remaining)
        )
        near_corner, near_junction = None, False
        step = cfg.curve_step
        for index in range(1, len(path) - 1):
            left, right = max(0, index - step), min(len(path) - 1, index + step)
            a, b, c = path[left], path[index], path[right]
            ab, bc = hypot(b[0] - a[0], b[1] - a[1]), hypot(c[0] - b[0], c[1] - b[1])
            interior = index >= step and index + step < len(path) - cfg.curve_trim
            if min(ab, bc) < (1 if interior else 5):
                continue
            angle = abs(
                _angle(degrees(atan2(c[0] - b[0], c[1] - b[1])) - degrees(atan2(b[0] - a[0], b[1] - a[1])))
            )
            # Short end chords keep a newly visible turn, but not one pixel of rim noise.
            if not interior and angle < 30:
                continue
            cross = abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
            curvature = 2 * cross / max(ab * bc * hypot(c[0] - a[0], c[1] - a[1]), 1e-6)
            corner = max(cfg.slow_speed, sqrt(cfg.lateral_acceleration * scale / max(curvature, 1e-6)))
            if angle >= 60:
                corner = min(corner, cfg.junction_speed)
            junction = angle >= 80 and cfg.turn_speed > 0
            if junction:
                # At a right angle the route's line has a corner where the car has a junction's
                # width to turn in. A bend of sixty degrees is the road itself and keeps its speed.
                corner = max(corner, cfg.turn_speed)
            # Plan to the measured bend at b, while remembering an arc from a.
            bend_at = travel[index]
            remaining = max(0.0, bend_at * scale - reserve)
            planned = sqrt(corner * corner + 2 * cfg.planned_deceleration * remaining)
            deceleration = cfg.braking_deceleration
            self._brake_limit = min(self._brake_limit, sqrt(corner * corner + 2 * deceleration * remaining))
            if planned < limit:
                limit, self.speed_reason = planned, "curve"
            if travel[left] * scale <= max(40.0, (speed or 0) * 2):
                if near_corner is None or corner < near_corner:
                    near_corner, near_junction = corner, junction
        # Keep a genuine nearby corner while it passes under the arrow. Pixel wander
        # on a straight must not create a remembered corner during a heading correction.
        a, b = path[0], path[min(step, len(path) - 1)]
        course = degrees(atan2(b[0] - a[0], b[1] - a[1]))
        heading_error = abs(_angle(course - self._road_heading))
        if heading_error < 10:
            self._turn_limit = None
        if near_corner is not None and (self._turn_limit is None or near_corner <= self._turn_limit * 1.1):
            self._turn_junction = near_junction
            self._turn_limit = near_corner if self._turn_limit is None else min(self._turn_limit, near_corner)
            self._turn_remaining = max(2 * cfg.lookahead_px * scale, (speed or 0) * cfg.gps_window / 2)
        if self._turn_limit is not None and heading_error >= 10:
            if self._turn_limit < limit:
                limit, self.speed_reason = self._turn_limit, "curve-exit"
            # In the turn the pedal is lifted and the brake left alone: on the drive to the golf
            # club (20261114-015901) twenty of 46 brake pulses fell here, at 9 to 21 m/s, where
            # Kerim's turns are taken at 14 to 21 with no brake at all.
        if heading_error > 60:
            target = _target(path, cfg.lookahead_px)
            radius = hypot(*target) * scale
            error = radians(_angle(degrees(atan2(*target)) - self._road_heading))
            turn = max(
                cfg.slow_speed, sqrt(cfg.lateral_acceleration * radius / max(2 * abs(sin(error)), 1e-6))
            )
            if turn < limit:
                limit, self.speed_reason = turn, "hidden-turn"
            self._brake_limit = min(self._brake_limit, turn)
        return limit

    def _map_scale(self, speed):
        speed = speed or 0.0
        return max(
            self.config.map_scale_min,
            0.7 if speed < 6 else 1.0 if speed < 12 else 2.1 if speed < 18 else 3.6 if speed < 24 else 3.7,
        )

    def _pedal(self, limit, speed, now, flagged, distance):
        cfg = self.config
        if flagged:
            self.speed_reason = "flagged-map"
        if distance is not None and 0 <= distance <= cfg.arrival_distance:
            self.speed_reason = "arrival"
        if self.speed_reason == "unknown-path":
            return cfg.unknown_throttle, 0.0
        if speed is None:
            self.speed_reason = "unknown-speed"
            # Keep startup unchanged until this driver has measured speed. The
            # P104 gap trials bound the later open-road increase to one third;
            # the road limit lowers it for bends, arrival and flagged maps.
            return min(
                cfg.cruise_throttle,
                cfg.unknown_throttle * (4 / 3 if self._speed_at is not None else 1),
                cfg.unknown_throttle * limit / max(cfg.junction_speed, 1.0),
            ), 0.0
        speed = self._present_speed(speed, now)
        if self.speed_reason == "straight":
            # A noisy GPS slope may ease the pedal, but cannot brake an empty straight. The pedal
            # that holds the limit in one car carries a faster one far past it (35 m/s under a
            # limit of 22), so well above the limit it falls with the excess instead of resting.
            return _clip(
                cfg.hold_throttle + cfg.speed_gain * (cfg.speed_limit - speed),
                cfg.hold_throttle if speed <= cfg.speed_limit + STRAIGHT_EXCESS else 0.0,
                cfg.cruise_throttle,
            ), 0.0
        error = limit - speed
        # A small nonzero command is lifted above the trigger dead zone by the profile.
        # Lift completely before the bend instead of continuing to accelerate into it.
        hold = min(cfg.hold_throttle, limit * 0.05)
        # Before a bend the pedal is lifted two metres a second early. In the turn at a junction
        # there is nothing left to lift for: the car is held at the turn's speed, not let fall below.
        early = 0.0 if self.speed_reason == "curve-exit" and self._turn_junction else 2.0
        throttle = (
            _clip(hold + cfg.speed_gain * (error - early), 0, cfg.cruise_throttle) if error > 0 else 0.0
        )
        if self.speed_reason in {"arrival", "flagged-map"}:
            throttle = _clip(0.25 + cfg.speed_gain * error, 0, cfg.cruise_throttle)
        brake = 0.0
        brake_limit = limit if self.speed_reason in {"arrival", "flagged-map"} else self._brake_limit
        if speed > brake_limit + cfg.brake_margin:
            brake = _clip(cfg.brake_gain * (speed - brake_limit - cfg.brake_margin), 0, 0.7)
        # Even tiny L2 is raised past the trigger dead zone. Start a pulse only
        # with another m/s of evidence; once started it can taper down normally.
        if not self._last.brake and brake < cfg.brake_gain:
            brake = 0.0
        return throttle, self._pulsed(brake, speed, now)

    def _present_speed(self, speed: float, now: float) -> float:
        """The speed now, from a reading that still shows the car as it was before the pedal came off.

        Off the pedal the game's cars lose about 5 m/s each second (quartiles 2.8 to 6.3 over twenty such
        seconds of the night of 14 November), and while a car slows the slope of the printed distance is
        3.5 m/s above it at the median. With the pedal held off until the reading fell below a turn's
        speed the car stood before the junction (20261114-042324 at 134 to 139 s: read 15 m/s, driven 2)."""
        cfg = self.config
        dt = 0.0 if self._pedal_time is None else min(max(now - self._pedal_time, 0.0), cfg.max_step_time)
        self._pedal_time = now
        if self._last.throttle < 0.05 and dt > 0:
            self._off.append((now, dt))
        while self._off and now - self._off[0][0] > cfg.speed_lag:
            self._off.popleft()
        return max(0.0, speed - cfg.coast_loss * sum(seconds for _, seconds in self._off))

    def _pulsed(self, brake: float, speed: float, now: float) -> float:
        """L2 for speed in bounded pulses: the reading lags, and a brake held too long ends in reverse."""
        cfg = self.config
        if cfg.drive_through and cfg.brake_pulse and (brake or self._last.brake) and speed < cfg.brake_floor:
            # A requested pulse cut short by the speed floor gets its rest too;
            # GPS noise around the floor must not reopen it on the next tick.
            self._brake_since = now - cfg.brake_pulse
            return 0.0
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
        ) or (
            self.config.drive_through
            and abs(error) <= 5
            and abs(self._trusted_error) <= 5
            and _straight(_path(reading.path), self.config, False)
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

    def _manoeuvre(self, now, near_error, error, moving, speed, ahead, side, clean, path=(), arrow=0):
        active = self._phase is not None and self._phase.startswith(("bypass-", "turn-"))
        if not clean:
            if active:
                return self._emit(0, 0, 0, "coast")
            return None
        # A detached start behind the arrow can lead onto a road running ahead.
        # Use points in the car's frame, not the short aim extrapolated behind it.
        angle = radians(arrow)
        points = tuple((x * cos(angle) - y * sin(angle), x * sin(angle) + y * cos(angle)) for x, y in path)
        joining = len(points) >= 3 and points[0][1] < 0 and points[-1][1] > 20 and abs(error) < 75
        if self._phase in {"turn-join", "turn-clear", "turn-along"}:
            if len(points) < 3:
                return self._emit(0, 0, 0, "coast")
        elif joining and not active and self._phase is None and not ahead:
            self._phase, self._phase_since = "turn-join", now
            self._manoeuvre_moved = self._recovery_moved = False
            self._manoeuvre_still_since = None
            self._moving_since = None
            self._turns = 0
        if self._phase in {"turn-join", "turn-clear", "turn-along"}:
            elapsed = now - self._phase_since
            start, end = points[len(points) // 2], points[-1]
            course = _angle(degrees(atan2(end[0] - start[0], end[1] - start[1])))
            if moving is True and self._moving_since is None:
                self._moving_since = now
            moved = moving is True and now - self._moving_since >= 0.1
            if elapsed > 0.6 and moved:
                self._manoeuvre_moved = self._recovery_moved = True
            if self._phase == "turn-clear":
                if elapsed < self.config.bypass_reverse_time:
                    return self._emit(-_clip(course * 0.04), 0, 1, self._phase)
                self._phase, self._phase_since = "turn-along", now
                self._manoeuvre_moved = False
                self._manoeuvre_still_since = None
                self._moving_since = None
                elapsed = 0.0
            if elapsed > 1.5 and moving is False:
                if self._manoeuvre_still_since is None:
                    self._manoeuvre_still_since = now
            else:
                self._manoeuvre_still_since = None
            if self._manoeuvre_still_since is not None and now - self._manoeuvre_still_since >= 0.3:
                if self._turns >= self.config.max_recoveries:
                    self._phase = "failed-recovery" if self._recovery_moved else "dead-or-held"
                    return self._emit(0, 0, 0, self._phase)
                self._turns += 1
                lateral = start[0] * cos(radians(course)) - start[1] * sin(radians(course))
                self._manoeuvre_side = -1 if lateral > 0 else 1
                self._phase, self._phase_since = "turn-clear", now
                self._manoeuvre_still_since = None
                return self._emit(-_clip(course * 0.04), 0, 1, self._phase)
            if self._manoeuvre_moved and points[0][1] >= 0 and abs(points[0][0]) < 6:
                self._end_manoeuvre()
                return None
            if self._phase == "turn-join":
                target = min(
                    (p for p in points if p[1] > 0), key=lambda p: abs(p[1] - 35), default=points[-1]
                )
                course = degrees(atan2(target[0], target[1]))
            else:
                # Leave some room beside the obstruction before holding its course.
                course += self._manoeuvre_side * 8 if elapsed < 3 else 0
                steer = _clip(course * 0.04)
                return self._emit(
                    -steer if elapsed < 0.55 else steer,
                    1 if elapsed < 1.5 else self.config.recovery_throttle,
                    0,
                    self._phase,
                )
            steer = _clip(course * 0.04) if abs(course) > 3 else 0
            return self._emit(steer, self.config.recovery_throttle, 0, self._phase)
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
                chosen = side or (1 if error >= 0 else -1)
                self._start_bypass(now, chosen, blind=False)
            elif abs(near_error) > 120 and abs(error) > 120 and slow and not ahead:
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
            self._recovery_moved = False
            self._moving_since = None
            self._recovery_distance = 0.0
        elapsed = now - self._phase_since
        if moving is True and self._moving_since is None:
            self._moving_since = now
        moved = moving is True and now - self._moving_since >= 0.1
        settling = 1.5 if self._phase.endswith("forward") else 0.6
        if elapsed > settling:
            self._manoeuvre_moved |= moving is True
        if elapsed > 0.6 and moved:
            self._recovery_moved = True
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
                self._reverse_duration if self._phase == "bypass-reverse" else self.config.turn_reverse_time
            )
            if not self._phase.endswith("reverse") or elapsed < bound:
                return self._emit(0, 0, 0, self._phase)
        if self._phase == "bypass-reverse":
            if elapsed < self._reverse_duration - 1e-9 and not blocked:
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
            self._moving_since = None
            elapsed, blocked = 0.0, False
        if self._phase == "bypass-forward":
            if blocked:
                return self._retry_bypass(now)
            if not self._bypass_blind and ((not ahead and elapsed > 1.2 and moved) or elapsed >= 4.5):
                self._end_manoeuvre()
                return self._emit(0, 0.8, 0, "follow")
            # Losing the box during the gear change is not passing the car.
            # Later attempts hold a different arc as well as changing sides.
            lock_time = 2.6 + 0.3 * min(2, (self._bypass_attempts - 1) // 2)
            if moved and elapsed >= lock_time and (not ahead or elapsed >= 4.5):
                self._phase, self._phase_since = "bypass-pass", now
                self._bypass_distance = self._recovery_distance
                self._manoeuvre_still_since = None
            else:
                steer = (
                    -self._manoeuvre_side if self._bypass_blind and elapsed < 0.55 else self._manoeuvre_side
                )
                return self._emit(steer, 1, 0, self._phase)
        if self._phase == "bypass-pass":
            if blocked:
                return self._retry_bypass(now)
            if elapsed >= 6:
                self._end_manoeuvre()
                return self._emit(0, 0.8, 0, "follow")
            if moved and self._recovery_distance - self._bypass_distance >= 6:
                self._end_manoeuvre()
                return None
            # Keep abreast of the obstruction before the near route pulls back
            # into its flank. The far route supplies the road's onward heading.
            return self._emit(_clip(error * 0.04), 1, 0, self._phase)
        if self._phase == "turn-forward":
            # The same far heading starts, steers and finishes the turn. A changed
            # route or an unmoving car cannot turn the gear-change pause into success.
            elapsed = now - self._phase_since
            if elapsed > 0.6 and moved:
                self._manoeuvre_moved = True
            if abs(error) < 25 and elapsed >= 1.0 and self._manoeuvre_moved and moved:
                self._turns = 0
                self._end_manoeuvre()
                return None
            if elapsed >= 4.0 or blocked:
                if self._turns >= 3 or self._attempts >= self.config.max_recoveries:
                    self._phase = "failed-recovery" if self._recovery_moved else "dead-or-held"
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
        self._turns = 0
        self._manoeuvre_moved = False
        self._manoeuvre_still_since = None
        self._stuck_since = self._moving_since = None
        self._error = self._filtered_error = self._filtered_near = self._filtered_far = None
        self._steer = 0.0

    def _start_bypass(self, now, side, *, blind):
        if self._attempts == 0:
            self._bypass_attempts = 0
        self._attempts += 1
        self._manoeuvre_side = side if self._bypass_attempts == 0 else -self._manoeuvre_side
        self._bypass_attempts += 1
        self._bypass_blind = blind
        # A detected queue can leave room; an unseen obstruction was hit. Twice
        # the 0.9 s clearance buys its width, still below generic recovery's
        # previous 2.5 s ceiling. A confirmed rear stop cuts either bound short.
        self._reverse_duration = self.config.bypass_reverse_time * (2 if blind else 1)
        self._phase, self._phase_since = "bypass-reverse", now
        self._manoeuvre_moved = self._recovery_moved = False
        self._manoeuvre_still_since = None
        self._stuck_since = self._moving_since = None
        self._recovery_distance = 0.0

    def _retry_bypass(self, now):
        if self._attempts >= self.config.max_recoveries:
            self._phase = "failed-recovery"
            return self._emit(0, 0, 0, self._phase)
        self._start_bypass(now, -self._manoeuvre_side, blind=True)
        return self._emit(0, 0, 1, self._phase)

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


def _onward(path, config, was: bool, heading: float) -> bool:
    """Whether the path's beginning goes on from the car: in the direction in which its first point
    lies from it, or in the direction the car is heading.

    The beginning is taken over one and a half times the short aim's length, so that a pixel of
    wander in one point does not decide it, and once it holds it holds until the directions differ
    by a third more. A corner under the arrow shows as a path that begins round it: its first point lies
    to one side and its beginning runs across the car's way, by 33 degrees and more against the line
    to that point for a right angle 6 px ahead or nearer, and by the corner's angle against the
    heading. A car beside a straight route is heading its way, however far off it is, and is brought
    back in a flatter curve than the short aim's.
    """
    span = 1.5 * config.lookahead_px
    if config.bend_lookahead_px <= config.lookahead_px or len(path) < 2:
        return False
    start, travelled, previous, end = path[0], 0.0, path[0], None
    for point in path[1:]:
        step = hypot(point[0] - previous[0], point[1] - previous[1])
        if step > 0 and travelled + step >= span:
            fraction = (span - travelled) / step
            end = tuple(a + fraction * (b - a) for a, b in zip(previous, point, strict=True))
            break
        travelled, previous = travelled + step, point
    if end is None or hypot(*start) <= 0:
        return False
    leg = degrees(atan2(start[0], start[1]))
    onward = degrees(atan2(end[0] - start[0], end[1] - start[1]))
    limit = config.onward_bend * (4 / 3 if was else 1.0)
    return abs(_angle(onward - leg)) < limit or abs(_angle(onward - heading)) < limit


def _target(path, radius: float, heading: float | None = None):
    """The point to steer at, `radius` from the car along the route.

    The route's first `path_hidden` pixels lie under the arrow. Where the aim is nearer than the
    path's first point, the path's first segment is continued back under the arrow as a line. With
    `heading`, the car's own direction on the map, the hidden stretch is taken to run from the car
    along that direction to where it meets that line, and along the line from there: while the
    meeting point lies ahead, further off than the aim, the aim lies straight ahead. Without it,
    and where the two do not meet ahead of the car and before the path's first point, the aim is
    on the line, at its nearest point until the circle reaches it. The first reading is right for
    a corner or a bend ahead, visible or under the arrow; the second for a car beside its route. By
    the second alone, the right turn of 13 November, 18:32, whose beginning leaned to the right 13
    px ahead of the car, was steered at 6 to 28 degrees to the left: the line that continued that
    lean backwards passed the car on its left.
    """
    previous = path[0]
    if len(path) >= 2 and hypot(*previous) > radius:
        # Continue only the first visible straight segment under the arrow.
        # This short aiming point avoids cutting a wide corner as the map zooms.
        x, y = previous
        dx, dy = path[1][0] - x, path[1][1] - y
        length = hypot(dx, dy)
        if length > 0:
            dx, dy = dx / length, dy / length
            if heading is not None:
                hx, hy = sin(radians(heading)), cos(radians(heading))
                cross = dx * hy - dy * hx
                if abs(cross) > 1e-6:
                    ahead = (dx * y - dy * x) / cross  # along the heading to the line
                    before = (hx * y - hy * x) / cross  # from the first point along the line, back negative
                    if ahead >= radius and before <= 0:
                        return radius * hx, radius * hy
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
