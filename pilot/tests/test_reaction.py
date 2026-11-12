"""Behavioral timing, anti-cheating and extension checks for the offline bench."""

import json
import time
from dataclasses import replace

import numpy as np
import pytest

from pilot.approaches import REGISTRY, Config, Judge, ReflexJudge, create
from pilot.contract import Pad
from pilot.reaction import Decision, Scene, aggregate, append_result, board, measure, replay


def scene(kind="enemy", **kwargs):
    return Scene(
        "test", "synthetic", 0.1, kind, answers=[{"l2": 0.5, "why": "aim"}], start=0, end=0.3, **kwargs
    )


def sample(t, matches=True):
    return {"t": t, "matches": matches, "decision_s": 0.01}


def test_known_onset_and_answer_and_link():
    result = measure(scene(), [sample(0.05, False), sample(0.18)])
    assert result["reaction_s"] == pytest.approx(0.08)
    assert result["reaction_link_s"] == pytest.approx(0.215)
    assert result["answered_3s"]


def test_pre_onset_void_and_held_pad_false_alarm():
    result = measure(scene(), [sample(0.01), sample(0.04), sample(0.18)])
    assert result["reaction_s"] is None
    assert result["void_pre_onset"]
    assert result["false_answers"] == 1


def test_calm_counts_separate_false_alarm_episodes_and_rates():
    s = scene("calm")
    metrics = measure(s, [sample(0.01), sample(0.08), sample(0.1, False), sample(0.2)])
    assert metrics["false_answers"] == 2
    a = aggregate([{"scene": {"kind": "calm"}, "metrics": metrics}])
    assert a["calm_false_per_scene"] == 2
    assert a["calm_false_per_minute"] == pytest.approx(400)


class Frames:
    closed = False

    def at(self, timestamp):
        return np.zeros((8, 8, 3), np.uint8), timestamp

    def close(self):
        self.closed = True


class Slow:
    def __init__(self, delay=0):
        self.delay = delay

    def step(self, frame, capture, now):
        time.sleep(self.delay)
        return Decision(Pad(l2=1) if capture >= 0.1 else Pad())

    def close(self):
        pass


def test_slow_real_computation_and_measured_cost_model():
    real = replay(scene(), Slow(0.075), recording=Frames())
    assert real["metrics"]["reaction_s"] >= 0.075
    assert real["metrics"]["decision_rate_hz"] < 20
    modelled = replay(scene(), Slow(), mode="modelled", cost_s=0.075, recording=Frames())
    assert modelled["mode"] == "modelled"
    assert modelled["metrics"]["reaction_s"] == pytest.approx(0.125)
    assert modelled["metrics"]["answer"]["frame_age_s"] == pytest.approx(0.075)


def test_model_requires_measured_cost():
    with pytest.raises(ValueError, match="measured cost"):
        replay(scene(), Slow(), mode="modelled", recording=Frames())


def test_judge_requires_second_agreeing_answer():
    judge = Judge(Config(second=True))
    try:
        judge.accept({"action": "fight", "why": "enemy"}, 1)
        assert judge.latest.pad == Pad()
        judge.accept({"action": "fight", "why": "enemy again"}, 2)
        assert judge.latest.pad.r2 == 1
        assert judge.latest.judgment_capture == 2
        judge.accept({"action": "neutral", "why": "gone"}, 3)
        assert judge.latest.pad.r2 == 1
        judge.accept({"action": "neutral", "why": "gone again"}, 4)
        assert judge.latest.pad == Pad()
    finally:
        judge.close()


def test_delayed_judge_keeps_cadence_until_real_reply():
    def transport(frame, capture):
        time.sleep(0.08)
        return {"action": "fight", "why": "test"}

    judge = Judge(Config(), transport=transport)
    pixels = np.zeros((8, 8, 3), np.uint8)
    try:
        start = time.perf_counter()
        assert judge.step(pixels, 1, 1).pad == Pad()
        assert time.perf_counter() - start < 0.05
        time.sleep(0.09)
        answer = judge.step(pixels, 1.1, 1.1)
        assert answer.pad.r2 == 1
        assert answer.judgment_capture == 1
    finally:
        judge.close()


