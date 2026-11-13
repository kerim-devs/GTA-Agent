"""Walking to a point on foot: the waypoint or a blip. Distances are minimap pixels only."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import ClassVar

import numpy as np

from . import ahead, sides
from .ahead import SEEN
from .breath import Breath
from .contract import NEUTRAL_PAD, Blip, Observation, Pad, SkillResult, player_mode
from .foot import hud_crop, road_position, stick_for
from .profile import active
from .waymark import Spot, find_waypoint, way_by_road
from .wayround import WayRound


def _turn(degrees: float) -> float:
    """An angle as the shorter turn, from -180 to 180."""
    return (degrees + 180.0) % 360.0 - 180.0


class WalkTo:
    name = "walk_to_point"
    # Kerim, 12 November: he sprints most of the way (four parts in five by his own word) and walks
    # only when he has time, and on foot the game draws no line, so the walker finds the road on
    # the map itself. Both are what the skill does unless it is told otherwise.
    parameters: ClassVar = {
        "color": ("purple", "yellow", "blue", "red"),
        "duration": (1.0, 180.0, 180.0),
        "radius": (1.0, 12.0, 4.0),
        "sprint": (True, False),
        "roads": (True, False),
        "side": (False, True),
        "exact": (True, False),
    }
    prompt = (
        "Go on foot to the purple waypoint, or the nearest blip of color, for up to 180 s, sprinting "
        "unless sprint=false. roads=true keeps to the map's roads, side=true to their side and off "
        "the carriageway at the end. Done within radius map pixels or when the game removes a near "
        "waypoint; exact=true goes on to the place's symbol. Climbs or walks round obstacles."
    )
    SETTLE = 0.6
    LOST_AFTER = 3.0
    ROAD_FALLBACK = True
    PLAN_EVERY = 0.15  # seconds between two looks for the way on the map; the map turns with the camera
    DIRECT_WITHIN = 15.0  # map pixels: this near, the last steps go straight at the point
    # Degrees between two looks that are taken for another way and not for the same way a little
    # further on. Replayed over six walks of 13 November, 288 s: with 60 degrees the way turned by
    # more than 25 within a third of a second 39 times, with 20 nine times.
    OTHER_WAY = 20.0
    OTHER_WAY_PLANS = 5
    # Degrees a second the stick turns to a new direction: a thumb's speed, a quarter of a second
    # for a street corner, where the planner names the new direction from one tick to the next.
    TURN_RATE = 300.0
    # The game takes a waypoint off the map before the figure reaches it: on the console on
    # 12 November at 33 and at 31 map pixels, the figure sprinting. A marker last seen inside the
    # map this close and then gone counts as reached.
    GONE_WITHIN = 40.0
    HOLD = 2.0  # seconds the walk keeps its direction while an icon lies over the marker
    # Seconds the stick is kept over ticks that say nothing, a damaged or repeated frame. Of the
    # 131 such stretches in the walk of 13 November, 00:11, one was longer than half a second, 0.7 s,
    # and at half a second the figure stood for a quarter of one.
    COAST = 1.0
    BLIND = 5.0  # seconds of such ticks in a row after which the walk gives up
    # After the marker has gone the walk goes on to where it was: for as long as the last distance
    # takes at the rate the marker came nearer that evening (64 map pixels in 15 s of sprinting;
    # 7.4 in 8.4 s of walking, not straight at it), and never longer than CARRY_MAX.
    SPRINT_PACE, WALK_PACE = 4.3, 0.9
    CARRY_MAX = 6.0
    # After half a minute without an input the game shows the scene from changing cameras, and the
    # map turns with each of them. The third run of 12 November began under that view and the stick
    # swung three times in five seconds. Where the detector does not see the figure in its place
    # on the first tick, the camera is touched first and the walk waits for the game's own view.
    WAKE_PUSH, WAKE = 0.2, 0.45
    # A target behind the figure is first brought before the camera. Pushed toward at once, the
    # figure runs at the camera, the game swings the camera round behind it, the marker passes the
    # map's lower rim where it goes unread, and the stick, which is the camera's, points somewhere
    # else on every tick: on 13 November, 00:45, three swings in the first two seconds. The camera
    # turns at about 15 degrees a second and 133 more for a whole stick.
    FACE_FIRST, FACE_DONE, FACE_MAX = 100.0, 25.0, 2.5
    SEARCH_AFTER = 0.5  # seconds without any marker after which the camera is turned to look for it
    # The place under a waypoint that the game has removed (see `waymark.Spot`): looked for once
    # the marker has been gone this long, since by day the marker goes unread for up to a third
    # of a second while it is there; reached when its symbol is this near the arrow, which then
    # covers it, or when the figure is held up this near it, by the place's own wall.
    GONE_FOR, AT_PLACE, AT_WALL = 0.35, 9.0, 13.0
    SPOT_TRIES = 3
    SPOT_LOST = 10  # ticks in a row without the symbol
    ASIDE_MAX = 2.5  # seconds the figure is walked off the carriageway at the end
    # A figure that is not on foot before the walk's first step is waited for this long, as it is
    # before the camera is levelled: over a road that lies along the map's upper edge the reader
    # held "tilted" for as long as the figure stood (12 November, 23:44, right after the camera was
    # touched), and a judge that was looking at the game's scenery needs a second to take its
    # word back.
    FOOT_SETTLE = 3.0
    # A figure knocked down is not on its feet either, and is again a few seconds later: run over
    # by a pickup on 13 November, 01:04, it lay beside the truck, the judge no longer called it on
    # foot, and the walk ended while it was getting up. While the map is still on the screen the
    # walk waits this long with the stick let go; without a map it is a scene (SCENE, below).
    KNOCKED = 4.0
    DAMAGED_MAX = 15.0  # seconds in a row a walk goes on by its own marker through damaged pictures
    SPOT_STALL = 4.0  # seconds a followed symbol may fail to come nearer before it is let go
    # A walk under way that loses the map is being shown a scene: on 13 November, 02:28, the walk
    # ran in at the barber's door, the game showed the shop's welcome for more than seven seconds,
    # and the walk ended after five as "nothing readable". A scene is waited out, with nothing on
    # the pad, and after it the model is asked where the figure is before anything is pushed.
    SCENE, SCENE_MIN = 15.0, 1.0
    # The place the figure is in, asked of the local model once a second while the figure runs
    # free (see `ahead`: outdoors on 61 of 61 frames of the night's walks, a room on 31 of 31 in
    # the barber's, an answer in 0.15 s). Outdoors and then, twice running, in a room: the figure
    # has run into a building, and the guard takes it back out the way it came (Kerim, 13
    # November). A walk that begins in a room has the way out looked for before its first step.
    PLACE_EVERY, PLACE_WAIT = 1.0, 2.0
    INDOORS = 0.9  # what the model has to give "a room" for the walk to act on it
    # A room is asked about once more before it counts, of a later picture: under the barber's
    # porch, the figure against the shop's window, one frame in 35 was called a room (0.99) and
    # the next, a second later, was not (0.06). On the 86 frames of two walks in the open, none.
    PLACE_AGAIN = 0.3
    ENTRIES = 3  # times a walk is taken out of a building or a room; at the next it gives up

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("unknown walk_to arguments")
        for key in ("duration", "radius"):
            low, high, default = self.parameters[key]
            value = args.get(key, default)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be a finite number")
            if not math.isfinite(value):
                raise ValueError(f"{key} must be a finite number")
            setattr(self, key, max(low, min(high, value)))
        self.color = args.get("color", "purple")
        if self.color not in self.parameters["color"]:
            raise ValueError("unknown blip color")
        for key in ("sprint", "roads", "side", "exact"):
            value = args.get(key, self.parameters[key][0])
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be boolean")
            setattr(self, key, value)
        self.limit = float(self.duration)
        self.profile = active()
        self.guard = WayRound(sides=sides.active(), ahead=ahead.active())
        self.where = ahead.place()
        self.where_asked = None  # when the model was asked for the place and has not answered
        self.where_at = -math.inf  # when it last answered
        self.outdoors = False  # the figure has been outdoors on this walk, as far as the model said
        self.room_at = None  # when an answer called the place a room, and one more decides
        self.entries = 0  # times the guard has been sent to take the figure out of a building
        self.backs = 0  # of them, back the way it came
        self.unpushed = self.skipped = False  # ticks since the guard's last step that were not its
        self.nomap_since = None
        self.scene = None  # until when the walk stands after a scene, for the model's word on the place
        self.breath = Breath()
        self.winded = False  # the figure has run itself out and jogs until it has its breath back
        self.spot = Spot()
        self.spot_on = False
        self.spot_tries = 0
        self.marker_at = None  # where the marker itself was last read
        self.marker_gone = 0.0  # seconds of readable ticks since
        self.followed = False  # the target of this tick is the place's symbol, not the marker
        self.aside = None  # (since, reason, outward): arrived, and stepping off the carriageway
        self.damaged_since = None
        self.turned = False  # the guard has turned the camera since the target was last read
        self.spot_best = None  # the nearest the followed symbol has been, and when it last came nearer
        self.spot_gain = 0.0
        self.started = None
        self.last_tick = None
        self.last_frame = None
        self.seen = False  # the target has been seen at all
        self.fresh = False  # and since the last gap in the ticks
        self.absent = 0.0  # seconds of readable ticks on foot without the target
        self.carried = 0.0  # of them, seconds the walk went on
        self.blind_since = None
        self.close_since = None
        self.bad_since = None
        self.wake_until = None
        self.wake_push = None
        self.stepped = False  # the stick has been pushed at all
        self.face_until = None  # until when the camera is turned to the target before the first step
        self.face_side = 0.0
        self.start_distance = None
        self.end_distance = None
        self.start_border = False
        self.end_border = False
        self.finished = None
        self.road_mode = False
        self.road_entries = 0
        self.road_start_distance = None
        self.road_until = 0.0
        self.road_retry = 0.0
        self.on_road = False
        self.way = None  # (degrees from the line to the target, on a road)
        self.other = None
        self.other_looks = 0
        self.off_looks = 0  # looks in a row that did not find the way being walked
        self.way_time = 0.0
        self.last_direction = None
        self.last_left = None
        self.last_left_time = 0.0
        self.road_seconds = 0.0
        self.walk_seconds = 0.0

    def _reason(self, reason: str) -> str:
        def distance(value, border):
            if value is None:
                return "unknown"
            return f"{value:.2f}px" + (" (rim; direction only)" if border else "")

        roads = f"on a road {self.road_seconds:.0f} of {self.walk_seconds:.0f} s; " if self.roads else ""
        return (
            f"{reason}; start={distance(self.start_distance, self.start_border)}; "
            f"end={distance(self.end_distance, self.end_border)}; {roads}"
            "pixels are not metres; rim target distance and arrival are unknown"
        )

    def _finish(self, status: str, reason: str) -> SkillResult:
        self.finished = SkillResult(status=status, reason=self._reason(reason))
        return self.finished

    def stop(self, reason: str) -> SkillResult:
        return self._finish("failed", reason)

    def _by_road(self, observation, target):
        """The stick for the first stretch of the way along the map's roads, or None to walk straight."""
        now = observation.time
        toward = math.degrees(math.atan2(target.x, target.y))
        if now - self.way_time > 3 * self.PLAN_EVERY:
            # A way kept over a stretch without looks is no measure for the next look.
            self.way, self.other, self.other_looks = None, None, 0
        if self.way is None or now - self.way_time >= self.PLAN_EVERY:
            # The planner is told the way being walked, and leaves it only for a clearly cheaper one.
            keep = None if self.way is None else toward + self.way[0]
            found = way_by_road(hud_crop(observation.frame), target.x, target.y, side=self.side, keep=keep)
            self.way_time = now
            # The map turns with the camera and the target with it: a way is kept as its angle to
            # the line to the target, which a turn of the camera leaves as it is.
            look = None if found is None else (_turn(found[0] - toward), found[1])
            if look is None or self.way is None or abs(_turn(look[0] - self.way[0])) <= self.OTHER_WAY:
                self.way, self.other, self.other_looks, self.off_looks = look, None, 0, 0
            else:
                # The planner itself keeps to the way being walked while another is not clearly
                # cheaper. What it still names here is another way, at a turn, or a misread map:
                # by day the scene shows through the map, and a post behind a road takes a piece
                # out of it for half a second (13 November, 00:45). So it has to be found several
                # times running.
                agrees = self.other is not None and abs(_turn(look[0] - self.other[0])) <= self.OTHER_WAY
                self.other, self.other_looks = look, self.other_looks + 1 if agrees else 1
                self.off_looks += 1
                # Looks that agree neither with the way walked nor with each other say at least
                # that the way walked is no longer found: after twice as many, the newest is taken.
                if self.other_looks >= self.OTHER_WAY_PLANS or self.off_looks >= 2 * self.OTHER_WAY_PLANS:
                    self.way, self.other, self.other_looks, self.off_looks = look, None, 0, 0
        if self.way is None:
            return None
        self.on_road = self.way[1]
        return stick_for(toward + self.way[0], 1.0)

    def _direction(self, observation, target, distance):
        want = (target.x / distance, -target.y / distance)
        self.on_road = False
        if self.roads and (target.border or distance > self.DIRECT_WITHIN):
            return self._by_road(observation, target) or want
        if self.roads or not self.ROAD_FALLBACK:
            return want
        now = observation.time
        if not self.road_mode and self.guard.failures >= 2 and now >= self.road_retry:
            self.road_mode = True
            self.road_entries += 1
            self.road_start_distance = None if target.border else distance
            self.road_until = now + 12.0
        if not self.road_mode:
            return want
        road = road_position(observation)
        if road is None or road.along is None:
            return want
        along = stick_for(road.along, 1.0)
        dot = sum(a * b for a, b in zip(along, want, strict=True))
        if dot < 0:
            along = (-along[0], -along[1])
            dot = -dot
        away = (
            not target.border
            and self.road_start_distance is not None
            and distance > self.road_start_distance + max(3.0, self.radius)
        )
        if dot < 0.15 or away or now >= self.road_until:
            self.road_mode = False
            self.road_retry = now + 4.0
            return want
        # Approach the nearest road first, then follow its best aligned tangent.
        if road.distance > 5.0:
            approach = stick_for(road.bearing, 1.0)
            if sum(a * b for a, b in zip(approach, want, strict=True)) >= -0.15:
                return approach
            self.road_mode = False
            self.road_retry = now + 4.0
            return want
        return along

    def step(self, observation: Observation) -> SkillResult:
        if self.finished is not None:
            return self.finished
        now = observation.time
        if isinstance(now, bool) or not isinstance(now, (float, int)) or not math.isfinite(now):
            self.close_since = None
            return self._stand()
        if self.started is None:
            self.started = now
        if now - self.started >= self.duration:
            if self.aside is not None:
                return self._finish("done", self.aside[1] + "; still on the carriageway")
            return self._finish("failed", "time limit")
        if self.last_tick is not None and now <= self.last_tick:
            # A tick out of its order: nothing is decided on it and nothing is kept going by it.
            self.close_since = None
            return self._blind(now, coast=False)
        gap = self.last_tick is not None and now - self.last_tick > 1.0
        step = 0.0 if self.last_tick is None or gap else now - self.last_tick
        self.last_tick = now
        if gap:
            # What was seen before a gap in the ticks says nothing about now.
            self.close_since = self.bad_since = self.blind_since = None
            self.fresh, self.absent, self.last_direction, self.way = False, 0.0, None, None
            # On 12 November the picture was gone for twenty seconds, and the guard, still holding
            # a push from before it, called the figure stuck three tenths of a second after it.
            self._new_guard()
            self.breath.gap()
            return self._stand()
        if self.unpushed:
            # The tick before this one put nothing of the guard's on the pad.
            self.skipped = True
        self.unpushed = True
        reading = observation.reading
        # No map on the screen: a scene, whatever else the tick says or does not say.
        dark = reading is not None and reading.minimap == "none"
        nomap = dark and self.stepped
        if nomap and self.nomap_since is None:
            self.nomap_since = now
        patience = self.SCENE if nomap else self.BLIND
        frame = observation.frame
        if frame is not None:
            valid_frame = (
                isinstance(frame, np.ndarray) and frame.shape == (720, 1280, 3) and frame.dtype == np.uint8
            )
            repeated = self.last_frame is not None and np.array_equal(frame, self.last_frame)
            if not valid_frame or repeated:
                self.close_since = None
                return self._blind(now, coast=self._afoot(observation) and not dark, patience=patience)
            self.last_frame = frame.copy()
            if self.sprint:
                self.winded = not self.breath.sprint(frame, now)
        if reading is None:
            self.close_since = None
            return self._blind(now, coast=False)
        marker = None
        if reading.corrupt:
            # A damaged picture says neither where the target is nor whether the figure is on foot.
            # But the reader also takes roads that run along the codec's block borders for damage:
            # on 13 November, 01:02, the camera looking north in Sandy Shores, it called a clean
            # map damaged for five seconds and the figure stood in the road. A walk under way needs
            # the marker, which it reads itself, and goes on where it finds it in such a picture.
            # Not near the place, where an arrival is decided and a damaged picture decides
            # nothing, and not for longer than DAMAGED_MAX in a row.
            if self.stepped and self.color == "purple" and reading.minimap == "flat":
                marker = find_waypoint(hud_crop(frame))
                if marker is not None and not marker.border:
                    marker = marker if math.hypot(marker.x, marker.y) > self.GONE_WITHIN else None
            if self.damaged_since is None:
                self.damaged_since = now
            if marker is None or now - self.damaged_since >= self.DAMAGED_MAX:
                self.close_since = None
                return self._blind(now, coast=self._afoot(observation) and not dark, patience=patience)
            reading = replace(reading, corrupt=False, confidence=max(reading.confidence, 0.6), blips=())
            observation = replace(observation, reading=reading)
        else:
            self.damaged_since = None
        if player_mode(observation) != "foot":
            self.close_since = self.blind_since = None
            if self.bad_since is None:
                self.bad_since = now
            patience = self.SCENE if nomap else self.KNOCKED
            if now - self.bad_since >= (patience if self.stepped else self.FOOT_SETTLE):
                return self._finish("failed", "no longer on foot")
            return self._stand()
        if reading.confidence < 0.6:
            self.close_since = None
            # With no map on the screen something else is being shown, and nothing is pushed into it.
            return self._blind(now, coast=not dark, patience=patience)
        if self.nomap_since is not None:
            if now - self.nomap_since >= self.SCENE_MIN:
                # What the guard saw and was doing before the scene says nothing about now, and
                # where the figure stands after it is asked before it is pushed anywhere.
                self._new_guard()
                if self.where is not None:
                    self.scene, self.room_at = now + self.PLACE_WAIT, None
                    self.where_asked, self.where_at = None, -math.inf
            self.nomap_since = None
        self.bad_since = self.blind_since = None
        if self.wake_until is None:
            unseen = observation.objects_time is not None and observation.figure is None
            self.wake_push = now + self.WAKE_PUSH if unseen else now
            self.wake_until = now + self.WAKE if unseen else now
        if now < self.wake_until:
            self.last_left = None
            return SkillResult(
                pad=Pad(right=(0.4, 0.0)) if now < self.wake_push else NEUTRAL_PAD,
                reason="touching the camera for the game's own view",
            )
        targets = [
            blip
            for blip in reading.blips
            if blip.color == self.color and math.isfinite(blip.x) and math.isfinite(blip.y)
        ]
        if self.aside is not None:
            return self._step_aside(observation)
        waiting = self._where(observation)
        if waiting is not None:
            return waiting
        if not targets and self.color == "purple" and reading.route != "purple":
            # The minimap reader knows no purple disc: the waypoint's marker is read from the frame.
            # Not beside a purple route, which is a vehicle's and whose end the bars cut to a disc.
            marker = marker or find_waypoint(hud_crop(frame))
            targets = [] if marker is None else [marker]
        self.followed = False
        if targets:
            self.spot_on, self.marker_gone = False, 0.0
        else:
            self.marker_gone += step
            place = self._place(observation)
            if isinstance(place, SkillResult):
                return place
            if place is not None:
                near = math.hypot(place.x, place.y)
                nearer = self.spot_best is None or near < self.spot_best - 1.0
                if nearer:
                    self.spot_best = near
                if nearer or self.guard.state != "go":
                    # Held up, the figure stands and the symbol with it: that is the guard's.
                    self.spot_gain = now
                if now - self.spot_gain >= self.SPOT_STALL:
                    # What a running figure is walking towards comes nearer. What does not is
                    # part of the screen and not of the map: the clock decides, and it has run
                    # since the marker went.
                    self.spot_on, self.spot_tries, place = False, self.SPOT_TRIES, None
                    self.end_distance = math.hypot(*self.marker_at)
                    self.absent = self.carried = self.marker_gone
            if place is not None:
                targets, self.followed = [place], True
        if not targets:
            self.close_since = None
            # Only a readable tick on foot counts as one without the target.
            self.absent += step
            if self._facing(now) and self.absent < self.LOST_AFTER:
                # The marker is passing the lower rim: the turn that takes it there brings it back.
                return self._face(self.face_side, 1.0)
            if not self.seen:
                if self.absent >= self.LOST_AFTER:
                    return self._finish("failed", "no matching blip")
                if self.color == "purple" and self.absent >= self.SEARCH_AFTER:
                    # Straight behind the figure the marker lies on the map's lower rim, under the
                    # bars and whatever symbol stands there: at Ammu-Nation on 13 November, 01:13,
                    # a waypoint 231 m behind the figure was not on the map at all. Looking round
                    # brings it up the side.
                    self.face_side = 1.0
                    return self._face(1.0, 1.0)
                return self._stand()
            # A near marker that is gone was taken off the map by the game, which is an arrival;
            # not one the guard's own turn of the camera has put under the map's bars.
            reached = (
                self.color == "purple"
                and self.fresh
                and not self.turned
                and not self.end_border
                and self.end_distance is not None
                and self.end_distance <= self.GONE_WITHIN
            )
            pace = self.SPRINT_PACE if self.sprint else self.WALK_PACE
            keep = min(self.CARRY_MAX, self.end_distance / pace) if reached else self.HOLD
            if not reached and self.stepped and self.guard.state in {"climb", "round"}:
                # The guard is at an obstacle, and where it looks round it turns the camera: the
                # marker passes the map's lower rim, where it is not read. What the guard has
                # begun it finishes, and the marker is missed from when it has.
                self.absent = 0.0
                return self._push(observation, self.last_direction or self.guard.AHEAD, step, fresh=False)
            if self.turned and not reached and self.color == "purple" and self.absent < self.LOST_AFTER:
                # The camera is where the guard's look left it, and the old direction, which was
                # the camera's, means nothing now: the marker is looked for as at a walk's start.
                # (Inside the barber's on 13 November the walk ended here as "blip lost".)
                return self._face(1.0, 1.0) if self.absent >= self.SEARCH_AFTER else self._stand()
            # The direction is the camera's, which the guard leaves alone but for its looks.
            if self.fresh and self.absent < keep and self.last_direction is not None:
                self.carried += step
                return self._push(observation, self.last_direction, step, fresh=False)
            if self.absent >= self.LOST_AFTER:
                if reached:
                    return self._arrive(
                        observation,
                        "arrived; the game took the near waypoint off the map, "
                        f"walked on {self.carried:.1f} s",
                    )
                return self._finish("failed", "blip lost; end is last observed distance")
            return self._stand()
        target = min(targets, key=lambda blip: math.hypot(blip.x, blip.y))
        distance = math.hypot(target.x, target.y)
        self.seen = self.fresh = True
        self.turned = False
        self.absent = self.carried = 0.0
        if not self.followed:
            self.marker_at = None if target.border else (target.x, target.y)
        if self.start_distance is None:
            self.start_distance, self.start_border = distance, target.border
        self.end_distance, self.end_border = distance, target.border
        radius = max(self.radius, self.AT_PLACE) if self.followed else self.radius
        if not target.border and distance <= radius:
            if self.close_since is None:
                self.close_since = now
            if self.followed:
                return self._arrive(observation, "arrived; at the symbol under the waypoint")
            if now - self.close_since >= self.SETTLE:
                return self._arrive(observation, "arrived; stable interior blip")
            return self._stand()
        self.close_since = None
        if distance == 0:
            return self._stand()
        if not self.stepped:
            bearing = math.degrees(math.atan2(target.x, target.y))
            if self.face_until is None:
                self.face_until = now + self.FACE_MAX if abs(bearing) > self.FACE_FIRST else now
            if self._facing(now):
                if abs(bearing) > self.FACE_DONE:
                    # Straight behind, the marker's side changes with half a pixel: the side is
                    # chosen once, and changed only for a target the turn has carried past ahead.
                    if self.face_side == 0.0 or abs(bearing) < 90.0:
                        self.face_side = 1.0 if bearing > 0 else -1.0
                    return self._face(self.face_side, min(1.0, max(0.4, abs(bearing) / 90.0)))
                self.face_until = now
        self.last_direction = self._eased(self._direction(observation, target, distance), step)
        pushed = self._push(observation, self.last_direction, step)
        if (
            self.finished is None
            and self.followed
            and distance <= self.AT_WALL
            and self.guard.state == "round"
        ):
            # What holds the figure up this near the place's symbol, and Square does not take it
            # over, is the place. (Not before the symbol is followed: a parked car thirteen pixels
            # short of a marker is a car, and a climb that is still under way may be taking it.)
            return self._arrive(observation, f"arrived; held up {distance:.0f} px from the place")
        return pushed

    def _place(self, observation):
        """The place under a waypoint the game has removed, as a blip; None where it is not followed."""
        if not self.exact or self.color != "purple" or not self.fresh or self.marker_at is None:
            return None
        crop = hud_crop(observation.frame)
        if crop is None:
            return None
        if not self.spot_on:
            near = math.hypot(*self.marker_at) <= self.GONE_WITHIN
            if not near or self.marker_gone < self.GONE_FOR or self.spot_tries >= self.SPOT_TRIES:
                return None
            self.spot_tries += 1
            self.spot_on, self.spot_best = self.spot.begin(crop, *self.marker_at), None
            at = self.marker_at if self.spot_on else None
        else:
            at = self.spot.follow(crop)
            if at is None and self.spot.missed >= self.SPOT_LOST:
                self.spot_on = False
                last = self.spot.last()
                if last is not None and math.hypot(*last) <= self.AT_WALL:
                    # The arrow covers a symbol it stands on.
                    return self._arrive(observation, "arrived; on the symbol under the waypoint")
                # What was followed may have been the marker, and the symbol shows where it stood.
                self.marker_at = last
        return None if at is None else Blip("purple", at[0], at[1], False)

    def _arrive(self, observation, reason: str) -> SkillResult:
        """Done; where the walk keeps to the side of roads, after a step off the carriageway."""
        if self.side:
            road = road_position(observation)
            if road is not None and road.position == "lane" and road.outward is not None:
                self.aside = (observation.time, reason, road.outward)
                return self._step_aside(observation)
        return self._finish("done", reason)

    def _step_aside(self, observation) -> SkillResult:
        since, reason, outward = self.aside
        road = road_position(observation)
        if observation.time - since >= self.ASIDE_MAX:
            return self._finish("done", reason + "; still on the carriageway")
        if road is None or road.position != "lane" or road.outward is None:
            return self._finish("done", reason + "; off the carriageway")
        # On a band's middle line the nearer edge changes from tick to tick: the side first read
        # is kept, and the reading only bends it.
        if abs(_turn(road.outward - outward)) <= 90.0:
            outward = road.outward
            self.aside = (since, reason, outward)
        self.last_left = None
        return SkillResult(pad=Pad(left=stick_for(outward, 1.0)), reason="stepping off the carriageway")

    def _eased(self, want, step: float):
        """The direction the stick takes on this tick on its way round to the one that is wanted."""
        before = self.last_direction
        if before is None or not self.stepped:
            return want
        turn = _turn(math.degrees(math.atan2(want[0], -want[1]) - math.atan2(before[0], -before[1])))
        most = self.TURN_RATE * step
        if abs(turn) <= most:
            return want
        bearing = math.degrees(math.atan2(before[0], -before[1])) + math.copysign(most, turn)
        return stick_for(bearing, math.hypot(*want))

    @staticmethod
    def _afoot(observation) -> bool:
        return observation.reading is not None and player_mode(observation) == "foot"

    def _facing(self, now) -> bool:
        return not self.stepped and self.face_until is not None and now < self.face_until

    def _face(self, side: float, stick: float) -> SkillResult:
        self.last_left = None
        return SkillResult(pad=Pad(right=(side * stick, 0.0)), reason="turning the camera to the target")

    def _stand(self) -> SkillResult:
        """Nothing on the pad, and nothing left over for a later tick to send again."""
        self.last_left = None
        return SkillResult()

    def _new_guard(self) -> None:
        """A guard that has seen nothing yet, and knows of the place what the walk knows."""
        place = self.guard.place
        self.guard = WayRound(sides=sides.active(), ahead=ahead.active())
        self.guard.place = self.guard.indoors = place

    def _where(self, observation) -> SkillResult | None:
        """Keeps asking the model for the place, and acts on a room: a result to stand by, or None."""
        if self.where is None:
            return None
        now, guard = observation.time, self.guard
        after_scene = self.scene is not None
        if after_scene and now >= self.scene:
            # No answer in time: the walk goes on without one.
            self.scene, after_scene = None, False
        if guard.state != "go" or (self.room_at is not None and now - self.room_at > 2 * self.PLACE_EVERY):
            # Twice running means of two pictures a moment apart, with nothing between them.
            self.room_at = None
        if self.where_asked is not None:
            view = self.where.answer(self.where_asked)
            if view is None and now - self.where_asked < self.PLACE_WAIT:
                return self._stand() if after_scene else None
            self.where_asked, self.where_at, self.scene = None, now, None
            share = None if view is None or view.error is not None else view.indoors
            room = share is not None and share >= self.INDOORS
            if share is not None and (room or share < SEEN):
                guard.place = room
                if guard.state == "go":
                    guard.indoors = room
            if not room:
                self.outdoors = self.outdoors or (share is not None and share < SEEN)
                self.room_at = None
            elif guard.state == "go" and self.room_at is None and not after_scene:
                # One answer is not acted on: the next is asked for a moment later.
                self.room_at, self.where_at = now, now - self.PLACE_EVERY + self.PLACE_AGAIN
            elif guard.state == "go":
                self.room_at = None
                near = self.seen and not self.end_border and (self.end_distance or 0.0) <= self.GONE_WITHIN
                if not near:
                    # (This near the place the room may be the place itself: a waypoint set on a
                    # shop lies in the shop.)
                    self.stepped, self.face_until = True, now
                    self.entries += 1
                    if self.entries > self.ENTRIES:
                        return self._finish("failed", "in a building again and again")
                    if self.outdoors:
                        # Run in from outdoors: back the way it came, and along the building's
                        # front on the other side each time.
                        self.outdoors = False
                        guard.side = guard.first_side * (-1) ** self.backs
                        self.backs += 1
                        guard.back_out(observation)
                    else:
                        # The walk begins in a room, or a way back out did not lead out.
                        guard.leave(observation)
            after_scene = False
        if self.where_asked is None and guard.state == "go" and now - self.where_at >= self.PLACE_EVERY:
            if self.where.ask(observation.frame, now, ahead=False, exit=False):
                self.where_asked = now
        return self._stand() if after_scene else None

    def _blind(self, now, *, coast: bool = True, patience: float | None = None) -> SkillResult:
        """A tick that says nothing decides nothing, and does not stop a figure that is running."""
        patience = self.BLIND if patience is None else patience
        if self.blind_since is None:
            self.blind_since = now
        if now - self.blind_since >= patience:
            return self._finish("failed", f"nothing readable for {patience:.0f} s")
        if coast and self.last_left is not None and 0 <= now - self.last_left_time <= self.COAST:
            sprint = self.sprint and not self.winded
            buttons = self.profile.sprint_buttons(now - self.started) if sprint else ()
            return SkillResult(pad=Pad(left=self.last_left, buttons=buttons))
        return self._stand()

    def _push(self, observation, direction, step, *, fresh: bool = True):
        sprint = self.sprint and not self.winded
        if self.skipped:
            # On a tick that said nothing the pad was let go, the guard not asked: a press of its
            # Square that such a tick cut must not come back as a second one (see `resume`).
            self.guard.resume(observation.time)
        self.skipped = self.unpushed = False
        steer = self.guard.step(observation, direction, sprint=sprint, fresh=fresh)
        self.turned = self.turned or steer.right != (0.0, 0.0)
        if steer.failed:
            return self._finish("failed", "stuck; guard exhausted")
        if steer.buttons and self.damaged_since is not None:
            # A picture the reader calls damaged carries the walk on by its marker; it is no
            # ground for a jump.
            steer = replace(steer, buttons=())
            self.guard.pressing = False
        # A way round is run like the way itself; a climb is the guard's own press and no sprint.
        buttons = steer.buttons + (
            self.profile.sprint_buttons(observation.time - self.started)
            if sprint and steer.state in {"go", "idle", "round"}
            else ()
        )
        self.stepped = True
        self.walk_seconds += step
        self.road_seconds += step if self.on_road else 0.0
        doing = "following road" if self.road_mode or self.on_road else "walking"
        if self.winded:
            doing += ", out of breath"
        if steer.state == "odd":
            self.last_left = None
            return SkillResult(pad=NEUTRAL_PAD, reason=self._reason(doing))
        # A push is kept for a tick that says nothing, forward or round an obstacle; a climb is not.
        self.last_left = steer.left if steer.state in {"go", "round"} else None
        self.last_left_time = observation.time
        return SkillResult(
            pad=Pad(left=steer.left, right=steer.right, buttons=buttons),
            reason=self._reason(doing),
        )
