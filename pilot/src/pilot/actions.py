"""What Kerim does in a recording, as stretches of one action each, for a model that learns to name it.

A recording of his play holds the picture (`video.mp4`, `frames.jsonl`) and his controller (`pad.jsonl`,
every change on the clock of the frames). The action at a frame is decided from his hand first, read event by
event so that a press shorter than the sampling is kept, and from the cheap pixel readers second: the minimap
class and route, the screen the HUD reader names, the wanted level and whether the map moves. Text recognition
and the object detector are never used. Where the evidence does not decide, the action is `unknown`.

His hand leads the picture: an input reaches the console and comes back as a changed frame some time later,
about 0.14 s over the cable and more over Wi-Fi. Every recording carries that lead in itself, because the
camera turns when the right stick is pushed; `estimate_lead` finds the shift at which the stick and the
turning picture agree best. The frame at time t is then labelled with the hand of the window that ends at
t - lead, so that every label stays on the clock of the frames and describes what that frame shows.
"""

from __future__ import annotations

import itertools
import json
import math
import random
import time
from bisect import bisect_left, bisect_right
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from .contract import HUD_RECT, Pad
from .profile import GTA5, Profile

# The closed list. The first group is what the pilot's skills can carry out (drive_route, enter_vehicle,
# walk, walk_to, look, fight, melee, punch, wait, set_waypoint on the map); the rest is what a player
# visibly does besides.
ACTIONS = (
    "follow_route",  # driving with a route on the minimap
    "drive_free",  # driving with no route
    "reverse_or_turn",  # in a vehicle, L2 held without R2: reversing, or a long brake into a turn
    "enter_vehicle",  # from the press of the enter button on foot until the vehicle's map
    "leave_vehicle",  # from the press of the same button in a vehicle until the figure is on foot
    "walk",  # on foot, left stick pushed
    "sprint",  # on foot, left stick pushed with the sprint button tapped (gta5) or held
    "aim",  # on foot, L2 held
    "fire",  # on foot, R2 pulled
    "melee",  # on foot, the melee button pressed
    "look",  # only the right stick: the camera turns
    "cover",  # on foot, the cover button pressed
    "use_phone",  # the phone is on screen
    "menu",  # pause menu, interaction menu, weapon wheel
    "map",  # the pause map
    "wait",  # loading, a banner, a cutscene: the game takes no ordinary input
    "idle",  # the hand at rest in play
    "unknown",
)
DRIVING = ("follow_route", "drive_free")
# Actions that may last a single sample: a press is never smoothed away.
EVENTS = ("fire", "melee", "cover", "enter_vehicle", "leave_vehicle")

SAMPLE_HZ = 10
INDEX_HZ = 2
# Measured on 20261111-164039 (Wi-Fi, 11 November): the camera follows the right stick best 0.20 s later,
# correlation 0.59, with a broad top from 0.14 to 0.22 s. Used only where a recording does not say itself.
DEFAULT_LEAD = 0.2
LEAD_SEARCH = (0.0, 1.5, 0.02)
LEAD_MIN_CORRELATION = 0.3

STICK_REST = 0.2  # a thumb at rest reads up to about 0.1; the camera does not turn below 0.3
LOOK_STICK = 0.35
SPRINT_STICK = 0.5
TRIGGER_REST = 0.1
PEDAL = 0.2
TRIGGER_PULLED = 0.5
SUSTAIN = 1.0  # a minimap class counts after a second: on foot it reads tilted for up to 0.83 s
SPRINT_TAP = 0.5  # gta5 sprint is a tap every 0.2 to 0.3 s; a pause of half a second ends it
COVER_HOLD = 0.5
LONG_L2 = 0.6  # shorter is a brake inside a drive
ENTER_WINDOW = 8.0  # getting in, a hijack included, takes two to six seconds
LEAVE_WINDOW = 4.0
LEAVE_QUIET = 1.5  # the exit animation; a hand on the pedals in that time means the press did nothing
IDLE_MIN = 1.0
COAST = 1.5  # a car let off R2 rolls for longer than this
STRONG_TILT = 5.0
FROZEN = 20.0  # an unchanged pad that is not neutral for this long is a controller lying on its sticks

WAIT_SCREENS = ("loading", "failed", "passed", "wasted", "busted")
MENU_SCREENS = ("pause", "interaction_menu", "weapon_wheel")


@dataclass(frozen=True)
class Layout:
    """Which button does what, from the game profile where it holds the button, else the GTA V default."""

    sprint: str
    sprint_held: bool
    enter: str
    melee: str
    cover: str
    wheel: str = "l1"  # held on foot: the weapon wheel

    @classmethod
    def of(cls, profile: Profile) -> Layout:
        return cls(profile.sprint, profile.sprint_held, profile.enter_vehicle, profile.melee, profile.cover)


GTA5_LAYOUT = Layout.of(GTA5)


# --- the controller, event by event


def load_controller(recording: Path, source: str = "human") -> list[tuple[float, Pad]] | None:
    """Every change of the controller, or None for a recording with the controller on the console: such a
    recording has at most one line, and a hand that was never seen is not a hand at rest."""
    path = recording / "pad.jsonl"
    if not path.exists():
        return None
    events = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("src") != source:
            continue
        events.append((float(row["t"]), pad_of(row)))
    events.sort(key=lambda item: item[0])
    if len(events) < 2:
        return None
    return events


