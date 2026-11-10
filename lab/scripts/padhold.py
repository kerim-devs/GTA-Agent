import sys, time
import httpx
seconds = float(sys.argv[1])
with httpx.Client(base_url="http://127.0.0.1:9395", timeout=2.0) as http:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        r = http.post("/pad", json={"buttons": ["r3"]})
        if r.status_code != 200:
            sys.exit(f"stopped: {r.text}")
        time.sleep(1 / 60)
    print("last reply", r.json(), "pad now", http.get("/pad").json()["agent"]["buttons"])
    http.post("/pad", json={})
