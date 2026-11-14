
### active — holdout period, bank 20.0m, 8 segments, 651 decisions

Fill rule `strict_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | -30.6k [-40.6k .. -19.2k] | 4.3k | -3.9k | -2.0k | -0.66% | 45% | 21% | 66% | 30% | -4.07% | 11.42% | 100% | 91% | 79.3 | — | — |
| browser_baseline | 5.9k [2.6k .. 8.6k] | 18.4k | 767 | 917 | 0.25% | 68% | 17% | 85% | 43% | -3.15% | 1.64% | 97% | 41% | 77.6 | 36.5k [23.8k .. 47.6k] | 0.000 |
| policy | 10.5k [9.3k .. 11.6k] | 13.1k | 1.4k | 7.1k | 1.24% | 81% | 8% | 90% | 70% | -2.55% | 0.21% | 99% | 9% | 103.5 | 41.2k [30.1k .. 50.9k] | 0.000 |
| browser | 10.5k [9.3k .. 11.6k] | 13.1k | 1.4k | 7.1k | 1.24% | 81% | 8% | 90% | 70% | -2.55% | 0.21% | 99% | 9% | 103.5 | 41.2k [30.1k .. 50.9k] | 0.000 |
| naive_roi | -67 [-481 .. 364] | 2.4k | -8 | -34 | -5.90% | 2% | 3% | 5% | 0% | 0.00% | 0.15% | 100% | 10% | 92.4 | 30.6k [19.0k .. 40.6k] | 0.000 |
| naive_margin | -17.5k [-22.7k .. -12.9k] | 11.6k | -2.2k | -1.2k | -5.13% | 1% | 7% | 9% | 0% | -1.86% | 6.70% | 100% | 77% | 89.4 | 13.1k [1.9k .. 23.7k] | 0.009 |
| random | -8.6k [-13.7k .. -4.5k] | 68 | -1.1k | -819 | -1.47% | 25% | 15% | 41% | 3% | -1.94% | 3.61% | 100% | 63% | 77.9 | 22.1k [7.9k .. 34.3k] | 0.001 |
| ev_per_offer | -27.7k [-40.2k .. -14.8k] | 4.4k | -3.5k | -1.8k | -0.63% | 41% | 20% | 62% | 27% | -4.26% | 11.71% | 99% | 89% | 78.5 | 2.9k [-4.2k .. 10.6k] | 0.234 |
| ev_roi | 69 [18 .. 128] | 278 | 9 | 4.6k | 19.22% | 13% | 7% | 21% | 7% | -15.24% | 0.02% | 99% | 0% | 86.5 | 30.7k [19.3k .. 40.6k] | 0.000 |
| gp_slot_hour | -34.0k [-43.9k .. -22.9k] | 4.3k | -4.3k | -2.1k | -0.71% | 40% | 21% | 61% | 30% | -4.01% | 12.32% | 99% | 93% | 80.1 | -3.4k [-10.1k .. 3.1k] | 0.857 |
| gp_capital_hour | 107 [38 .. 185] | 356 | 13 | 9.1k | 21.27% | 14% | 6% | 22% | 8% | -9.98% | 0.01% | 99% | 0% | 87.2 | 30.7k [19.3k .. 40.7k] | 0.000 |

Fill rule `touch_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | 7.5k [-7.5k .. 21.7k] | 44.4k | 982 | 467 | 0.13% | 69% | 16% | 86% | 57% | -3.69% | 12.67% | 100% | 91% | 99.6 | — | — |
| browser_baseline | 13.3k [9.2k .. 16.7k] | 24.1k | 1.8k | 2.2k | 0.50% | 81% | 14% | 94% | 55% | -2.62% | 1.83% | 97% | 41% | 85.2 | 5.8k [-10.6k .. 22.7k] | 0.264 |
| policy | 13.2k [11.8k .. 14.4k] | 15.6k | 1.8k | 9.2k | 1.34% | 87% | 7% | 94% | 78% | -1.82% | 0.25% | 99% | 9% | 116.9 | 5.7k [-8.5k .. 20.2k] | 0.234 |
| browser | 13.2k [11.8k .. 14.4k] | 15.6k | 1.8k | 9.2k | 1.34% | 87% | 7% | 94% | 78% | -1.82% | 0.25% | 99% | 9% | 116.9 | 5.7k [-8.5k .. 20.2k] | 0.234 |
| naive_roi | 992 [27 .. 2.2k] | 5.8k | 123 | 369 | 58.69% | 9% | 4% | 15% | 0% | 0.00% | 0.31% | 100% | 14% | 87.4 | -6.5k [-20.8k .. 8.4k] | 0.821 |
| naive_margin | -19.0k [-27.1k .. -12.1k] | 21.1k | -2.4k | -1.3k | -4.31% | 2% | 9% | 11% | 1% | -2.17% | 9.42% | 100% | 79% | 87.7 | -26.5k [-43.3k .. -9.4k] | 0.999 |
| random | -4.0k [-8.3k .. 388] | 5.0k | -500 | -400 | -0.62% | 50% | 17% | 67% | 4% | -1.40% | 3.10% | 100% | 68% | 71.3 | -11.5k [-26.6k .. 4.4k] | 0.924 |
| ev_per_offer | 1.7k [-18.1k .. 21.8k] | 40.9k | 217 | 101 | 0.03% | 62% | 18% | 81% | 49% | -3.60% | 14.71% | 99% | 91% | 91.5 | -5.8k [-18.7k .. 7.6k] | 0.802 |
| ev_roi | 2.5k [2.0k .. 3.2k] | 3.2k | 345 | 276.4k | 82.89% | 72% | 5% | 80% | 63% | -0.28% | 0.01% | 99% | 0% | 115.8 | -5.0k [-19.2k .. 9.9k] | 0.761 |
| gp_slot_hour | -2.0k [-17.9k .. 14.9k] | 37.9k | -256 | -116 | -0.04% | 64% | 17% | 81% | 53% | -3.57% | 15.95% | 99% | 93% | 93.9 | -9.5k [-18.3k .. -2.8k] | 0.998 |
| gp_capital_hour | 2.2k [1.7k .. 2.8k] | 2.9k | 308 | 239.7k | 77.51% | 74% | 4% | 82% | 68% | 0.00% | 0.01% | 99% | 0% | 120.2 | -5.2k [-19.4k .. 9.5k] | 0.773 |