def pad_of(row: dict) -> Pad:
    return Pad(
        buttons=tuple(row.get("buttons", ())),
        left=tuple(row.get("left", (0.0, 0.0))),
        right=tuple(row.get("right", (0.0, 0.0))),
        l2=float(row.get("l2", 0.0)),
        r2=float(row.get("r2", 0.0)),
    )


def rest(pad: Pad) -> bool:
    return (
        not pad.buttons
        and math.hypot(*pad.left) < STICK_REST
        and math.hypot(*pad.right) < STICK_REST
        and pad.l2 < TRIGGER_REST
        and pad.r2 < TRIGGER_REST
    )


@dataclass(frozen=True)
class Hand:
    """What the controller did in one window of hand time: maxima and every press that began in it."""

    left: float = 0.0  # highest stick magnitude
    right: float = 0.0
    l2: float = 0.0
    r2: float = 0.0
    l2_time: float = 0.0  # seconds in the window with the trigger above PEDAL
    r2_time: float = 0.0
    held: frozenset[str] = frozenset()  # buttons down at any moment of the window
    pressed: frozenset[str] = frozenset()  # buttons whose press began in the window
    presses: tuple[tuple[str, float], ...] = ()  # (button, hand time) of every press in the window
    neutral: bool = True  # nothing at any moment of the window
    still: float = 0.0  # seconds since the last change, at the end of the window
    state: Pad = field(default_factory=Pad)  # the state at the end of the window


class Controller:
    def __init__(self, events: list[tuple[float, Pad]]):
        self.times = [t for t, _ in events]
        self.pads = [pad for _, pad in events]

    def state_at(self, t: float) -> Pad:
        index = bisect_right(self.times, t) - 1
        return self.pads[index] if index >= 0 else Pad()

    def window(self, start: float, end: float) -> Hand:
        # A line at the very start of the window belongs to it, so a press on a sample boundary counts.
        first = bisect_left(self.times, start)
        last = bisect_left(self.times, end)
        index = first - 1
        current = self.pads[index] if index >= 0 else Pad()
        changed = self.times[index] if index >= 0 else -math.inf
        states = [current]
        presses = []
        l2_time = r2_time = 0.0
        moment = start
        for i in range(first, last):
            t, pad = self.times[i], self.pads[i]
            l2_time += (t - moment) * (current.l2 > PEDAL)
            r2_time += (t - moment) * (current.r2 > PEDAL)
            presses.extend((button, t) for button in pad.buttons if button not in current.buttons)
            current, moment, changed = pad, t, t
            states.append(pad)
        l2_time += (end - moment) * (current.l2 > PEDAL)
        r2_time += (end - moment) * (current.r2 > PEDAL)
        return Hand(
            left=max(math.hypot(*pad.left) for pad in states),
            right=max(math.hypot(*pad.right) for pad in states),
            l2=max(pad.l2 for pad in states),
            r2=max(pad.r2 for pad in states),
            l2_time=l2_time,
            r2_time=r2_time,
            held=frozenset(button for pad in states for button in pad.buttons),
            pressed=frozenset(button for button, _ in presses),
            presses=tuple(presses),
            neutral=all(rest(pad) for pad in states),
            still=end - changed,
            state=current,
        )


# --- what the readers saw


@dataclass(frozen=True)
class Look:
    """The cheap pixel readers at one sampled frame."""

    minimap: str = "none"  # "flat" | "tilted" | "none"
    route: str = "none"
    corrupt: bool = False
    screen: str = "game"
    wanted: int | None = None
    moving: bool | None = None  # the map moved between this frame and the one 0.2 s before
    pan: float | None = None  # horizontal picture motion in pixels a second of a 256 px wide view
    section: str | None = None  # the P38 section kind at this time, when sections were given


@dataclass(frozen=True)
class Sample:
    index: int  # frame index in the video
    time: float  # on the clock of frames.jsonl
    end: float  # time of the next sample; the frames from index to last belong to this one
    last: int
    look: Look
    hand: Hand | None = None


def sample_indices(rows: list[dict], hz: float = SAMPLE_HZ) -> list[int]:
    """The first frame at or after every 1/hz seconds, by the times in frames.jsonl, never by a frame rate."""
    selected, deadline = [], None
    for row in rows:
        t = row["t"]
        if deadline is None:
            deadline = t
        if t + 1e-9 >= deadline:
            selected.append(row["i"])
            deadline += (math.floor((t - deadline + 1e-9) * hz) + 1) / hz
    return selected


def frame_rows(recording: Path) -> list[dict]:
    rows = [
        json.loads(line) for line in (recording / "frames.jsonl").read_text().splitlines() if line.strip()
    ]
    previous = -math.inf
    for index, row in enumerate(rows):
        if row["i"] != index or not math.isfinite(row["t"]) or row["t"] <= previous:
            raise ValueError("frames.jsonl must have contiguous indices and increasing times")
        previous = row["t"]
    return rows


def attach_hands(samples: list[Sample], controller: Controller | None, lead: float) -> list[Sample]:
    if controller is None:
        return [replace(sample, hand=None) for sample in samples]
    output = []
    run_start = -math.inf
    for i, sample in enumerate(samples):
        if i and sample.time - samples[i - 1].end > 1:
            run_start = sample.time
        known = bisect_right(controller.times, sample.time - lead) - 1
        hand = (
            controller.window(sample.time - lead, sample.end - lead)
            if run_start == -math.inf or (known >= 0 and controller.times[known] >= run_start)
            else None
        )
        output.append(replace(sample, hand=hand))
    return output


