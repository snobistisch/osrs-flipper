
### active — all period, bank 20.0m, 12 segments, 925 decisions

Fill rule `strict_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| policy | 8.2k [4.7k .. 11.3k] | 12.5k | 1.1k | 4.4k | 0.86% | 80% | 12% | 91% | 69% | -4.27% | 2.37% | 100% | 11% | 100.5 | — | — |
| browser | 8.3k [4.8k .. 11.4k] | 12.6k | 1.1k | 4.5k | 0.87% | 80% | 11% | 91% | 69% | -4.26% | 2.37% | 100% | 11% | 100.5 | — | — |

Fill rule `touch_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| policy | 11.2k [8.1k .. 14.1k] | 14.8k | 1.5k | 6.3k | 1.05% | 85% | 9% | 94% | 75% | -3.25% | 2.31% | 100% | 12% | 111.5 | — | — |
| browser | 11.3k [8.1k .. 14.2k] | 14.9k | 1.5k | 6.3k | 1.06% | 85% | 9% | 94% | 76% | -3.25% | 2.31% | 100% | 12% | 111.5 | — | — |

Bank gp/h under every fill assumption (rule_capture):

| method | strict_0.03 | strict_0.10 | strict_0.30 | touch_0.03 | touch_0.10 | touch_0.30 |
|---|---|---|---|---|---|---|
| policy | -1.6k | 8.2k | 13.8k | 2.5k | 11.2k | 18.2k |
| browser | -1.7k | 8.3k | 13.8k | 2.5k | 11.3k | 18.2k |

### overnight — all period, bank 20.0m, 13 segments, 38 decisions

Fill rule `strict_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| policy | 1.3k [-1.0k .. 3.9k] | 6.1k | 204 | 257 | 0.34% | 61% | 21% | 82% | 40% | -6.70% | 1.69% | 99% | 33% | 15.9 | — | — |
| browser | 1.1k [-1.5k .. 3.7k] | 6.0k | 168 | 211 | 0.28% | 61% | 21% | 82% | 39% | -6.70% | 2.22% | 99% | 33% | 15.9 | — | — |

Fill rule `touch_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| policy | 2.5k [190 .. 5.0k] | 7.1k | 382 | 482 | 0.62% | 66% | 19% | 86% | 48% | -6.37% | 1.66% | 99% | 33% | 15.9 | — | — |
| browser | 2.2k [-308 .. 4.9k] | 6.9k | 346 | 434 | 0.56% | 66% | 19% | 86% | 48% | -6.37% | 2.19% | 99% | 33% | 15.9 | — | — |

Bank gp/h under every fill assumption (rule_capture):

| method | strict_0.03 | strict_0.10 | strict_0.30 | touch_0.03 | touch_0.10 | touch_0.30 |
|---|---|---|---|---|---|---|
| policy | -1.5k | 1.3k | 3.0k | -646 | 2.5k | 4.1k |
| browser | -1.6k | 1.1k | 2.7k | -819 | 2.2k | 3.9k |

### profit — all period, bank 20.0m, 11 segments, 110 decisions

Fill rule `strict_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| policy | 8.3k [-76 .. 16.6k] | 15.7k | 988 | 647 | 0.75% | 78% | 16% | 94% | 52% | -7.75% | 4.93% | 100% | 84% | 15.7 | — | — |
| browser | 8.3k [-35 .. 16.5k] | 15.7k | 987 | 648 | 0.75% | 78% | 16% | 94% | 51% | -7.74% | 4.93% | 100% | 84% | 15.7 | — | — |

Fill rule `touch_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| policy | 13.0k [5.4k .. 20.5k] | 19.6k | 1.6k | 1.0k | 1.09% | 83% | 13% | 96% | 59% | -6.19% | 3.56% | 100% | 85% | 16.7 | — | — |
| browser | 13.0k [5.5k .. 20.6k] | 19.7k | 1.6k | 1.0k | 1.10% | 83% | 13% | 96% | 59% | -6.16% | 3.56% | 100% | 85% | 16.8 | — | — |

Bank gp/h under every fill assumption (rule_capture):

| method | strict_0.03 | strict_0.10 | strict_0.30 | touch_0.03 | touch_0.10 | touch_0.30 |
|---|---|---|---|---|---|---|
| policy | -7.5k | 8.3k | 19.6k | -4.3k | 13.0k | 22.9k |
| browser | -7.5k | 8.3k | 19.6k | -4.3k | 13.0k | 23.0k |

#### active / policy — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1879 | 81% | 68% |
| 90%-100% | 57 | 95% | 79% |

