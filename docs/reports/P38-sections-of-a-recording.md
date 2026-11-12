P38 is implemented and evaluated on all eight requested recordings. The accuracy targets are not met: audited strict section recall is 10/19 and 7/23, false sections are 1.66 and 1.72 per five minutes, and the existing judge proxy agrees on 110/158 frames (69.6%, with 41 unknown misses). Runtime passes at 1.806 to 3.581 seconds per recording minute. The full gate passed: 2715 tests passed, 1 skipped and 236 expected failures. All card-owned deliverables and the eight-recording evaluation are present.

The scoped command `env -u PS5_HOST .venv/bin/pytest -q tests/test_sections.py` reports `14 passed in 0.14s`. Scoped Ruff check reports `All checks passed!`, and formatting reports `3 files already formatted`. The required full command is `env -u PS5_HOST .venv/bin/python tools/gate.py --full` from pilot; its completed replacement run is saved in lab/sections/gate.txt. It reports `2715 passed, 1 skipped, 236 xfailed in 585.75s (0:09:45)` and `gate passed in 586.13s (full)`. No checks were disabled. The scoped files were also read after the gate; no further fix was required.

Reproduction from pilot: `env -u PS5_HOST .venv/bin/python ../lab/sections/contact.py /Users/kerim/recordings/kerim/20261111-164039 /Users/kerim/Documents/ChatGPT/gta/recordings/20261110-093238 --out ../lab/sections/contact` creates the independent sheets. The exact eight-recording command is below. `env -u PS5_HOST .venv/bin/python ../lab/sections/evaluate.py` regenerates metrics.json, judge-comparison.json and report-tables.md from the preserved truth files and outputs.

```sh
env -u PS5_HOST .venv/bin/python tools/sections.py \
  /Users/kerim/recordings/kerim/20261111-164039 \
  /Users/kerim/recordings/kerim/20261111-165543 \
  /Users/kerim/recordings/kerim/20261111-171046 \
  /Users/kerim/recordings/kerim/20261111-172549 \
  /Users/kerim/recordings/kerim/20261111-065022 \
  /Users/kerim/Documents/ChatGPT/gta/recordings/20261110-093238 \
  /Users/kerim/recordings/pilot/20261110-231512 \
  /Users/kerim/recordings/kerim/20261111-135510 \
  --out ../lab/sections/out
```

The measured command output is preserved verbatim in lab/sections/timing.txt. Representative lines are `20261111-164039: 27 sections; 53.807s; 3.581s/recording-minute` and `20261111-135510: 1 sections; 51.131s; 2.780s/recording-minute`. Both the Wi-Fi multi-section sheet and the stationary-car sheet were visually checked after generation.

P38 adds an offline recording section reader, a command, deterministic reader-sequence tests and reproducible evaluation artifacts. It reads the existing minimap and HUD readers at 10 Hz on frames.jsonl timestamps. It never instantiates Pipeline, starts OCR or connects to a console. The decision callable accepts a Sample including frame index, source time, wanted level, minimap and aligned human pad, so a later judge can replace it without changing segmentation.

The original truth in lab/sections/truth.json was frozen before the first section run and is preserved unchanged. A later visual audit found missed short overlays, scripted HUD-free animations and source-gap timing errors. The tables below use the explicitly post-run correction in truth-audited.json; initial scores are retained in metrics.json under initial_truth_recordings. No classifier threshold was tuned against either version. Every distinct nearest frame on the one-second contact sheets was visually reviewed, using printed capture timestamps. There are 886 distinct frames for the 901-second afternoon sample and 693 for the 695-second Wi-Fi sample; multiple target seconds can point to the same source frame across gaps. Boundaries have approximately one-second uncertainty. System overlays and unreadable transitions were labelled unknown. The first car entry was placed at 330 seconds, when the player is seated, rather than at the door-opening animation.

Segmentation requires a second of stable clean evidence. A damaged sample cannot call the decision function, advance a boundary, contribute wanted/route/speed, or confirm a change across a long gap. Short unconfirmed changes keep the preceding section. Adjacent equal kinds merge. Sections use half-open intervals except the final source frame. Human activity integrates held human controller events over the exact interval; no human events or a single event means picture-only. Menu screen is the most frequent clean reader screen within a section.

The pixel readers cannot establish that absent minimap means a cutscene, so that case stays unknown. A later judge can emit cutscene. Tilt with wanted stars needs controller evidence; tilt without stars retains the existing geometric vehicle cue. This can still confuse stationary cars, brief entry/exit states, and unusual camera angles. Pad and picture are not latency-corrected; the Wi-Fi source can lag controller events. GPS speed remains null because the current speed reader requires forbidden OCR. The schema accepts injected GPS speed, tested with synthetic reader output. Route share is the fraction of clean sampled drive readings that have a route; damaged is the fraction of all sampled readings marked corrupt.

Against the original pre-run truth, 164039 found 10/13 kinds, 5/13 with both boundaries within two seconds, and 9 false sections (3.00 per five minutes). Wi-Fi found 14/18 kinds, 3/18 with both boundaries within two seconds, and 7 false sections (3.02 per five minutes). The later correction is reported separately below rather than silently replacing these initial results.

Evaluation uses one-to-one same-kind matches by largest temporal overlap. Kind found requires at least half the true interval covered; the strict target additionally requires both boundaries within two seconds. True unknown intervals are excluded from accuracy and false-section scoring. Extra known predictions overlapping known truth by at least half their duration count as false sections, including fragmentation. Unknown predictions count as missed coverage and are reported separately.

| Recording | True >=3s | Kind found | Kind and ends <=2s | False sections | False /5min | Unknown on known truth (s) |
|---|---:|---:|---:|---:|---:|---:|
| 20261111-164039 | 19 | 13 | 10 | 5 | 1.66 | 60.7 |
| 20261110-093238 | 23 | 18 | 7 | 4 | 1.72 | 38.8 |

