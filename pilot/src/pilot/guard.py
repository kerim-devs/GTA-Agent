"""The guard: rules that answer a threat on the same tick, without waiting for a model.

The reaction bench of 12 November (docs/LOG.md, "Ways of control, measured on 55 scenes") found that
readers and rules see a red marker or lit stars 36 ms after they are on the screen, the judge names a
threat in half of the scenes and seconds late, and a model head answers after eight seconds. So a
threat is answered here, in the tick, the way the flow reflex answers a menu, and the head hears of it
afterwards. A rule is started only by what the game draws and a reader reads exactly: the screen, the
stars, the health bar, a red marker on the minimap. No answer of a model starts one.

The conductor asks the guard on every tick, after the flow reflex and before the plan. One rule holds
the pad at a time, the one of the highest rank that counts, and a higher rank takes over from a lower
one at once. A rule that has let go leaves its threat to the head's rules, and nothing of lower rank
starts while it lasts. In a vehicle the guard puts nothing on the pad and only tells the head. Its
answers are skills that exist (`Walk`, `Fight`, `Face`), not pads of its own.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field, replace

from .combat import Fight, nearest_red
from .contract import NEUTRAL_PAD, Observation, Pad
from .mission import FIGHT_SECONDS
from .notes import intent
from .skills import Face, Walk

# A bar fading in after a black screen reads 0.0 for about 0.35 s although it is full (P64: enemy-13,
# 15 and 16), so health counts only once the HUD has been back this long.
HUD_SETTLE = 1.0
# A reading the reader abstains from stands out; the run it belongs to breaks after this long without
# one, as the conductor's star count does.
STAND_OUT = 1.0
# A rule that has let go answers again only after its signal has been gone this long, so that the stars
# the head is already fleeing from, or a marker a fight has given up on, do not take the pad back on the
# next tick. Two seconds is how long Fight waits without red before it calls a fight done.
RE_ARM = 2.0
# How long a flight lasts when its rule names no time of its own.
FLEE_SECONDS = 4.0


@dataclass(frozen=True)
class Rule:
    """One rule. `signal` names the method that reads it; `holds` says when it counts: ("seconds", s)
    the same reading held for s seconds, ("ticks", n, m) on n of the last m ticks. `lets_go` holds what
    ends it besides a rule of higher rank: "health" read back at that level, "seconds" after it took the
    pad, "plan" once the head's plan has started, "clear" seconds without red on the map, "skill" when
    its skill ends by itself."""

    rank: int
    name: str
    signal: str
    holds: tuple
    answer: str | None  # "flee", "fight" or "turn"; None is silence
    lets_go: dict = field(default_factory=dict)


RULES = (
    # A screen that takes no ordinary input, or the judge's mode none: the flow reflex has the screen, and
    # a cutscene, a black picture or a dead figure is not answered.
    Rule(1, "screen", "screen", ("ticks", 2, 2), None),
    # Half a second, as the conductor reports low health, once the HUD has been back for a second.
    Rule(2, "low_health", "low_health", ("seconds", 0.5), "flee", {"health": 0.45, "seconds": 4.0}),
    # The same number of stars on two readings 0.1 s apart. Flee and never fire: the head's wanted rules
    # bring the car and the route.
    Rule(3, "stars", "stars", ("seconds", 0.1), "flee", {"plan": True, "seconds": 4.0}),
    # A red marker inside the map, as the reflex and the take-out rule read it: fight as Fight does.
    Rule(4, "red", "red_inside", ("ticks", 2, 3), "fight", {"skill": True}),
    # Red pinned to the map's edge and none inside: out of range at an unknown distance, so the camera
    # turns to its bearing and nothing is fired along it.
    Rule(5, "red_edge", "red_edge", ("ticks", 2, 3), "turn", {"clear": 2.0}),
)


@dataclass(frozen=True)
class Verdict:
    """What the guard says on one tick. A pad of None leaves the tick to the plan."""

    pad: Pad | None = None
    rule: str | None = None  # the rule that holds the pad, or that counts while the guard only tells
    why: str = ""
    events: tuple[dict, ...] = ()  # guard_start, guard_end and guard_news, for the head
    abandon: bool = False  # drop the head's request in flight, so that the rules are asked at once


class _Held:
    """The same reading for `seconds`; a reading of nothing breaks it, an abstention stands out."""

    def __init__(self, seconds):
        self.seconds = seconds
        self.value = self.since = self.seen = None
        self.counting = False

    @property
    def first(self):
        """When the reading that counts was first read."""
        return self.since

    def update(self, value, t):
        if value is None:
            if self.value is not None and t - self.seen > STAND_OUT:
                self.value = self.since = None
                self.counting = False
            return self.counting
        if not value:
            self.value = self.since = None
            self.counting = False
            return False
        if value != self.value:
            self.value, self.since = value, t
        self.seen = t
        self.counting = t - self.since >= self.seconds
        return self.counting


class _Ticks:
    """On n of the last m ticks that said anything; a tick that says nothing stands out."""

    def __init__(self, n, m):
        self.n = n
        self.window = deque(maxlen=m)
        self.counting = False

    @property
    def first(self):
        """The first tick of the window on which the signal was read."""
        return next((t for on, t in self.window if on), None)

    def update(self, value, t):
        if value is None:
            return self.counting
        self.window.append((bool(value), t))
        self.counting = sum(on for on, _ in self.window) >= self.n
        return self.counting


def bearing(blip) -> float | None:
    """Picture degrees of a marker from the arrow: 0 straight ahead, positive to the right."""
    return None if blip is None else round(math.degrees(math.atan2(blip.x, blip.y)), 1)


class Guard:
    def __init__(self, rules=RULES):
        self.rules = tuple(sorted(rules, key=lambda rule: rule.rank))
        self.counters = {
            rule.name: _Held(rule.holds[1]) if rule.holds[0] == "seconds" else _Ticks(*rule.holds[1:])
            for rule in self.rules
        }
        self.absent = {rule.name: None for rule in self.rules}
        self.spent = set()  # rules that have let go, until their signal has been gone for RE_ARM
        self.told = set()  # rules the head has heard of while the guard kept off the pad
        self.holder = self.since = self.skill = self.answer = None
        self.why = ""
        self.where = None  # "foot" or "vehicle", as last read without stars
        self.stars_lit = False
        self.hud_since = None
        self.last_red = None
        self.observation = None
        self.flow = False
        # One entry per episode for the bench and the logs: the rule, when it took the pad or told the
        # head, when and why it let go, and on how many ticks it aimed, fired, turned and sprinted.
        self.episodes = []

    @property
    def holding(self) -> str | None:
        return None if self.holder is None else self.holder.name

    def settled(self, t) -> bool:
        """The HUD has been back long enough for its health bar to be read."""
        return self.hud_since is not None and t - self.hud_since >= HUD_SETTLE

    # ------------------------------------------------------------------ signals

    def screen(self, observation):
        reading, hud = observation.reading, observation.hud
        if self.flow or observation.mode == "none" or (hud is not None and hud.screen != "game"):
            return True
        return None if reading.corrupt else reading.minimap == "none"

    def low_health(self, observation):
        if not self.settled(observation.time):
            return False
        health = None if observation.hud is None else observation.hud.health
        if health is None or not math.isfinite(health):
            return None
        return health < 1 / 3

    def stars(self, observation):
        return None if observation.hud is None else observation.hud.wanted

    def _reds(self, observation):
        if observation.reading.corrupt:
            return None
        # No fight while stars are lit: the red is the police's, and theirs are the wanted rules.
        return [] if self.stars_lit else [b for b in observation.reading.blips if b.color == "red"]

    def red_inside(self, observation):
        reds = self._reds(observation)
        return None if reds is None else any(not blip.border for blip in reds)

    def red_edge(self, observation):
        reds = self._reds(observation)
        return None if reds is None else bool(reds) and all(blip.border for blip in reds)

    # ------------------------------------------------------------------ the tick

    def tick(
        self,
        observation: Observation,
        *,
        objective: str = "",
        moving: bool = False,
        plan_since: float | None = None,
        flow: bool = False,
    ) -> Verdict:
        """`moving`: a skill of the plan has the figure. `plan_since`: when the head's last plan was put in
        the runner. `flow`: the flow reflex holds this tick."""
        t = observation.time
        self.observation, self.flow = observation, flow
        where = self._read(observation)
        counting = []
        for rule in self.rules:
            value = getattr(self, rule.signal)(observation)
            if self.counters[rule.name].update(value, t):
                counting.append(rule)
            if value:
                self.absent[rule.name] = None
            elif value is not None:
                if self.absent[rule.name] is None:
                    self.absent[rule.name] = t
                if t - self.absent[rule.name] >= RE_ARM:
                    self.spent.discard(rule.name)
                    self.told.discard(rule.name)
        top = counting[0] if counting else None

        screen = top is not None and top.answer is None
        if screen or flow:
            # The screen is the flow reflex's. Nothing starts on it, and what the guard holds it lets go
            # of once the screen counts; a first odd reading decides nothing.
            return self._release(t, "screen") if screen and self.holder is not None else Verdict()
        if top is not None and top.name in self.spent:
            if self.holder is not None and self.holder.rank > top.rank:
                return self._release(t, f"{top.name} is left to the head")
            top = None  # what the head's rules answer now; nothing of lower rank starts
        if where != "foot":
            return self._vehicle(top, t, where)

        if self.holder is not None:
            if top is not None and top.rank < self.holder.rank:
                return self._take(top, t, objective, after=self.holder.name)
            pad, ended = self._step(t, plan_since)
            if ended:
                return self._release(t, ended)
            self._count(pad)
            return Verdict(pad, self.holder.name, self.why)
        if top is None:
            return Verdict()
        if top.answer == "turn" and moving:
            # A turn of the camera would steer the walk the plan is on: the head hears of it, and the
            # guard turns once nothing moves the figure.
            news = () if top.name in self.told else (self._news(top, t, "moving"),)
            self.told.add(top.name)
            return Verdict(None, top.name, f"{top.name}: a skill moves the figure", news)
        return self._take(top, t, objective)

    def _read(self, observation):
        """Where the figure is, whether stars are lit, and since when the HUD has been back."""
        t, reading, hud = observation.time, observation.reading, observation.hud
        if hud is not None and hud.wanted is not None:
            self.stars_lit = hud.wanted > 0
        if not reading.corrupt:
            if any(blip.color == "red" for blip in reading.blips):
                self.last_red = t
            present = (
                hud is not None
                and hud.screen == "game"
                and observation.mode != "none"
                and reading.minimap != "none"
            )
            if not present:
                self.hud_since = None
            elif self.hud_since is None:
                self.hud_since = t
        if observation.mode in ("foot", "vehicle"):
            self.where = observation.mode
        elif observation.mode is None and not reading.corrupt:
            if reading.minimap == "flat":
                self.where = "foot"
            elif reading.minimap == "tilted" and not self.stars_lit:
                # docs/LOG.md, 11 November: with stars the map tilts on foot as well, so a tilted map with
                # stars says nothing, and the figure is where it was before the stars.
                self.where = "vehicle"
        return self.where

    # ------------------------------------------------------------------ answers

    def _vehicle(self, top, t, where):
        """In a vehicle, or nowhere known: nothing on the pad, and the head hears of the threat once."""
        events = []
        held = self.holder is not None
        if held:
            events.append(self._let_go(t, "vehicle"))
        news = top is not None and top.name not in self.told
        if news:
            self.told.add(top.name)
            self.spent.add(top.name)
            events.append(self._news(top, t, where or "unknown"))
        return Verdict(
            NEUTRAL_PAD if held else None,
            top.name if news else None,
            "news for the head",
            tuple(events),
            abandon=news,
        )

    def _take(self, rule, t, objective, after=None):
        if self.holder is not None:
            self._close(t, f"{rule.name} took over")
        nearest = nearest_red(self.observation.reading)
        answer = rule.answer
        if answer == "fight" and intent(objective)["class"] == "escape":
            answer = "flee"
        self.holder, self.since, self.answer = rule, t, answer
        self.skill = self._skill(rule, answer, nearest)
        self.why = f"{rule.name}: {answer}"
        self.episodes.append(
            {
                "rule": rule.name,
                "seen": self.counters[rule.name].first,
                "from": t,
                "answer": answer,
                "bearing": bearing(nearest),
                "ticks": 0,
            }
        )
        event = {
            "kind": "guard_start",
            "rule": rule.name,
            "rank": rule.rank,
            "answer": answer,
            "bearing": bearing(nearest),
            # The first tick on which the signal was read, before it counted: a live run is timed from it.
            "seen": self.counters[rule.name].first,
            **({"after": after} if after else {}),
        }
        pad, _ = self._step(t, None)
        self._count(pad)
        return Verdict(pad, rule.name, self.why, (event,))

    @staticmethod
    def _skill(rule, answer, nearest):
        if answer == "fight":
            return Fight({"duration": float(FIGHT_SECONDS), "cover": "no"})
        if answer == "turn":
            return Face({"color": "red", "duration": 5.0})
        if nearest is None or math.hypot(nearest.x, nearest.y) < 1:
            x, y = 0.0, -1.0  # straight ahead
        else:
            # Away from the marker: the map's x is the stick's, and its y points up where the stick's
            # points down.
            distance = math.hypot(nearest.x, nearest.y)
            x, y = -nearest.x / distance, nearest.y / distance
        seconds = rule.lets_go.get("seconds", FLEE_SECONDS)
        return Walk({"duration": seconds, "x": x, "y": y, "sprint": True})

    def _step(self, t, plan_since):
        """The holder's pad on this tick, and why it lets go, if it does."""
        rule, observation = self.holder, self.observation
        lets_go = rule.lets_go
        hud = observation.hud
        if hud is not None and not self.settled(t):
            # A bar fading in reads empty, and Fight ends on an empty bar: on the bench the fights that
            # started as the HUD came back after a black screen ended on their second tick (P65,
            # enemy-19 and enemy-20). Neither the rule nor its skill sees health until the HUD settles.
            hud = replace(hud, health=None)
            observation = replace(observation, hud=hud)
        health = None if hud is None else hud.health
        if "health" in lets_go and health is not None and health >= lets_go["health"]:
            return NEUTRAL_PAD, "health back"
        if "seconds" in lets_go and t - self.since >= lets_go["seconds"]:
            return NEUTRAL_PAD, "time"
        if lets_go.get("plan") and plan_since is not None and plan_since >= self.since:
            return NEUTRAL_PAD, "head plan started"
        if "clear" in lets_go and t - max(self.since, self.last_red or self.since) >= lets_go["clear"]:
            return NEUTRAL_PAD, "no red left"
        result = self.skill.step(observation)
        if result.status != "running":
            if self.answer == "turn" and result.status == "done":
                # Facing the marker: hold still until it comes inside or is gone.
                self.skill = Face({"color": "red", "duration": 5.0})
                return NEUTRAL_PAD, None
            return NEUTRAL_PAD, result.reason or result.status
        pad = result.pad
        wanted = None if hud is None else hud.wanted
        if (pad.l2 > 0 or pad.r2 > 0) and (self.stars_lit or bool(wanted)):
            # Never fire, nor aim, while stars are lit; one reading of them is enough to hold the trigger.
            pad = NEUTRAL_PAD
        return pad, None

    def _count(self, pad):
        episode = self.episodes[-1]
        episode["ticks"] += 1
        for key, on in (
            ("aim", pad.l2 > 0),
            ("fire", pad.r2 > 0),
            ("turn", any(pad.right)),
            ("sprint", bool(pad.buttons)),
            ("walk", any(pad.left)),
        ):
            if on:
                episode[key] = episode.get(key, 0) + 1

    def _close(self, t, reason):
        self.episodes[-1].update({"until": t, "reason": reason})
        if self.skill is not None:
            self.skill.stop("guard-let-go")
        self.holder = self.skill = self.answer = None

    def _let_go(self, t, reason):
        rule, seconds = self.holder, round(t - self.since, 3)
        event = {"kind": "guard_end", "rule": rule.name, "reason": reason, "seconds": seconds}
        self._close(t, reason)
        self.spent.add(rule.name)
        return event

    def _release(self, t, reason):
        """Let go: this tick carries the neutral pad, and the head hears why."""
        return Verdict(NEUTRAL_PAD, None, f"let go: {reason}", (self._let_go(t, reason),))

    def _news(self, rule, t, where):
        nearest = nearest_red(self.observation.reading)
        self.episodes.append({"rule": rule.name, "from": t, "news": where, "bearing": bearing(nearest)})
        return {
            "kind": "guard_news",
            "rule": rule.name,
            "rank": rule.rank,
            "where": where,
            "bearing": bearing(nearest),
            "seen": self.counters[rule.name].first,
        }
