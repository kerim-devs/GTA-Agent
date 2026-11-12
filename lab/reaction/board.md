# First-reaction bench

Every number inherits the mode in its row. Two times per try: noticed is the first tick on which the way of control decides anything because of the threat, by its own account; answered is the first pad from the scene's answer set. For Kerim only the pad exists. Missing answers are not zero. Time statistics include noticed or answered, non-void threat scenes only; a state held in the two seconds before the onset voids the try. Repetitions are separate trials. Pilot/head use cached timestamped OCR and no object reader; their measured wall-clock results do not include fresh OCR/object inference. Delayed-stub rows measure a local reader stub, not model quality. A head delay row runs in real time with a head answer delayed by a modelled time. The recording never responds to these pads.

Link addition: 135 ms; docs/LOG.md:15: camera measurement, 60 fps, 10 samples, median 135 ms. Rows of implementation SHA-256 7f28da3db54e8dfc56b57906b7d3e873c847f4e918eb46ed9d18d68fb8006d34, scenes SHA-256 7b083561b41e90c4e3d9820f4fc7a070fae3322283c42a0b8e709e24eb2e642d.

| Approach | Mode | Threat/calm trials | Noticed ≤3s | Noticed median / p90 / worst ms | Answered ≤3s | Answered median / p90 / worst ms | Answered with link ms | False notices | False answers | Calm / scene / min | Decision ms | Hz |
|---|---|---:|---:|---|---:|---|---|---:|---:|---|---:|---:|
| Kerim | recorded-human-default | 8/9 | n/a | n/a | 50.0% | 682.2 / 2775.5 / 3651.5 | 817.2 / 2910.5 / 3786.5 | n/a | 98 | 10.6 / 71.2 | n/a | n/a |
| Kerim, looser reading: first new press after the onset | recorded-human-default | 8/9 | n/a | n/a | 62.5% | 2200.9 / 3827.2 / 3996.0 | 2335.9 / 3962.2 / 4131.0 | n/a | 98 | 10.6 / 71.2 | n/a | n/a |
| Kerim | recorded-human-estimated | 18/20 | n/a | n/a | 38.9% | 973.9 / 2106.6 / 2115.7 | 1108.9 / 2241.6 / 2250.7 | n/a | 98 | 3.9 / 25.7 | n/a | n/a |
| Kerim, looser reading: first new press after the onset | recorded-human-estimated | 18/20 | n/a | n/a | 83.3% | 1132.3 / 2109.7 / 2149.7 | 1267.3 / 2244.7 / 2284.7 | n/a | 98 | 3.9 / 25.7 | n/a | n/a |
| head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 26/29 | 26.9% | 539.9 / 2784.4 / 3475.3 | 0.0% | n/a / n/a / n/a | n/a / n/a / n/a | 0 | 0 | 0.0 / 0.0 | 12.9 | 30.0 |
| judge (qwen/qwen3-vl-8b, json question) | realtime | 26/29 | 15.4% | 2044.2 / 3217.5 / 3277.2 | 15.4% | 2044.2 / 3217.5 / 3277.2 | 2179.2 / 3352.5 / 3412.2 | 15 | 15 | 0.0 / 0.0 | 516.2 | 30.0 |
| judge (qwen/qwen3-vl-8b, letter question) | realtime | 26/29 | 19.2% | 2639.9 / 3105.5 / 3271.1 | 19.2% | 2639.9 / 3105.5 / 3271.1 | 2774.9 / 3240.5 / 3406.1 | 12 | 12 | 0.0 / 0.0 | 298.8 | 30.0 |
| judge-second (qwen/qwen3-vl-8b, json question) | realtime | 26/29 | 11.5% | 1427.8 / 3096.7 / 3375.3 | 19.2% | 1339.1 / 2560.4 / 2705.0 | 1474.1 / 2695.4 / 2840.0 | 15 | 7 | 0.0 / 0.0 | 531.9 | 30.0 |
| judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 26/29 | 15.4% | 2867.2 / 3285.0 / 3333.5 | 11.5% | 2334.3 / 3528.4 / 3541.5 | 2469.3 / 3663.4 / 3676.5 | 13 | 6 | 0.0 / 0.0 | 298.0 | 30.0 |
| pilot | realtime | 26/29 | 34.6% | 14.3 / 815.3 / 1900.2 | 30.8% | 75.4 / 689.1 / 1971.3 | 210.4 / 824.1 / 2106.3 | 2 | 19 | 0.0 / 0.0 | 14.0 | 29.9 |
| policy (nitrogen) | realtime | 26/29 | n/a | n/a | 15.4% | 623.3 / 1408.2 / 1711.3 | 758.3 / 1543.2 / 1846.3 | n/a | 200 | 5.4 / 32.5 | 348.4 | 30.0 |
| reflex | realtime | 26/29 | 88.5% | 36.5 / 1265.6 / 1671.0 | 53.8% | 422.8 / 3072.0 / 3904.2 | 557.8 / 3207.0 / 4039.2 | 9 | 0 | 0.0 / 0.0 | 13.1 | 30.0 |
| reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 26/29 | 61.5% | 25.4 / 1421.1 / 1812.4 | 38.5% | 538.5 / 3330.3 / 3714.1 | 673.5 / 3465.3 / 3849.1 | 20 | 11 | 0.0 / 0.0 | 514.9 | 30.0 |
| reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 26/29 | 57.7% | 12.6 / 1127.5 / 1436.2 | 42.3% | 13.4 / 2921.2 / 3576.1 | 148.4 / 3056.2 / 3711.1 | 20 | 10 | 0.0 / 0.0 | 297.7 | 30.0 |