Bank gp/h under every fill assumption (rule_capture):

| method | strict_0.03 | strict_0.10 | strict_0.30 | touch_0.03 | touch_0.10 | touch_0.30 |
|---|---|---|---|---|---|---|
| current | -37.1k | -30.6k | -16.9k | -24.6k | 7.5k | 35.9k |
| browser_baseline | -5.3k | 5.9k | 19.4k | -2.0k | 13.3k | 29.9k |
| policy | 3.9k | 10.5k | 13.5k | 6.2k | 13.2k | 17.5k |
| browser | 3.9k | 10.5k | 13.5k | 6.2k | 13.2k | 17.5k |
| naive_roi | -69 | -67 | -693 | 234 | 992 | 3.4k |
| naive_margin | -7.6k | -17.5k | -25.9k | -8.7k | -19.0k | -19.6k |
| random | -5.1k | -8.6k | -13.1k | -3.9k | -4.0k | -3.1k |
| ev_per_offer | -42.8k | -27.7k | -16.8k | -18.2k | 1.7k | 17.6k |
| ev_roi | 39 | 69 | 151 | 2.2k | 2.5k | 3.0k |
| gp_slot_hour | -47.4k | -34.0k | -25.3k | -27.8k | -2.0k | 18.1k |
| gp_capital_hour | 55 | 107 | 117 | 1.8k | 2.2k | 2.6k |

### overnight — holdout period, bank 20.0m, 9 segments, 27 decisions

