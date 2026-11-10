"""What a minimap reader returns. An implementation is a module with `read(crop) -> Reading`.

`crop` is the bottom-left HUD corner of a GTA V frame, cut at x 30..290, y 530..700 of a 1280x720 frame
(for other resolutions the same fractions, resized to 260x170): a 170 x 260 x 3 uint8 RGB array.

Angles are degrees in the picture: 0 = straight up, positive = clockwise (to the right), range (-180, 180].
"""

from __future__ import annotations

from dataclasses import dataclass

ARROW_XY = (123, 117)  # where the player arrow sits in the crop, roughly; verify before relying on it
NEAR_R, FAR_R = 30, 60  # radii in crop pixels of the two circles around the arrow, see `bearing`


@dataclass(frozen=True)
class Reading:
    minimap: str  # "none" (cutscene, black, menu, big map) | "flat" (on foot, top-down) | "tilted" (in a vehicle)
    route: str  # "none" | "yellow" (mission route) | "purple" (waypoint set by the player)
    # direction from the arrow to the point where the route, followed from the arrow, crosses the circle
    # of radius NEAR_R around the arrow; if the route ends earlier, its end point. None without a route.
    bearing: float | None
    far_bearing: float | None  # the same for radius FAR_R
    arrow: float | None  # where the player arrow points; None if it cannot be read
    corrupt: bool  # the picture is damaged by the stream (smeared or misplaced blocks)
    confidence: float  # 0..1, how far to trust `route` and `bearing`
