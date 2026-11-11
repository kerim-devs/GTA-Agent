"""Offline screen machine with delayed controls, late reads and transient errors."""

import json

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
        assert len(presses) == 1
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