Fill rule `strict_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | -12.0k [-20.1k .. -4.0k] | 806 | -1.9k | -804 | -1.41% | 34% | 26% | 61% | 19% | -6.04% | 4.82% | 100% | 95% | 16.0 | — | — |
| browser_baseline | -1.5k [-4.1k .. 1.3k] | 5.9k | -347 | -180 | -0.30% | 46% | 24% | 71% | 18% | -4.39% | 1.53% | 65% | 52% | 10.4 | 10.5k [3.4k .. 17.5k] | 0.002 |
| policy | 2.7k [803 .. 4.6k] | 5.9k | 431 | 566 | 0.79% | 60% | 15% | 75% | 45% | -5.38% | 0.42% | 98% | 31% | 15.6 | 14.7k [6.4k .. 22.9k] | 0.000 |
| browser | 2.7k [803 .. 4.6k] | 5.9k | 431 | 566 | 0.79% | 60% | 15% | 75% | 45% | -5.38% | 0.42% | 98% | 31% | 15.6 | 14.7k [6.4k .. 22.9k] | 0.000 |
| naive_roi | 34 [-186 .. 310] | 1.1k | 6 | 22 | 11.45% | 3% | 6% | 9% | 0% | -0.35% | 0.08% | 100% | 12% | 16.0 | 12.1k [3.9k .. 20.3k] | 0.002 |
| naive_margin | -16.7k [-33.3k .. -6.4k] | 15.8k | -2.8k | -1.6k | -8.31% | 4% | 19% | 23% | 2% | -6.82% | 13.97% | 100% | 74% | 16.0 | -4.7k [-22.8k .. 8.9k] | 0.681 |
| random | -9.3k [-22.1k .. -1.6k] | -2.8k | -1.4k | -1.3k | -4.00% | 33% | 31% | 66% | 4% | -8.16% | 7.38% | 100% | 47% | 16.0 | 2.7k [-9.0k .. 13.8k] | 0.306 |
| ev_per_offer | -13.8k [-24.0k .. -3.9k] | -1.4k | -2.2k | -918 | -1.84% | 29% | 26% | 57% | 18% | -7.10% | 5.43% | 100% | 97% | 16.0 | -1.8k [-8.2k .. 4.5k] | 0.700 |
| ev_roi | -75 [-289 .. 52] | 209 | -14 | -3.2k | -11.65% | 8% | 9% | 17% | 6% | -3.28% | 0.16% | 98% | 0% | 15.6 | 12.0k [4.0k .. 20.0k] | 0.002 |
| gp_slot_hour | -14.5k [-23.7k .. -5.7k] | -3.4k | -2.3k | -941 | -1.51% | 33% | 24% | 57% | 28% | -6.73% | 5.82% | 100% | 100% | 16.0 | -2.4k [-13.8k .. 9.0k] | 0.664 |
| gp_capital_hour | -19 [-129 .. 55] | 44 | -3 | -1.0k | -6.28% | 9% | 8% | 19% | 7% | -4.25% | 0.08% | 98% | 0% | 15.7 | 12.0k [3.9k .. 20.1k] | 0.002 |

Fill rule `touch_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | 13.0k [4.9k .. 21.4k] | 26.4k | 2.0k | 835 | 1.09% | 67% | 23% | 89% | 52% | -6.08% | 1.36% | 100% | 95% | 16.0 | — | — |
| browser_baseline | -324 [-3.0k .. 2.5k] | 6.7k | -75 | -39 | -0.06% | 50% | 24% | 74% | 21% | -4.35% | 1.53% | 65% | 52% | 10.4 | -13.4k [-21.1k .. -5.8k] | 1.000 |
| policy | 3.3k [1.2k .. 5.5k] | 6.6k | 536 | 702 | 0.91% | 66% | 15% | 81% | 54% | -5.38% | 0.53% | 98% | 31% | 15.6 | -9.7k [-18.3k .. -2.0k] | 0.995 |
| browser | 3.3k [1.2k .. 5.5k] | 6.6k | 536 | 702 | 0.91% | 66% | 15% | 81% | 54% | -5.38% | 0.53% | 98% | 31% | 15.6 | -9.7k [-18.3k .. -2.0k] | 0.995 |
| naive_roi | 98 [-123 .. 373] | 3.1k | 16 | 63 | 21.72% | 15% | 11% | 30% | 0% | -1.14% | 0.07% | 100% | 12% | 16.0 | -12.9k [-21.3k .. -4.6k] | 1.000 |
| naive_margin | -17.7k [-34.6k .. -7.6k] | 19.9k | -2.9k | -1.6k | -7.26% | 6% | 23% | 29% | 2% | -7.05% | 14.26% | 100% | 74% | 16.0 | -30.7k [-49.3k .. -16.7k] | 1.000 |
| random | -9.7k [-22.2k .. -1.9k] | -1.7k | -1.4k | -1.4k | -3.44% | 47% | 35% | 83% | 6% | -7.76% | 7.44% | 100% | 47% | 16.0 | -22.7k [-33.1k .. -13.3k] | 1.000 |
| ev_per_offer | 4.4k [-7.7k .. 15.8k] | 17.1k | 664 | 282 | 0.44% | 51% | 27% | 80% | 41% | -6.98% | 4.59% | 100% | 97% | 16.0 | -8.7k [-17.2k .. -798] | 0.984 |
| ev_roi | 4 [-211 .. 132] | 333 | 1 | 158 | 0.50% | 36% | 11% | 55% | 24% | -7.77% | 0.16% | 98% | 0% | 15.6 | -13.0k [-21.2k .. -4.9k] | 1.000 |
| gp_slot_hour | -5.4k [-17.1k .. 5.7k] | 5.7k | -849 | -343 | -0.49% | 57% | 23% | 80% | 51% | -6.62% | 4.59% | 100% | 100% | 16.0 | -18.4k [-30.8k .. -6.5k] | 1.000 |
| gp_capital_hour | 139 [-21 .. 297] | 214 | 23 | 7.3k | 27.43% | 41% | 11% | 57% | 25% | -4.03% | 0.07% | 98% | 0% | 15.7 | -12.9k [-21.2k .. -4.7k] | 1.000 |

Bank gp/h under every fill assumption (rule_capture):

| method | strict_0.03 | strict_0.10 | strict_0.30 | touch_0.03 | touch_0.10 | touch_0.30 |
|---|---|---|---|---|---|---|
| current | -14.6k | -12.0k | -9.5k | 732 | 13.0k | 15.9k |
| browser_baseline | -2.1k | -1.5k | 2.0k | -1.6k | -324 | 3.5k |
| policy | 35 | 2.7k | 3.8k | 736 | 3.3k | 4.6k |
| browser | 35 | 2.7k | 3.8k | 736 | 3.3k | 4.6k |
| naive_roi | 26 | 34 | 98 | 37 | 98 | 327 |
| naive_margin | -10.9k | -16.7k | -20.0k | -11.5k | -17.7k | -19.8k |
| random | -5.3k | -9.3k | -11.7k | -5.4k | -9.7k | -11.6k |
| ev_per_offer | -14.1k | -13.8k | -8.3k | -2.6k | 4.4k | 8.5k |
| ev_roi | 6 | -75 | -77 | 46 | 4 | 65 |
| gp_slot_hour | -10.8k | -14.5k | -11.6k | -3.4k | -5.4k | -2.4k |
| gp_capital_hour | -5 | -19 | -22 | 109 | 139 | 210 |

### profit — holdout period, bank 20.0m, 8 segments, 77 decisions

