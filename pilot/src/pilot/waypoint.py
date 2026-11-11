"""Picture-checked pause-map navigation. Registration belongs to the skill registry."""

import base64
import math
import re
import zlib
from dataclasses import dataclass
from typing import ClassVar

import cv2
import numpy as np

from .contract import Observation, Pad, SkillResult
from .hud import read as read_hud
from .profile import active
from .scene import SceneText, TextReader

# The outlined map badge differs from the plain legend glyph at the opening zoom.
# Grayscale 25x25 crop centred at (750, 207), 20261111-124637 frame 155.
_LIVE_S = np.repeat(
    np.frombuffer(
        zlib.decompress(
            base64.b85decode(
                "c-jGR0*?J$PBwe;`}y~AM_OB1SXy3RV1Zp$Urt9bSz=z<`0f7Oa$Q_nVq#%rWNB|sSz=yMQg(Qe{rUFlpE*cve|T+ZW@Tz<P+MVWR9{_0nf~~>hBzQABspG#b#8BaWmsNfUs{hZHQBUYO^dR?pMN|uUUhkUgJoc2V@p`eGi{kh$MWs*^zrcWuq!ujYI1*mdT>T+`6iZ9!t(#>sh_#=^!=?ai?XnrfOu_p$@e{YY5DToGAc(%R_5>aTPG|^aH5r))cX8(c$okGbs~VuLmP+m{csZ*4FMQqfm!AM&VrEl{kt1Tn==U#J5NWG^XR5E2MikC^7*1?`|b49f>A620&)EM{QdXy_Z9#q`t|bZTcZB@_Wt|dr)EBR{rvs>{rsOV8IJq=|IajC*Yf@G{p$JSay@ThY*ubi#ThdH@AT_r8Y4%5wdMZ)?E6>+1_==c9^FL;-1((?LMSFcZyPUm-1_(D85l`ELC^ks5Ulh_kdAf~E2t4YlR@+M{4`DP_VfSqg$9Z7PvQLbDI3NkFZ3$*_Vh)v^YZ@m?REgR?Qf>?`LHoc6cbBv?)A}4{`mj@`Swf;@A;@n>GJv3rGbda>Gkz!q5Sy$^8daSL;Lythgj$R{`v6e`TXQ;T<`Pv`TBz~8n5^9tdC1EOP;~e$C_9(i2wfb|NgWZ1~vNs>Oed;CMhN=RT?l11vjF$!m3dt0UJB-|L#jRN=-^)UB0Wd$v_bk7Z?u!F}&Qn_3`(Cb*s<O^7;7t`u+RLk859LuE+TL|M>U&r?%Ys{QUa#+rq1ok&A(Ie@#^I|NQ&^&*y0Q"
            )
        ),
        dtype=np.uint8,
    ).reshape(25, 25, 1),
    3,
    axis=2,
)


def map_screen(frame: np.ndarray, text: SceneText) -> str | None:
    """Recognise the selected map tab or the interactive map, never just an absent HUD."""
    if frame.shape != (720, 1280, 3) or frame.dtype != np.uint8:
        return None
    lines = [line for line in text.lines if line.confidence >= 0.5]
    footer = " ".join(line.text.lower() for line in lines if line.box[1] > 650)
    header = " ".join(line.text.lower() for line in lines if line.box[1] < 155)
    # Other pause pages have the same tab names. Require the white selected KARTE tab.
    tab = frame[123:145, 215:345]
    selected = np.mean(np.min(tab, axis=2) > 205) > 0.65
    overview = (
        selected
        and "karte" in header
        and any(word in header for word in ("statistiken", "einstellungen", "grand theft", "spiel"))
    )
    if "karte" in header and "zoomen" in footer and "weiterbl" in footer:
        return "transition"
    if overview:
        return "overview"
    if (
        "wegpunkt" in footer
        and "zoomen" in footer
        and any(word in footer for word in ("markierung", "interessanter ort", "wenig details"))
    ):
        return "map"
    return None


