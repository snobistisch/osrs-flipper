
### active — all period, bank 20.0m, 12 segments, 925 decisions

Fill rule `strict_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| replay_portfolio | 9.0k [5.1k .. 12.1k] | 16.5k | 1.2k | 3.1k | 0.70% | 77% | 14% | 91% | 58% | -4.17% | 2.56% | 100% | 18% | 86.9 | — | — |
| rp_w50 | 6.8k [-1.7k .. 12.7k] | 13.9k | 872 | 2.4k | 0.54% | 77% | 13% | 91% | 57% | -3.84% | 7.76% | 100% | 18% | 86.5 | — | — |
| rp_w100 | 4.2k [-4.6k .. 10.6k] | 12.6k | 538 | 1.5k | 0.34% | 72% | 16% | 88% | 52% | -4.55% | 8.45% | 100% | 18% | 84.9 | — | — |
| rp_c16 | 8.4k [5.0k .. 11.3k] | 12.8k | 1.1k | 4.4k | 0.84% | 81% | 11% | 92% | 69% | -3.65% | 2.44% | 100% | 12% | 103.3 | — | — |
| rp_c32 | 6.2k [3.7k .. 8.2k] | 9.2k | 840 | 5.3k | 0.89% | 82% | 10% | 92% | 76% | -3.80% | 1.47% | 100% | 7% | 119.6 | — | — |
| rp_w50_c16 | 9.4k [6.6k .. 12.0k] | 13.8k | 1.2k | 5.2k | 0.97% | 80% | 11% | 91% | 68% | -4.00% | 2.33% | 100% | 11% | 101.3 | — | — |

Fill rule `touch_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| replay_portfolio | 12.8k [8.8k .. 16.2k] | 19.2k | 1.7k | 4.4k | 0.91% | 83% | 11% | 94% | 65% | -3.15% | 2.18% | 100% | 19% | 93.2 | — | — |
| rp_w50 | 10.4k [1.2k .. 16.7k] | 16.9k | 1.4k | 3.6k | 0.74% | 84% | 10% | 94% | 66% | -3.11% | 8.43% | 100% | 18% | 94.3 | — | — |
| rp_w100 | 10.7k [2.3k .. 16.7k] | 17.4k | 1.4k | 3.7k | 0.76% | 85% | 10% | 95% | 65% | -2.94% | 7.71% | 100% | 18% | 92.9 | — | — |
| rp_c16 | 8.5k [-770 .. 14.6k] | 12.2k | 1.1k | 4.6k | 0.76% | 86% | 8% | 94% | 76% | -2.89% | 8.76% | 100% | 12% | 113.5 | — | — |
| rp_c32 | 7.5k [2.0k .. 10.9k] | 9.8k | 1.0k | 6.8k | 0.93% | 88% | 7% | 95% | 83% | -2.69% | 4.77% | 100% | 7% | 136.8 | — | — |
| rp_w50_c16 | 10.2k [1.1k .. 16.1k] | 13.8k | 1.4k | 5.7k | 0.90% | 88% | 7% | 95% | 78% | -2.55% | 8.50% | 100% | 12% | 117.1 | — | — |

Bank gp/h under every fill assumption (rule_capture):

| method | strict_0.03 | strict_0.10 | strict_0.30 | touch_0.03 | touch_0.10 | touch_0.30 |
|---|---|---|---|---|---|---|
| replay_portfolio | -4.8k | 9.0k | 15.8k | -1.4k | 12.8k | 19.5k |
| rp_w50 | -3.8k | 6.8k | 16.6k | -2.8k | 10.4k | 23.6k |
| rp_w100 | -2.2k | 4.2k | 12.7k | -2.3k | 10.7k | 22.2k |
| rp_c16 | -984 | 8.4k | 13.8k | 2.7k | 8.5k | 15.0k |
| rp_c32 | 1.2k | 6.2k | 6.5k | 3.0k | 7.5k | 9.9k |
| rp_w50_c16 | 604 | 9.4k | 13.8k | 3.6k | 10.2k | 17.5k |

### overnight — all period, bank 20.0m, 13 segments, 38 decisions