# --- the lead of the hand


def estimate_lead(samples: list[Sample], controller: Controller | None) -> tuple[float | None, float | None]:
    """The delay at which the right stick and the turning picture agree best, with the correlation.
    None when the recording has too little camera work to tell."""
    if controller is None:
        return None, None
    usable = [
        s
        for s in samples
        if s.look.pan is not None
        and s.look.screen == "game"
        and s.look.minimap != "none"
        and not s.look.corrupt
    ]
    if len(usable) < 200:
        return None, None
    # A pan is measured between a sample and the one before it, so it belongs to the middle of the two.
    times = np.array([s.time - 0.5 / SAMPLE_HZ for s in usable])
    pan = -np.array([s.look.pan for s in usable])
    best = (None, -1.0)
    lo, hi, step = LEAD_SEARCH
    for lag in np.arange(lo, hi + 1e-9, step):
        stick = np.array([controller.state_at(t - lag).right[0] for t in times])
        if np.count_nonzero(np.abs(stick) > 0.3) < 30 or np.std(stick) < 1e-6:
            continue
        correlation = float(np.corrcoef(pan, stick)[0, 1])
        if correlation > best[1] + 1e-9:
            best = (round(float(lag), 3), correlation)
    if best[0] is None:
        return None, None
    return best


# --- the figure's mode: on foot or in a vehicle


def map_kind(look: Look, wanted: int | None) -> str | None:
    """What the minimap alone says. With stars the game tilts the map on foot as well, so a tilted map with
    stars, or with a level not read, decides nothing."""
    if look.corrupt:
        return None
    if look.screen != "game" or look.minimap == "none":
        return "none"
    if look.minimap == "flat":
        return "foot"
    if wanted == 0:
        return "vehicle"
    return "starred"


def sustained(samples: list[Sample]) -> list[str | None]:
    """The map kind where it lasted a second, damaged samples bridged; elsewhere None."""
    wanted, kinds = None, []
    seen_at = -math.inf
    for s in samples:
        if s.look.wanted is not None:
            wanted, seen_at = s.look.wanted, s.time
        elif s.time - seen_at > 3.0:
            wanted = None
        kind = map_kind(s.look, wanted)
        if kind == "starred" and s.look.section in ("foot", "drive"):
            kind = "foot" if s.look.section == "foot" else "vehicle"
        kinds.append(kind)
    # A damaged sample takes the kind of its neighbours when both sides agree.
    filled = list(kinds)
    i = 0
    while i < len(filled):
        if filled[i] is None:
            j = i
            while j < len(filled) and filled[j] is None:
                j += 1
            before = filled[i - 1] if i > 0 else None
            after = filled[j] if j < len(filled) else None
            if before is not None and before == after:
                filled[i:j] = [before] * (j - i)
            i = j
        else:
            i += 1
    result: list[str | None] = [None] * len(samples)
    i = 0
    while i < len(filled):
        j = i
        while j < len(filled) and filled[j] == filled[i]:
            j += 1
        end = samples[j].time if j < len(samples) else samples[-1].end
        if filled[i] is not None and end - samples[i].time >= SUSTAIN - 1e-9:
            result[i:j] = [filled[i]] * (j - i)
        i = j
    return result


def modes(samples: list[Sample], layout: Layout) -> tuple[list[str | None], dict[int, str]]:
    """The mode per sample and the samples of a confirmed getting in or out.

    A flat map that lasts a second puts the figure on foot. A tilted one does not by itself put it in a
    vehicle once it is known to be on foot: in alleys and under bridges the reader calls the map tilted for
    seconds with the figure on foot. Getting in is a press of the enter button after which the map turns
    over within ENTER_WINDOW seconds, or, where stars keep the map tilted, after which R2 is held for half a
    second with no sprint. Getting out is the same button followed by a flat map within LEAVE_WINDOW, or by a
    quiet pedal for LEAVE_QUIET seconds and then a stick. A tilted map without a press counts only when it
    lasts STRONG_TILT seconds with R2 held for a second in it: a recording that starts in a car, or a
    cutscene that ends in one."""
    kinds = sustained(samples)
    strong = _strong_tilt(samples, kinds)
    result: list[str | None] = [None] * len(samples)
    transitions: dict[int, str] = {}
    mode = None
    k = 0
    while k < len(samples):
        if kinds[k] == "foot" or (kinds[k] == "vehicle" and (mode is None or strong[k])):
            mode = kinds[k]
        result[k] = mode
        hand = samples[k].hand
        if hand is not None and layout.enter in hand.pressed and samples[k].look.screen == "game":
            confirmed = _confirm(samples, kinds, k, mode, layout)
            if confirmed is not None:
                for m in range(k, confirmed):
                    result[m] = mode
                    transitions[m] = "enter_vehicle" if mode == "foot" else "leave_vehicle"
                mode = "vehicle" if mode == "foot" else "foot"
                k = confirmed
                continue
        k += 1
    return result, transitions


def _strong_tilt(samples: list[Sample], kinds: list[str | None]) -> list[bool]:
    strong = [False] * len(samples)
    i = 0
    while i < len(kinds):
        j = i
        while j < len(kinds) and kinds[j] == kinds[i]:
            j += 1
        if kinds[i] == "vehicle":
            end = samples[j].time if j < len(samples) else samples[-1].end
            pedal = sum(s.hand.r2_time for s in samples[i:j] if s.hand is not None)
            if end - samples[i].time >= STRONG_TILT and pedal >= 1.0:
                strong[i:j] = [True] * (j - i)
        i = j
    return strong