Fill rule `strict_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | -18.6k [-56.5k .. 3.2k] | -8.1k | -2.2k | -961 | -1.55% | 63% | 14% | 78% | 53% | -5.28% | 29.47% | 100% | 100% | 18.6 | — | — |
| browser_baseline | 12.0k [6.5k .. 17.1k] | 18.7k | 1.5k | 867 | 1.06% | 80% | 15% | 95% | 48% | -2.96% | 1.02% | 93% | 89% | 14.3 | 30.6k [8.2k .. 66.7k] | 0.000 |
| policy | 15.6k [10.9k .. 21.6k] | 20.4k | 1.8k | 1.2k | 1.36% | 82% | 11% | 93% | 60% | -4.49% | 1.77% | 100% | 79% | 16.8 | 34.2k [10.8k .. 71.9k] | 0.000 |
| browser | 15.6k [10.9k .. 21.6k] | 20.4k | 1.8k | 1.2k | 1.36% | 82% | 11% | 93% | 60% | -4.49% | 1.77% | 100% | 79% | 16.8 | 34.2k [10.8k .. 71.9k] | 0.000 |
| naive_roi | -295 [-723 .. -1] | 125 | -30 | -129 | -22.89% | 4% | 6% | 10% | 0% | -0.20% | 0.30% | 100% | 10% | 18.3 | 18.3k [-3.5k .. 56.3k] | 0.153 |
| naive_margin | -12.4k [-34.0k .. 5.5k] | 24.6k | -1.3k | -682 | -4.45% | 12% | 14% | 26% | 5% | -6.46% | 13.66% | 100% | 80% | 16.4 | 6.2k [-28.4k .. 50.4k] | 0.418 |
| random | -1.1k [-4.2k .. 1.7k] | 1.9k | -116 | -107 | -0.35% | 47% | 21% | 69% | 13% | -7.40% | 2.73% | 100% | 57% | 14.3 | 17.5k [-4.9k .. 55.8k] | 0.203 |
| ev_per_offer | -6.8k [-18.6k .. 5.0k] | 3.6k | -785 | -322 | -0.71% | 47% | 16% | 63% | 39% | -6.76% | 7.66% | 100% | 99% | 17.0 | 11.8k [-8.5k .. 42.6k] | 0.253 |
| ev_roi | 2.0k [225 .. 5.0k] | 1.6k | 213 | 13.2k | 178.49% | 14% | 6% | 20% | 7% | -2.35% | 0.00% | 100% | 1% | 17.9 | 20.7k [-1.6k .. 59.4k] | 0.066 |
| gp_slot_hour | -9.4k [-27.8k .. 3.6k] | -2.3k | -1.2k | -477 | -0.58% | 60% | 11% | 71% | 58% | -5.18% | 16.90% | 100% | 99% | 20.6 | 9.3k [-6.8k .. 32.6k] | 0.215 |
| gp_capital_hour | 1.6k [133 .. 4.5k] | 1.3k | 171 | 9.2k | 277.71% | 14% | 7% | 20% | 7% | -5.05% | 0.01% | 100% | 1% | 17.8 | 20.3k [-1.8k .. 58.3k] | 0.070 |

Fill rule `touch_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | 45.6k [1.3k .. 73.0k] | 52.9k | 5.9k | 2.8k | 2.21% | 83% | 10% | 93% | 73% | -2.73% | 26.50% | 100% | 99% | 22.6 | — | — |
| browser_baseline | 16.2k [12.2k .. 20.2k] | 22.0k | 2.1k | 1.3k | 1.32% | 85% | 13% | 97% | 55% | -2.41% | 0.71% | 91% | 87% | 15.1 | -29.4k [-56.5k .. 12.8k] | 0.928 |
| policy | 18.4k [13.9k .. 23.1k] | 22.7k | 2.3k | 1.6k | 1.47% | 85% | 10% | 95% | 66% | -3.29% | 1.77% | 100% | 81% | 17.4 | -27.2k [-54.7k .. 16.3k] | 0.919 |
| browser | 18.4k [13.9k .. 23.1k] | 22.7k | 2.3k | 1.6k | 1.47% | 85% | 10% | 95% | 66% | -3.29% | 1.77% | 100% | 81% | 17.4 | -27.2k [-54.7k .. 16.3k] | 0.919 |
| naive_roi | 1.2k [-157 .. 3.4k] | 3.0k | 123 | 441 | 81.39% | 28% | 6% | 38% | 0% | -0.43% | 0.28% | 100% | 13% | 16.2 | -44.3k [-71.7k .. -429] | 0.977 |
| naive_margin | -10.4k [-36.1k .. 8.5k] | 31.5k | -1.1k | -561 | -3.65% | 14% | 16% | 30% | 6% | -6.38% | 17.12% | 100% | 83% | 16.2 | -56.0k [-95.3k .. -7.5k] | 0.989 |
| random | -3.1k [-8.5k .. 1.7k] | 20 | -341 | -285 | -0.89% | 70% | 19% | 89% | 18% | -5.16% | 5.77% | 100% | 64% | 13.8 | -48.7k [-75.4k .. -8.1k] | 0.988 |
| ev_per_offer | 24.4k [5.2k .. 43.4k] | 36.3k | 3.1k | 1.2k | 1.65% | 68% | 13% | 82% | 65% | -5.45% | 4.48% | 100% | 99% | 21.6 | -21.1k [-48.8k .. 12.1k] | 0.902 |
| ev_roi | 1.9k [384 .. 4.6k] | 1.6k | 223 | 16.0k | 329.99% | 49% | 5% | 58% | 36% | 0.00% | 0.00% | 100% | 1% | 18.0 | -43.7k [-70.9k .. 517] | 0.973 |
| gp_slot_hour | 3.2k [-17.1k .. 18.8k] | 10.2k | 460 | 163 | 0.17% | 76% | 9% | 85% | 74% | -3.62% | 19.23% | 99% | 100% | 25.5 | -42.4k [-63.0k .. -15.1k] | 0.997 |
| gp_capital_hour | 2.0k [447 .. 4.8k] | 1.7k | 232 | 16.4k | 150.85% | 49% | 8% | 61% | 37% | -5.03% | 0.01% | 100% | 1% | 18.0 | -43.5k [-70.7k .. 927] | 0.973 |

