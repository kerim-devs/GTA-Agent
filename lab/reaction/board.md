# First-reaction bench

Every number inherits the mode in its row. Missing answers are not zero. Reaction statistics include answered, non-void threat scenes only. Repetitions are separate trials. Pilot/head use cached timestamped OCR and no object reader; their measured wall-clock results do not include fresh OCR/object inference. Delayed-stub rows measure a local reader stub, not model quality. The recording never responds to these pads.

Link addition: 135 ms; docs/LOG.md:15: camera measurement, 60 fps, 10 samples, median 135 ms.

| Approach | Mode | Threat/calm trials | Answer ≤3s | Median / p90 / worst ms | With link ms | False alarms | Calm / scene / min | Decision ms | Hz |
|---|---|---:|---:|---|---|---:|---|---:|---:|
| Kerim | recorded-human-estimated | 9/3 | 11.1% | 784.6 / 784.6 / 784.6 | 919.6 / 919.6 / 919.6 | 16 | 0.0 / 0.0 | n/a | n/a |
| head (delayed-stub) | realtime | 9/3 | 11.1% | 1791.0 / 2979.8 / 3277.0 | 1926.0 / 3114.8 / 3412.0 | 0 | 0.0 / 0.0 | 13.6 | 24.2 |
| judge (delayed-stub) | realtime | 9/3 | 22.2% | 569.2 / 703.4 / 737.0 | 704.2 / 838.4 / 872.0 | 1 | 0.0 / 0.0 | 403.0 | 30.0 |
| judge-second (delayed-stub) | realtime | 9/3 | 22.2% | 952.2 / 1151.1 / 1200.9 | 1087.2 / 1286.1 / 1335.9 | 1 | 0.0 / 0.0 | 396.9 | 30.0 |
| pilot | modelled | 9/3 | 11.1% | 2020.7 / 3580.7 / 3970.7 | 2155.7 / 3715.7 / 4105.7 | 0 | 0.0 / 0.0 | 13.6 | 30.0 |
| pilot | realtime | 9/3 | 11.1% | 74.2 / 74.2 / 74.2 | 209.2 / 209.2 / 209.2 | 0 | 0.0 / 0.0 | 12.8 | 29.9 |
| policy (delayed-stub) | realtime | 9/3 | 22.2% | 402.1 / 403.1 / 403.3 | 537.1 / 538.1 / 538.3 | 1 | 0.0 / 0.0 | 401.1 | 30.0 |
| reflex | modelled | 9/3 | 44.4% | 53.1 / 606.4 / 836.4 | 188.1 / 741.4 / 971.4 | 2 | 0.0 / 0.0 | 12.7 | 30.0 |
| reflex | realtime | 9/3 | 44.4% | 38.7 / 609.1 / 839.1 | 173.7 / 744.1 / 974.1 | 2 | 0.0 / 0.0 | 12.4 | 29.7 |
| reflex+judge (delayed-stub) | realtime | 9/3 | 33.3% | 5.5 / 326.1 / 406.2 | 140.5 / 461.1 / 541.2 | 2 | 0.0 / 0.0 | 388.8 | 30.0 |

## Per-scene timeline

All times below are seconds on the recording clock. Each trial includes onset, Kerim's aligned input and the approach's first valid answer. A void trial has no valid answer.

