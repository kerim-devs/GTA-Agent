# P1: close two gaps on the path that sends inputs to the console

Package: `remoteplay/`. Your files: `src/ps5_remoteplay_mcp/daemon.py`, `src/ps5_remoteplay_mcp/backend/base.py`, `src/ps5_remoteplay_mcp/backend/remoteplay.py`, `src/ps5_remoteplay_mcp/backend/fake.py`, and the tests under `tests/`. Do not touch `recorder.py` and stay out of `vendor/` unless a fix is impossible without it; if so, explain why in the report.

This path is safety critical. The bridge sends every input change once, and the agent will hold the throttle through it on a live stream: an input that sticks on the console drives the car into a wall while daemon and agent both believe it was released. An independent reviewer confirmed the two gaps below and checked the fixes.

## Gap 1: a short stall can swallow a release

`Daemon._resend_input` forces a repeat of the input state only after the supervisor has observed the state "stalled", which needs a frame older than 2 s, and `backend.status()` can block for seconds during an outage. A dropout of 1.5 s can therefore swallow a release together with all its repeats.

The resender has to decide for itself from the age of the newest frame. Add a backend method `frame_ts() -> float | None` (the monotonic time of the newest decoded frame, None without one): in the `ConsoleBackend` protocol, in `RemotePlayBackend` from what its receiver already tracks, and in `FakeBackend` from `_frame_ts()`. Add a constant `FROZEN_FRAME_S = 0.3` next to `RESEND_S`. In the loop, when the state is "stalled", or the state is "up" and there is no frame or the newest frame is older than `FROZEN_FRAME_S`, set `heal_until` to now plus `RESEND_SETTLE_S`; in any state other than "up" and "stalled" skip the round as today.

Add a slow heartbeat as well, the way chiaki does it: while the session is up, the state is repeated at least every 0.3 s even when nothing is held and the picture is fresh. The console discards repeats by their sequence number, which was verified live.

Tests, in the style of the existing ones around `fake.stall_s` and `fake.resends`: with nothing held and no recent input, a stall of one second (below the supervisor's 2 s) keeps `fake.resends` growing at the resend pace, and it stops growing at that pace a moment after the frames are fresh again; with nothing held and fresh frames the heartbeat still repeats the state, at its own slow pace and not at the resend pace.

## Gap 2: `release_all` pushes a release out of the repeat window

Only the last five events are repeated (`MAX_EVENTS = 5` in the vendored controller). `RemotePlayBackend.release_all` always appends two trigger events, also when no trigger is pressed. With four buttons and R2 held, one release falls out of the window and is never repeated.

Release a trigger only when that side is pressed, the way buttons are already handled. A limit stays: more than five release events at once do not fit the window. Say so in a comment at that place.

Tests in `tests/test_remoteplay_backend.py`: with four buttons and R2 held, `release_all` produces exactly five events and all five are in the buffer that the resend repeats; with no trigger held it produces no trigger event. If `FakeBackend.release_all` records operations, keep it in step.

## Also cover what is untested today

The `force` branch of `RemotePlayBackend.resend_input` has no test: after a long quiet period `resend_input()` sends nothing and `resend_input(force=True)` sends. Add it.

## Done when

Each new test fails without its fix (show the failing output in the report) and passes with it. `.venv/bin/python tools/gate.py` in `remoteplay/` prints "gate passed"; the suite had 120 passing tests and one skipped before your change. The report lists the timing constants you chose and why, and anything in the resend path that still worries you.