Bank gp/h under every fill assumption (rule_capture):

| method | strict_0.03 | strict_0.10 | strict_0.30 | touch_0.03 | touch_0.10 | touch_0.30 |
|---|---|---|---|---|---|---|
| current | -23.4k | -18.6k | -6.4k | 7.2k | 45.6k | 69.5k |
| browser_baseline | -3.2k | 12.0k | 26.0k | -196 | 16.2k | 33.0k |
| policy | 1.6k | 15.6k | 28.5k | 3.8k | 18.4k | 36.8k |
| browser | 1.6k | 15.6k | 28.5k | 3.8k | 18.4k | 36.8k |
| naive_roi | -127 | -295 | -564 | 1.0k | 1.2k | 2.0k |
| naive_margin | -11.1k | -12.4k | -11.7k | -10.1k | -10.4k | 1.4k |
| random | -5.8k | -1.1k | 3.1k | -4.8k | -3.1k | 8.7k |
| ev_per_offer | -8.6k | -6.8k | 578 | 9.1k | 24.4k | 48.0k |
| ev_roi | 489 | 2.0k | 2.2k | 622 | 1.9k | 2.6k |
| gp_slot_hour | -18.0k | -9.4k | -8.5k | -11.1k | 3.2k | 14.1k |
| gp_capital_hour | 473 | 1.6k | 2.0k | 944 | 2.0k | 3.0k |

#### active / current — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 742 | 82% | 22% |
| 90%-100% | 333 | 97% | 50% |

Calibration error 56.2%. Finished within own P50/P80/P90: 8% / 21% / 24% (targets 50 / 80 / 90). Realised -10.0m of 213.5m predicted gp (-5%).

#### active / current — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 949 | 82% | 55% |
| 90%-100% | 402 | 97% | 61% |

Calibration error 29.0%. Finished within own P50/P80/P90: 37% / 48% / 51% (targets 50 / 80 / 90). Realised 2.4m of 221.0m predicted gp (1%).

#### active / browser_baseline — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1050 | 81% | 43% |
| 90%-100% | 3 | 92% | 33% |

Calibration error 37.3%. Finished within own P50/P80/P90: 24% / 43% / 43% (targets 50 / 80 / 90). Realised 1.9m of 10.7m predicted gp (18%).

#### active / browser_baseline — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1151 | 80% | 56% |
| 90%-100% | 4 | 92% | 25% |

Calibration error 25.1%. Finished within own P50/P80/P90: 37% / 55% / 55% (targets 50 / 80 / 90). Realised 4.3m of 11.4m predicted gp (38%).

#### active / policy — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1361 | 81% | 70% |
| 90%-100% | 43 | 94% | 79% |

Calibration error 10.7%. Finished within own P50/P80/P90: 52% / 70% / 70% (targets 50 / 80 / 90). Realised 3.4m of 3.5m predicted gp (98%).

#### active / policy — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1543 | 81% | 78% |
| 90%-100% | 43 | 94% | 84% |

Calibration error 3.2%. Finished within own P50/P80/P90: 63% / 77% / 78% (targets 50 / 80 / 90). Realised 4.3m of 3.9m predicted gp (110%).

#### active / browser — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1361 | 81% | 70% |
| 90%-100% | 43 | 94% | 79% |

Calibration error 10.7%. Finished within own P50/P80/P90: 52% / 70% / 70% (targets 50 / 80 / 90). Realised 3.4m of 3.5m predicted gp (98%).

#### active / browser — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1543 | 81% | 78% |
| 90%-100% | 43 | 94% | 84% |

Calibration error 3.2%. Finished within own P50/P80/P90: 63% / 77% / 78% (targets 50 / 80 / 90). Realised 4.3m of 3.9m predicted gp (110%).

#### active / ev_per_offer — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 774 | 82% | 19% |
| 90%-100% | 290 | 97% | 47% |

Calibration error 59.2%. Finished within own P50/P80/P90: 6% / 18% / 21% (targets 50 / 80 / 90). Realised -9.0m of 214.6m predicted gp (-4%).

#### active / ev_per_offer — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 922 | 82% | 47% |
| 90%-100% | 319 | 97% | 56% |

Calibration error 36.5%. Finished within own P50/P80/P90: 30% / 41% / 44% (targets 50 / 80 / 90). Realised 545.3k of 219.9m predicted gp (0%).

#### active / ev_roi — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1067 | 82% | 7% |
| 90%-100% | 106 | 92% | 8% |

Calibration error 76.2%. Finished within own P50/P80/P90: 4% / 6% / 7% (targets 50 / 80 / 90). Realised 22.4k of 190.8m predicted gp (0%).

#### active / ev_roi — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1441 | 82% | 64% |
| 90%-100% | 130 | 92% | 55% |

Calibration error 19.7%. Finished within own P50/P80/P90: 51% / 61% / 63% (targets 50 / 80 / 90). Realised 825.4k of 191.3m predicted gp (0%).

#### active / gp_slot_hour — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 717 | 83% | 21% |
| 90%-100% | 369 | 97% | 47% |

Calibration error 57.3%. Finished within own P50/P80/P90: 8% / 19% / 23% (targets 50 / 80 / 90). Realised -11.1m of 213.0m predicted gp (-5%).