def _confirm(samples, kinds, k, mode, layout) -> int | None:
    start = samples[k].time
    if mode == "foot":
        pedal = 0.0
        for j in range(k + 1, len(samples)):
            s = samples[j]
            # The map stays flat while the figure walks to the door, so only time ends the wait.
            if s.time - start > ENTER_WINDOW or (hand_pressed(s, layout.enter) and j > k):
                return None
            if kinds[j] == "vehicle":
                return j
            hand = s.hand
            if hand is None:
                continue
            if layout.sprint in hand.pressed or hand.l2 > TRIGGER_PULLED:
                pedal = 0.0
                continue
            pedal += hand.r2_time
            if pedal >= 0.5 and kinds[j] in ("starred", None):
                return j
        return None
    if mode == "vehicle":
        for j in range(k + 1, len(samples)):
            s = samples[j]
            if s.time - start > LEAVE_WINDOW or hand_pressed(s, layout.enter):
                return None
            if kinds[j] == "foot":
                return j
            hand = s.hand
            if hand is None:
                continue
            if hand.l2 > PEDAL or hand.r2 > PEDAL:
                return None
            walking = hand.left >= STICK_REST or layout.sprint in hand.pressed
            if s.time - start >= LEAVE_QUIET and walking and kinds[j] in ("starred", None):
                return j
        return None
    return None


def hand_pressed(sample: Sample, button: str) -> bool:
    return sample.hand is not None and button in sample.hand.pressed


# --- the decision


@dataclass(frozen=True)
class Context:
    mode: str | None
    transition: str | None = None
    route: bool | None = (
        None  # a route on the minimap around this sample; None where every reading is damaged
    )
    moving: bool | None = None
    no_hud: bool = False  # the game screen without a minimap for a second
    long_l2: bool = False
    sprinting: bool = False  # the sprint button tapped within SPRINT_TAP, or held
    covering: bool = False
    coasting: bool = False  # R2 held within COAST seconds
    has_pad: bool = True


def decide(sample: Sample, context: Context, layout: Layout) -> tuple[str, str]:
    """One sample's action and the rule that gave it. Replaceable: `label` takes any function like it."""
    look, hand = sample.look, sample.hand
    if look.screen in WAIT_SCREENS:
        return "wait", f"screen {look.screen}"
    if look.screen == "map":
        return "map", "screen map"
    if look.screen == "phone":
        return "use_phone", "screen phone"
    if look.screen in MENU_SCREENS:
        return "menu", f"screen {look.screen}"
    if look.section in ("cutscene", "loading", "banner"):
        return "wait", f"section {look.section}"
    if context.transition is not None:
        return context.transition, "enter button, then the mode changed"
    if hand is None:
        return "unknown", "no controller in the recording"
    if hand.still >= FROZEN and not hand.neutral:
        return "unknown", "controller unchanged for 20 s and not at rest"
    if context.no_hud:
        if hand.left < STICK_REST and hand.right < LOOK_STICK and max(hand.l2, hand.r2) < PEDAL:
            return "wait", "no minimap on the game screen, hand quiet"
        return "unknown", "no minimap on the game screen, hand busy"
    if context.mode == "vehicle":
        return _vehicle(hand, context)
    if context.mode == "foot":
        return _foot(hand, context, layout)
    if hand.neutral and look.minimap != "none":
        return "idle", "hand at rest, mode unknown"
    if (
        hand.right >= LOOK_STICK
        and hand.left < STICK_REST
        and max(hand.l2, hand.r2) < PEDAL
        and not hand.held
    ):
        return "look", "right stick only, mode unknown"
    return "unknown", "mode unknown"


def _driving(context: Context, rule: str) -> tuple[str, str]:
    if context.route is None:
        return "unknown", f"{rule}, route unreadable"
    return ("follow_route", f"{rule}, route") if context.route else ("drive_free", f"{rule}, no route")


def _vehicle(hand: Hand, context: Context) -> tuple[str, str]:
    if context.long_l2 and hand.r2 < PEDAL:
        return "reverse_or_turn", "vehicle, L2 held without R2"
    if hand.r2 >= PEDAL:
        return _driving(context, "vehicle, R2")
    if hand.l2 >= PEDAL:
        return _driving(context, "vehicle, brake")
    if context.moving is True:
        return _driving(context, "vehicle, rolling")
    if context.moving is False:
        if hand.neutral:
            return "idle", "vehicle standing, hand at rest"
        if hand.right >= LOOK_STICK and hand.left < STICK_REST:
            return "look", "vehicle standing, right stick only"
        return "unknown", "vehicle standing, no pedal"
    # The map's motion cannot be read: a car released from R2 a moment ago is still rolling.
    if context.coasting:
        return _driving(context, "vehicle, coasting after R2")
    return "unknown", "vehicle, no pedal, motion unreadable"


