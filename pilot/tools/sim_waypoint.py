"""Offline map model: fixed crosshair, panning roads, delayed pictures and wrong pages."""

import argparse
import json
from collections import deque
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from pilot.contract import NEUTRAL_PAD, Hud, Reading
from pilot.scene import SceneText, TextLine
from pilot.skills import Observation
from pilot.waypoint import SetWaypoint, land_at_cursor, map_shift, read_map

WRONG_SCREENS = (
    "settings",
    "online",
    "store",
    "pause",
    "weapon_wheel",
    "phone",
    "failed",
    "passed",
    "wasted",
    "busted",
    "loading",
)
PHASES = ("open", "enter", "acquire", "aim", "confirm", "exit")


def map_text(screen):
    if screen == "overview":
        return SceneText((TextLine("KARTE STATISTIKEN", 1, (250, 130, 400, 14), "other"),))
    if screen == "map":
        return SceneText(
            (
                TextLine("Zoomen Markierung wählen Wegpunkt", 1, (555, 666, 650, 14), "other"),
                TextLine("Spieler", 1, (1146, 44, 46, 12), "other"),
                TextLine("Simeon S", 1, (1144, 338, 66, 17), "other"),
            )
        )
    return SceneText()


class MapWorld:
    def __init__(self, gain=None, edge=False, sea=False, markers=True, zoom="original", coast=False):
        if gain is None:
            # Complete November 11 push groups move about 107 px/s at .65 stick.
            gain = 165 if zoom == "live" else 1200
        self.gain, self.edge, self.sea = gain, edge, sea
        self.screen = "game"
        self.offset = np.zeros(2)
        self.waypoint = False
        self.previous_buttons = ()
        self.route = False
        self.base = np.full((720, 1280, 3), 45, np.uint8)
        self.zoom = zoom
        # Uneven road junctions make the target observable after panning.
        for points in (
            [(290, 225), (390, 310), (560, 260), (740, 430), (920, 495)],
            [(300, 500), (410, 400), (570, 430), (680, 340), (900, 210)],
            [(360, 190), (420, 270), (450, 410), (520, 510)],
            [(850, 200), (800, 270), (770, 420), (870, 510)],
        ):
            cv2.polylines(self.base, [np.array(points)], False, (220, 220, 220), 3)
        if markers:
            self._arrow(self.base, (610, 470))
            self._letter(self.base, (760, 280))
        if not markers:
            # Street blocks across a wider area keep away independent of marker templates.
            rng = np.random.default_rng(19)
            for _ in range(300):
                x, y = rng.integers([40, 40], [1240, 680])
                cv2.rectangle(self.base, (int(x), int(y)), (int(x + 12), int(y + 8)), (160, 160, 160), 1)

        if zoom == "live":
            self.base[:] = 45
            # Approximate the fine grid at the recorded 1007 m opening scale,
            # with irregular junctions alongside the repeated street pattern.
            for x in range(20, 1280, 19):
                cv2.line(self.base, (x, 0), (x + 70, 719), (220, 220, 220), 1)
            for y in range(15, 720, 23):
                cv2.line(self.base, (0, y), (1279, y + 35), (220, 220, 220), 1)
            cv2.ellipse(self.base, (810, 280), (160, 130), 25, 0, 360, (220, 220, 220), 3)
            if markers:
                fixture = Path(__file__).parents[1] / "tests/fixtures/waypoint/live/124637-2.605.png"
                source = cv2.cvtColor(cv2.imread(str(fixture)), cv2.COLOR_BGR2RGB)
                self.base[195:220, 738:763] = source[195:220, 738:763]
        if coast:
            # Model the Pacific Bluffs land/sea boundary, not the captured road layout.
            self.base[:345, :730] = 80

    @staticmethod
    def _arrow(frame, centre):
        x, y = centre
        cv2.fillPoly(
            frame, [np.array([(x, y - 7), (x - 6, y + 6), (x, y + 3), (x + 6, y + 6)])], (245, 245, 245)
        )

    @staticmethod
    def _letter(frame, centre):
        x, y = centre
        cv2.putText(frame, "S", (x - 6, y + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 235, 190), 2)

    def act(self, pad, dt):
        pressed = set(pad.buttons) - set(self.previous_buttons)
        self.previous_buttons = pad.buttons
        if "options" in pressed and self.screen == "game":
            self.screen = "overview"
        if "cross" in pressed:
            if self.screen == "overview":
                self.screen = "map"
            elif self.screen == "map":
                self.waypoint = not self.waypoint
                self.route = self.waypoint
            else:
                raise AssertionError("cross outside map")
        if "circle" in pressed:
            self.screen = {"map": "overview", "overview": "game"}.get(self.screen, "game")
        if self.screen == "map" and not self.edge:
            self.offset -= np.array(pad.left) * self.gain * dt

    def frame(self):
        frame = np.zeros_like(self.base)
        if self.screen == "game":
            frame[:] = (20, 40, 20)
        elif self.screen not in {"map", "overview"}:
            frame[:] = (40, 20, 20)
        if self.screen == "overview":
            frame[123:145, 215:345] = 240
        if self.screen == "map":
            frame = cv2.warpAffine(
                self.base,
                np.float32([[1, 0, self.offset[0]], [0, 1, self.offset[1]]]),
                (1280, 720),
                borderValue=(45, 45, 45),
            )
            if self.sea:
                frame[300:420, 580:700] = 80
            frame[:, 1000:] = 45
            self._arrow(frame, (1204, 50))
            self._letter(frame, (1204, 346))
            cv2.line(frame, (640, 305), (640, 415), (220, 220, 220), 1)
            cv2.line(frame, (585, 360), (695, 360), (220, 220, 220), 1)
            if self.waypoint:
                cv2.polylines(
                    frame, [np.array([(645, 365), (655, 385), (720, 410)])], False, (180, 30, 230), 4
                )
            if self.zoom == "live":
                cv2.line(frame, (64, 605), (204, 605), (220, 220, 220), 1)
                cv2.putText(frame, "1007m", (162, 623), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (220, 220, 220), 1)
        return frame


