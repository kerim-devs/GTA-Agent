"""What the controller at this computer reports for a few seconds, raw, before the bridge's rest zone."""
import statistics as st
import sys
import time
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import sdl2

seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, b"1")
assert sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER) == 0, sdl2.SDL_GetError()
pad = None
for index in range(sdl2.SDL_NumJoysticks()):
    if sdl2.SDL_IsGameController(index):
        pad = sdl2.SDL_GameControllerOpen(index)
        break
assert pad, "no controller"
print((sdl2.SDL_GameControllerName(pad) or b"?").decode())
names = ("LEFTX", "LEFTY", "RIGHTX", "RIGHTY", "TRIGGERLEFT", "TRIGGERRIGHT")
axes = {n: getattr(sdl2, f"SDL_CONTROLLER_AXIS_{n}") for n in names}
seen = {n: [] for n in names}
end = time.monotonic() + seconds
time.sleep(0.3)
while time.monotonic() < end:
    sdl2.SDL_PumpEvents()
    for n, a in axes.items():
        seen[n].append(sdl2.SDL_GameControllerGetAxis(pad, a) / 32767.0)
    time.sleep(0.01)
for n, v in seen.items():
    print(f"{n:13s} min {min(v):+.3f}  median {st.median(v):+.3f}  max {max(v):+.3f}  n {len(v)}")
sdl2.SDL_GameControllerClose(pad)
sdl2.SDL_Quit()
