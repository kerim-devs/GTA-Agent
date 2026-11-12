import json

import numpy as np
import pytest

from pilot.trimming import check, cut, frame_runs, plan, resting


def write_json(path, value):
    path.write_text(json.dumps(value))


def write_lines(path, values):
    path.write_text("".join(json.dumps(value) + "\n" for value in values))


@pytest.fixture
def recording(tmp_path):
    rec = tmp_path / "source"
    rec.mkdir()
    write_lines(rec / "frames.jsonl", [{"i": i, "frame_id": 1000 + i, "t": i} for i in range(121)])
    write_lines(
        rec / "pad.jsonl",
        [{"t": 0, "src": "human", "buttons": [], "left": [0, 0], "right": [0, 0], "l2": 0, "r2": 0}],
    )
    write_json(rec / "meta.json", {})
    derived = tmp_path / "derived"
    derived.mkdir()
    write_json(derived / "sections.json", {"sections": [{"start": 0, "end": 120, "kind": "foot"}]})
    write_lines(derived / "texts.jsonl", [])
    return rec, derived


def test_plan_margins_whole_recording_and_no_human(recording):
    rec, derived = recording
    result = plan(rec, derived)
    assert result["whole_recording_would_be_cut"]
    assert [(s["start"], s["end"]) for s in result["stretches"]] == [(5, 115)]
    write_lines(rec / "pad.jsonl", [{"t": 0, "src": "agent"}])
    result = plan(rec, derived)
    assert result["no_human_input"] and result["stretches"] == []


@pytest.mark.parametrize("kind", ["foot", "drive", "menu", "unknown"])
def test_allowed_sections(recording, kind):
    rec, derived = recording
    write_json(derived / "sections.json", {"sections": [{"start": 0, "end": 120, "kind": kind}]})
    assert plan(rec, derived)["stretches"][0]["decision"] == "cut"


@pytest.mark.parametrize("kind", ["cutscene", "loading", "banner"])
def test_protected_sections(recording, kind):
    rec, derived = recording
    write_json(derived / "sections.json", {"sections": [{"start": 0, "end": 120, "kind": kind}]})
    result = plan(rec, derived)
    assert all(s["decision"] == "keep" for s in result["stretches"])
    assert kind in result["stretches"][0]["reason"]


@pytest.mark.parametrize("kind", ["subtitle", "objective", "banner", "dialogue"])
def test_text_kept_including_context(recording, kind):
    rec, derived = recording
    write_lines(derived / "texts.jsonl", [{"kind": kind, "first": 65, "last": 80}])
    result = plan(rec, derived)
    assert all(not (s["start"] < 85 and s["end"] > 60) for s in result["stretches"] if s["decision"] == "cut")
    assert any(kind in s["reason"] for s in result["stretches"])


def test_thresholds_and_short_rest(recording):
    assert resting({"l2": 0.099, "left": [0.249, 0]})
    for state in (
        {"l2": 0.1},
        {"r2": 0.1},
        {"left": [0.25, 0]},
        {"right": [0.2, 0.2]},
        {"buttons": ["cross"]},
    ):
        assert not resting(state)
    rec, derived = recording
    write_lines(
        rec / "pad.jsonl", [{"t": 0, "src": "human"}, {"t": 59.99, "src": "human", "buttons": ["cross"]}]
    )
    assert not plan(rec, derived)["stretches"]


def test_clock_holes_never_make_rest(recording):
    rec, derived = recording
    rows = [{"i": i, "frame_id": i, "t": t} for i, t in enumerate([0, 0.02, 100, 100.02])]
    write_lines(rec / "frames.jsonl", rows)
    assert list(frame_runs(rows)) == [(0, 2), (2, 4)]
    assert not plan(rec, derived)["stretches"]