def _foot(hand: Hand, context: Context, layout: Layout) -> tuple[str, str]:
    if hand.r2 >= TRIGGER_PULLED:
        return "fire", "on foot, R2"
    if layout.melee in hand.pressed:
        return "melee", f"on foot, {layout.melee}"
    if hand.l2 >= TRIGGER_PULLED:
        return "aim", "on foot, L2"
    if layout.cover in hand.pressed or (context.covering and hand.left < STICK_REST):
        return "cover", f"on foot, {layout.cover}"
    if layout.wheel in hand.held and hand.left < STICK_REST:
        return "menu", f"on foot, {layout.wheel} held: weapon wheel"
    if hand.left >= SPRINT_STICK and context.sprinting:
        return "sprint", f"on foot, left stick with {layout.sprint}"
    if hand.left >= STICK_REST:
        return "walk", "on foot, left stick"
    if hand.right >= LOOK_STICK:
        return "look", "on foot, right stick only"
    if hand.neutral:
        # The map's motion is not used here: on foot it calls a figure at rest moving too often.
        return "idle", "on foot, hand at rest"
    return "unknown", "on foot, " + "+".join(sorted(hand.held)) if hand.held else "on foot, small stick"


def contexts(samples: list[Sample], layout: Layout, has_pad: bool, lead: float = 0.0) -> list[Context]:
    mode_of, transitions = modes(samples, layout)
    times = [s.time for s in samples]
    out = []
    last_sprint = last_cover = last_r2 = -math.inf
    for k, s in enumerate(samples):
        hand = s.hand
        if hand is not None:
            for button, t in hand.presses:
                if button == layout.sprint:
                    last_sprint = t
                if button == layout.cover:
                    last_cover = t
        hand_end = s.end - lead
        sprinting = hand is not None and (
            (layout.sprint_held and layout.sprint in hand.held) or hand_end - last_sprint <= SPRINT_TAP
        )
        covering = hand is not None and hand_end - last_cover <= COVER_HOLD
        if hand is not None and hand.r2 >= PEDAL:
            last_r2 = hand_end
        coasting = hand is not None and hand_end - last_r2 <= COAST
        lo, hi = bisect_left(times, s.time - 1.0), bisect_right(times, s.time + 1.0)
        clean = [o.look for o in samples[lo:hi] if not o.look.corrupt and o.look.minimap != "none"]
        route = None if not clean else sum(o.route != "none" for o in clean) >= 0.4 * len(clean)
        near = [
            o.look.moving for o in samples[bisect_left(times, s.time - 0.3) : bisect_right(times, s.time)]
        ]
        known = [m for m in near if m is not None]
        moving = known[-1] if known else None
        no_hud = _no_hud(samples, times, k)
        out.append(
            Context(
                mode=mode_of[k],
                transition=transitions.get(k),
                route=route,
                moving=moving,
                no_hud=no_hud,
                long_l2=_long_l2(samples, k),
                coasting=coasting,
                sprinting=sprinting,
                covering=covering,
                has_pad=has_pad,
            )
        )
    return out


def _no_hud(samples, times, k) -> bool:
    look = samples[k].look
    if look.screen != "game" or look.minimap != "none" or look.corrupt:
        return False
    lo, hi = bisect_left(times, times[k] - 1.0), bisect_right(times, times[k] + 1.0)
    window = [s.look for s in samples[lo:hi] if not s.look.corrupt]
    span_before = [s.look for s in samples[lo : k + 1] if not s.look.corrupt]
    span_after = [s.look for s in samples[k:hi] if not s.look.corrupt]
    gone = lambda looks: looks and all(o.minimap == "none" and o.screen == "game" for o in looks)  # noqa: E731
    return bool(window) and (
        (gone(span_before) and times[k] - times[lo] >= SUSTAIN - 0.15)
        or (gone(span_after) and times[hi - 1] - times[k] >= SUSTAIN - 0.15)
    )


def _long_l2(samples, k) -> bool:
    """L2 held without R2 over a stretch of at least LONG_L2 seconds that covers this sample."""

    def held(s):
        return s.hand is not None and s.hand.l2_time >= 0.5 * (s.end - s.time) and s.hand.r2 < PEDAL

    if not held(samples[k]):
        return False
    i = j = k
    while i > 0 and held(samples[i - 1]):
        i -= 1
    while j + 1 < len(samples) and held(samples[j + 1]):
        j += 1
    return samples[j].end - samples[i].time >= LONG_L2 - 1e-9


# --- stretches


SMOOTHABLE = ("walk", "sprint", "look", "idle", *DRIVING, "reverse_or_turn")


def label(
    samples: list[Sample],
    *,
    layout: Layout = GTA5_LAYOUT,
    has_pad: bool = True,
    decision: Callable[[Sample, Context, Layout], tuple[str, str]] = decide,
    lead: float = 0.0,
) -> list[dict]:
    """Stretches of one action over the samples, with what each was decided from."""
    if not samples:
        return []
    boundaries = [0, *(i for i in range(1, len(samples)) if samples[i].time - samples[i - 1].end > 1)]
    if len(boundaries) > 1:
        boundaries.append(len(samples))
        return [
            stretch
            for first, stop in itertools.pairwise(boundaries)
            for stretch in label(
                samples[first:stop], layout=layout, has_pad=has_pad, decision=decision, lead=lead
            )
        ]
    decided = [
        decision(s, c, layout) for s, c in zip(samples, contexts(samples, layout, has_pad, lead), strict=True)
    ]
    actions = [action for action, _ in decided]
    _smooth(samples, actions)
    _short_rests(samples, actions, decided)
    stretches = []
    i = 0
    while i < len(samples):
        j = i
        while j < len(samples) and actions[j] == actions[i]:
            j += 1
        stretches.append(_stretch(samples[i:j], actions[i], [rule for _, rule in decided[i:j]], lead))
        i = j
    return stretches