The target is every true section of at least three seconds with both boundaries within two seconds, and at most one false section per five minutes. Any row below full recall or above 1.00 false sections per five minutes fails that target.
The existing judge truth corrects movement labels only; other labels are inherited from sample.json. This is a partially hand-corrected proxy, not independent complete truth for cutscenes, banners or menus. Unclear frames are excluded. Unknown predictions count as misses. None of the four afternoon recordings or the stationary-car recording appears in that existing sample.
| Judge recording | Correct / eligible | Agreement | Unknown misses |
|---|---:|---:|---:|
| 20261111-065022 | 61/103 | 59.2% | 41 |
| 20261110-093238 | 31/37 | 83.8% | 0 |
| 20261110-231512 | 18/18 | 100.0% | 0 |
| total | 110/158 | 69.6% | 41 |

The judge target is 90%; measured aggregate agreement is 69.6%.
The four afternoon recordings total 53.50 metadata minutes. The section clock accounts for 53.49 minutes; recording setup/tail time outside frame timestamps is not invented.
| Kind | Afternoon minutes |
|---|---:|
| drive | 20.67 |
| foot | 17.60 |
| cutscene | 0.00 |
| menu | 1.28 |
| banner | 0.25 |
| loading | 0.39 |
| unknown | 13.31 |

Timing includes decoding, readers, JSON and midpoint contact sheet output in one process. The performance limit is 10 seconds per recording minute, equivalent to ten minutes per hour. The full gate ran concurrently, so this is an observed end-to-end run under that load.
| Recording | Metadata seconds | Has human pad | Sections | Runtime seconds | Seconds / recording minute |
|---|---:|---|---:|---:|---:|
| 20261110-093238 | 695.9 | True | 28 | 20.947 | 1.806 |
| 20261110-231512 | 240.1 | False | 1 | 11.079 | 2.769 |
| 20261111-065022 | 375.4 | True | 13 | 16.604 | 2.654 |
| 20261111-135510 | 1103.4 | False | 1 | 51.131 | 2.78 |
| 20261111-164039 | 901.5 | True | 27 | 53.807 | 3.581 |
| 20261111-165543 | 901.0 | True | 43 | 51.77 | 3.447 |
| 20261111-171046 | 900.6 | True | 48 | 47.598 | 3.171 |
| 20261111-172549 | 506.8 | True | 17 | 24.189 | 2.864 |

Sections for 20261110-093238. The full contract and labelled midpoint sheet are in lab/sections/out/20261110-093238/.
| Start | End | Kind | Screen | Wanted | Route | Damaged | Human | Route share | Speed m/s |
|---:|---:|---|---|---:|---|---:|---:|---:|---:|
| -0.03 | 5.02 | unknown | game | None | none | 0.359 | 0.478 | null | null |
| 5.02 | 31.00 | foot | game | 0 | none | 0.222 | 0.747 | null | null |
| 31.00 | 33.29 | unknown | game | None | none | 0.000 | 0.201 | null | null |
| 33.29 | 40.12 | banner | failed | None | none | 0.038 | 0.161 | null | null |
| 40.12 | 43.39 | loading | loading | None | none | 0.000 | 0.070 | null | null |
| 43.39 | 155.08 | foot | game | 0 | none | 0.230 | 0.823 | null | null |
| 155.08 | 159.58 | menu | game | 0 | none | 0.297 | 0.927 | null | null |
| 159.58 | 213.36 | drive | game | 0 | none | 0.486 | 0.906 | 0.000 | null |
| 213.36 | 240.07 | foot | game | 0 | yellow | 0.405 | 0.818 | null | null |
| 240.07 | 307.67 | drive | game | 0 | yellow | 0.400 | 0.864 | 0.938 | null |
| 307.67 | 336.80 | unknown | game | None | none | 0.200 | 0.047 | null | null |
| 336.80 | 350.38 | foot | game | 0 | none | 0.061 | 0.460 | null | null |
| 350.38 | 385.07 | drive | game | 0 | none | 0.370 | 0.773 | 0.000 | null |
| 385.07 | 401.89 | menu | game | 0 | purple | 0.254 | 0.586 | null | null |
| 401.89 | 407.28 | drive | game | 0 | purple | 0.762 | 0.703 | 1.000 | null |
| 407.28 | 408.38 | foot | game | 0 | none | 0.125 | 0.573 | null | null |
| 408.38 | 411.35 | drive | game | 0 | none | 0.080 | 0.880 | 0.000 | null |
| 411.35 | 438.08 | foot | game | 0 | none | 0.518 | 0.952 | null | null |
| 438.08 | 481.70 | drive | game | 0 | none | 0.471 | 0.878 | 0.000 | null |
| 481.70 | 537.94 | foot | game | 1 | none | 0.394 | 0.822 | null | null |
| 537.94 | 552.17 | menu | game | 1 | none | 0.400 | 0.953 | null | null |
| 552.17 | 627.00 | foot | game | 3 | none | 0.322 | 0.754 | null | null |
| 627.00 | 628.81 | unknown | game | None | none | 0.077 | 0.000 | null | null |
| 628.81 | 635.44 | banner | wasted | None | none | 0.135 | 0.000 | null | null |
| 635.44 | 640.09 | loading | loading | None | none | 0.000 | 0.000 | null | null |
| 640.09 | 643.70 | unknown | game | None | none | 0.000 | 0.312 | null | null |
| 643.70 | 688.88 | foot | game | 0 | none | 0.287 | 0.866 | null | null |
| 688.88 | 695.83 | drive | game | 0 | none | 0.034 | 1.000 | 0.000 | null |

