"""Game-specific actions and outbound stick and pedal calibration."""

from dataclasses import dataclass, replace
from math import copysign
from typing import ClassVar

from .contract import Pad


@dataclass(frozen=True)
class Profile:
    name: str
    sprint: str
    sprint_held: bool
    enter_vehicle: str = "triangle"
    melee: str = "circle"
    cover: str = "r1"
    pause: str = "options"
    confirm: str = "cross"
    back: str = "circle"
    retry: str = "cross"
    left_dead_zone: float = 0.0
    right_dead_zone: float = 0.3
    # Measured in a car on 11 November (lab/pedal): held for three seconds the accelerator moves
    # nothing at 0.33 and the car at 0.36. Every pedal value the driver asks for below its cruise
    # lay under that, and the car stood still until the driver took it for stuck and reversed.
    # The brake is the same kind of trigger and is taken to answer the same way.
    trigger_dead_zone: float = 0.35

    # Kerim sprints by tapping, never by holding: on 224 stretches of his recordings with 4,377
    # presses the button is down for 0.11 s and up for 0.10 s at the median, no press over a second.
    SPRINT_DOWN: ClassVar[float] = 0.11
    SPRINT_PERIOD: ClassVar[float] = 0.21

    def sprint_buttons(self, elapsed: float) -> tuple[str, ...]:
        if self.sprint_held or elapsed % self.SPRINT_PERIOD < self.SPRINT_DOWN:
            return (self.sprint,)
        return ()

    def shape(self, pad: Pad) -> Pad:
        return replace(
            pad,
            left=tuple(_component(value, self.left_dead_zone) for value in pad.left),
            right=tuple(_component(value, self.right_dead_zone) for value in pad.right),
            l2=_component(pad.l2, self.trigger_dead_zone),
            r2=_component(pad.r2, self.trigger_dead_zone),
        )

    def right_for(self, sent: float) -> float:
        """The request that leaves as `sent` on the right stick, for a value measured at the console."""
        zone = self.right_dead_zone
        if zone == 0:
            return sent
        return copysign(max(NOISE_FLOOR, (abs(sent) - zone) / (1.0 - zone)), sent)


NOISE_FLOOR = 0.02


def _component(value: float, dead_zone: float) -> float:
    # An unmeasured stick (zero dead zone) must keep its existing behavior.
    if dead_zone == 0:
        return value
    if abs(value) < NOISE_FLOOR:
        return 0.0
    return copysign(min(1.0, dead_zone + (1.0 - dead_zone) * abs(value)), value)


GTA5 = Profile(name="gta5", sprint="cross", sprint_held=False)
# All GTA VI bindings and calibration are unconfirmed placeholders.
GTA6 = Profile(name="gta6", sprint="l3", sprint_held=True)
PROFILES = {profile.name: profile for profile in (GTA5, GTA6)}
_active = GTA5


def active() -> Profile:
    return _active


def use(name: str) -> Profile:
    """Select the profile for subsequently created skills and runtimes."""
    global _active
    try:
        selected = PROFILES[name]
    except KeyError:
        raise ValueError(f"Unknown game profile: {name}") from None
    _active = selected
    return selected
