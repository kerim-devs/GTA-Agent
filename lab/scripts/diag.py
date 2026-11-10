"""Does a held trigger reach the console when nothing else is sent? Three plain pulses, then one with
a tiny stick jitter that forces stick packets alongside."""
import sys, time
import httpx

PHASES = [  # name, seconds, r2, l2, jitter
    ("plain 1", 2.0, 0.6, 0.0, False), ("rest", 1.5, 0.0, 0.0, False),
    ("plain 2", 2.0, 0.6, 0.0, False), ("rest", 1.5, 0.0, 0.0, False),
    ("plain 3", 2.0, 0.6, 0.0, False), ("rest", 1.5, 0.0, 0.0, False),
    ("jitter", 2.0, 0.6, 0.0, True), ("brake", 1.2, 0.0, 1.0, False),
]
with httpx.Client(base_url="http://127.0.0.1:9395", timeout=2.0) as http:
    start = time.monotonic()
    try:
        for name, seconds, r2, l2, jitter in PHASES:
            end = time.monotonic() + seconds
            print(f"{name}: from {time.monotonic() - start:.2f} s", flush=True)
            n = 0
            while time.monotonic() < end:
                n += 1
                x = 0.02 * (n % 2) if jitter else 0.0
                reply = http.post("/pad", json={"left": [x, 0], "r2": r2, "l2": l2})
                if reply.status_code != 200:
                    sys.exit(f"stopped: {reply.json().get('error')}")
                time.sleep(1 / 60)
    finally:
        http.post("/input", json={"op": "release_all"})
print(f"done at {time.monotonic() - start:.2f} s")