class Constant:
    def __init__(self, decision):
        self.decision = decision

    def step(self, *args):
        return self.decision

    def close(self):
        pass


def test_reflex_protects_then_judge_withdraws_and_stale_reply_cannot_veto():
    reflex = Constant(Decision(Pad(l2=1), "threat"))
    judge = Constant(Decision())
    combined = ReflexJudge(Config(), reflex, judge)
    assert combined.step(None, 10, 10).pad.l2 == 1
    judge.decision = Decision(judgment_capture=9)
    assert combined.step(None, 10.1, 10.1).pad.l2 == 1
    judge.decision = Decision(judgment_capture=10)
    assert combined.step(None, 10.2, 10.2).pad == Pad()
    combined.close()


def test_one_registry_entry_is_sufficient(monkeypatch):
    monkeypatch.setitem(REGISTRY, "added", lambda config: Constant(Decision(Pad(l2=1))))
    added = create("added", Config())
    assert added.step(None, 0, 0).pad.l2 == 1
    added.close()


def test_ledger_is_append_only_board_separates_modes(tmp_path):
    row = replay(scene(), Slow(), mode="modelled", cost_s=0.02, recording=Frames())
    row["approach"] = "slow"
    path = tmp_path / "ledger.jsonl"
    append_result(path, row)
    original = path.read_bytes()
    append_result(path, {**row, "mode": "realtime"})
    assert path.read_bytes().startswith(original)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    result = board(rows, tmp_path)
    assert "slow | modelled" in result and "slow | realtime" in result
    assert "<table>" in (tmp_path / "board.html").read_text()


def test_human_alignment_adds_lead_and_held_state_voids(tmp_path):
    from pilot.reaction import human_result

    (tmp_path / "pad.jsonl").write_text(
        "\n".join(
            json.dumps(
                {"t": t, "src": "human", "buttons": [], "left": [0, 0], "right": [0, 0], "l2": l2, "r2": 0}
            )
            for t, l2 in [(-0.1, 0), (0.1, 1), (0.2, 0)]
        )
    )
    s = replace(scene(), recording=str(tmp_path), human={"lead_s": 0.05, "lead_source": "estimated"})
    row = human_result(s)
    assert row["metrics"]["reaction_s"] == pytest.approx(0.05)
    s.onset = 0.18
    assert human_result(s)["metrics"]["void_pre_onset"]


def test_real_pilot_path_produces_pad_and_cleans_scratch(tmp_path):
    from pilot.approaches import Pilot

    approach = Pilot(Config(output=tmp_path, modelled_delay=0.1))
    try:
        pixels = np.zeros((720, 1280, 3), np.uint8)
        result = approach.step(pixels, 1, 1)
        assert isinstance(result.pad, Pad)
        result = approach.step(pixels, 1.04, 1.04)
        assert isinstance(result.pad, Pad)
    finally:
        approach.close()
    assert not list(tmp_path.glob("scratch-*"))


class TurnsFirst:
    """Sees the threat at once and turns towards it, as Fight does; the replayed picture never
    turns, so it never aims."""

    def step(self, frame, capture, now):
        if capture >= 0.1:
            return Decision(Pad(right=(0.4, 0.0)), "turning to the blip", noticed="red blip")
        return Decision()

    def close(self):
        pass


def test_noticed_and_answered_are_two_times():
    turning = replay(scene(), TurnsFirst(), recording=Frames())
    assert turning["metrics"]["noticed_s"] == pytest.approx(0, abs=0.04)
    assert turning["metrics"]["reaction_s"] is None
    # Noticed from the decision's own field, not guessed from the pad: an answer without it is
    # answered and not noticed.
    plain = replay(scene(), Slow(), recording=Frames())
    assert plain["metrics"]["reaction_s"] is not None
    assert plain["metrics"]["noticed_s"] is None