Fill rule `strict_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| replay_portfolio | -2.1k [-7.4k .. 2.8k] | 6.8k | -321 | -266 | -0.41% | 59% | 22% | 82% | 24% | -7.06% | 3.40% | 99% | 51% | 15.8 | — | — |
| rp_w50 | -2.9k [-9.0k .. 2.7k] | 5.9k | -435 | -360 | -0.58% | 56% | 21% | 79% | 21% | -6.83% | 4.21% | 99% | 51% | 15.8 | — | — |
| rp_w100 | -2.3k [-6.5k .. 2.1k] | 6.8k | -354 | -288 | -0.48% | 55% | 21% | 78% | 19% | -6.66% | 3.26% | 99% | 52% | 15.8 | — | — |
| rp_c16 | 1.0k [-1.5k .. 3.8k] | 5.9k | 161 | 203 | 0.28% | 61% | 21% | 82% | 41% | -7.75% | 1.69% | 99% | 33% | 15.8 | — | — |
| rp_c32 | -1.0k [-6.1k .. 2.3k] | 2.7k | -164 | -317 | -0.39% | 61% | 22% | 84% | 49% | -8.09% | 3.93% | 99% | 21% | 15.9 | — | — |
| rp_w50_c16 | -475 [-4.5k .. 3.3k] | 4.8k | -73 | -88 | -0.12% | 58% | 20% | 80% | 35% | -7.69% | 3.42% | 99% | 34% | 15.8 | — | — |

Fill rule `touch_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| replay_portfolio | -777 [-6.1k .. 4.2k] | 8.1k | -116 | -96 | -0.14% | 63% | 21% | 85% | 29% | -6.71% | 3.39% | 99% | 51% | 15.8 | — | — |
| rp_w50 | -1.1k [-7.4k .. 4.5k] | 7.8k | -163 | -135 | -0.20% | 62% | 21% | 84% | 29% | -6.83% | 4.18% | 99% | 51% | 15.8 | — | — |
| rp_w100 | -68 [-4.4k .. 4.5k] | 8.9k | -10 | -8 | -0.01% | 63% | 21% | 85% | 26% | -6.18% | 3.04% | 99% | 52% | 15.8 | — | — |
| rp_c16 | 2.1k [-356 .. 4.8k] | 6.8k | 326 | 410 | 0.53% | 65% | 19% | 85% | 48% | -7.13% | 1.66% | 99% | 33% | 15.8 | — | — |
| rp_c32 | -416 [-5.6k .. 3.0k] | 3.2k | -66 | -126 | -0.15% | 67% | 20% | 87% | 56% | -8.09% | 3.93% | 99% | 21% | 15.9 | — | — |
| rp_w50_c16 | 1.2k [-2.8k .. 4.8k] | 6.1k | 179 | 217 | 0.29% | 65% | 18% | 84% | 45% | -7.07% | 3.42% | 99% | 34% | 15.8 | — | — |

Bank gp/h under every fill assumption (rule_capture):

| method | strict_0.03 | strict_0.10 | strict_0.30 | touch_0.03 | touch_0.10 | touch_0.30 |
|---|---|---|---|---|---|---|
| replay_portfolio | -3.5k | -2.1k | 1.7k | -3.1k | -777 | 3.2k |
| rp_w50 | -4.6k | -2.9k | 1.2k | -3.8k | -1.1k | 2.9k |
| rp_w100 | -4.1k | -2.3k | 2.1k | -3.2k | -68 | 4.5k |
| rp_c16 | -1.8k | 1.0k | 2.8k | -1.2k | 2.1k | 3.9k |
| rp_c32 | -2.7k | -1.0k | -390 | -2.1k | -416 | 250 |
| rp_w50_c16 | -3.3k | -475 | 1.6k | -2.3k | 1.2k | 3.2k |

### profit — all period, bank 20.0m, 11 segments, 110 decisions

