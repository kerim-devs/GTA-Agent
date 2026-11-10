"""Continuous controller state from a local control loop: the agent's virtual gamepad.

A control loop posts the whole pad state many times a second. Only what changed is sent on, the state
lives only while it is refreshed (a dead loop must not leave the car accelerating), and it is dropped
the moment the human touches the computer gamepad, the stream stalls or the session is lost.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING

from .backend import Button, ConsoleError, Side
from .gamepad import IDLE, PadState

if TYPE_CHECKING:
    from .daemon import Daemon

_LOG = logging.getLogger(__name__)
DEFAULT_TTL_MS = 250
MAX_TTL_MS = 1_000
WATCH_S = 0.02
BUSY_WAIT_S = 0.1  # how long a pad state waits behind a running button sequence before it is refused


def _stick(raw: object) -> tuple[float, float]:
    try:
        x, y = (float(v) for v in raw)  # type: ignore[union-attr]
    except TypeError:
        raise ValueError("a stick is [x, y]") from None
    if not (-1.0 <= x <= 1.0 and -1.0 <= y <= 1.0):
        raise ValueError("stick x and y must be within -1..1")
    return round(x, 2), round(y, 2)


def _trigger(raw: object) -> float:
    try:
        value = float(raw)  # type: ignore[arg-type]
    except TypeError:
        raise ValueError("a trigger is a number within 0..1") from None
    if not 0.0 <= value <= 1.0:
        raise ValueError("trigger value must be within 0..1")
    return round(value, 2)


def parse_state(body: dict) -> PadState:
    """`{"buttons": ["r1"], "left": [x, y], "right": [x, y], "l2": 0..1, "r2": 0..1}`, all optional;
    what is left out is released. y=-1 is up, as everywhere else."""
    return PadState(
        frozenset(Button(str(b).lower()) for b in body.get("buttons", ())),
        {Side.LEFT: _stick(body.get("left", (0, 0))), Side.RIGHT: _stick(body.get("right", (0, 0)))},
        {Side.LEFT: _trigger(body.get("l2", 0)), Side.RIGHT: _trigger(body.get("r2", 0))},
    )


class AgentPad:
    def __init__(self, daemon: Daemon) -> None:
        self.daemon = daemon
        self._applied = IDLE
        self._deadline = 0.0
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self.expired = 0  # times a silent control loop had its input released

    @property
    def active(self) -> bool:
        return not self._applied.idle

    @property
    def state(self) -> PadState:
        return self._applied

    def start(self) -> None:
        self._task = asyncio.create_task(self._watch())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.drop()

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(WATCH_S)
            if self.active and time.monotonic() > self._deadline:
                self.expired += 1
                _LOG.warning("control loop went silent: releasing its input")
                await self.drop()

    def _require_live(self) -> None:
        self.daemon.pad.require_agent()
        if self.daemon.state != "up":
            raise ConsoleError(f"pad state not applied: the stream is not live (state: {self.daemon.state})")

    async def set(self, state: PadState, ttl_ms: int = DEFAULT_TTL_MS) -> None:
        """Make `state` the whole controller state for the next `ttl_ms`; refresh it before then."""
        if not 0 < ttl_ms <= MAX_TTL_MS:
            raise ValueError(f"ttl_ms must be within 1..{MAX_TTL_MS}")
        self._require_live()
        async with self._lock, self.daemon.engine.stream(BUSY_WAIT_S):
            self._require_live()  # the human or a stall may have come in while this waited
            try:
                await self._apply(state)
            except Exception as err:
                await self.drop(force=True)  # sent part-way: what the console holds is unknown
                if isinstance(err, ConsoleError):
                    raise
                raise ConsoleError(f"pad state not applied: {err}") from err
            self._deadline = time.monotonic() + ttl_ms / 1000
            self.daemon.recorder.on_pad("agent", state, time.monotonic())

    async def _apply(self, state: PadState) -> None:
        backend, prev = self.daemon.backend, self._applied
        if state.buttons != prev.buttons:
            await backend.set_buttons(set(state.buttons))
        for side in Side:
            if state.sticks[side] != prev.sticks[side]:
                await backend.set_stick(side, *state.sticks[side])
            if state.triggers[side] != prev.triggers[side]:
                await backend.set_trigger(side, state.triggers[side])
        self._applied = state

    def forget(self) -> None:
        """Someone else is releasing everything: the loop's next state is sent in full again."""
        if not self._applied.idle:
            self.daemon.recorder.on_pad("agent", IDLE, time.monotonic())
        self._applied = IDLE
        self._deadline = 0.0

    async def drop(self, force: bool = False) -> None:
        """Release what the control loop holds. Not behind the lock on purpose: like
        `InputEngine.release_all`, it must work while a state is being applied."""
        if self._applied.idle and not force:
            return
        self.forget()
        try:
            await self.daemon.backend.release_all()
        except Exception:
            _LOG.exception("releasing the control loop's input failed")
