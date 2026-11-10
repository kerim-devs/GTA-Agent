Implemented P1 bridge input safety in the assigned worktree. The resender now reads the newest decoded-frame timestamp directly, heals missing or frozen video before the supervisor declares a stall, and maintains a slow idle heartbeat. ConsoleBackend, RemotePlayBackend and FakeBackend expose frame_ts(); it returns None without a frame. release_all() now releases only pressed triggers, preserving all five releases from four buttons plus R2 in the vendor's five-event window. No recorder or vendor files were changed.

RESEND_S remains 0.05 seconds and RESEND_SETTLE_S remains 0.5 seconds. FROZEN_FRAME_S is 0.3 seconds as requested. INPUT_HEARTBEAT_S is 0.25 seconds, leaving one 0.05-second polling tick before the 0.3-second heartbeat target. Frozen video extends healing every tick; fresh video returns to the slow heartbeat after settling. Failed forced sends do not advance the heartbeat timer. These are event-loop scheduling targets, not hard real-time guarantees.

Before changing production code, the new tests reproduced the defects. All commands below ran from remoteplay/. The release-window test uses the actual vendored Controller and its event buffer with a stub session, without starting controller threads or contacting a console.

```text
$ .venv/bin/python -m pytest -q tests/test_input_resender.py tests/test_remoteplay_backend.py
test_short_freeze_repeats_idle_input_then_returns_to_heartbeat: assert 0 == 20
test_fresh_idle_input_has_a_slow_heartbeat: assert 6 <= 0
test_missing_frame_or_stalled_state_keeps_healing[up-None]: assert 0 == 20
test_fake_exposes_the_current_frame_timestamp: AttributeError: 'FakeBackend' object has no attribute 'frame_ts'
test_release_all_keeps_all_five_releases_in_the_resend_window: assert 6 == 5
test_release_all_does_not_emit_an_unpressed_trigger: assert not [('event',), ('event',)]
test_frame_timestamp_is_absent_without_a_decoded_frame: AttributeError: 'RemotePlayBackend' object has no attribute 'frame_ts'
7 failed, 9 passed in 0.57s
```

The force behavior and two state-guard controls already worked before this patch, so their new tests correctly passed the baseline. To establish that these tests detect regressions, isolated Python processes removed their respective behavior in memory. No mutation was written to a repository file. This is the interpretation used for the card's requirement that each new test fail without its fix.

```python
# Run with .venv/bin/python - <<'PY' ... PY
import inspect
import textwrap
import pytest
from ps5_remoteplay_mcp.backend import remoteplay
namespace = vars(remoteplay).copy()
source = textwrap.dedent(inspect.getsource(remoteplay.RemotePlayBackend.resend_input))
assert 'held or force or' in source
exec(source.replace('held or force or', 'held or'), namespace)
remoteplay.RemotePlayBackend.resend_input = namespace['resend_input']
raise SystemExit(pytest.main(['-q', 'tests/test_remoteplay_backend.py::test_force_resends_after_a_long_quiet_period']))
```

```text
test_force_resends_after_a_long_quiet_period: assert [] == ['STATE', 'EVENT']
1 failed in 0.41s
```

```python
# Run in a separate process with .venv/bin/python - <<'PY' ... PY
import inspect
import textwrap
import pytest
from ps5_remoteplay_mcp import daemon
source = textwrap.dedent(inspect.getsource(daemon.Daemon._resend_input))
assert 'self.state == "stalled" or ' in source
assert 'if self.state not in {"up", "stalled"}:' in source
source = source.replace('self.state == "stalled" or ', '').replace('if self.state not in {"up", "stalled"}:', 'if False:')
exec(source, vars(daemon))
daemon.Daemon._resend_input = daemon._resend_input
raise SystemExit(pytest.main(['-q', 'tests/test_input_resender.py::test_missing_frame_or_stalled_state_keeps_healing[stalled-0.0]', 'tests/test_input_resender.py::test_resender_skips_sessions_that_are_not_up']))
```

```text
test_missing_frame_or_stalled_state_keeps_healing[stalled-0.0]: assert 4 == 20
test_resender_skips_sessions_that_are_not_up: assert [1, 1, 1, 1, 1, 1] == [0, 0, 0, 0, 0, 0]
2 failed in 0.06s
```

An initial state-guard mutation harness copied module globals, preventing the test clock from reaching the replacement function. That run was interrupted and is excluded from the evidence above; the corrected command uses the module's actual globals.

With the fixes in place, the targeted tests passed. Existing integration assertions were updated to expect a slow heartbeat after settling instead of complete silence. The deterministic tests observed twenty resends during twenty frozen ticks, continued healing after recovery, and heartbeat intervals of five to six ticks with fresh idle video. All five packed release events remain buffered and are repeated with the existing event sequence number. Ordinary quiet resend sends nothing; force=True still sends STATE and EVENT.

```text
$ .venv/bin/python -m pytest -q tests/test_input_resender.py tests/test_remoteplay_backend.py tests/test_agent_pad.py
38 passed in 10.02s

$ .venv/bin/python tools/gate.py
$ ruff check src tests tools
All checks passed!
$ ruff format --check src tests tools
39 files already formatted
$ pytest -q
130 passed, 1 skipped in 34.79s
gate passed
```

The final gate exceeds the card's 120-test baseline by ten passing cases. No measured test target is below the requested threshold. The required independent input-path break-it review found no blocking defect, and git diff --check passed. The timestamp accessor follows the existing status path's unlocked reads of receiver fields; it does not decode or copy video pixels.

More than five simultaneous release events still cannot fit in the resend window. Repeated packets cannot guarantee delivery during a prolonged transport outage, and scheduler delays can exceed the nominal heartbeat bound. Healing repeats the currently stored state; it does not introduce a new input cancellation policy. Existing TTL and supervisor release behavior remain responsible for cancelling held input. The next reviewer must retain those safeguards and the five-event limitation when relying on this change.

The live daemon, PS5 commands, PS5_HOST and credential directory were not accessed. Real-console packet-loss behavior, live sequence deduplication, gameplay recovery time and physical input release were not verified; the task card's reported live sequence check was not repeated. Hardware verification still requires the project's explicit authorization. Changes and this report remain uncommitted for the reviewer, as docs/tasks/README.md requires; no push or pull request was made.

## Review

The reviewer reran the checks outside the worker's sandbox: the resender tests fail on the old `daemon.py`, the two release tests fail with the unconditional trigger release put back, and the gate passes with 131 tests and one skipped. One change was added in review. The read of the frame timestamp sat outside the `try` of the resend loop, so an exception there would have ended the task for good and with it every repeat; it now sits inside, with a test that fails on the earlier version.

What stays open. More than five releases at once do not fit the repeat window. A release can also leave the window when five newer events follow it during an outage, which matters once a skill presses buttons while the loop changes the triggers. The heartbeat replays the last events for as long as they sit in the window, so a tap whose packets were all lost can arrive late instead of never. None of this was exercised against the console yet: on the next live session check that walking with the physical controller on the console stays smooth while the daemon idles next to it.