def simulate(
    target="mission",
    delay=0.14,
    wrong_at=None,
    wrong_screen="settings",
    duration=45,
    exit_works=True,
    gain=None,
    edge=False,
    sea=False,
    damaged=False,
    direction="east",
    distance="near",
    zoom="original",
    coast=False,
    cinematic=False,
):
    world = MapWorld(gain=gain, edge=edge, sea=sea, markers=target == "mission", zoom=zoom, coast=coast)
    skill = SetWaypoint(
        {"target": target, "duration": duration, "direction": direction, "distance": distance}
    )
    text = SceneText()
    skill._picture = lambda frame: read_map(frame, text)
    pending = deque()
    trace = []
    injected = False
    failure_seen = False
    dt = 0.05
    for tick in range(1000):
        now = round(tick * dt, 6)
        if wrong_at == skill.phase and now >= skill.ready_at and not injected:
            world.screen = wrong_screen
            injected = True
            # The injected picture is already visible at this observation boundary.
            pending.clear()
        pending.append((now, world.frame(), world.screen, world.route))
        while len(pending) > 1 and pending[1][0] <= now - delay:
            pending.popleft()
        _, frame, screen, route = pending[0]
        corrupt = damaged and skill.phase == "pan" and now >= skill.ready_at and not injected
        if corrupt:
            injected = True
            frame = frame.copy()
            frame[180:540, 250:950] = (0, 255, 80)
        text = map_text(screen)
        reading = Reading(
            "tilted" if screen == "game" else "none",
            "purple" if route and screen == "game" else "none",
            None,
            None,
            None,
            corrupt,
            1.0,
        )
        observation = Observation(
            reading,
            False,
            now,
            frame,
            hud=Hud(screen="pause" if screen in {"overview", "settings"} else screen),
        )
        if cinematic and screen == "game":
            from pilot.contract import HUD_RECT
            from pilot.hud import read as read_hud
            from pilot.minimap import read as read_minimap

            fixture = Path(__file__).parents[1] / "tests/fixtures/waypoint/live/133505-42111.png"
            frame = cv2.cvtColor(cv2.imread(str(fixture)), cv2.COLOR_BGR2RGB)
            x, y, w, h = HUD_RECT
            observation = Observation(
                read_minimap(frame[y : y + h, x : x + w]), False, now, frame, hud=read_hud(frame)
            )
        result = skill.step(observation)
        trace.append(
            {
                "t": now,
                "phase": skill.phase,
                "screen": screen,
                "pad": asdict(result.pad),
                "status": result.status,
                "reason": result.reason,
                "displacement": skill.displacement.tolist(),
                "moves": skill.moves,
                "corrupt": corrupt,
                "unmeasured": skill.unmeasured,
                "travel_seconds": skill.travel_seconds,
            }
        )
        if target == "away" and "cross" in result.pad.buttons and screen == "map":
            assert not corrupt and land_at_cursor(frame), "cross on damaged picture or sea"
            assert skill.inland_used or (
                skill.travel_seconds >= skill.travel_goal
                if skill.unmeasured
                else np.linalg.norm(skill.displacement) >= skill.distance
            )
        assert not set(result.pad.buttons) & {"l1", "r1", "ps", "create"}
        if failure_seen:
            assert set(result.pad.buttons) <= {"circle"} and result.pad.left == (0, 0)
        failure_seen |= skill.failure is not None
        if result.status != "running":
            assert result.pad == NEUTRAL_PAD
            return {
                "target": target,
                "zoom": zoom,
                "gain": world.gain,
                "coast": coast,
                "cinematic": cinematic,
                "edge": edge,
                "sea": sea,
                "damaged": damaged,
                "direction": direction,
                "distance": distance,
                "delay": delay,
                "wrong_at": wrong_at,
                "wrong_screen": wrong_screen,
                "injected": injected,
                "status": result.status,
                "reason": result.reason,
                "seconds": now,
                "exits": skill.exits,
                "trace": trace,
            }
        if exit_works or "circle" not in result.pad.buttons:
            world.act(result.pad, dt)
    raise AssertionError("unbounded skill")