def test_notice_before_the_onset_voids_and_counts_as_false():
    rows = [
        {"t": 0.05, "matches": False, "noticed": "red blip", "decision_s": 0.01},
        {"t": 0.12, "matches": True, "noticed": "red blip", "decision_s": 0.01},
    ]
    metrics = measure(scene(), rows)
    assert metrics["noticed_s"] is None and metrics["notice_void_pre_onset"]
    assert metrics["false_notices"] == 1
    assert metrics["reaction_s"] == pytest.approx(0.02)


def test_board_shows_both_times_and_says_which(tmp_path):
    row = replay(scene(), TurnsFirst(), recording=Frames())
    row["approach"] = "turns"
    content = board([row], tmp_path)
    assert "Noticed median" in content and "Answered median" in content
    line = next(line for line in content.splitlines() if line.startswith("| turns |"))
    cells = [cell.strip() for cell in line.strip("|").split("|")]
    assert cells[3] == "100.0%" and cells[5] == "0.0%"


def test_second_answer_judge_notices_at_the_first_and_answers_at_the_second():
    judge = Judge(Config(second=True), transport=lambda frame, capture: {"action": "fight", "why": "x"})
    pixels = np.zeros((8, 8, 3), np.uint8)
    seen = []
    try:
        for tick in range(200):
            decision = judge.step(pixels, tick, tick)
            seen.append((judge.answers, decision))
            if judge.answers >= 2:
                break
            time.sleep(0.005)
    finally:
        judge.close()
    after_first = next(decision for count, decision in seen if count == 1)
    assert after_first.noticed == "model named fight" and after_first.pad == Pad()
    assert seen[-1][1].pad.r2 == 1
    assert [row["action"] for row in judge.answer_log] == ["fight", "fight"]
    assert all(row["duration_s"] >= 0 for row in judge.answer_log)


def test_letter_reply_is_one_fixed_answer_or_a_failure():
    from pilot.approaches import letter_answer

    choice = {
        "message": {"content": " B\n"},
        "logprobs": {
            "content": [
                {
                    "token": "B",
                    "logprob": -0.1,
                    "top_logprobs": [{"token": "B", "logprob": -0.1}, {"token": "A", "logprob": -2.4}],
                }
            ]
        },
    }
    answer = letter_answer(choice)
    assert answer["action"] == "fight" and answer["letter"] == "B"
    assert 0.9 < answer["p"] < 1
    assert letter_answer({"message": {"content": "c."}})["action"] == "flee"
    for content in ("B D", "Yes", '{"action":"fight"}', "E", ""):
        with pytest.raises(ValueError):
            letter_answer({"message": {"content": content}})