Audited visual truth beside its best same-kind predicted interval. Missing matches remain explicit; mismatched kinds are visible in the complete table above.
| True start | True end | True kind | Predicted start | Predicted end | Boundary errors (s) |
|---:|---:|---|---:|---:|---|
| 0.00 | 32.00 | foot | 5.02 | 31.00 | 5.02, 1.00 |
| 32.00 | 34.00 | unknown | missing | missing | not scored |
| 34.00 | 41.00 | banner | 33.29 | 40.12 | 0.71, 0.88 |
| 41.00 | 44.00 | loading | 40.12 | 43.39 | 0.88, 0.61 |
| 44.00 | 148.00 | foot | 43.39 | 155.08 | 0.61, 7.08 |
| 148.00 | 154.00 | drive | missing | missing | missed |
| 154.00 | 157.00 | menu | 155.08 | 159.58 | 1.08, 2.58 |
| 157.00 | 208.00 | drive | 159.58 | 213.36 | 2.58, 5.36 |
| 208.00 | 224.00 | foot | 213.36 | 240.07 | 5.36, 16.07 |
| 224.00 | 309.00 | drive | 240.07 | 307.67 | 16.07, 1.33 |
| 309.00 | 339.00 | cutscene | missing | missing | missed |
| 339.00 | 342.00 | banner | missing | missing | missed |
| 342.00 | 351.00 | foot | 336.80 | 350.38 | 5.20, 0.62 |
| 351.00 | 385.00 | drive | 350.38 | 385.07 | 0.62, 0.07 |
| 385.00 | 393.00 | menu | 385.07 | 401.89 | 0.07, 8.89 |
| 393.00 | 482.00 | drive | 438.08 | 481.70 | 45.08, 0.30 |
| 482.00 | 538.00 | foot | 481.70 | 537.94 | 0.30, 0.06 |
| 538.00 | 541.00 | menu | 537.94 | 552.17 | 0.06, 11.17 |
| 541.00 | 627.00 | foot | 552.17 | 627.00 | 11.17, 0.00 |
| 627.00 | 629.00 | unknown | missing | missing | not scored |
| 629.00 | 636.00 | banner | 628.81 | 635.44 | 0.19, 0.56 |
| 636.00 | 642.00 | loading | 635.44 | 640.09 | 0.56, 1.91 |
| 642.00 | 658.00 | foot | missing | missing | missed |
| 658.00 | 659.00 | menu | missing | missing | missed |
| 659.00 | 690.00 | foot | 643.70 | 688.88 | 15.30, 1.12 |
| 690.00 | 695.90 | drive | 688.88 | 695.83 | 1.12, 0.07 |

Sections for 20261110-231512. The full contract and labelled midpoint sheet are in lab/sections/out/20261110-231512/.
| Start | End | Kind | Screen | Wanted | Route | Damaged | Human | Route share | Speed m/s |
|---:|---:|---|---|---:|---|---:|---:|---:|---:|
| -0.00 | 240.01 | foot | game | 0 | none | 0.020 | null | null | null |

Sections for 20261111-065022. The full contract and labelled midpoint sheet are in lab/sections/out/20261111-065022/.
| Start | End | Kind | Screen | Wanted | Route | Damaged | Human | Route share | Speed m/s |
|---:|---:|---|---|---:|---|---:|---:|---:|---:|
| -0.01 | 2.51 | unknown | game | None | none | 0.000 | 0.000 | null | null |
| 2.51 | 33.20 | foot | game | 0 | none | 0.000 | 0.517 | null | null |
| 33.20 | 41.00 | drive | game | 1 | none | 0.090 | 0.935 | 0.000 | null |
| 41.00 | 162.40 | unknown | game | 2 | none | 0.039 | 0.932 | null | null |
| 162.40 | 220.31 | foot | game | 2 | none | 0.010 | 0.983 | null | null |
| 220.31 | 225.89 | unknown | game | 1 | none | 0.036 | 1.000 | null | null |
| 225.89 | 275.89 | foot | game | 1 | none | 0.030 | 0.954 | null | null |
| 275.89 | 280.50 | unknown | game | 1 | yellow | 0.022 | 1.000 | null | null |
| 280.50 | 290.49 | foot | game | 1 | none | 0.020 | 1.000 | null | null |
| 290.49 | 297.10 | unknown | game | 1 | none | 0.030 | 0.882 | null | null |
| 297.10 | 301.50 | foot | game | 0 | none | 0.000 | 1.000 | null | null |
| 301.50 | 303.00 | drive | game | 0 | none | 0.000 | 1.000 | 0.000 | null |
| 303.00 | 375.37 | foot | game | 0 | yellow | 0.004 | 0.260 | null | null |

Sections for 20261111-135510. The full contract and labelled midpoint sheet are in lab/sections/out/20261111-135510/.
| Start | End | Kind | Screen | Wanted | Route | Damaged | Human | Route share | Speed m/s |
|---:|---:|---|---|---:|---|---:|---:|---:|---:|
| -0.02 | 1103.36 | drive | game | 0 | purple | 0.000 | null | 1.000 | null |

