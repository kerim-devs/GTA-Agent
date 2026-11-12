"""Evidence and safety tests use disposable logs and a fake console only."""

import json

import pytest

from pilot import bench


def session(
    folder,
    *,
    start="flat",
    end="flat",
    skill="press",
    done=True,
    reason="done",
    route="none",
    mission=False,
    moving=None,
):
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for t in range(23):
        row = {
            "t": t,
            "fresh": True,
            "status": 200,
            "reading": {
                "minimap": start if t < 2 else end,
                "route": route,
                "gps_distance": 300 - t * 5,
                "gps_speed": 10,
            },
            "skill": {"name": skill, "status": "done" if done else "failed", "reason": reason},
        }
        if moving is not None:
            row["moving"] = moving[t] if isinstance(moving, list) else moving
        rows.append(row)
    (folder / "play.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    head = [
        {
            "id": t,
            "t": 400000 + t,
            "type": "request",
            "request": {
                "objective": "Follow him" if mission else "",
                "hud": {"screen": "game", "wanted": 0, "health": 1},
                "objects": [],
                "last_skill": rows[t]["skill"],
            },
        }
        for t in range(23)
    ]
    (folder / "head.jsonl").write_text("".join(json.dumps(r) + "\n" for r in head))
    return folder


@pytest.mark.parametrize(
    "skill,proof,expected",
    [
        (True, True, ("ok", None)),
        (True, False, ("failed", "proof")),
        (False, True, ("failed", "proof")),
        (False, False, ("failed", None)),
        (None, True, ("not_counted", None)),
        (True, None, ("not_counted", None)),
    ],
)
def test_outcome(skill, proof, expected):
    assert bench.outcome(skill, proof) == expected


def test_exit_proof_and_invalid_start(tmp_path):
    folder = session(tmp_path / "leave", start="tilted")
    row = bench.judge(folder, "car.leave")
    assert row["outcome"] == "ok"
    assert row["proof"]["numbers"]["end_mode"] == "foot"
    session(folder, start="flat")
    assert bench.judge(folder, "car.leave")["outcome"] == "not_counted"


def test_walk_requires_independent_motion_and_detects_hold(tmp_path):
    folder = session(tmp_path / "walk", skill="walk_road", reason="foot:motion=going")
    assert bench.judge(folder, "foot.walk")["proof"]["ok"] is None
    session(folder, skill="walk_road", moving=True)
    assert bench.judge(folder, "foot.walk")["outcome"] == "ok"
    session(folder, skill="walk_road", moving=[False] * 4 + [True] * 19)
    assert bench.judge(folder, "foot.walk")["cause"] == "proof"


def test_enter_does_not_invent_driver_evidence(tmp_path):
    folder = session(tmp_path / "entry", end="tilted", skill="enter_vehicle")
    assert bench.judge(folder, "foot.enter")["proof"]["ok"] is None
    session(folder, skill="enter_vehicle")
    assert bench.judge(folder, "foot.enter")["cause"] == "proof"


def test_waypoint_false_success_and_unknown_legend(tmp_path):
    folder = session(tmp_path / "place", skill="set_waypoint", reason="waypoint set: Shop; gameplay observed")
    assert bench.judge(folder, "map.place")["cause"] == "proof"
    session(folder, skill="set_waypoint", route="purple")
    row = bench.judge(folder, "map.place")
    assert row["outcome"] == "not_counted"
    assert "legend" in row["exclusion"]


def test_follow_and_arrive(tmp_path):
    folder = session(tmp_path / "drive", start="tilted", end="tilted", skill="drive_route", route="purple")
    assert bench.judge(folder, "car.follow")["proof"]["ok"] is True
    assert bench.judge(folder, "car.arrive")["proof"]["ok"] is False
    log = bench.load_session(folder)
    log["play"][-1]["reading"].update(gps_distance=20, gps_speed=0)
    log["head"][-1]["sentence"] = "Not arrived."
    assert bench.prove(log, "car.arrive")["ok"] is False
    log["head"][-1]["sentence"] = "Arrived at the destination."
    assert bench.prove(log, "car.arrive")["ok"] is True


def test_cause_evidence(tmp_path):
    log = bench.load_session(session(tmp_path / "log", skill="enter_vehicle"))
    assert bench.cause("time-limit", log) == "see"
    log["head"][0]["request"]["objects"] = [{"kind": "person", "confidence": 0.9}]
    assert bench.cause("time-limit", log) == "see"
    assert bench.cause("door locked or blocked", log) == "act"
    assert bench.cause("place-not-in-legend: Shop; gameplay observed; places: X", log) == "see"
    assert bench.cause("skill-error: RuntimeError", log) == "tech"
    assert bench.cause("novel reason", log) == "unclear"
    log["head"][-1]["request"]["hud"]["health"] = 0.5
    assert bench.cause("time-limit", log) == "world"


