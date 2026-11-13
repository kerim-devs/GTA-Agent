# First-reaction bench

Every number inherits the mode in its row. Two times per try: noticed is the first tick on which the way of control decides anything because of the threat, by its own account; answered is the first pad from the scene's answer set. For Kerim only the pad exists. Missing answers are not zero. Time statistics include noticed or answered, non-void threat scenes only; a state held in the two seconds before the onset voids the try. Repetitions are separate trials. Pilot/head use cached timestamped OCR and no object reader; their measured wall-clock results do not include fresh OCR/object inference. Delayed-stub rows measure a local reader stub, not model quality. A head delay row runs in real time with a head answer delayed by a modelled time. The recording never responds to these pads.

Link addition: 135 ms; docs/LOG.md:15: camera measurement, 60 fps, 10 samples, median 135 ms. Rows of implementation SHA-256 26ecdb1d5decf7c08921e474a7c1759df348ab198e5bf142eb0453b2eacc9992, scenes SHA-256 ac26b690aab85946b8428cab71e29e1322de5a8c6ff462db818778dab03bd6ff.

| Approach | Mode | Threat/calm trials | Noticed ≤3s | Noticed median / p90 / worst ms | Answered ≤3s | Answered median / p90 / worst ms | Answered with link ms | False notices | False answers | Calm / scene / min | Decision ms | Hz |
|---|---|---:|---:|---|---:|---|---|---:|---:|---|---:|---:|
| Kerim | recorded-human-default | 0/3 | n/a | n/a | n/a% | n/a / n/a / n/a | n/a / n/a / n/a | n/a | 90 | 30.0 / 180.0 | n/a | n/a |
| Kerim, looser reading: first new press after the onset | recorded-human-default | 0/3 | n/a | n/a | n/a% | n/a / n/a / n/a | n/a / n/a / n/a | n/a | 90 | 30.0 / 180.0 | n/a | n/a |
| Kerim | recorded-human-estimated | 0/8 | n/a | n/a | n/a% | n/a / n/a / n/a | n/a / n/a / n/a | n/a | 0 | 0.0 / 0.0 | n/a | n/a |
| Kerim, looser reading: first new press after the onset | recorded-human-estimated | 0/8 | n/a | n/a | n/a% | n/a / n/a / n/a | n/a / n/a / n/a | n/a | 0 | 0.0 / 0.0 | n/a | n/a |
| head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 0/11 | n/a% | n/a / n/a / n/a | n/a% | n/a / n/a / n/a | n/a / n/a / n/a | 10 | 0 | 0.0 / 0.0 | 15.0 | 30.0 |
| pilot+guard | realtime | 0/11 | n/a% | n/a / n/a / n/a | n/a% | n/a / n/a / n/a | n/a / n/a / n/a | 10 | 0 | 0.0 / 0.0 | 17.5 | 29.9 |
| reflex | realtime | 0/11 | n/a% | n/a / n/a / n/a | n/a% | n/a / n/a / n/a | n/a / n/a / n/a | 38 | 0 | 0.0 / 0.0 | 12.3 | 30.0 |

## Per-scene timeline

All times below are seconds on the recording clock. Each trial includes onset, Kerim's aligned input under both readings, and the approach's first notice and first valid answer. A void trial has no valid answer.

