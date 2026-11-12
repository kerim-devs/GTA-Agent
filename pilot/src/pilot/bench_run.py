"""The loop that tries the capabilities on the console by itself, and the report it leaves.

Everything that talks to the bridge or starts the pilot is in the two functions `bridge` and `pilot`;
tests replace both and nothing else here touches the console. The loop goes through the catalogue, makes
the start state a try needs by trying the capability that produces it, ends a try the moment a person
touches the controller, and survives a failed try, a pilot that dies, a bridge that does not answer and
an error of its own: those are written to the report apart from the pilot's failures, so that "the loop
did not work there" is never taken for "the pilot failed".
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import traceback
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

from . import bench
from .bench import CATALOGUE, START_STATES, Capability, plan_for, state_of, step
from .bench_proofs import Session, read_jsonl

BRIDGE_URL = "http://127.0.0.1:9395"
# The judge server and the still plan are those of lab/live/basics.sh: after its one plan the scripted
# head would follow any route it sees, so waiting plans keep it from doing anything else.
JUDGE = "http://192.168.0.248:1234=qwen/qwen3-vl-8b"
STILL = [step("wait", duration=30)]
PILOT_DIR = Path(__file__).resolve().parents[2]
RECORDINGS = Path.home() / "recordings" / "pilot"  # where `pilot.cli play` and basics.sh put sessions
OUT_OF_TIME = "the minutes ran out"
# The order of the chain: on foot, into a vehicle, a place, along the route, arrived, out, then the rest.
CHAIN_ORDER = (
    "foot.view",
    "foot.walk",
    "foot.walk_to",
    "foot.enter",
    "map.place",
    "map.mission",
    "car.follow",
    "car.arrive",
    "car.leave",
    "map.open_close",
    "chain.basic",
)
# Seconds the session's opening takes before the plan starts: the far view, then the camera levelled
# (on foot), or the opening's quick refusals (seated). Not needed where the map is the subject.
OPENING = {"foot": 25.0, "vehicle": 8.0}
MARGIN = 40.0  # seconds past its own time that a pilot gets before it is ended
OVERHEAD = 14.0  # seconds a try costs besides its own: the nudge, the start-up, the stop, the judging
NUDGE_SETTLE = 1.5
BRIDGE_SILENT = 10.0  # seconds the bridge may be silent during a try
LOOP_BROKEN = 5  # errors of the loop's own in a row that stop it
GIVE_UP = 3  # skips of one capability in a row after which the run leaves it be
NO_SESSION = 3  # tries in a row that left no session folder, after which the run stops


def bridge(path: str = "/status", payload: dict | None = None) -> dict:
    """The only place that talks to the bridge: GET /status, or POST a pad state to /pad. Tests replace it.

    It raises on anything that is not an answer, and the loop treats that as a bridge that is down."""
    url = BRIDGE_URL + path
    request = (
        Request(url)
        if payload is None
        else Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"}, method="POST")
    )
    with build_opener(ProxyHandler({})).open(request, timeout=2) as response:
        body = response.read()
    return json.loads(body) if body else {}


def pilot_command(cap: Capability | None, number: int, *, record_dir: Path, judge: str = JUDGE) -> list[str]:
    """The command line of one try, as lab/live/basics.sh runs it: the scripted head with the plan and four
    waiting plans after it, `--no-level` where the map is the subject, the judge and the record directory.
    `cap` None is a probe: a session that only waits and reads the start state."""
    plan = (step("wait", duration=2),) if cap is None else plan_for(cap, number) or tuple(STILL)
    level = cap is not None and cap.level
    args = [sys.executable, "-m", "pilot.cli", "play"]
    if not level:
        args.append("--no-level")
    args += ["--head", "scripted", "--plan", json.dumps(list(plan))]
    for _ in range(4):
        args += ["--plan", json.dumps(STILL)]
    args += ["--seconds", str(int(try_seconds(cap))), "--judge", judge, "--record-dir", str(record_dir)]
    return args


def try_seconds(cap: Capability | None) -> float:
    """How long a session lasts: the capability's own seconds, and the opening's where there is one."""
    if cap is None:
        return 3.0
    if not cap.level or cap.opening:
        return float(cap.seconds)
    return cap.seconds + (OPENING["foot"] if "foot" in cap.start else OPENING["vehicle"])


def pilot(action: str, *, handle=None, command: list[str] | None = None, log: Path | None = None):
    """The only place that starts or ends the pilot. Tests replace it.

    start: run `command` without PS5_HOST (the hardware tests' switch), output to `log`; returns the process.
    poll: the exit code of the process, None while it runs.
    interrupt: end a running process the way basics.sh does, with SIGINT, which lets the pilot let go of
    the pad and close the recording; after 25 s with SIGTERM, after 10 more with SIGKILL. Returns the exit
    code."""
    if action == "start":
        env = {key: value for key, value in os.environ.items() if key != "PS5_HOST"}
        stream = open(log, "w") if log else subprocess.DEVNULL
        try:
            return subprocess.Popen(command, cwd=PILOT_DIR, env=env, stdout=stream, stderr=subprocess.STDOUT)
        finally:
            if log:
                stream.close()
    if action == "poll":
        return handle.poll()
    if action == "interrupt":
        if handle.poll() is None:
            handle.send_signal(signal.SIGINT)
            for sig, wait in ((None, 25), (signal.SIGTERM, 10), (signal.SIGKILL, 10)):
                if sig is not None:
                    handle.send_signal(sig)
                try:
                    return handle.wait(timeout=wait)
                except subprocess.TimeoutExpired:
                    continue
        return handle.poll()
    raise ValueError(f"unknown pilot action {action!r}")


def clear(status: dict) -> bool:
    """A try starts only when the bridge says the session is up, no controller reports input and nothing
    records. Anything missing or of another type is a no."""
    return (
        isinstance(status, dict)
        and status.get("session_up") is True
        and status.get("human_input") is False
        and status.get("recording") is False
    )


def waiting_for(status: dict) -> str:
    if not isinstance(status, dict):
        return "the bridge's answer is not a status"
    if status.get("human_input") is not False:
        return (
            "a person is on the controller"
            if status.get("human_input") is True
            else "human_input is not reported"
        )
    if status.get("recording") is not False:
        return "a recording runs" if status.get("recording") is True else "recording is not reported"
    return "the session is not up" if status.get("session_up") is not True else "ready"


class LoopStoppedError(Exception):
    """The loop ends on purpose, with a message for the person who started it."""


@dataclass
class TryResult:
    folder: Path | None
    interruption: str | None = None
    exit_code: int | None = None
    log_tail: str = ""
    seconds: float = 0.0


@dataclass
class Plan:
    """One line of what the loop will do: a try, with the start state it needs."""

    number: int
    capability: str
    round: int
    needs: tuple[str, ...]
    setup: str | None = None  # the capability tried first to make a missing state
    note: str = ""


class Loop:
    def __init__(
        self,
        ids: list[str],
        ledger: Path,
        *,
        tries: int = 10,
        minutes: float | None = None,
        guard_mission: bool = False,
        record_dir: Path | None = None,
        judge: str = JUDGE,
        clock=time.monotonic,
        pause=time.sleep,
        now=lambda: datetime.now(UTC),
    ):
        self.ids = ids
        self.ledger = ledger
        self.tries, self.minutes = tries, minutes
        self.guard_mission = guard_mission
        self.record_dir = record_dir or RECORDINGS
        self.judge_url = judge
        self.clock, self.pause_for, self.now = clock, pause, now
        self.run_id = now().strftime("%Y%m%dT%H%M%S")
        self.run_dir = ledger.parent / "runs" / self.run_id
        self.status_path = ledger.parent / "bench.status.json"
        self.started = clock()
        self.deadline = None if minutes is None else self.started + minutes * 60
        self.state: dict | None = None
        self.mission: dict = {}
        self.serial: Counter = Counter()
        self.done: Counter = Counter()
        self.streak: Counter = Counter()
        self.rows: list[dict] = []
        self.ran: list[dict] = []
        self.skipped: Counter = Counter()
        self.errors: list[dict] = []
        self.pointers: list[dict] = []
        self.lines: list[str] = []
        self.state_text, self.state_since, self.current = "starting", now(), ""
        self.bridge_down_since: float | None = None
        self.broken_in_a_row = 0
        self.timed_out = False
        self.skip_streak: Counter = Counter()
        self.bare = 0
        self.given_up: dict[str, str] = {}
        self.before = self.board()
        self.stopped_because = ""

    # ---- bookkeeping
    def board(self) -> dict:
        rows = bench.apply_marks(read_jsonl(self.ledger), read_jsonl(bench.marks_path(self.ledger)))
        return bench.board_data(rows)

    def left(self) -> float | None:
        return None if self.deadline is None else self.deadline - self.clock()

    def out_of_time(self) -> bool:
        return self.deadline is not None and self.clock() >= self.deadline

    def say(self, line: str) -> None:
        stamp = self.now().strftime("%H:%M:%S")
        self.lines.append(f"{stamp} {line}")
        print(f"{stamp} {line}", flush=True)
        self.set_status(self.state_text)

    def set_status(self, text: str) -> None:
        """The status file beside the ledger: what the loop is doing, since when, and its last line, so
        that one look tells whether it lives or hangs. `updated` moves with every heartbeat."""
        if text != self.state_text:
            self.state_text, self.state_since = text, self.now()
        left = self.left()
        payload = {
            "run": self.run_id,
            "pid": os.getpid(),
            "state": self.state_text,
            "since": self.state_since.isoformat(),
            "updated": self.now().isoformat(),
            "capability": self.current,
            "tries_done": sum(self.done.values()),
            "minutes_left": None if left is None else round(max(left, 0) / 60, 1),
            "loop_errors": len(self.errors),
            "last_line": self.lines[-1] if self.lines else "",
            "report": str(self.run_dir / "report.md"),
        }
        try:
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.status_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
            os.replace(temporary, self.status_path)
        except OSError:
            pass  # a status file that cannot be written must not stop the loop

    def wait(self, seconds: float, text: str | None = None) -> None:
        if text is not None:
            self.set_status(text)
        self.pause_for(seconds)
        self.set_status(self.state_text)

    def incident(self, where: str, exc: BaseException | str, *, trace: bool = True) -> None:
        """An error of the loop or its surroundings (not a failure of the pilot), with its traceback."""
        text = (
            "".join(traceback.format_exception(exc)) if isinstance(exc, BaseException) and trace else str(exc)
        )
        self.errors.append(
            {
                "time": self.now().isoformat(),
                "where": where,
                "error": f"{type(exc).__name__}: {exc}" if isinstance(exc, BaseException) else str(exc),
                "traceback": text,
                "capability": self.current,
            }
        )
        self.say(f"loop problem at {where}: {self.errors[-1]['error']}")

    # ---- the bridge
    def ready(self) -> bool:
        """Wait until the bridge says a try may start; False when the minutes ran out first."""
        while True:
            if self.out_of_time():
                return False
            try:
                status = bridge()
                if not isinstance(status, dict):
                    raise ValueError(f"the bridge's status is not an object: {status!r}")
                if self.bridge_down_since is not None:
                    self.say("the bridge answers again")
                self.bridge_down_since = None
            except Exception as exc:
                first = self.bridge_down_since is None
                self.bridge_down_since = self.bridge_down_since or self.clock()
                if first:
                    self.incident("bridge", exc)
                self.wait(5, f"waiting: the bridge does not answer (since {self.now().strftime('%H:%M:%S')})")
                continue
            if clear(status):
                return True
            if status.get("human_input") is True:
                self.state = None  # a person played: nothing is known of where the figure stands
            self.wait(5, f"waiting: {waiting_for(status)}")

    def nudge(self) -> None:
        """A small push of the right stick ends the game's idle camera, which shows the figure from
        somewhere else after half a minute without input and misleads every reader."""
        try:
            bridge(
                "/pad",
                {"buttons": [], "left": [0, 0], "right": [0.5, 0.0], "l2": 0.0, "r2": 0.0, "ttl_ms": 250},
            )
            self.pause_for(0.3)
            bridge(
                "/pad", {"buttons": [], "left": [0, 0], "right": [0, 0], "l2": 0.0, "r2": 0.0, "ttl_ms": 250}
            )
            self.pause_for(NUDGE_SETTLE)
        except Exception as exc:
            self.incident("nudge", exc)

    def scramble(self, number: int) -> int:
        """Presses of the touchpad before a view try, so that tries begin in different views."""
        presses = 1 + number % 3
        try:
            for _ in range(presses):
                bridge(
                    "/pad",
                    {
                        "buttons": ["touchpad"],
                        "left": [0, 0],
                        "right": [0, 0],
                        "l2": 0.0,
                        "r2": 0.0,
                        "ttl_ms": 250,
                    },
                )
                self.pause_for(0.15)
                bridge(
                    "/pad",
                    {"buttons": [], "left": [0, 0], "right": [0, 0], "l2": 0.0, "r2": 0.0, "ttl_ms": 250},
                )
                self.pause_for(1.6)
        except Exception as exc:
            self.incident("scramble", exc)
            return 0
        return presses

    # ---- one session
    def sessions(self) -> set[str]:
        return {p.name for p in self.record_dir.glob("[0-9]" * 8 + "-*") if p.is_dir()}  # 20261112-143047

    def fits(self, cap: Capability | None) -> bool:
        """A try starts only if it can end before the minutes are used up."""
        left = self.left()
        return left is None or left >= try_seconds(cap) + OVERHEAD

    def execute(self, cap: Capability | None, number: int) -> TryResult:
        if not self.fits(cap) or not self.ready():
            self.timed_out = True
            return TryResult(None, OUT_OF_TIME)
        self.nudge()
        scrambled = self.scramble(number) if cap is not None and cap.scramble else 0
        if not self.ready():
            self.timed_out = True
            return TryResult(None, OUT_OF_TIME)
        before = self.sessions()
        name = "probe" if cap is None else cap.id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        log = self.run_dir / f"pilot-{len(self.ran) + 1:03d}-{name}.log"
        command = pilot_command(cap, number, record_dir=self.record_dir, judge=self.judge_url)
        started = self.clock()
        handle = pilot("start", command=command, log=log)
        limit = started + try_seconds(cap) + MARGIN
        interruption = None
        silent_since = None
        try:
            while pilot("poll", handle=handle) is None:
                try:
                    status = bridge()
                except Exception:
                    status = None
                if status is not None and status.get("human_input") is True:
                    interruption = "human input"
                    break
                if status is None or status.get("session_up") is not True:
                    silent_since = silent_since if silent_since is not None else self.clock()
                    if self.clock() - silent_since >= BRIDGE_SILENT:
                        interruption = "bridge not answering"
                        break
                else:
                    silent_since = None
                if self.clock() > limit:
                    interruption = "the pilot did not end in time"
                    break
                self.set_status(f"trying {name}, {self.clock() - started:.0f} s of {try_seconds(cap):.0f}")
                self.pause_for(0.5)
        finally:
            code = pilot("poll", handle=handle)
            if code is None:
                code = pilot("interrupt", handle=handle)
        found = sorted(self.sessions() - before)
        folder = None
        if len(found) == 1:
            folder = self.record_dir / found[0]
        elif len(found) > 1:
            self.incident(
                "session",
                f"{len(found)} new session folders appeared during the try; cannot tell which is this "
                f"one: {found}",
                trace=False,
            )
        tail = ""
        try:
            tail = log.read_text()[-1500:]
        except OSError:
            pass
        result = TryResult(folder, interruption, code, tail, self.clock() - started)
        if scrambled:
            self.say(f"{name}: began after {scrambled} touchpad press(es)")
        return result

    def probe(self) -> None:
        """A session that only waits reads where the figure stands and whether an objective shows."""
        self.current = "probe"
        self.set_status("reading the start state")
        result = self.execute(None, 0)
        if result.interruption == OUT_OF_TIME:
            self.state = None
            return
        record = {
            "capability": "probe",
            "session": str(result.folder) if result.folder else None,
            "interruption": result.interruption,
        }
        self.ran.append(record)
        if result.folder is None or result.interruption:
            self.state = None
            if result.interruption != "human input":
                self.say(f"the state probe gave no session ({result.interruption or 'no folder'})")
            return
        session = Session(result.folder)
        try:
            self.state = state_of(session, end=True)
            self.mission = bench.mission_signs(session)
            record["state"] = dict(self.state)
        finally:
            session.close()
        self.say(
            "state: "
            + ", ".join(
                f"{k} {'yes' if v else 'no' if v is False else '?'}"
                for k, v in self.state.items()
                if k in ("foot", "vehicle", "route")
            )
        )

    # ---- one try, and the state it needs
    def mission_active(self) -> bool:
        return bool(self.mission.get("active"))

    def prepare(self, cap: Capability, depth: int = 0) -> str | None:
        """Make the start state; the reason it cannot be made, or None when it holds."""
        if self.state is None:
            self.probe()
        state = self.state or {}
        for needed in cap.start:
            if state.get(needed) is True:
                continue
            definition = START_STATES[needed]
            if definition.producer is None or depth >= 2:
                return (
                    f"the start state `{needed}` is missing ({definition.text}) and nothing in the "
                    "catalogue makes it"
                )
            opposite = {"foot": "vehicle", "vehicle": "foot"}.get(needed)
            if opposite and state.get(opposite) is not True:
                self.probe()
                state = self.state or {}
                if state.get(opposite) is not True and state.get(needed) is not True:
                    return (
                        f"the start state `{needed}` is not clear (the minimap and the judge disagree) "
                        "and a producer must not press blind"
                    )
                if state.get(needed) is True:
                    continue
            producer = CATALOGUE[definition.producer]
            reason = self.prepare(producer, depth + 1)
            if reason:
                return reason
            self.say(f"{cap.id} needs `{needed}`: trying {producer.id} first")
            self.try_once(producer, setup_for=cap.id)
            if self.timed_out:
                return OUT_OF_TIME
            state = self.state or {}
            if state.get(needed) is not True:
                return f"{producer.id} did not make `{needed}` for {cap.id}"
        if self.guard_mission:
            while self.mission_active() and not self.out_of_time():
                self.wait(30, "waiting: an objective is on the screen (mission guard)")
                self.probe()
            if self.mission_active():
                return "an objective stayed on the screen until the minutes ran out (mission guard)"
        return None

    def try_once(self, cap: Capability, *, setup_for: str | None = None) -> dict | None:
        number = self.serial[cap.id]
        self.serial[cap.id] += 1
        self.current = cap.id
        self.set_status(f"trying {cap.id} (try {number + 1})")
        code = bench.version()
        result = self.execute(cap, number)
        if result.interruption == OUT_OF_TIME:
            self.serial[cap.id] -= 1
            return None
        record = {
            "capability": cap.id,
            "number": number + 1,
            "setup_for": setup_for,
            "session": str(result.folder) if result.folder else None,
            "interruption": result.interruption,
            "exit_code": result.exit_code,
            "seconds": round(result.seconds, 1),
        }
        self.ran.append(record)
        if result.exit_code not in (0, None) and not result.interruption:
            self.incident(
                "pilot",
                f"the pilot process ended with exit code {result.exit_code}; its output ended: "
                f"{result.log_tail[-600:]!r}",
                trace=False,
            )
        if result.folder is None:
            record["outcome"] = "no session"
            self.state = None
            if result.interruption and result.interruption != "human input":
                self.incident("try", f"{cap.id}: no session folder ({result.interruption})", trace=False)
            elif not result.interruption:
                self.incident(
                    "session",
                    f"{cap.id}: the pilot ended (exit code {result.exit_code}) and left no session folder",
                    trace=False,
                )
                self.bare += 1
                if self.bare >= NO_SESSION:
                    raise LoopStoppedError(
                        f"{NO_SESSION} tries in a row left no session folder; the loop stops."
                    )
            return None
        self.bare = 0
        session = Session(result.folder)
        try:
            row = bench.judge(result.folder, cap.id, code=code, session=session)
            row["run"] = self.run_id
            if setup_for:
                row["setup_for"] = setup_for
            if result.interruption:
                row["interruption"] = result.interruption
            if result.interruption == "human input":
                row.update(
                    outcome="not_counted",
                    cause=None,
                    exclusion="a person took the controller; the pilot was stopped",
                )
                row["moment"] = None
            elif result.interruption == "bridge not answering":
                row.update(
                    outcome="not_counted", cause=None, exclusion="the bridge stopped answering during the try"
                )
                row["moment"] = None
            bench.append(self.ledger, row)
            self.rows.append(row)
            for incident in bench.harvest(result.folder, code=code):
                bench.append(self.ledger, incident)
            record["outcome"], record["cause"] = row["outcome"], row["cause"]
            self.state = None if result.interruption == "human input" else state_of(session, end=True)
            self.mission = bench.mission_signs(session)
            if row["outcome"] == "failed":
                self.pointers.append(build_pointer(row, session, self.run_dir, len(self.pointers) + 1))
            self.say(
                f"{cap.id} try {number + 1}: {row['outcome']}"
                + (
                    f" ({row['cause']}: {bench.reason_stem(row['skill_reason'])})"
                    if row["outcome"] == "failed"
                    else ""
                )
                + (f", {row['exclusion']}" if row["outcome"] == "not_counted" and row["exclusion"] else "")
            )
        finally:
            session.close()
        if result.interruption not in ("human input", "bridge not answering"):
            self.done[cap.id] += 1
        self.streak[cap.id] = (
            self.streak[cap.id] + 1 if row["outcome"] == "failed" and row["cause"] == "tech" else 0
        )
        if self.streak[cap.id] >= 3:
            raise LoopStoppedError(
                f"{cap.id}: three tries in a row failed for a technical cause; the loop stops."
            )
        self.write_report()
        return row

    def attempt(self, name: str) -> None:
        cap = CATALOGUE[name]
        self.timed_out = False
        reason = self.prepare(cap)
        if reason and self.timed_out:
            return  # the minutes are over; that is no reason to report
        if reason:
            self.skipped[(name, reason)] += 1
            self.skip_streak[name] += 1
            self.say(f"skipped {name}: {reason}")
            if self.skip_streak[name] >= GIVE_UP:
                self.given_up[name] = reason
                self.say(f"{name} is left be: skipped {GIVE_UP} times in a row")
            return
        self.skip_streak[name] = 0
        self.try_once(cap)

    # ---- the run
    def order(self) -> list[str]:
        return list(self.ids)

    def run(self) -> str:
        self.say(
            f"run {self.run_id}: {', '.join(self.ids)}; up to {self.tries} tries each"
            + (f", {self.minutes:g} minutes" if self.minutes else "")
        )
        try:
            while True:
                if self.out_of_time():
                    self.stopped_because = "the minutes were used up"
                    break
                todo = [
                    name
                    for name in self.order()
                    if self.done[name] < self.tries and name not in self.given_up
                ]
                if not todo:
                    self.stopped_because = (
                        "every capability had its tries"
                        if not self.given_up
                        else "what was left could not be tried: "
                        + ", ".join(f"{n} (skipped {GIVE_UP} times in a row)" for n in self.given_up)
                    )
                    break
                round_began = len(self.ran)
                for name in todo:
                    if self.out_of_time():
                        break
                    self.guarded(name)
                if (
                    len([r for r in self.ran[round_began:] if r["capability"] != "probe"]) == 0
                    and not self.out_of_time()
                ):
                    self.stopped_because = (
                        "the minutes were used up: no try fits in what is left"
                        if self.timed_out
                        else "nothing could be tried in a whole round: every capability was skipped"
                    )
                    break
        except LoopStoppedError as stop:
            self.stopped_because = str(stop)
            self.say(str(stop))
        except KeyboardInterrupt:
            self.stopped_because = "stopped by the person who started it"
            self.say(self.stopped_because)
        finally:
            self.current = ""
            self.set_status("finished: " + (self.stopped_because or "ended"))
            summary = self.write_report(final=True)
        self.say(summary)
        return summary

    def guarded(self, name: str) -> None:
        """One try of a capability that an error of the loop itself cannot end the run with."""
        try:
            self.attempt(name)
            self.broken_in_a_row = 0
        except (LoopStoppedError, KeyboardInterrupt):
            raise
        except Exception as exc:
            self.broken_in_a_row += 1
            self.incident(f"try of {name}", exc)
            self.state = None
            if self.broken_in_a_row >= LOOP_BROKEN:
                raise LoopStoppedError(
                    f"the loop itself failed {LOOP_BROKEN} times in a row; it stops."
                ) from exc
            self.wait(5, "waiting after an error of the loop")

    # ---- the report
    def summary(self) -> str:
        ran = self.rows
        counted = [r for r in ran if r["outcome"] != "not_counted"]
        failed = [r for r in ran if r["outcome"] == "failed"]
        minutes = (self.clock() - self.started) / 60
        text = (
            f"{len(ran)} tries in {minutes:.0f} minutes, {sum(r['outcome'] == 'ok' for r in ran)} ok, "
            f"{len(failed)} failed, {len(ran) - len(counted)} not counted"
        )
        if failed:
            per = Counter(r["capability"] for r in failed)
            worst, number = max(
                per.items(),
                key=lambda item: (
                    item[1],
                    -sum(r["outcome"] == "ok" for r in ran if r["capability"] == item[0]),
                ),
            )
            causes = Counter(r["cause"] for r in failed)
            text += (
                f"; worst capability {worst} with {number} failure(s); "
                f"most frequent cause `{causes.most_common(1)[0][0]}` ({causes.most_common(1)[0][1]} of "
                f"{len(failed)})"
            )
        else:
            text += "; no failures"
        if self.errors:
            text += f"; {len(self.errors)} problem(s) of the loop itself (see the report)"
        return text + f". Stopped: {self.stopped_because or 'still running'}."

    def write_report(self, final: bool = False) -> str:
        summary = self.summary()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        after = self.board()
        data = {
            "run": self.run_id,
            "final": final,
            "options": {
                "capabilities": self.ids,
                "tries": self.tries,
                "minutes": self.minutes,
                "guard_mission": self.guard_mission,
            },
            "stopped": self.stopped_because,
            "planned": [{"capability": name, "tries": self.tries} for name in self.ids],
            "ran": self.ran,
            "skipped": [{"capability": n, "reason": r, "times": c} for (n, r), c in self.skipped.items()],
            "loop_errors": self.errors,
            "board_before": _board_view(self.before),
            "board_after": _board_view(after),
            "failures": self.pointers,
            "summary": summary,
        }
        (self.run_dir / "report.json").write_text(json.dumps(data, indent=1, ensure_ascii=False))
        (self.run_dir / "report.md").write_text(report_markdown(data))
        return summary


def _board_view(board: dict) -> list[dict]:
    return [
        {
            "capability": c["id"],
            "state": c["state"],
            "last10": c["last10"],
            "all": c["all"],
            "not_counted": c["excluded"],
            "causes": c["causes"],
        }
        for c in board["capabilities"]
    ]


# ---- what a failure points at
def _snapshot(session: Session, t: float) -> dict:
    """What the readers logged at second `t`: the nearest tick, the skill running, the head's last HUD and
    objective, the judge's last answers."""
    ticks = [row for row in session.play if row["t"] <= t]
    tick = ticks[-1] if ticks else (session.play[0] if session.play else {})
    reading = tick.get("reading") or {}
    skill = tick.get("skill") or {}
    requests = [r for r in session.requests if r["t"] <= t]
    judged = [(jt, answers) for jt, answers in session.judgments if jt <= t]
    judgment = {}
    if judged:
        answers = judged[-1][1]
        judgment = {
            key: (answers.get(key) or {}).get("value")
            for key in ("mode", "overlay", "banner", "wanted", "path", "car")
        }
        judgment["age_s"] = round(t - judged[-1][0], 2)
    return {
        "tick_at": round(tick.get("t", 0.0), 2),
        "minimap": {k: reading.get(k) for k in ("minimap", "route", "gps_distance", "arrow", "corrupt")},
        "blips": [f"{b.get('color')}@({b.get('x')},{b.get('y')})" for b in reading.get("blips", [])][:5],
        "skill": {
            "name": skill.get("name"),
            "status": skill.get("status"),
            "reason": str(skill.get("reason"))[:100],
        },
        "hud": (requests[-1].get("hud") if requests else None),
        "objective": (requests[-1].get("objective") if requests else None),
        "judge": judgment,
    }


PIECE_HINTS = {
    "view_far_at_end": (
        "the figure's box at that second against the far band (height 0.23 to 0.345 of the frame, "
        "feet 0.66 to 0.86)"
    ),
    "seated_at_end": "the minimap class and the judge's mode at that second: which one matches the picture",
    "seated_within": "the minimap class and the judge's mode from the start: when does the figure sit",
    "on_foot_at_end": "the minimap class and the judge's mode at that second: which one matches the picture",
    "waypoint_changed": (
        "the minimap's rim for the purple blip before the map opens and at the end, then the pad log for "
        "a second cross"
    ),
    "game_back": "the HUD screen at the end: what is left open",
    "map_opened": "the HUD screen over the try: did a menu open at all",
    "distance_fell": "gps_distance in play.jsonl over the first 30 s of readings",
    "never_held": "gps_distance in play.jsonl where it stands still",
    "arrived": "gps_distance and the vehicle's speed at the last reading",
    "moving_on_most_ticks": "the movement field in play.jsonl",
}


def build_pointer(row: dict, session: Session, run_dir: Path, number: int) -> dict:
    """What saves the search for a failure: where it went wrong, what the readers said then against what
    the proof saw, the picture of that moment, and one line on where to look first."""
    import cv2

    moment = row.get("moment") or {"t": session.end, "how": "the end of the session"}
    t = float(moment["t"])
    picture = None
    frame = session.frame(t)
    if frame is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"failure-{number:02d}-{row['capability']}.jpg"
        small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), (640, 360), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(path), small, [cv2.IMWRITE_JPEG_QUALITY, 80])
        picture = path.name
    failing = next((name for name, ok in (row["proof"].get("parts") or {}).items() if ok is False), None)
    piece = (failing or "").split("[")[0]
    look = bench.LOOK_FIRST[row["cause"] or "unclear"]
    if piece in PIECE_HINTS:
        look = f"{PIECE_HINTS[piece]}; {look}"
    video = Path(row["session"]) / "video.mp4"
    return {
        "capability": row["capability"],
        "cause": row["cause"],
        "skill_reason": row["skill_reason"],
        "session": row["session"],
        "second": round(t, 2),
        "how_found": moment["how"],
        "readers_said": _snapshot(session, t),
        "proof_saw": {
            "ok": row["proof"]["ok"],
            "parts": row["proof"].get("parts"),
            "numbers": row["proof"]["numbers"],
        },
        "picture": picture,
        "look_first": f"Look first at {video} at {t:.1f} s: {look}.",
    }