Fill rule `strict_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| replay_portfolio | 7.5k [-1.0k .. 15.9k] | 18.2k | 848 | 501 | 0.75% | 75% | 18% | 93% | 36% | -11.91% | 6.08% | 100% | 92% | 14.1 | — | — |
| rp_w50 | 7.2k [-1.2k .. 15.4k] | 17.8k | 811 | 485 | 0.72% | 76% | 19% | 95% | 36% | -11.97% | 5.05% | 100% | 92% | 14.1 | — | — |
| rp_w100 | 2.9k [-6.9k .. 12.3k] | 14.7k | 320 | 183 | 0.28% | 71% | 21% | 92% | 32% | -11.79% | 7.55% | 100% | 92% | 14.3 | — | — |
| rp_c16 | 8.6k [-1.9k .. 18.7k] | 15.8k | 1.0k | 659 | 0.75% | 79% | 16% | 95% | 53% | -8.90% | 6.08% | 100% | 86% | 16.0 | — | — |
| rp_c32 | 3.4k [-21.6k .. 17.7k] | 9.0k | 415 | 318 | 0.29% | 82% | 14% | 96% | 67% | -7.62% | 23.64% | 100% | 67% | 19.3 | — | — |
| rp_w50_c16 | 5.4k [-3.6k .. 13.4k] | 14.0k | 647 | 405 | 0.49% | 77% | 19% | 96% | 51% | -11.33% | 6.39% | 100% | 86% | 15.3 | — | — |

Fill rule `touch_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| replay_portfolio | 8.7k [-717 .. 17.8k] | 19.4k | 991 | 588 | 0.81% | 78% | 17% | 95% | 40% | -10.29% | 5.63% | 100% | 92% | 14.4 | — | — |
| rp_w50 | 9.6k [1.1k .. 18.2k] | 20.4k | 1.1k | 669 | 0.89% | 80% | 17% | 97% | 43% | -10.06% | 5.35% | 100% | 92% | 14.4 | — | — |
| rp_w100 | 12.1k [4.0k .. 20.0k] | 22.7k | 1.4k | 806 | 1.09% | 80% | 16% | 96% | 41% | -7.59% | 4.83% | 100% | 92% | 14.7 | — | — |
| rp_c16 | 12.8k [2.3k .. 22.0k] | 19.5k | 1.6k | 997 | 1.04% | 82% | 14% | 96% | 59% | -7.05% | 6.75% | 100% | 87% | 16.9 | — | — |
| rp_c32 | 7.1k [-16.7k .. 20.7k] | 12.3k | 895 | 675 | 0.53% | 86% | 11% | 97% | 73% | -6.69% | 23.27% | 100% | 69% | 20.8 | — | — |
| rp_w50_c16 | 11.9k [3.9k .. 19.9k] | 19.1k | 1.4k | 932 | 1.01% | 81% | 14% | 96% | 59% | -7.80% | 5.29% | 100% | 86% | 16.7 | — | — |

Bank gp/h under every fill assumption (rule_capture):

| method | strict_0.03 | strict_0.10 | strict_0.30 | touch_0.03 | touch_0.10 | touch_0.30 |
|---|---|---|---|---|---|---|
| replay_portfolio | -10.5k | 7.5k | 24.7k | -10.1k | 8.7k | 28.1k |
| rp_w50 | -8.2k | 7.2k | 25.0k | -4.5k | 9.6k | 29.1k |
| rp_w100 | -10.0k | 2.9k | 26.1k | -7.3k | 12.1k | 30.1k |
| rp_c16 | -8.5k | 8.6k | 19.0k | -4.8k | 12.8k | 24.5k |
| rp_c32 | -3.2k | 3.4k | 13.3k | -4.4k | 7.1k | 18.5k |
| rp_w50_c16 | -6.5k | 5.4k | 19.5k | -5.6k | 11.9k | 27.2k |

#### active / replay_portfolio — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1631 | 81% | 58% |
| 90%-100% | 43 | 95% | 60% |

Calibration error 23.2%. Finished within own P50/P80/P90: 35% / 57% / 58% (targets 50 / 80 / 90). Realised 4.2m of 8.0m predicted gp (52%).

#### active / replay_portfolio — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1750 | 81% | 65% |
| 90%-100% | 47 | 95% | 70% |

Calibration error 15.9%. Finished within own P50/P80/P90: 43% / 64% / 65% (targets 50 / 80 / 90). Realised 5.9m of 8.4m predicted gp (71%).

#### active / rp_w50 — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1622 | 81% | 57% |
| 90%-100% | 44 | 96% | 68% |

Calibration error 23.9%. Finished within own P50/P80/P90: 35% / 56% / 57% (targets 50 / 80 / 90). Realised 3.1m of 8.5m predicted gp (37%).

#### active / rp_w50 — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1776 | 81% | 66% |
| 90%-100% | 41 | 95% | 71% |

Calibration error 15.1%. Finished within own P50/P80/P90: 45% / 65% / 66% (targets 50 / 80 / 90). Realised 4.8m of 9.2m predicted gp (52%).

#### active / rp_w100 — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1602 | 81% | 51% |
| 90%-100% | 35 | 95% | 66% |

Calibration error 29.2%. Finished within own P50/P80/P90: 32% / 51% / 52% (targets 50 / 80 / 90). Realised 2.0m of 9.0m predicted gp (22%).

