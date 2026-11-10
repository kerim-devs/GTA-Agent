"""Step test through /pad: drive off, hold a small steering angle, then a large one, then brake."""
import sys, time
import httpx

PHASES = [  # seconds, left stick x, r2, l2
    (4.0, 0.0, 0.6, 0.0),
    (1.5, -0.3, 0.4, 0.0),
    (1.0, 0.0, 0.4, 0.0),
    (1.0, -0.9, 0.4, 0.0),
    (1.2, 0.0, 0.0, 1.0),
]
with httpx.Client(base_url="http://127.0.0.1:9395", timeout=2.0) as http:
    start = time.monotonic()
    try:
        for n, (seconds, x, r2, l2) in enumerate(PHASES):
            end = time.monotonic() + seconds
            print(f"phase {n}: x={x} r2={r2} l2={l2} from {time.monotonic() - start:.2f} s", flush=True)
            while time.monotonic() < end:
                reply = http.post("/pad", json={"left": [x, 0], "r2": r2, "l2": l2})
                if reply.status_code != 200:
                    sys.exit(f"stopped: {reply.json().get('error')}")
                time.sleep(1 / 60)
    finally:
        http.post("/input", json={"op": "release_all"})
print("done")