#### active / gp_slot_hour — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 839 | 82% | 51% |
| 90%-100% | 435 | 97% | 57% |

Calibration error 34.4%. Finished within own P50/P80/P90: 30% / 41% / 46% (targets 50 / 80 / 90). Realised -641.2k of 218.1m predicted gp (-0%).

#### active / gp_capital_hour — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1038 | 83% | 8% |
| 90%-100% | 144 | 92% | 10% |

Calibration error 75.4%. Finished within own P50/P80/P90: 4% / 7% / 8% (targets 50 / 80 / 90). Realised 34.9k of 190.5m predicted gp (0%).

#### active / gp_capital_hour — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1436 | 82% | 69% |
| 90%-100% | 194 | 92% | 61% |

Calibration error 15.6%. Finished within own P50/P80/P90: 54% / 65% / 67% (targets 50 / 80 / 90). Realised 731.2k of 191.1m predicted gp (0%).

#### overnight / current — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 68 | 39% | 0% |
| 40%-60% | 17 | 50% | 18% |
| 60%-80% | 30 | 71% | 20% |
| 80%-90% | 22 | 85% | 14% |
| 90%-100% | 79 | 98% | 37% |

Calibration error 51.3%. Finished within own P50/P80/P90: 1% / 6% / 9% (targets 50 / 80 / 90). Realised -3.9m of 72.6m predicted gp (-5%).

#### overnight / current — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 68 | 39% | 68% |
| 40%-60% | 17 | 49% | 41% |
| 60%-80% | 31 | 71% | 32% |
| 80%-90% | 23 | 85% | 48% |
| 90%-100% | 77 | 97% | 49% |

Calibration error 36.4%. Finished within own P50/P80/P90: 27% / 34% / 38% (targets 50 / 80 / 90). Realised 4.2m of 72.7m predicted gp (6%).

#### overnight / browser_baseline — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 73 | 39% | 15% |
| 40%-60% | 34 | 48% | 12% |
| 60%-80% | 12 | 70% | 25% |
| 80%-90% | 11 | 87% | 27% |
| 90%-100% | 10 | 97% | 40% |

Calibration error 33.8%. Finished within own P50/P80/P90: 11% / 15% / 17% (targets 50 / 80 / 90). Realised -482.7k of 2.8m predicted gp (-17%).

#### overnight / browser_baseline — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 73 | 39% | 19% |
| 40%-60% | 34 | 48% | 12% |
| 60%-80% | 12 | 70% | 25% |
| 80%-90% | 11 | 87% | 36% |
| 90%-100% | 10 | 97% | 40% |

Calibration error 30.9%. Finished within own P50/P80/P90: 13% / 19% / 20% (targets 50 / 80 / 90). Realised -105.0k of 2.8m predicted gp (-4%).

#### overnight / policy — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 97 | 39% | 33% |
| 40%-60% | 39 | 50% | 46% |
| 60%-80% | 37 | 67% | 57% |
| 80%-90% | 33 | 88% | 61% |
| 90%-100% | 5 | 94% | 60% |

Calibration error 10.1%. Finished within own P50/P80/P90: 25% / 43% / 44% (targets 50 / 80 / 90). Realised 868.4k of 2.8m predicted gp (31%).

#### overnight / policy — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 97 | 39% | 45% |
| 40%-60% | 39 | 50% | 54% |
| 60%-80% | 37 | 67% | 59% |
| 80%-90% | 33 | 88% | 73% |
| 90%-100% | 5 | 94% | 60% |

Calibration error 8.3%. Finished within own P50/P80/P90: 32% / 52% / 54% (targets 50 / 80 / 90). Realised 1.1m of 2.8m predicted gp (39%).

#### overnight / browser — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 97 | 39% | 33% |
| 40%-60% | 39 | 50% | 46% |
| 60%-80% | 37 | 67% | 57% |
| 80%-90% | 33 | 88% | 61% |
| 90%-100% | 5 | 94% | 60% |

Calibration error 10.1%. Finished within own P50/P80/P90: 25% / 43% / 44% (targets 50 / 80 / 90). Realised 868.4k of 2.8m predicted gp (31%).

#### overnight / browser — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 97 | 39% | 45% |
| 40%-60% | 39 | 50% | 54% |
| 60%-80% | 37 | 67% | 59% |
| 80%-90% | 33 | 88% | 73% |
| 90%-100% | 5 | 94% | 60% |

Calibration error 8.3%. Finished within own P50/P80/P90: 32% / 52% / 54% (targets 50 / 80 / 90). Realised 1.1m of 2.8m predicted gp (39%).

#### overnight / ev_per_offer — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 1 | 10% | 0% |
| 20%-40% | 39 | 39% | 3% |
| 40%-60% | 21 | 51% | 10% |
| 60%-80% | 32 | 69% | 12% |
| 80%-90% | 21 | 85% | 14% |
| 90%-100% | 102 | 97% | 27% |

Calibration error 58.9%. Finished within own P50/P80/P90: 1% / 5% / 8% (targets 50 / 80 / 90). Realised -4.5m of 56.0m predicted gp (-8%).

#### overnight / ev_per_offer — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 1 | 10% | 0% |
| 20%-40% | 39 | 39% | 41% |
| 40%-60% | 23 | 51% | 48% |
| 60%-80% | 34 | 70% | 35% |
| 80%-90% | 17 | 84% | 29% |
| 90%-100% | 102 | 97% | 43% |