#### active / rp_w100 — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1759 | 81% | 65% |
| 90%-100% | 32 | 95% | 88% |

Calibration error 15.4%. Finished within own P50/P80/P90: 43% / 64% / 65% (targets 50 / 80 / 90). Realised 4.9m of 9.7m predicted gp (51%).

#### active / rp_c16 — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1940 | 81% | 69% |
| 90%-100% | 51 | 95% | 82% |

Calibration error 12.1%. Finished within own P50/P80/P90: 52% / 68% / 69% (targets 50 / 80 / 90). Realised 3.9m of 5.7m predicted gp (68%).

#### active / rp_c16 — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 2130 | 81% | 76% |
| 90%-100% | 57 | 95% | 82% |

Calibration error 5.4%. Finished within own P50/P80/P90: 60% / 75% / 76% (targets 50 / 80 / 90). Realised 3.9m of 6.3m predicted gp (63%).

#### active / rp_c32 — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 2223 | 81% | 75% |
| 90%-100% | 81 | 94% | 90% |

Calibration error 5.6%. Finished within own P50/P80/P90: 62% / 75% / 76% (targets 50 / 80 / 90). Realised 2.9m of 3.8m predicted gp (75%).

#### active / rp_c32 — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 2554 | 81% | 83% |
| 90%-100% | 82 | 94% | 91% |

Calibration error 1.8%. Finished within own P50/P80/P90: 71% / 82% / 83% (targets 50 / 80 / 90). Realised 3.4m of 4.2m predicted gp (82%).

#### active / rp_w50_c16 — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1903 | 81% | 68% |
| 90%-100% | 50 | 95% | 78% |

Calibration error 12.6%. Finished within own P50/P80/P90: 50% / 68% / 68% (targets 50 / 80 / 90). Realised 4.3m of 6.4m predicted gp (68%).

#### active / rp_w50_c16 — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 2206 | 81% | 78% |
| 90%-100% | 50 | 95% | 86% |

Calibration error 3.0%. Finished within own P50/P80/P90: 62% / 77% / 78% (targets 50 / 80 / 90). Realised 4.7m of 7.1m predicted gp (66%).

#### overnight / replay_portfolio — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 134 | 39% | 17% |
| 40%-60% | 58 | 49% | 14% |
| 60%-80% | 59 | 68% | 29% |
| 80%-90% | 36 | 87% | 44% |
| 90%-100% | 13 | 93% | 69% |

Calibration error 30.2%. Finished within own P50/P80/P90: 11% / 21% / 24% (targets 50 / 80 / 90). Realised -973.3k of 6.4m predicted gp (-15%).

#### overnight / replay_portfolio — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 134 | 39% | 22% |
| 40%-60% | 58 | 49% | 19% |
| 60%-80% | 59 | 68% | 34% |
| 80%-90% | 36 | 87% | 47% |
| 90%-100% | 13 | 93% | 77% |

Calibration error 25.6%. Finished within own P50/P80/P90: 13% / 26% / 29% (targets 50 / 80 / 90). Realised -354.2k of 6.4m predicted gp (-6%).

#### overnight / rp_w50 — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 143 | 39% | 13% |
| 40%-60% | 52 | 50% | 12% |
| 60%-80% | 60 | 68% | 23% |
| 80%-90% | 33 | 87% | 48% |
| 90%-100% | 12 | 93% | 67% |

Calibration error 33.1%. Finished within own P50/P80/P90: 9% / 18% / 20% (targets 50 / 80 / 90). Realised -1.3m of 7.1m predicted gp (-19%).

#### overnight / rp_w50 — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 143 | 39% | 22% |
| 40%-60% | 52 | 50% | 21% |
| 60%-80% | 60 | 68% | 32% |
| 80%-90% | 33 | 87% | 52% |
| 90%-100% | 12 | 93% | 75% |

Calibration error 24.5%. Finished within own P50/P80/P90: 15% / 27% / 29% (targets 50 / 80 / 90). Realised -497.8k of 7.1m predicted gp (-7%).

#### overnight / rp_w100 — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 143 | 39% | 10% |
| 40%-60% | 56 | 49% | 9% |
| 60%-80% | 58 | 68% | 24% |
| 80%-90% | 32 | 87% | 47% |
| 90%-100% | 12 | 93% | 67% |

Calibration error 34.7%. Finished within own P50/P80/P90: 7% / 16% / 19% (targets 50 / 80 / 90). Realised -1.1m of 7.8m predicted gp (-14%).

