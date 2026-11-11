"""Calibration measurements and safety against a delayed, frame-based console."""

import importlib.util
import json
from pathlib import Path

import pytest

from pilot import calibrate
from pilot.contract import NEUTRAL_PAD

SPEC = importlib.util.spec_from_file_location(
    "sim_console", Path(__file__).resolve().parents[1] / "tools" / "sim_console.py"
)
sim_console = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sim_console)


@pytest.fixture(scope="module")
def images():
    return sim_console.bases()


def run(tmp_path, images, *, only=(), skip=(), shadow=False, **kwargs):
    sim = sim_console.SimConsole(images=images, **kwargs)
    report = calibrate.run_calibrate(
        sim,
        only=only,
        skip=skip,
        car=True,
        yes=True,
        shadow=shadow,
        record_dir=tmp_path,
        clock=sim.clock,
        sleep=sim.sleep,
        detector_factory=sim_console.SimDetector,
        head=sim_console.SimHead(),
        output=lambda line: None,
    )
    assert sim.stopped
    saved = json.loads((tmp_path / "session" / "calibration.json").read_text())
    assert saved == json.loads(json.dumps(report))
    for call in sim.calls:
        pad = call["pad"]
        assert set(pad.buttons) <= calibrate.BUTTONS
        assert not pad.l2 and not pad.r2
        if "cross" in pad.buttons:
            assert call["screen"] == "pause"
    if sim.calls:
        assert sim.calls[-1]["pad"] == NEUTRAL_PAD
        assert sim.input == NEUTRAL_PAD
    return sim, {item["name"]: item for item in report["checks"]}, report


@pytest.mark.parametrize("delay,deadzone,ticks,sign,door", [(0.14, 0.12, 1, 1, 2.0), (0.6, 0.25, 3, -1, 5.0)])
def test_recovers_console_values(tmp_path, images, delay, deadzone, ticks, sign, door):
    _sim, checks, report = run(
        tmp_path, images, delay=delay, deadzone=deadzone, press_ticks=ticks, map_sign=sign, door=door
    )
    assert {name: item["reason"] for name, item in checks.items() if item["status"] != "ran"} == {}
    assert checks["delay"]["numbers"]["seconds"] == pytest.approx(delay, abs=2 * calibrate.TICK)
    camera = checks["camera"]["numbers"]
    assert deadzone < camera["minimum_stick"] <= deadzone + 0.1
    assert camera["samples"][-1]["pixels_per_second"] == pytest.approx(120, abs=5)
    assert deadzone < checks["walk"]["numbers"]["minimum_stick"] <= deadzone + 0.1
    assert all(isinstance(value["moving"], bool) for value in checks["walk"]["numbers"]["samples"])
    assert checks["press"]["numbers"]["minimum_ticks"] == {"options": ticks, "circle": ticks}
    for axis, name in enumerate(("right", "down")):
        assert checks["map"]["numbers"][name]["pixels_per_second"][axis] == pytest.approx(65 * sign, abs=5)
    assert checks["wheel"]["numbers"]["after_release"] == "game"
    assert checks["phone"]["numbers"]["close_seconds"] > 0
    for name in ("enter", "exit"):
        assert checks["car"]["numbers"][name]["seconds"] == pytest.approx(
            door + delay, abs=3 * calibrate.TICK
        )
        assert checks["car"]["numbers"][name]["confirmed_seconds"] >= door + delay + 0.99
    assert checks["detector"]["numbers"]["results_per_second"] == pytest.approx(10, abs=0.21)
    assert checks["detector"]["numbers"]["loop_per_second"] == pytest.approx(30, abs=0.1)
    assert checks["head"]["numbers"]["request_count"] == 1
    assert 30 < report["elapsed_seconds"] < 120
    assert all(item["raw"] for item in checks.values())


@pytest.mark.parametrize("name", calibrate.CHECKS[:8])
def test_unmet_precondition_is_passive(tmp_path, images, name):
    sim, checks, _ = run(tmp_path, images, only=[name], initial="pause")
    assert checks[name]["status"] == "skipped"
    assert sim.calls == []


@pytest.mark.parametrize("name", calibrate.CHECKS[:8])
@pytest.mark.parametrize("failure", ["interrupt_at", "conflict_at"])
def test_active_checks_neutralize_on_interrupt_and_takeover(tmp_path, images, name, failure):
    sim, checks, _ = run(tmp_path, images, only=[name], **{failure: 0.2})
    assert checks[name]["status"] == "aborted"
    assert sim.calls[-1]["pad"] == NEUTRAL_PAD


