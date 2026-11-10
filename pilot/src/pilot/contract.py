"""What the parts of the pilot hand to each other.

A frame is 1280x720 RGB. The HUD crop is the bottom-left corner that holds the minimap: `HUD_RECT` of the
frame, a 170 x 260 x 3 uint8 RGB array (for other resolutions the same fractions, resized to 260x170).

Angles are degrees in the picture: 0 = straight up, positive = clockwise (to the right), range (-180, 180].
"""

from __future__ import annotations

from dataclasses import dataclass

FRAME_SIZE = (1280, 720)
HUD_RECT = (30, 530, 260, 170)  # x, y, w, h of the HUD crop in a 1280x720 frame
ARROW_XY = (123, 117)  # where the player arrow sits in the crop, roughly; verify before relying on it
NEAR_R, FAR_R = 30, 60  # radii in crop pixels of the two circles around the arrow, see `bearing`


@dataclass(frozen=True)
class Blip:
    """An observed circular map marker, in pixels relative to the player."""

    color: str
    x: float
    y: float
    border: bool = False


@dataclass(frozen=True)
class Reading:
    # "none" (cutscene, black, menu, big map) | "flat" (on foot, top-down) | "tilted" (in a vehicle)
    minimap: str
    route: str  # "none" | "yellow" (mission route) | "purple" (waypoint set by the player)
    # direction from the arrow to the point where the route, followed from the arrow, crosses the circle
    # of radius NEAR_R around the arrow; if the route ends earlier, its end point. None without a route.
    bearing: float | None
    far_bearing: float | None  # the same for radius FAR_R
    arrow: float | None  # where the player arrow points; None if it cannot be read
    corrupt: bool  # the picture is damaged by the stream (smeared or misplaced blocks)
    confidence: float  # 0..1, how far to trust `route` and `bearing`
    # Ordered route samples in map pixels relative to the arrow: x right, y up.
    path: tuple[tuple[float, float], ...] = ()
    gps_distance: float | None = None  # Remaining route distance in metres.
    gps_arrow: str | None = None  # Printed next turn, separate from the vehicle arrow.
    gps_speed: float | None = None  # Causal distance slope in metres per second.
    gps_time: float | None = None  # Capture time of the last accepted distance.
    blips: tuple[Blip, ...] = ()


@dataclass(frozen=True)
class Detection:
    """One object the local detector sees in the frame. The player's own figure or vehicle is not reported."""

    kind: str  # "person" | "car" | "truck" | "bus" | "motorcycle" | "bicycle"
    box: tuple[float, float, float, float]  # x0, y0, x1, y1 in pixels of the 1280x720 frame
    confidence: float  # 0..1


@dataclass(frozen=True)
class Hud:
    """What the game shows besides the minimap. None means the value could not be read."""

    wanted: int | None = None  # stars shown, 0..5
    wanted_flashing: bool = False  # the stars blink while the police have lost sight of the player
    health: float | None = None  # filled fraction of the green bar under the minimap, 0..1
    armour: float | None = None  # the blue bar
    special: float | None = None  # the yellow bar
    # "game" | "pause" | "map" | "weapon_wheel" | "phone" | "failed" | "passed" | "wasted" | "busted" |
    # "loading"; a screen other than "game" means the character does not take ordinary input
    screen: str = "game"


@dataclass(frozen=True)
class Command:
    """One controller state for the car. The runtime maps it to the pad: left stick x, R2, L2."""

    steer: float  # -1 = full left .. +1 = full right
    throttle: float  # 0..1
    brake: float  # 0..1; held on a standing car it reverses
    state: str  # what the driver is doing, for the log and the overlay: "idle", "follow", "coast", ...


NEUTRAL = Command(0.0, 0.0, 0.0, "idle")


@dataclass(frozen=True)
class Pad:
    """Complete controller state; no state is inherited from a previous tick."""

    buttons: tuple[str, ...] = ()
    left: tuple[float, float] = (0.0, 0.0)
    right: tuple[float, float] = (0.0, 0.0)
    l2: float = 0.0
    r2: float = 0.0

    @classmethod
    def from_command(cls, command: Command) -> Pad:
        return cls(left=(command.steer, 0.0), l2=command.brake, r2=command.throttle)

    def payload(self) -> dict:
        return {
            "buttons": list(self.buttons),
            "left": list(self.left),
            "right": list(self.right),
            "l2": self.l2,
            "r2": self.r2,
            "ttl_ms": 250,
        }


NEUTRAL_PAD = Pad()