#### overnight / rp_w100 — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 143 | 39% | 22% |
| 40%-60% | 56 | 49% | 14% |
| 60%-80% | 58 | 68% | 28% |
| 80%-90% | 32 | 87% | 50% |
| 90%-100% | 12 | 93% | 67% |

Calibration error 27.4%. Finished within own P50/P80/P90: 13% / 23% / 26% (targets 50 / 80 / 90). Realised -30.8k of 7.8m predicted gp (-0%).

#### overnight / rp_c16 — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 140 | 39% | 32% |
| 40%-60% | 58 | 50% | 28% |
| 60%-80% | 57 | 68% | 61% |
| 80%-90% | 37 | 88% | 62% |
| 90%-100% | 9 | 94% | 44% |

Calibration error 13.1%. Finished within own P50/P80/P90: 24% / 39% / 41% (targets 50 / 80 / 90). Realised 476.9k of 4.0m predicted gp (12%).

#### overnight / rp_c16 — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 140 | 39% | 41% |
| 40%-60% | 58 | 50% | 40% |
| 60%-80% | 57 | 68% | 63% |
| 80%-90% | 37 | 88% | 62% |
| 90%-100% | 9 | 94% | 44% |

Calibration error 8.5%. Finished within own P50/P80/P90: 30% / 45% / 48% (targets 50 / 80 / 90). Realised 961.5k of 4.0m predicted gp (24%).

#### overnight / rp_c32 — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 2 | 15% | 0% |
| 20%-40% | 143 | 38% | 44% |
| 40%-60% | 56 | 50% | 38% |
| 60%-80% | 57 | 68% | 63% |
| 80%-90% | 30 | 88% | 53% |
| 90%-100% | 14 | 93% | 86% |

Calibration error 9.6%. Finished within own P50/P80/P90: 33% / 46% / 49% (targets 50 / 80 / 90). Realised -478.1k of 2.3m predicted gp (-21%).

#### overnight / rp_c32 — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 2 | 15% | 0% |
| 20%-40% | 143 | 38% | 54% |
| 40%-60% | 56 | 50% | 48% |
| 60%-80% | 57 | 68% | 65% |
| 80%-90% | 30 | 88% | 53% |
| 90%-100% | 14 | 93% | 86% |

Calibration error 11.9%. Finished within own P50/P80/P90: 40% / 53% / 56% (targets 50 / 80 / 90). Realised -189.6k of 2.3m predicted gp (-8%).

#### overnight / rp_w50_c16 — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 150 | 39% | 25% |
| 40%-60% | 52 | 50% | 29% |
| 60%-80% | 58 | 68% | 52% |
| 80%-90% | 34 | 88% | 59% |
| 90%-100% | 7 | 94% | 43% |

Calibration error 18.1%. Finished within own P50/P80/P90: 21% / 33% / 35% (targets 50 / 80 / 90). Realised -216.5k of 4.5m predicted gp (-5%).

#### overnight / rp_w50_c16 — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 150 | 39% | 36% |
| 40%-60% | 52 | 50% | 42% |
| 60%-80% | 58 | 68% | 59% |
| 80%-90% | 34 | 88% | 62% |
| 90%-100% | 7 | 94% | 43% |

Calibration error 8.5%. Finished within own P50/P80/P90: 28% / 43% / 45% (targets 50 / 80 / 90). Realised 530.3k of 4.5m predicted gp (12%).

#### profit / replay_portfolio — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 43 | 39% | 12% |
| 40%-60% | 71 | 51% | 25% |
| 60%-80% | 112 | 69% | 44% |
| 80%-90% | 24 | 85% | 54% |
| 90%-100% | 9 | 93% | 78% |

Calibration error 25.7%. Finished within own P50/P80/P90: 26% / 35% / 36% (targets 50 / 80 / 90). Realised 3.3m of 21.9m predicted gp (15%).

#### profit / replay_portfolio — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 45 | 39% | 11% |
| 40%-60% | 75 | 52% | 31% |
| 60%-80% | 111 | 69% | 51% |
| 80%-90% | 23 | 85% | 57% |
| 90%-100% | 10 | 94% | 80% |

Calibration error 21.1%. Finished within own P50/P80/P90: 32% / 40% / 40% (targets 50 / 80 / 90). Realised 3.8m of 22.2m predicted gp (17%).

#### profit / rp_w50 — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 34 | 39% | 12% |
| 40%-60% | 66 | 52% | 29% |
| 60%-80% | 124 | 68% | 39% |
| 80%-90% | 25 | 85% | 48% |
| 90%-100% | 10 | 93% | 90% |