def simulate_coast(delay=0.14, distance="near"):
    # Reproduce the real road tracker's abstention separately from the modeled coast.
    with patch("pilot.waypoint.map_shift", lambda a, b: map_shift(a, b) if np.array_equal(a, b) else None):
        result = simulate(
            target="away",
            zoom="live",
            coast=True,
            cinematic=True,
            direction="north",
            delay=delay,
            distance=distance,
        )
    result["shift_refused"] = True
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("../lab/waypoint/simulation.json"))
    args = parser.parse_args()
    results = [simulate(target, delay) for target in ("mission", "away") for delay in (0.14, 0.6, 1.1)]
    results += [simulate(wrong_at=phase, wrong_screen=screen) for phase in PHASES for screen in WRONG_SCREENS]
    results += [simulate(wrong_at=phase, exit_works=False) for phase in PHASES]
    results += [
        simulate(target="away", gain=gain, delay=delay, distance=distance)
        for gain in (65, 130, 260)
        for delay in (0.14, 0.6, 1.1)
        for distance in ("near", "far")
    ]
    results += [
        simulate(target="away", delay=delay, **case)
        for delay in (0.14, 0.6, 1.1)
        for case in ({"edge": True}, {"sea": True}, {"damaged": True})
    ]
    results += [
        simulate(target="away", wrong_at=phase, wrong_screen=screen)
        for phase in ("open", "enter", "acquire", "pan", "confirm", "exit")
        for screen in WRONG_SCREENS
    ]
    results += [
        simulate(target=target, zoom="live", delay=delay, distance=distance)
        for target in ("mission", "away")
        for delay in (0.14, 0.6, 1.1)
        for distance in ("near", "far")
    ]
    results += [
        simulate_coast(delay=delay, distance=distance)
        for delay in (0.14, 0.6, 1.1)
        for distance in ("near", "far")
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + "\n")
    for result in results:
        print(json.dumps({key: value for key, value in result.items() if key != "trace"}))
    assert all(
        r["status"] == ("failed" if r["wrong_at"] or r["edge"] or r["sea"] else "done") for r in results
    )
    assert all(r["injected"] for r in results if r["wrong_at"])