@dataclass(frozen=True)
class MapPicture:
    screen: str | None = None
    cursor: tuple[float, float] | None = None
    player: tuple[float, float] | None = None
    missions: tuple[tuple[float, float], ...] = ()
    roads: tuple[tuple[float, float], ...] = ()
    waypoint: bool = False
    proof: str | None = None


def _matches(frame, template, threshold=0.85):
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    tile = cv2.cvtColor(template, cv2.COLOR_RGB2GRAY)
    if tile.std() < 15:
        return ()
    scores = cv2.matchTemplate(gray[160:570, 220:990], tile, cv2.TM_CCOEFF_NORMED)
    points = []
    for _ in range(12):
        _, score, _, (x, y) = cv2.minMaxLoc(scores)
        if score < threshold:
            break
        points.append((x + 220 + (tile.shape[1] - 1) / 2, y + 160 + (tile.shape[0] - 1) / 2))
        scores[max(0, y - 15) : y + 16, max(0, x - 15) : x + 16] = -1
    return tuple(points)


def _track(frame, template, previous):
    candidates = []
    for point in _matches(frame, template, 0.45):
        if math.dist(point, previous) >= 120:
            continue
        x, y = map(round, point)
        patch = frame[y - 12 : y + 13, x - 12 : x + 13]
        yy, xx = np.mgrid[y - 12 : y + 13, x - 12 : x + 13]
        # The stationary crosshair occludes the moving target; compare the remaining pixels.
        mask = ~(
            ((abs(xx - 640) <= 2) & (abs(yy - 360) <= 56)) | ((abs(yy - 360) <= 2) & (abs(xx - 640) <= 56))
        )
        a, b = template[mask].astype(float).ravel(), patch[mask].astype(float).ravel()
        a -= a.mean()
        b -= b.mean()
        denominator = np.linalg.norm(a) * np.linalg.norm(b)
        if denominator and a @ b / denominator >= 0.8:
            candidates.append((float(a @ b / denominator), point))
    candidates.sort(reverse=True)
    if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 0.08:
        return []
    return [candidates[0][1]] if candidates else []


def read_map(frame: np.ndarray, text: SceneText) -> MapPicture:
    screen = map_screen(frame, text)
    if screen != "map":
        return MapPicture(screen)
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    # The recorded interactive map pans under a fixed centre crosshair.
    vertical = gray[315:405, 639:642].max(axis=1)
    horizontal = gray[359:362, 595:685].max(axis=0)
    cursor = (640.0, 360.0) if (vertical > 180).mean() > 0.75 and (horizontal > 180).mean() > 0.75 else None
    player = None
    missions = []
    for line in text.lines:
        if line.confidence < 0.8 or line.box[0] < 1000:
            continue
        words = line.text.split()
        y = line.box[1] + line.box[3] // 2
        if words and words[0].lower() == "spieler":
            points = _matches(frame, frame[y - 8 : y + 9, 1197:1212])
            if len(points) == 1:
                player = points[0]
        # Only a named mission giver with an explicit letter in the legend supplies a template.
        if len(words) >= 2 and words[-1] in {"S", "L", "M", "F", "T", "B", "D", "H"}:
            missions.extend(_matches(frame, frame[y - 8 : y + 9, 1197:1212]))
        # Native OCR sometimes separates the legend's S into its own line.
        if words and words[0].lower() == "simeon":
            for point in _matches(frame, _LIVE_S, 0.8):
                if all(math.dist(point, other) > 15 for other in missions):
                    missions.append(point)
    # Thin bright, neutral road strokes surrounded by dark map pixels, excluding the legend.
    neutral = frame.max(axis=2).astype(int) - frame.min(axis=2).astype(int) < 25
    white = (gray > 185) & neutral
    dark = (gray < 110).astype(np.float32)
    density = cv2.boxFilter(dark, -1, (15, 15))
    road = white & (density > 0.35) & (density < 0.85)
    road[:180] = False
    road[540:] = False
    road[:, :250] = False
    road[:, 950:] = False
    yy, xx = np.where(road)
    roads = tuple(zip(xx[::12].astype(float), yy[::12].astype(float), strict=True))
    hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
    purple = cv2.inRange(hsv[330:391, 610:671], (130, 80, 70), (165, 255, 255))
    legend = next(
        (
            line.text
            for line in text.lines
            if line.confidence >= 0.8
            and line.box[0] >= 1000
            and re.search(r"wegpunkt\s*\([\d.,\s]+\s*(?:m|km)\)", line.text.lower())
        ),
        None,
    )
    route = cv2.inRange(hsv[170:565, 230:980], (130, 80, 70), (165, 255, 255))
    count, _, stats, _ = cv2.connectedComponentsWithStats(route)
    drawn = any(
        stats[i, cv2.CC_STAT_AREA] >= 100
        and max(stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]) >= 60
        for i in range(1, count)
    )
    proof = f"waypoint legend: {legend}" if legend else "route on the map" if drawn else None
    return MapPicture(screen, cursor, player, tuple(missions), roads, cv2.countNonZero(purple) >= 12, proof)


