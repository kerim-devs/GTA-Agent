"""p108_idle_stick.py <run>...: every onset of turn-join, and the six seconds of following before it:
seconds the stick stood within 0.1 of the middle while the route's near bearing was 30 degrees and more to a side,
the speed read at the first full stick, and how long before the onset that was."""
import json, sys
tot=0; late=0
for run in sys.argv[1:]:
    rows=[]
    for l in open(run+"/play.jsonl"):
        try: r=json.loads(l)
        except Exception: continue
        res=r.get("result") or {}
        if "driver_state" not in res: continue
        rd=r.get("reading") or {}; pad=r.get("sent_pad") or {}
        b,a=rd.get("bearing"),rd.get("arrow")
        e=None if b is None or a is None else (b-a+180)%360-180
        rows.append((r["t"],res.get("driver_state"),e,(pad.get("left") or [0])[0],rd.get("gps_speed"),res.get("aim_px"),res.get("speed_reason")))
    for i in range(1,len(rows)):
        if rows[i][1]=="turn-join" and rows[i-1][1]!="turn-join":
            t=rows[i][0]; w=[r for r in rows[:i] if t-r[0]<=6 and r[1] in("follow","coast")]
            if len(w)<20: continue
            idle=0.0; first=None
            for p,q in zip(w,w[1:]):
                if p[2] is not None and abs(p[2])>=30 and abs(p[3])<0.1 and p[1]=="follow": idle+=min(q[0]-p[0],0.2)
                if first is None and abs(p[3])>=0.9 and p[2] is not None and abs(p[2])>=30: first=p
            vs=[r[4] for r in w if r[4] is not None]
            tot+=1; late+= idle>=1.0
            print(f"{run[-6:]} {t:6.1f}s stick idle {idle:4.1f}s of the route to a side; full stick {('%.1f s before at %.1f m/s'%(t-first[0],first[4] or -1)) if first else 'never'}; speed {min(vs) if vs else -1:.1f}-{max(vs) if vs else -1:.1f}; reasons {sorted({r[6] for r in w if r[6]})}")
print("turn-join onsets after following:",tot,"with the stick idle a second and more:",late)