Calibration error 35.9%. Finished within own P50/P80/P90: 13% / 20% / 27% (targets 50 / 80 / 90). Realised 1.4m of 56.1m predicted gp (3%).

#### overnight / ev_roi — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 54 | 5% | 0% |
| 20%-40% | 99 | 37% | 3% |
| 40%-60% | 46 | 46% | 15% |
| 60%-80% | 2 | 63% | 0% |
| 80%-90% | 7 | 86% | 14% |
| 90%-100% | 3 | 96% | 33% |

Calibration error 28.0%. Finished within own P50/P80/P90: 5% / 6% / 6% (targets 50 / 80 / 90). Realised -24.4k of 63.9m predicted gp (-0%).

#### overnight / ev_roi — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 54 | 5% | 15% |
| 20%-40% | 99 | 37% | 25% |
| 40%-60% | 46 | 46% | 26% |
| 60%-80% | 2 | 63% | 0% |
| 80%-90% | 7 | 86% | 29% |
| 90%-100% | 3 | 96% | 100% |

Calibration error 15.2%. Finished within own P50/P80/P90: 20% / 24% / 24% (targets 50 / 80 / 90). Realised 1.2k of 63.9m predicted gp (0%).

#### overnight / gp_slot_hour — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 1 | 7% | 0% |
| 20%-40% | 16 | 39% | 6% |
| 40%-60% | 6 | 53% | 0% |
| 60%-80% | 14 | 68% | 0% |
| 80%-90% | 25 | 86% | 4% |
| 90%-100% | 154 | 98% | 38% |

Calibration error 60.3%. Finished within own P50/P80/P90: 0% / 1% / 3% (targets 50 / 80 / 90). Realised -4.7m of 53.7m predicted gp (-9%).

#### overnight / gp_slot_hour — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 1 | 7% | 0% |
| 20%-40% | 16 | 39% | 25% |
| 40%-60% | 6 | 54% | 33% |
| 60%-80% | 17 | 70% | 41% |
| 80%-90% | 21 | 86% | 38% |
| 90%-100% | 155 | 98% | 57% |

Calibration error 37.6%. Finished within own P50/P80/P90: 4% / 11% / 17% (targets 50 / 80 / 90). Realised -1.7m of 53.7m predicted gp (-3%).

#### overnight / gp_capital_hour — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 50 | 5% | 0% |
| 20%-40% | 100 | 38% | 5% |
| 40%-60% | 48 | 46% | 15% |
| 60%-80% | 4 | 65% | 0% |
| 80%-90% | 7 | 87% | 14% |
| 90%-100% | 3 | 96% | 33% |

Calibration error 28.4%. Finished within own P50/P80/P90: 5% / 7% / 7% (targets 50 / 80 / 90). Realised -6.1k of 63.8m predicted gp (-0%).

#### overnight / gp_capital_hour — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 50 | 5% | 18% |
| 20%-40% | 100 | 38% | 26% |
| 40%-60% | 48 | 46% | 27% |
| 60%-80% | 4 | 65% | 0% |
| 80%-90% | 7 | 87% | 43% |
| 90%-100% | 3 | 96% | 100% |

Calibration error 15.8%. Finished within own P50/P80/P90: 21% / 25% / 25% (targets 50 / 80 / 90). Realised 45.1k of 63.8m predicted gp (0%).

#### profit / current — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 6 | 40% | 17% |
| 40%-60% | 11 | 51% | 18% |
| 60%-80% | 35 | 72% | 0% |
| 80%-90% | 19 | 85% | 26% |
| 90%-100% | 168 | 98% | 70% |

Calibration error 36.9%. Finished within own P50/P80/P90: 12% / 23% / 34% (targets 50 / 80 / 90). Realised -5.7m of 1223.2m predicted gp (-0%).

#### profit / current — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 6 | 40% | 0% |
| 40%-60% | 13 | 50% | 23% |
| 60%-80% | 66 | 70% | 89% |
| 80%-90% | 22 | 85% | 77% |
| 90%-100% | 183 | 98% | 73% |

Calibration error 22.4%. Finished within own P50/P80/P90: 38% / 51% / 59% (targets 50 / 80 / 90). Realised 14.0m of 1415.3m predicted gp (1%).

#### profit / browser_baseline — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 13 | 39% | 8% |
| 40%-60% | 19 | 52% | 32% |
| 60%-80% | 57 | 71% | 49% |
| 80%-90% | 38 | 85% | 39% |
| 90%-100% | 56 | 96% | 68% |

Calibration error 29.1%. Finished within own P50/P80/P90: 25% / 42% / 44% (targets 50 / 80 / 90). Realised 3.7m of 6.5m predicted gp (57%).

#### profit / browser_baseline — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 15 | 39% | 20% |
| 40%-60% | 25 | 51% | 32% |
| 60%-80% | 60 | 71% | 63% |
| 80%-90% | 38 | 85% | 45% |
| 90%-100% | 56 | 96% | 71% |

Calibration error 21.5%. Finished within own P50/P80/P90: 37% / 49% / 52% (targets 50 / 80 / 90). Realised 5.0m of 6.8m predicted gp (73%).

#### profit / policy — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 56 | 39% | 59% |
| 40%-60% | 71 | 51% | 58% |
| 60%-80% | 64 | 68% | 59% |
| 80%-90% | 15 | 84% | 67% |
| 90%-100% | 9 | 93% | 78% |