Sections for 20261111-164039. The full contract and labelled midpoint sheet are in lab/sections/out/20261111-164039/.
| Start | End | Kind | Screen | Wanted | Route | Damaged | Human | Route share | Speed m/s |
|---:|---:|---|---|---:|---|---:|---:|---:|---:|
| -0.03 | 16.59 | foot | game | 0 | none | 0.000 | 0.000 | null | null |
| 16.59 | 27.13 | loading | loading | None | none | 0.000 | 0.000 | null | null |
| 27.13 | 80.68 | foot | game | 0 | none | 0.002 | 0.000 | null | null |
| 80.68 | 91.59 | loading | loading | None | none | 0.000 | 0.000 | null | null |
| 91.59 | 329.48 | foot | game | 1 | none | 0.002 | 0.170 | null | null |
| 329.48 | 336.79 | unknown | game | 1 | none | 0.000 | 0.835 | null | null |
| 336.79 | 342.96 | menu | map | None | none | 0.000 | 0.307 | null | null |
| 342.96 | 387.68 | unknown | game | 1 | purple | 0.039 | 0.887 | null | null |
| 387.68 | 418.78 | drive | game | 1 | purple | 0.017 | 0.899 | 0.695 | null |
| 418.78 | 428.94 | foot | game | 0 | none | 0.030 | 0.703 | null | null |
| 428.94 | 431.88 | unknown | game | None | none | 0.000 | 0.199 | null | null |
| 431.88 | 439.68 | foot | game | 0 | none | 0.064 | 0.765 | null | null |
| 439.68 | 544.38 | drive | game | 0 | yellow | 0.069 | 0.794 | 0.738 | null |
| 544.38 | 581.58 | foot | game | 0 | none | 0.051 | 0.890 | null | null |
| 581.58 | 587.67 | drive | game | 0 | none | 0.051 | 1.000 | 0.000 | null |
| 587.67 | 600.49 | foot | game | 0 | none | 0.055 | 1.000 | null | null |
| 600.49 | 604.39 | drive | game | 0 | none | 0.026 | 1.000 | 0.000 | null |
| 604.39 | 622.69 | foot | game | 0 | none | 0.000 | 0.740 | null | null |
| 622.69 | 626.38 | unknown | game | None | none | 0.000 | 0.141 | null | null |
| 626.38 | 679.88 | foot | game | 0 | none | 0.076 | 0.800 | null | null |
| 679.88 | 681.97 | unknown | game | None | none | 0.000 | 0.274 | null | null |
| 681.97 | 687.18 | banner | failed | None | none | 0.000 | 0.102 | null | null |
| 687.18 | 688.88 | loading | loading | None | none | 0.000 | 0.105 | null | null |
| 688.88 | 785.69 | foot | game | 0 | none | 0.099 | 0.863 | null | null |
| 785.69 | 876.78 | drive | game | 0 | none | 0.085 | 0.876 | 0.000 | null |
| 876.78 | 891.54 | foot | game | 0 | yellow | 0.015 | 0.859 | null | null |
| 891.54 | 901.45 | drive | game | 0 | yellow | 0.032 | 0.932 | 1.000 | null |

Audited visual truth beside its best same-kind predicted interval. Missing matches remain explicit; mismatched kinds are visible in the complete table above.
| True start | True end | True kind | Predicted start | Predicted end | Boundary errors (s) |
|---:|---:|---|---:|---:|---|
| 0.00 | 16.00 | foot | -0.03 | 16.59 | 0.03, 0.59 |
| 16.00 | 27.13 | unknown | missing | missing | not scored |
| 27.13 | 80.00 | foot | 27.13 | 80.68 | 0.00, 0.68 |
| 80.00 | 91.20 | unknown | missing | missing | not scored |
| 91.20 | 330.00 | foot | 91.59 | 329.48 | 0.39, 0.52 |
| 330.00 | 337.00 | drive | missing | missing | missed |
| 337.00 | 343.00 | menu | 336.79 | 342.96 | 0.21, 0.04 |
| 343.00 | 419.00 | drive | 387.68 | 418.78 | 44.68, 0.22 |
| 419.00 | 429.00 | foot | 418.78 | 428.94 | 0.22, 0.06 |
| 429.00 | 432.00 | cutscene | missing | missing | missed |
| 432.00 | 440.00 | foot | 431.88 | 439.68 | 0.12, 0.32 |
| 440.00 | 545.00 | drive | 439.68 | 544.38 | 0.32, 0.62 |
| 545.00 | 624.00 | foot | 544.38 | 581.58 | 0.62, 42.42 |
| 624.00 | 627.00 | cutscene | missing | missing | missed |
| 627.00 | 631.00 | foot | missing | missing | missed |
| 631.00 | 633.00 | menu | missing | missing | missed |
| 633.00 | 680.00 | foot | 626.38 | 679.88 | 6.62, 0.12 |
| 680.00 | 689.00 | banner | 681.97 | 687.18 | 1.97, 1.82 |
| 689.00 | 783.00 | foot | 688.88 | 785.69 | 0.12, 2.69 |
| 783.00 | 878.00 | drive | 785.69 | 876.78 | 2.69, 1.22 |
| 878.00 | 890.00 | foot | 876.78 | 891.54 | 1.22, 1.54 |
| 890.00 | 901.50 | drive | 891.54 | 901.45 | 1.54, 0.05 |