def _smooth(samples: list[Sample], actions: list[str]) -> None:
    """A flicker shorter than 0.3 s between two stretches of the same ongoing action joins them; a press,
    `unknown` and anything the screen decided are never smoothed away."""
    i = 0
    while i < len(actions):
        j = i
        while j < len(actions) and actions[j] == actions[i]:
            j += 1
        if 0 < i and j < len(actions) and actions[i - 1] == actions[j] and actions[j] in SMOOTHABLE:
            if actions[i] in SMOOTHABLE and samples[j].time - samples[i].time < 0.3 - 1e-9:
                actions[i:j] = [actions[j]] * (j - i)
        i = j


def _short_rests(samples: list[Sample], actions: list[str], decided: list[tuple[str, str]]) -> None:
    """A hand at rest for less than IDLE_MIN between two inputs is not a figure at rest: a fist fight, a
    bicycle rolling on or a gun being lowered goes on in the picture. Such a pause is `unknown`."""
    i = 0
    while i < len(actions):
        j = i
        while j < len(actions) and actions[j] == actions[i]:
            j += 1
        if (
            actions[i] == "idle"
            and 0 < i
            and j < len(actions)
            and samples[j].time - samples[i].time < IDLE_MIN
        ):
            actions[i:j] = ["unknown"] * (j - i)
            decided[i:j] = [("unknown", "hand at rest for less than a second")] * (j - i)
        i = j


def _stretch(samples: list[Sample], action: str, rules: list[str], lead: float) -> dict:
    hands = [s.hand for s in samples if s.hand is not None]
    looks = [s.look for s in samples]
    pressed = Counter(button for hand in hands for button, _ in hand.presses)
    wanted = [look.wanted for look in looks if look.wanted is not None]
    moving = [look.moving for look in looks if look.moving is not None]
    span = samples[-1].end - samples[0].time
    rest_time = sum(s.end - s.time for s in samples if s.hand is not None and s.hand.neutral)
    return {
        "start": round(samples[0].time, 4),
        "end": round(samples[-1].end, 4),
        "first_frame": samples[0].index,
        "last_frame": samples[-1].last,
        "action": action,
        "evidence": {
            "rule": Counter(rules).most_common(1)[0][0],
            "hand": None
            if not hands
            else {
                "pressed": dict(sorted(pressed.items())),
                "left": round(max(h.left for h in hands), 2),
                "right": round(max(h.right for h in hands), 2),
                "l2": round(max(h.l2 for h in hands), 2),
                "r2": round(max(h.r2 for h in hands), 2),
                "rest": round(rest_time / span, 2) if span > 0 else None,
            },
            "readers": {
                "minimap": dict(
                    Counter("damaged" if look.corrupt else look.minimap for look in looks).most_common()
                ),
                "route": sorted({look.route for look in looks if look.route != "none" and not look.corrupt}),
                "screen": sorted({look.screen for look in looks}),
                "wanted": max(wanted) if wanted else None,
                "moving": round(sum(moving) / len(moving), 2) if moving else None,
                **(
                    {"section": sorted({look.section for look in looks if look.section})}
                    if any(look.section for look in looks)
                    else {}
                ),
            },
            "lead": lead,
        },
    }


# --- a recording


def load_sections(path: Path) -> list[tuple[float, float, str]]:
    """The sections of P38 as (start, end, kind)."""
    data = json.loads(path.read_text())
    return [(float(s["start"]), float(s["end"]), str(s["kind"])) for s in data.get("sections", [])]


def _section_at(sections: list[tuple[float, float, str]], t: float) -> str | None:
    for start, end, kind in sections:
        if start <= t < end:
            return kind
    return None


PAN_RECT = (160, 120, 960, 360)  # x, y, w, h: the middle of the picture, clear of the HUD
PAN_SIZE = (256, 96)


def sample_windows(rows: list[dict], picks: list[int]) -> tuple[list[float], list[int]]:
    """Use the recorded clock, ending each window before any missing footage."""
    from .trimming import frame_runs

    run_ends = {i: stop for first, stop in frame_runs(rows) for i in range(first, stop)}
    ends, lasts = [], []
    for position, first in enumerate(picks):
        stop = min(picks[position + 1] if position + 1 < len(picks) else len(rows), run_ends[first])
        lasts.append(stop - 1)
        ends.append(rows[stop]["t"] if stop < run_ends[first] else rows[stop - 1]["t"])
    return ends, lasts