## Model answers

One line per way of control that asks a model. Time per answer is from the request to the reply. Named: the share of threat scenes on which an answer about a frame from the onset on names any threat, and the median number of such answers it took. False calls: the share of answers that call a threat on calm scenes and on the six seconds before each onset.

| Approach | Mode | Answers (errors) | Per answer median / p90 / worst ms | Threat named | Answers to name it | False calls calm | False calls before onset |
|---|---|---:|---|---:|---:|---:|---:|
| judge (qwen/qwen3-vl-8b, json question) | realtime | 1595 (0) | 311.6 / 417.1 / 763.2 | 57.7% | 5.0 | 0.0% of 789 | 16.0% of 470 |
| judge (qwen/qwen3-vl-8b, letter question) | realtime | 2830 (0) | 166.4 / 254.9 / 487.3 | 50.0% | 11.0 | 0.0% of 1413 | 14.9% of 851 |

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
| wanted-03 / wanted | reflex | realtime | 209.426 | n/a | 210.6 | n/a | 210.2 | False |
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
| enemy-15 / enemy | reflex | realtime | 539.931 | n/a | 543.9 | 540.6 | n/a | False |
| enemy-16 / enemy | reflex | realtime | 621.694 | 622.2 | 622.2 | 622.4 | n/a | False |
| enemy-17 / enemy | reflex | realtime | 154.015 | 155.5 | 155.5 | 154.0 | 154.0 | False |
| enemy-18 / enemy | reflex | realtime | 205.163 | 205.8 | 205.8 | 205.2 | 205.2 | False |
| enemy-19 / enemy | reflex | realtime | 672.947 | 675.1 | 675.1 | 673.0 | n/a | False |
| enemy-20 / enemy | reflex | realtime | 819.069 | 820.0 | 820.0 | 819.1 | 822.8 | False |
| wanted-04 / wanted | reflex | realtime | 300.220 | n/a | n/a | 300.2 | 300.2 | False |
| wanted-05 / wanted | reflex | realtime | 291.850 | n/a | 293.1 | 291.9 | 291.9 | False |
| wanted-06 / wanted | reflex | realtime | 163.943 | n/a | 166.1 | 163.9 | 163.9 | False |
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
| enemy-01 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 412.498 | n/a | n/a | n/a | n/a | False |
| enemy-02 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 395.999 | n/a | 397.4 | n/a | n/a | False |
| enemy-03 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 356.219 | n/a | 356.4 | n/a | n/a | False |
| wanted-02 / wanted | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 391.332 | 392.1 | 392.1 | 391.9 | n/a | False |
| wanted-03 / wanted | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 209.426 | n/a | 210.6 | 210.0 | n/a | False |
| calm-walk-01 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 12.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-02 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 489.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-03 / calm | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 499.000 | n/a | n/a | n/a | n/a | False |
| enemy-04 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 410.845 | 412.5 | 412.5 | 414.3 | n/a | False |
| enemy-05 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 425.519 | 426.2 | 426.2 | n/a | n/a | False |
| enemy-06 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 461.120 | n/a | 462.1 | n/a | n/a | False |
| enemy-07 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 364.505 | n/a | 366.3 | n/a | n/a | False |
| enemy-08 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 320.065 | n/a | n/a | n/a | n/a | False |
| enemy-09 / enemy | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 690.952 | n/a | 694.7 | 693.4 | n/a | False |
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
| wanted-04 / wanted | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 300.220 | n/a | n/a | 300.8 | n/a | False |
| wanted-05 / wanted | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 291.850 | n/a | 293.1 | 292.4 | n/a | False |
| wanted-06 / wanted | head (codex-delay-modelled, head delay 8.47 s) | realtime, head delay modelled | 163.943 | n/a | 166.1 | 164.5 | n/a | False |
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
| enemy-01 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 412.498 | n/a | n/a | 414.9 | 414.9 | False |
| enemy-02 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 395.999 | n/a | 397.4 | n/a | n/a | False |
| enemy-03 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 356.219 | n/a | 356.4 | n/a | n/a | True |
| wanted-02 / wanted | judge (qwen/qwen3-vl-8b, letter question) | realtime | 391.332 | 392.1 | 392.1 | n/a | n/a | False |
| wanted-03 / wanted | judge (qwen/qwen3-vl-8b, letter question) | realtime | 209.426 | n/a | 210.6 | n/a | n/a | False |
| calm-walk-01 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 12.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-02 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 489.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-03 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 499.000 | n/a | n/a | n/a | n/a | False |
| enemy-04 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 410.845 | 412.5 | 412.5 | n/a | n/a | True |
| enemy-05 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 425.519 | 426.2 | 426.2 | 427.6 | 427.6 | False |
| enemy-06 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 461.120 | n/a | 462.1 | n/a | n/a | True |
| enemy-07 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 364.505 | n/a | 366.3 | n/a | n/a | True |
| enemy-08 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 320.065 | n/a | n/a | n/a | n/a | True |
| enemy-09 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 690.952 | n/a | 694.7 | n/a | n/a | False |
| enemy-10 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 803.466 | n/a | 806.4 | 806.7 | 806.7 | False |
| enemy-11 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 659.240 | 662.9 | 662.9 | n/a | n/a | False |
| enemy-12 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 771.165 | 771.8 | 771.8 | 774.0 | 774.0 | False |
| enemy-13 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 627.117 | 629.2 | 629.2 | n/a | n/a | False |
| enemy-14 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 417.951 | 418.3 | 418.3 | n/a | n/a | True |
| enemy-15 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 539.931 | n/a | 543.9 | n/a | n/a | False |
| enemy-16 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 621.694 | 622.2 | 622.2 | n/a | n/a | False |
| enemy-17 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 154.015 | 155.5 | 155.5 | n/a | n/a | True |
| enemy-18 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 205.163 | 205.8 | 205.8 | 206.1 | 206.1 | False |
| enemy-19 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 672.947 | 675.1 | 675.1 | 675.9 | 675.9 | False |
| enemy-20 / enemy | judge (qwen/qwen3-vl-8b, letter question) | realtime | 819.069 | 820.0 | 820.0 | n/a | n/a | False |
| wanted-04 / wanted | judge (qwen/qwen3-vl-8b, letter question) | realtime | 300.220 | n/a | n/a | n/a | n/a | False |
| wanted-05 / wanted | judge (qwen/qwen3-vl-8b, letter question) | realtime | 291.850 | n/a | 293.1 | n/a | n/a | False |
| wanted-06 / wanted | judge (qwen/qwen3-vl-8b, letter question) | realtime | 163.943 | n/a | 166.1 | n/a | n/a | True |
| wanted-07 / wanted | judge (qwen/qwen3-vl-8b, letter question) | realtime | 655.364 | n/a | 655.6 | n/a | n/a | False |
| calm-walk-04 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 328.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-05 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 358.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-06 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 156.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-07 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 186.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-08 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 216.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-09 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 142.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-10 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 513.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-11 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 162.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-12 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 500.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-13 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 732.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-14 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 767.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-15 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 683.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-16 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 277.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-17 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 773.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-18 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 141.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-19 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 67.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-20 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 111.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-21 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 131.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-22 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 276.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-23 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 82.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-24 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 242.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-25 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 88.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-26 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 164.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-27 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 780.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-28 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 31.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-29 / calm | judge (qwen/qwen3-vl-8b, letter question) | realtime | 20.000 | n/a | n/a | n/a | n/a | False |
| enemy-01 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 412.498 | n/a | n/a | n/a | n/a | True |
| enemy-02 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 395.999 | n/a | 397.4 | n/a | n/a | False |
| enemy-03 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 356.219 | n/a | 356.4 | n/a | n/a | True |
| wanted-02 / wanted | judge (qwen/qwen3-vl-8b, json question) | realtime | 391.332 | 392.1 | 392.1 | n/a | n/a | True |
| wanted-03 / wanted | judge (qwen/qwen3-vl-8b, json question) | realtime | 209.426 | n/a | 210.6 | n/a | n/a | True |
| calm-walk-01 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 12.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-02 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 489.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-03 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 499.000 | n/a | n/a | n/a | n/a | False |
| enemy-04 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 410.845 | 412.5 | 412.5 | n/a | n/a | True |
| enemy-05 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 425.519 | 426.2 | 426.2 | 427.4 | 427.4 | False |
| enemy-06 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 461.120 | n/a | 462.1 | n/a | n/a | True |
| enemy-07 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 364.505 | n/a | 366.3 | n/a | n/a | True |
| enemy-08 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 320.065 | n/a | n/a | n/a | n/a | True |
| enemy-09 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 690.952 | n/a | 694.7 | n/a | n/a | True |
| enemy-10 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 803.466 | n/a | 806.4 | 806.7 | 806.7 | False |
| enemy-11 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 659.240 | 662.9 | 662.9 | n/a | n/a | False |
| enemy-12 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 771.165 | 771.8 | 771.8 | n/a | n/a | False |
| enemy-13 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 627.117 | 629.2 | 629.2 | n/a | n/a | False |
| enemy-14 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 417.951 | 418.3 | 418.3 | n/a | n/a | False |
| enemy-15 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 539.931 | n/a | 543.9 | 543.0 | 543.0 | False |
| enemy-16 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 621.694 | 622.2 | 622.2 | n/a | n/a | False |
| enemy-17 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 154.015 | 155.5 | 155.5 | n/a | n/a | True |
| enemy-18 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 205.163 | 205.8 | 205.8 | 206.9 | 206.9 | False |
| enemy-19 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 672.947 | 675.1 | 675.1 | 676.1 | 676.1 | False |
| enemy-20 / enemy | judge (qwen/qwen3-vl-8b, json question) | realtime | 819.069 | 820.0 | 820.0 | n/a | n/a | False |
| wanted-04 / wanted | judge (qwen/qwen3-vl-8b, json question) | realtime | 300.220 | n/a | n/a | n/a | n/a | False |
| wanted-05 / wanted | judge (qwen/qwen3-vl-8b, json question) | realtime | 291.850 | n/a | 293.1 | 293.9 | 293.9 | False |
| wanted-06 / wanted | judge (qwen/qwen3-vl-8b, json question) | realtime | 163.943 | n/a | 166.1 | 165.7 | 165.7 | False |
| wanted-07 / wanted | judge (qwen/qwen3-vl-8b, json question) | realtime | 655.364 | n/a | 655.6 | n/a | n/a | True |
| calm-walk-04 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 328.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-05 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 358.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-06 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 156.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-07 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 186.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-08 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 216.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-09 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 142.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-10 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 513.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-11 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 162.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-12 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 500.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-13 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 732.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-14 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 767.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-15 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 683.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-16 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 277.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-17 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 773.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-18 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 141.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-19 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 67.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-20 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 111.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-21 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 131.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-22 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 276.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-23 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 82.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-24 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 242.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-25 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 88.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-26 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 164.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-27 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 780.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-28 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 31.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-29 / calm | judge (qwen/qwen3-vl-8b, json question) | realtime | 20.000 | n/a | n/a | n/a | n/a | False |
| enemy-01 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 412.498 | n/a | n/a | 415.4 | n/a | False |
| enemy-02 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 395.999 | n/a | 397.4 | n/a | n/a | False |
| enemy-03 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 356.219 | n/a | 356.4 | n/a | n/a | True |
| wanted-02 / wanted | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 391.332 | 392.1 | 392.1 | n/a | n/a | False |
| wanted-03 / wanted | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 209.426 | n/a | 210.6 | n/a | n/a | False |
| calm-walk-01 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 12.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-02 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 489.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-03 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 499.000 | n/a | n/a | n/a | n/a | False |
| enemy-04 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 410.845 | 412.5 | 412.5 | n/a | n/a | True |
| enemy-05 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 425.519 | 426.2 | 426.2 | 427.7 | 427.9 | False |
| enemy-06 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 461.120 | n/a | 462.1 | n/a | 464.6 | False |
| enemy-07 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 364.505 | n/a | 366.3 | n/a | n/a | True |
| enemy-08 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 320.065 | n/a | n/a | n/a | n/a | True |
| enemy-09 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 690.952 | n/a | 694.7 | n/a | n/a | False |
| enemy-10 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 803.466 | n/a | 806.4 | 806.8 | 807.0 | False |
| enemy-11 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 659.240 | 662.9 | 662.9 | n/a | n/a | False |
| enemy-12 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 771.165 | 771.8 | 771.8 | n/a | n/a | False |
| enemy-13 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 627.117 | 629.2 | 629.2 | n/a | n/a | False |
| enemy-14 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 417.951 | 418.3 | 418.3 | n/a | n/a | True |
| enemy-15 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 539.931 | n/a | 543.9 | 542.8 | n/a | False |
| enemy-16 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 621.694 | 622.2 | 622.2 | n/a | n/a | False |
| enemy-17 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 154.015 | 155.5 | 155.5 | n/a | n/a | True |
| enemy-18 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 205.163 | 205.8 | 205.8 | 206.4 | 206.7 | False |
| enemy-19 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 672.947 | 675.1 | 675.1 | 676.2 | n/a | False |
| enemy-20 / enemy | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 819.069 | 820.0 | 820.0 | n/a | n/a | False |
| wanted-04 / wanted | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 300.220 | n/a | n/a | n/a | n/a | False |
| wanted-05 / wanted | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 291.850 | n/a | 293.1 | n/a | n/a | False |
| wanted-06 / wanted | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 163.943 | n/a | 166.1 | n/a | 164.4 | False |
| wanted-07 / wanted | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 655.364 | n/a | 655.6 | n/a | n/a | False |
| calm-walk-04 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 328.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-05 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 358.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-06 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 156.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-07 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 186.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-08 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 216.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-09 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 142.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-10 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 513.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-11 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 162.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-12 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 500.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-13 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 732.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-14 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 767.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-15 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 683.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-16 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 277.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-17 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 773.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-18 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 141.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-19 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 67.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-20 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 111.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-21 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 131.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-22 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 276.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-23 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 82.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-24 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 242.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-25 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 88.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-26 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 164.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-27 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 780.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-28 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 31.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-29 / calm | judge-second (qwen/qwen3-vl-8b, letter question) | realtime | 20.000 | n/a | n/a | n/a | n/a | False |
| enemy-01 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 412.498 | n/a | n/a | n/a | 413.5 | False |
| enemy-02 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 395.999 | n/a | 397.4 | n/a | n/a | False |
| enemy-03 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 356.219 | n/a | 356.4 | n/a | n/a | True |
| wanted-02 / wanted | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 391.332 | 392.1 | 392.1 | n/a | n/a | True |
| wanted-03 / wanted | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 209.426 | n/a | 210.6 | n/a | n/a | True |
| calm-walk-01 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 12.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-02 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 489.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-03 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 499.000 | n/a | n/a | n/a | n/a | False |
| enemy-04 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 410.845 | 412.5 | 412.5 | n/a | n/a | True |
| enemy-05 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 425.519 | 426.2 | 426.2 | 428.0 | 428.2 | False |
| enemy-06 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 461.120 | n/a | 462.1 | n/a | n/a | False |
| enemy-07 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 364.505 | n/a | 366.3 | n/a | n/a | True |
| enemy-08 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 320.065 | n/a | n/a | n/a | n/a | True |
| enemy-09 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 690.952 | n/a | 694.7 | n/a | n/a | False |
| enemy-10 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 803.466 | n/a | 806.4 | 803.7 | 804.0 | False |
| enemy-11 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 659.240 | 662.9 | 662.9 | n/a | n/a | False |
| enemy-12 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 771.165 | 771.8 | 771.8 | n/a | n/a | False |
| enemy-13 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 627.117 | 629.2 | 629.2 | n/a | n/a | False |
| enemy-14 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 417.951 | 418.3 | 418.3 | n/a | n/a | False |
| enemy-15 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 539.931 | n/a | 543.9 | n/a | n/a | False |
| enemy-16 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 621.694 | 622.2 | 622.2 | n/a | n/a | False |
| enemy-17 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 154.015 | 155.5 | 155.5 | n/a | 156.4 | False |
| enemy-18 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 205.163 | 205.8 | 205.8 | 205.6 | 206.5 | False |
| enemy-19 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 672.947 | 675.1 | 675.1 | 676.3 | n/a | False |
| enemy-20 / enemy | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 819.069 | 820.0 | 820.0 | n/a | n/a | False |
| wanted-04 / wanted | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 300.220 | n/a | n/a | n/a | n/a | False |
| wanted-05 / wanted | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 291.850 | n/a | 293.1 | n/a | n/a | False |
| wanted-06 / wanted | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 163.943 | n/a | 166.1 | n/a | n/a | False |
| wanted-07 / wanted | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 655.364 | n/a | 655.6 | n/a | n/a | False |
| calm-walk-04 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 328.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-05 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 358.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-06 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 156.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-07 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 186.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-08 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 216.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-09 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 142.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-10 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 513.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-11 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 162.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-12 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 500.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-13 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 732.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-14 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 767.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-15 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 683.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-16 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 277.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-17 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 773.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-18 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 141.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-19 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 67.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-20 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 111.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-21 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 131.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-22 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 276.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-23 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 82.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-24 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 242.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-25 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 88.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-26 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 164.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-27 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 780.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-28 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 31.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-29 / calm | judge-second (qwen/qwen3-vl-8b, json question) | realtime | 20.000 | n/a | n/a | n/a | n/a | False |
| enemy-01 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 412.498 | n/a | n/a | 412.6 | n/a | False |
| enemy-02 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 395.999 | n/a | 397.4 | 396.1 | n/a | False |
| enemy-03 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 356.219 | n/a | 356.4 | n/a | n/a | True |
| wanted-02 / wanted | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 391.332 | 392.1 | 392.1 | 391.3 | 391.3 | False |
| wanted-03 / wanted | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 209.426 | n/a | 210.6 | n/a | 210.2 | False |
| calm-walk-01 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 12.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-02 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 489.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-03 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 499.000 | n/a | n/a | n/a | n/a | False |
| enemy-04 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 410.845 | 412.5 | 412.5 | n/a | n/a | True |
| enemy-05 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 425.519 | 426.2 | 426.2 | 426.9 | 427.3 | False |
| enemy-06 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 461.120 | n/a | 462.1 | n/a | n/a | True |
| enemy-07 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 364.505 | n/a | 366.3 | n/a | n/a | True |
| enemy-08 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 320.065 | n/a | n/a | n/a | n/a | True |
| enemy-09 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 690.952 | n/a | 694.7 | 692.4 | n/a | False |
| enemy-10 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 803.466 | n/a | 806.4 | 803.5 | 807.0 | False |
| enemy-11 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 659.240 | 662.9 | 662.9 | 659.2 | n/a | False |
| enemy-12 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 771.165 | 771.8 | 771.8 | 771.2 | 771.2 | False |
| enemy-13 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 627.117 | 629.2 | 629.2 | n/a | n/a | False |
| enemy-14 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 417.951 | 418.3 | 418.3 | n/a | n/a | True |
| enemy-15 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 539.931 | n/a | 543.9 | 540.6 | 542.6 | False |
| enemy-16 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 621.694 | 622.2 | 622.2 | 622.4 | n/a | False |
| enemy-17 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 154.015 | 155.5 | 155.5 | n/a | n/a | True |
| enemy-18 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 205.163 | 205.8 | 205.8 | 205.2 | 205.2 | False |
| enemy-19 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 672.947 | 675.1 | 675.1 | 673.0 | 675.9 | False |
| enemy-20 / enemy | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 819.069 | 820.0 | 820.0 | 819.1 | n/a | False |
| wanted-04 / wanted | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 300.220 | n/a | n/a | 300.2 | 300.2 | False |
| wanted-05 / wanted | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 291.850 | n/a | 293.1 | 291.9 | 291.9 | False |
| wanted-06 / wanted | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 163.943 | n/a | 166.1 | n/a | 164.0 | False |
| wanted-07 / wanted | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 655.364 | n/a | 655.6 | n/a | 655.4 | False |
| calm-walk-04 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 328.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-05 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 358.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-06 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 156.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-07 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 186.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-08 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 216.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-09 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 142.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-10 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 513.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-11 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 162.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-12 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 500.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-13 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 732.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-14 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 767.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-15 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 683.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-16 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 277.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-17 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 773.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-18 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 141.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-19 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 67.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-20 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 111.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-21 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 131.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-22 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 276.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-23 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 82.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-24 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 242.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-25 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 88.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-26 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 164.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-27 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 780.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-28 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 31.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-29 / calm | reflex+judge (qwen/qwen3-vl-8b, letter question) | realtime | 20.000 | n/a | n/a | n/a | n/a | False |
| enemy-01 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 412.498 | n/a | n/a | n/a | n/a | True |
| enemy-02 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 395.999 | n/a | 397.4 | 396.1 | n/a | False |
| enemy-03 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 356.219 | n/a | 356.4 | n/a | n/a | True |
| wanted-02 / wanted | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 391.332 | 392.1 | 392.1 | 391.3 | 391.3 | False |
| wanted-03 / wanted | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 209.426 | n/a | 210.6 | n/a | n/a | True |
| calm-walk-01 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 12.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-02 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 489.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-03 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 499.000 | n/a | n/a | n/a | n/a | False |
| enemy-04 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 410.845 | 412.5 | 412.5 | n/a | n/a | True |
| enemy-05 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 425.519 | 426.2 | 426.2 | 426.9 | 427.2 | False |
| enemy-06 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 461.120 | n/a | 462.1 | 462.9 | 463.9 | False |
| enemy-07 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 364.505 | n/a | 366.3 | n/a | n/a | True |
| enemy-08 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 320.065 | n/a | n/a | n/a | n/a | True |
| enemy-09 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 690.952 | n/a | 694.7 | 692.4 | n/a | False |
| enemy-10 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 803.466 | n/a | 806.4 | 803.5 | 804.0 | False |
| enemy-11 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 659.240 | 662.9 | 662.9 | 659.3 | n/a | False |
| enemy-12 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 771.165 | 771.8 | 771.8 | 771.2 | 771.2 | False |
| enemy-13 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 627.117 | 629.2 | 629.2 | n/a | n/a | False |
| enemy-14 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 417.951 | 418.3 | 418.3 | 418.0 | 419.6 | False |
| enemy-15 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 539.931 | n/a | 543.9 | 540.6 | 543.3 | False |
| enemy-16 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 621.694 | 622.2 | 622.2 | 622.4 | n/a | False |
| enemy-17 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 154.015 | 155.5 | 155.5 | 154.0 | 154.0 | False |
| enemy-18 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 205.163 | 205.8 | 205.8 | 205.2 | 205.2 | False |
| enemy-19 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 672.947 | 675.1 | 675.1 | 673.0 | 676.1 | False |
| enemy-20 / enemy | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 819.069 | 820.0 | 820.0 | 819.1 | 822.8 | False |
| wanted-04 / wanted | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 300.220 | n/a | n/a | n/a | n/a | True |
| wanted-05 / wanted | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 291.850 | n/a | 293.1 | 291.9 | 291.9 | False |
| wanted-06 / wanted | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 163.943 | n/a | 166.1 | n/a | 163.9 | False |
| wanted-07 / wanted | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 655.364 | n/a | 655.6 | n/a | n/a | True |
| calm-walk-04 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 328.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-05 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 358.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-06 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 156.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-07 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 186.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-08 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 216.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-09 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 142.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-10 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 513.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-11 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 162.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-12 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 500.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-13 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 732.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-14 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 767.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-15 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 683.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-16 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 277.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-17 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 773.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-18 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 141.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-19 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 67.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-20 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 111.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-21 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 131.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-22 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 276.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-23 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 82.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-24 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 242.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-25 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 88.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-26 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 164.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-27 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 780.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-28 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 31.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-29 / calm | reflex+judge (qwen/qwen3-vl-8b, json question) | realtime | 20.000 | n/a | n/a | n/a | n/a | False |
| enemy-01 / enemy | policy (nitrogen) | realtime | 412.498 | n/a | n/a | n/a | 413.2 | False |
| enemy-02 / enemy | policy (nitrogen) | realtime | 395.999 | n/a | 397.4 | n/a | 396.5 | False |
| enemy-03 / enemy | policy (nitrogen) | realtime | 356.219 | n/a | 356.4 | n/a | n/a | True |
| wanted-02 / wanted | policy (nitrogen) | realtime | 391.332 | 392.1 | 392.1 | n/a | n/a | True |
| wanted-03 / wanted | policy (nitrogen) | realtime | 209.426 | n/a | 210.6 | n/a | n/a | True |
| calm-walk-01 / calm | policy (nitrogen) | realtime | 12.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-02 / calm | policy (nitrogen) | realtime | 489.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-03 / calm | policy (nitrogen) | realtime | 499.000 | n/a | n/a | n/a | n/a | False |
| enemy-04 / enemy | policy (nitrogen) | realtime | 410.845 | 412.5 | 412.5 | n/a | n/a | True |
| enemy-05 / enemy | policy (nitrogen) | realtime | 425.519 | 426.2 | 426.2 | n/a | n/a | True |
| enemy-06 / enemy | policy (nitrogen) | realtime | 461.120 | n/a | 462.1 | n/a | n/a | True |
| enemy-07 / enemy | policy (nitrogen) | realtime | 364.505 | n/a | 366.3 | n/a | 366.2 | False |
| enemy-08 / enemy | policy (nitrogen) | realtime | 320.065 | n/a | n/a | n/a | n/a | True |
| enemy-09 / enemy | policy (nitrogen) | realtime | 690.952 | n/a | 694.7 | n/a | n/a | True |
| enemy-10 / enemy | policy (nitrogen) | realtime | 803.466 | n/a | 806.4 | n/a | n/a | True |
| enemy-11 / enemy | policy (nitrogen) | realtime | 659.240 | 662.9 | 662.9 | n/a | n/a | True |
| enemy-12 / enemy | policy (nitrogen) | realtime | 771.165 | 771.8 | 771.8 | n/a | n/a | True |
| enemy-13 / enemy | policy (nitrogen) | realtime | 627.117 | 629.2 | 629.2 | n/a | n/a | True |
| enemy-14 / enemy | policy (nitrogen) | realtime | 417.951 | 418.3 | 418.3 | n/a | n/a | True |
| enemy-15 / enemy | policy (nitrogen) | realtime | 539.931 | n/a | 543.9 | n/a | n/a | True |
| enemy-16 / enemy | policy (nitrogen) | realtime | 621.694 | 622.2 | 622.2 | n/a | n/a | True |
| enemy-17 / enemy | policy (nitrogen) | realtime | 154.015 | 155.5 | 155.5 | n/a | n/a | True |
| enemy-18 / enemy | policy (nitrogen) | realtime | 205.163 | 205.8 | 205.8 | n/a | n/a | True |
| enemy-19 / enemy | policy (nitrogen) | realtime | 672.947 | 675.1 | 675.1 | n/a | n/a | True |
| enemy-20 / enemy | policy (nitrogen) | realtime | 819.069 | 820.0 | 820.0 | n/a | n/a | True |
| wanted-04 / wanted | policy (nitrogen) | realtime | 300.220 | n/a | n/a | n/a | n/a | True |
| wanted-05 / wanted | policy (nitrogen) | realtime | 291.850 | n/a | 293.1 | n/a | 292.0 | False |
| wanted-06 / wanted | policy (nitrogen) | realtime | 163.943 | n/a | 166.1 | n/a | n/a | True |
| wanted-07 / wanted | policy (nitrogen) | realtime | 655.364 | n/a | 655.6 | n/a | n/a | True |
| calm-walk-04 / calm | policy (nitrogen) | realtime | 328.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-05 / calm | policy (nitrogen) | realtime | 358.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-06 / calm | policy (nitrogen) | realtime | 156.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-07 / calm | policy (nitrogen) | realtime | 186.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-08 / calm | policy (nitrogen) | realtime | 216.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-09 / calm | policy (nitrogen) | realtime | 142.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-10 / calm | policy (nitrogen) | realtime | 513.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-11 / calm | policy (nitrogen) | realtime | 162.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-12 / calm | policy (nitrogen) | realtime | 500.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-13 / calm | policy (nitrogen) | realtime | 732.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-14 / calm | policy (nitrogen) | realtime | 767.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-15 / calm | policy (nitrogen) | realtime | 683.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-16 / calm | policy (nitrogen) | realtime | 277.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-17 / calm | policy (nitrogen) | realtime | 773.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-18 / calm | policy (nitrogen) | realtime | 141.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-19 / calm | policy (nitrogen) | realtime | 67.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-20 / calm | policy (nitrogen) | realtime | 111.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-21 / calm | policy (nitrogen) | realtime | 131.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-22 / calm | policy (nitrogen) | realtime | 276.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-23 / calm | policy (nitrogen) | realtime | 82.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-24 / calm | policy (nitrogen) | realtime | 242.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-25 / calm | policy (nitrogen) | realtime | 88.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-26 / calm | policy (nitrogen) | realtime | 164.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-27 / calm | policy (nitrogen) | realtime | 780.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-28 / calm | policy (nitrogen) | realtime | 31.000 | n/a | n/a | n/a | n/a | False |
| calm-walk-29 / calm | policy (nitrogen) | realtime | 20.000 | n/a | n/a | n/a | n/a | False |
