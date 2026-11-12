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