Sections for 20261111-165543. The full contract and labelled midpoint sheet are in lab/sections/out/20261111-165543/.
| Start | End | Kind | Screen | Wanted | Route | Damaged | Human | Route share | Speed m/s |
|---:|---:|---|---|---:|---|---:|---:|---:|---:|
| -0.00 | 75.30 | drive | game | 0 | yellow | 0.059 | 0.898 | 0.902 | null |
| 75.30 | 101.98 | unknown | game | None | none | 0.000 | 0.000 | null | null |
| 101.98 | 156.21 | foot | game | 0 | none | 0.087 | 0.825 | null | null |
| 156.21 | 159.21 | drive | game | 0 | none | 0.036 | 0.371 | 0.000 | null |
| 159.21 | 176.51 | menu | phone | None | none | 0.000 | 0.516 | null | null |
| 176.51 | 179.81 | foot | game | 0 | none | 0.030 | 1.000 | null | null |
| 179.81 | 214.61 | unknown | game | None | none | 0.000 | 0.021 | null | null |
| 214.61 | 222.57 | foot | game | 0 | none | 0.013 | 0.424 | null | null |
| 222.57 | 309.30 | drive | game | 0 | none | 0.148 | 0.810 | 0.000 | null |
| 309.30 | 315.41 | foot | game | 0 | none | 0.000 | 0.708 | null | null |
| 315.41 | 501.61 | drive | game | 0 | yellow | 0.042 | 0.882 | 0.326 | null |
| 501.61 | 502.71 | unknown | game | None | none | 0.000 | 0.136 | null | null |
| 502.71 | 504.62 | drive | game | 0 | none | 0.000 | 0.839 | 0.000 | null |
| 504.62 | 507.82 | foot | game | 0 | none | 0.062 | 1.000 | null | null |
| 507.82 | 509.52 | banner | passed | None | none | 0.000 | 1.000 | null | null |
| 509.52 | 516.21 | foot | game | 0 | none | 0.000 | 0.585 | null | null |
| 516.21 | 521.30 | drive | game | 0 | none | 0.280 | 0.258 | 0.000 | null |
| 521.30 | 522.51 | unknown | game | None | none | 0.000 | 0.711 | null | null |
| 522.51 | 572.91 | drive | game | 0 | none | 0.022 | 0.765 | 0.000 | null |
| 572.91 | 585.41 | unknown | game | 2 | none | 0.065 | 0.902 | null | null |
| 585.41 | 589.56 | drive | game | 2 | none | 0.000 | 0.969 | 0.000 | null |
| 589.56 | 595.70 | unknown | game | 2 | none | 0.000 | 0.969 | null | null |
| 595.70 | 600.91 | drive | game | 2 | none | 0.019 | 1.000 | 0.000 | null |
| 600.91 | 638.41 | unknown | game | 2 | none | 0.084 | 0.952 | null | null |
| 638.41 | 640.11 | drive | game | 2 | none | 0.000 | 1.000 | 0.000 | null |
| 640.11 | 650.38 | unknown | game | 2 | none | 0.139 | 0.800 | null | null |
| 650.38 | 659.60 | drive | game | 2 | none | 0.054 | 1.000 | 0.000 | null |
| 659.60 | 669.31 | unknown | game | 2 | none | 0.000 | 0.935 | null | null |
| 669.31 | 679.02 | drive | game | 2 | none | 0.092 | 0.918 | 0.000 | null |
| 679.02 | 687.31 | unknown | game | 2 | none | 0.203 | 0.837 | null | null |
| 687.31 | 692.71 | drive | game | 2 | none | 0.111 | 1.000 | 0.000 | null |
| 692.71 | 711.39 | unknown | game | 2 | none | 0.065 | 0.990 | null | null |
| 711.39 | 717.68 | drive | game | 2 | none | 0.063 | 1.000 | 0.000 | null |
| 717.68 | 740.32 | unknown | game | 2 | none | 0.152 | 0.830 | null | null |
| 740.32 | 750.20 | drive | game | 2 | none | 0.011 | 0.989 | 0.000 | null |
| 750.20 | 808.70 | unknown | game | 2 | none | 0.111 | 0.963 | null | null |
| 808.70 | 815.20 | drive | game | 2 | none | 0.047 | 0.991 | 0.000 | null |
| 815.20 | 858.61 | unknown | game | 2 | none | 0.076 | 0.908 | null | null |
| 858.61 | 862.70 | menu | map | None | none | 0.000 | 0.305 | null | null |
| 862.70 | 868.99 | unknown | game | 2 | purple | 0.000 | 0.518 | null | null |
| 868.99 | 872.13 | drive | game | 2 | purple | 0.000 | 0.973 | 0.875 | null |
| 872.13 | 895.40 | unknown | game | 2 | purple | 0.043 | 0.937 | null | null |
| 895.40 | 900.87 | drive | game | 0 | purple | 0.164 | 0.853 | 1.000 | null |

Sections for 20261111-171046. The full contract and labelled midpoint sheet are in lab/sections/out/20261111-171046/.
| Start | End | Kind | Screen | Wanted | Route | Damaged | Human | Route share | Speed m/s |
|---:|---:|---|---|---:|---|---:|---:|---:|---:|
| -0.01 | 4.89 | unknown | game | 0 | purple | 0.041 | 0.840 | null | null |
| 4.89 | 28.50 | drive | game | 0 | purple | 0.105 | 0.908 | 0.939 | null |
| 28.50 | 34.91 | foot | game | 0 | none | 0.049 | 0.538 | null | null |
| 34.91 | 36.30 | menu | weapon_wheel | None | none | 0.000 | 0.994 | null | null |
| 36.30 | 44.19 | foot | game | 0 | none | 0.025 | 0.868 | null | null |
| 44.19 | 116.85 | unknown | game | None | none | 0.006 | 0.007 | null | null |
| 116.85 | 154.69 | foot | game | 0 | none | 0.014 | 0.820 | null | null |
| 154.69 | 159.84 | unknown | game | None | none | 0.000 | 0.000 | null | null |
| 159.84 | 279.05 | drive | game | 0 | yellow | 0.074 | 0.823 | 0.911 | null |
| 279.05 | 327.29 | unknown | game | None | none | 0.004 | 0.107 | null | null |
| 327.29 | 332.90 | foot | game | 0 | none | 0.018 | 0.847 | null | null |
| 332.90 | 407.90 | drive | game | 0 | none | 0.142 | 0.927 | 0.000 | null |
| 407.90 | 418.00 | unknown | game | None | none | 0.000 | 0.256 | null | null |
| 418.00 | 473.11 | foot | game | 0 | none | 0.055 | 0.935 | null | null |
| 473.11 | 480.79 | unknown | game | 0 | none | 0.026 | 0.201 | null | null |
| 480.79 | 487.60 | foot | game | 0 | none | 0.030 | 0.947 | null | null |
| 487.60 | 503.25 | unknown | game | None | none | 0.036 | 0.289 | null | null |
| 503.25 | 505.60 | foot | game | 0 | none | 0.000 | 1.000 | null | null |
| 505.60 | 506.80 | drive | game | 0 | none | 0.000 | 0.777 | 0.000 | null |
| 506.80 | 531.89 | foot | game | 0 | none | 0.016 | 0.400 | null | null |
| 531.89 | 567.50 | unknown | game | None | none | 0.030 | 0.058 | null | null |
| 567.50 | 579.00 | foot | game | 0 | none | 0.000 | 0.833 | null | null |
| 579.00 | 587.40 | unknown | game | None | none | 0.024 | 0.275 | null | null |
| 587.40 | 592.10 | drive | game | 0 | none | 0.021 | 0.417 | 0.000 | null |
| 592.10 | 596.89 | unknown | game | None | none | 0.000 | 0.201 | null | null |
| 596.89 | 613.03 | foot | game | 0 | none | 0.020 | 0.689 | null | null |
| 613.03 | 618.69 | unknown | game | None | none | 0.000 | 0.310 | null | null |
| 618.69 | 639.20 | foot | game | 0 | yellow | 0.005 | 0.977 | null | null |
| 639.20 | 641.00 | menu | weapon_wheel | 0 | none | 0.000 | 1.000 | null | null |
| 641.00 | 645.99 | foot | game | 0 | none | 0.000 | 1.000 | null | null |
| 645.99 | 677.89 | unknown | game | None | none | 0.010 | 0.074 | null | null |
| 677.89 | 688.60 | drive | game | 0 | yellow | 0.208 | 1.000 | 1.000 | null |
| 688.60 | 689.70 | unknown | game | None | yellow | 0.000 | 0.401 | null | null |
| 689.70 | 730.69 | drive | game | 0 | yellow | 0.079 | 0.911 | 0.933 | null |
| 730.69 | 732.36 | unknown | game | None | none | 0.000 | 0.711 | null | null |
| 732.36 | 739.30 | drive | game | 0 | none | 0.000 | 0.712 | 0.000 | null |
| 739.30 | 749.80 | unknown | game | None | yellow | 0.010 | 0.113 | null | null |
| 749.80 | 802.29 | drive | game | 0 | yellow | 0.031 | 0.887 | 0.919 | null |
| 802.29 | 819.99 | unknown | game | None | none | 0.011 | 0.023 | null | null |
| 819.99 | 824.92 | drive | game | 0 | none | 0.000 | 0.540 | 0.000 | null |
| 824.92 | 831.12 | banner | game | 0 | none | 0.016 | 0.780 | null | null |
| 831.12 | 834.27 | drive | game | 0 | none | 0.032 | 0.450 | 0.000 | null |
| 834.27 | 836.20 | foot | game | 0 | none | 0.050 | 1.000 | null | null |
| 836.20 | 838.99 | drive | game | 0 | none | 0.038 | 1.000 | 0.000 | null |
| 838.99 | 840.40 | foot | game | 0 | none | 0.000 | 1.000 | null | null |
| 840.40 | 867.69 | drive | game | 0 | none | 0.039 | 0.863 | 0.000 | null |
| 867.69 | 882.00 | foot | game | 0 | none | 0.035 | 0.662 | null | null |
| 882.00 | 900.49 | unknown | game | None | none | 0.000 | 0.000 | null | null |