def read_recording(recording: Path, sections: list[tuple[float, float, str]] | None = None) -> list[Sample]:
    """Run the cheap readers over a recording at SAMPLE_HZ. Every frame is decoded once and only the sampled
    ones are converted; nothing is kept beyond the last few crops."""
    import cv2

    from .hud import read as read_hud
    from .minimap import read as read_map
    from .motion import map_motion, motion_state

    rows = frame_rows(recording)
    picks = sample_indices(rows)
    if not picks:
        return []
    ends, lasts = sample_windows(rows, picks)
    wanted = set(picks)
    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    if not capture.isOpened():
        raise ValueError(f"cannot open {recording / 'video.mp4'}")
    window = cv2.createHanningWindow(PAN_SIZE, cv2.CV_32F)
    x, y, w, h = HUD_RECT
    px, py, pw, ph = PAN_RECT
    samples: list[Sample] = []
    crops: list[tuple[float, np.ndarray]] = []
    previous = None
    pick = 0
    try:
        for row in rows:
            if not capture.grab():
                raise ValueError(f"video ends before frame {row['i']}")
            if row["i"] not in wanted:
                continue
            ok, bgr = capture.retrieve()
            if not ok:
                raise ValueError(f"cannot decode frame {row['i']}")
            t = row["t"]
            if previous is not None and t - previous[0] > 1:
                previous = None
                crops = []
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            if rgb.shape[:2] != (720, 1280):
                rgb = cv2.resize(rgb, (1280, 720), interpolation=cv2.INTER_AREA)
            crop = np.ascontiguousarray(rgb[y : y + h, x : x + w])
            reading = read_map(crop)
            hud = read_hud(rgb)
            moving = None
            older = [c for c in crops if t - c[0] >= 0.15]
            if older:
                moving = motion_state(map_motion(older[-1][1], crop))
            crops = [*crops[-3:], (t, crop)]
            gray = cv2.cvtColor(
                cv2.resize(rgb[py : py + ph, px : px + pw], PAN_SIZE, interpolation=cv2.INTER_AREA),
                cv2.COLOR_RGB2GRAY,
            ).astype(np.float32)
            pan = None
            if previous is not None and t > previous[0]:
                (dx, _dy), response = cv2.phaseCorrelate(previous[1], gray, window)
                if response > 0.05:
                    pan = dx / (t - previous[0])
            previous = (t, gray)
            samples.append(
                Sample(
                    index=row["i"],
                    time=t,
                    end=ends[pick],
                    last=lasts[pick],
                    look=Look(
                        minimap=reading.minimap,
                        route=reading.route,
                        corrupt=reading.corrupt,
                        screen=hud.screen,
                        wanted=hud.wanted,
                        moving=moving,
                        pan=pan,
                        section=_section_at(sections, t) if sections else None,
                    ),
                )
            )
            pick += 1
    finally:
        capture.release()
    return samples


def finished(recording: Path) -> bool:
    """A folder still being recorded has a meta.json without "seconds"."""
    try:
        meta = json.loads((recording / "meta.json").read_text())
    except (OSError, ValueError):
        return False
    return meta.get("seconds") is not None and (recording / "video.mp4").exists()


def label_recording(
    recording: Path,
    out_root: Path,
    *,
    sections: Path | None = None,
    lead: float | None = None,
    profile: Profile = GTA5,
) -> dict:
    """Label one finished recording into out_root/<name>/actions.jsonl, with labels.json beside it."""
    started = time.perf_counter()
    if not finished(recording):
        raise ValueError(f"{recording} is not a finished recording")
    layout = Layout.of(profile)
    samples = read_recording(recording, load_sections(sections) if sections else None)
    events = load_controller(recording)
    controller = Controller(events) if events else None
    has_gaps = any(right.time - left.end > 1 for left, right in itertools.pairwise(samples))
    estimated, correlation = (None, None) if has_gaps else estimate_lead(samples, controller)
    if lead is not None:
        used, source = lead, "given"
    elif estimated is not None and correlation is not None and correlation >= LEAD_MIN_CORRELATION:
        used, source = estimated, "estimated"
    else:
        used, source = DEFAULT_LEAD, "default"
    samples = attach_hands(samples, controller, used)
    stretches = label(samples, layout=layout, has_pad=controller is not None, lead=used)
    meta = json.loads((recording / "meta.json").read_text())
    minutes = Counter()
    for stretch in stretches:
        minutes[stretch["action"]] += (stretch["end"] - stretch["start"]) / 60
    info = {
        "recording": str(recording.resolve()),
        "seconds": meta.get("seconds"),
        "sample_hz": SAMPLE_HZ,
        "has_pad": controller is not None,
        "lead": used,
        "lead_source": source,
        "lead_estimate": estimated,
        "lead_correlation": None if correlation is None else round(correlation, 3),
        "game": profile.name,
        "sections": None if sections is None else str(sections),
        "stretches": len(stretches),
        "minutes": {action: round(value, 3) for action, value in sorted(minutes.items())},
        "elapsed": round(time.perf_counter() - started, 1),
    }
    target = out_root / recording.name
    target.mkdir(parents=True, exist_ok=True)
    (target / "labels.json").write_text(json.dumps(info, indent=2) + "\n")
    # actions.jsonl is written last and whole, so a folder that has it is complete.
    partial = target / "actions.jsonl.part"
    with partial.open("w") as out:
        for stretch in stretches:
            out.write(json.dumps(stretch) + "\n")
    partial.replace(target / "actions.jsonl")
    return info


# --- the data set


