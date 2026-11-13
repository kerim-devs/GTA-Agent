# First-reaction bench

Every number inherits the mode in its row. Two times per try: noticed is the first tick on which the way of control decides anything because of the threat, by its own account; answered is the first pad from the scene's answer set. For Kerim only the pad exists. Missing answers are not zero. Time statistics include noticed or answered, non-void threat scenes only; a state held in the two seconds before the onset voids the try. Repetitions are separate trials. Pilot/head use cached timestamped OCR and no object reader; their measured wall-clock results do not include fresh OCR/object inference. Delayed-stub rows measure a local reader stub, not model quality. A head delay row runs in real time with a head answer delayed by a modelled time. The recording never responds to these pads.

Link addition: 135 ms; docs/LOG.md:15: camera measurement, 60 fps, 10 samples, median 135 ms. Rows of implementation SHA-256 26ecdb1d5decf7c08921e474a7c1759df348ab198e5bf142eb0453b2eacc9992, scenes SHA-256 7b083561b41e90c4e3d9820f4fc7a070fae3322283c42a0b8e709e24eb2e642d.

| Approach | Mode | Threat/calm trials | Noticed ≤3s | Noticed median / p90 / worst ms | Answered ≤3s | Answered median / p90 / worst ms | Answered with link ms | False notices | False answers | Calm / scene / min | Decision ms | Hz |
|---|---|---:|---:|---|---:|---|---|---:|---:|---|---:|---:|
| Kerim | recorded-human-default | 8/9 | n/a | n/a | 50.0% | 682.2 / 2775.5 / 3651.5 | 817.2 / 2910.5 / 3786.5 | n/a | 98 | 10.6 / 71.2 | n/a | n/a |
| Kerim, looser reading: first new press after the onset | recorded-human-default | 8/9 | n/a | n/a | 62.5% | 2200.9 / 3827.2 / 3996.0 | 2335.9 / 3962.2 / 4131.0 | n/a | 98 | 10.6 / 71.2 | n/a | n/a |
| Kerim | recorded-human-estimated | 18/20 | n/a | n/a | 38.9% | 973.9 / 2106.6 / 2115.7 | 1108.9 / 2241.6 / 2250.7 | n/a | 98 | 3.9 / 25.7 | n/a | n/a |
| Kerim, looser reading: first new press after the onset | recorded-human-estimated | 18/20 | n/a | n/a | 83.3% | 1132.3 / 2109.7 / 2149.7 | 1267.3 / 2244.7 / 2284.7 | n/a | 98 | 3.9 / 25.7 | n/a | n/a |
| head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 26/29 | 26.9% | 508.4 / 1310.7 / 2509.6 | 0.0% | n/a / n/a / n/a | n/a / n/a / n/a | 1 | 0 | 0.0 / 0.0 | 13.5 | 30.0 |
| head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 26/29 | 88.5% | 48.8 / 138.3 / 146.6 | 50.0% | 145.8 / 3200.7 / 3915.3 | 280.8 / 3335.7 / 4050.3 | 3 | 12 | 0.0 / 0.0 | 16.1 | 30.0 |
| pilot | realtime | 26/29 | 34.6% | 10.3 / 815.0 / 1913.0 | 30.8% | 74.7 / 689.1 / 1979.8 | 209.7 / 824.1 / 2114.8 | 2 | 19 | 0.0 / 0.0 | 13.6 | 29.9 |
| pilot+guard | realtime | 26/29 | 88.5% | 62.4 / 123.7 / 175.7 | 50.0% | 125.8 / 3475.9 / 3911.4 | 260.8 / 3610.9 / 4046.4 | 3 | 17 | 0.0 / 0.0 | 16.5 | 29.8 |
| reflex | realtime | 26/29 | 84.6% | 36.7 / 1344.0 / 1672.9 | 53.8% | 470.5 / 3073.6 / 3904.0 | 605.5 / 3208.6 / 4039.0 | 11 | 0 | 0.0 / 0.0 | 13.5 | 30.0 |