def _map_features(frame):
    if frame.shape != (720, 1280, 3) or frame.dtype != np.uint8:
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    neutral = frame.max(axis=2).astype(int) - frame.min(axis=2).astype(int) < 30
    mask = ((gray > 120) & neutral).astype(np.uint8) * 255
    mask[:165] = 0
    mask[565:] = 0
    mask[:, :230] = 0
    mask[:, 980:] = 0
    mask[300:420, 580:700] = 0  # Fixed cursor, including its occlusion of streets.
    points = cv2.goodFeaturesToTrack(gray, 250, 0.01, 8, mask=mask)
    if points is None or len(points) < 16:
        return None
    return gray, points


def map_shift(before, after):
    """Return a supported translation, or None when damage/motion cannot be separated.

    Only neutral road features vote; the coloured paused scene and fixed UI do not.
    A majority must agree in several regions, with matching local pixel patches in
    both pictures. A damaged pair is never added to the travelled distance.
    """
    a, b = _map_features(before), _map_features(after)
    if a is None or b is None:
        return None
    moved, forward, error = cv2.calcOpticalFlowPyrLK(a[0], b[0], a[1], None, winSize=(31, 31), maxLevel=4)
    returned, backward, _ = cv2.calcOpticalFlowPyrLK(b[0], a[0], moved, None, winSize=(31, 31), maxLevel=4)
    valid = (
        (forward[:, 0] == 1)
        & (backward[:, 0] == 1)
        & (error[:, 0] < 20)
        & (np.linalg.norm(a[1] - returned, axis=2)[:, 0] < 1.5)
    )
    start, end = a[1][:, 0][valid], moved[:, 0][valid]
    if len(start) < 16 or valid.mean() < 0.65:
        return None
    shifts = end - start
    delta = np.median(shifts, axis=0)
    consistent = np.linalg.norm(shifts - delta, axis=1) < 2
    if consistent.sum() < 16 or consistent.mean() < 0.8:
        return None
    start, end = start[consistent], end[consistent]
    if np.any((end[:, 0] < 235) | (end[:, 0] > 975) | (end[:, 1] < 170) | (end[:, 1] > 560)):
        keep = (end[:, 0] >= 235) & (end[:, 0] <= 975) & (end[:, 1] >= 170) & (end[:, 1] <= 560)
        start, end = start[keep], end[keep]
        if len(start) < 16:
            return None
    if np.ptp(start[:, 0]) < 100 or np.ptp(start[:, 1]) < 80:
        return None

    errors = []
    for first, second in zip(start, end, strict=True):
        x, y = np.rint(first).astype(int)
        u, v = np.rint(second).astype(int)
        left = a[0][y - 5 : y + 6, x - 5 : x + 6].astype(float)
        right = b[0][v - 5 : v + 6, u - 5 : u + 6].astype(float)
        errors.append(np.mean(np.abs(left - right)))
    if np.mean(np.array(errors) < 25) < 0.85:
        return None
    return tuple(float(value) for value in np.median(shifts[consistent], axis=0))