Sections for 20261111-172549. The full contract and labelled midpoint sheet are in lab/sections/out/20261111-172549/.
| Start | End | Kind | Screen | Wanted | Route | Damaged | Human | Route share | Speed m/s |
|---:|---:|---|---|---:|---|---:|---:|---:|---:|
| -0.04 | 20.26 | unknown | game | None | none | 0.000 | 0.200 | null | null |
| 20.26 | 24.06 | foot | game | 0 | none | 0.000 | 0.351 | null | null |
| 24.06 | 69.96 | drive | game | 0 | yellow | 0.095 | 0.918 | 0.859 | null |
| 69.96 | 101.66 | menu | phone | None | yellow | 0.109 | 0.873 | null | null |
| 101.66 | 125.57 | drive | game | 0 | yellow | 0.129 | 0.787 | 0.770 | null |
| 125.57 | 276.16 | foot | game | 0 | yellow | 0.017 | 0.757 | null | null |
| 276.16 | 281.67 | drive | game | 0 | yellow | 0.018 | 1.000 | 1.000 | null |
| 281.67 | 296.07 | menu | phone | None | yellow | 0.049 | 0.953 | null | null |
| 296.07 | 362.35 | drive | game | 0 | yellow | 0.059 | 0.907 | 0.947 | null |
| 362.35 | 382.37 | unknown | game | None | none | 0.000 | 0.000 | null | null |
| 382.37 | 385.67 | drive | game | 0 | none | 0.000 | 0.041 | 0.000 | null |
| 385.67 | 412.56 | unknown | game | 0 | none | 0.004 | 0.371 | null | null |
| 412.56 | 429.16 | foot | game | 0 | none | 0.000 | 1.000 | null | null |
| 429.16 | 478.57 | unknown | game | None | none | 0.010 | 0.036 | null | null |
| 478.57 | 480.36 | foot | game | 0 | none | 0.000 | 0.637 | null | null |
| 480.36 | 482.17 | banner | passed | None | none | 0.000 | 1.000 | null | null |
| 482.17 | 506.76 | foot | game | 0 | none | 0.000 | 0.062 | null | null |

All eight recordings were read without changing their contents. The command completed in one process, and every output has the exact top-level and section fields required by P38. Section endpoints preserve small negative initial capture timestamps rather than shifting the source clock. The four afternoon recordings contain 3209.9 metadata seconds, or 53 minutes 29.9 seconds.

The independent one-second contact-sheet pass preceded the first section run. Its original labels remain in truth.json. A later blind second reading of the afternoon sheets and direct adjudication of the disputed frames found missed system interruptions, a short handshake, a window-entry animation, and short radial menus. truth-audited.json records those corrections and explicitly identifies their post-run provenance. Both evaluation versions are retained in metrics.json. These are approximate visual labels, not frame-accurate production ground truth.

The contact sheet labels name requested integer seconds and source frame indices. They select the nearest source frame; long gaps can map several requested seconds to one source frame. The original sheet generator collapsed those duplicate frames. For example, 164039 frame 1077 was captured at 17.9507 seconds but carries the final duplicate request label 22; frame 1078 arrives at 27.1275 seconds. The corrected truth excludes the whole system interruption through 27.13 seconds. A second interruption around 80 to 91.2 seconds is also excluded. This does not affect the section command, which always uses the original frame timestamps.

The Wi-Fi midpoint sheet visibly shows a motorcycle ride labelled foot in the 213.3621 to 240.0727 section. Contact sheet 007.jpg shows the player seated on the motorcycle at 224 seconds, frame 4900, and riding continuously afterwards. The classifier does not recover drive until 240.0727 seconds. The existing map reader can remain flat while the player is in a vehicle.