| Scene / kind | Approach | Mode | Onset | Kerim | Answer | Pre-onset void |
|---|---|---|---:|---:|---:|---|
| enemy-01 / enemy | Kerim | recorded-human-estimated | 412.498 | n/a | n/a | True |
| enemy-02 / enemy | Kerim | recorded-human-estimated | 395.999 | n/a | n/a | True |
| enemy-03 / enemy | Kerim | recorded-human-estimated | 356.219 | n/a | n/a | True |
| hit-01 / hit | Kerim | recorded-human-estimated | 396.364 | n/a | n/a | True |
| hit-02 / hit | Kerim | recorded-human-estimated | 210.830 | n/a | n/a | True |
| hit-03 / hit | Kerim | recorded-human-estimated | 565.100 | n/a | n/a | True |
| wanted-01 / wanted | Kerim | recorded-human-estimated | 161.677 | n/a | n/a | True |
| wanted-02 / wanted | Kerim | recorded-human-estimated | 391.332 | 392.1 | 392.1 | False |
| wanted-03 / wanted | Kerim | recorded-human-estimated | 209.426 | n/a | n/a | True |
| calm-walk-01 / calm | Kerim | recorded-human-estimated | 12.000 | n/a | n/a | False |
| calm-walk-02 / calm | Kerim | recorded-human-estimated | 489.000 | n/a | n/a | False |
| calm-walk-03 / calm | Kerim | recorded-human-estimated | 499.000 | n/a | n/a | False |
| enemy-01 / enemy | reflex | realtime | 412.498 | 412.5 | n/a | False |
| enemy-02 / enemy | reflex | realtime | 395.999 | 396.0 | n/a | False |
| enemy-03 / enemy | reflex | realtime | 356.219 | 356.2 | n/a | False |
| hit-01 / hit | reflex | realtime | 396.364 | 397.6 | n/a | False |
| hit-02 / hit | reflex | realtime | 210.830 | 210.8 | n/a | True |
| hit-03 / hit | reflex | realtime | 565.100 | 565.1 | 565.2 | False |
| wanted-01 / wanted | reflex | realtime | 161.677 | 162.1 | 161.7 | False |
| wanted-02 / wanted | reflex | realtime | 391.332 | 392.1 | 391.3 | False |
| wanted-03 / wanted | reflex | realtime | 209.426 | 209.4 | 210.3 | False |
| calm-walk-01 / calm | reflex | realtime | 12.000 | n/a | n/a | False |
| calm-walk-02 / calm | reflex | realtime | 489.000 | n/a | n/a | False |
| calm-walk-03 / calm | reflex | realtime | 499.000 | n/a | n/a | False |
| enemy-01 / enemy | pilot | realtime | 412.498 | 412.5 | n/a | False |
| enemy-02 / enemy | pilot | realtime | 395.999 | 396.0 | n/a | False |
| enemy-03 / enemy | pilot | realtime | 356.219 | 356.2 | n/a | False |
| hit-01 / hit | pilot | realtime | 396.364 | 397.6 | n/a | False |
| hit-02 / hit | pilot | realtime | 210.830 | 210.8 | n/a | False |
| hit-03 / hit | pilot | realtime | 565.100 | 565.1 | n/a | False |
| wanted-01 / wanted | pilot | realtime | 161.677 | 162.1 | n/a | False |
| wanted-02 / wanted | pilot | realtime | 391.332 | 392.1 | 391.4 | False |
| wanted-03 / wanted | pilot | realtime | 209.426 | 209.4 | n/a | False |
| calm-walk-01 / calm | pilot | realtime | 12.000 | n/a | n/a | False |
| calm-walk-02 / calm | pilot | realtime | 489.000 | n/a | n/a | False |
| calm-walk-03 / calm | pilot | realtime | 499.000 | n/a | n/a | False |
| enemy-01 / enemy | judge | realtime | 412.498 | 412.5 | n/a | False |
| enemy-02 / enemy | judge | realtime | 395.999 | 396.0 | n/a | False |
| enemy-03 / enemy | judge | realtime | 356.219 | 356.2 | n/a | False |
| hit-01 / hit | judge | realtime | 396.364 | 397.6 | n/a | False |
| hit-02 / hit | judge | realtime | 210.830 | 210.8 | n/a | True |
| hit-03 / hit | judge | realtime | 565.100 | 565.1 | n/a | False |
| wanted-01 / wanted | judge | realtime | 161.677 | 162.1 | n/a | False |
| wanted-02 / wanted | judge | realtime | 391.332 | 392.1 | 391.7 | False |
| wanted-03 / wanted | judge | realtime | 209.426 | 209.4 | 210.2 | False |
| calm-walk-01 / calm | judge | realtime | 12.000 | n/a | n/a | False |
| calm-walk-02 / calm | judge | realtime | 489.000 | n/a | n/a | False |
| calm-walk-03 / calm | judge | realtime | 499.000 | n/a | n/a | False |
| enemy-01 / enemy | judge-second | realtime | 412.498 | 412.5 | n/a | False |
| enemy-02 / enemy | judge-second | realtime | 395.999 | 396.0 | n/a | False |
| enemy-03 / enemy | judge-second | realtime | 356.219 | 356.2 | n/a | False |
| hit-01 / hit | judge-second | realtime | 396.364 | 397.6 | n/a | False |
| hit-02 / hit | judge-second | realtime | 210.830 | 210.8 | n/a | True |
| hit-03 / hit | judge-second | realtime | 565.100 | 565.1 | n/a | False |
| wanted-01 / wanted | judge-second | realtime | 161.677 | 162.1 | n/a | False |
| wanted-02 / wanted | judge-second | realtime | 391.332 | 392.1 | 392.0 | False |
| wanted-03 / wanted | judge-second | realtime | 209.426 | 209.4 | 210.6 | False |
| calm-walk-01 / calm | judge-second | realtime | 12.000 | n/a | n/a | False |
| calm-walk-02 / calm | judge-second | realtime | 489.000 | n/a | n/a | False |
| calm-walk-03 / calm | judge-second | realtime | 499.000 | n/a | n/a | False |
| enemy-01 / enemy | head | realtime | 412.498 | 412.5 | n/a | False |
| enemy-02 / enemy | head | realtime | 395.999 | 396.0 | n/a | False |
| enemy-03 / enemy | head | realtime | 356.219 | 356.2 | n/a | False |
| hit-01 / hit | head | realtime | 396.364 | 397.6 | n/a | False |
| hit-02 / hit | head | realtime | 210.830 | 210.8 | n/a | False |
| hit-03 / hit | head | realtime | 565.100 | 565.1 | n/a | False |
| wanted-01 / wanted | head | realtime | 161.677 | 162.1 | n/a | False |
| wanted-02 / wanted | head | realtime | 391.332 | 392.1 | 391.6 | False |
| wanted-03 / wanted | head | realtime | 209.426 | 209.4 | 212.7 | False |
| calm-walk-01 / calm | head | realtime | 12.000 | n/a | n/a | False |
| calm-walk-02 / calm | head | realtime | 489.000 | n/a | n/a | False |
| calm-walk-03 / calm | head | realtime | 499.000 | n/a | n/a | False |
| enemy-01 / enemy | reflex+judge | realtime | 412.498 | 412.5 | n/a | False |
| enemy-02 / enemy | reflex+judge | realtime | 395.999 | 396.0 | n/a | False |
| enemy-03 / enemy | reflex+judge | realtime | 356.219 | 356.2 | n/a | False |
| hit-01 / hit | reflex+judge | realtime | 396.364 | 397.6 | n/a | False |
| hit-02 / hit | reflex+judge | realtime | 210.830 | 210.8 | n/a | True |
| hit-03 / hit | reflex+judge | realtime | 565.100 | 565.1 | n/a | False |
| wanted-01 / wanted | reflex+judge | realtime | 161.677 | 162.1 | 161.7 | False |
| wanted-02 / wanted | reflex+judge | realtime | 391.332 | 392.1 | 391.3 | False |
| wanted-03 / wanted | reflex+judge | realtime | 209.426 | 209.4 | 209.8 | False |
| calm-walk-01 / calm | reflex+judge | realtime | 12.000 | n/a | n/a | False |
| calm-walk-02 / calm | reflex+judge | realtime | 489.000 | n/a | n/a | False |
| calm-walk-03 / calm | reflex+judge | realtime | 499.000 | n/a | n/a | False |
| enemy-01 / enemy | policy | realtime | 412.498 | 412.5 | n/a | False |
| enemy-02 / enemy | policy | realtime | 395.999 | 396.0 | n/a | False |
| enemy-03 / enemy | policy | realtime | 356.219 | 356.2 | n/a | False |
| hit-01 / hit | policy | realtime | 396.364 | 397.6 | n/a | False |
| hit-02 / hit | policy | realtime | 210.830 | 210.8 | n/a | True |
| hit-03 / hit | policy | realtime | 565.100 | 565.1 | n/a | False |
| wanted-01 / wanted | policy | realtime | 161.677 | 162.1 | n/a | False |
| wanted-02 / wanted | policy | realtime | 391.332 | 392.1 | 391.7 | False |
| wanted-03 / wanted | policy | realtime | 209.426 | 209.4 | 209.8 | False |
| calm-walk-01 / calm | policy | realtime | 12.000 | n/a | n/a | False |
| calm-walk-02 / calm | policy | realtime | 489.000 | n/a | n/a | False |
| calm-walk-03 / calm | policy | realtime | 499.000 | n/a | n/a | False |
| enemy-01 / enemy | reflex | modelled | 412.498 | 412.5 | n/a | False |
| enemy-02 / enemy | reflex | modelled | 395.999 | 396.0 | n/a | False |
| enemy-03 / enemy | reflex | modelled | 356.219 | 356.2 | n/a | False |
| hit-01 / hit | reflex | modelled | 396.364 | 397.6 | n/a | False |
| hit-02 / hit | reflex | modelled | 210.830 | 210.8 | n/a | True |
| hit-03 / hit | reflex | modelled | 565.100 | 565.1 | 565.2 | False |
| wanted-01 / wanted | reflex | modelled | 161.677 | 162.1 | 161.7 | False |
| wanted-02 / wanted | reflex | modelled | 391.332 | 392.1 | 391.3 | False |
| wanted-03 / wanted | reflex | modelled | 209.426 | 209.4 | 210.3 | False |
| calm-walk-01 / calm | reflex | modelled | 12.000 | n/a | n/a | False |
| calm-walk-02 / calm | reflex | modelled | 489.000 | n/a | n/a | False |
| calm-walk-03 / calm | reflex | modelled | 499.000 | n/a | n/a | False |
| enemy-01 / enemy | pilot | modelled | 412.498 | 412.5 | n/a | False |
| enemy-02 / enemy | pilot | modelled | 395.999 | 396.0 | n/a | False |
| enemy-03 / enemy | pilot | modelled | 356.219 | 356.2 | n/a | False |
| hit-01 / hit | pilot | modelled | 396.364 | 397.6 | n/a | False |
| hit-02 / hit | pilot | modelled | 210.830 | 210.8 | n/a | False |
| hit-03 / hit | pilot | modelled | 565.100 | 565.1 | n/a | False |
| wanted-01 / wanted | pilot | modelled | 161.677 | 162.1 | 165.6 | False |
| wanted-02 / wanted | pilot | modelled | 391.332 | 392.1 | 391.4 | False |
| wanted-03 / wanted | pilot | modelled | 209.426 | 209.4 | n/a | False |
| calm-walk-01 / calm | pilot | modelled | 12.000 | n/a | n/a | False |
| calm-walk-02 / calm | pilot | modelled | 489.000 | n/a | n/a | False |
| calm-walk-03 / calm | pilot | modelled | 499.000 | n/a | n/a | False |