Calibration error 12.7%. Finished within own P50/P80/P90: 50% / 68% / 68% (targets 50 / 80 / 90). Realised 3.8m of 5.6m predicted gp (68%).

#### active / policy — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 2091 | 81% | 75% |
| 90%-100% | 58 | 95% | 86% |

Calibration error 5.7%. Finished within own P50/P80/P90: 59% / 75% / 75% (targets 50 / 80 / 90). Realised 5.2m of 6.0m predicted gp (86%).

#### active / browser — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1880 | 81% | 68% |
| 90%-100% | 56 | 95% | 79% |

Calibration error 12.5%. Finished within own P50/P80/P90: 50% / 68% / 69% (targets 50 / 80 / 90). Realised 3.8m of 5.6m predicted gp (69%).

#### active / browser — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 2092 | 81% | 75% |
| 90%-100% | 57 | 95% | 86% |

Calibration error 5.6%. Finished within own P50/P80/P90: 59% / 75% / 75% (targets 50 / 80 / 90). Realised 5.2m of 6.1m predicted gp (86%).

#### overnight / policy — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 141 | 39% | 33% |
| 40%-60% | 53 | 50% | 23% |
| 60%-80% | 57 | 68% | 54% |
| 80%-90% | 39 | 88% | 64% |
| 90%-100% | 12 | 94% | 42% |

Calibration error 14.9%. Finished within own P50/P80/P90: 23% / 36% / 40% (targets 50 / 80 / 90). Realised 604.1k of 3.9m predicted gp (15%).

#### overnight / policy — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 141 | 39% | 45% |
| 40%-60% | 53 | 50% | 38% |
| 60%-80% | 57 | 68% | 58% |
| 80%-90% | 39 | 88% | 64% |
| 90%-100% | 12 | 94% | 42% |

Calibration error 12.0%. Finished within own P50/P80/P90: 30% / 45% / 48% (targets 50 / 80 / 90). Realised 1.1m of 3.9m predicted gp (29%).

#### overnight / browser — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 142 | 39% | 33% |
| 40%-60% | 53 | 50% | 23% |
| 60%-80% | 57 | 68% | 54% |
| 80%-90% | 38 | 88% | 63% |
| 90%-100% | 12 | 94% | 42% |

Calibration error 15.1%. Finished within own P50/P80/P90: 23% / 36% / 39% (targets 50 / 80 / 90). Realised 497.8k of 3.9m predicted gp (13%).

#### overnight / browser — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 142 | 39% | 44% |
| 40%-60% | 53 | 50% | 38% |
| 60%-80% | 57 | 68% | 58% |
| 80%-90% | 38 | 88% | 63% |
| 90%-100% | 12 | 94% | 42% |

Calibration error 12.0%. Finished within own P50/P80/P90: 30% / 45% / 48% (targets 50 / 80 / 90). Realised 1.0m of 3.9m predicted gp (26%).

#### profit / policy — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 60 | 39% | 38% |
| 40%-60% | 104 | 51% | 51% |
| 60%-80% | 93 | 68% | 54% |
| 80%-90% | 18 | 85% | 78% |
| 90%-100% | 12 | 94% | 67% |

Calibration error 6.5%. Finished within own P50/P80/P90: 47% / 51% / 52% (targets 50 / 80 / 90). Realised 3.7m of 17.4m predicted gp (21%).

#### profit / policy — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 63 | 39% | 48% |
| 40%-60% | 113 | 51% | 60% |
| 60%-80% | 97 | 68% | 60% |
| 80%-90% | 22 | 86% | 73% |
| 90%-100% | 12 | 93% | 75% |

Calibration error 9.5%. Finished within own P50/P80/P90: 55% / 59% / 59% (targets 50 / 80 / 90). Realised 5.7m of 18.2m predicted gp (31%).

#### profit / browser — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 59 | 39% | 37% |
| 40%-60% | 107 | 51% | 50% |
| 60%-80% | 92 | 68% | 54% |
| 80%-90% | 18 | 85% | 78% |
| 90%-100% | 12 | 94% | 67% |

Calibration error 6.4%. Finished within own P50/P80/P90: 47% / 51% / 51% (targets 50 / 80 / 90). Realised 3.7m of 17.5m predicted gp (21%).

#### profit / browser — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 63 | 39% | 48% |
| 40%-60% | 115 | 51% | 61% |
| 60%-80% | 96 | 68% | 60% |
| 80%-90% | 22 | 86% | 73% |
| 90%-100% | 12 | 93% | 75% |

Calibration error 9.6%. Finished within own P50/P80/P90: 56% / 59% / 59% (targets 50 / 80 / 90). Realised 5.7m of 18.2m predicted gp (32%).