The same recording shows the passed banner at 339 seconds, frame 7279, through 341 seconds, frame 7317, in contact sheet 011.jpg. The output remains foot from 336.8013 to 350.3767. The existing screen reader therefore misses an entire mission-result interval. The scripted conversation at 313 seconds, frame 6674, through the following HUD-free shots is emitted as unknown because missing map pixels cannot establish a cutscene on their own.

The cable recording provides the opposite ambiguity. The existing hand label marks kerim-13385 as foot, but the reader has a tilted minimap and one wanted star. Frame 13385 is at 223.408 seconds; the output correctly abstains with unknown over 220.3057 to 225.8947 rather than treating tilt alone as proof of a vehicle. Forty-one eligible judge frames become unknown, which counts against accuracy.

The 164039 system overlays are emitted as loading from 16.5851 to 27.1275 and from 80.6765 to 91.5939. The screen reader cannot distinguish these external overlays and black interruptions from a game loading screen. The contact images show this in 000.jpg and 002.jpg. No changes were made to hud.py or minimap.py because they belong to other tasks.

GPS speed cannot currently be obtained by the permitted pixel-only readers. Pipeline.step starts the GPS OCR reader, so it is deliberately not used. The selected ordinary recordings have no play.jsonl. The pilot recording has the gps_speed schema in its existing log, but its inspected initial rows contain null values and the recording is on foot throughout. Output speed is null; it is not zero and must not be used as a driving-speed baseline. Synthetic reader-sequence tests verify that finite injected GPS speeds are aggregated when a future offline source supplies them.

The first full gate ran inside the sandbox. Its failures were local socket binding in the existing commentator/overlay tests and CoreML temporary-directory creation in existing object-detector tests. A diagnostic `env -u PS5_HOST .venv/bin/python -m pytest -q --full -x` reproduced the socket permission error after 186 passing tests. The obsolete sandboxed run was interrupted after the replacement full gate started with local permissions; it had 2521 passes, 236 expected failures, 3 skips, 5 socket failures and 5 CoreML setup errors at interruption. It is not a completed gate result. The replacement run is recorded separately in gate.txt.

The global Git workflow conflicts with docs/tasks/README.md, which says, "Git cannot write here: no commit, stash, checkout or reset." The global rule has priority, but no merge to main is authorized. Publication and final gate status are stated in the task report rather than inferred from a local artifact.

Delivery remains in the isolated feat/pilot-sections worktree for the integrating reviewer. PLAN.md designates the shared feat/pilot branch as the integration branch and requires the PR to go from there to main. Integrating neighbouring workers or publishing that shared branch is outside this card's file ownership, so no main update or PR was made here. The task is ready for that integration step; the measured labels are not accepted ground truth. The reviewer still needs an authoritative movement judge, better screen observations for missed banners and overlays, and a permitted offline speed source before relying on this output for training labels or driving-speed comparisons.


## Second round, 11 November: the judge

The readers leave a quarter of Kerim's afternoon unknown and call the figure wrongly where the minimap and the game disagree, so the second round asks the judge, the vision model on the gaming PC, about the frames the readers cannot decide. The command takes `--judge http://192.168.0.248:1234=qwen/qwen3-vl-8b`; without the flag nothing is different from the first round, the same code runs and the same sections come out. With it, a first pass of the readers runs as before. The tool then marks the samples that are open: every sample the readers leave unknown, and every foot or vehicle that rests on the minimap alone, near a change of the readers' mind (three seconds either side) or while stars are lit, since stars tilt the map on foot. A foot or vehicle that the controller settles, a pushed stick with Cross or a held trigger with steering on a tilted map, is not asked about, and neither are menus, banners and loading screens the screen reader names, nor damaged frames. In every second that holds an open sample the tool sends the frame nearest the middle of that second to the judge at 640 pixels, which is about one frame a second on the open stretches and never the whole recording: 278 of the 901 seconds of 20261111-164039 and 400 of the 696 of the Wi-Fi recording, which has many stars and many damaged frames.

Each frame costs three requests, one per question, for the banner, the overlay and the mode. The first attempt used the joint request of lab/judge, which is faster by a third, and it made the afternoon worse: the model answers the overlay question right on 55 percent of the frames in a joint request and on 96 percent alone (lab/judge/results), and the sections filled with menus that were not there, 40 false sections in 20261111-164039. The questions are asked one by one now. The wanted level stays with the readers. A banner answer makes a banner, an overlay a menu, and otherwise the mode decides: on foot is `foot`, in a vehicle `drive`, and neither, without a HUD, `cutscene`. This runs through the same replaceable function: a sample carries the answers of its second in a new field, and `decide` names the kind they give before it looks at the minimap. The screens the readers name keep their say, so the judge never turns a loading screen into a cutscene.

One odd answer decides nothing, as one odd reading does not. An answer is handed to its second only if a neighbouring second, at most one and a half seconds away, gave the same kind; an answer that stands alone leaves the samples to the readers, and an answer the questions do not allow counts as asked and decides nothing. The segmentation is unchanged and still wants a second of stable evidence on top of that. Every answer is written to `judge.json` in the output folder, keyed by frame, with the model that gave it; a rerun reads it and asks nothing twice, which was checked on 20261111-192328 (219 frames in the cache, 0 requests, byte-identical sections). The file is not committed, it is about 100 kilobytes a recording and rebuilt by the command. If the server does not answer, the tool tries the request once more, says so at once, ends the second pass for all recordings, and writes the result of the readers, which stays valid; the answers already cached are kept. The tests inject the answers and the transport, never calling the server: they pin the cutscene from no map, the lone answer, the two in a row, the unparsable answer, which seconds are asked, the controller's frames being left alone, the cache, the wrong model, the server that is down and the whole pass over a small synthetic recording.

