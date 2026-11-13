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
leg. With every view called blocked, or no answer, the sides are felt for as before. In a room
every way is open for a few steps and none leads on: there the model is asked for the way out, the
door to the outside, and in which part of the picture it is, the camera is turned to it and the
figure runs through it. (On 13 November the walk had run into the barber's it stood in front of.)

Kerim, the same night, of the minutes that took: use the way out you came in by; if nothing else
helps, run at every face of the room once, all the way round the shop, until you are out; and once
out, a few steps straight on before you turn left or right, so as not to hang at the door again.
So a walk that finds itself in a building it has run into has the guard turn the camera to where
the figure came from and run back (`back_out`); in a room in which the model sees no way out the
figure goes round along the walls, pushing into each (the wall round); and behind a door it runs
straight on for a few steps, and where the way to the target leads back through the building it
has left, along its front before it turns to the target again.

Outdoors a side is felt for first, running, and the look comes when that side is closed: standing
and turning the camera at every hold-up cost four to five seconds, where a leg sideways is run.
"""

from __future__ import annotations

import math
from typing import ClassVar

from .ahead import SEEN, Ahead, View
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
    # That is outdoors. In the barber's the arrow on the map, which is the figure's facing against
    # the camera's and is read in a room as well, went 37 to 45 degrees with such a turn, a part of
    # it after the stick was let go. Where the arrow is seen to follow, a turn goes on until it has
    # gone as far as it should, less what it goes on by after the stick: so it is measured.
    LOOK_STEP = 72.0
    TURN_LAG = 18.0  # degrees the arrow goes on after the stick is let go
    TURN_SEEN = 10.0  # degrees within LOOK_TURN that say the arrow follows the camera
    TURN_RATE = 80.0  # degrees a second at the least, for the longest a measured turn may take
    AIM_TURN = 0.19  # the camera's turn to a door in the left or the right part of the picture, 28 degrees
    # Running at a way out of a room. On 13 November four seconds ended a step short of the
    # barber's door, and chairs stood in the straight line to it: the run goes on until the model
    # calls the figure outdoors, and on the way the door is looked at again and the camera, which
    # the stick goes by, is turned to the part of the picture it is in.
    EXIT_RUN = 9.0  # seconds at the most
    WATCH_EVERY = 0.6  # seconds between two looks at the way out while running at it
    # Straight on once outside, before any turn to the side: a porch and its posts are three
    # metres deep, and the model calls the figure outdoors a step or two beyond the door.
    CLEAR = 1.5
    LOOK_SETTLE = 0.3  # seconds for the turned camera's picture to arrive; the stream is 0.14 s behind
    LOOK_WAIT = 1.0  # seconds an answer is waited for
    LOOKS = 4
    OPEN = 0.9  # what the model has to give "open" for a view to be run into
    AHEAD: ClassVar = (0.0, -1.0)
    # The way back out of a building: the camera is turned until the figure faces it, which is
    # where it came from, and the figure runs into the picture, watched as at any way out.
    ABOUT = 180.0
    # Out of a building the target lies behind: along the front, a quarter turn to the side.
    ASIDE = 90.0
    BEHIND = 0.3  # the stick's share toward the camera above which the target lies behind
    # The wall round, the worst case in a room: an eighth turn of the camera and straight on until
    # the figure stands, again and again. Pushed at an angle into a wall the figure slides along
    # it and through any door in it; in a corner it stands, and the next turn takes it along the
    # next wall. Three times round and still inside, the guard gives up; running free for
    # WALL_FREE seconds it is out, whatever the model says or does not say.
    WALL_TURN = 0.5
    WALL_TURNS = 24
    WALL_FREE = 6.0

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
        self.looked = 0  # views looked at, at this obstacle; the first is the view as it stands
        self.asked_at = None
        self.views: list[str] = []  # what the model said of each
        self.indoors = None  # whether the model called this place a room
        self.aim = 0  # the part of the picture a way out was seen in: -1 left, 1 right
        self.way_out = False  # the run under way is at a way out of a room
        self.watch_at = None  # when the model was last asked about the way out during such a run
        self.watched = 0.0
        self.nudge, self.nudge_until = 0.0, -math.inf  # the camera's turn to the way out
        self.outside = None  # when the model called the figure outdoors
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
        self.place = None  # what the walk knows of the place: True a room, False outdoors
        self.entered = False  # the figure ran into this building and is on its way back out
        self.turn_side, self.turn_by, self.turn_from = 0, 0.0, None  # a measured turn of the camera
        self.turn_took = 0.0  # seconds the turn before the view under way took
        self.wall_turns = 0
        self.fresh = True  # the direction wanted was read on this tick

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

    def step(
        self,
        observation: Observation,
        want: tuple[float, float],
        *,
        sprint: bool = False,
        fresh: bool = True,
    ) -> Steer:
        """`fresh` false says the direction is an old one, kept while the target is not read."""
        now = observation.time
        self.sprinting = sprint
        self.fresh = fresh
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
        if self.state == "round" and self.phase == "wall":
            return self._wall(observation)
        if self.state == "round" and self.phase in ("about", "aside"):
            if not self._turned(observation):
                return Steer((0.0, 0.0), (float(self.turn_side), 0.0), state="look")
            # Round: into the picture, out of the building or along its front.
            self.phase = "run"
            self._enter("round", now)
        if self.state == "round" and self.phase == "aim":
            if now - self.state_since < self.AIM_TURN:
                return Steer((0.0, 0.0), (float(self.aim), 0.0), state="look")
            self.phase = "run"
            self._enter("round", now)
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
            if self.phase == "run" and self.way_out and not closed:
                self._watch(observation)
            if self.phase == "run" and closed:
                # The model called this way open and the feet say otherwise.
                return self._look_on(observation, toward)
            if self.phase == "run" and (
                now - self.state_since >= (self.EXIT_RUN if self.way_out else self.LEGS[self.level])
                or (self.way_out and self.outside is not None and now - self.outside >= self.CLEAR)
            ):
                out = self.way_out and self.outside is not None
                behind = toward[1] > self.BEHIND if fresh else self.entered
                self.way_out = self.entered = False
                if out and behind:
                    # The way to the target leads back through the building: along its front
                    # first, on the side the target is on where that is seen.
                    if fresh and abs(toward[0]) > self.BEHIND:
                        self.side = 1 if toward[0] > 0 else -1
                    self.level = len(self.LEGS) - 1
                    self._turn(observation, self.side, self.ASIDE, "aside")
                    return Steer((0.0, 0.0), (float(self.turn_side), 0.0), state="look")
                self.round_ended = now
                self._enter("go", now)
                self.push_since = None
            elif self.phase == "out" and closed:
                # This side is closed as well. (The way back in is too short to be judged: held up
                # on it, the figure is held up again right after it, and goes further out.)
                self.closed.add(self.side)
                if not self._count(now) or (len(self.closed) == 2 and self.backed):
                    return self._fail(now)
                if self.ahead is not None and self.indoors is False and self.looked <= 1:
                    # Felt for and closed: now the look, which begins with a turn of the camera.
                    self.looked = 1
                    return self._look_on(observation, toward)
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
                right = (self.nudge, 0.0) if now < self.nudge_until else (0.0, 0.0)
                return Steer(self._leg(toward), right, state="round")

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
        elif self.state == "round" and self.phase == "wall":
            text += f";wall={self.wall_turns}"
        elif self.state == "round" and self.phase in ("about", "aside"):
            text += f";{self.phase}"
        elif self.state == "round":
            text += f";side={'left' if self.side < 0 else 'right'};leg={self.level};{self.phase}"
        if self.said is not None:
            text += f";open={self.said[0]:.2f}/{self.said[1]:.2f}"
        if self.views:
            text += ";views=" + "/".join(self.views)
        return text

    def _free(self, now: float) -> None:
        """The figure is going: what was learnt about the last obstacle is of no use at the next."""
        if self.state != "go":
            self._enter("go", now)
        self.push_since = None
        self.rounds = self.level = self.looked = 0
        self.indoors = self.place
        self.entered = False
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
            self._begin(now)
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

    def _begin(self, now: float) -> None:
        """Another obstacle, or another room: nothing learnt at the last one counts."""
        self.level = self.looked = 0
        self.indoors = self.place
        self.closed.clear()
        self.jumped.clear()
        self.views = []
        self.backed = False
        self.leg_jump, self.pressing = None, False
        self.way_out, self.outside = False, None

    def back_out(self, observation: Observation) -> None:
        """The figure has run into a building: out again by the way it came in.

        It still faces the way it ran in, and the arrow shows that facing against the camera's:
        the camera is turned until the figure faces it, and the figure runs into the picture.
        """
        now = observation.time
        self._begin(now)
        self.indoors = self.entered = self.way_out = True
        self.watch_at, self.watched = None, now
        self.views.append("back")
        arrow = observation.reading.arrow
        # The shorter way round, by the side the figure is turned to already.
        self._turn(observation, -1 if arrow is not None and arrow >= 0 else 1, self.ABOUT, "about")

    def leave(self, observation: Observation) -> None:
        """The walk begins in a room: the way out is looked for before the figure runs at a wall."""
        self._begin(observation.time)
        self.indoors = True
        self._look_on(observation, self.AHEAD)

    def _turn(self, observation: Observation, side: int, by: float, phase: str) -> None:
        """Begin a turn of the camera that is measured by the arrow, standing."""
        self.turn_side, self.turn_by, self.turn_from = side, by, observation.reading.arrow
        self.turn_took = 0.0
        self.phase = phase
        self._enter("round", observation.time)

    def _turned(self, observation: Observation) -> bool:
        """Whether the camera has gone as far round as the turn under way asks.

        By the arrow where it is seen to follow the camera; by the clock, at the rate measured
        outdoors, where it is not read or stays where it was.
        """
        since = observation.time - self.state_since
        by_clock = self.LOOK_TURN * self.turn_by / self.LOOK_STEP
        arrow = observation.reading.arrow
        if self.turn_from is None or arrow is None:
            return since >= by_clock
        gone = abs((arrow - self.turn_from + 180.0) % 360.0 - 180.0)
        if gone >= self.turn_by - self.TURN_LAG:
            return True
        if gone < self.TURN_SEEN:
            return since >= by_clock
        return since >= self.turn_by / self.TURN_RATE

    def _round(self, observation: Observation, toward) -> Steer:
        now = observation.time
        if not self._count(now):
            return self._fail(now)
        self._take_hint(now, toward)
        if self.ahead is not None and self.indoors is False and self.looked == 0:
            # Outdoors a side is felt for first, running.
            self.phase = "out"
            self._enter("round", now)
            return Steer(self._leg(toward), state="round")
        return self._look_on(observation, toward)

    def _look_on(self, observation: Observation, toward) -> Steer:
        """The next view: first the one as it stands, then the camera a step further round each
        time; with no model, or nothing left to look at, the way by feel, and in a room the
        round along its walls."""
        now = observation.time
        if self.ahead is None or self.looked > self.LOOKS:
            if self.ahead is not None and self.indoors:
                self.wall_turns = 0
                self.way_out, self.outside = True, None
                self.watch_at, self.watched = None, now
                self.views.append("wall")
                self.turn_side = self.side
                self.phase = "wall"
                self._enter("round", now)
                return Steer((0.0, 0.0), (float(self.side), 0.0), state="look")
            self._take_hint(now, toward)
            if self.side in self.closed and -self.side not in self.closed:
                self.side = -self.side
            self.phase = "out"
            self._enter("round", now)
            return Steer(self._leg(toward), state="round")
        self.looked += 1
        self.asked_at = None
        self._turn(observation, self.side, self.LOOK_STEP if self.looked > 1 else 0.0, "look")
        return Steer((0.0, 0.0), (float(self.side) if self.looked > 1 else 0.0, 0.0), state="look")

    def _wall(self, observation: Observation) -> Steer:
        """Round the room along its walls: a turn of the camera, and straight on until the figure stands."""
        now = observation.time
        since = now - self.state_since
        if since < self.WALL_TURN:
            return Steer((0.0, 0.0), (float(self.turn_side), 0.0), state="look")
        self._watch(observation)
        started = self.state_since + self.WALL_TURN + self.LEG_START
        if self.outside is not None or now - started >= self.WALL_FREE:
            # Out: the model says so, or nothing has held the figure up for longer than a room is wide.
            if self.outside is None:
                self.outside = now
                self.views.append("free")
            self.phase = "run"
            self._enter("round", now)
            return Steer(self.AHEAD, state="round")
        if now - started >= self.LEG_HELD_AFTER and self._stands(started, now):
            self.wall_turns += 1
            if self.wall_turns > self.WALL_TURNS:
                return self._fail(now)
            self._enter("round", now)
            return Steer((0.0, 0.0), (float(self.turn_side), 0.0), state="look")
        right = (self.nudge, 0.0) if now < self.nudge_until else (0.0, 0.0)
        return Steer(self.AHEAD, right, state="round")

    def _look(self, observation: Observation, toward) -> Steer:
        """Standing: the camera turns, its picture settles, and the model is asked about it."""
        now = observation.time
        since = now - self.state_since
        # The first view is the one the figure is held up in: no turn, and the feet have judged it.
        if self.turn_by:
            if not self._turned(observation):
                return Steer((0.0, 0.0), (float(self.turn_side), 0.0), state="look")
            self.turn_by, self.turn_took = 0.0, since
        turn = self.turn_took
        if since < turn + self.LOOK_SETTLE:
            return Steer((0.0, 0.0), state="look")
        if self.asked_at is None and self.ahead.ask(
            observation.frame, now, indoors=self.indoors, ahead=self.looked > 1
        ):
            self.asked_at = now
        view = None if self.asked_at is None else self.ahead.answer(self.asked_at)
        if view is None:
            if since < turn + self.LOOK_SETTLE + self.LOOK_WAIT:
                return Steer((0.0, 0.0), state="look")
            view = View(error="no answer")
        if self.indoors is None and view.indoors is not None:
            self.indoors = view.indoors >= SEEN
        if view.error is not None or self.indoors is None:
            # The model is not there: at this obstacle the way is felt for as before.
            self.views.append("none")
            self.looked = self.LOOKS + 1
        elif self.indoors:
            if view.exit is not None and view.exit >= self.OPEN:
                # The way out of the room, and the part of the picture it is in.
                parts = view.parts or (0.0, 1.0, 0.0)
                self.aim = max(range(3), key=lambda part: parts[part]) - 1 if max(parts) >= SEEN else 0
                self.views.append("exit" + "LMR"[self.aim + 1])
                self.way_out, self.outside = True, None
                self.watch_at, self.watched = None, now
                self.phase = "aim" if self.aim else "run"
                self._enter("round", now)
                stick = (0.0, 0.0) if self.aim else self.AHEAD
                return Steer(stick, (float(self.aim), 0.0), state="look" if self.aim else "round")
            self.views.append("room" if view.exit is None else f"room{view.exit:.2f}")
        elif view.open is not None:
            self.views.append(f"{view.open:.2f}")
            if view.open >= self.OPEN:
                self.way_out = False
                self.phase = "run"
                self._enter("round", now)
                return Steer(self.AHEAD, state="round")
        else:
            self.views.append("out")
            if not self.closed:
                # Outdoors a side is felt for first, running; the look goes on when it is closed.
                self.phase = "out"
                self._enter("round", now)
                return Steer(self._leg(toward), state="round")
        return self._look_on(observation, toward)

    def _watch(self, observation: Observation) -> None:
        """Running at a way out: where it is in the picture now, and whether the figure is outside."""
        now = observation.time
        if self.outside is not None:
            return
        if self.watch_at is None:
            due = now - self.watched >= self.WATCH_EVERY
            if due and self.ahead.ask(observation.frame, now, ahead=False):
                self.watch_at = now
            return
        view = self.ahead.answer(self.watch_at)
        if view is None:
            if now - self.watch_at >= self.LOOK_WAIT:
                self.watch_at, self.watched = None, now
            return
        self.watch_at, self.watched = None, now
        if view.indoors is not None and view.indoors < SEEN:
            self.outside, self.indoors = now, False
            self.views.append("outside")
        elif view.parts is not None and max(view.parts) >= SEEN:
            part = max(range(3), key=lambda index: view.parts[index]) - 1
            if part:
                self.nudge, self.nudge_until = float(part), now + self.AIM_TURN

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