## Per-scene timeline

All times below are seconds on the recording clock. Each trial includes onset, Kerim's aligned input under both readings, and the approach's first notice and first valid answer. A void trial has no valid answer.

| Scene / kind | Approach | Mode | Onset | Kerim | Kerim looser | Noticed | Answered | Pre-onset void |
|---|---|---|---:|---:|---:|---:|---:|---|
| enemy-01 / enemy | Kerim | recorded-human-estimated | 412.498 | n/a | n/a | n/a | n/a | True |
| enemy-02 / enemy | Kerim | recorded-human-estimated | 395.999 | n/a | 397.4 | n/a | n/a | True |
| enemy-03 / enemy | Kerim | recorded-human-estimated | 356.219 | n/a | 356.4 | n/a | n/a | True |
| wanted-02 / wanted | Kerim | recorded-human-estimated | 391.332 | 392.1 | 392.1 | n/a | 392.1 | False |
| wanted-03 / wanted | Kerim | recorded-human-estimated | 209.426 | n/a | 210.6 | n/a | n/a | True |
| calm-walk-01 / calm | Kerim | recorded-human-estimated | 12.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-02 / calm | Kerim | recorded-human-estimated | 489.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-03 / calm | Kerim | recorded-human-estimated | 499.000 | n/a | n/a | n/a | n/a | False |
| enemy-04 / enemy | Kerim | recorded-human-estimated | 410.845 | 412.5 | 412.5 | n/a | 412.5 | False |
| enemy-05 / enemy | Kerim | recorded-human-estimated | 425.519 | 426.2 | 426.2 | n/a | 426.2 | False |
| enemy-06 / enemy | Kerim | recorded-human-estimated | 461.120 | n/a | 462.1 | n/a | n/a | True |
| enemy-07 / enemy | Kerim | recorded-human-estimated | 364.505 | n/a | 366.3 | n/a | n/a | True |
| enemy-08 / enemy | Kerim | recorded-human-estimated | 320.065 | n/a | n/a | n/a | n/a | False |
| enemy-09 / enemy | Kerim | recorded-human-default | 690.952 | n/a | 694.7 | n/a | n/a | True |
| enemy-10 / enemy | Kerim | recorded-human-default | 803.466 | n/a | 806.4 | n/a | n/a | True |
| enemy-11 / enemy | Kerim | recorded-human-default | 659.240 | 662.9 | 662.9 | n/a | 662.9 | False |
| enemy-12 / enemy | Kerim | recorded-human-default | 771.165 | 771.8 | 771.8 | n/a | 771.8 | False |
| enemy-13 / enemy | Kerim | recorded-human-estimated | 627.117 | 629.2 | 629.2 | n/a | 629.2 | False |
| enemy-14 / enemy | Kerim | recorded-human-estimated | 417.951 | 418.3 | 418.3 | n/a | 418.3 | False |
| enemy-15 / enemy | Kerim | recorded-human-default | 539.931 | n/a | 543.9 | n/a | n/a | True |
| enemy-16 / enemy | Kerim | recorded-human-default | 621.694 | 622.2 | 622.2 | n/a | 622.2 | False |
| enemy-17 / enemy | Kerim | recorded-human-default | 154.015 | 155.5 | 155.5 | n/a | 155.5 | False |
| enemy-18 / enemy | Kerim | recorded-human-default | 205.163 | 205.8 | 205.8 | n/a | 205.8 | False |
| enemy-19 / enemy | Kerim | recorded-human-estimated | 672.947 | 675.1 | 675.1 | n/a | 675.1 | False |
| enemy-20 / enemy | Kerim | recorded-human-estimated | 819.069 | 820.0 | 820.0 | n/a | 820.0 | False |
| wanted-04 / wanted | Kerim | recorded-human-estimated | 300.220 | n/a | n/a | n/a | n/a | True |
| wanted-05 / wanted | Kerim | recorded-human-estimated | 291.850 | n/a | 293.1 | n/a | n/a | True |
| wanted-06 / wanted | Kerim | recorded-human-estimated | 163.943 | n/a | 166.1 | n/a | n/a | True |
| wanted-07 / wanted | Kerim | recorded-human-estimated | 655.364 | n/a | 655.6 | n/a | n/a | True |
| calm-walk-04 / calm | Kerim | recorded-human-estimated | 328.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-05 / calm | Kerim | recorded-human-estimated | 358.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-06 / calm | Kerim | recorded-human-estimated | 156.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-07 / calm | Kerim | recorded-human-estimated | 186.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-08 / calm | Kerim | recorded-human-estimated | 216.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-09 / calm | Kerim | recorded-human-estimated | 142.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-10 / calm | Kerim | recorded-human-estimated | 513.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-11 / calm | Kerim | recorded-human-estimated | 162.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-12 / calm | Kerim | recorded-human-default | 500.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-13 / calm | Kerim | recorded-human-default | 732.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-14 / calm | Kerim | recorded-human-default | 767.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-15 / calm | Kerim | recorded-human-estimated | 683.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-16 / calm | Kerim | recorded-human-default | 277.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-17 / calm | Kerim | recorded-human-estimated | 773.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-18 / calm | Kerim | recorded-human-estimated | 141.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-19 / calm | Kerim | recorded-human-default | 67.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-20 / calm | Kerim | recorded-human-default | 111.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-21 / calm | Kerim | recorded-human-estimated | 131.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-22 / calm | Kerim | recorded-human-estimated | 276.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-23 / calm | Kerim | recorded-human-estimated | 82.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-24 / calm | Kerim | recorded-human-estimated | 242.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-25 / calm | Kerim | recorded-human-default | 88.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-26 / calm | Kerim | recorded-human-default | 164.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-27 / calm | Kerim | recorded-human-estimated | 780.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-28 / calm | Kerim | recorded-human-estimated | 31.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-29 / calm | Kerim | recorded-human-default | 20.000 | n/a | n/a | n/a | n/a | False |
| enemy-01 / enemy | reflex | realtime | 412.498 | n/a | n/a | 412.6 | n/a | False |
| enemy-02 / enemy | reflex | realtime | 395.999 | n/a | 397.4 | 396.1 | n/a | False |
| enemy-03 / enemy | reflex | realtime | 356.219 | n/a | 356.4 | 356.2 | n/a | False |
| wanted-02 / wanted | reflex | realtime | 391.332 | 392.1 | 392.1 | 391.3 | 391.3 | False |
| wanted-03 / wanted | reflex | realtime | 209.426 | n/a | 210.6 | n/a | 210.3 | False |
| calm-walk-01 / calm | reflex | realtime | 12.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-02 / calm | reflex | realtime | 489.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-03 / calm | reflex | realtime | 499.000 | n/a | n/a | n/a | n/a | False |
| enemy-04 / enemy | reflex | realtime | 410.845 | 412.5 | 412.5 | 410.9 | n/a | False |
| enemy-05 / enemy | reflex | realtime | 425.519 | 426.2 | 426.2 | 426.9 | 427.2 | False |
| enemy-06 / enemy | reflex | realtime | 461.120 | n/a | 462.1 | 462.8 | 465.0 | False |
| enemy-07 / enemy | reflex | realtime | 364.505 | n/a | 366.3 | 364.5 | 366.9 | False |
| enemy-08 / enemy | reflex | realtime | 320.065 | n/a | n/a | 320.1 | n/a | False |
| enemy-09 / enemy | reflex | realtime | 690.952 | n/a | 694.7 | 692.4 | 693.1 | False |
| enemy-10 / enemy | reflex | realtime | 803.466 | n/a | 806.4 | 803.5 | n/a | False |
| enemy-11 / enemy | reflex | realtime | 659.240 | 662.9 | 662.9 | 659.2 | n/a | False |
| enemy-12 / enemy | reflex | realtime | 771.165 | 771.8 | 771.8 | 771.2 | 771.2 | False |
| enemy-13 / enemy | reflex | realtime | 627.117 | 629.2 | 629.2 | n/a | 629.5 | False |
| enemy-14 / enemy | reflex | realtime | 417.951 | 418.3 | 418.3 | 418.0 | 419.5 | False |
| enemy-15 / enemy | reflex | realtime | 539.931 | n/a | 543.9 | 540.7 | n/a | False |
| enemy-16 / enemy | reflex | realtime | 621.694 | 622.2 | 622.2 | 622.4 | n/a | False |
| enemy-17 / enemy | reflex | realtime | 154.015 | 155.5 | 155.5 | 154.0 | 154.0 | False |
| enemy-18 / enemy | reflex | realtime | 205.163 | 205.8 | 205.8 | 205.2 | 205.2 | False |
| enemy-19 / enemy | reflex | realtime | 672.947 | 675.1 | 675.1 | 673.0 | n/a | False |
| enemy-20 / enemy | reflex | realtime | 819.069 | 820.0 | 820.0 | 819.1 | 822.8 | False |
| wanted-04 / wanted | reflex | realtime | 300.220 | n/a | n/a | 300.2 | 300.2 | False |
| wanted-05 / wanted | reflex | realtime | 291.850 | n/a | 293.1 | 291.9 | 291.9 | False |
| wanted-06 / wanted | reflex | realtime | 163.943 | n/a | 166.1 | n/a | 164.0 | False |
| wanted-07 / wanted | reflex | realtime | 655.364 | n/a | 655.6 | n/a | 655.4 | False |
| calm-walk-04 / calm | reflex | realtime | 328.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-05 / calm | reflex | realtime | 358.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-06 / calm | reflex | realtime | 156.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-07 / calm | reflex | realtime | 186.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-08 / calm | reflex | realtime | 216.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-09 / calm | reflex | realtime | 142.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-10 / calm | reflex | realtime | 513.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-11 / calm | reflex | realtime | 162.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-12 / calm | reflex | realtime | 500.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-13 / calm | reflex | realtime | 732.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-14 / calm | reflex | realtime | 767.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-15 / calm | reflex | realtime | 683.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-16 / calm | reflex | realtime | 277.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-17 / calm | reflex | realtime | 773.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-18 / calm | reflex | realtime | 141.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-19 / calm | reflex | realtime | 67.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-20 / calm | reflex | realtime | 111.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-21 / calm | reflex | realtime | 131.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-22 / calm | reflex | realtime | 276.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-23 / calm | reflex | realtime | 82.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-24 / calm | reflex | realtime | 242.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-25 / calm | reflex | realtime | 88.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-26 / calm | reflex | realtime | 164.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-27 / calm | reflex | realtime | 780.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-28 / calm | reflex | realtime | 31.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-29 / calm | reflex | realtime | 20.000 | n/a | n/a | n/a | n/a | False |
| enemy-01 / enemy | pilot | realtime | 412.498 | n/a | n/a | n/a | n/a | False |
| enemy-02 / enemy | pilot | realtime | 395.999 | n/a | 397.4 | n/a | n/a | False |
| enemy-03 / enemy | pilot | realtime | 356.219 | n/a | 356.4 | n/a | n/a | False |
| wanted-02 / wanted | pilot | realtime | 391.332 | 392.1 | 392.1 | 391.3 | 391.4 | False |
| wanted-03 / wanted | pilot | realtime | 209.426 | n/a | 210.6 | 210.0 | n/a | False |
| calm-walk-01 / calm | pilot | realtime | 12.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-02 / calm | pilot | realtime | 489.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-03 / calm | pilot | realtime | 499.000 | n/a | n/a | n/a | n/a | False |
| enemy-04 / enemy | pilot | realtime | 410.845 | 412.5 | 412.5 | n/a | n/a | True |
| enemy-05 / enemy | pilot | realtime | 425.519 | 426.2 | 426.2 | n/a | n/a | True |
| enemy-06 / enemy | pilot | realtime | 461.120 | n/a | 462.1 | n/a | n/a | False |
| enemy-07 / enemy | pilot | realtime | 364.505 | n/a | 366.3 | n/a | n/a | False |
| enemy-08 / enemy | pilot | realtime | 320.065 | n/a | n/a | n/a | n/a | False |
| enemy-09 / enemy | pilot | realtime | 690.952 | n/a | 694.7 | n/a | n/a | False |
| enemy-10 / enemy | pilot | realtime | 803.466 | n/a | 806.4 | n/a | n/a | False |
| enemy-11 / enemy | pilot | realtime | 659.240 | 662.9 | 662.9 | n/a | n/a | False |
| enemy-12 / enemy | pilot | realtime | 771.165 | 771.8 | 771.8 | n/a | n/a | False |
| enemy-13 / enemy | pilot | realtime | 627.117 | 629.2 | 629.2 | n/a | n/a | True |
| enemy-14 / enemy | pilot | realtime | 417.951 | 418.3 | 418.3 | n/a | n/a | False |
| enemy-15 / enemy | pilot | realtime | 539.931 | n/a | 543.9 | 540.0 | 540.1 | False |
| enemy-16 / enemy | pilot | realtime | 621.694 | 622.2 | 622.2 | 621.7 | 621.8 | False |
| enemy-17 / enemy | pilot | realtime | 154.015 | 155.5 | 155.5 | 155.9 | 156.0 | False |
| enemy-18 / enemy | pilot | realtime | 205.163 | 205.8 | 205.8 | n/a | n/a | False |
| enemy-19 / enemy | pilot | realtime | 672.947 | 675.1 | 675.1 | n/a | n/a | False |
| enemy-20 / enemy | pilot | realtime | 819.069 | 820.0 | 820.0 | n/a | n/a | False |
| wanted-04 / wanted | pilot | realtime | 300.220 | n/a | n/a | 300.2 | 300.3 | False |
| wanted-05 / wanted | pilot | realtime | 291.850 | n/a | 293.1 | 291.9 | 291.9 | False |
| wanted-06 / wanted | pilot | realtime | 163.943 | n/a | 166.1 | 164.0 | 164.0 | False |
| wanted-07 / wanted | pilot | realtime | 655.364 | n/a | 655.6 | 655.4 | 655.4 | False |
| calm-walk-04 / calm | pilot | realtime | 328.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-05 / calm | pilot | realtime | 358.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-06 / calm | pilot | realtime | 156.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-07 / calm | pilot | realtime | 186.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-08 / calm | pilot | realtime | 216.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-09 / calm | pilot | realtime | 142.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-10 / calm | pilot | realtime | 513.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-11 / calm | pilot | realtime | 162.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-12 / calm | pilot | realtime | 500.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-13 / calm | pilot | realtime | 732.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-14 / calm | pilot | realtime | 767.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-15 / calm | pilot | realtime | 683.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-16 / calm | pilot | realtime | 277.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-17 / calm | pilot | realtime | 773.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-18 / calm | pilot | realtime | 141.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-19 / calm | pilot | realtime | 67.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-20 / calm | pilot | realtime | 111.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-21 / calm | pilot | realtime | 131.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-22 / calm | pilot | realtime | 276.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-23 / calm | pilot | realtime | 82.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-24 / calm | pilot | realtime | 242.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-25 / calm | pilot | realtime | 88.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-26 / calm | pilot | realtime | 164.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-27 / calm | pilot | realtime | 780.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-28 / calm | pilot | realtime | 31.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-29 / calm | pilot | realtime | 20.000 | n/a | n/a | n/a | n/a | False |
| enemy-01 / enemy | pilot+guard | realtime | 412.498 | n/a | n/a | 412.6 | n/a | False |
| enemy-02 / enemy | pilot+guard | realtime | 395.999 | n/a | 397.4 | 396.1 | n/a | False |
| enemy-03 / enemy | pilot+guard | realtime | 356.219 | n/a | 356.4 | 356.3 | n/a | False |
| wanted-02 / wanted | pilot+guard | realtime | 391.332 | 392.1 | 392.1 | 391.5 | 391.4 | False |
| wanted-03 / wanted | pilot+guard | realtime | 209.426 | n/a | 210.6 | n/a | 209.6 | False |
| calm-walk-01 / calm | pilot+guard | realtime | 12.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-02 / calm | pilot+guard | realtime | 489.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-03 / calm | pilot+guard | realtime | 499.000 | n/a | n/a | n/a | n/a | False |
| enemy-04 / enemy | pilot+guard | realtime | 410.845 | 412.5 | 412.5 | n/a | n/a | True |
| enemy-05 / enemy | pilot+guard | realtime | 425.519 | 426.2 | 426.2 | n/a | n/a | True |
| enemy-06 / enemy | pilot+guard | realtime | 461.120 | n/a | 462.1 | 461.2 | 465.0 | False |
| enemy-07 / enemy | pilot+guard | realtime | 364.505 | n/a | 366.3 | 364.6 | 366.9 | False |
| enemy-08 / enemy | pilot+guard | realtime | 320.065 | n/a | n/a | 320.2 | 323.3 | False |
| enemy-09 / enemy | pilot+guard | realtime | 690.952 | n/a | 694.7 | 691.0 | 693.1 | False |
| enemy-10 / enemy | pilot+guard | realtime | 803.466 | n/a | 806.4 | 803.5 | n/a | False |
| enemy-11 / enemy | pilot+guard | realtime | 659.240 | 662.9 | 662.9 | 659.3 | n/a | False |
| enemy-12 / enemy | pilot+guard | realtime | 771.165 | 771.8 | 771.8 | 771.2 | 771.2 | False |
| enemy-13 / enemy | pilot+guard | realtime | 627.117 | 629.2 | 629.2 | 627.2 | 629.5 | False |
| enemy-14 / enemy | pilot+guard | realtime | 417.951 | 418.3 | 418.3 | 418.0 | 419.5 | False |
| enemy-15 / enemy | pilot+guard | realtime | 539.931 | n/a | 543.9 | 540.0 | n/a | False |
| enemy-16 / enemy | pilot+guard | realtime | 621.694 | 622.2 | 622.2 | 621.7 | n/a | False |
| enemy-17 / enemy | pilot+guard | realtime | 154.015 | 155.5 | 155.5 | 154.1 | 154.1 | False |
| enemy-18 / enemy | pilot+guard | realtime | 205.163 | 205.8 | 205.8 | 205.2 | 205.2 | False |
| enemy-19 / enemy | pilot+guard | realtime | 672.947 | 675.1 | 675.1 | 673.0 | n/a | False |
| enemy-20 / enemy | pilot+guard | realtime | 819.069 | 820.0 | 820.0 | 819.2 | 822.8 | False |
| wanted-04 / wanted | pilot+guard | realtime | 300.220 | n/a | n/a | 300.4 | 300.3 | False |
| wanted-05 / wanted | pilot+guard | realtime | 291.850 | n/a | 293.1 | 292.0 | 291.9 | False |
| wanted-06 / wanted | pilot+guard | realtime | 163.943 | n/a | 166.1 | 164.1 | 164.0 | False |
| wanted-07 / wanted | pilot+guard | realtime | 655.364 | n/a | 655.6 | 655.5 | 655.4 | False |
| calm-walk-04 / calm | pilot+guard | realtime | 328.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-05 / calm | pilot+guard | realtime | 358.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-06 / calm | pilot+guard | realtime | 156.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-07 / calm | pilot+guard | realtime | 186.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-08 / calm | pilot+guard | realtime | 216.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-09 / calm | pilot+guard | realtime | 142.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-10 / calm | pilot+guard | realtime | 513.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-11 / calm | pilot+guard | realtime | 162.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-12 / calm | pilot+guard | realtime | 500.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-13 / calm | pilot+guard | realtime | 732.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-14 / calm | pilot+guard | realtime | 767.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-15 / calm | pilot+guard | realtime | 683.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-16 / calm | pilot+guard | realtime | 277.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-17 / calm | pilot+guard | realtime | 773.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-18 / calm | pilot+guard | realtime | 141.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-19 / calm | pilot+guard | realtime | 67.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-20 / calm | pilot+guard | realtime | 111.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-21 / calm | pilot+guard | realtime | 131.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-22 / calm | pilot+guard | realtime | 276.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-23 / calm | pilot+guard | realtime | 82.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-24 / calm | pilot+guard | realtime | 242.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-25 / calm | pilot+guard | realtime | 88.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-26 / calm | pilot+guard | realtime | 164.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-27 / calm | pilot+guard | realtime | 780.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-28 / calm | pilot+guard | realtime | 31.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-29 / calm | pilot+guard | realtime | 20.000 | n/a | n/a | n/a | n/a | False |
| enemy-01 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 412.498 | n/a | n/a | n/a | n/a | False |
| enemy-02 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 395.999 | n/a | 397.4 | n/a | n/a | False |
| enemy-03 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 356.219 | n/a | 356.4 | n/a | n/a | False |
| wanted-02 / wanted | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 391.332 | 392.1 | 392.1 | 391.8 | n/a | False |
| wanted-03 / wanted | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 209.426 | n/a | 210.6 | 209.9 | n/a | False |
| calm-walk-01 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 12.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-02 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 489.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-03 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 499.000 | n/a | n/a | n/a | n/a | False |
| enemy-04 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 410.845 | 412.5 | 412.5 | n/a | n/a | False |
| enemy-05 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 425.519 | 426.2 | 426.2 | n/a | n/a | False |
| enemy-06 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 461.120 | n/a | 462.1 | n/a | n/a | False |
| enemy-07 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 364.505 | n/a | 366.3 | n/a | n/a | False |
| enemy-08 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 320.065 | n/a | n/a | n/a | n/a | False |
| enemy-09 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 690.952 | n/a | 694.7 | 693.5 | n/a | False |
| enemy-10 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 803.466 | n/a | 806.4 | n/a | n/a | False |
| enemy-11 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 659.240 | 662.9 | 662.9 | n/a | n/a | False |
| enemy-12 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 771.165 | 771.8 | 771.8 | n/a | n/a | False |
| enemy-13 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 627.117 | 629.2 | 629.2 | n/a | n/a | False |
| enemy-14 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 417.951 | 418.3 | 418.3 | n/a | n/a | False |
| enemy-15 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 539.931 | n/a | 543.9 | n/a | n/a | False |
| enemy-16 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 621.694 | 622.2 | 622.2 | n/a | n/a | False |
| enemy-17 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 154.015 | 155.5 | 155.5 | n/a | n/a | False |
| enemy-18 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 205.163 | 205.8 | 205.8 | n/a | n/a | False |
| enemy-19 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 672.947 | 675.1 | 675.1 | n/a | n/a | False |
| enemy-20 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 819.069 | 820.0 | 820.0 | n/a | n/a | False |
| wanted-04 / wanted | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 300.220 | n/a | n/a | 300.7 | n/a | False |
| wanted-05 / wanted | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 291.850 | n/a | 293.1 | 292.4 | n/a | False |
| wanted-06 / wanted | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 163.943 | n/a | 166.1 | 164.4 | n/a | False |
| wanted-07 / wanted | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 655.364 | n/a | 655.6 | 655.9 | n/a | False |
| calm-walk-04 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 328.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-05 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 358.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-06 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 156.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-07 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 186.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-08 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 216.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-09 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 142.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-10 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 513.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-11 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 162.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-12 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 500.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-13 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 732.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-14 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 767.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-15 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 683.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-16 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 277.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-17 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 773.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-18 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 141.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-19 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 67.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-20 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 111.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-21 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 131.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-22 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 276.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-23 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 82.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-24 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 242.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-25 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 88.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-26 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 164.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-27 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 780.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-28 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 31.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-29 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 20.000 | n/a | n/a | n/a | n/a | False |
| enemy-01 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 412.498 | n/a | n/a | 412.6 | n/a | False |
| enemy-02 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 395.999 | n/a | 397.4 | 396.1 | n/a | False |
| enemy-03 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 356.219 | n/a | 356.4 | 356.3 | n/a | False |
| wanted-02 / wanted | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 391.332 | 392.1 | 392.1 | 391.4 | 391.4 | False |
| wanted-03 / wanted | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 209.426 | n/a | 210.6 | n/a | 209.5 | False |
| calm-walk-01 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 12.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-02 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 489.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-03 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 499.000 | n/a | n/a | n/a | n/a | False |
| enemy-04 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 410.845 | 412.5 | 412.5 | n/a | n/a | True |
| enemy-05 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 425.519 | 426.2 | 426.2 | n/a | n/a | True |
| enemy-06 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 461.120 | n/a | 462.1 | 461.2 | 465.0 | False |
| enemy-07 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 364.505 | n/a | 366.3 | 364.6 | 366.9 | False |
| enemy-08 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 320.065 | n/a | n/a | 320.1 | n/a | False |
| enemy-09 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 690.952 | n/a | 694.7 | 691.0 | 693.1 | False |
| enemy-10 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 803.466 | n/a | 806.4 | 803.5 | n/a | False |
| enemy-11 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 659.240 | 662.9 | 662.9 | 659.3 | n/a | False |
| enemy-12 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 771.165 | 771.8 | 771.8 | 771.2 | 771.2 | False |
| enemy-13 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 627.117 | 629.2 | 629.2 | 627.2 | 629.5 | False |
| enemy-14 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 417.951 | 418.3 | 418.3 | 418.0 | 419.5 | False |
| enemy-15 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 539.931 | n/a | 543.9 | 540.0 | n/a | False |
| enemy-16 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 621.694 | 622.2 | 622.2 | 621.7 | n/a | False |
| enemy-17 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 154.015 | 155.5 | 155.5 | 154.1 | 154.1 | False |
| enemy-18 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 205.163 | 205.8 | 205.8 | 205.2 | 205.2 | False |
| enemy-19 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 672.947 | 675.1 | 675.1 | 673.0 | n/a | False |
| enemy-20 / enemy | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 819.069 | 820.0 | 820.0 | 819.1 | 822.8 | False |
| wanted-04 / wanted | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 300.220 | n/a | n/a | 300.3 | 300.3 | False |
| wanted-05 / wanted | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 291.850 | n/a | 293.1 | 292.0 | 292.0 | False |
| wanted-06 / wanted | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 163.943 | n/a | 166.1 | 164.1 | 164.1 | False |
| wanted-07 / wanted | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 655.364 | n/a | 655.6 | 655.5 | 655.5 | False |
| calm-walk-04 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 328.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-05 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 358.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-06 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 156.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-07 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 186.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-08 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 216.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-09 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 142.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-10 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 513.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-11 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 162.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-12 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 500.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-13 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 732.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-14 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 767.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-15 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 683.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-16 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 277.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-17 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 773.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-18 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 141.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-19 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 67.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-20 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 111.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-21 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 131.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-22 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 276.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-23 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 82.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-24 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 242.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-25 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 88.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-26 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 164.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-27 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 780.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-28 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 31.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-29 / calm | head+guard (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 20.000 | n/a | n/a | n/a | n/a | False |
