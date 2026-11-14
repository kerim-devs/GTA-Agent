"""Read morning bypass episodes without decoding or copying the recordings."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path("/Users/kerim/recordings/pilot")


def state(row):
    return (row.get("result") or {}).get("driver_state", "")


def angle(row, name):
    r = row.get("reading") or {}
    if r.get(name) is None or r.get("arrow") is None or r.get("corrupt"):
        return None
    return round((r[name] - r["arrow"] + 180) % 360 - 180, 2)


def endpoint(row):
    r = row.get("reading") or {}
    return dict(
        t=row["t"],
        near=angle(row, "bearing"),
        far=angle(row, "far_bearing"),
        bearing=r.get("bearing"),
        far_bearing=r.get("far_bearing"),
        arrow=r.get("arrow"),
        distance=r.get("gps_distance"),
    )


def measure():
    episodes, sources = [], []
    for file in sorted(ROOT.glob("20261114-*/play.jsonl")):
        if not "20261114-051709" <= file.parent.name <= "20261114-115959":
            continue
        rows = [json.loads(line) for line in file.open()]
        sources.append(
            dict(
                session=file.parent.name,
                ticks=len(rows),
                sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
            )
        )
        i = 0
        while i < len(rows):
            if not state(rows[i]).startswith("bypass-"):
                i += 1
                continue
            start = i
            # Coast does not end an attempt if a bypass resumes within 0.5 s.
            while i + 1 < len(rows):
                if state(rows[i + 1]).startswith("bypass-"):
                    i += 1
                    continue
                j = i + 1
                while j < len(rows) and rows[j]["t"] - rows[i]["t"] <= 0.5 and state(rows[j]) == "coast":
                    j += 1
                if (
                    j < len(rows)
                    and state(rows[j]).startswith("bypass-")
                    and rows[j]["t"] - rows[i]["t"] <= 0.5
                ):
                    i = j
                    continue
                break
            segment = rows[start : i + 1]
            end = rows[min(i + 1, len(rows) - 1)]["t"]
            later = [r for r in rows[i + 1 :] if end <= r["t"] <= end + 5]
            # Follow plus both headings close is a log proxy, not visual lane membership.
            following = [
                r
                for r in later
                if state(r) == "follow"
                and angle(r, "bearing") is not None
                and abs(angle(r, "bearing")) <= 20
                and angle(r, "far_bearing") is not None
                and abs(angle(r, "far_bearing")) <= 20
            ]
            reverse = next((j for j, r in enumerate(segment) if state(r) == "bypass-reverse"), None)
            length = None
            if reverse is not None:
                tail = next((r for r in segment[reverse + 1 :] if state(r) == "bypass-forward"), None)
                if tail:
                    length = tail["t"] - segment[reverse]["t"]
            origin = (
                "detected"
                if any(state(r) == "bypass-wait" for r in segment[: (reverse or 0) + 1])
                else "blind"
                if length is not None and length > 1.3
                else "unknown"
            )
            a, b = endpoint(segment[0]), endpoint(segment[-1])
            dist = [
                r["reading"]["gps_distance"]
                for r in segment
                if (r.get("reading") or {}).get("gps_distance") is not None
            ]
            episodes.append(
                dict(
                    session=file.parent.name,
                    start=a,
                    end=b,
                    until=end,
                    source_inferred=origin,
                    first_reverse_s=length,
                    distance_change=None if len(dist) < 2 else dist[-1] - dist[0],
                    first_distance=None if not dist else dist[0],
                    last_distance=None if not dist else dist[-1],
                    within_5s=bool(following),
                    next_state=state(rows[min(i + 1, len(rows) - 1)]),
                    phases=list(dict.fromkeys(state(r) for r in segment)),
                )
            )
            i += 1
    result = dict(sources=sources, episodes=episodes)
    (HERE / "p110-episodes.json").write_text(json.dumps(result, indent=2) + "\n")
    valid = [e for e in episodes if e["end"]["near"] is not None]
    print(
        json.dumps(
            dict(
                recordings=len(sources),
                episodes=len(episodes),
                valid_endings=len(valid),
                near_over_45=sum(abs(e["end"]["near"]) > 45 for e in valid),
                far_over_45=sum(e["end"]["far"] is not None and abs(e["end"]["far"]) > 45 for e in valid),
                following_within_5s=sum(e["within_5s"] for e in episodes),
            )
        )
    )


if __name__ == "__main__":
    measure()
