"""Six throttle pulses with a brake and a rest after each: does every pulse reach the console?"""
import sys, time
import httpx

PHASES = [("wake", 0.3, {"right": [0.3, 0]}), ("settle", 2.5, {})]
for n in range(1, 7):
    PHASES += [(f"gas {n}", 1.2, {"r2": 0.7}), (f"brake {n}", 0.5, {"l2": 1.0}), (f"rest {n}", 1.0, {})]
with httpx.Client(base_url="http://127.0.0.1:9395", timeout=2.0) as http:
    start = time.monotonic()
    try:
        for name, seconds, state in PHASES:
            end = time.monotonic() + seconds
            print(f"{name} {time.monotonic() - start:.2f}", flush=True)
            while time.monotonic() < end:
                reply = http.post("/pad", json=state)
                if reply.status_code != 200:
                    sys.exit(f"stopped: {reply.json().get('error')}")
                time.sleep(1 / 60)
    finally:
        http.post("/input", json={"op": "release_all"})
print(f"end {time.monotonic() - start:.2f}")
