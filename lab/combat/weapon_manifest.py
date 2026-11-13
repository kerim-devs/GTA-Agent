from pathlib import Path
import json
import glob
import os

rows = []
for label, action in (("armed", "fire"), ("unarmed", "melee")):
    for path in glob.glob("/Users/kerim/recordings/derived/kerim/*/actions.jsonl"):
        name = os.path.basename(os.path.dirname(path))
        root = f"/Users/kerim/recordings/kerim/{name}"
        if not (os.path.exists(root + "/video.mp4") and os.path.exists(root + "/frames.jsonl")):
            continue
        frames = [json.loads(line) for line in open(root + "/frames.jsonl") if line.strip()]
        for line in open(path):
            action_row = json.loads(line)
            if action_row["action"] != action:
                continue
            index = (action_row["first_frame"] + action_row["last_frame"]) // 2
            if index >= len(frames):
                continue
            meta = frames[index]
            rows.append({
                "label": label, "recording": name, "frame": meta["i"], "t": meta["t"],
                "action_span": {key: action_row[key] for key in ("start", "end", "first_frame", "last_frame")},
            })
            if sum(row["label"] == label for row in rows) >= 40:
                break
        if sum(row["label"] == label for row in rows) >= 40:
            break

json.dump({
    "selection": "midpoint native frame of derived action span; fire proves armed; melee is a candidate unarmed label requiring visual top-right absence confirmation",
    "samples": rows,
}, open(str(Path(__file__).with_name("weapon-samples.json")), "w"), indent=2)
