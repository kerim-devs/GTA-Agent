"""An in-process bridge using real recording frames and delayed controller states.

This never imports or connects a live Bridge. Run it from pilot/ to reproduce
the calibration receipt in lab/calibrate/simulation/.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from pilot.bridge import Frame
from pilot.calibrate import TICK, run_calibrate
from pilot.contract import NEUTRAL_PAD

FIXTURES = Path(__file__).resolve().parents[2] / "lab" / "hud" / "fixtures"


def bases():
    names = {
        "game": "wifi-01013",
        "pause": "wifi-08196",
        "map": "wifi-08243",
        "phone": "wifi-03424",
        "weapon_wheel": "wifi-10961",
    }
    result = {}
    for name, file in names.items():
        bgr = cv2.imread(str(FIXTURES / f"{file}.png"))
        if bgr is None:
            raise ValueError(f"missing recorded fixture {file}")
        result[name] = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    wheel = cv2.imread(str(Path(__file__).resolve().parents[1] / "tests/fixtures/calibrate/wheel.png"))
    result["weapon_wheel"] = cv2.cvtColor(wheel, cv2.COLOR_BGR2RGB)
    tilted = result["game"].copy()
    tilted[530:700, 30:290] = result["phone"][530:700, 30:290]
    result["tilted"] = tilted
    return result


class SimConsole:
    def __init__(
        self,
        *,
        delay=0.14,
        deadzone=0.12,
        press_ticks=1,
        map_sign=1,
        door=2.0,
        rate=120.0,
        frozen=False,
        no_pause=False,
        initial="game",
        conflict_at=None,
        surprise_at=None,
        surprise_screen="phone",
        interrupt_at=None,
        stale=None,
        images=None,
    ):
        self.images = images if images is not None else bases()
        self.delay, self.deadzone, self.press_ticks = delay, deadzone, press_ticks
        self.map_sign, self.door, self.rate = map_sign, door, rate
        self.frozen, self.no_pause = frozen, no_pause
        self.conflict_at, self.surprise_at, self.interrupt_at = conflict_at, surprise_at, interrupt_at
        self.surprise_screen = surprise_screen
        self.stale = stale  # (from, until): no frame arrives in between
        self.now = self.updated = 0.0
        self.screen = initial
        self.vehicle = False
        self.input = self.effective = NEUTRAL_PAD
        self.queue = []
        self.calls = []
        self.id = 0
        self.pressed_at = 0.0
        self.triggered = False
        self.door_at = None
        self.camera_x = self.walk_y = self.map_x = self.map_y = 0.0
        self.recording = False
        self.stopped = False
        self._image_key = None
        self._image = None

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(seconds, 1e-9)

    def gain(self, value):
        return np.sign(value) * max(0, (abs(value) - self.deadzone) / (1 - self.deadzone))

    def _advance(self):
        # Small integration steps keep hold thresholds independent of poll rate.
        while self.updated < self.now - 1e-9:
            end = min(self.now, self.updated + 0.005)
            dt = end - self.updated
            self.updated = end
            while self.queue and self.queue[0][0] <= end + 1e-9:
                _, value = self.queue.pop(0)
                if value.buttons != self.effective.buttons:
                    self.pressed_at, self.triggered = end, False
                self.effective = value
            pad = self.effective
            if not self.frozen:
                if self.screen == "game":
                    self.camera_x += self.gain(pad.right[0]) * self.rate * dt
                    self.walk_y += self.gain(-pad.left[1]) * 60 * dt
                elif self.screen == "map":
                    self.map_x += pad.left[0] * self.map_sign * 100 * dt
                    self.map_y += pad.left[1] * self.map_sign * 100 * dt
            if self.screen == "weapon_wheel" and "l1" not in pad.buttons:
                self.screen = "game"
            if (
                pad.buttons
                and not self.triggered
                and end - self.pressed_at >= self.press_ticks * TICK - 0.006
            ):
                self.triggered = True
                if "options" in pad.buttons and self.screen == "game" and not self.no_pause:
                    self.screen = "pause"
                elif "cross" in pad.buttons and self.screen == "pause":
                    self.screen = "map"
                elif "circle" in pad.buttons and self.screen in {"pause", "map", "phone"}:
                    self.screen = "pause" if self.screen == "map" else "game"
                elif "up" in pad.buttons and self.screen == "game":
                    self.screen = "phone"
                elif "l1" in pad.buttons and self.screen == "game":
                    self.screen = "weapon_wheel"
                elif "triangle" in pad.buttons and self.screen == "game":
                    self.door_at = self.pressed_at + self.door
            if self.door_at is not None and end >= self.door_at:
                self.vehicle = not self.vehicle
                self.door_at = None
        if self.surprise_at is not None and self.now >= self.surprise_at:
            self.screen, self.surprise_at = self.surprise_screen, None
        if self.interrupt_at is not None and self.now >= self.interrupt_at:
            self.interrupt_at = None
            raise KeyboardInterrupt("simulated interrupt")

    @staticmethod
    def translate(rgb, x, y):
        return cv2.warpAffine(
            rgb,
            np.float32([[1, 0, x], [0, 1, y]]),
            (rgb.shape[1], rgb.shape[0]),
            borderMode=cv2.BORDER_REFLECT,
        )

    def frame(self, rect=None, after=None):
        self._advance()
        if self.stale is not None and self.stale[0] <= self.now < self.stale[1]:
            return None
        self.id += 1
        key = (
            self.screen,
            self.vehicle,
            round(self.camera_x, 3),
            round(self.walk_y, 3),
            round(self.map_x, 3),
            round(self.map_y, 3),
        )
        if key != self._image_key:
            base = self.images["tilted" if self.screen == "game" and self.vehicle else self.screen]
            if self.screen == "game":
                rgb = self.translate(base, self.camera_x, 0)
                crop = base[530:700, 30:290].copy()
                y, x = np.mgrid[:170, :260]
                moving = (x >= 39) & (x < 209) & (y >= 32) & (y < 138)
                moving &= (x - 123) ** 2 + (y - 117) ** 2 >= 20**2
                moving &= (x - 125) ** 2 + (y - 39) ** 2 >= 14**2
                shifted = self.translate(crop, 0, 0 if self.vehicle else self.walk_y)
                crop[moving] = shifted[moving]
                rgb[530:700, 30:290] = crop
            elif self.screen == "map":
                rgb = base.copy()
                rgb[165:565, 230:980] = self.translate(base, self.map_x, self.map_y)[165:565, 230:980]
                rgb[300:420, 580:700] = base[300:420, 580:700]
            else:
                rgb = base
            self._image_key, self._image = key, rgb
        return Frame(self._image, self.id, 0.0)

    def pad(self, command=None):
        self._advance()
        command = command or NEUTRAL_PAD
        self.calls.append({"t": self.now, "screen": self.screen, "pad": command})
        if self.conflict_at is not None and self.now >= self.conflict_at:
            self.input = NEUTRAL_PAD
            return 409
        if command != self.input:
            self.input = command
            self.queue.append((self.now + self.delay, command))
        return 200

    def record_start(self, directory, shadow=False):
        destination = Path(directory) / "session"
        destination.mkdir(parents=True, exist_ok=True)
        self.recording = True
        return destination

    def record_stop(self):
        self.recording, self.stopped = False, True


class SimDetector:
    """Results complete at 10 Hz while the caller continues at its own rate."""

    def __init__(self):
        self.last = None

    def poll(self, rgb, t):
        stamp = int((t + 1e-7) * 10) / 10
        self.last = (stamp, ())
        return self.last

    def close(self):
        pass


class SimHead:
    def __init__(self, sleep=None):
        self.sleep = sleep

    def decide(self, request):
        if self.sleep is not None:
            self.sleep(0.75)
        return {"description": "A recorded game picture; no inputs requested."}


def simulate(directory, **kwargs):
    sim = SimConsole(**kwargs)
    result = run_calibrate(
        sim,
        car=True,
        yes=True,
        record_dir=directory,
        clock=sim.clock,
        sleep=sim.sleep,
        detector_factory=SimDetector,
        head=SimHead(sim.sleep),
    )
    return sim, result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("../lab/calibrate/simulation"))
    args = parser.parse_args()
    rows = []
    images = bases()
    for index, truth in enumerate(
        (
            {"delay": 0.14, "deadzone": 0.12, "press_ticks": 1, "map_sign": 1, "door": 2.0},
            {"delay": 0.6, "deadzone": 0.25, "press_ticks": 3, "map_sign": -1, "door": 5.0},
        )
    ):
        sim, report = simulate(args.out / str(index), images=images, **truth)
        rows.append(
            {
                "true": truth,
                "checks": [
                    {key: value for key, value in check.items() if key != "raw"} for check in report["checks"]
                ],
                "elapsed_seconds": report["elapsed_seconds"],
            }
        )
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "measured.json").write_text(json.dumps(rows, indent=2) + "\n")