@pytest.mark.parametrize("name", calibrate.CHECKS[:8])
def test_active_checks_obey_session_deadline(tmp_path, images, monkeypatch, name):
    monkeypatch.setattr(calibrate, "LIMIT", 0.25)
    sim, checks, report = run(tmp_path, images, only=[name])
    assert checks[name]["status"] == "aborted"
    assert "deadline" in report["stop_reason"]
    assert report["elapsed_seconds"] <= 0.25 + 2 * calibrate.TICK
    assert sim.calls[-1]["pad"] == NEUTRAL_PAD


def test_shadow_is_read_only(tmp_path, images):
    sim, checks, _ = run(tmp_path, images, shadow=True)
    assert sim.calls == []
    assert all(item["status"] == "ran" for item in checks.values())


def test_frozen_picture_and_pause_failure_are_aborted(tmp_path, images):
    _, checks, _ = run(tmp_path, images, only=["delay", "press"], frozen=True, no_pause=True)
    assert all(item["status"] == "aborted" for item in checks.values())
    assert "did not move" in checks["delay"]["reason"]
    assert "four ticks" in checks["press"]["reason"]


def test_unexpected_phone_backs_out_then_next_check_runs(tmp_path, images):
    sim, checks, _ = run(tmp_path, images, only=["camera", "wheel"], surprise_at=0.3)
    assert checks["camera"]["status"] == "aborted"
    assert checks["wheel"]["status"] == "ran"
    assert any(call["screen"] == "phone" and call["pad"].buttons == ("circle",) for call in sim.calls)


def test_a_frame_that_comes_late_does_not_end_a_check(tmp_path, images):
    _, checks, _ = run(tmp_path, images, only=["camera"], stale=(0.3, 0.5))
    assert checks["camera"]["status"] == "ran"
    assert any(not row["fresh"] for row in checks["camera"]["raw"])
    assert checks["camera"]["numbers"]["samples"][-1]["pixels_per_second"] == pytest.approx(120, abs=5)


def test_a_picture_that_stays_away_ends_the_check_with_a_neutral_pad(tmp_path, images):
    sim, checks, _ = run(tmp_path, images, only=["camera", "phone"], stale=(0.3, 1.5))
    assert checks["camera"]["status"] == "aborted"
    assert checks["camera"]["reason"] == "missing or stale picture"
    released = [call for call in sim.calls if 0.3 <= call["t"] < 1.5]
    assert released and all(call["pad"] == NEUTRAL_PAD for call in released)
    assert checks["phone"]["status"] == "ran"


def test_a_menu_that_shows_up_late_is_still_closed(tmp_path, images):
    # Slower than the wait for the answer: the phone is asked for, given up on, and then appears.
    sim, checks, _ = run(tmp_path, images, only=["phone"], delay=1.5)
    assert checks["phone"]["status"] == "aborted"
    sim.sleep(5)
    sim.frame()
    assert sim.screen == "game"
    assert [call["pad"].buttons for call in sim.calls if call["pad"].buttons][-1] == ("circle",)


def test_cross_is_let_go_the_moment_the_map_is_seen(tmp_path, images):
    # A link faster than the press: the map is in the picture while Cross would still be held.
    sim, checks, _ = run(tmp_path, images, only=["map"], delay=0.03)
    assert checks["map"]["status"] == "ran"
    assert sum("cross" in call["pad"].buttons for call in sim.calls) < 4


@pytest.mark.parametrize("name", calibrate.CHECKS[:8])
def test_an_open_phone_on_foot_is_no_place_to_start(tmp_path, images, name):
    # The minimap stays on screen behind the phone, so the map alone would let the check run.
    on_foot = dict(images)
    on_foot["phone"] = images["phone"].copy()
    on_foot["phone"][530:700, 30:290] = images["game"][530:700, 30:290]
    sim, checks, _ = run(tmp_path, on_foot, only=[name], initial="phone")
    assert checks[name]["status"] == "skipped" and "screen=phone, minimap=flat" in checks[name]["reason"]
    assert sim.calls == []


def test_a_backout_that_loses_the_picture_looks_again(tmp_path, images):
    _sim, checks, _ = run(tmp_path, images, only=["camera", "wheel"], surprise_at=0.3, stale=(0.45, 1.0))
    assert checks["camera"]["status"] == "aborted"
    assert checks["wheel"]["status"] == "ran"


def test_later_checks_wait_as_long_as_the_measured_delay_asks(tmp_path, images):
    _, checks, _ = run(tmp_path, images, only=["delay", "phone", "wheel"], delay=0.9)
    assert checks["delay"]["numbers"]["settle_seconds"] == pytest.approx(2 * 0.9 + 0.4, abs=0.1)
    assert checks["phone"]["status"] == checks["wheel"]["status"] == "ran"