def test_letter_question_goes_out_as_the_pilot_judge_asks(tmp_path):
    import base64
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    import cv2

    from pilot import judge as judge_questions
    from pilot.approaches import LETTER_TOKENS, THREAT_QUESTION, request

    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(data)
            body = json.dumps({"choices": [{"message": {"content": "C"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = Config(endpoint=f"http://127.0.0.1:{server.server_port}", model="m", question="letter")
        answer = request(config, np.zeros((720, 1280, 3), np.uint8), 5)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert answer["action"] == "flee" and answer["p"] is None
    data = seen[0]
    assert data["max_tokens"] == LETTER_TOKENS and data["temperature"] == 0
    assert data["messages"][0] == {"role": "system", "content": judge_questions.SYSTEM}
    image, text = data["messages"][1]["content"]
    assert text == {"type": "text", "text": THREAT_QUESTION}
    jpeg = base64.b64decode(image["image_url"]["url"].split(",", 1)[1])
    assert cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR).shape[:2] == (360, 640)


def test_kerim_looser_reading_counts_a_new_press_while_another_is_held(tmp_path):
    from pilot.reaction import human_result

    rows = [(-0.1, 1, 0), (0.15, 1, 1), (0.25, 1, 0)]  # aim held from before, fire pressed after
    (tmp_path / "pad.jsonl").write_text(
        "\n".join(
            json.dumps(
                {"t": t, "src": "human", "buttons": [], "left": [0, 0], "right": [0, 0], "l2": l2, "r2": r2}
            )
            for t, l2, r2 in rows
        )
    )
    answers = [{"l2": 0.5, "why": "aim"}, {"r2": 0.5, "why": "fire"}]
    s = replace(
        scene(), recording=str(tmp_path), answers=answers, human={"lead_s": 0.0, "lead_source": "estimated"}
    )
    metrics = human_result(s)["metrics"]
    assert metrics["void_pre_onset"] and metrics["reaction_s"] is None
    assert metrics["loose_reaction_s"] == pytest.approx(0.05)
    assert metrics["loose_answer"]["why"] == "fire"
    # A held input that is never pressed anew gives no looser answer either.
    (tmp_path / "pad.jsonl").write_text(
        json.dumps(
            {"t": -0.1, "src": "human", "buttons": [], "left": [0, 0], "right": [0, 0], "l2": 1, "r2": 0}
        )
    )
    assert human_result(s)["metrics"]["loose_reaction_s"] is None


def test_answer_statistics_count_naming_and_false_calls():
    from pilot.reaction import answer_stats

    def answer(capture, action, duration=0.3):
        return {"capture": capture, "action": action, "duration_s": duration}

    threat = {
        "scene": {"kind": "enemy", "onset": 10.0},
        "model_answers": [
            answer(3.5, "fight"),  # outside the six seconds before the onset
            answer(5, "neutral"),
            answer(9, "fight"),  # a false call before the onset
            answer(10.1, "neutral"),
            answer(10.4, "fight", 0.5),
        ],
    }
    calm = {
        "scene": {"kind": "calm", "onset": 20.0},
        "model_answers": [answer(18, "neutral"), answer(19, "flee")],
    }
    s = answer_stats([threat, calm])
    assert s["named_share"] == 1 and s["named_needed_median"] == 2
    assert s["lead_false_share"] == pytest.approx(0.5) and s["lead_answers"] == 2
    assert s["calm_false_share"] == pytest.approx(0.5)
    assert s["answer_worst_s"] == pytest.approx(0.5)


def test_local_delayed_http_judge_policy_and_head(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from pilot.approaches import Head, request

    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, data))
            time.sleep(0.06)
            answer = {"action": "flee", "why": "fixed delayed test answer"}
            body = json.dumps(
                {"version": 1, "capture": data["capture"], "pad": {"l2": 1}, "why": "test"}
                if self.path == "/policy"
                else {"choices": [{"message": {"content": json.dumps(answer)}}]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = Config(endpoint=f"http://127.0.0.1:{server.server_port}", output=tmp_path)
    pixels = np.zeros((720, 1280, 3), np.uint8)
    try:
        start = time.perf_counter()
        assert request(config, pixels, 3)["action"] == "flee"
        assert time.perf_counter() - start >= 0.06
        assert request(config, pixels, 4, policy=True)["capture"] == 4
        approach = Head(config)
        try:
            start = time.perf_counter()
            while time.perf_counter() - start < 0.35:
                now = time.perf_counter() - start
                approach.step(pixels, now, now)
                time.sleep(0.02)
            assert any(row["stage"] == "head" for row in approach.trace)
            assert any(row["stage"] == "plan" for row in approach.trace)
        finally:
            approach.close()
        assert any(path == "/policy" for path, _ in requests)
        assert all("image_jpeg_base64" in data or "messages" in data for _, data in requests)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
