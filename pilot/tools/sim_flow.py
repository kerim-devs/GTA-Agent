"""Offline screen machine with delayed controls, late reads and transient errors."""

import json
from dataclasses import asdict

from pilot.contract import Hud, Reading
from pilot.flow import Flow
from pilot.skills import Observation

READING = Reading("tilted", "purple", 0.0, 0.0, 0.0, False, 1.0)
STEP = 0.05
CONTROL_DELAY = 0.14


def simulate(initial: str, *, read_delay: int, stuck: bool = False) -> dict:
    flow = Flow(response_timeout=0.7, wait_timeout=3)
    actual = "game"
    history = []
    pending = None
    entered = 0.0
    trace = []
    presses = []
    events = []
    recovered = False
    wrong_reads = 0
    held = False
    for tick in range(120):
        now = round(tick * STEP, 6)
        if tick == 10:
            actual, entered = initial, now
        if pending and now >= pending[0]:
            actual, entered = pending[1], now
            pending = None
        if not stuck and actual in {"passed", "loading", "wasted", "busted"} and now - entered >= 0.6:
            actual, entered = "game", now
        history.append(actual)
        read = history[max(0, tick - read_delay)]
        # A false failure during normal play, then a false game during an active screen.
        wrong = tick in {3, 18}
        if wrong:
            read = "failed" if tick == 3 else "game"
            wrong_reads += 1
        text = "Retry X" if read == "failed" else "Close Circle"
        result = flow.tick(Observation(READING, True, now, hud=Hud(screen=read)), text)
        if result:
            assert result.pad.left == result.pad.right == (0, 0)
            assert result.pad.l2 == result.pad.r2 == 0
            assert not {"l1", "r1"} & set(result.pad.buttons)
            if wrong:
                assert not result.pad.buttons, "a one-tick wrong read caused a press"
            events.extend(result.events)
            # A press spans several ticks; count it once, where it starts.
            if result.pad.buttons and not held:
                presses.append({"time": now, "screen": actual, "button": result.pad.buttons[0]})
            if result.pad.buttons or result.events:
                trace.append(
                    {
                        "time": now,
                        "actual": actual,
                        "read": read,
                        "action": result.action,
                        "buttons": result.pad.buttons,
                        "events": result.events,
                    }
                )
            if not stuck and pending is None:
                destination = None
                if actual == "failed" and result.pad.buttons == ("cross",):
                    destination = "loading"
                elif actual == "map" and result.pad.buttons == ("circle",):
                    destination = "pause"
                elif actual in {"pause", "phone"} and result.pad.buttons == ("circle",):
                    destination = "game"
                elif actual == "weapon_wheel" and result.action == "release":
                    destination = "game"
                if destination:
                    pending = (now + CONTROL_DELAY, destination)
        elif tick > 10 and actual == "game" and pending is None:
            recovered = True
        held = bool(result and result.pad.buttons)
    assert wrong_reads == 2
    if stuck:
        assert sum(event["kind"] == "stuck" for event in events) == 1
        # One press, one more when the picture does not change, then the head is told.
        assert len(presses) == 2
        assert not recovered
    else:
        assert recovered, (initial, read_delay, trace)
        assert not any(event["kind"] == "stuck" for event in events)
        assert len(presses) == {"failed": 1, "map": 2, "pause": 1, "phone": 1}.get(initial, 0)
    return {
        "screen": initial,
        "read_delay_ticks": read_delay,
        "stuck": stuck,
        "recovered": recovered,
        "wrong_reads_without_press": wrong_reads,
        "trace": trace,
    }


def simulate_conductor(out, initial="failed", *, read_delay=0, stuck=False):
    """Exercise the real conductor against a delayed, button-driven screen machine."""
    import json
    from concurrent.futures import Future

    import numpy as np

    from pilot.conductor import Conductor
    from pilot.head import parse_response
    from pilot.scene import SceneText

    class Head:
        def decide(self, request):
            return parse_response(
                {
                    "plan": [{"name": "walk", "args": {"y": -0.6, "duration": 30}}],
                    "sentence": "Ich gehe weiter.",
                }
            )

    class NoEvents:
        def update(self, *args, **kwargs):
            return []

    jobs = []
    now = 0.0

    def submit(function, *args):
        future = Future()
        jobs.append((now + 0.2, future, function, args))
        return future

    conductor = Conductor(
        out,
        head=Head(),
        notebook=out / "notebook.txt",
        flow=Flow(),
        detector=NoEvents(),
        submit=submit,
        clock=lambda: now,
    )
    conductor.runner.replace(Head().decide(None).plan)
    conductor.pending.clear()
    conductor.last_request_time = 0
    conductor.head_latency = 0
    rgb = np.zeros((720, 1280, 3), dtype=np.uint8)
    reading = Reading("flat", None, None, None, None, False, 1)
    actual, changed, pending = "game", 0.0, None
    history, trace, presses = [], [], []
    held = ()
    try:
        for index in range(80):
            now = round(index * STEP, 6)
            if index == 10:
                actual, changed = initial, now
            if pending is not None and now >= pending[0]:
                actual, changed = pending[1], now
                pending = None
            if actual in {"loading", "passed", "wasted", "busted"} and now - changed >= 0.6 and not stuck:
                actual, changed = "game", now
            history.append(actual)
            screen = history[max(0, index - read_delay)]
            for due, future, function, args in jobs:
                if due <= now and not future.done():
                    future.set_result(function(*args))
            result = conductor.tick(
                Observation(reading, True, now, hud=Hud(screen=screen)),
                rgb,
                text=SceneText(help="Retry X" if screen == "failed" else ""),
            )
            pad = result.pad
            if pad.buttons and pad.buttons != held:
                presses.append({"t": now, "screen": actual, "buttons": list(pad.buttons)})
                destination = (
                    "loading"
                    if actual == "failed" and "cross" in pad.buttons
                    else "pause"
                    if actual == "map" and "circle" in pad.buttons
                    else "game"
                    if actual in {"pause", "phone"} and "circle" in pad.buttons
                    else None
                )
                if destination and not stuck:
                    pending = (now + CONTROL_DELAY, destination)
            if (
                actual == "weapon_wheel"
                and conductor.flow_result is not None
                and pending is None
                and not stuck
            ):
                pending = (now + CONTROL_DELAY, "game")
            held = pad.buttons
            trace.append(
                {
                    "t": now,
                    "screen": screen,
                    "actual": actual,
                    "skill": conductor.describe(result),
                    "pad": asdict(pad),
                }
            )
    finally:
        conductor.close()
    rows = [json.loads(line) for line in (out / "head.jsonl").read_text().splitlines()]
    report = {
        "initial": initial,
        "read_delay": read_delay,
        "presses": presses,
        "requests": [row for row in rows if row["type"] == "request"],
        "flow": [row for row in rows if row["type"].startswith("flow_")],
        "trace": trace,
    }
    (out / "simulation.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    scenarios = [
        simulate(screen, read_delay=delay)
        for delay in (0, 2, 4)
        for screen in (
            "failed",
            "passed",
            "loading",
            "pause",
            "map",
            "phone",
            "weapon_wheel",
            "wasted",
            "busted",
        )
    ]
    scenarios.extend(simulate("failed", read_delay=delay, stuck=True) for delay in (0, 2, 4))
    print(
        json.dumps(
            {
                "control_delay_seconds": CONTROL_DELAY,
                "tick_seconds": STEP,
                "passed_scenarios": len(scenarios),
                "scenarios": scenarios,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
