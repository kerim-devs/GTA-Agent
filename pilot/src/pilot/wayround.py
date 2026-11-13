"""The foot guard of a walk that has somewhere to go: held up, it climbs or goes round.

Kerim, 12 November: over a car or a wall the figure climbs with Square where it reaches, and where
it does not it walks round, "right, right and then further out", and which side is for the local
model to say. The guard in `foot` turns 70 degrees for 1.6 s, the other way next time: on
13 November it stood against a boulder for eleven seconds before it called the figure stuck, used
its four turns in six and gave up.

What is different here. Under a sprint the figure is measured by a sprint's pace, and by the
picture of the world before the map: against the boulder the map still moved 0.4 to 1.1 crop
pixels in half a second, which the walking thresholds read as going, and wedged between two
boulders it moved 1.5 to 3.5, as much as in a free sprint, for the five seconds the figure got
nowhere, while the world stood nearly still. Held up, it presses Square once and pushes on. If
that does not free it, it goes round on one side, at right angles to where it wants to go, and
comes back in at 45 degrees; held up again at once, it goes further out on the same side, and only
a side that is itself closed makes it try the other. With both sides closed it is in a pocket, and
walks back out the way it came before it tries the sides again, once. The direction is taken from
where the walk wants to go on every tick, so a way round stays a way round while the camera swings
behind the figure.

Kerim, 13 November, of a figure wedged between a palm, a leaning sheet of iron and a wall, where the
guard had pressed Square once, forward, and given up: stuck, always try Square as well, the jump, it
helps. So no direction is called closed before the figure has jumped in it: a side, and the way
back, each once at an obstacle.

And of the same figure: that is where the model is needed, to look and say where the way goes on.
With a model to ask (see `ahead`) the guard looks before it feels: after the press of Square has
freed nothing the figure stands, the camera goes a fifth of a circle round at a time, and of each
view the model is asked whether the way straight ahead is open. Into the first view it calls open
the figure runs, as far as a leg sideways would have gone, and the feet judge it as they judge a
leg. With every view called blocked, or no answer, the sides are felt for as before.
"""

from __future__ import annotations

import math
from typing import ClassVar

from .ahead import Ahead
from .contract import Observation, player_mode
from .foot import FootGuard, Steer, _rotate, hud_crop, map_shift, world_shift, world_view
from .sides import Sides, choose


