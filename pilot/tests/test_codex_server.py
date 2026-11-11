"""The stdio protocol is exercised without connecting to Codex or a controller."""

import json
import sys
import threading
import time

import pytest

from pilot.head import CodexServerHead, HeadRequest, parse_response

FAKE = r"""
import json, sys, time
from pathlib import Path
mode, log = sys.argv[1:3]
threads = 0
for line in sys.stdin:
    msg = json.loads(line)
    with Path(log).open("a") as out: out.write(json.dumps(msg) + "\n")
    method = msg["method"]
    result = {}
    if method == "initialized": continue
    if method == "thread/start":
        threads += 1
        result = {"thread": {"id": str(threads)}}
    if method == "turn/start":
        if mode == "broken":
            print("not json", flush=True); continue
        if mode == "timeout":
            time.sleep(10); continue
        if mode == "dead": sys.exit(1)
        result = {"turn": {"id": str(threads)}}
    print(json.dumps({"id": msg["id"], "result": result}), flush=True)
    if method == "turn/start":
        answer = json.dumps({"plan": [{"name": "walk", "args": {"duration": 1, "y": -1}}],
                             "sentence": "Weiter."})
        if mode == "invalid": answer = '{"plan": [], "sentence": "bad"}'
        print(json.dumps({"method": "item/completed", "params": {
            "threadId": str(threads), "turnId": str(threads),
            "item": {"id": "answer", "type": "agentMessage", "text": answer}}}), flush=True)
        print(json.dumps({"method": "turn/completed", "params": {
            "threadId": str(threads), "turn": {"id": str(threads), "status": "completed", "items": []}}}),
            flush=True)
"""


class Fallback:
    def __init__(self):
        self.calls = []

    def decide(self, request):
        self.calls.append(request)
        return parse_response({"plan": [{"name": "wait", "args": {}}], "sentence": "Fallback."})


def server(tmp_path, mode):
    import subprocess

    script = tmp_path / "server.py"
    script.write_text(FAKE)
    log = tmp_path / "protocol.jsonl"
    processes = []

    def factory(command, **kwargs):
        assert command[1:] == ["app-server", "--listen", "stdio://"]
        process = subprocess.Popen([sys.executable, str(script), mode, str(log)], **kwargs)
        processes.append(process)
        return process

    fallback = Fallback()
    head = CodexServerHead(process_factory=factory, fallback=fallback, timeout=0.5)
    request = HeadRequest([], "", "", "", "", {}, None, "", str(tmp_path / "frame.jpg"))
    return head, request, fallback, processes, log


def test_persistent_process_independent_threads_and_image(tmp_path):
    head, request, fallback, processes, log = server(tmp_path, "ok")
    try:
        assert head.decide(request).plan[0].name == "walk"
        assert head.decide(request).plan[0].name == "walk"
        assert len(processes) == 1
        assert not fallback.calls
        messages = [json.loads(line) for line in log.read_text().splitlines()]
        starts = [row for row in messages if row["method"] == "thread/start"]
        assert len(starts) == 2
        assert all(row["params"]["ephemeral"] is True for row in starts)
        turns = [row["params"] for row in messages if row["method"] == "turn/start"]
        assert [row["threadId"] for row in turns] == ["1", "2"]
        assert turns[0]["input"][1] == {"type": "localImage", "path": request.jpeg_path, "detail": "low"}
        assert turns[0]["outputSchema"]["additionalProperties"] is False
    finally:
        head.close()


@pytest.mark.parametrize("mode", ["broken", "timeout", "dead", "invalid"])
def test_bad_server_falls_back_and_restarts(tmp_path, mode):
    head, request, fallback, processes, _log = server(tmp_path, mode)
    try:
        assert head.decide(request).sentence == "Fallback."
        assert fallback.calls == [request]
        deadline = time.monotonic() + 2
        while len(processes) < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert len(processes) == 2
    finally:
        head.close()


def test_close_does_not_wait_for_process_or_lock():
    done = threading.Event()

    class Stuck:
        stdin = stdout = None

        def kill(self):
            pass

        def wait(self):
            done.wait(2)

    head = CodexServerHead()
    head.process = Stuck()
    head.lock.acquire()
    try:
        started = time.monotonic()
        head.close()
        assert time.monotonic() - started < 0.1
        assert head.process is None
    finally:
        head.lock.release()
        done.set()
