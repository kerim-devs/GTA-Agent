"""Defensive minimap feedback controller; no speed sensor or external state."""

from dataclasses import dataclass
from math import isfinite

from pilot.contract import NEUTRAL, Command, Reading


@dataclass(frozen=True)
class DriveConfig:
    """Times are seconds, angles degrees, controls normalized.

    Lower steer_gain / increase steer_smoothing for weaving. Increase corner_bias
    for early corner cutting. Lower bend_throttle or increase bend_gain for late braking.
    command_delay estimates capture-to-actuation delay. brake acts as reverse once
    stopped, as in the game's pedal controls. A fresh Driver resets a failed run.
    """

    steer_gain: float = 0.035  # Heading error to stick deflection per degree.
    steer_zero: float = 0.005  # Snap a decayed stick to zero below this magnitude.
    max_step_time: float = 0.5  # Bound feedback integration after a scheduling pause.
    steer_smoothing: float = 0.2  # Low-pass time constant for stick output.
    bearing_smoothing: float = 0.4  # Reject rapid angle noise before feedback.
    steer_deadband: float = 2.0  # Ignore small filtered heading errors.
    steering_bias: float = 0.25  # Minimum active stick to tolerate a physical dead zone.
    corner_bias: float = 7.0  # Delay early corner cutting indicated by far-near angle.
    command_delay: float = 0.21  # Capture-to-control latency used for prediction.
    prediction_limit: float = 8.0  # Maximum angle extrapolation across the delay.
    cruise_throttle: float = 0.58  # Pedal on a straight, legible route.
    bend_throttle: float = 0.22  # Minimum pedal while following a bend.
    bend_gain: float = 0.013  # Pedal reduction per degree of upcoming bend.
    confidence_min: float = 0.5  # Lowest accepted perception confidence.
    hold_time: float = 0.3  # Last follow command survives only this long without evidence.
    route_gone_time: float = 2.0  # Time of observed route absence before stopping.
    stuck_time: float = 2.0  # Throttle plus explicitly absent movement before escape.
    reverse_time: float = 1.25  # Duration of the reverse pedal phase.
    forward_time: float = 2.5  # Forward escape observation window.
    recovery_clear_time: float = 2.0  # Sustained forward motion clears failed-attempt count.
    recovery_steer: float = 0.8  # Stick magnitude used to reverse away from the route.
    recovery_throttle: float = 0.45  # Forward pedal during escape.
    max_recoveries: int = 3  # Consecutive failed escapes before a latched stop.
    outlier_angle: float = 60.0  # Abrupt jumps larger than this require persistence.
    outlier_window: float = 0.3  # Accept a persistent new direction after this interval.
    stop_brake_time: float = 0.7  # Bound L2 use so a stop cannot become indefinite reverse.

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                raise ValueError(f"{name} must be finite")
            if value < 0:
                raise ValueError(f"{name} must be nonnegative")
        for name in (
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
        self._last_good: float | None = None
        self._missing_duration = 0.0
        self._missing_observed_at: float | None = None
        self._route_stop_time: float | None = None
        self._route_stopped = False
        self._error: float | None = None
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
        self._escape = 0.0

    def _emit(self, steer: float, throttle: float, brake: float, state: str) -> Command:
        self._last = Command(_clip(steer), _clip(throttle, 0), _clip(brake, 0), state)
        return self._last

    def _idle(self) -> Command:
        self._last_good = self._missing_observed_at = self._route_stop_time = None
        self._missing_duration = 0.0
        self._route_stopped = False
        self._error = self._outlier_since = None
        self._filtered_error = self._filtered_far = self._moving_since = None
        self._stuck_since = None
        self._steer = 0.0
        if self._phase != "failed-recovery":
            self._phase = None
        return self._emit(0, 0, 0, "idle")

    def _coast(self, now: float) -> Command:
        if self._last_good is not None and now - self._last_good <= self.config.hold_time:
            if self._last.state in {"follow", "coast", "recovery-reverse", "recovery-forward"}:
                return self._emit(self._last.steer, self._last.throttle, self._last.brake, "coast")
        self._steer = 0.0
        self._stuck_since = None
        if self._phase != "failed-recovery":
            self._phase = None
        return self._emit(0, 0, 0, "coast")

    def step(self, reading: Reading, t: float, moving: bool | None = None) -> Command:
        """Return bounded controls; invalid/backwards clocks release and reset timers.

        Unknown motion never means stuck. A failure latch survives clock changes.
        Picture angles minus the arrow give camera-independent heading errors.
        """
        moving = moving if isinstance(moving, bool) else None
        if moving is not True:
            self._moving_since = None
        now = _number(t)
        if now is None or (self._time is not None and now < self._time):
            self._time = now
            return self._idle()
        dt = 0.0 if self._time is None else min(now - self._time, self.config.max_step_time)
        self._time = now
        if (
            not isinstance(reading, Reading)
            or not isinstance(reading.minimap, str)
            or reading.minimap != "tilted"
        ):
            return self._idle()
        if self._phase == "failed-recovery":
            return self._emit(0, 0, 0, "failed-recovery")
        confidence = _number(reading.confidence)
        if (
            reading.corrupt is not False
            or confidence is None
            or not self.config.confidence_min <= confidence <= 1
        ):
            self._missing_observed_at = None
            return self._coast(now)
        if not isinstance(reading.route, str):
            return self._coast(now)
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
            return self._coast(now)
        error = _angle(_angle(near) - _angle(arrow))
        far_error = error if far is None else _angle(_angle(far) - _angle(arrow))
        if self._error is not None and abs(_angle(error - self._error)) > self.config.outlier_angle:
            if self._outlier_since is None:
                self._outlier_since = now
            if now - self._outlier_since < self.config.outlier_window:
                return self._coast(now)
        self._outlier_since = None
        self._last_good = now

        if self._phase == "recovery-reverse":
            if now - self._phase_since < self.config.reverse_time:
                return self._emit(self._escape, 0, 1, "recovery-reverse")
            self._phase, self._phase_since = "recovery-forward", now
        if self._phase == "recovery-forward":
            if moving is True:
                if self._moving_since is None:
                    self._moving_since = now
                if now - self._moving_since >= self.config.recovery_clear_time:
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
                        ),
                        self.config.recovery_throttle,
                        0,
                        "recovery-forward",
                    )
                if moving is not False:
                    self._phase = None
                elif self._attempts >= self.config.max_recoveries:
                    self._phase = "failed-recovery"
                    return self._emit(0, 0, 0, "failed-recovery")
                else:
                    return self._recover(now, error)

        if moving is False and self._last.throttle > 0:
            if self._stuck_since is None:
                self._stuck_since = now
            if now - self._stuck_since >= self.config.stuck_time:
                if self._attempts >= self.config.max_recoveries:
                    self._phase = "failed-recovery"
                    return self._emit(0, 0, 0, "failed-recovery")
                return self._recover(now, error)
        else:
            self._stuck_since = None

        if moving is True and self._last.throttle > 0:
            if self._moving_since is None:
                self._moving_since = now
            if now - self._moving_since >= self.config.recovery_clear_time:
                self._attempts = 0
        else:
            self._moving_since = None
        previous = self._filtered_error
        alpha = 1.0 if previous is None else dt / max(dt + self.config.bearing_smoothing, 1e-9)
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
        adjusted = self._filtered_error + correction
        bend_delta = _angle(self._filtered_far - self._filtered_error)
        if adjusted * bend_delta > 0:
            adjusted -= _clip(self.config.corner_bias * bend_delta, -abs(adjusted), abs(adjusted))
        adjusted = (1 if adjusted >= 0 else -1) * max(0.0, abs(adjusted) - self.config.steer_deadband)
        target = _clip(self.config.steer_gain * adjusted)
        if target:
            target = (1 if target > 0 else -1) * (
                self.config.steering_bias + (1 - self.config.steering_bias) * abs(target)
            )
        alpha = 1.0 if self._error is None else dt / max(dt + self.config.steer_smoothing, 1e-9)
        self._steer += alpha * (target - self._steer)
        if abs(self._steer) < self.config.steer_zero and target == 0:
            self._steer = 0.0
        bend = max(abs(self._filtered_error), abs(self._filtered_far), abs(bend_delta))
        throttle = max(self.config.bend_throttle, self.config.cruise_throttle - self.config.bend_gain * bend)
        self._error = error
        return self._emit(self._steer, throttle, 0, "follow")

    def _recover(self, now: float, error: float) -> Command:
        self._attempts += 1
        self._phase, self._phase_since = "recovery-reverse", now
        self._escape = -self.config.recovery_steer if error >= 0 else self.config.recovery_steer
        self._stuck_since = self._moving_since = None
        return self._emit(self._escape, 0, 1, "recovery-reverse")
