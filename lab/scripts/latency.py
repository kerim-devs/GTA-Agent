"""Hold 'look behind' five times for 1.5 s: how long after each press and release does the picture flip?"""
import sys, time
import httpx
with httpx.Client(base_url="http://127.0.0.1:9395", timeout=2.0) as http:
    def hold(seconds, state):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            r = http.post("/pad", json=state)
            if r.status_code != 200:
                sys.exit(f"stopped: {r.text}")
            time.sleep(1 / 60)
    try:
        hold(1.0, {})
        for _ in range(5):
            hold(1.5, {"buttons": ["r3"]})
            hold(1.5, {})
    finally:
        http.post("/pad", json={})
