"""replay_drive.py <session> [NAME=VALUE...] : run the driver again over a session's readings; states, limits, pedals."""
import json, sys, collections
from pilot.contract import Reading
from pilot.drive import Driver, DriveConfig
from pilot.cli import LIVE, MEASURED_DELAY_S
d = sys.argv[1]
over = {k: float(v) for k, v in (a.split("=") for a in sys.argv[2:])}
cfg = DriveConfig(**{"command_delay": MEASURED_DELAY_S, **LIVE, **over})
rows = [json.loads(l) for l in open(d + "/play.jsonl")]
rows = [r for r in rows if r["skill"] and r["skill"]["name"] == "drive_route"]
driver = Driver(cfg); limits = []
orig = driver._speed_limit
def spy(path, bend, speed):
    v = orig(path, bend, speed); limits.append((bend, v, speed)); return v
driver._speed_limit = spy
states = collections.Counter(); thr = collections.Counter(); why = collections.Counter()
last_t = None
for r in rows:
    if last_t is not None and r["t"] - last_t > 2: driver = Driver(cfg); driver._speed_limit = spy; orig = Driver(cfg)._speed_limit
    last_t = r["t"]
    rd = dict(r["reading"]); rd["path"] = tuple(tuple(p) for p in rd["path"]); rd["blips"] = ()
    n = len(limits)
    c = driver.step(Reading(**rd), r["t"], None, speed=rd["gps_speed"])
    states[c.state] += 1; thr[round(c.throttle, 1)] += 1
    if c.state == "follow" and len(limits) > n:
        bend, lim, sp = limits[-1]
        why["bend<10" if bend < 10 else "bend<25" if bend < 25 else "bend>=25"] += 1
        if sp is not None and c.throttle == 0: why["over-limit"] += 1
n = len(rows)
print("ticks", n, "states", {k: round(v / n, 2) for k, v in states.most_common()})
print("throttle", sorted((k, round(v / n, 2)) for k, v in thr.items()))
print("why", dict(why))
ls = sorted(l for _, l, _ in limits); print("limit p10 p50 p90", [round(ls[int(len(ls) * q)], 1) for q in (0.1, 0.5, 0.9)])
