# P5: harden the recorder

Package: `remoteplay/`. Started on 10 November, ahead of the first long sessions: a recorder that gets stuck or keeps reporting "recording" would cost a whole session its record. None of these touch the path that sends inputs. An independent reviewer confirmed each point on commit `9945a67`.

After a writer thread has died, two concurrent calls of `Recorder.start()` both get through and start two writer threads on the same queue. Check again right after `await self.stop()` and raise `ConsoleError(f"already recording to {self.dir}")` when a thread is set. Test: two starts with `asyncio.gather` after a forced writer failure, exactly one succeeds and the other gets a 409.

When the writer dies before `start()` has set the frame tap, for instance because `frames.jsonl` cannot be opened, the tap stays on a dead recording and frames pile up. Call `self._abandon()` right after setting the tap when `self._failed` is set. Test: make the directory read-only after `meta.json` is written; afterwards the fake backend has no frame tap and the queue is empty.

The HTTP runner cancels a handler when the client hangs up. If that happens during the `join` in `stop()`, `_thread` stays set and the status reports "recording" forever. Move everything from the `join` on into its own coroutine and await it in `stop()` through `asyncio.shield`, keeping a reference to the task.

The check for an absolute path in `_make_dir` also hits the default directory: with a relative `PS5_CONFIG_DIR`, or one that holds a literal tilde, `record start` without `-o` fails with "dir must be an absolute path, not None". Reject only a directory the caller named, and resolve the default one.

The three newest tests in `tests/test_recorder.py` still pass when `_abandon` no longer empties `_pad` and the queue, no longer sets `_seconds`, or when `stop()` loses its check `if self._thread is not thread`. Sharpen them: record briefly before the broken frame and build a backlog, wait for the thread to end rather than for `not active`, then assert that both are empty and that the seconds in the meta match the time of death; and count that `meta.json` is written once when two stops race.

`self.agent_pad.drop` in `Daemon.latency` is untested: add a test that `latency` releases a state the loop was holding.

Still undecided, and not to be changed without Kerim: whether `POST /input {"op": "release_all"}` may interrupt the human on the gamepad. Today it calls `pad.reset()`.
