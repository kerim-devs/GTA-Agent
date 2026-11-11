"""level.py <pre> <pulses> <shot>: optional pre-tilt ("down", "up", "none"), then the levelling move
(up to the limit, then <pulses> short pulses down), then save a picture."""
import sys, time
import cv2
from pilot.bridge import Bridge
from pilot.contract import Pad

pre, pulses, shot = sys.argv[1], int(sys.argv[2]), sys.argv[3]


def hold(bridge, pad, seconds):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if bridge.pad(pad) == 409:
            bridge.pad(Pad())
            sys.exit("person on the controller")
        time.sleep(1 / 30)


with Bridge() as bridge:
    if bridge.status()["human_input"]:
        sys.exit("person on the controller")
    if pre == "down":
        hold(bridge, Pad(right=(0.0, 1.0)), 2.0)
    elif pre == "up":
        hold(bridge, Pad(right=(0.0, -1.0)), 1.0)
    hold(bridge, Pad(), 0.7)
    began = time.monotonic()
    hold(bridge, Pad(right=(0.0, -1.0)), 2.0)
    hold(bridge, Pad(), 0.5)
    for _ in range(pulses):
        hold(bridge, Pad(right=(0.0, 0.5)), 0.3)
        hold(bridge, Pad(), 0.5)
    took = time.monotonic() - began
    bridge.pad(Pad())
    time.sleep(0.4)
    frame = bridge.frame()
    cv2.imwrite(shot, cv2.cvtColor(cv2.resize(frame.rgb, (640, 360)), cv2.COLOR_RGB2BGR))
print("levelled in", round(took, 1), "s")