def _stretches(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def index_rows(labelled: Path, recording: Path | None = None) -> Iterator[dict]:
    """INDEX_HZ samples of one labelled recording: frame, time, action and the controller at the hand time
    that frame answers (time less the lead). No pixels: a training job reads them from the video by index."""
    info = json.loads((labelled / "labels.json").read_text())
    recording = Path(info["recording"]) if recording is None else recording
    rows = frame_rows(recording)
    stretches = _stretches(labelled / "actions.jsonl")
    events = load_controller(recording) if info["has_pad"] else None
    controller = Controller(events) if events else None
    starts = [s["start"] for s in stretches]
    for i in sample_indices(rows, INDEX_HZ):
        t = rows[i]["t"]
        k = bisect_right(starts, t + 1e-9) - 1
        if k < 0:
            continue
        pad = None
        if controller is not None:
            state = controller.state_at(t - info["lead"])
            pad = {
                "buttons": list(state.buttons),
                "left": list(state.left),
                "right": list(state.right),
                "l2": state.l2,
                "r2": state.r2,
            }
        yield {
            "recording": info["recording"],
            "frame": i,
            "time": round(t, 4),
            "action": stretches[k]["action"],
            "pad": pad,
        }


def write_index(out_root: Path, recordings: Iterable[Path] = ()) -> dict:
    """DIR/index.jsonl over everything labelled so far and DIR/summary.md. `recordings` are roots in which
    a recording is looked up by name when the path in its labels.json is gone, as after a move to a disk."""
    roots = list(recordings)
    folders = sorted(
        p.parent for p in out_root.glob("*/actions.jsonl") if (p.parent / "labels.json").exists()
    )
    per: dict[str, dict] = {}
    partial = out_root / "index.jsonl.part"
    count = 0
    with partial.open("w") as out:
        for folder in folders:
            info = json.loads((folder / "labels.json").read_text())
            source = Path(info["recording"])
            if not (source / "frames.jsonl").exists():
                found = [
                    root / folder.name for root in roots if (root / folder.name / "frames.jsonl").exists()
                ]
                if not found:
                    print(f"skipped {folder.name}: recording not found at {source}")
                    continue
                source = found[0]
            for row in index_rows(folder, source):
                row["recording"] = str(source)
                out.write(json.dumps(row) + "\n")
                count += 1
            minutes, stretches = Counter(), Counter()
            for stretch in _stretches(folder / "actions.jsonl"):
                minutes[stretch["action"]] += (stretch["end"] - stretch["start"]) / 60
                stretches[stretch["action"]] += 1
            per[folder.name] = {"info": info, "minutes": minutes, "stretches": stretches}
    partial.replace(out_root / "index.jsonl")
    (out_root / "summary.md").write_text(summary(per, count))
    return {"recordings": len(per), "samples": count}


def summary(per: dict[str, dict], samples: int) -> str:
    names = sorted(per)
    total = sum((p["minutes"] for p in per.values()), Counter())
    stretches = sum((p["stretches"] for p in per.values()), Counter())
    all_minutes = sum(total.values())
    lines = [
        "# Action labels",
        "",
        f"{len(names)} recordings, {all_minutes:.1f} minutes, {samples} samples at {INDEX_HZ} a second "
        "in `index.jsonl`. Minutes and stretches per action over all of them, then minutes per recording.",
        "",
        "| action | minutes | share | stretches |",
        "|---|---:|---:|---:|",
    ]
    for action in ACTIONS:
        if total[action] or stretches[action]:
            share = total[action] / all_minutes if all_minutes else 0
            lines.append(f"| {action} | {total[action]:.1f} | {share:.1%} | {stretches[action]} |")
    lines += ["", "| recording | minutes | lead s | stretches | unknown |", "|---|---:|---:|---:|---:|"]
    for name in names:
        p = per[name]
        minutes = sum(p["minutes"].values())
        unknown = p["minutes"]["unknown"] / minutes if minutes else 0
        info = p["info"]
        lead = f"{info['lead']:.2f} ({info['lead_source']})" if info["has_pad"] else "no controller"
        lines.append(f"| {name} | {minutes:.1f} | {lead} | {sum(p['stretches'].values())} | {unknown:.1%} |")
    used = [a for a in ACTIONS if total[a]]
    lines += ["", "| recording | " + " | ".join(used) + " |", "|---|" + "---:|" * len(used)]
    for name in names:
        lines.append(f"| {name} | " + " | ".join(f"{per[name]['minutes'][a]:.1f}" for a in used) + " |")
    lines += ["", "| stretches | " + " | ".join(used) + " |", "|---|" + "---:|" * len(used)]
    for name in names:
        lines.append(f"| {name} | " + " | ".join(str(per[name]["stretches"][a]) for a in used) + " |")
    return "\n".join(lines) + "\n"


def training_frames(
    index: Path, *, actions: Iterable[str] | None = None, limit: int | None = None, seed: int | None = None
) -> Iterator[tuple[np.ndarray, dict]]:
    """(frame, label) for the samples of an index, the frame as 1280x720 RGB read from the recording's video.
    `actions` keeps only those labels, `seed` draws `limit` samples at random instead of the first ones.
    Each video is read once from the front, so the samples come grouped by recording in frame order."""
    import cv2

    keep = None if actions is None else set(actions)
    rows = [json.loads(line) for line in index.read_text().splitlines() if line.strip()]
    rows = [row for row in rows if keep is None or row["action"] in keep]
    if limit is not None:
        rows = random.Random(seed).sample(rows, min(limit, len(rows))) if seed is not None else rows[:limit]
    by_recording: dict[str, list[dict]] = {}
    for row in rows:
        by_recording.setdefault(row["recording"], []).append(row)
    for recording, chosen in by_recording.items():
        chosen.sort(key=lambda row: row["frame"])
        capture = cv2.VideoCapture(str(Path(recording) / "video.mp4"))
        try:
            position = 0
            for row in chosen:
                while position < row["frame"]:
                    if not capture.grab():
                        raise ValueError(f"{recording}: video ends before frame {row['frame']}")
                    position += 1
                ok, bgr = capture.read()
                position += 1
                if not ok:
                    raise ValueError(f"{recording}: cannot decode frame {row['frame']}")
                yield cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), row
        finally:
            capture.release()