def land_at_cursor(frame, centre=(640, 360)):
    # Open water is flat. Require street/terrain detail around (not on) the cursor;
    # uncertainty is treated like water, including the coloured scene behind the map.
    x, y = map(round, centre)
    patch = frame[y - 32 : y + 33, x - 32 : x + 33]
    gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY)
    neutral = patch.max(axis=2).astype(int) - patch.min(axis=2).astype(int) < 30
    mask = np.ones(gray.shape, bool)
    mask[28:37] = False
    mask[:, 28:37] = False
    dark = (gray < 150) & neutral & mask
    edges = cv2.Canny(gray, 70, 140) > 0
    return bool(dark.sum() >= 250 and (edges & neutral & mask).sum() >= 35)


def map_motion(before, after):
    """Confirm movement on the fine live grid without treating its pitch as distance."""
    if _map_features(before) is None or _map_features(after) is None:
        return None
    estimates = []
    for left in (250, 700):
        roads = []
        for frame in (before, after):
            patch = frame[165:565, left:980]
            gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY).astype(np.float32)
            neutral = (patch.max(axis=2) - patch.min(axis=2) < 30) & (patch.min(axis=2) > 120)
            roads.append(np.where(neutral, gray, 0))
        delta, response = cv2.phaseCorrelate(*roads)
        if response < 0.4 or not np.isfinite(delta).all() or np.linalg.norm(delta) > 160:
            return None
        estimates.append(np.array(delta))
    if np.linalg.norm(estimates[0] - estimates[1]) > 2:
        return None
    if np.linalg.norm(estimates[0]) >= 2:
        # Pacific Bluffs has no roads in the old upper strip. Require spread among
        # the visible roads instead; neither the paused car nor sea is movement proof.
        a, b = before[165:565, 250:980], after[165:565, 250:980]
        roads = ((a.max(axis=2) - a.min(axis=2) < 30) & (a.min(axis=2) > 120)) | (
            (b.max(axis=2) - b.min(axis=2) < 30) & (b.min(axis=2) > 120)
        )
        changed = np.max(np.abs(a.astype(int) - b.astype(int)), axis=2) > 30
        yy, xx = np.where(roads & changed)
        if len(xx) < 100 or np.ptp(xx) < 100 or np.ptp(yy) < 80:
            return None
    return tuple(estimates[0])


BLIND_SECONDS = 2.0


