"""reset.py [seconds, default 240]: the way out of a spot the figure does not get out of.

Kerim's rule of 13 November for the nights the pilot practises alone: draw a weapon and shoot, the
police come and end it, and the figure begins again at the hospital, on foot in a town with cars. It
leaves a car first, takes a weapon from the wheel (L1 held, the right stick toward a slot, tried slot
by slot until shots bring a star), fires in bursts while turning, and waits for the game to come back.
Exit code 0 when the figure stood in the game again after a death or an arrest, 1 otherwise.
"""

import sys
import time

from pilot import hud, minimap
from pilot.bridge import Bridge
from pilot.conductor import minimap_crop
from pilot.contract import Pad

SLOTS = ((1.0, 0.0), (0.7, -0.7), (0.0, -1.0), (-0.7, -0.7), (0.7, 0.7), (0.0, 1.0))
OVER = ("wasted", "busted")


def main(limit):
    with Bridge() as bridge:
        status = bridge.status()
        if status.get("human_input") or status.get("recording") or not status.get("session_up"):
            return "a hand, a recording or no session: nothing sent", 1
        end = time.monotonic() + limit

        def see():
            frame = bridge.frame()
            if frame is None or not 0 <= frame.age <= 0.5:
                return None, None
            return hud.read(frame.rgb), minimap.read(minimap_crop(frame.rgb))

        def hold(pad, seconds):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                if bridge.pad(pad) != 200:
                    raise SystemExit("the bridge refused the pad: a hand is on the controller")
                time.sleep(0.04)
            bridge.pad(Pad())

        def over():
            now, _ = see()
            return now is not None and now.screen in OVER

        now, reading = see()
        if now is None or now.screen != "game":
            return f"no game picture ({now.screen if now else 'no frame'}): nothing sent", 1
        if reading.minimap == "tilted":
            hold(Pad(buttons=("triangle",)), 0.15)
            hold(Pad(), 3.0)
        died, slot, stars, turn = False, 0, False, 1.0
        while time.monotonic() < end and not died:
            if not stars:
                x, y = SLOTS[slot % len(SLOTS)]
                hold(Pad(buttons=("l1",), right=(x, y)), 0.7)
                hold(Pad(), 0.4)
                slot += 1
            for _ in range(6):
                hold(Pad(l2=1.0, r2=1.0), 0.8)
                hold(Pad(right=(turn * 0.6, 0.0)), 0.3)
                now, _ = see()
                if now is not None and now.screen in OVER:
                    died = True
                    break
                stars = stars or bool(now is not None and now.wanted)
            turn = -turn
        bridge.pad(Pad())
        if not died:
            return f"no death within {limit:.0f} s (stars seen: {stars}, slots tried: {slot})", 1
        back = None
        while time.monotonic() < end + 90:
            now, _ = see()
            if now is not None and now.screen == "game":
                back = back or time.monotonic()
                if time.monotonic() - back >= 2:
                    return f"back in the game after a death (slots tried: {slot})", 0
            else:
                back = None
            time.sleep(0.25)
        return "died, and the game did not come back in time", 1


if __name__ == "__main__":
    words, code = main(float(sys.argv[1]) if len(sys.argv) > 1 else 240.0)
    print(time.strftime("%H:%M:%S"), "reset:", words)
    raise SystemExit(code)
