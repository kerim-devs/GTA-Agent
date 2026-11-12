"""Gamepad attached to this computer (DualSense over USB or Bluetooth), read through SDL2.

SDL's GameController API names buttons the same way for every connection type, so one mapping
covers USB and Bluetooth (graph `ps5-agent-bridge`, node #20).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .backend import Button, Side

STICK_DEADZONE = 0.08
# A stick at rest is not a person. Kerim's DualSense rests at up to 0.11 on an axis (his recordings
# of 12 November): lying connected it held the bridge for itself, kept a recording running and passed
# its drift on to the console. So a stick whose whole deflection stays under this is at rest; one
# that is moved further is passed on axis by axis as before.
STICK_REST = 0.18
AXIS_MAX = 32767.0


@dataclass(frozen=True)
class PadState:
    buttons: frozenset[Button] = frozenset()
    sticks: dict[Side, tuple[float, float]] = field(
        default_factory=lambda: {Side.LEFT: (0.0, 0.0), Side.RIGHT: (0.0, 0.0)}
    )
    triggers: dict[Side, float] = field(default_factory=lambda: {Side.LEFT: 0.0, Side.RIGHT: 0.0})

    @property
    def idle(self) -> bool:
        return (
            not self.buttons
            and all(v == (0.0, 0.0) for v in self.sticks.values())
            and not any(self.triggers.values())
        )

    def as_dict(self) -> dict:
        """The same shape a control loop posts to `/pad`."""
        return {
            "buttons": sorted(b.value for b in self.buttons),
            "left": list(self.sticks[Side.LEFT]),
            "right": list(self.sticks[Side.RIGHT]),
            "l2": self.triggers[Side.LEFT],
            "r2": self.triggers[Side.RIGHT],
        }


IDLE = PadState()


def _axis(raw: int) -> float:
    value = max(-1.0, min(1.0, raw / AXIS_MAX))
    return 0.0 if abs(value) < STICK_DEADZONE else round(value, 2)


def _stick(raw_x: int, raw_y: int) -> tuple[float, float]:
    if math.hypot(raw_x, raw_y) / AXIS_MAX < STICK_REST:
        return (0.0, 0.0)
    return (_axis(raw_x), _axis(raw_y))


def _trigger(raw: int) -> float:
    value = max(0.0, min(1.0, raw / AXIS_MAX))
    return 0.0 if value < STICK_DEADZONE else round(value, 2)


def state_from_sdl(pressed: set[str], axes: dict[str, int]) -> PadState:
    """`pressed`: SDL button names without the SDL_CONTROLLER_BUTTON_ prefix; `axes`: raw SDL axis values."""
    buttons = frozenset(BUTTONS[name] for name in pressed if name in BUTTONS)
    return PadState(
        buttons,
        {
            Side.LEFT: _stick(axes.get("LEFTX", 0), axes.get("LEFTY", 0)),
            Side.RIGHT: _stick(axes.get("RIGHTX", 0), axes.get("RIGHTY", 0)),
        },
        {Side.LEFT: _trigger(axes.get("TRIGGERLEFT", 0)), Side.RIGHT: _trigger(axes.get("TRIGGERRIGHT", 0))},
    )


# SDL names follow the Xbox layout by position: A is the bottom face button (cross on a DualSense).
BUTTONS = {
    "A": Button.CROSS,
    "B": Button.CIRCLE,
    "X": Button.SQUARE,
    "Y": Button.TRIANGLE,
    "BACK": Button.CREATE,
    "GUIDE": Button.PS,
    "START": Button.OPTIONS,
    "LEFTSTICK": Button.L3,
    "RIGHTSTICK": Button.R3,
    "LEFTSHOULDER": Button.L1,
    "RIGHTSHOULDER": Button.R1,
    "DPAD_UP": Button.UP,
    "DPAD_DOWN": Button.DOWN,
    "DPAD_LEFT": Button.LEFT,
    "DPAD_RIGHT": Button.RIGHT,
    "TOUCHPAD": Button.TOUCHPAD,
}
AXES = ("LEFTX", "LEFTY", "RIGHTX", "RIGHTY", "TRIGGERLEFT", "TRIGGERRIGHT")
