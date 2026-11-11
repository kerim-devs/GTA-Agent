"""Exercise the local overlay with disposable logs and HTTP only."""

import json
import threading
import time
from contextlib import contextmanager
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from pilot import cli
from pilot.overlay import JsonlTail, OverlayState, make_server


def append(path, row):
    with path.open("a") as stream:
        stream.write(json.dumps(row) + "\n")


def request(identifier=1, t=100, **context):
    return {"type": "request", "id": identifier, "t": t, "request": context}


def response(sentence, identifier=1, t=101, **changes):
    return {
        "type": "response",
        "id": identifier,
        "t": t,
        "applied": True,
        "overtaken": False,
        "sentence": sentence,
        "plan": [{"name": "drive_route", "args": {}}, {"name": "wait", "args": {}}],
        **changes,
    }


@contextmanager
def serving(state):
    server = make_server(state, port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def fetch(url):
    with urlopen(url, timeout=2) as reply:
        return json.load(reply)


def event(stream):
    while True:
        line = stream.readline()
        if not line:
            raise AssertionError("event stream closed")
        if line.startswith(b"data: "):
            return json.loads(line[6:])


def test_http_growing_log_updates_within_one_second_and_reconnects(tmp_path):
    session = tmp_path / "001"
    session.mkdir()
    head = session / "head.jsonl"
    append(head, request(objective="Zum Hafen", help="Route prüfen"))
    with serving(OverlayState(tmp_path)) as (server, base):
        assert server.server_address[0] == "127.0.0.1"
        with urlopen(base + "/events", timeout=2) as stream:
            assert stream.headers["Content-Type"].startswith("text/event-stream")
            first = event(stream)
            assert first["thinking"] and first["objective"] == "Zum Hafen"
            started = time.monotonic()
            append(head, response("Ich fahre zum Hafen."))
            while time.monotonic() - started < 1:
                state = event(stream)
                if state["sentence"]:
                    break
            elapsed = time.monotonic() - started
            assert elapsed < 1
            print(f"SSE append-to-client latency: {elapsed:.3f}s")
            assert state["sentence"] == "Ich fahre zum Hafen."
            assert not state["thinking"]
            assert len(state["plan"]) == 2
        # A reconnected stream receives a complete snapshot, without a cursor.
        with urlopen(base + "/events", timeout=2) as stream:
            assert event(stream) == state


def test_partial_malformed_and_replaced_logs_remain_usable(tmp_path):
    session = tmp_path / "001"
    session.mkdir()
    head = session / "head.jsonl"
    head.write_bytes(b'{"type":"request","id":1,"request":')
    with serving(OverlayState(tmp_path)) as (_, base):
        assert not fetch(base + "/api/state")["thinking"]
        with head.open("ab") as stream:
            stream.write(b"{} }\nnot json\n[]\nnull\n\xff\n")
        assert fetch(base + "/api/state")["thinking"]
        append(head, response("Weiterfahren"))
        assert fetch(base + "/api/state")["sentence"] == "Weiterfahren"
        head.write_text(json.dumps(response("Kurz")) + "\n")
        assert fetch(base + "/api/state")["sentence"] == "Kurz"
        replacement = session / "replacement"
        replacement.write_text(json.dumps(response("Neue Datei")) + "\n")
        replacement.replace(head)
        assert fetch(base + "/api/state")["sentence"] == "Neue Datei"
        head.unlink()
        assert fetch(base + "/api/state")["sentence"] == "Neue Datei"


def test_tail_recovers_from_same_size_rewrite_and_oversized_partial_line(tmp_path):
    path = tmp_path / "log"
    path.write_text('{"value":1}\n')
    tail = JsonlTail(path)
    assert tail.read() == [{"value": 1}]
    path.write_text('{"value":2}\n')
    assert tail.read() == [{"value": 2}]
    with path.open("ab") as stream:
        stream.write(b"x" * (2 * 1024 * 1024 + 10))
    for _ in range(3):
        assert tail.read() == []
    with path.open("ab") as stream:
        stream.write(b'\n{"value":3}\n')
    assert tail.read() == [{"value": 3}]


def test_missing_root_new_session_and_idle_end(tmp_path):
    now = [0.0]
    root = tmp_path / "missing"
    model = OverlayState(root, clock=lambda: now[0])
    with serving(model) as (_, base):
        assert fetch(base + "/api/state")["status"] == "waiting"
        first = root / "001"
        first.mkdir(parents=True)
        append(first / "head.jsonl", response("Alt"))
        assert fetch(base + "/api/state")["sentence"] == "Alt"
        second = root / "002"
        second.mkdir()
        append(second / "play.jsonl", {"t": 0, "skill": {"name": "wait", "status": "running"}})
        state = fetch(base + "/api/state")
        assert state["session"] == "002"
        assert state["sentence"] == "" and state["skill"]["name"] == "wait"
        now[0] = 5
        assert fetch(base + "/api/state")["status"] == "stale"


def test_only_applied_answers_and_current_request_clear_thinking(tmp_path):
    session = tmp_path / "001"
    session.mkdir()
    head = session / "head.jsonl"
    model = OverlayState(tmp_path)
    append(head, response("Gültig"))
    append(head, request(identifier=2, objective="Neues Ziel"))
    append(head, response("Verworfen", applied=False))
    assert model.snapshot()["thinking"]
    append(head, response("Überholt", identifier=2, overtaken=True))
    state = model.snapshot()
    assert state["sentence"] == "Gültig" and not state["thinking"]
    append(head, request(identifier=3))
    assert model.snapshot()["objective"] == ""


def test_metrics_takeover_and_explicit_shadow(tmp_path):
    session = tmp_path / "001"
    session.mkdir()
    play = session / "play.jsonl"
    append(play, {"reading": {"gps_speed": 10, "gps_distance": 1234}, "status": 409})
    state = OverlayState(tmp_path).snapshot()
    assert state["speed_kmh"] == 36 and state["distance_m"] == 1234
    assert state["takeover"] and state["shadow"] is False
    model = OverlayState(tmp_path, shadow=True)
    assert model.snapshot()["shadow"] is True
    append(play, {"reading": None, "status": None, "sent": False})
    assert model.snapshot()["takeover"]
    append(play, {"reading": {"gps_speed": 1e308, "gps_distance": float("nan")}, "status": 200, "sent": True})
    state = model.snapshot()
    assert state["speed_kmh"] is None and state["distance_m"] is None
    assert not state["takeover"]
    append(play, {"reading": None, "skill": "invalid", "sent": False})
    assert model.snapshot()["skill"] is None


def test_demo_aligns_time_bases_and_preserves_recorded_pace(tmp_path):
    session = tmp_path / "demo"
    session.mkdir()
    append(session / "play.jsonl", {"t": 0.1, "fresh": False})
    append(session / "play.jsonl", {"t": 0.5, "fresh": True, "reading": {"gps_speed": 10}})
    append(session / "play.jsonl", {"t": 2.5, "fresh": True, "reading": {"gps_speed": 20}})
    append(session / "head.jsonl", request(t=700))
    append(session / "head.jsonl", response("Angekommen", t=702, duration=2))
    now = [50.0]
    model = OverlayState(tmp_path, demo=session, clock=lambda: now[0])
    assert model.snapshot()["sentence"] == ""
    now[0] = 50.5
    state = model.snapshot()
    assert state["thinking"] and state["speed_kmh"] == 36
    now[0] = 52.49
    assert model.snapshot()["sentence"] == ""
    now[0] = 52.5
    state = model.snapshot()
    assert state["sentence"] == "Angekommen"
    assert state["speed_kmh"] == 72 and state["status"] == "ended"
    now[0] = 100
    assert model.snapshot() == state


def test_demo_missing_empty_or_malformed_recording(tmp_path):
    assert OverlayState(tmp_path, demo=tmp_path / "missing").snapshot()["status"] == "waiting"
    append(tmp_path / "head.jsonl", {"t": "invalid"})
    append(tmp_path / "play.jsonl", {"t": float("nan")})
    assert OverlayState(tmp_path, demo=tmp_path).snapshot()["status"] == "ended"


def test_local_assets_served_without_external_dependencies(tmp_path):
    with serving(OverlayState(tmp_path)) as (_, base):
        for route, content_type in (
            ("/", "text/html"),
            ("/overlay.css", "text/css"),
            ("/overlay.js", "text/javascript"),
        ):
            with urlopen(base + route, timeout=2) as reply:
                body = reply.read().decode()
                assert reply.headers["Content-Type"].startswith(content_type)
                assert reply.headers["Cache-Control"] == "no-store"
                assert "http://" not in body and "https://" not in body
                assert body
        with pytest.raises(HTTPError) as caught:
            urlopen(base + "/../head.jsonl", timeout=2)
        assert caught.value.code == 404


def test_cli_overlay_defaults_and_options_do_not_construct_bridge(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(cli, "run_overlay", lambda *args: calls.append(args))
    monkeypatch.setattr(cli, "Pipeline", lambda **kwargs: pytest.fail("overlay constructed driving pipeline"))
    monkeypatch.setattr(cli, "Bridge", lambda *args, **kwargs: pytest.fail("overlay constructed bridge"))
    cli.main(["overlay"])
    assert calls == [(cli.PLAY_RECORDINGS, 9396, None, False)]
    cli.main(["overlay", "--root", str(tmp_path), "--port", "9400", "--demo", str(tmp_path), "--shadow"])
    assert calls[-1] == (tmp_path, 9400, tmp_path, True)


@pytest.mark.parametrize("port", ["0", "-1", "65536", "not-a-port"])
def test_cli_rejects_invalid_overlay_port(port):
    with pytest.raises(SystemExit) as caught:
        cli.main(["overlay", "--port", port])
    assert caught.value.code == 2


def test_overlay_page_hides_stale_content_and_resumes(tmp_path):
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to exercise the shipped overlay script")
    script = Path(__file__).parents[1] / "src" / "pilot" / "overlay_web" / "overlay.js"
    harness = tmp_path / "quiet.cjs"
    harness.write_text(r"""
const fs = require("fs");
const vm = require("vm");
const assert = require("assert/strict");
const nodes = new Map();
global.document = {
  body: { hidden: false },
  getElementById(id) {
    if (!nodes.has(id)) {
      nodes.set(id, {textContent: "", hidden: false, replaceChildren() {}, appendChild() {}});
    }
    return nodes.get(id);
  },
  createElement() { return {textContent: ""}; },
};
global.EventSource = class {};
vm.runInThisContext(fs.readFileSync(process.argv[2], "utf8"));
render({status: "live", sentence: "A current thought"});
assert.equal(document.body.hidden, false);
render({status: "stale", sentence: "An old thought"});
assert.equal(document.body.hidden, true);
render({status: "live", sentence: "A new thought"});
assert.equal(document.body.hidden, false);
assert.equal(document.getElementById("sentence").textContent, "A new thought");
render({status: "ended", sentence: "Demo finished"});
assert.equal(document.body.hidden, false);
""")
    subprocess.run([node, str(harness), str(script)], check=True, capture_output=True, timeout=5)
