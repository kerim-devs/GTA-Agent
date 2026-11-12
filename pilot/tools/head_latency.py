"""Send a saved session's independent requests to a real head and print timings."""

import argparse
import json
import time
from dataclasses import fields
from pathlib import Path

from pilot.head import CodexHead, CodexServerHead, HeadRequest, response_data


def saved_requests(session):
    keys = {field.name for field in fields(HeadRequest)}
    with (session / "head.jsonl").open() as log:
        for line in log:
            row = json.loads(line)
            if row.get("type") != "request":
                continue
            data = {key: value for key, value in row["request"].items() if key in keys}
            # A copied session should use its own image, not the old absolute path.
            image = session / row.get("frame_file", Path(data["jpeg_path"]).name)
            if not image.is_file():
                raise FileNotFoundError(image)
            data["jpeg_path"] = str(image.resolve())
            yield row.get("id"), HeadRequest(**data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--head", choices=("codex", "codex-server"), default="codex")
    parser.add_argument("--model")
    parser.add_argument("--effort", default="low")
    args = parser.parse_args()
    cls = CodexServerHead if args.head == "codex-server" else CodexHead
    head = cls(model=args.model, effort=args.effort)
    try:
        for ident, request in saved_requests(args.session):
            started = time.monotonic()
            try:
                answer = response_data(head.decide(request))
                row = {
                    "id": ident,
                    "head": args.head,
                    "duration": time.monotonic() - started,
                    "answer": answer,
                }
            except Exception as exc:
                row = {
                    "id": ident,
                    "head": args.head,
                    "duration": time.monotonic() - started,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            row["backend"] = getattr(head, "last_backend", args.head)
            row["server_error"] = getattr(head, "last_error", None)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    finally:
        close = getattr(head, "close", None)
        if close is not None:
            close()


if __name__ == "__main__":
    main()