On the two hand-labelled recordings, scored against truth-audited.json as before (`lab/sections/evaluate_judge.py` writes the table; the reader-only sections are kept in `lab/sections/readers/`, the judged ones in `out/` and `judged/`), no threshold was touched after seeing the truth.

| Recording | Pass | True >=3s | Kind found | Kind and ends <=2s | False sections | False /5min | Unknown on known truth (s) | Unknown minutes |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 20261111-164039 | readers | 19 | 13 | 10 | 5 | 1.66 | 60.7 | 1.01 |
| 20261111-164039 | judge | 19 | 14 | 8 | 5 | 1.66 | 1.9 | 0.03 |
| 20261110-093238 | readers | 23 | 18 | 7 | 4 | 1.72 | 38.8 | 0.70 |
| 20261110-093238 | judge | 23 | 20 | 8 | 2 | 0.86 | 5.0 | 0.08 |

The unknown seconds on stretches the truth knows fall from 60.7 to 1.9 in 20261111-164039 and from 38.8 to 5.0 in the Wi-Fi recording, and the unknown minutes of the whole recording from 1.01 to 0.03 and from 0.70 to 0.08. Counted per second on the truth's known stretches, the section kind is right on 847 of 879 seconds against 795 before (96.4 against 90.4 percent) in the afternoon recording, and on 621 of 692 against 563 (89.7 against 81.4 percent) in the Wi-Fi one. Kind found rises from 13 to 14 of 19 and from 18 to 20 of 23, and the false sections fall from 4 to 2 in the Wi-Fi recording and stay at 5 in the other. The strict target, every true section of three seconds or more found with both ends within two seconds, is still not met: 8 of 19 and 8 of 23, and the afternoon recording went down from 10 because the judge moves ends. Around 440 seconds the truth has a foot section until 440 and then a drive, while the judged drive starts at 454 and a judged foot section runs until 439; the short truth sections at 429 to 432 and 624 to 633 seconds, three-second cutscenes and a menu of two seconds, are not found, since a short stretch needs two answers in a row and then a second of evidence. The false-section target of one per five minutes is met in the Wi-Fi recording (0.86) and not in the afternoon one (1.66), where the five false sections are a menu of 1.5 seconds at 15.1 inside what the truth calls an overlay, a drive and a menu from 439 to 454 seconds, a cutscene of two seconds at 678 and a loading of 1.7 seconds at 687, the last of which is the first round's as well.

The cutscenes the judge finds in the Wi-Fi recording are partly called foot or drive: of the truth's cutscene seconds, 18 become foot and 12 drive, so in a cutscene that shows the character the mode question does not give the "neither" it is meant to give. A `cutscene` section is therefore a lower bound: where it is missing, that is no evidence of play.

The eleven finished recordings of 11 November from 16:40 on were run in one process into `lab/sections/out/` with the judge (the four afternoon folders are overwritten with the judged result; the eight reader-only outputs of the first round for the other recordings stay). The minutes per kind, from the section clocks:

| Recording | Minutes | drive | foot | cutscene | menu | banner | loading | unknown |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 20261111-164039 | 15.03 | 4.82 | 9.50 | 0.03 | 0.16 | 0.09 | 0.39 | 0.03 |
| 20261111-165543 | 15.02 | 12.19 | 2.29 | 0.00 | 0.51 | 0.03 | 0.00 | 0.00 |
| 20261111-171046 | 15.01 | 7.73 | 6.97 | 0.00 | 0.13 | 0.03 | 0.00 | 0.16 |
| 20261111-172549 | 8.45 | 3.07 | 4.45 | 0.00 | 0.88 | 0.05 | 0.00 | 0.00 |
| 20261111-175312 | 15.00 | 6.02 | 8.37 | 0.00 | 0.44 | 0.17 | 0.00 | 0.00 |
| 20261111-180814 | 15.00 | 7.35 | 5.19 | 0.00 | 1.31 | 0.00 | 0.00 | 1.15 |
| 20261111-182316 | 15.03 | 6.60 | 6.79 | 0.05 | 0.96 | 0.42 | 0.16 | 0.05 |
| 20261111-183820 | 15.01 | 0.80 | 13.57 | 0.00 | 0.46 | 0.11 | 0.06 | 0.00 |
| 20261111-185323 | 15.00 | 2.98 | 9.92 | 0.03 | 1.71 | 0.14 | 0.11 | 0.09 |
| 20261111-190825 | 15.01 | 10.96 | 2.95 | 0.17 | 0.42 | 0.27 | 0.11 | 0.12 |
| 20261111-192328 | 4.88 | 0.55 | 4.03 | 0.03 | 0.04 | 0.12 | 0.10 | 0.00 |
| all eleven | 148.42 | 63.07 | 74.05 | 0.32 | 7.02 | 1.42 | 0.93 | 1.60 |

Of the 148.41 minutes the judge leaves 1.60 unknown, 1.1 percent. For the four recordings of the first round the unknown minutes fall from 13.31 of 53.49 to 0.19, and the kinds are now 27.80 minutes of driving, 23.22 on foot, 1.68 in menus, 0.39 of loading, 0.19 of banners, 0.03 of cutscene. The first round gave 20.67 driving and 17.60 on foot over the same time, so most of what was unknown was play, as expected, and about half of it drive. 20261111-180814 is the recording that keeps the most unknown, 1.2 minutes.

The judge answered 16668 requests for 5556 frames, with no failure and no reply the questions did not allow, in 2434 seconds, 0.146 seconds a request (about 0.44 a frame); the Wi-Fi recording took another 1200 requests and 182.7 seconds in an earlier run of the same code. Including decoding and the readers, the eleven took 2965 seconds for 148.4 minutes of recording, 20 seconds per recording minute against 1.6 to 3.6 without the judge (11 to 31 per minute, depending on how much is open), so the limit of ten seconds per recording minute set for the readers does not hold with the judge; the requests are serial and bound by the server, and the open stretches could be asked in parallel if that matters. The full gate is in `lab/sections/gate-judge.txt`.
