"""reset.py [seconds, default 240]: the way out of a spot the figure does not get out of.

Kerim's rule of 13 November for the nights the pilot practises alone: draw a weapon and shoot, the
police come and end it, and the figure begins again at the hospital, on foot in a town with cars. It
leaves a car first, takes a weapon from the wheel (L1 held, the right stick toward a slot, tried slot
by slot until shots bring a star), fires in bursts while turning, and waits for the game to come back.
Where nobody hears the shots (the tram's cutting, 14 November: thirty slots and no star) his second way
out follows: the other figure. The switch wheel is held open with the pad's down, the right stick picks
Michael on its left or Franklin above, and the game goes on wherever that one is.
Exit code 0 when the figure stood in the game again after a death, an arrest or a switch, 1 otherwise.
"""

import sys
import tempfile
import time
from pathlib import Path

from pilot import hud, minimap
from pilot.bridge import Bridge
from pilot.conductor import minimap_crop
from pilot.contract import Pad

SLOTS = ((1.0, 0.0), (0.7, -0.7), (0.0, -1.0), (-0.7, -0.7), (0.7, 0.7), (0.0, 1.0))
OVER = ("wasted", "busted")
QUIET = 2 * len(SLOTS)  # slots fired through without a star: nobody is there to hear it
# The switch wheel: Michael to the left, Franklin above, Trevor, who lives in the desert, last.
FIGURES = {"left": (-1.0, 0.0), "top": (0.0, -1.0), "right": (1.0, 0.0)}
BLIND = (
    Path(tempfile.gettempdir()) / "gta-reset-blind-slot"
)  # how often the wheel was switched unread


def switch(bridge):
    """Open the switch wheel, pick a figure other than the one who plays, and say which, or None."""
    from pilot.wheel import wheel

    def read():
        frame = bridge.frame()
        return None if frame is None or not 0 <= frame.age <= 0.5 else wheel(frame.rgb)

    def held(pad, seconds, enough):
        until, reading = time.monotonic() + seconds, None
        while time.monotonic() < until:
            if bridge.pad(pad) != 200:
                raise SystemExit(
                    "the bridge refused the pad: a hand is on the controller"
                )
            time.sleep(0.04)
            reading = read()
            if reading is not None and reading.visible and enough(reading):
                return reading
        return None

    reading = held(Pad(buttons=("down",)), 3.0, lambda r: r.highlight in FIGURES)
    if reading is None:
        # The wheel was not read. Blind, as on 14 November at 01:40, when it brought Michael; each
        # time the next slot, since the same one twice in a row leaves the figure where it is.
        try:
            turn = int(BLIND.read_text())
        except (OSError, ValueError):
            turn = 1  # the first blind switch of the night went left
        slot = list(FIGURES)[turn % len(FIGURES)]
        BLIND.write_text(str(turn + 1))
        held(Pad(buttons=("down",), right=FIGURES[slot]), 1.0, lambda r: False)
        held(Pad(right=FIGURES[slot]), 0.3, lambda r: False)
        bridge.pad(Pad())
        return f"{slot} (wheel unread)"
    target = reading and next(
        (
            slot
            for slot in FIGURES
            if slot != reading.highlight and slot not in reading.disabled
        ),
        None,
    )
    seen = target and held(
        Pad(buttons=("down",), right=FIGURES[target]),
        3.0,
        lambda r: r.highlight == target,
    )
    if seen:
        # The stick is held across the release, or the wheel falls back on the figure who plays.
        held(Pad(right=FIGURES[target]), 0.3, lambda r: False)
    bridge.pad(Pad())
    return target if seen else None


def main(limit):
    with Bridge() as bridge:
        status = bridge.status()
        if (
            status.get("human_input")
            or status.get("recording")
            or not status.get("session_up")
        ):
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
                    raise SystemExit(
                        "the bridge refused the pad: a hand is on the controller"
                    )
                time.sleep(0.04)
            bridge.pad(Pad())

        def over():
            now, _ = see()
            return now is not None and now.screen in OVER

        now, reading = see()
        if now is None or now.screen != "game":
            return (
                f"no game picture ({now.screen if now else 'no frame'}): nothing sent",
                1,
            )
        if reading.minimap == "tilted":
            hold(Pad(buttons=("triangle",)), 0.15)
            hold(Pad(), 3.0)
        died, slot, stars, turn = False, 0, False, 1.0
        while time.monotonic() < end and not died and (stars or slot < QUIET):
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
            chosen = switch(bridge)
            if chosen is None:
                return (
                    f"no death within {limit:.0f} s (stars: {stars}, slots: {slot}), no switch",
                    1,
                )
            # The picture stays a game picture while the camera rises and comes down on the other
            # figure, so the wheel's word is the proof and the time is waited out.
            time.sleep(15)
            back, until = None, time.monotonic() + 90
            while time.monotonic() < until:
                now, _ = see()
                if now is not None and now.screen == "game":
                    back = back or time.monotonic()
                    if time.monotonic() - back >= 3:
                        return (
                            f"no death (stars: {stars}, slots: {slot}); switched to the {chosen} figure",
                            0,
                        )
                else:
                    back = None
                time.sleep(0.25)
            return "switched, and the game did not come back in time", 1
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
