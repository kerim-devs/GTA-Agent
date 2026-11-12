#!/usr/bin/env python3
"""Offline reaction bench, with an explicitly local delayed HTTP test server."""

from __future__ import annotations

import argparse
import base64
import bisect
import hashlib
import json
import sys
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pilot.approaches import REGISTRY, Config, action_pad, create, stub_answer
from pilot.reaction import (
    Recording,
    append_result,
    board,
    compact,
    human_result,
    implementation_hash,
    load_scenes,
    provenance,
    replay,
)

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "lab/reaction"


def sheets(scenes, destination):
    destination.mkdir(parents=True, exist_ok=True)
    for scene in scenes:
        source = Recording(scene.recording)
        times = [r["t"] for r in source.rows]
        index = bisect.bisect_left(times, scene.onset)
        tiles = []
        try:
            if scene.kind == "calm":
                for timestamp in (scene.begin, scene.onset, scene.stop):
                    row = source.rows[max(0, bisect.bisect_right(times, timestamp) - 1)]
                    source.cap.set(cv2.CAP_PROP_POS_FRAMES, row["i"])
                    ok, frame = source.cap.read()
                    if not ok:
                        raise ValueError(scene.id)
                    tile = cv2.resize(frame, (320, 180))
                    cv2.putText(
                        tile,
                        f"{scene.id} {row['t']:.3f}",
                        (4, 16),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.4,
                        (255, 255, 255),
                        1,
                    )
                    tiles.append(tile)
                cv2.imwrite(
                    str(destination / f"{scene.id}.jpg"), np.hstack(tiles), [cv2.IMWRITE_JPEG_QUALITY, 65]
                )
                continue
            for offset in (-3, -2, -1, 0, 1, 2):
                row = source.rows[max(0, index + offset)]
                source.cap.set(cv2.CAP_PROP_POS_FRAMES, row["i"])
                ok, frame = source.cap.read()
                if not ok:
                    raise ValueError(scene.id)
                # HUD crops stay legible at native resolution; full view gives context.
                tile = cv2.resize(frame, (480, 270))
                cv2.putText(
                    tile,
                    f"{scene.id} {row['t']:.4f} i={row['i']}",
                    (8, 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.44,
                    (255, 255, 255),
                    1,
                )
                map_crop = cv2.resize(frame[510:720, :330], (330, 210))
                stars = frame[:90, 950:1280]
                hud = np.vstack([stars, map_crop])
                tile = np.hstack([cv2.copyMakeBorder(tile, 0, 30, 0, 0, cv2.BORDER_CONSTANT), hud])
                tiles.append(tile)
            sheet = np.vstack([np.hstack(tiles[:3]), np.hstack(tiles[3:])])
            cv2.imwrite(str(destination / f"{scene.id}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 75])
        finally:
            source.close()


def comparisons(scenes, rows):
    for scene in scenes:
        if scene.kind == "calm":
            continue
        trials = [r for r in rows if r["scene"]["id"] == scene.id]
        slots = [
            ("onset", scene.onset),
            ("Kerim before", (scene.human.get("answer_t") or scene.onset) - 0.15),
            ("Kerim after", (scene.human.get("answer_t") or scene.onset) + 0.15),
        ]
        for trial in trials:
            answer = trial["metrics"]["answer"]
            slots.append((trial["approach"] + " " + trial["mode"], answer["t"] if answer else None))
        source = Recording(scene.recording)
        tiles = []
        try:
            times = [r["t"] for r in source.rows]
            for label, timestamp in slots:
                tile = np.zeros((205, 320, 3), dtype=np.uint8)
                if timestamp is not None:
                    index = max(0, bisect.bisect_right(times, timestamp) - 1)
                    source.cap.set(cv2.CAP_PROP_POS_FRAMES, source.rows[index]["i"])
                    ok, frame = source.cap.read()
                    if ok:
                        tile[25:] = cv2.resize(frame, (320, 180))
                caption = label + (f" {timestamp:.3f}" if timestamp is not None else " NO VALID ANSWER")
                cv2.putText(tile, caption, (4, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.31, (255, 255, 255), 1)
                tiles.append(tile)
            while len(tiles) % 3:
                tiles.append(np.zeros_like(tiles[0]))
            cv2.imwrite(
                str(LAB / "sheets" / f"compare-{scene.id}.jpg"),
                np.vstack([np.hstack(tiles[i : i + 3]) for i in range(0, len(tiles), 3)]),
                [cv2.IMWRITE_JPEG_QUALITY, 72],
            )
        finally:
            source.close()


def serve(port, delay, action):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path not in ("/policy", "/v1/chat/completions"):
                self.send_error(404)
                return
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            encoded = (
                data["image_jpeg_base64"]
                if self.path == "/policy"
                else data["messages"][0]["content"][1]["image_url"]["url"].split(",", 1)[1]
            )
            frame = cv2.imdecode(np.frombuffer(base64.b64decode(encoded), dtype=np.uint8), cv2.IMREAD_COLOR)
            frame = cv2.resize(frame, (1280, 720))
            answer = (
                stub_answer(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                if action == "pixels"
                else {"action": action, "why": "fixed delayed test stub"}
            )
            time.sleep(delay)
            if self.path == "/policy":
                response = {
                    "version": 1,
                    "capture": data["capture"],
                    "pad": asdict(action_pad(answer["action"])),
                    "why": answer["why"],
                }
            else:
                response = {"choices": [{"message": {"content": json.dumps(answer)}}]}
            body = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Delayed stub http://127.0.0.1:{server.server_port}; delay={delay}s action={action}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    scene_parser = subs.add_parser("scenes")
    scene_parser.add_argument("--scenes", type=Path, default=LAB / "scenes.json")
    scene_parser.add_argument("--sheets", action="store_true")
    run = subs.add_parser("run")
    run.add_argument("names", nargs="+", choices=list(REGISTRY))
    run.add_argument("--scenes", type=Path, default=LAB / "scenes.json")
    run.add_argument("--repeat", type=int, default=1)
    run.add_argument("--mode", choices=("realtime", "modelled"), default="realtime")
    run.add_argument("--cost-table", type=Path)
    run.add_argument("--endpoint", default="http://127.0.0.1:18762")
    run.add_argument("--model", default="delayed-stub")
    run.add_argument("--codex", action="store_true")
    run.add_argument("--stub-delay", type=float, default=0.25)
    run.add_argument("--ledger", type=Path, default=LAB / "ledger.jsonl")
    board_parser = subs.add_parser("board")
    board_parser.add_argument("--ledger", type=Path, default=LAB / "ledger.jsonl")
    board_parser.add_argument("--comparisons", action="store_true")
    stub = subs.add_parser("stub")
    stub.add_argument("--port", type=int, default=18762)
    stub.add_argument("--delay", type=float, default=0.25)
    stub.add_argument("--action", choices=("pixels", "fight", "neutral", "flee", "cover"), default="pixels")
    args = parser.parse_args()
    if args.command == "stub":
        serve(args.port, args.delay, args.action)
    elif args.command == "scenes":
        scenes = load_scenes(args.scenes)
        if args.sheets:
            sheets(scenes, LAB / "sheets")
        print(
            json.dumps(
                {
                    "scenes": len(scenes),
                    "kinds": {kind: sum(s.kind == kind for s in scenes) for kind in {s.kind for s in scenes}},
                }
            )
        )
    elif args.command == "board":
        rows = [json.loads(line) for line in args.ledger.read_text().splitlines() if line.strip()]
        current = hashlib.sha256((LAB / "scenes.json").read_bytes()).hexdigest()
        rows = [
            row
            for row in rows
            if row.get("scenes_sha256") == current
            and row.get("implementation_sha256") == implementation_hash(ROOT)
        ]
        human = {row["scene"]["id"]: row for row in rows if row["approach"] == "Kerim"}
        rows = list(human.values()) + [row for row in rows if row["approach"] != "Kerim"]
        print(board(rows, LAB))
        if args.comparisons:
            comparisons(load_scenes(LAB / "scenes.json"), rows)
    else:
        if args.repeat < 1:
            parser.error("--repeat must be positive")
        if args.mode == "modelled" and not args.cost_table:
            parser.error("modelled mode requires --cost-table measured from a realtime run")
        if args.mode == "modelled" and args.codex:
            parser.error("Codex inference is realtime only; modelled head uses the delayed pixel stub")
        costs = json.loads(args.cost_table.read_text()) if args.cost_table else {}
        scenes = load_scenes(args.scenes)
        metadata = provenance(ROOT)
        metadata["scenes_sha256"] = hashlib.sha256(args.scenes.read_bytes()).hexdigest()
        for scene in scenes:
            human = human_result(scene)
            human["scene"]["human"]["answer_t"] = (
                human["metrics"]["answer"]["t"] if human["metrics"]["answer"] else None
            )
            append_result(args.ledger, {**metadata, **compact(human)})
        for name in args.names:
            config = Config(
                output=LAB,
                endpoint=args.endpoint,
                model=args.model,
                codex=args.codex,
                modelled_delay=args.stub_delay if args.mode == "modelled" else None,
            )
            for repeat in range(args.repeat):
                for scene in scenes:
                    config.recording = scene.recording
                    approach = create(name, config)
                    result = replay(
                        scene, approach, mode=args.mode, cost_s=costs.get(name, {}).get("compute_s")
                    )
                    append_result(
                        args.ledger,
                        {
                            **metadata,
                            "approach": name,
                            "repeat": repeat,
                            "model": "codex" if args.codex and name == "head" else args.model,
                            "endpoint": args.endpoint if name not in ("reflex", "pilot") else None,
                            "cost_provenance": costs.get(name),
                            **compact(result),
                        },
                    )
                    print(
                        f"{name} {scene.id} {args.mode}: {result['metrics']['reaction_s']} s; false={result['metrics']['false_answers']}",  # noqa: E501
                        flush=True,
                    )


if __name__ == "__main__":
    main()