Calibration error 12.0%. Finished within own P50/P80/P90: 54% / 60% / 60% (targets 50 / 80 / 90). Realised 4.8m of 10.8m predicted gp (44%).

#### profit / policy — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 58 | 39% | 69% |
| 40%-60% | 74 | 51% | 61% |
| 60%-80% | 60 | 69% | 67% |
| 80%-90% | 19 | 85% | 79% |
| 90%-100% | 12 | 93% | 67% |

Calibration error 13.6%. Finished within own P50/P80/P90: 61% / 66% / 66% (targets 50 / 80 / 90). Realised 5.7m of 11.1m predicted gp (51%).

#### profit / browser — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 56 | 39% | 59% |
| 40%-60% | 71 | 51% | 58% |
| 60%-80% | 64 | 68% | 59% |
| 80%-90% | 15 | 84% | 67% |
| 90%-100% | 9 | 93% | 78% |

Calibration error 12.0%. Finished within own P50/P80/P90: 54% / 60% / 60% (targets 50 / 80 / 90). Realised 4.8m of 10.8m predicted gp (44%).

#### profit / browser — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 58 | 39% | 69% |
| 40%-60% | 74 | 51% | 61% |
| 60%-80% | 60 | 69% | 67% |
| 80%-90% | 19 | 85% | 79% |
| 90%-100% | 12 | 93% | 67% |

Calibration error 13.6%. Finished within own P50/P80/P90: 61% / 66% / 66% (targets 50 / 80 / 90). Realised 5.7m of 11.1m predicted gp (51%).

#### profit / ev_per_offer — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 5 | 40% | 0% |
| 40%-60% | 15 | 50% | 7% |
| 60%-80% | 27 | 72% | 11% |
| 80%-90% | 19 | 85% | 16% |
| 90%-100% | 152 | 98% | 52% |

Calibration error 49.4%. Finished within own P50/P80/P90: 6% / 18% / 22% (targets 50 / 80 / 90). Realised -2.1m of 579.6m predicted gp (-0%).

#### profit / ev_per_offer — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 5 | 40% | 0% |
| 40%-60% | 16 | 49% | 6% |
| 60%-80% | 38 | 71% | 61% |
| 80%-90% | 23 | 85% | 74% |
| 90%-100% | 195 | 98% | 71% |

Calibration error 24.5%. Finished within own P50/P80/P90: 29% / 43% / 48% (targets 50 / 80 / 90). Realised 7.5m of 1291.3m predicted gp (1%).

#### profit / ev_roi — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 32 | 7% | 9% |
| 20%-40% | 57 | 34% | 9% |
| 40%-60% | 125 | 47% | 6% |
| 60%-80% | 15 | 66% | 7% |
| 80%-90% | 1 | 85% | 0% |

Calibration error 32.9%. Finished within own P50/P80/P90: 7% / 7% / 7% (targets 50 / 80 / 90). Realised 625.3k of 1209.6m predicted gp (0%).

#### profit / ev_roi — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 48 | 6% | 25% |
| 20%-40% | 61 | 34% | 43% |
| 40%-60% | 106 | 47% | 35% |
| 60%-80% | 14 | 65% | 57% |
| 80%-90% | 2 | 86% | 50% |

Calibration error 12.3%. Finished within own P50/P80/P90: 36% / 36% / 36% (targets 50 / 80 / 90). Realised 581.1k of 1209.1m predicted gp (0%).

#### profit / gp_slot_hour — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 5 | 40% | 0% |
| 40%-60% | 6 | 50% | 0% |
| 60%-80% | 7 | 70% | 14% |
| 80%-90% | 6 | 86% | 0% |
| 90%-100% | 240 | 99% | 64% |

Calibration error 36.9%. Finished within own P50/P80/P90: 6% / 19% / 24% (targets 50 / 80 / 90). Realised -2.9m of 834.2m predicted gp (-0%).

#### profit / gp_slot_hour — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 5 | 40% | 0% |
| 40%-60% | 9 | 50% | 0% |
| 60%-80% | 11 | 71% | 55% |
| 80%-90% | 5 | 86% | 60% |
| 90%-100% | 297 | 99% | 78% |

Calibration error 21.1%. Finished within own P50/P80/P90: 27% / 38% / 43% (targets 50 / 80 / 90). Realised 978.9k of 957.3m predicted gp (0%).

#### profit / gp_capital_hour — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 28 | 7% | 7% |
| 20%-40% | 50 | 34% | 8% |
| 40%-60% | 125 | 48% | 6% |
| 60%-80% | 18 | 66% | 11% |
| 80%-90% | 7 | 85% | 14% |
| 90%-100% | 1 | 91% | 0% |

Calibration error 35.6%. Finished within own P50/P80/P90: 6% / 7% / 7% (targets 50 / 80 / 90). Realised 506.4k of 1210.2m predicted gp (0%).

#### profit / gp_capital_hour — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 39 | 6% | 26% |
| 20%-40% | 54 | 34% | 43% |
| 40%-60% | 113 | 48% | 33% |
| 60%-80% | 18 | 66% | 44% |
| 80%-90% | 6 | 86% | 100% |
| 90%-100% | 1 | 91% | 100% |

Calibration error 14.8%. Finished within own P50/P80/P90: 36% / 37% / 37% (targets 50 / 80 / 90). Realised 619.4k of 1209.2m predicted gp (0%).