class SetWaypoint:
    name = "set_waypoint"
    opens = ("pause", "map")
    parameters: ClassVar = {
        "target": ("mission", "away"),
        "duration": (1.0, 45.0, 45.0),
        "direction": ("any", "north", "east", "south", "west"),
        "distance": ("near", "far"),
    }
    directions: ClassVar = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}
    distances: ClassVar = {"near": 100.0, "far": 220.0}
    counter = 0
    prompt = (
        "Set a waypoint to a recognised mission letter, or pan away by a near/far amount. "
        "Away needs no player marker; direction any rotates. Needs fresh readable German map pictures. "
        "Fails and backs out on an unverified screen, missing target/cursor, or time limit."
    )
    settle = 1.3  # Exceeds the recorded Wi-Fi picture delay of 0.6-1.1 s.
    SLOW_TICK = 0.07  # two ticks of the loop
    LATE = 1.0
    max_exits = 3

    def __init__(self, args: dict):
        self.profile = active()
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("expected target, duration, direction and distance")
        self.target = args.get("target", "mission")
        if not isinstance(self.target, str) or self.target not in self.parameters["target"]:
            raise ValueError("target must be mission or away")
        for key in ("direction", "distance"):
            value = args.get(key, self.parameters[key][0])
            if not isinstance(value, str) or value not in self.parameters[key]:
                raise ValueError(f"invalid {key}")
        self.direction = args.get("direction", "any")
        self.distance = self.distances[args.get("distance", "near")]
        if self.target == "away" and self.direction == "any":
            self.direction = tuple(self.directions)[SetWaypoint.counter % 4]
            SetWaypoint.counter += 1
        self.displacement = np.zeros(2)
        self.alternate_used = False
        self.inland_used = False
        self.push_seconds = 0.10
        self.push_rate = None
        self.unmeasured = False
        self.travel_seconds = 0.0
        self.travel_goal = 0.8 if args.get("distance", "near") == "near" else 2.0
        # Which way the map moves under the stick was fitted on one noisy clip. The first
        # push that moves the map settles it; a map that runs the other way turns the stick.
        self.sense = 1
        self.sense_known = False
        duration = args.get("duration", 45.0)
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(duration)
        ):
            raise ValueError("duration must be finite")
        self.limit = min(45.0, max(1.0, duration))
        self.started = None
        self.last_time = None
        self.finished = None
        self.phase = "open"
        self.ready_at = 0.0
        self.release_at = 0.0
        self.hold = None
        self.pressed = 0.0
        self.held = Pad()
        self.reader = None
        self.failure = None
        self.exits = 0
        self.point = None
        self.template = None
        self.previous_distance = None
        self.aim_gain = None
        self.moves = 0
        self.proved_waypoint = False
        self.waypoint_proof = None
        self.previous_proof = None
        self.confirm_since = None
        self.command_frame = None
        self.current_frame = None
        self.blind_since = None
        self.game_since = None

    def stop(self, reason="interrupted") -> SkillResult:
        self.finished = SkillResult(status="failed", reason=reason)
        return self.finished

    def _press(self, pad, now, phase, seconds=0.10):
        self.phase = phase
        self.held = pad
        self.hold = seconds
        self.pressed = now
        self.release_at = now + seconds
        self.ready_at = self.release_at + self.settle
        self.command_frame = None if self.current_frame is None else self.current_frame.copy()
        return SkillResult(pad)

    def _fail(self, reason):
        self.failure = reason
        self.phase = "exit"
        self.held = Pad()
        self.release_at = 0.0
        self.hold = None
        return SkillResult()

    def _picture(self, frame):
        if self.reader is None:
            self.reader = TextReader()
        return read_map(frame, self.reader.read(frame))

    def _game(self, observation):
        if (
            observation.frame is None
            or (self.command_frame is not None and np.array_equal(observation.frame, self.command_frame))
            or (observation.hud is not None and observation.hud.screen != "game")
        ):
            self.game_since = None
            return False
        if (
            not observation.reading.corrupt
            and observation.reading.minimap in {"flat", "tilted"}
            and observation.reading.confidence >= 0.6
        ):
            self.game_since = None
            return True
        # The Pacific Bluffs idle camera keeps the HUD but defeats minimap geometry.
        # Screen="game" alone is a reader default, so require fresh coloured HUD bars.
        hud = read_hud(observation.frame)
        visible = (
            self.phase in {"open", "exit"}
            and hud.screen == "game"
            and sum(value is not None for value in (hud.health, hud.armour, hud.special)) >= 2
        )
        if not visible:
            self.game_since = None
            return False
        if self.game_since is None:
            self.game_since = observation.time
        return True

    def step(self, observation: Observation) -> SkillResult:
        if self.finished is not None:
            return self.finished
        now = observation.time
        if not math.isfinite(now) or (self.last_time is not None and now < self.last_time):
            return self.stop("clock-invalid")
        self.last_time = now
        if self.started is None:
            self.started = now
        if now - self.started >= self.limit:
            return self.stop(f"time-limit: {self.failure or self.phase}; verify the screen before retrying")
        if self.hold is not None:
            # A press goes out when the tick that decided it ends, and a tick that read the map's
            # text first takes longer than a press lasts (0.12 s against 0.10 s in session
            # 20261111-122636). Counted from that tick's beginning the press was over as it began:
            # the console saw one tick of cross and the map stayed shut. So after a slow tick the
            # next one starts the count, unless it comes so late that the press is long over.
            if self.SLOW_TICK < now - self.pressed <= self.LATE:
                self.release_at = now + self.hold
                self.ready_at = self.release_at + self.settle
            self.hold = None
        if now < self.release_at:
            if observation.hud is not None and self.held.buttons != ("circle",):
                allowed = {"game", "pause", "map"} if self.held.buttons == ("options",) else {"pause", "map"}
                if observation.hud.screen not in allowed:
                    return self._fail(f"wrong-screen-during-input: {observation.hud.screen}")
            return SkillResult(self.held)
        if now < self.ready_at:
            return SkillResult()
        try:
            return self._step(observation)
        except Exception as exc:
            # OCR can be unavailable; an observation failure never authorises a forward input.
            return self._fail(f"picture-error: {type(exc).__name__}; inspect the map manually")

    def _step(self, observation):
        now = observation.time
        game = self._game(observation)
        if game and self.game_since is not None and now - self.game_since < 0.15:
            return SkillResult()
        if observation.frame is None or (observation.reading.corrupt and not game):
            # Nothing is decided on such a tick. The minimap reader calls a clean cable picture
            # damaged for a tick or two about once a second; only damage that lasts is a fault.
            if self.blind_since is None:
                self.blind_since = now
            if now - self.blind_since < BLIND_SECONDS:
                return SkillResult()
        else:
            self.blind_since = None
        self.current_frame = observation.frame
        if self.phase == "exit":
            if not game and self.failure is None:
                picture = None if observation.frame is None else self._picture(observation.frame)
                if picture is None or picture.screen not in {"map", "overview"}:
                    self.failure = "wrong-screen-while-exiting"
            if game:
                if self.failure:
                    return self.stop(f"{self.failure}; gameplay observed")
                if self.proved_waypoint:
                    # The game draws the route only in a vehicle, so on foot the map's own
                    # picture of the waypoint is all there is to see.
                    seen = "route on the minimap" if observation.reading.route == "purple" else "no route yet"
                    self.finished = SkillResult(
                        status="done", reason=f"waypoint set; {self.waypoint_proof}; {seen}"
                    )
                    return self.finished
                return self.stop("gameplay returned without a waypoint")
            if self.exits >= self.max_exits:
                return self.stop(
                    f"{self.failure or 'return-unverified'}; gameplay not observed after 3 exits"
                )
            self.exits += 1
            return self._press(Pad(buttons=(self.profile.back,)), now, "exit")
        if self.phase == "open":
            if not game:
                # Nothing has been opened yet, so there is nothing to back out of: circle on a
                # screen this skill has not read quits a failed mission or throws a punch.
                return self.stop("start-screen-unverified; start from visible gameplay")
            return self._press(Pad(buttons=(self.profile.pause,)), now, "enter")
        if observation.frame is None or observation.reading.corrupt:
            return self._fail("map-picture-missing-or-damaged")
        if (
            self.command_frame is not None
            and np.array_equal(observation.frame, self.command_frame)
            and not (self.target == "away" and self.phase == "pan")
        ):
            return self._fail("picture-unchanged-after-input; check the video feed")
        if observation.hud is not None and observation.hud.screen not in {"map", "pause"}:
            return self._fail(f"wrong-screen: {observation.hud.screen}")
        picture = self._picture(observation.frame)
        if picture.screen not in {"map", "overview"}:
            return self._fail(f"map-check-failed: {self.phase}")
        if self.phase == "enter":
            if picture.screen == "overview":
                return self._press(Pad(buttons=(self.profile.confirm,)), now, "acquire")
            self.phase = "acquire"
        if picture.screen != "map" or picture.cursor is None:
            return self._fail("interactive-map-or-cursor-unverified")
        if self.target == "away" and self.phase in {"acquire", "pan"}:
            return self._away(observation, picture)
        if self.phase == "acquire":
            points = picture.missions
            if not points:
                return self._fail(f"no-visible-{self.target}-target; inspect the map manually")
            # The game opens this map centred on the player, beneath the fixed cursor.
            origin = picture.player if picture.player is not None else picture.cursor
            points = sorted(points, key=lambda p: math.dist(p, origin))
            for point in points:
                x, y = map(round, point)
                template = observation.frame[y - 12 : y + 13, x - 12 : x + 13].copy()
                if template.shape == (25, 25, 3) and len(_matches(observation.frame, template, 0.8)) == 1:
                    self.point, self.template = point, template
                    break
            if self.point is None:
                return self._fail("target-not-uniquely-trackable; inspect the map manually")
            self.phase = "aim"
        elif self.phase == "aim":
            candidates = _track(observation.frame, self.template, self.point)
            if len(candidates) != 1:
                return self._fail("target-tracking-unverified; inspect the selected marker")
            moved = math.dist(self.point, candidates[0])
            strength = math.hypot(*self.held.left)
            if moved >= 2 and strength:
                self.aim_gain = moved / (self.push_seconds * strength)
            self.point = candidates[0]
        if self.phase == "confirm":
            if not picture.proof:
                return self._fail("waypoint-not-visible-after-cross")
            if self.command_frame is not None:
                masks = [
                    cv2.inRange(cv2.cvtColor(image, cv2.COLOR_RGB2HSV), (130, 80, 70), (165, 255, 255))
                    for image in (self.command_frame, observation.frame)
                ]
                unchanged = cv2.countNonZero(cv2.absdiff(*masks)[170:565, 230:980]) < 12
                if unchanged and (
                    picture.proof == self.previous_proof or picture.proof == "route on the map"
                ):
                    return self._fail("waypoint-proof-unchanged-after-cross")
            if self.confirm_since is None:
                self.confirm_since = now
            if now - self.confirm_since < 0.15:
                return SkillResult()
            self.proved_waypoint = True
            self.waypoint_proof = picture.proof
            self.phase = "exit"
            return SkillResult()
        distance = math.dist(self.point, picture.cursor)
        if distance <= 9:
            if self.target == "away" and not land_at_cursor(observation.frame):
                return self._fail("sea-at-inland-target; inspect the map manually")
            if picture.waypoint:
                return self._fail("existing-waypoint-at-target; avoid toggling it off")
            self.previous_proof = picture.proof
            return self._press(Pad(buttons=(self.profile.confirm,)), now, "confirm")
        if self.previous_distance is not None and distance >= self.previous_distance - 1:
            return self._fail("cursor-did-not-approach-target; check stick direction and map scale")
        if self.moves >= 16:
            return self._fail("cursor-move-limit")
        self.previous_distance = distance
        self.moves += 1
        # Pan direction and gain are assumptions; the next picture must demonstrate progress.
        dx, dy = self.point[0] - picture.cursor[0], self.point[1] - picture.cursor[1]
        scale = min(0.65, max(0.12, distance / 200)) / distance
        self.push_seconds = 0.1
        if self.aim_gain:
            self.push_seconds = min(
                0.4, max(0.1, min(60, distance * 0.8) / (self.aim_gain * distance * scale))
            )
        if self.target == "away":
            scale *= self.sense
        return self._press(Pad(left=(dx * scale, dy * scale)), now, "aim", self.push_seconds)

    def _away(self, observation, picture):
        frame, now = observation.frame, observation.time
        if self.phase == "acquire":
            if map_shift(frame, frame) is None:
                return self._fail("map-texture-unverified; need a clean detailed map")
        else:
            delta = map_shift(self.command_frame, frame)
            observed_only = False
            if delta is None:
                motion = map_motion(self.command_frame, frame)
                if motion is not None:
                    observed_only = np.linalg.norm(motion) >= 2
                    if not observed_only:
                        delta = (0.0, 0.0)
            if delta is None and not observed_only:
                return self._fail("map-shift-unverified; damaged or ambiguous map pair")
            direction = np.array(self.directions[self.direction])
            progress = 0.0 if delta is None else -float(np.dot(delta, direction))
            across = 0.0 if delta is None else abs(direction[0] * delta[1] - direction[1] * delta[0])
            if not observed_only and np.linalg.norm(delta) < 2:
                if self.alternate_used:
                    return self._fail("map-unmoved-after-alternate; check map edge or video feed")
                self.alternate_used = True
                names = tuple(self.directions)
                self.direction = names[(names.index(self.direction) + 1) % 4]
                self.push_rate = None
            elif (
                not observed_only
                and not self.sense_known
                and progress <= -2
                and across <= max(3, -progress * 0.25)
            ):
                self.sense, self.sense_known = -1, True
                self.displacement += np.array(delta)
            elif not observed_only and (progress < 2 or across > max(3, progress * 0.25)):
                return self._fail("map-shift-wrong-direction; check stick mapping")
            else:
                if observed_only:
                    self.unmeasured = True
                else:
                    self.sense_known = True
                    self.displacement += np.array(delta)
                self.travel_seconds += self.push_seconds
                self.push_rate = None if observed_only else progress / self.push_seconds
                if self.inland_used and (
                    not land_at_cursor(frame)
                    or (not self.unmeasured and np.linalg.norm(self.displacement) < 2)
                ):
                    return self._fail("sea-or-distance-unverified-after-inland-look")
                enough = (
                    self.travel_seconds >= self.travel_goal
                    if self.unmeasured
                    else np.linalg.norm(self.displacement) >= self.distance
                )
                if self.inland_used or enough:
                    if land_at_cursor(frame):
                        if picture.waypoint:
                            return self._fail("existing-waypoint-at-target; avoid toggling it off")
                        self.previous_proof = picture.proof
                        return self._press(Pad(buttons=(self.profile.confirm,)), now, "confirm")
                    self.inland_used = True
                    if self.unmeasured:
                        if self.moves >= 16:
                            return self._fail("map-move-limit")
                        # At Pacific Bluffs reversing one short push can still end at sea.
                        # Aim at a visible, uniquely trackable land patch using the same
                        # checked approach as a mission badge, within the existing move cap.
                        for point in sorted(picture.roads, key=lambda p: math.dist(p, picture.cursor)):
                            if not land_at_cursor(frame, point):
                                continue
                            x, y = map(round, point)
                            template = frame[y - 12 : y + 13, x - 12 : x + 13].copy()
                            if len(_matches(frame, template, 0.8)) != 1:
                                continue
                            self.point, self.template = point, template
                            self.previous_distance = math.dist(point, picture.cursor)
                            vector = (np.array(point) - picture.cursor) / self.previous_distance
                            self.push_seconds = 0.1
                            self.moves += 1
                            return self._press(
                                Pad(left=tuple(vector * 0.65 * self.sense)), now, "aim", self.push_seconds
                            )
                    # One look back toward the land visible before this push, without a coast model.
                    names = tuple(self.directions)
                    self.direction = names[(names.index(self.direction) + 2) % 4]
        if self.moves >= 16:
            return self._fail("map-move-limit")
        self.moves += 1
        remaining = max(30, min(60, self.distance - np.linalg.norm(self.displacement)))
        self.push_seconds = 0.10 if not self.push_rate else min(0.40, max(0.10, remaining / self.push_rate))
        if self.unmeasured:
            self.push_seconds = 0.4
        direction = self.directions[self.direction]
        stick = 0.65 * self.sense
        return self._press(
            Pad(left=(direction[0] * stick, direction[1] * stick)), now, "pan", self.push_seconds
        )