def test_mark_is_separate_and_board_ranks(tmp_path):
    folder = session(tmp_path / "place", skill="set_waypoint")
    row = bench.judge(folder, "map.place")
    ledger = tmp_path / "bench.jsonl"
    bench.append(ledger, row)
    before = ledger.read_bytes()
    bench.main(
        ["--ledger", str(ledger), "mark", str(folder), "--outcome", "ok", "--note", "Reviewed footage"]
    )
    assert ledger.read_bytes() == before
    marked = bench.apply_marks([row], bench.read_jsonl(bench.marks_path(ledger)))
    assert marked[0]["marked"]
    data = bench.board_data([row, row, {**row, "capability": "foot.enter", "cause": "act"}])
    assert data["ranking"][0]["capability"] == "map.place"
    assert data["ranking"][0]["count"] == 2
    bench.write_board(ledger, sheets=False)
    assert "<article>" not in ledger.with_suffix(".html").read_text()  # now a pass
    assert "marked 1" in ledger.with_suffix(".html").read_text()


def test_import_idempotent_and_historical_commit_unknown(tmp_path):
    folder = session(tmp_path / "20261112-test", start="tilted")
    source = tmp_path / "basics.tsv"
    source.write_text(f"1\tleave\t{folder}\n")
    ledger = tmp_path / "bench.jsonl"
    assert len(bench.import_basics(source, ledger)) == 1
    assert bench.import_basics(source, ledger) == []
    assert bench.read_jsonl(ledger)[0]["commit"] == "unknown"


class Console:
    def __init__(self, monkeypatch, *, initial="flat", human=False, tech=False, mission=False):
        self.current = initial
        self.human = human
        self.tech = tech
        self.mission = mission
        self.active = False
        self.calls = []
        self.stops = 0
        self.polls = 0
        monkeypatch.setattr(bench, "bridge", self.bridge)
        monkeypatch.setattr(bench, "pilot", self.pilot)

    def bridge(self):
        return {
            "session_up": True,
            "recording": False,
            "human_input": self.human and self.active and len(self.calls) > 1,
        }

    def pilot(self, action, *, handle=None, plan=(), seconds=0, folder=None):
        if action == "start":
            skill = plan[0]["name"]
            self.calls.append(skill)
            end = "tilted" if skill == "enter_vehicle" else "flat" if skill == "press" else self.current
            session(
                folder,
                start=self.current,
                end=end,
                skill=skill,
                done=not self.tech,
                reason="no-frame" if self.tech else "done",
                moving=not self.tech,
                mission=self.mission,
            )
            self.current = end
            self.active, self.polls = True, 0
            return object()
        if action == "poll":
            self.polls += 1
            if self.polls == 1:
                return None
            self.active = False
            return 0
        self.stops += 1
        self.active = False
        return 0


def test_runner_produces_missing_state(monkeypatch, tmp_path):
    console = Console(monkeypatch)
    rows = bench.run(["car.leave"], 1, tmp_path / "bench.jsonl", pause=lambda _: None)
    assert console.calls == ["wait", "enter_vehicle", "press"]
    assert [r["capability"] for r in rows] == ["foot.enter", "car.leave"]
    assert rows[-1]["outcome"] == "ok"


def test_runner_stops_controller_and_excludes(monkeypatch, tmp_path):
    console = Console(monkeypatch, human=True)
    ledger = tmp_path / "bench.jsonl"
    with pytest.raises(bench.BenchStoppedError, match="Controller input"):
        bench.run(["foot.walk"], 10, ledger, pause=lambda _: None)
    assert console.stops == 1
    assert bench.read_jsonl(ledger)[0]["outcome"] == "not_counted"
    assert len(console.calls) == 2


def test_runner_three_tech_failures(monkeypatch, tmp_path):
    console = Console(monkeypatch, tech=True)
    # A failed skill with a failed independent proof is a tech failure.
    with pytest.raises(bench.BenchStoppedError, match="three consecutive tech"):
        bench.run(["foot.walk"], 10, tmp_path / "bench.jsonl", pause=lambda _: None)
    assert len(console.calls) == 4


def test_mission_guard_and_override(monkeypatch, tmp_path):
    console = Console(monkeypatch, mission=True)
    with pytest.raises(bench.BenchStoppedError, match="Mission guard"):
        bench.run(["foot.walk"], 1, tmp_path / "blocked.jsonl", pause=lambda _: None)
    assert console.calls == ["wait"]
    bench.run(["foot.walk"], 1, tmp_path / "allowed.jsonl", allow_mission=True, pause=lambda _: None)
    assert console.calls[-1] == "walk_road"


