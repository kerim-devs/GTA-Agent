This is an offline first-reaction bench. It reads source recordings without changing them and never opens the console bridge. Run commands from `pilot/`. `scenes.json` contains the reviewed recording references, native-frame onsets, shared answer sets and human alignment evidence. `tools/reaction.py scenes --sheets` regenerates the contact sheets. The retained set is nine threats and three playable on-foot controls, below the intended thirty plus thirty. Rejected proposals and missing footage are recorded in the scene file. Vehicle controls need their own answer definitions because R2 is throttle while driving.

An approach implements `step(rgb, capture, now) -> Decision` and `close()`. `rgb` is the newest available RGB frame, `capture` is its timestamp in `frames.jsonl`, and `now` is the current recording-relative wall time. Return a complete `Pad`, never a button delta. `Decision.source_capture` identifies the frame used for a model answer; the separately recorded newest-frame age must not hide old inference input. A network approach should keep one request in flight and return its current pad while waiting. The runner asks at 30 Hz, skips missed deadlines, and includes decoding and computation in elapsed time. It closes the approach on failure too.

For example, add this class in `pilot/approaches.py`, then add the single entry `"cover-example": CoverExample` to `REGISTRY`. The runner and tool need no changes. This deliberately unconditional example should fail the pre-onset and calm-scene tests; it demonstrates extension, not a useful controller.

```python
class CoverExample:
    def __init__(self, config):
        pass

    def step(self, rgb, capture, now):
        return Decision(Pad(buttons=("r1",)), "example cover input",
                        source_capture=capture)

    def close(self):
        pass
```

`reflex` uses the existing minimap/HUD readers and `Fight`, or immediate flight. `pilot` runs `Pipeline`, `EventDetector`, `MissionHead` with the offline scripted fallback, `Conductor` and `SkillRunner`. Its timestamped OCR inputs come from the existing derived `readings.jsonl`, made available after their recorded OCR duration. The output is a real wall-clock measurement of this cached-text, no-object-reader configuration. It is not a fresh Vision/CoreML measurement or the live judge-assisted configuration. No object inference timing is claimed. Head, event, plan-acceptance and skill timings are instrumented at the existing call boundaries without modifying those modules.

`judge` accepts the first fixed-question answer. `judge-second` needs two consecutive agreeing pads, retaining its previously accepted pad while a changed answer waits for confirmation. `head` uses the same local HTTP test contract but feeds its answer through the real conductor and skills; it requests again on visible reader changes. `--codex` uses the actual `CodexHead` instead. `reflex+judge` protects immediately and permits a judgment based on the current threat or a newer frame to withdraw it. `policy` defines only the client contract. The real policy server belongs to P63. Model errors are not successful neutral decisions.

The local server is a deterministic delayed stub, not an inference model. Its pixel mode uses the existing readers, so its quality scores say nothing about a real vision model. Start it in another terminal, then run the approaches serially:

```sh
env -u PS5_HOST .venv/bin/python tools/reaction.py stub --delay 0.25 --action pixels
env -u PS5_HOST .venv/bin/python tools/reaction.py run reflex pilot
env -u PS5_HOST .venv/bin/python tools/reaction.py run judge judge-second head reflex+judge policy --endpoint http://127.0.0.1:18762 --model delayed-stub
env -u PS5_HOST .venv/bin/python tools/reaction.py board --comparisons
```

`--action fight`, `neutral`, `flee` or `cover` makes the stub return a fixed answer after `--delay` seconds. HTTP model requests go to `/v1/chat/completions` with the fixed `REACTION_PROMPT`, one JPEG and deterministic generation settings. Replies contain JSON `{"action":"neutral|fight|flee|cover","why":"visible evidence"}` in the OpenAI-compatible message envelope. The exact live-server reviewer commands are in `docs/reports/P62-the-reaction-bench.md`; none were executed here.

The policy request is `POST /policy`, JSON `{"version":1,"capture":12.345,"image_jpeg_base64":"..."}`. The reply is JSON `{"version":1,"capture":12.345,"pad":{"buttons":[],"left":[0,0],"right":[0,0],"l2":0,"r2":0},"why":"visible evidence"}`. Sticks range from -1 to 1, triggers from 0 to 1, and button names follow `Pad`. `capture` must echo the requested frame and all omitted pad fields mean neutral. A response is one complete state. HTTP errors, malformed answers and out-of-range values are failures; the client releases to neutral and records the error. There is no bridge TTL, feedback, hidden state or console endpoint in this protocol. The client holds one request in flight and always submits the newest available frame next.

`ledger.jsonl` is append-only. Every trial stores commit, dirty state, machine, scene snapshot, mode, timings, first answer, false-alarm episodes, signal transitions and pilot chain events. The early aborted run remains present for audit. The board selects the current `scenes.json` and implementation SHA-256 and deduplicates the recorded human reference across repeated invocations; completed trials and repetitions on that revision remain visible. Different model names and modes are kept in separate rows. Missing answers are censored, not zero. Medians and p90 describe valid answers only, so always read them with the answered share. A held answer in the two seconds before onset voids a threat trial and counts as a false-alarm episode. Calm rates use the entire observed duration. Per-tick false-answer counts are retained separately from episodes.

Kerim's inputs are placed on picture time with `pad.t + labels.lead`, the inverse of the existing label lookup at `frame.t - lead`. All retained leads are estimated. Their 20 ms search grid is resolution, not an error bound; unknown systematic offset, capture batching and input sampling remain. The human row is therefore labelled recorded-human-estimated. Human compute time and decision rate are unavailable. The added 135 ms is the ten-sample median in `docs/LOG.md:15`, not a newly measured replay link.

Fast mode requires a cost table measured from a realtime ledger, for example `{"reflex":{"compute_s":0.002,"source":"ledger row and machine"}}`. The supplied `costs.json` cites the measurements actually used. `--mode modelled --cost-table ../lab/reaction/costs.json` advances a virtual clock by the table's tick cost and skips missed deadlines. Network approaches use the explicitly simulated pixel stub with `--stub-delay`; no real model timing is inferred. Codex is disallowed in modelled mode. Every such board row says modelled.

The recording never reacts to emitted pads. This bench can compare first reactions and false initial responses, not survival, aim accuracy, successful flight, or any action after a counterfactual input. Capture timestamps, rather than nominal MP4 frame rate, control playback because some recordings contain batches and gaps. No benchmark here proves a console capability.