| Scene / kind | Approach | Mode | Onset | Kerim | Kerim looser | Noticed | Answered | Pre-onset void |
|---|---|---|---:|---:|---:|---:|---:|---|
| hard-01 / calm | Kerim | recorded-human-estimated | 185.670 | n/a | n/a | n/a | n/a | False |
| hard-02 / calm | Kerim | recorded-human-estimated | 195.720 | n/a | n/a | n/a | n/a | False |
| hard-03 / calm | Kerim | recorded-human-estimated | 603.220 | n/a | n/a | n/a | n/a | False |
| hard-04 / calm | Kerim | recorded-human-default | 313.040 | n/a | n/a | n/a | n/a | False |
| hard-05 / calm | Kerim | recorded-human-estimated | 405.780 | n/a | n/a | n/a | n/a | False |
| hard-06 / calm | Kerim | recorded-human-estimated | 328.400 | n/a | n/a | n/a | n/a | False |
| hard-07 / calm | Kerim | recorded-human-estimated | 601.750 | n/a | n/a | n/a | n/a | False |
| hard-08 / calm | Kerim | recorded-human-estimated | 615.630 | n/a | n/a | n/a | n/a | False |
| hard-09 / calm | Kerim | recorded-human-default | 216.600 | n/a | n/a | n/a | n/a | False |
| hard-10 / calm | Kerim | recorded-human-default | 823.390 | n/a | n/a | n/a | n/a | False |
| hard-11 / calm | Kerim | recorded-human-estimated | 790.990 | n/a | n/a | n/a | n/a | False |
| hard-01 / calm | reflex | realtime | 185.670 | n/a | n/a | n/a | n/a | False |
| hard-02 / calm | reflex | realtime | 195.720 | n/a | n/a | n/a | n/a | False |
| hard-03 / calm | reflex | realtime | 603.220 | n/a | n/a | n/a | n/a | False |
| hard-04 / calm | reflex | realtime | 313.040 | n/a | n/a | n/a | n/a | False |
| hard-05 / calm | reflex | realtime | 405.780 | n/a | n/a | n/a | n/a | False |
| hard-06 / calm | reflex | realtime | 328.400 | n/a | n/a | n/a | n/a | False |
| hard-07 / calm | reflex | realtime | 601.750 | n/a | n/a | n/a | n/a | False |
| hard-08 / calm | reflex | realtime | 615.630 | n/a | n/a | n/a | n/a | False |
| hard-09 / calm | reflex | realtime | 216.600 | n/a | n/a | n/a | n/a | False |
| hard-10 / calm | reflex | realtime | 823.390 | n/a | n/a | n/a | n/a | False |
| hard-11 / calm | reflex | realtime | 790.990 | n/a | n/a | n/a | n/a | False |
| hard-01 / calm | pilot+guard | realtime | 185.670 | n/a | n/a | n/a | n/a | False |
| hard-02 / calm | pilot+guard | realtime | 195.720 | n/a | n/a | n/a | n/a | False |
| hard-03 / calm | pilot+guard | realtime | 603.220 | n/a | n/a | n/a | n/a | False |
| hard-04 / calm | pilot+guard | realtime | 313.040 | n/a | n/a | n/a | n/a | False |
| hard-05 / calm | pilot+guard | realtime | 405.780 | n/a | n/a | n/a | n/a | False |
| hard-06 / calm | pilot+guard | realtime | 328.400 | n/a | n/a | n/a | n/a | False |
| hard-07 / calm | pilot+guard | realtime | 601.750 | n/a | n/a | n/a | n/a | False |
| hard-08 / calm | pilot+guard | realtime | 615.630 | n/a | n/a | n/a | n/a | False |
| hard-09 / calm | pilot+guard | realtime | 216.600 | n/a | n/a | n/a | n/a | False |
| hard-10 / calm | pilot+guard | realtime | 823.390 | n/a | n/a | n/a | n/a | False |
| hard-11 / calm | pilot+guard | realtime | 790.990 | n/a | n/a | n/a | n/a | False |
| hard-01 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 185.670 | n/a | n/a | n/a | n/a | False |
| hard-02 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 195.720 | n/a | n/a | n/a | n/a | False |
| hard-03 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 603.220 | n/a | n/a | n/a | n/a | False |
| hard-04 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 313.040 | n/a | n/a | n/a | n/a | False |
| hard-05 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 405.780 | n/a | n/a | n/a | n/a | False |
| hard-06 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 328.400 | n/a | n/a | n/a | n/a | False |
| hard-07 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 601.750 | n/a | n/a | n/a | n/a | False |
| hard-08 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 615.630 | n/a | n/a | n/a | n/a | False |
| hard-09 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 216.600 | n/a | n/a | n/a | n/a | False |
| hard-10 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 823.390 | n/a | n/a | n/a | n/a | False |
| hard-11 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 790.990 | n/a | n/a | n/a | n/a | False |