def test_missing_detector_weights_end_only_that_check(tmp_path, images):
    sim = sim_console.SimConsole(images=images)

    def missing():
        raise RuntimeError("YOLOX weights missing or corrupt")

    report = calibrate.run_calibrate(
        sim,
        only=["detector", "head"],
        yes=True,
        record_dir=tmp_path,
        clock=sim.clock,
        sleep=sim.sleep,
        detector_factory=missing,
        head=sim_console.SimHead(),
        output=lambda line: None,
    )
    assert [(item["name"], item["status"]) for item in report["checks"]] == [
        ("detector", "aborted"),
        ("head", "ran"),
    ]
    assert "stop_reason" not in report


def test_selection_is_ordered_and_requires_car_flag():
    assert calibrate.selection(["phone,delay,car", "camera"], ["camera"]) == ["delay", "phone"]
    assert calibrate.selection(["car"], car=True) == ["car"]
    with pytest.raises(ValueError):
        calibrate.selection(["unknown"])


@pytest.mark.parametrize("screen", ["pause", "map", "phone", "weapon_wheel"])
def test_backout_is_only_circle_on_supported_screens(tmp_path, images, screen):
    sim, checks, _ = run(tmp_path, images, only=["camera", "head"], surprise_at=0.3, surprise_screen=screen)
    assert checks["camera"]["status"] == "aborted"
    assert checks["head"]["status"] == "ran"
    after = [call for call in sim.calls if call["t"] >= 0.3 and call["pad"].buttons]
    assert all(
        call["pad"].buttons == ("circle",) and call["screen"] in {"pause", "map", "phone"} for call in after
    )
    if screen == "weapon_wheel":
        assert not after


def test_passive_diagnostics_have_no_pad_calls(tmp_path, images):
    sim, checks, _ = run(tmp_path, images, only=["detector", "head"])
    assert sim.calls == []
    assert all(item["status"] == "ran" for item in checks.values())


def test_head_duration_is_one_request(tmp_path, images):
    sim = sim_console.SimConsole(images=images)

    class Head:
        calls = 0

        def decide(self, request):
            self.calls += 1
            assert Path(request.jpeg_path).is_file()
            sim.sleep(0.75)
            return "A passive description"

    head = Head()
    report = calibrate.run_calibrate(
        sim,
        only=["head"],
        yes=True,
        record_dir=tmp_path,
        clock=sim.clock,
        sleep=sim.sleep,
        head=head,
        output=lambda line: None,
    )
    assert report["checks"][0]["numbers"]["seconds"] == pytest.approx(0.75, abs=2 * calibrate.TICK)
    assert head.calls == 1
    assert not sim.calls


def test_default_deadline_prevents_inputs_after_four_minutes(tmp_path, images):
    sim = sim_console.SimConsole(images=images)

    def sleep(seconds):
        sim.sleep(seconds)
        if sim.calls:
            sim.now = 240.0

    report = calibrate.run_calibrate(
        sim,
        only=["camera", "phone"],
        yes=True,
        record_dir=tmp_path,
        clock=sim.clock,
        sleep=sleep,
        output=lambda line: None,
    )
    assert report["limit_seconds"] == 240
    assert report["elapsed_seconds"] == 240
    assert report["checks"][0]["status"] == "aborted"
    assert report["checks"][1]["status"] == "skipped"
    assert all(call["pad"] == NEUTRAL_PAD for call in sim.calls if call["t"] >= 240)


def test_confirmation_precedes_first_command(tmp_path, images):
    sim = sim_console.SimConsole(images=images)
    prompts = []

    def confirm(message):
        assert not sim.calls
        prompts.append(message)

    calibrate.run_calibrate(
        sim,
        only=["phone"],
        record_dir=tmp_path,
        clock=sim.clock,
        sleep=sim.sleep,
        confirm=confirm,
        output=lambda line: None,
    )
    assert prompts == ["Enter startet die Eingaben. "]


def test_cli_forwards_selection_without_live_bridge(monkeypatch):
    from pilot import cli

    class Bridge:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    calls = []
    monkeypatch.setattr(cli, "Bridge", Bridge)
    monkeypatch.setattr(cli, "run_calibrate", lambda bridge, **kwargs: calls.append(kwargs))
    cli.main(
        ["calibrate", "--only", "phone,car", "--skip", "phone", "--car", "--yes", "--shadow", "--head", "off"]
    )
    assert calls[0]["only"] == ["phone,car"]
    assert calls[0]["skip"] == ["phone"]
    assert calls[0]["car"] and calls[0]["yes"] and calls[0]["shadow"]
    assert calls[0]["head"] is None
