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


@dataclass(frozen=True)
class Command:
    """One controller state for the car. The runtime maps it to the pad: left stick x, R2, L2."""

    steer: float  # -1 = full left .. +1 = full right
    throttle: float  # 0..1
    brake: float  # 0..1; held on a standing car it reverses
    state: str  # what the driver is doing, for the log and the overlay: "idle", "follow", "coast", ...


NEUTRAL = Command(0.0, 0.0, 0.0, "idle")