def synthetic(tmp_path):
    import av

    rec = tmp_path / "source"
    rec.mkdir()
    with av.open(str(rec / "video.mp4"), "w") as output:
        stream = output.add_stream("libx264", rate=10)
        stream.width, stream.height, stream.pix_fmt = 64, 48, "yuv420p"
        stream.options = {"g": "10", "keyint_min": "10", "sc_threshold": "0", "bf": "2"}
        for i in range(120):
            pixels = np.zeros((48, 64, 3), dtype=np.uint8)
            pixels[:, :, 0] = i * 2
            pixels[:, i % 60 : i % 60 + 4, 1] = 255
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
    write_lines(rec / "frames.jsonl", [{"i": i, "frame_id": i + 100, "t": i / 10} for i in range(120)])
    write_lines(rec / "pad.jsonl", [{"t": t, "src": "human", "buttons": []} for t in [0, 2, 3, 6, 8, 11]])
    write_json(rec / "meta.json", {})
    specification = tmp_path / "plan.json"
    write_json(
        specification, {"recording": str(rec), "stretches": [{"start": 2.3, "end": 7.7, "decision": "cut"}]}
    )
    return rec, specification


def test_packet_copy_b_frames_and_failure_checks(tmp_path):
    rec, specification = synthetic(tmp_path)
    destination = tmp_path / "trimmed"
    result = cut(rec, specification, destination)
    assert [(c["start"], c["end"]) for c in result["cuts"]] == [(3, 7)]
    assert result["frames_after"] == 80
    assert check(rec, destination)["sampled_frames"] >= 50
    with pytest.raises(ValueError, match="new folder"):
        cut(rec, specification, destination)
    frames = destination / "frames.jsonl"
    old = frames.read_text()
    frames.write_text("\n".join(old.splitlines()[:-1]) + "\n")
    with pytest.raises(ValueError, match="missing"):
        check(rec, destination)
    frames.write_text(old)
    pad = destination / "pad.jsonl"
    pad.write_text(pad.read_text().replace('"t": 8', '"t": 8.1'))
    with pytest.raises(ValueError, match="pad line"):
        check(rec, destination)


def test_incident_trace_resets_image_change_at_clock_hole(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location(
        "trim_incident_tool", Path(__file__).parents[1] / "tools/incidents.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = [{"i": i, "t": t} for i, t in enumerate([0, 0.1, 61, 61.1])]
    write_lines(tmp_path / "frames.jsonl", rows)

    class Capture:
        index = -1

        def grab(self):
            self.index += 1
            return self.index < 4

        def retrieve(self):
            return True, np.full((720, 1280, 3), self.index * 30, np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(module.cv2, "VideoCapture", lambda _: Capture())
    monkeypatch.setattr(module.hud, "read", lambda _: SimpleNamespace(screen="game", wanted=0, health=1))
    monkeypatch.setattr(
        module,
        "read_minimap",
        lambda _: SimpleNamespace(minimap="flat", route="none", corrupt=False, blips=[]),
    )
    monkeypatch.setattr(module, "map_shift", lambda *_: 0)
    module.trace(tmp_path, tmp_path)
    traced = [json.loads(line) for line in (tmp_path / "hud.jsonl").read_text().splitlines()]
    assert [row["t"] for row in traced] == [0, 0.1, 61, 61.1]
    assert traced[1]["change"] is not None
    assert traced[2]["change"] is None and traced[2]["move"] is None


def test_action_video_reader_uses_original_clock_and_resets_motion(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from pilot import hud, minimap, motion
    from pilot.actions import read_recording

    rec, _ = synthetic(tmp_path)
    rows = [{"i": i, "frame_id": i + 100, "t": i / 10 + (60 if i >= 60 else 0)} for i in range(120)]
    write_lines(rec / "frames.jsonl", rows)
    monkeypatch.setattr(hud, "read", lambda _: SimpleNamespace(screen="game", wanted=0))
    monkeypatch.setattr(
        minimap, "read", lambda _: SimpleNamespace(minimap="flat", route="none", corrupt=False)
    )
    monkeypatch.setattr(motion, "map_motion", lambda *_: 1)
    monkeypatch.setattr(motion, "motion_state", lambda _: True)
    observed = read_recording(rec)
    before = [sample for sample in observed if sample.time < 60]
    after = [sample for sample in observed if sample.time >= 60]
    assert before[-1].end == 5.9
    assert after[0].time == 66 and after[0].index == 60
    assert after[0].look.moving is None and after[0].look.pan is None
    assert observed[-1].end == rows[-1]["t"]