Calibration error 27.4%. Finished within own P50/P80/P90: 26% / 35% / 36% (targets 50 / 80 / 90). Realised 3.2m of 22.2m predicted gp (14%).

#### profit / rp_w50 — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 34 | 39% | 12% |
| 40%-60% | 72 | 52% | 38% |
| 60%-80% | 115 | 68% | 49% |
| 80%-90% | 30 | 85% | 53% |
| 90%-100% | 13 | 94% | 77% |

Calibration error 20.2%. Finished within own P50/P80/P90: 34% / 42% / 43% (targets 50 / 80 / 90). Realised 4.2m of 22.3m predicted gp (19%).

#### profit / rp_w100 — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 39 | 39% | 8% |
| 40%-60% | 64 | 53% | 28% |
| 60%-80% | 128 | 69% | 36% |
| 80%-90% | 22 | 85% | 45% |
| 90%-100% | 10 | 94% | 80% |

Calibration error 30.6%. Finished within own P50/P80/P90: 24% / 32% / 32% (targets 50 / 80 / 90). Realised 1.3m of 23.3m predicted gp (6%).

#### profit / rp_w100 — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 41 | 39% | 5% |
| 40%-60% | 66 | 53% | 35% |
| 60%-80% | 124 | 69% | 49% |
| 80%-90% | 26 | 86% | 62% |
| 90%-100% | 13 | 94% | 62% |

Calibration error 22.4%. Finished within own P50/P80/P90: 33% / 40% / 41% (targets 50 / 80 / 90). Realised 5.3m of 23.5m predicted gp (23%).

#### profit / rp_c16 — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 58 | 39% | 41% |
| 40%-60% | 107 | 51% | 53% |
| 60%-80% | 96 | 68% | 54% |
| 80%-90% | 23 | 85% | 65% |
| 90%-100% | 9 | 93% | 67% |

Calibration error 8.4%. Finished within own P50/P80/P90: 49% / 52% / 53% (targets 50 / 80 / 90). Realised 3.8m of 17.8m predicted gp (21%).

#### profit / rp_c16 — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 65 | 39% | 49% |
| 40%-60% | 115 | 51% | 59% |
| 60%-80% | 98 | 69% | 63% |
| 80%-90% | 24 | 85% | 62% |
| 90%-100% | 8 | 93% | 62% |

Calibration error 9.5%. Finished within own P50/P80/P90: 56% / 58% / 59% (targets 50 / 80 / 90). Realised 5.6m of 18.6m predicted gp (30%).

#### profit / rp_c32 — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 92 | 39% | 64% |
| 40%-60% | 106 | 50% | 63% |
| 60%-80% | 115 | 68% | 70% |
| 80%-90% | 28 | 87% | 86% |
| 90%-100% | 12 | 93% | 67% |

Calibration error 11.9%. Finished within own P50/P80/P90: 65% / 67% / 67% (targets 50 / 80 / 90). Realised 1.5m of 14.3m predicted gp (11%).

#### profit / rp_c32 — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 96 | 39% | 68% |
| 40%-60% | 120 | 51% | 70% |
| 60%-80% | 125 | 68% | 77% |
| 80%-90% | 27 | 87% | 89% |
| 90%-100% | 14 | 93% | 64% |

Calibration error 17.4%. Finished within own P50/P80/P90: 71% / 73% / 73% (targets 50 / 80 / 90). Realised 3.1m of 15.2m predicted gp (20%).

#### profit / rp_w50_c16 — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 44 | 39% | 41% |
| 40%-60% | 108 | 51% | 43% |
| 60%-80% | 99 | 68% | 58% |
| 80%-90% | 20 | 85% | 70% |
| 90%-100% | 10 | 93% | 80% |

Calibration error 8.8%. Finished within own P50/P80/P90: 47% / 51% / 51% (targets 50 / 80 / 90). Realised 2.4m of 17.6m predicted gp (14%).

#### profit / rp_w50_c16 — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 46 | 39% | 50% |
| 40%-60% | 122 | 51% | 55% |
| 60%-80% | 107 | 68% | 64% |
| 80%-90% | 23 | 86% | 70% |
| 90%-100% | 8 | 94% | 75% |

Calibration error 6.1%. Finished within own P50/P80/P90: 56% / 59% / 59% (targets 50 / 80 / 90). Realised 5.2m of 19.0m predicted gp (28%).
