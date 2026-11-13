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

from pilot.approaches import REGISTRY, THREAT_LETTERS, Config, action_pad, create, stub_answer
from pilot.judge import endpoint as private_endpoint
from pilot.reaction import (
    Recording,
    append_result,
    board,
    compact,
    human_result,
    implementation_hash,
    load_scenes,
    provenance,
    read_rows,
    replay,
)

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "lab/reaction"
# The ways of control that run the conductor with a modelled head, with and without the guard.
HEADS = ("head", "head+guard")


def frame_at(source, row):
    source.cap.set(cv2.CAP_PROP_POS_FRAMES, row["i"])
    ok, frame = source.cap.read()
    if not ok:
        raise ValueError(f"cannot decode frame {row['i']}")
    return frame


def caption(tile, text, scale=0.4):
    cv2.putText(tile, text, (4, 14), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3)
    cv2.putText(tile, text, (4, 14), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 1)
    return tile


def sheets(scenes, destination):
    """One small sheet per scene, kept small because sixty of them share lab/reaction's 5 MB: for a
    threat the HUD of the frame before the onset, the onset and the frame after at native size
    (stars over minimap and health), and the onset frame for context; for a calm scene its start,
    centre and end."""
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
                    tile = cv2.resize(frame_at(source, row), (288, 162), interpolation=cv2.INTER_AREA)
                    tiles.append(caption(tile, f"{scene.id} {row['t']:.3f}", 0.36))
                cv2.imwrite(
                    str(destination / f"{scene.id}.jpg"), np.hstack(tiles), [cv2.IMWRITE_JPEG_QUALITY, 60]
                )
                continue
            for offset in (-1, 0, 1):
                row = source.rows[max(0, index + offset)]
                frame = frame_at(source, row)
                hud = np.vstack([frame[:90, 950:1280], frame[510:720, :330]])
                tiles.append(caption(np.ascontiguousarray(hud), f"{row['t']:.4f} i={row['i']}"))
                if offset == 0:
                    context = cv2.resize(frame, (400, 225), interpolation=cv2.INTER_AREA)
                    context = cv2.copyMakeBorder(context, 0, 75, 0, 0, cv2.BORDER_CONSTANT)
                    context = caption(context, f"{scene.id} onset {scene.onset:.4f}")
            sheet = np.hstack([*tiles, context])
            cv2.imwrite(str(destination / f"{scene.id}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 60])
        finally:
            source.close()


def misses(scenes, before=0.5, after=2.0):
    """What the minimap and HUD readers return on every frame from `before` seconds ahead of the
    onset to `after` seconds past it, as the reflex reads them: the minimap pipeline runs from the
    start of the scene so that its state is the reflex's. Only changes are kept, each with the
    frames it lasted."""
    from pilot.conductor import minimap_crop
    from pilot.hud import read as read_hud
    from pilot.loop import Pipeline

    report = {}
    for scene in scenes:
        source = Recording(scene.recording)
        pipeline = Pipeline()
        runs = []
        try:
            first = bisect.bisect_left([r["t"] for r in source.rows], scene.begin)
            for row in source.rows[first:]:
                if row["t"] > scene.onset + after:
                    break
                frame, capture = source.at(row["t"])
                reading, _, _ = pipeline.step(minimap_crop(frame), capture, feedback=False)
                if capture < scene.onset - before:
                    continue
                hud = read_hud(frame)
                state = {
                    "map": reading.minimap,
                    "damaged": reading.corrupt,
                    "blips": sorted(
                        f"{b.color}{'-border' if b.border else ''}@{b.x:.0f},{b.y:.0f}" for b in reading.blips
                    ),
                    "health": None if hud.health is None else round(hud.health, 2),
                    "stars": hud.wanted,
                    "screen": hud.screen,
                }
                # Blip positions move every frame; a run is one set of colours and borders.
                key = json.dumps({**state, "blips": sorted(b.split("@")[0] for b in state["blips"])})
                if runs and runs[-1]["key"] == key:
                    runs[-1]["frames"] += 1
                    runs[-1]["until"] = round(capture - scene.onset, 4)
                else:
                    runs.append(
                        {
                            "key": key,
                            "from": round(capture - scene.onset, 4),
                            "until": round(capture - scene.onset, 4),
                            "frames": 1,
                            **state,
                        }
                    )
        finally:
            source.close()
            pipeline.close()
        report[scene.id] = [{k: v for k, v in run.items() if k != "key"} for run in runs]
    return report


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


def chat_image(data: dict) -> str:
    for message in data["messages"]:
        for part in message["content"] if isinstance(message["content"], list) else ():
            if part.get("type") == "image_url":
                return part["image_url"]["url"].split(",", 1)[1]
    raise ValueError("no image in the request")


def letter_reply(action: str) -> dict:
    """A reply as LM Studio gives one to judge.post: the letter, with its log-probability."""
    letter = next(key for key, value in THREAT_LETTERS.items() if value == action)
    token = {"token": letter, "logprob": 0.0, "top_logprobs": [{"token": letter, "logprob": 0.0}]}
    return {"choices": [{"message": {"content": letter}, "logprobs": {"content": [token]}}]}


def serve(port, delay, action):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path not in ("/policy", "/v1/chat/completions"):
                self.send_error(404)
                return
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            encoded = data["image_jpeg_base64"] if self.path == "/policy" else chat_image(data)
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
            elif data["messages"][0]["role"] == "system":
                # The letter question goes out through judge.post, with the judge's system prompt.
                response = letter_reply(answer["action"])
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
    run.add_argument("--question", choices=("json", "letter"), default="json")
    run.add_argument(
        "--head-delay", type=float, help="modelled head: the readers' answer held back this many seconds"
    )
    run.add_argument("--head-delay-source", default="", help="where the modelled head delay comes from")
    run.add_argument("--only", nargs="+", help="scene ids to run, default all")
    run.add_argument("--ledger", type=Path, default=LAB / "ledger.jsonl")
    board_parser = subs.add_parser("board")
    board_parser.add_argument(
        "--ledger", type=Path, default=LAB / "ledger.jsonl", help="a ledger, or an archived one (.jsonl.gz)"
    )
    board_parser.add_argument(
        "--scenes",
        type=Path,
        default=LAB / "scenes.json",
        help="the scene file whose rows to show; another than scenes.json gets board-<name>.md beside it",
    )
    board_parser.add_argument("--comparisons", action="store_true")
    board_parser.add_argument(
        "--implementation",
        help="implementation SHA-256 whose rows to show, default the current code; the board names it",
    )
    miss = subs.add_parser("misses", help="what the readers return around each onset, changes only")
    miss.add_argument("--scenes", type=Path, default=LAB / "scenes.json")
    miss.add_argument("--only", nargs="+", help="scene ids, default every threat scene")
    miss.add_argument("--out", type=Path, default=LAB / "misses.json")
    stub = subs.add_parser("stub")
    stub.add_argument("--port", type=int, default=18762)
    stub.add_argument("--delay", type=float, default=0.25)
    stub.add_argument("--action", choices=("pixels", "fight", "neutral", "flee", "cover"), default="pixels")
    args = parser.parse_args()
    if args.command == "stub":
        serve(args.port, args.delay, args.action)
    elif args.command == "misses":
        chosen = [
            scene
            for scene in load_scenes(args.scenes)
            if scene.kind != "calm" and (not args.only or scene.id in args.only)
        ]
        found = json.loads(args.out.read_text()) if args.out.exists() else {}
        found.update(misses(chosen))
        args.out.write_text(json.dumps(found, indent=1) + "\n")
        print(json.dumps({scene.id: len(found[scene.id]) for scene in chosen}))
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
        rows = read_rows(args.ledger)
        current = hashlib.sha256(args.scenes.read_bytes()).hexdigest()
        main_scenes = args.scenes.resolve() == (LAB / "scenes.json").resolve()
        measured = args.implementation or implementation_hash(ROOT)
        rows = [
            row
            for row in rows
            if row.get("scenes_sha256") == current and row.get("implementation_sha256") == measured
        ]
        human = {row["scene"]["id"]: row for row in rows if row["approach"] == "Kerim"}
        rows = list(human.values()) + [row for row in rows if row["approach"] != "Kerim"]
        print(
            board(
                rows,
                LAB,
                provenance_line=f"Rows of implementation SHA-256 {measured}, scenes SHA-256 {current}.",
                stem="board" if main_scenes else "board-" + args.scenes.stem.removeprefix("scenes-"),
            )
        )
        if args.comparisons:
            comparisons(load_scenes(args.scenes), rows)
    else:
        if args.repeat < 1:
            parser.error("--repeat must be positive")
        if args.mode == "modelled" and not args.cost_table:
            parser.error("modelled mode requires --cost-table measured from a realtime run")
        if args.mode == "modelled" and args.codex:
            parser.error("Codex inference is realtime only; modelled head uses the delayed pixel stub")
        if args.head_delay is not None and (
            args.codex or args.mode != "realtime" or not args.head_delay_source
        ):
            parser.error("--head-delay is a realtime run without Codex and needs --head-delay-source")
        if set(args.names) & {"judge", "judge-second", "reflex+judge", "policy"} or (
            set(args.names) & set(HEADS) and args.head_delay is None and not args.codex
        ):
            # Answers go to a model server on this machine or the local network, never further.
            private_endpoint(f"{args.endpoint}={args.model}")
        costs = json.loads(args.cost_table.read_text()) if args.cost_table else {}
        scenes = load_scenes(args.scenes)
        if args.only:
            unknown = set(args.only) - {scene.id for scene in scenes}
            if unknown:
                parser.error(f"unknown scenes: {sorted(unknown)}")
            scenes = [scene for scene in scenes if scene.id in args.only]
        metadata = provenance(ROOT)
        metadata["scenes_sha256"] = hashlib.sha256(args.scenes.read_bytes()).hexdigest()
        # Kerim's row of a scene is the same on every run of one scene file and implementation.
        known = set()
        if args.ledger.exists():
            for line in args.ledger.read_text().splitlines():
                row = json.loads(line) if '"approach":"Kerim"' in line else None
                if row and row.get("scenes_sha256") == metadata["scenes_sha256"]:
                    if row.get("implementation_sha256") == metadata["implementation_sha256"]:
                        known.add(row["scene"]["id"])
        for scene in scenes:
            if scene.id in known:
                continue
            human = human_result(scene)
            human["scene"]["human"]["answer_t"] = (
                human["metrics"]["answer"]["t"] if human["metrics"]["answer"] else None
            )
            loose = human["metrics"]["loose_answer"]
            human["scene"]["human"]["loose_t"] = loose["t"] if loose else None
            append_result(args.ledger, {**metadata, **compact(human)})
        for name in args.names:
            config = Config(
                output=LAB,
                endpoint=args.endpoint,
                model=args.model,
                codex=args.codex,
                modelled_delay=args.stub_delay if args.mode == "modelled" else None,
                question=args.question,
                head_delay=args.head_delay if name in HEADS else None,
            )
            asks_model = name in ("judge", "judge-second", "reflex+judge") or (
                name in HEADS and config.head_delay is None and not args.codex
            )
            modelled_head = name in HEADS and config.head_delay is not None
            for repeat in range(args.repeat):
                for scene in scenes:
                    config.recording = scene.recording
                    approach = create(name, config)
                    result = replay(
                        scene, approach, mode=args.mode, cost_s=costs.get(name, {}).get("compute_s")
                    )
                    if modelled_head:
                        # Everything else runs on the wall clock; the head's answer time is modelled.
                        result["mode"] = "realtime, head delay modelled"
                    append_result(
                        args.ledger,
                        {
                            **metadata,
                            "approach": name,
                            "repeat": repeat,
                            "model": "codex"
                            if args.codex and name in HEADS
                            else "codex-delay-modelled"
                            if modelled_head
                            else args.model,
                            "question": args.question if asks_model else None,
                            "head_delay_s": config.head_delay if modelled_head else None,
                            "head_delay_source": args.head_delay_source if modelled_head else None,
                            "endpoint": args.endpoint
                            if name not in ("reflex", "pilot", "pilot+guard") and not modelled_head
                            else None,
                            "cost_provenance": costs.get(name),
                            **compact(result),
                        },
                    )
                    metrics = result["metrics"]
                    print(
                        f"{name} {scene.id} {result['mode']}: noticed {metrics['noticed_s']} s, answered {metrics['reaction_s']} s; false={metrics['false_answers']}; errors={len(result['errors'])}",  # noqa: E501
                        flush=True,
                    )


if __name__ == "__main__":
    main()
