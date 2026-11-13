"""Reproduce corpus checks, or explicitly measure a configured local model."""

from __future__ import annotations

import argparse
import json
import math
import socket
import statistics
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot" / "src"))

from pilot.chooser import Chooser  # noqa: E402
from pilot.head import HeadRequest, parse_response  # noqa: E402
from pilot.localhead import LocalHead  # noqa: E402


def load():
    folder = Path(__file__).resolve().parent
    entries = json.loads((folder / "situations.json").read_text())
    for entry in entries:
        raw = entry["request"].copy()
        raw["jpeg_path"] = str(folder / entry["frame"])
        entry["head_request"] = HeadRequest(**raw)
    return entries


def checked_candidates(entry):
    options = LocalHead().candidates(entry["head_request"])
    snapshot = []
    for option in options:
        response = option.response
        plan = [{"name": call.name, "args": call.args} for call in response.plan]
        parse_response({"plan": plan, "sentence": response.sentence})
        snapshot.append({"name": option.name, "description": option.description, "plan": plan})
    if snapshot != entry["candidates"]:
        raise ValueError(f"Candidate drift in frame {entry['id']}; review its label before measuring")
    names = {option.name for option in options}
    if not set(entry["right"]) <= names:
        raise ValueError(f"Label names an absent candidate in frame {entry['id']}")
    return options


def local(entries):
    correct = 0
    candidates = 0
    for entry in entries:
        options = checked_candidates(entry)
        candidates += len(options)
        correct += options[0].name in entry["right"]
    frame_bytes = sum(Path(entry["head_request"].jpeg_path).stat().st_size for entry in entries)
    return {
        "situations": len(entries),
        "valid_candidates": candidates,
        "all_candidate_plans_valid": True,
        "first_reasonable": correct,
        "first_reasonable_share": correct / len(entries),
        "frame_bytes": frame_bytes,
        "empty_right_labels": sum(not entry["right"] for entry in entries),
        "threshold": 0.5,
        "threshold_measured_on_real_model": False,
        "model_called": False,
    }


def probe():
    """Exercise only ephemeral loopback peers; never use a configured model."""
    state = {"delay": 0.0, "content": "nonsense"}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            delay, content = state["delay"], state["content"]
            time.sleep(delay)
            data = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}=fake"
    rows = []
    budget = 1.5

    def check(name, client):
        started = time.monotonic()
        answer = client.choose(
            "What should the player do next?",
            {"road": "Walk along the road", "look": "Look around"},
            np.zeros((60, 100, 3), dtype=np.uint8),
            timeout=budget,
        )
        seconds = time.monotonic() - started
        rows.append({"case": name, "timeout": budget, "seconds": seconds, "returned_none": answer is None})
        assert answer is None and seconds <= budget, rows[-1]

    try:
        check("nonsense", Chooser([url]))
        state["content"] = "B"
        check("missing_probability", Chooser([url]))
        state["delay"] = 2.0
        check("hung", Chooser([url]))
        with socket.socket() as held:
            held.bind(("127.0.0.1", 0))
            dead = f"http://127.0.0.1:{held.getsockname()[1]}=fake"
            check("refused", Chooser([dead]))
        check("dead", Chooser([dead]))
        check("unconfigured", Chooser([]))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
    return {"loopback_only": True, "cases": rows}


def wrong_sheets(rows, entries, directory, threshold):
    directory.mkdir(parents=True, exist_ok=True)
    tiles = []
    for row, entry in zip(rows, entries, strict=True):
        accepted = row["name"] if row["probability"] is not None and row["probability"] >= threshold else None
        correct = accepted in entry["right"] if accepted is not None else not entry["right"]
        if correct:
            continue
        img = cv2.imread(entry["head_request"].jpeg_path)
        tile = np.full((310, 448, 3), 255, dtype=np.uint8)
        tile[:252] = cv2.resize(img, (448, 252))
        cv2.putText(
            tile,
            f"{entry['id']:03d} got {accepted} p={row['probability']}",
            (5, 275),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (0, 0, 0),
            1,
        )
        cv2.putText(
            tile, "right: " + ",".join(entry["right"]), (5, 297), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 1
        )
        tiles.append(tile)
    for start in range(0, len(tiles), 9):
        page = tiles[start : start + 9]
        page += [np.full_like(tiles[0], 255)] * (9 - len(page))
        sheet = np.vstack([np.hstack(page[offset : offset + 3]) for offset in range(0, 9, 3)])
        cv2.imwrite(str(directory / f"wrong-{start // 9 + 1:02d}.jpg"), sheet)


def measure(entries, server, timeout, output):
    # Retain all valid, scored answers once; apply each threshold to the same run.
    client = Chooser([server], threshold=0)
    rows = []
    for entry in entries:
        options = checked_candidates(entry)
        request = entry["head_request"]
        started = time.monotonic()
        result = client.choose(
            "What should the player do next?",
            {o.name: o.description for o in options},
            request.jpeg_path,
            timeout=timeout,
            prior={"objective": request.objective, "help": request.help},
        )
        rows.append(
            {
                "id": entry["id"],
                "name": result.name if result else None,
                "probability": result.probabilities[result.name] if result else None,
                "probabilities": result.probabilities if result else {},
                "seconds": time.monotonic() - started,
                "right": entry["right"],
            }
        )
    thresholds = []
    for integer in range(4, 10):
        threshold = integer / 10
        accepted = [row for row in rows if row["probability"] is not None and row["probability"] >= threshold]
        right = sum(row["name"] in row["right"] for row in accepted)
        abstained = [row for row in rows if row not in accepted]
        thresholds.append(
            {
                "threshold": threshold,
                "accepted": len(accepted),
                "right": right,
                "right_share_of_answers": right / len(accepted) if accepted else None,
                "right_share_of_all": right / len(rows),
                "none_rate": len(abstained) / len(rows),
                "correct_abstentions": sum(not row["right"] for row in abstained),
            }
        )
    latency = sorted(row["seconds"] for row in rows)
    result = {
        "server": server,
        "situations": len(rows),
        "thresholds": thresholds,
        "latency_seconds": {
            "median": statistics.median(latency),
            "p95": latency[max(0, math.ceil(len(latency) * 0.95) - 1)],
            "max": max(latency),
        },
        "rows": rows,
    }
    wrong_sheets(rows, entries, output.parent / "wrong-frames", 0.5)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", help="Explicit local URL=MODEL; absent means offline checks only")
    parser.add_argument("--timeout", type=float, default=1.5)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--probe", action="store_true", help="Measure ephemeral loopback failure cases only")
    args = parser.parse_args()
    if args.probe:
        if args.server:
            parser.error("--probe never accepts an external server")
        result = probe()
        output = args.output or Path(__file__).with_name("timeout-results.json")
        output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return
    entries = load()
    if args.server:
        output = args.output or Path(__file__).with_name("model-results.json")
        result = measure(entries, args.server, args.timeout, output)
    else:
        output = args.output or Path(__file__).with_name("local-results.json")
        result = local(entries)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, indent=2))
    if not args.server:
        assert result["situations"] >= 150
        assert result["frame_bytes"] < 6_000_000
        assert result["first_reasonable_share"] >= 0.9


if __name__ == "__main__":
    main()