def test_harvest_separate_event_attempts(tmp_path):
    folder = session(tmp_path / "walk")
    head = bench.read_jsonl(folder / "head.jsonl")
    head[2]["request"]["hud"].update(screen="pause", wanted=1)
    head[3]["request"]["hud"].update(screen="wasted", wanted=1)
    (folder / "head.jsonl").write_text("".join(json.dumps(row) + "\n" for row in head))
    rows = bench.harvest(folder)
    assert {r["capability"] for r in rows} == {"incident.menu", "incident.down", "incident.wanted"}
    assert all(r["outcome"] == "not_counted" for r in rows)
    assert next(r for r in rows if r["capability"] == "incident.wanted")["proof"]["ok"] is True


@pytest.mark.parametrize(
    "status",
    [
        {"session_up": False, "recording": False, "human_input": False},
        {"session_up": True, "recording": True, "human_input": False},
        {"session_up": True, "recording": False, "human_input": True},
        {"session_up": True},
    ],
)
def test_preflight_never_starts_with_unsafe_or_missing_status(monkeypatch, tmp_path, status):
    console = Console(monkeypatch)
    monkeypatch.setattr(bench, "bridge", lambda: status)
    with pytest.raises(bench.BenchStoppedError):
        bench.run(["foot.walk"], 1, tmp_path / "bench.jsonl", pause=lambda _: None)
    assert console.calls == []


def test_rejudgement_revises_rates_without_rewriting_ledger(tmp_path):
    folder = session(tmp_path / "leave", start="tilted")
    first = bench.judge(folder, "car.leave")
    second = {**first, "outcome": "failed", "cause": "proof"}
    ledger = tmp_path / "bench.jsonl"
    bench.append(ledger, first)
    original = ledger.read_bytes()
    bench.append(ledger, second)
    assert ledger.read_bytes().startswith(original)
    effective = bench.apply_marks(bench.read_jsonl(ledger), [])
    assert len(effective) == 1
    assert effective[0]["outcome"] == "failed"


def test_recording_child_is_judged(monkeypatch, tmp_path):
    console = Console(monkeypatch, initial="tilted")
    base = console.pilot

    def nested(action, **kwargs):
        if action == "start":
            kwargs["folder"] = kwargs["folder"] / "recorder-created-session"
        return base(action, **kwargs)

    monkeypatch.setattr(bench, "pilot", nested)
    rows = bench.run(["car.leave"], 1, tmp_path / "bench.jsonl", pause=lambda _: None)
    assert rows[-1]["outcome"] == "ok"
    assert rows[-1]["session"].endswith("recorder-created-session")


def test_single_stale_frame_is_not_technical_failure(tmp_path):
    log = bench.load_session(session(tmp_path / "log"))
    log["play"][3]["fresh"] = False
    assert bench.cause("replaced", log) == "decide"
    log["play"][4]["fresh"] = False
    assert bench.cause("replaced", log) == "tech"


def test_map_roundtrip_reads_hud_instead_of_press_result(tmp_path):
    folder = session(tmp_path / "map")
    log = bench.load_session(folder)
    assert bench.prove(log, "map.open_close")["ok"] is False
    log["head"][2]["request"]["hud"]["screen"] = "map"
    assert bench.prove(log, "map.open_close")["ok"] is True
    log["head"] = [log["head"][0], log["head"][-1]]
    assert bench.prove(log, "map.open_close")["ok"] is None


def test_missing_late_head_reading_requires_fresh_mission_probe(tmp_path):
    log = bench.load_session(session(tmp_path / "short"))
    log["head"] = log["head"][:1]
    log["play"] = log["play"][:4]
    assert bench.state(log, end=True)["mission_known"]
    log["play"][-1]["t"] = 20
    assert not bench.state(log, end=True)["mission_known"]


def test_runnable_catalogue_plans_use_the_real_head_contract():
    from pilot.head import parse_response

    for capability in bench.CATALOGUE.values():
        if capability.plan:
            response = parse_response({"plan": list(capability.plan), "sentence": "Bench validation."})
            assert len(response.plan) == len(capability.plan)


def test_walk_to_requires_its_actual_blip_and_target_bound_distance(tmp_path):
    log = bench.load_session(session(tmp_path / "point", skill="walk_to", route="purple"))
    assert not bench.meets(bench.state(log), bench.CATALOGUE["foot.walk_to"].start)
    assert bench.prove(log, "foot.walk_to")["ok"] is None
    for row in log["play"]:
        row["reading"]["blips"] = [{"color": "yellow", "x": 10, "y": 5}]
    assert bench.meets(bench.state(log), bench.CATALOGUE["foot.walk_to"].start)
    log["play"][-1]["reading"].update(target_distance_metres=9, target_color="yellow")
    assert bench.prove(log, "foot.walk_to")["ok"] is True
