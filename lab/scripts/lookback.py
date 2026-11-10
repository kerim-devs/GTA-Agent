"""Hold 'look behind' (R3) fifteen times: every hold must flip the view, every release must flip it back."""
import sys, time
import httpx

with httpx.Client(base_url="http://127.0.0.1:9395", timeout=2.0) as http:
    def hold(seconds, state):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            reply = http.post("/pad", json=state)
            if reply.status_code != 200:
                sys.exit(f"stopped: {reply.json().get('error')}")
            time.sleep(1 / 60)
    try:
        hold(0.3, {"right": [0.3, 0]})  # wake the camera
        hold(2.5, {})
        for n in range(15):
            hold(0.7, {"buttons": ["r3"]})
            hold(0.7, {})
    finally:
        http.post("/pad", json={})
print("done")