def _board_cell(row: dict) -> str:
    return (
        f"{row['state']}, last ten {row['last10'][0]}/{row['last10'][1]}, all {row['all'][0]}/{row['all'][1]}"
    )


def report_markdown(data: dict) -> str:
    out = [f"# Bench run {data['run']}", "", data["summary"], ""]
    options = data["options"]
    out += [
        "## What was planned",
        "",
        f"Capabilities {', '.join(options['capabilities'])}, up to {options['tries']} tries each"
        + (f", {options['minutes']:g} minutes" if options["minutes"] else "")
        + f"; mission guard {'on' if options['guard_mission'] else 'off'}. "
        f"The loop stopped: {data['stopped'] or 'still running'}.",
        "",
        "## What ran",
        "",
        "| # | Capability | Try | Session | Outcome | Cause | Seconds | Note |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, item in enumerate(data["ran"], 1):
        note = item.get("interruption") or (f"setup for {item['setup_for']}" if item.get("setup_for") else "")
        out.append(
            f"| {index} | {item['capability']} | {item.get('number', '')} | {item.get('session') or '-'} | "
            f"{item.get('outcome', '')} | {item.get('cause') or ''} | {item.get('seconds', '')} | {note} |"
        )
    out += ["", "## What was skipped, and why", ""]
    out += [f"- {s['capability']} ({s['times']} times): {s['reason']}" for s in data["skipped"]] or [
        "Nothing was skipped."
    ]
    out += ["", "## Problems of the loop itself (not failures of the pilot)", ""]
    if data["loop_errors"]:
        for error in data["loop_errors"]:
            out += [
                f"- {error['time']} at {error['where']}: {error['error']}",
                "",
                "```",
                error["traceback"].rstrip(),
                "```",
                "",
            ]
    else:
        out.append("None.")
    out += ["", "## The board before and after", "", "| Capability | Before | After |", "| --- | --- | --- |"]
    after = {c["capability"]: c for c in data["board_after"]}
    for before in data["board_before"]:
        later = after[before["capability"]]
        out.append(f"| {before['capability']} | {_board_cell(before)} | {_board_cell(later)} |")
    out += ["", "## Failures, each with where to look", ""]
    for number, failure in enumerate(data["failures"], 1):
        said = failure["readers_said"]
        out += [
            f"### {number}. {failure['capability']}: {failure['cause']} ({failure['skill_reason']})",
            "",
            f"- Session: {failure['session']}",
            f"- Went wrong at {failure['second']} s of the video. Found by: {failure['how_found']}.",
            f"- The readers said then: minimap {said['minimap']}, blips {said['blips']}, "
            f"skill {said['skill']}, HUD {said['hud']}, objective {said['objective']!r}, "
            f"judge {said['judge']}.",
            f"- The proof saw: {json.dumps(failure['proof_saw'], ensure_ascii=False)}",
            f"- Picture: {failure['picture'] or 'none (no video)'}",
            f"- {failure['look_first']}",
            "",
        ]
    out += ["", data["summary"], ""]
    return "\n".join(out)


# ---- the dry run: what the loop would do, try by try
def plan_lines(
    ids: list[str], tries: int, minutes: float | None, *, assume: str = "foot", guard_mission: bool = False
) -> list[str]:
    """What the loop would do, with the start state each try needs. A model of the states stands in for
    the console: it begins as `assume` says and changes as the entries' `ends` say. Touches nothing."""
    state = {
        "foot": assume == "foot",
        "vehicle": assume == "vehicle",
        "route": False,
        "route_far": False,
        "route_near": False,
        "game": True,
        "yellow_target": False,
        "behind": False,
    }
    lines = [
        f"Dry run: {', '.join(ids)}; up to {tries} tries each"
        + (f", {minutes:g} minutes" if minutes else "")
        + f"; mission guard {'on' if guard_mission else 'off'}. Nothing is touched.",
        "First a session that only waits reads the start state; "
        f"the lines below assume the figure is {assume}.",
        "Before every try a small push of the right stick ends the game's idle camera, and a try starts "
        "only when the bridge reports session_up, no human input and no recording.",
        "",
    ]
    budget = None if minutes is None else minutes * 60
    used = 0.0
    done: Counter = Counter()
    number = 0
    skipped: set[str] = set()

    def show(name: str, setup_for: str | None = None) -> bool:
        nonlocal used, number
        cap = CATALOGUE[name]
        cost = try_seconds(cap) + OVERHEAD
        if budget is not None and used + cost > budget + 1:
            return False
        number += 1
        used += cost
        needs = ", ".join(f"{n} ({'held' if state.get(n) else 'missing'})" for n in cap.start) or "nothing"
        how = (
            "the session's opening"
            if cap.opening
            else json.dumps(
                [f"{s['name']} {s['args']}" for s in plan_for(cap, done[name])], ensure_ascii=False
            )
        )
        lines.append(
            f"{number:3d}. {name:<15} round {done[name] + 1:<2} start: {needs}; {how}; about {cost:.0f} s"
            + (f"; made for {setup_for}" if setup_for else "")
            + ("; presses the touchpad first" if cap.scramble else "")
        )
        done[name] += 1
        for key, value in cap.ends:
            state[key] = value
        if dict(cap.ends).get("route"):
            # the game draws a route only while the figure sits in a vehicle; the model takes its length
            # as fitting
            state["route"] = state["route_far"] = state["route_near"] = bool(state["vehicle"])
        if dict(cap.ends).get("vehicle") is False:
            state["route"] = state["route_far"] = state["route_near"] = False
        return True

    def ready(name: str, depth: int = 0) -> bool:
        cap = CATALOGUE[name]
        for needed in cap.start:
            if state.get(needed):
                continue
            producer = START_STATES[needed].producer
            if producer is None or depth >= 2:
                if name not in skipped:
                    skipped.add(name)
                    lines.append(
                        f"     {name} is skipped: `{needed}` is missing and nothing in the catalogue "
                        f"makes it ({START_STATES[needed].text})"
                    )
                return False
            if not ready(producer, depth + 1):
                return False
            if not show(producer, setup_for=name):
                return False
            if not state.get(needed):
                lines.append(f"     {name} is skipped: {producer} would not leave `{needed}` in the model")
                return False
        return True

    while True:
        todo = [n for n in ids if done[n] < tries and n not in skipped]
        if not todo:
            break
        progressed = False
        for name in todo:
            if ready(name):
                if not show(name):
                    todo = []
                    break
                progressed = True
        if not progressed:
            break
        if budget is not None and used + 20 > budget:
            break
    lines.append("")
    lines.append(
        f"About {used / 60:.0f} minutes for {number} sessions"
        + (f" of the {minutes:g} available." if minutes else ".")
    )
    return lines


def resolve(names: list[str]) -> list[str]:
    """`all` is the catalogue's runnable capabilities in the order of the chain."""
    ids: list[str] = []
    for name in names:
        if name == "all":
            ids += [n for n in CHAIN_ORDER if CATALOGUE[n].runnable]
            ids += [c.id for c in CATALOGUE.values() if c.runnable and c.id not in CHAIN_ORDER]
        elif name in CATALOGUE:
            cap = CATALOGUE[name]
            if not cap.runnable:
                raise ValueError(
                    f"{name} cannot be run alone: "
                    + (
                        "not built"
                        if not cap.built
                        else "harvested from other sessions"
                        if cap.harvested
                        else "no plan"
                    )
                )
            ids.append(name)
        else:
            raise ValueError(f"unknown capability {name!r}; known: {', '.join(CATALOGUE)}, all")
    return list(dict.fromkeys(ids))


def main_run(args) -> int:
    try:
        ids = resolve(args.capabilities)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.tries < 1:
        print("--tries must be at least 1", file=sys.stderr)
        return 2
    if args.dry:
        print(
            "\n".join(
                plan_lines(
                    ids, args.tries, args.minutes, assume=args.assume, guard_mission=args.guard_mission
                )
            )
        )
        return 0
    loop = Loop(
        ids,
        args.ledger,
        tries=args.tries,
        minutes=args.minutes,
        guard_mission=args.guard_mission,
        record_dir=args.record_dir,
        judge=args.judge or JUDGE,
    )
    loop.run()
    print(f"Report: {loop.run_dir / 'report.md'}")
    return 0 if not loop.stopped_because.startswith(("three tries", "the loop itself")) else 1