class WayRound(FootGuard):
    # Under a sprint, in half a second, over seven stretches of 12 and 13 November. The world
    # (pixels of the small view): running free 2.3 to 3.1 at the tenth percentile and 4.2 to 7.6
    # at the median; wedged between boulders 0.29 to 0.71; against a rock 0.0 to 0.27. The map
    # (crop pixels): running free 1.9 to 2.3 at the tenth percentile and 2.5 to 2.6 at the median;
    # against the rock 0.2 to 0.9; wedged 1.5 to 3.5. The world is read on about half the ticks,
    # and where it is read it decides: of the ticks of four free sprints it was under 1.0 on 0.2
    # to 2.4 in a hundred, never for longer than a quarter of a second.
    WORLD_STILL, WORLD_GOING = 1.0, 1.8
    MAP_STILL, MAP_GOING = 1.2, 1.7
    HELD_AFTER = 1.5  # seconds of pushing before the figure is taken for held up
    CLIMB_PRESS = 0.15
    CLIMB_SECONDS = 1.6  # how long the push after the press is given to get the figure going
    CLIMB_AGAIN = 5.0  # Square is not pressed again this soon, whatever the last press did
    LEGS: ClassVar = (2.0, 3.5, 5.0)  # seconds sideways, further out each time
    TURN_IN = 1.0  # seconds at 45 degrees on the way back in
    # Under the porch of the barber's on 13 November, 00:55, the shop's wall was ahead, its window
    # on one side and the porch's posts on the other: both sides closed, and the walk gave up two
    # steps from open ground. A player turns round and walks out the way he came in.
    BACK = 2.5  # seconds back out of a pocket, once at an obstacle
    # A leg begins from a standstill and with a turn, and a shift is measured against the picture
    # of half a second before: what is seen in a leg's first second says nothing about the leg,
    # and what was seen before it says nothing either. On 13 November the stand before a leg was
    # counted into it, and a fence with its end eight metres to the right was called closed on
    # that side after one second; with half a second left out a figure already running along a
    # wall was called held up as well.
    LEG_START = 1.0
    LEG_HELD_AFTER = 1.0  # seconds of a leg after its start that have to say still
    # A climb shows as a burst of movement after the press, and the figure may stand on top of
    # what it climbed for a moment after: over the fence of 13 November, 00:24, seven ticks said
    # going from 0.8 s after the press and the next second said still.
    CLIMBED = 0.6  # the last seconds of a climb that say whether it got the figure going
    CLIMB_BURST = 4  # ticks of going within the climb that say the press took
    AGAIN_WITHIN = 4.0  # held up this soon after a way round, it is the same obstacle
    HINT_WITHIN = 1.0  # seconds into a way round in which the model's word may still turn it
    GIVE_UP = 8  # ways round without three seconds of going free between them
    CAMERA_BEHIND = 0.7  # the stick's forward share above which left in the picture is the figure's left
    # A look: the right stick turns the camera 148 degrees in a second, 72 in this half. Four of
    # them go once round and none ends with the target straight behind the camera, where its
    # marker lies under the bars of the map and is not read.
    LOOK_TURN = 0.49
    LOOK_SETTLE = 0.3  # seconds for the turned camera's picture to arrive; the stream is 0.14 s behind
    LOOK_WAIT = 1.0  # seconds an answer is waited for
    LOOKS = 4
    OPEN = 0.9  # what the model has to give "open" for a view to be run into
    AHEAD: ClassVar = (0.0, -1.0)

    def __init__(
        self,
        *,
        first_side: int = 1,
        climb: bool = True,
        sides: Sides | None = None,
        ahead: Ahead | None = None,
    ):
        super().__init__(first_side=first_side)
        self.climb = climb
        self.sides = sides
        self.ahead = ahead
        self.looked = 0  # views looked at, at this obstacle
        self.asked_at = None
        self.views: list = []  # what the model gave "open" in each
        self.side = self.first_side
        self.level = 0
        self.phase = None  # "out" | "in" | "back" while going round
        self.backed = False  # the figure has been walked back out of a pocket at this obstacle
        self.rounds = 0
        self.closed: set[int] = set()  # sides found closed at this obstacle
        self.round_ended = None
        self.climbed = None  # when Square was last pressed
        self.held_at = None
        self.hinted = False
        self.said = None  # what the model last said of the two sides: (left open, right open)
        self.sprinting = False
        self.pressing = False  # Square is down for this climb
        self.stepped_at = None
        self.jumped: set = set()  # directions jumped in at this obstacle: a side, or "back"
        self.leg_jump = None  # when Square was pressed in the leg under way

    def _evidence(self, observation: Observation) -> str | None:
        if not self.sprinting:
            return super()._evidence(observation)
        now = observation.time
        shifts = []
        for history, current, measure in (
            (self.crops, hud_crop(observation.frame), map_shift),
            (self.worlds, world_view(observation.frame), world_shift),
        ):
            while history and history[0][0] < now - self.SHIFT_SPAN[1]:
                history.popleft()
            shift = None
            if current is not None:
                if history and now - history[0][0] >= self.SHIFT_SPAN[0]:
                    shift = measure(history[0][1], current)
                history.append((now, current.copy()))
            shifts.append(shift)
        over_map, world = shifts
        if world is not None:
            if world >= self.WORLD_GOING:
                return "going"
            return "still" if world < self.WORLD_STILL else None
        if over_map is not None:
            if over_map < self.MAP_STILL:
                return "still"
            return "going" if over_map >= self.MAP_GOING else None
        return "still" if observation.moving is False else None

    def step(self, observation: Observation, want: tuple[float, float], *, sprint: bool = False) -> Steer:
        now = observation.time
        self.sprinting = sprint
        # A press cut by a tick the guard did not see, or did not act on, is not taken up again:
        # the game would count two presses.
        missed = self.stepped_at is None or now - self.stepped_at > self.CLIMB_PRESS
        if missed or observation.reading.corrupt:
            self.pressing = False
        self.stepped_at = now
        if player_mode(observation) != "foot":
            self.crops.clear()
            self.worlds.clear()
            self.evidence.clear()
            self.push_since = None
            return Steer(want, state="idle")
        if observation.reading.corrupt:
            self.crops.clear()
            self.worlds.clear()
            return Steer((0.0, 0.0), state="odd")
        if self.state == "failed":
            return Steer((0.0, 0.0), state="failed", failed="stuck")
        self.evidence.append((now, self._evidence(observation)))
        while self.evidence and self.evidence[0][0] < now - 3.0:
            self.evidence.popleft()
        magnitude = math.hypot(*want)
        if self.state_since is None:
            self.state_since = now
        if magnitude < self.PUSH:
            # The walk wants to stand: whatever the guard was doing is over.
            if self.state != "go":
                self._enter("go", now)
            self.push_since = None
            return Steer(want, state="go")
        toward = (want[0] / magnitude, want[1] / magnitude)
        self.wanted = toward

        if self.state == "climb":
            if now - self.state_since < self.CLIMB_SECONDS:
                self.pressing = self.pressing and now - self.state_since < self.CLIMB_PRESS
                return Steer(toward, state="climb", buttons=("square",) if self.pressing else ())
            burst = sum(kind == "going" for t, kind in self.evidence if t >= self.state_since)
            if burst < self.CLIMB_BURST and self._stands(now - self.CLIMBED, now):
                return self._round(observation, toward)
            # Over it, or at least moving: the push starts afresh and is judged afresh.
            self._enter("go", now)
            self.push_since = None
        if self.state == "round" and self.phase == "look":
            return self._look(observation, toward)
        if self.state == "round":
            if not self.hinted and self.phase == "out" and now - self.state_since <= self.HINT_WITHIN:
                self._take_hint(now, toward)
            jump = self.leg_jump if self.leg_jump is not None and self.leg_jump >= self.state_since else None
            if jump is not None:
                if now - jump < self.CLIMB_SECONDS:
                    self.pressing = self.pressing and now - jump < self.CLIMB_PRESS
                    return Steer(
                        self._leg(toward), state="climb", buttons=("square",) if self.pressing else ()
                    )
                burst = sum(kind == "going" for t, kind in self.evidence if t >= jump)
                closed = burst < self.CLIMB_BURST and self._stands(now - self.CLIMBED, now)
                if not closed:
                    # The jump took: the leg begins afresh from where the figure is now.
                    self._enter("round", now)
            else:
                started = self.state_since + self.LEG_START
                closed = now - started >= self.LEG_HELD_AFTER and self._stands(started, now)
                key = self.phase if self.phase == "back" else self.side
                if self.phase == "run":
                    key = ("run", self.looked)
                if closed and self.climb and self.phase != "in" and key not in self.jumped:
                    # Not closed before the figure has jumped at it.
                    self.jumped.add(key)
                    self.leg_jump, self.pressing = now, True
                    return Steer(self._leg(toward), state="climb", buttons=("square",))
            if self.phase == "run" and closed:
                # The model called this way open and the feet say otherwise.
                return self._look_on(observation, toward)
            if self.phase == "run" and now - self.state_since >= self.LEGS[self.level]:
                self.round_ended = now
                self._enter("go", now)
                self.push_since = None
            elif self.phase == "out" and closed:
                # This side is closed as well. (The way back in is too short to be judged: held up
                # on it, the figure is held up again right after it, and goes further out.)
                self.closed.add(self.side)
                if not self._count(now) or (len(self.closed) == 2 and self.backed):
                    return self._fail(now)
                if len(self.closed) == 2:
                    # Closed ahead and on both sides: the way out of a pocket is the way in.
                    self.backed, self.phase = True, "back"
                else:
                    self.side = -self.side
                self._enter("round", now)
            elif self.phase == "back" and closed:
                return self._fail(now)
            elif self.phase == "back" and now - self.state_since >= self.BACK:
                # From further back the sides are tried again, and further out than before.
                self.closed.clear()
                self.side, self.level, self.phase = self.first_side, min(1, len(self.LEGS) - 1), "out"
                self._enter("round", now)
            elif self.phase == "out" and now - self.state_since >= self.LEGS[self.level]:
                self.phase = "in"
                self._enter("round", now)
            elif self.phase == "in" and now - self.state_since >= self.TURN_IN:
                self.round_ended = now
                self._enter("go", now)
                self.push_since = None
            if self.state == "round":
                return Steer(self._leg(toward), state="round")

        # state "go"
        if self.push_since is None:
            self.push_since = now
        if self._verdict(now, self.push_since, self.HELD_AFTER):
            return self._held(observation, toward)
        if now - self.push_since >= self.PROGRESS_SECONDS and self._going(now):
            self._free(now)
            self.push_since = now
        return Steer(want, state="go")

    def _leg(self, toward) -> tuple[float, float]:
        """The stick of the leg under way: out at right angles, back in at 45 degrees, or straight back."""
        if self.phase == "back":
            return (-toward[0], -toward[1])
        if self.phase == "run":
            return self.AHEAD
        return _rotate(toward, self.side * (90.0 if self.phase == "out" else 45.0))

    def _stands(self, since: float, now: float) -> bool:
        """Most of what was seen from `since` on says still."""
        window = [kind for t, kind in self.evidence if since <= t <= now]
        if len(window) < 5:
            return False
        still, going = window.count("still"), window.count("going")
        return still >= self.STILL_SHARE * len(window) and going <= 0.25 * len(window)

    def diagnostic(self) -> str:
        text = super().diagnostic()
        if self.state == "round" and self.phase == "back":
            text += ";back"
        elif self.state == "round" and self.phase in ("look", "run"):
            text += f";{self.phase}={self.looked}"
        elif self.state == "round":
            text += f";side={'left' if self.side < 0 else 'right'};leg={self.level};{self.phase}"
        if self.said is not None:
            text += f";open={self.said[0]:.2f}/{self.said[1]:.2f}"
        if self.views:
            text += ";views=" + "/".join("none" if view is None else f"{view:.2f}" for view in self.views)
        return text

    def _free(self, now: float) -> None:
        """The figure is going: what was learnt about the last obstacle is of no use at the next."""
        if self.state != "go":
            self._enter("go", now)
        self.push_since = None
        self.rounds = self.level = self.looked = 0
        self.closed.clear()
        self.jumped.clear()
        self.backed = False
        self.round_ended = None

    def _count(self, now: float) -> bool:
        self.rounds += 1
        return self.rounds <= self.GIVE_UP

    def _fail(self, now: float) -> Steer:
        self.state, self.state_since = "failed", now
        self.events.append((now, "stuck"))
        return Steer((0.0, 0.0), state="failed", failed="stuck")

    def _held(self, observation: Observation, toward) -> Steer:
        now = observation.time
        self.failures += 1
        again = self.round_ended is not None and now - self.round_ended <= self.AGAIN_WITHIN
        if again:
            # The same obstacle: further out on the same side.
            self.level = min(self.level + 1, len(self.LEGS) - 1)
        else:
            self.level = self.looked = 0
            self.closed.clear()
            self.jumped.clear()
            self.views = []
            self.backed = False
            self.held_at, self.hinted, self.said = now, False, None
            if self.sides is not None:
                self.sides.ask(observation.frame, now)
        # What holds the figure up now may be another thing than last time, a fence after a wreck:
        # Square is tried at every hold-up, only not twice within a few seconds.
        if self.climb and (self.climbed is None or now - self.climbed > self.CLIMB_AGAIN):
            self.climbed, self.pressing = now, True
            self._enter("climb", now)
            return Steer(toward, state="climb", buttons=("square",))
        return self._round(observation, toward)

    def _round(self, observation: Observation, toward) -> Steer:
        now = observation.time
        if not self._count(now):
            return self._fail(now)
        self._take_hint(now, toward)
        return self._look_on(observation, toward)

    def _look_on(self, observation: Observation, toward) -> Steer:
        """The camera a step further round; with no model, or nothing left to look at, the way by feel."""
        now = observation.time
        if self.ahead is None or self.looked >= self.LOOKS:
            self._take_hint(now, toward)
            self.phase = "out"
            self._enter("round", now)
            return Steer(self._leg(toward), state="round")
        self.looked += 1
        self.phase, self.asked_at = "look", None
        self._enter("round", now)
        return Steer((0.0, 0.0), (float(self.side), 0.0), state="look")

    def _look(self, observation: Observation, toward) -> Steer:
        """Standing: the camera turns, its picture settles, and the model is asked about it."""
        now = observation.time
        since = now - self.state_since
        if since < self.LOOK_TURN:
            return Steer((0.0, 0.0), (float(self.side), 0.0), state="look")
        if since < self.LOOK_TURN + self.LOOK_SETTLE:
            return Steer((0.0, 0.0), state="look")
        if self.asked_at is None and self.ahead.ask(observation.frame, now):
            self.asked_at = now
        found = None if self.asked_at is None else self.ahead.answer(self.asked_at)
        if found is None:
            if since < self.LOOK_TURN + self.LOOK_SETTLE + self.LOOK_WAIT:
                return Steer((0.0, 0.0), state="look")
            found = (None, "no answer")
        share = found[0]
        self.views.append(share)
        if share is None:
            # The model is not there: at this obstacle the way is felt for as before.
            self.looked = self.LOOKS
        elif share >= self.OPEN:
            self.phase = "run"
            self._enter("round", now)
            return Steer(self.AHEAD, state="round")
        return self._look_on(observation, toward)

    def _take_hint(self, now: float, toward) -> None:
        """The side the model called open, where it has answered about this obstacle."""
        if self.hinted or self.sides is None or self.held_at is None:
            return
        answer = self.sides.answer(self.held_at)
        if answer is None:
            return
        self.hinted = True
        if answer[0] is not None and answer[1] is not None:
            self.said = answer
        side = choose(*answer)
        # Left in the picture is the figure's left only with the camera behind it.
        if side is None or -toward[1] < self.CAMERA_BEHIND or side in self.closed or side == self.side:
            return
        self.side = side
        if self.state == "round":
            self._enter("round", now)
