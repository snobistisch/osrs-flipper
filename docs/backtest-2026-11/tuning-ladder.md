
### active — all period, bank 20.0m, 12 segments, 925 decisions

Fill rule `strict_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | -62.0k [-96.0k .. -37.7k] | -17.2k | -7.7k | -3.8k | -1.34% | 43% | 23% | 67% | 32% | -5.62% | 42.31% | 100% | 91% | 79.3 | — | — |
| browser_baseline | -7.2k [-13.5k .. -2.1k] | 9.2k | -973 | -983 | -0.29% | 67% | 20% | 86% | 41% | -4.06% | 5.39% | 94% | 45% | 73.6 | 54.8k [32.6k .. 86.8k] | 0.000 |
| naive_roi | -487 [-1.1k .. -35] | 70.3k | -61 | -241 | -39.07% | 2% | 3% | 5% | 0% | 0.00% | 0.76% | 100% | 10% | 91.8 | 61.5k [37.2k .. 95.7k] | 0.000 |
| naive_margin | -15.1k [-25.7k .. -7.0k] | 75.4k | -1.9k | -989 | -4.27% | 2% | 6% | 8% | 0% | -0.65% | 12.35% | 100% | 78% | 90.1 | 46.9k [26.9k .. 71.8k] | 0.000 |
| random | -13.1k [-21.6k .. -6.3k] | -2.2k | -1.6k | -1.2k | -1.95% | 23% | 18% | 42% | 2% | -1.90% | 9.29% | 100% | 64% | 77.5 | 48.9k [26.2k .. 81.7k] | 0.000 |
| ev_per_offer | -56.7k [-91.6k .. -33.0k] | -10.4k | -7.1k | -3.4k | -1.33% | 38% | 24% | 62% | 24% | -5.55% | 44.72% | 99% | 92% | 77.0 | 5.3k [-7.7k .. 18.6k] | 0.217 |
| ev_roi | 166 [83 .. 259] | 535 | 21 | 13.6k | 34.72% | 14% | 9% | 25% | 9% | -22.22% | 0.02% | 99% | 0% | 84.9 | 62.1k [37.8k .. 96.2k] | 0.000 |
| gp_slot_hour | -61.8k [-85.2k .. -45.4k] | -12.0k | -7.7k | -3.7k | -1.35% | 40% | 24% | 64% | 30% | -5.63% | 34.92% | 100% | 93% | 79.7 | 213 [-13.2k .. 15.0k] | 0.524 |
| gp_capital_hour | 66 [-54 .. 162] | 450 | 8 | 7.0k | 11.48% | 16% | 9% | 27% | 10% | -21.18% | 0.10% | 99% | 0% | 85.5 | 62.0k [37.8k .. 96.0k] | 0.000 |
| gated | -40.6k [-66.4k .. -22.8k] | -5.0k | -5.1k | -2.9k | -0.94% | 56% | 27% | 84% | 33% | -5.23% | 28.97% | 100% | 83% | 74.7 | 21.4k [9.2k .. 35.2k] | 0.000 |
| reach | -17.6k [-52.8k .. 4.1k] | 2.1k | -2.2k | -2.3k | -0.64% | 64% | 20% | 84% | 41% | -5.74% | 28.53% | 100% | 46% | 81.2 | 44.4k [32.2k .. 58.2k] | 0.000 |
| replay_gate | -11.9k [-49.4k .. 9.4k] | 3.5k | -1.5k | -2.3k | -0.64% | 67% | 19% | 86% | 44% | -5.02% | 29.24% | 100% | 31% | 80.7 | 50.0k [38.2k .. 62.6k] | 0.000 |
| replay_gate_stable | 3.9k [-7.8k .. 11.9k] | 14.5k | 503 | 998 | 0.25% | 72% | 17% | 88% | 48% | -4.37% | 11.48% | 99% | 24% | 81.9 | 65.9k [46.9k .. 89.8k] | 0.000 |
| replay_portfolio | 9.0k [5.1k .. 12.1k] | 16.5k | 1.2k | 3.1k | 0.70% | 77% | 14% | 91% | 58% | -4.17% | 2.56% | 100% | 18% | 86.9 | 71.0k [47.2k .. 104.8k] | 0.000 |
| replay_portfolio_mean | -3.5k [-29.7k .. 12.4k] | 7.3k | -445 | -883 | -0.22% | 75% | 15% | 90% | 55% | -4.37% | 17.20% | 100% | 25% | 85.1 | 58.5k [47.5k .. 71.5k] | 0.000 |
| replay_portfolio_offer | 9.3k [4.6k .. 12.8k] | 16.8k | 1.2k | 3.2k | 0.74% | 77% | 14% | 91% | 57% | -4.26% | 3.54% | 100% | 18% | 86.1 | 71.3k [47.7k .. 105.5k] | 0.000 |

Fill rule `touch_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | -21.4k [-50.9k .. -1.1k] | 26.8k | -2.7k | -1.3k | -0.37% | 67% | 19% | 86% | 56% | -4.76% | 32.19% | 100% | 93% | 96.3 | — | — |
| browser_baseline | -2.8k [-8.4k .. 1.8k] | 12.9k | -386 | -403 | -0.10% | 77% | 16% | 94% | 52% | -3.48% | 4.48% | 94% | 45% | 78.6 | 18.5k [-2.3k .. 47.3k] | 0.053 |
| naive_roi | 741 [-262 .. 2.0k] | 73.4k | 91 | 291 | 50.18% | 9% | 4% | 16% | 0% | 0.00% | 0.73% | 100% | 15% | 86.9 | 22.1k [1.6k .. 52.3k] | 0.017 |
| naive_margin | -17.0k [-26.8k .. -7.8k] | 81.7k | -2.1k | -1.1k | -3.81% | 3% | 8% | 11% | 0% | -1.24% | 8.59% | 100% | 79% | 88.4 | 4.4k [-18.2k .. 29.6k] | 0.385 |
| random | -9.7k [-17.4k .. -3.4k] | 926 | -1.2k | -960 | -1.43% | 47% | 20% | 67% | 5% | -1.77% | 7.20% | 100% | 69% | 71.2 | 11.7k [-8.8k .. 40.4k] | 0.203 |
| ev_per_offer | -23.7k [-58.1k .. -368] | 24.3k | -3.1k | -1.4k | -0.47% | 62% | 19% | 81% | 49% | -4.72% | 39.54% | 99% | 92% | 91.9 | -2.4k [-13.2k .. 9.7k] | 0.664 |
| ev_roi | 2.2k [1.5k .. 3.2k] | 2.3k | 304 | 209.3k | 100.18% | 73% | 4% | 80% | 65% | 0.00% | 0.01% | 99% | 0% | 117.0 | 23.6k [3.5k .. 53.1k] | 0.008 |
| gp_slot_hour | -32.0k [-72.5k .. -5.1k] | 15.3k | -4.1k | -1.8k | -0.61% | 61% | 20% | 81% | 52% | -4.91% | 45.84% | 100% | 94% | 93.4 | -10.7k [-23.1k .. -116] | 0.977 |
| gp_capital_hour | 1.5k [978 .. 2.4k] | 1.6k | 210 | 201.8k | 94.95% | 73% | 4% | 80% | 67% | 0.00% | 0.00% | 99% | 0% | 118.4 | 22.9k [2.8k .. 52.4k] | 0.011 |
| gated | -38.6k [-66.3k .. -19.1k] | -3.6k | -4.8k | -2.8k | -0.83% | 62% | 26% | 87% | 37% | -5.24% | 31.37% | 100% | 83% | 76.3 | -17.2k [-27.7k .. -7.0k] | 1.000 |
| reach | -15.5k [-52.1k .. 6.8k] | 3.5k | -2.0k | -2.0k | -0.55% | 68% | 19% | 87% | 46% | -4.95% | 30.21% | 100% | 46% | 82.6 | 5.9k [-9.0k .. 19.9k] | 0.212 |
| replay_gate | -9.3k [-44.0k .. 11.4k] | 6.5k | -1.2k | -1.8k | -0.46% | 72% | 17% | 90% | 50% | -4.95% | 26.15% | 100% | 32% | 83.7 | 12.1k [-854 .. 24.4k] | 0.033 |
| replay_gate_stable | 10.9k [5.3k .. 15.9k] | 20.5k | 1.4k | 2.9k | 0.66% | 77% | 14% | 91% | 55% | -3.79% | 3.42% | 99% | 24% | 86.5 | 32.2k [13.2k .. 58.6k] | 0.000 |
| replay_portfolio | 12.8k [8.8k .. 16.2k] | 19.2k | 1.7k | 4.4k | 0.91% | 83% | 11% | 94% | 65% | -3.15% | 2.18% | 100% | 19% | 93.2 | 34.2k [13.7k .. 63.7k] | 0.000 |
| replay_portfolio_mean | 534 [-24.1k .. 15.7k] | 10.6k | 69 | 136 | 0.03% | 80% | 13% | 93% | 61% | -4.02% | 16.41% | 100% | 25% | 89.7 | 21.9k [11.9k .. 32.4k] | 0.000 |
| replay_portfolio_offer | 13.0k [9.3k .. 16.4k] | 19.7k | 1.7k | 4.6k | 0.95% | 82% | 11% | 94% | 64% | -3.38% | 2.11% | 100% | 18% | 91.2 | 34.3k [14.0k .. 64.1k] | 0.000 |

Bank gp/h under every fill assumption (rule_capture):

| method | strict_0.03 | strict_0.10 | strict_0.30 | touch_0.03 | touch_0.10 | touch_0.30 |
|---|---|---|---|---|---|---|
| current | -58.5k | -62.0k | -30.0k | -37.0k | -21.4k | 25.8k |
| browser_baseline | -12.6k | -7.2k | 3.7k | -9.7k | -2.8k | 12.3k |
| naive_roi | -168 | -487 | -874 | 509 | 741 | 3.5k |
| naive_margin | -5.1k | -15.1k | -21.6k | -7.2k | -17.0k | -14.1k |
| random | -5.4k | -13.1k | -12.2k | -4.0k | -9.7k | -5.4k |
| ev_per_offer | -62.6k | -56.7k | -42.5k | -43.2k | -23.7k | 14.7k |
| ev_roi | 46 | 166 | 341 | 1.6k | 2.2k | 2.6k |
| gp_slot_hour | -58.5k | -61.8k | -37.0k | -35.3k | -32.0k | 8.1k |
| gp_capital_hour | 54 | 66 | 159 | 1.1k | 1.5k | 1.9k |
| gated | -42.3k | -40.6k | -22.3k | -42.1k | -38.6k | -14.7k |
| reach | -29.3k | -17.6k | -1.5k | -29.8k | -15.5k | 4.6k |
| replay_gate | -25.3k | -11.9k | 1.9k | -20.9k | -9.3k | 8.3k |
| replay_gate_stable | -8.8k | 3.9k | 15.5k | -4.7k | 10.9k | 20.8k |
| replay_portfolio | -4.8k | 9.0k | 15.8k | -1.4k | 12.8k | 19.5k |
| replay_portfolio_mean | -16.7k | -3.5k | 9.9k | -13.3k | 534 | 14.3k |
| replay_portfolio_offer | -1.8k | 9.3k | 18.6k | 182 | 13.0k | 23.5k |

### overnight — all period, bank 20.0m, 13 segments, 38 decisions

Fill rule `strict_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | -22.2k [-41.8k .. -8.0k] | 195.8k | -3.4k | -1.6k | -2.39% | 38% | 24% | 65% | 28% | -6.46% | 19.90% | 100% | 89% | 16.0 | — | — |
| browser_baseline | -5.9k [-11.0k .. -1.5k] | 2.2k | -1.4k | -843 | -1.35% | 44% | 34% | 78% | 16% | -5.13% | 4.47% | 62% | 43% | 9.9 | 16.3k [3.3k .. 32.7k] | 0.004 |
| naive_roi | -1.2k [-3.4k .. -48] | 230.1k | -220 | -1.4k | -67.45% | 3% | 7% | 10% | 0% | -0.25% | 2.35% | 100% | 7% | 16.0 | 21.0k [7.2k .. 40.5k] | 0.000 |
| naive_margin | -10.2k [-15.5k .. -5.6k] | 234.7k | -1.7k | -945 | -5.64% | 4% | 15% | 19% | 1% | -6.79% | 5.52% | 100% | 76% | 16.0 | 12.0k [-3.1k .. 29.8k] | 0.065 |
| random | -7.9k [-13.5k .. -3.3k] | -1.2k | -1.2k | -1.3k | -3.50% | 27% | 30% | 59% | 4% | -10.44% | 5.46% | 100% | 41% | 16.0 | 14.3k [-555 .. 34.0k] | 0.033 |
| ev_per_offer | -32.1k [-58.9k .. -12.8k] | 187.8k | -5.0k | -2.1k | -3.32% | 31% | 27% | 60% | 22% | -11.22% | 19.73% | 100% | 96% | 15.9 | -10.0k [-19.1k .. -1.9k] | 0.996 |
| ev_roi | -1.1k [-3.1k .. -22] | 203.7k | -200 | -24.6k | -65.20% | 6% | 8% | 15% | 2% | -10.81% | 2.08% | 98% | 0% | 15.7 | 21.1k [7.2k .. 40.8k] | 0.000 |
| gp_slot_hour | -24.4k [-38.9k .. -11.7k] | 192.5k | -3.9k | -1.6k | -2.15% | 37% | 25% | 64% | 30% | -7.97% | 12.26% | 99% | 98% | 15.9 | -2.2k [-15.7k .. 12.4k] | 0.622 |
| gp_capital_hour | -941 [-2.8k .. -2] | 203.2k | -168 | -20.5k | -78.91% | 7% | 7% | 15% | 3% | -10.72% | 2.10% | 99% | 0% | 15.8 | 21.3k [7.4k .. 40.9k] | 0.000 |
| gated | -19.1k [-37.0k .. -7.5k] | -2.7k | -2.9k | -1.3k | -1.77% | 46% | 38% | 84% | 21% | -7.74% | 15.85% | 93% | 88% | 14.9 | 3.1k [-2.5k .. 9.4k] | 0.161 |
| reach | -12.2k [-26.0k .. -2.9k] | 2.2k | -1.8k | -931 | -1.53% | 49% | 30% | 80% | 14% | -9.19% | 10.85% | 97% | 82% | 15.5 | 10.0k [411 .. 19.0k] | 0.020 |
| replay_gate | -6.6k [-15.7k .. -544] | 5.9k | -1.0k | -586 | -0.99% | 52% | 28% | 81% | 14% | -7.46% | 5.79% | 94% | 72% | 15.1 | 15.5k [5.2k .. 27.6k] | 0.002 |
| replay_gate_stable | -4.7k [-11.9k .. 689] | 6.0k | -795 | -483 | -0.75% | 54% | 26% | 82% | 17% | -6.05% | 4.94% | 88% | 62% | 14.1 | 17.4k [6.4k .. 31.4k] | 0.000 |
| replay_portfolio | -2.1k [-7.4k .. 2.8k] | 6.8k | -321 | -266 | -0.41% | 59% | 22% | 82% | 24% | -7.06% | 3.40% | 99% | 51% | 15.8 | 20.1k [7.9k .. 35.7k] | 0.000 |
| replay_portfolio_mean | -5.2k [-18.3k .. 3.4k] | 5.5k | -775 | -542 | -0.86% | 56% | 23% | 81% | 18% | -7.79% | 8.14% | 100% | 61% | 15.9 | 17.0k [9.4k .. 25.3k] | 0.000 |
| replay_portfolio_offer | -2.1k [-7.4k .. 2.8k] | 6.8k | -321 | -266 | -0.41% | 59% | 22% | 82% | 24% | -7.06% | 3.40% | 99% | 51% | 15.8 | 20.1k [7.9k .. 35.7k] | 0.000 |

Fill rule `touch_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | 31 [-21.3k .. 15.6k] | 217.5k | 5 | 2 | 0.00% | 67% | 24% | 90% | 55% | -6.45% | 18.30% | 100% | 89% | 16.0 | — | — |
| browser_baseline | -5.2k [-10.4k .. -744] | 3.1k | -1.2k | -740 | -1.11% | 49% | 33% | 82% | 22% | -5.13% | 4.22% | 62% | 43% | 9.9 | -5.3k [-20.1k .. 13.3k] | 0.743 |
| naive_roi | -973 [-3.1k .. 213] | 231.6k | -160 | -1.1k | -49.66% | 21% | 10% | 37% | 0% | -0.42% | 2.35% | 100% | 7% | 16.0 | -1.0k [-16.2k .. 20.1k] | 0.582 |
| naive_margin | -11.1k [-16.8k .. -6.0k] | 237.5k | -1.9k | -1.0k | -5.21% | 5% | 18% | 24% | 1% | -7.62% | 6.46% | 100% | 76% | 16.0 | -11.1k [-27.9k .. 8.6k] | 0.884 |
| random | -7.7k [-13.5k .. -2.9k] | -539 | -1.1k | -1.2k | -3.06% | 47% | 34% | 83% | 7% | -10.38% | 5.42% | 100% | 41% | 16.0 | -7.7k [-23.5k .. 13.4k] | 0.803 |
| ev_per_offer | -18.8k [-46.8k .. 1.4k] | 201.0k | -2.9k | -1.2k | -1.60% | 56% | 27% | 83% | 47% | -8.52% | 18.52% | 100% | 96% | 15.9 | -18.8k [-29.3k .. -9.5k] | 1.000 |
| ev_roi | -1.0k [-3.0k .. 65] | 203.9k | -168 | -22.5k | -52.75% | 36% | 12% | 52% | 22% | -10.68% | 2.08% | 98% | 0% | 15.7 | -1.1k [-16.5k .. 20.3k] | 0.586 |
| gp_slot_hour | -17.4k [-33.0k .. -4.0k] | 199.3k | -2.7k | -1.1k | -1.39% | 59% | 25% | 84% | 49% | -7.70% | 12.00% | 99% | 98% | 15.9 | -17.4k [-32.4k .. -1.7k] | 0.984 |
| gp_capital_hour | -752 [-2.7k .. 255] | 203.6k | -122 | -16.1k | -45.97% | 38% | 12% | 53% | 24% | -10.56% | 2.10% | 99% | 0% | 15.8 | -783 [-16.2k .. 20.5k] | 0.577 |
| gated | -18.1k [-36.1k .. -6.3k] | -1.5k | -2.8k | -1.2k | -1.59% | 52% | 37% | 89% | 25% | -7.70% | 15.46% | 93% | 88% | 14.9 | -18.1k [-25.4k .. -10.4k] | 1.000 |
| reach | -11.1k [-25.3k .. -1.6k] | 3.5k | -1.7k | -844 | -1.33% | 51% | 31% | 82% | 16% | -8.89% | 10.85% | 97% | 82% | 15.5 | -11.1k [-21.6k .. -734] | 0.981 |
| replay_gate | -5.5k [-14.9k .. 762] | 7.4k | -859 | -482 | -0.77% | 54% | 28% | 83% | 16% | -6.63% | 5.78% | 94% | 72% | 15.1 | -5.5k [-17.3k .. 7.9k] | 0.803 |
| replay_gate_stable | -3.7k [-11.1k .. 2.1k] | 7.2k | -616 | -375 | -0.56% | 57% | 26% | 84% | 20% | -5.78% | 5.04% | 88% | 62% | 14.1 | -3.7k [-15.8k .. 11.6k] | 0.723 |
| replay_portfolio | -777 [-6.1k .. 4.2k] | 8.1k | -116 | -96 | -0.14% | 63% | 21% | 85% | 29% | -6.71% | 3.39% | 99% | 51% | 15.8 | -808 [-14.2k .. 16.6k] | 0.580 |
| replay_portfolio_mean | -3.9k [-17.4k .. 4.7k] | 6.8k | -583 | -407 | -0.62% | 60% | 22% | 83% | 22% | -6.67% | 8.18% | 100% | 61% | 15.9 | -4.0k [-13.1k .. 5.7k] | 0.791 |
| replay_portfolio_offer | -777 [-6.1k .. 4.2k] | 8.1k | -116 | -96 | -0.14% | 63% | 21% | 85% | 29% | -6.71% | 3.39% | 99% | 51% | 15.8 | -808 [-14.2k .. 16.6k] | 0.580 |

Bank gp/h under every fill assumption (rule_capture):

| method | strict_0.03 | strict_0.10 | strict_0.30 | touch_0.03 | touch_0.10 | touch_0.30 |
|---|---|---|---|---|---|---|
| current | -22.6k | -22.2k | -20.1k | -9.0k | 31 | 390 |
| browser_baseline | -5.1k | -5.9k | -3.1k | -5.1k | -5.2k | -2.0k |
| naive_roi | -377 | -1.2k | -3.4k | -296 | -973 | -2.6k |
| naive_margin | -4.4k | -10.2k | -18.1k | -4.7k | -11.1k | -17.9k |
| random | -3.6k | -7.9k | -9.5k | -3.4k | -7.7k | -8.3k |
| ev_per_offer | -33.0k | -32.1k | -30.3k | -23.8k | -18.8k | -16.9k |
| ev_roi | -443 | -1.1k | -1.2k | -407 | -1.0k | -1.0k |
| gp_slot_hour | -21.7k | -24.4k | -23.5k | -16.3k | -17.4k | -15.9k |
| gp_capital_hour | -323 | -941 | -918 | -222 | -752 | -589 |
| gated | -20.3k | -19.1k | -14.0k | -20.0k | -18.1k | -11.6k |
| reach | -13.8k | -12.2k | -6.3k | -13.6k | -11.1k | -5.0k |
| replay_gate | -8.7k | -6.6k | -993 | -8.6k | -5.5k | 655 |
| replay_gate_stable | -6.4k | -4.7k | -116 | -6.2k | -3.7k | 1.2k |
| replay_portfolio | -3.5k | -2.1k | 1.7k | -3.1k | -777 | 3.2k |
| replay_portfolio_mean | -6.6k | -5.2k | -121 | -6.4k | -3.9k | 1.2k |
| replay_portfolio_offer | -3.5k | -2.1k | 1.7k | -3.1k | -777 | 3.2k |

### profit — all period, bank 20.0m, 11 segments, 110 decisions

Fill rule `strict_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | -5.7k [-9.5k .. -1.7k] | 244.5k | -656 | -284 | -0.53% | 55% | 19% | 75% | 46% | -5.58% | 5.00% | 100% | 100% | 17.4 | — | — |
| browser_baseline | 4.0k [-4.1k .. 9.9k] | 9.7k | 500 | 276 | 0.37% | 77% | 17% | 95% | 49% | -6.43% | 8.11% | 91% | 88% | 13.5 | 9.7k [-646 .. 17.6k] | 0.029 |
| naive_roi | -1.2k [-3.7k .. 442] | 248.0k | -120 | -509 | -52.52% | 5% | 6% | 12% | 0% | -0.06% | 2.40% | 100% | 11% | 17.7 | 4.5k [-44 .. 9.1k] | 0.026 |
| naive_margin | -4.6k [-8.7k .. -323] | 11.1k | -469 | -257 | -2.08% | 8% | 15% | 23% | 4% | -7.42% | 7.81% | 100% | 77% | 16.8 | 1.0k [-4.2k .. 6.3k] | 0.354 |
| random | -5.4k [-10.3k .. -1.8k] | 165 | -561 | -493 | -2.04% | 42% | 25% | 68% | 12% | -10.69% | 4.32% | 100% | 55% | 14.1 | 235 [-6.2k .. 5.4k] | 0.462 |
| ev_per_offer | -30.5k [-59.4k .. -11.2k] | 222.6k | -3.5k | -1.4k | -2.77% | 51% | 18% | 70% | 44% | -7.24% | 29.27% | 100% | 98% | 18.0 | -24.8k [-55.1k .. -4.9k] | 0.999 |
| ev_roi | -931 [-3.2k .. 280] | 240.1k | -100 | -6.2k | -64.44% | 13% | 11% | 25% | 9% | -21.69% | 2.36% | 100% | 1% | 16.9 | 4.7k [432 .. 9.0k] | 0.012 |
| gp_slot_hour | -27.8k [-41.1k .. -16.3k] | 223.5k | -3.2k | -1.3k | -1.81% | 54% | 19% | 74% | 51% | -9.34% | 12.34% | 100% | 99% | 19.4 | -22.1k [-36.6k .. -10.0k] | 1.000 |
| gp_capital_hour | -1.0k [-3.3k .. 222] | 240.0k | -111 | -6.5k | -61.23% | 15% | 10% | 26% | 10% | -19.22% | 2.36% | 100% | 1% | 17.0 | 4.6k [315 .. 8.9k] | 0.017 |
| gated | -1.0k [-10.9k .. 7.0k] | 7.8k | -121 | -61 | -0.08% | 76% | 18% | 95% | 58% | -7.97% | 10.07% | 98% | 99% | 16.3 | 4.6k [-6.3k .. 13.7k] | 0.185 |
| reach | -1.8k [-13.9k .. 9.9k] | 8.9k | -204 | -107 | -0.17% | 69% | 23% | 92% | 38% | -11.37% | 9.48% | 100% | 98% | 14.5 | 3.8k [-10.3k .. 17.6k] | 0.303 |
| replay_gate | 930 [-11.9k .. 12.8k] | 11.4k | 104 | 53 | 0.08% | 73% | 21% | 94% | 42% | -11.22% | 7.98% | 99% | 99% | 14.6 | 6.6k [-8.1k .. 20.8k] | 0.172 |
| replay_gate_stable | 4.3k [-6.3k .. 14.9k] | 14.5k | 484 | 256 | 0.39% | 76% | 19% | 96% | 42% | -7.79% | 6.55% | 99% | 99% | 14.8 | 10.0k [-2.8k .. 22.9k] | 0.058 |
| replay_portfolio | 8.0k [-1.5k .. 16.7k] | 17.7k | 892 | 550 | 0.82% | 76% | 17% | 93% | 38% | -11.90% | 6.08% | 100% | 89% | 14.2 | 13.6k [2.3k .. 24.0k] | 0.010 |
| replay_portfolio_mean | 8.4k [-2.8k .. 19.0k] | 17.8k | 949 | 581 | 0.85% | 77% | 16% | 93% | 37% | -10.79% | 6.08% | 100% | 89% | 14.1 | 14.1k [1.2k .. 25.8k] | 0.017 |
| replay_portfolio_offer | 8.0k [-1.5k .. 16.7k] | 17.7k | 892 | 550 | 0.82% | 76% | 17% | 93% | 38% | -11.90% | 6.08% | 100% | 89% | 14.2 | 13.6k [2.3k .. 24.0k] | 0.010 |

Fill rule `touch_0.10`:

| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h | roi | win | loss | fill | done | p5 flip | max DD | slots | deployed | offers/day | vs current [95% CI] | p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | 50.1k [42.6k .. 58.2k] | 298.7k | 6.5k | 3.0k | 2.44% | 79% | 13% | 92% | 72% | -5.20% | 2.96% | 100% | 100% | 21.8 | — | — |
| browser_baseline | 8.8k [3.3k .. 13.7k] | 13.7k | 1.1k | 656 | 0.74% | 83% | 14% | 97% | 57% | -5.49% | 4.67% | 91% | 88% | 14.5 | -41.4k [-51.5k .. -32.3k] | 1.000 |
| naive_roi | -201 [-2.7k .. 1.7k] | 323.0k | -21 | -67 | -8.48% | 28% | 11% | 41% | 0% | -0.57% | 2.36% | 100% | 15% | 15.7 | -50.3k [-58.7k .. -42.6k] | 1.000 |
| naive_margin | -4.8k [-14.0k .. 3.6k] | 89.7k | -483 | -265 | -1.79% | 12% | 19% | 31% | 4% | -8.72% | 7.80% | 100% | 79% | 15.9 | -54.9k [-65.3k .. -44.5k] | 1.000 |
| random | -1.9k [-4.6k .. 634] | 2.8k | -208 | -185 | -0.72% | 67% | 20% | 87% | 16% | -6.30% | 1.98% | 100% | 58% | 13.4 | -52.1k [-60.8k .. -44.0k] | 1.000 |
| ev_per_offer | 5.3k [-28.9k .. 29.1k] | 256.2k | 686 | 266 | 0.34% | 72% | 14% | 86% | 65% | -6.92% | 28.56% | 100% | 98% | 22.0 | -44.8k [-81.4k .. -17.5k] | 1.000 |
| ev_roi | -769 [-3.1k .. 471] | 240.3k | -91 | -5.0k | -44.01% | 53% | 11% | 66% | 42% | -6.19% | 2.36% | 100% | 1% | 16.9 | -50.9k [-59.4k .. -43.0k] | 1.000 |
| gp_slot_hour | -12.4k [-29.9k .. 3.8k] | 123.7k | -1.8k | -603 | -0.67% | 77% | 13% | 89% | 73% | -8.48% | 14.01% | 100% | 100% | 23.9 | -62.6k [-79.3k .. -45.8k] | 1.000 |
| gp_capital_hour | -684 [-2.9k .. 517] | 240.5k | -81 | -4.6k | -39.42% | 54% | 9% | 65% | 43% | -5.32% | 2.35% | 99% | 1% | 17.8 | -50.8k [-59.2k .. -43.0k] | 1.000 |
| gated | 4.1k [-5.0k .. 12.1k] | 12.1k | 501 | 260 | 0.29% | 81% | 14% | 95% | 62% | -6.94% | 8.00% | 98% | 99% | 17.1 | -46.0k [-59.7k .. -32.8k] | 1.000 |
| reach | -302 [-12.8k .. 11.6k] | 10.1k | -34 | -18 | -0.03% | 71% | 22% | 93% | 43% | -11.24% | 9.49% | 100% | 98% | 14.5 | -50.4k [-65.5k .. -35.9k] | 1.000 |
| replay_gate | 3.4k [-8.8k .. 14.7k] | 12.9k | 389 | 203 | 0.30% | 77% | 18% | 96% | 46% | -9.98% | 7.66% | 99% | 99% | 14.8 | -46.7k [-61.4k .. -33.3k] | 1.000 |
| replay_gate_stable | 6.3k [-4.5k .. 16.6k] | 15.9k | 724 | 388 | 0.55% | 79% | 17% | 96% | 47% | -7.61% | 6.54% | 99% | 98% | 14.8 | -43.8k [-56.2k .. -31.8k] | 1.000 |
| replay_portfolio | 9.3k [596 .. 17.9k] | 19.7k | 1.1k | 656 | 0.90% | 78% | 17% | 95% | 42% | -10.30% | 5.63% | 100% | 90% | 14.3 | -40.9k [-53.6k .. -28.6k] | 1.000 |
| replay_portfolio_mean | 9.9k [-1.7k .. 20.5k] | 19.4k | 1.1k | 693 | 0.94% | 80% | 15% | 95% | 41% | -10.22% | 5.63% | 100% | 89% | 14.3 | -40.2k [-53.1k .. -28.2k] | 1.000 |
| replay_portfolio_offer | 9.3k [596 .. 17.9k] | 19.7k | 1.1k | 656 | 0.90% | 78% | 17% | 95% | 42% | -10.30% | 5.63% | 100% | 90% | 14.3 | -40.9k [-53.6k .. -28.6k] | 1.000 |

Bank gp/h under every fill assumption (rule_capture):

| method | strict_0.03 | strict_0.10 | strict_0.30 | touch_0.03 | touch_0.10 | touch_0.30 |
|---|---|---|---|---|---|---|
| current | -12.3k | -5.7k | 28 | 15.3k | 50.1k | 73.8k |
| browser_baseline | -4.9k | 4.0k | 15.9k | -2.9k | 8.8k | 24.8k |
| naive_roi | -445 | -1.2k | -3.5k | -310 | -201 | -850 |
| naive_margin | -6.0k | -4.6k | -9.9k | -5.7k | -4.8k | 1.4k |
| random | -3.0k | -5.4k | -5.7k | -2.5k | -1.9k | 1.7k |
| ev_per_offer | -30.7k | -30.5k | 513 | -9.3k | 5.3k | 36.1k |
| ev_roi | -270 | -931 | -995 | -217 | -769 | -744 |
| gp_slot_hour | -35.9k | -27.8k | -20.0k | -24.4k | -12.4k | -3.2k |
| gp_capital_hour | -379 | -1.0k | -1.0k | -60 | -684 | -741 |
| gated | -15.8k | -1.0k | 11.4k | -13.4k | 4.1k | 20.4k |
| reach | -15.9k | -1.8k | 16.0k | -14.0k | -302 | 16.3k |
| replay_gate | -10.3k | 930 | 16.9k | -8.1k | 3.4k | 21.0k |
| replay_gate_stable | -6.2k | 4.3k | 21.6k | -4.9k | 6.3k | 26.5k |
| replay_portfolio | -9.4k | 8.0k | 22.4k | -7.5k | 9.3k | 26.7k |
| replay_portfolio_mean | -9.5k | 8.4k | 21.4k | -7.6k | 9.9k | 31.3k |
| replay_portfolio_offer | -9.4k | 8.0k | 22.4k | -7.5k | 9.3k | 26.7k |

#### active / current — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 983 | 82% | 22% |
| 90%-100% | 545 | 97% | 49% |

Calibration error 55.8%. Finished within own P50/P80/P90: 9% / 21% / 25% (targets 50 / 80 / 90). Realised -28.7m of 278.8m predicted gp (-10%).

#### active / current — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1282 | 82% | 56% |
| 90%-100% | 573 | 97% | 55% |

Calibration error 30.9%. Finished within own P50/P80/P90: 36% / 46% / 49% (targets 50 / 80 / 90). Realised -9.9m of 292.6m predicted gp (-3%).

#### active / browser_baseline — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1409 | 81% | 41% |
| 90%-100% | 9 | 96% | 56% |

Calibration error 39.2%. Finished within own P50/P80/P90: 23% / 41% / 41% (targets 50 / 80 / 90). Realised -3.3m of 14.1m predicted gp (-24%).

#### active / browser_baseline — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1507 | 81% | 52% |
| 90%-100% | 7 | 96% | 43% |

Calibration error 28.9%. Finished within own P50/P80/P90: 33% / 51% / 52% (targets 50 / 80 / 90). Realised -1.3m of 14.9m predicted gp (-9%).

#### active / ev_per_offer — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 985 | 82% | 16% |
| 90%-100% | 499 | 97% | 41% |

Calibration error 62.9%. Finished within own P50/P80/P90: 5% / 14% / 18% (targets 50 / 80 / 90). Realised -26.2m of 213.6m predicted gp (-12%).

#### active / ev_per_offer — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1191 | 82% | 46% |
| 90%-100% | 580 | 97% | 56% |

Calibration error 37.7%. Finished within own P50/P80/P90: 30% / 38% / 42% (targets 50 / 80 / 90). Realised -11.0m of 222.1m predicted gp (-5%).

#### active / ev_roi — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1491 | 82% | 8% |
| 90%-100% | 146 | 92% | 18% |

Calibration error 74.5%. Finished within own P50/P80/P90: 5% / 8% / 9% (targets 50 / 80 / 90). Realised 76.9k of 210.1m predicted gp (0%).

#### active / ev_roi — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 2083 | 82% | 65% |
| 90%-100% | 172 | 92% | 60% |

Calibration error 17.6%. Finished within own P50/P80/P90: 52% / 63% / 65% (targets 50 / 80 / 90). Realised 1.0m of 217.9m predicted gp (0%).

#### active / gp_slot_hour — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 977 | 83% | 20% |
| 90%-100% | 559 | 97% | 47% |

Calibration error 57.7%. Finished within own P50/P80/P90: 7% / 18% / 21% (targets 50 / 80 / 90). Realised -28.6m of 170.4m predicted gp (-17%).

#### active / gp_slot_hour — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1144 | 82% | 50% |
| 90%-100% | 655 | 97% | 56% |

Calibration error 35.7%. Finished within own P50/P80/P90: 29% / 40% / 43% (targets 50 / 80 / 90). Realised -14.8m of 255.9m predicted gp (-6%).

#### active / gp_capital_hour — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1433 | 83% | 9% |
| 90%-100% | 214 | 92% | 21% |

Calibration error 73.6%. Finished within own P50/P80/P90: 5% / 9% / 10% (targets 50 / 80 / 90). Realised 30.5k of 211.2m predicted gp (0%).

#### active / gp_capital_hour — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 2031 | 82% | 67% |
| 90%-100% | 250 | 92% | 64% |

Calibration error 16.4%. Finished within own P50/P80/P90: 53% / 64% / 67% (targets 50 / 80 / 90). Realised 710.5k of 217.1m predicted gp (0%).

#### active / gated — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1196 | 81% | 30% |
| 90%-100% | 243 | 96% | 47% |

Calibration error 50.9%. Finished within own P50/P80/P90: 14% / 28% / 30% (targets 50 / 80 / 90). Realised -18.8m of 25.9m predicted gp (-73%).

#### active / gated — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1237 | 81% | 35% |
| 90%-100% | 234 | 96% | 48% |

Calibration error 46.6%. Finished within own P50/P80/P90: 18% / 32% / 35% (targets 50 / 80 / 90). Realised -17.8m of 26.7m predicted gp (-67%).

#### active / reach — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1526 | 81% | 41% |
| 90%-100% | 39 | 94% | 36% |

Calibration error 39.7%. Finished within own P50/P80/P90: 25% / 41% / 41% (targets 50 / 80 / 90). Realised -8.1m of 21.3m predicted gp (-38%).

#### active / reach — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1548 | 81% | 46% |
| 90%-100% | 44 | 95% | 39% |

Calibration error 35.1%. Finished within own P50/P80/P90: 28% / 45% / 46% (targets 50 / 80 / 90). Realised -7.2m of 21.7m predicted gp (-33%).

#### active / replay_gate — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1536 | 81% | 44% |
| 90%-100% | 20 | 94% | 20% |

Calibration error 36.6%. Finished within own P50/P80/P90: 26% / 43% / 44% (targets 50 / 80 / 90). Realised -5.5m of 16.3m predicted gp (-34%).

#### active / replay_gate — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1595 | 81% | 50% |
| 90%-100% | 18 | 94% | 28% |

Calibration error 30.7%. Finished within own P50/P80/P90: 33% / 49% / 50% (targets 50 / 80 / 90). Realised -4.3m of 16.9m predicted gp (-25%).

#### active / replay_gate_stable — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1568 | 81% | 49% |
| 90%-100% | 10 | 93% | 30% |

Calibration error 32.1%. Finished within own P50/P80/P90: 29% / 48% / 48% (targets 50 / 80 / 90). Realised 1.8m of 13.7m predicted gp (13%).

#### active / replay_gate_stable — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1657 | 81% | 55% |
| 90%-100% | 9 | 92% | 33% |

Calibration error 25.4%. Finished within own P50/P80/P90: 36% / 55% / 55% (targets 50 / 80 / 90). Realised 5.0m of 14.3m predicted gp (35%).

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

#### active / replay_portfolio_mean — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1618 | 81% | 55% |
| 90%-100% | 22 | 93% | 41% |

Calibration error 26.2%. Finished within own P50/P80/P90: 33% / 54% / 55% (targets 50 / 80 / 90). Realised -1.6m of 10.2m predicted gp (-16%).

#### active / replay_portfolio_mean — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1708 | 81% | 61% |
| 90%-100% | 21 | 94% | 48% |

Calibration error 19.5%. Finished within own P50/P80/P90: 40% / 60% / 61% (targets 50 / 80 / 90). Realised 246.9k of 10.6m predicted gp (2%).

#### active / replay_portfolio_offer — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1641 | 81% | 57% |
| 90%-100% | 19 | 95% | 63% |

Calibration error 24.2%. Finished within own P50/P80/P90: 34% / 56% / 57% (targets 50 / 80 / 90). Realised 4.3m of 8.1m predicted gp (53%).

#### active / replay_portfolio_offer — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 80%-90% | 1736 | 81% | 63% |
| 90%-100% | 22 | 94% | 68% |

Calibration error 17.3%. Finished within own P50/P80/P90: 41% / 63% / 64% (targets 50 / 80 / 90). Realised 6.0m of 8.5m predicted gp (71%).

#### overnight / current — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 48 | 39% | 2% |
| 40%-60% | 36 | 50% | 6% |
| 60%-80% | 41 | 71% | 12% |
| 80%-90% | 27 | 86% | 33% |
| 90%-100% | 152 | 97% | 45% |

Calibration error 49.7%. Finished within own P50/P80/P90: 1% / 6% / 9% (targets 50 / 80 / 90). Realised -10.1m of 49.1m predicted gp (-21%).

#### overnight / current — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 48 | 39% | 73% |
| 40%-60% | 39 | 50% | 49% |
| 60%-80% | 39 | 71% | 33% |
| 80%-90% | 28 | 85% | 54% |
| 90%-100% | 150 | 97% | 56% |

Calibration error 33.6%. Finished within own P50/P80/P90: 19% / 27% / 33% (targets 50 / 80 / 90). Realised 14.3k of 49.2m predicted gp (0%).

#### overnight / browser_baseline — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 106 | 39% | 14% |
| 40%-60% | 47 | 49% | 11% |
| 60%-80% | 16 | 69% | 19% |
| 80%-90% | 9 | 88% | 56% |
| 90%-100% | 10 | 94% | 30% |

Calibration error 32.5%. Finished within own P50/P80/P90: 11% / 15% / 16% (targets 50 / 80 / 90). Realised -2.7m of 3.0m predicted gp (-89%).

#### overnight / browser_baseline — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 106 | 39% | 20% |
| 40%-60% | 47 | 49% | 17% |
| 60%-80% | 16 | 69% | 25% |
| 80%-90% | 9 | 88% | 56% |
| 90%-100% | 10 | 94% | 30% |

Calibration error 27.2%. Finished within own P50/P80/P90: 16% / 21% / 22% (targets 50 / 80 / 90). Realised -2.4m of 3.0m predicted gp (-79%).

#### overnight / ev_per_offer — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 2 | 10% | 0% |
| 20%-40% | 41 | 39% | 0% |
| 40%-60% | 20 | 52% | 0% |
| 60%-80% | 38 | 69% | 11% |
| 80%-90% | 31 | 85% | 6% |
| 90%-100% | 171 | 97% | 36% |

Calibration error 58.7%. Finished within own P50/P80/P90: 0% / 2% / 3% (targets 50 / 80 / 90). Realised -14.7m of 48.7m predicted gp (-30%).

#### overnight / ev_per_offer — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 2 | 10% | 0% |
| 20%-40% | 42 | 39% | 21% |
| 40%-60% | 22 | 53% | 50% |
| 60%-80% | 37 | 70% | 35% |
| 80%-90% | 31 | 86% | 39% |
| 90%-100% | 169 | 98% | 57% |

Calibration error 34.3%. Finished within own P50/P80/P90: 8% / 16% / 19% (targets 50 / 80 / 90). Realised -8.6m of 48.7m predicted gp (-18%).

#### overnight / ev_roi — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 85 | 6% | 0% |
| 20%-40% | 141 | 38% | 3% |
| 40%-60% | 47 | 48% | 2% |
| 60%-80% | 15 | 66% | 7% |
| 80%-90% | 7 | 84% | 0% |
| 90%-100% | 4 | 94% | 0% |

Calibration error 31.8%. Finished within own P50/P80/P90: 2% / 2% / 2% (targets 50 / 80 / 90). Realised -507.9k of 39.1m predicted gp (-1%).

#### overnight / ev_roi — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 85 | 6% | 15% |
| 20%-40% | 141 | 38% | 18% |
| 40%-60% | 47 | 48% | 47% |
| 60%-80% | 15 | 66% | 40% |
| 80%-90% | 7 | 84% | 0% |
| 90%-100% | 4 | 94% | 0% |

Calibration error 16.9%. Finished within own P50/P80/P90: 20% / 22% / 22% (targets 50 / 80 / 90). Realised -472.1k of 39.1m predicted gp (-1%).

#### overnight / gp_slot_hour — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 22 | 39% | 0% |
| 40%-60% | 10 | 51% | 0% |
| 60%-80% | 30 | 69% | 17% |
| 80%-90% | 14 | 85% | 7% |
| 90%-100% | 226 | 98% | 37% |

Calibration error 59.1%. Finished within own P50/P80/P90: 0% / 2% / 5% (targets 50 / 80 / 90). Realised -11.1m of 46.3m predicted gp (-24%).

#### overnight / gp_slot_hour — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 23 | 39% | 17% |
| 40%-60% | 11 | 50% | 27% |
| 60%-80% | 27 | 70% | 37% |
| 80%-90% | 13 | 85% | 15% |
| 90%-100% | 228 | 98% | 57% |

Calibration error 39.9%. Finished within own P50/P80/P90: 3% / 6% / 10% (targets 50 / 80 / 90). Realised -7.9m of 46.0m predicted gp (-17%).

#### overnight / gp_capital_hour — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 75 | 6% | 0% |
| 20%-40% | 145 | 38% | 3% |
| 40%-60% | 48 | 49% | 2% |
| 60%-80% | 15 | 66% | 7% |
| 80%-90% | 10 | 85% | 0% |
| 90%-100% | 7 | 95% | 14% |

Calibration error 33.6%. Finished within own P50/P80/P90: 2% / 3% / 3% (targets 50 / 80 / 90). Realised -429.2k of 39.3m predicted gp (-1%).

#### overnight / gp_capital_hour — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 75 | 6% | 17% |
| 20%-40% | 145 | 38% | 19% |
| 40%-60% | 48 | 49% | 48% |
| 60%-80% | 15 | 66% | 33% |
| 80%-90% | 10 | 85% | 10% |
| 90%-100% | 7 | 95% | 14% |

Calibration error 18.3%. Finished within own P50/P80/P90: 21% / 24% / 24% (targets 50 / 80 / 90). Realised -342.9k of 39.3m predicted gp (-1%).

#### overnight / gated — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 81 | 39% | 14% |
| 40%-60% | 52 | 50% | 4% |
| 60%-80% | 52 | 69% | 25% |
| 80%-90% | 34 | 86% | 35% |
| 90%-100% | 64 | 96% | 33% |

Calibration error 44.1%. Finished within own P50/P80/P90: 7% / 14% / 16% (targets 50 / 80 / 90). Realised -8.7m of 6.5m predicted gp (-135%).

#### overnight / gated — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 81 | 39% | 19% |
| 40%-60% | 52 | 50% | 8% |
| 60%-80% | 52 | 68% | 29% |
| 80%-90% | 34 | 86% | 41% |
| 90%-100% | 64 | 96% | 34% |

Calibration error 40.2%. Finished within own P50/P80/P90: 10% / 18% / 20% (targets 50 / 80 / 90). Realised -8.3m of 6.5m predicted gp (-127%).

#### overnight / reach — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 177 | 39% | 11% |
| 40%-60% | 52 | 49% | 4% |
| 60%-80% | 28 | 68% | 21% |
| 80%-90% | 22 | 85% | 32% |
| 90%-100% | 16 | 95% | 38% |

Calibration error 36.2%. Finished within own P50/P80/P90: 7% / 11% / 13% (targets 50 / 80 / 90). Realised -5.5m of 8.5m predicted gp (-65%).

#### overnight / reach — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 177 | 39% | 14% |
| 40%-60% | 52 | 49% | 4% |
| 60%-80% | 29 | 69% | 21% |
| 80%-90% | 21 | 85% | 38% |
| 90%-100% | 16 | 95% | 38% |

Calibration error 34.1%. Finished within own P50/P80/P90: 8% / 13% / 15% (targets 50 / 80 / 90). Realised -5.1m of 8.5m predicted gp (-59%).

#### overnight / replay_gate — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 198 | 39% | 12% |
| 40%-60% | 43 | 48% | 7% |
| 60%-80% | 27 | 68% | 26% |
| 80%-90% | 11 | 86% | 27% |
| 90%-100% | 7 | 95% | 57% |

Calibration error 31.6%. Finished within own P50/P80/P90: 9% / 13% / 14% (targets 50 / 80 / 90). Realised -3.0m of 7.7m predicted gp (-39%).

#### overnight / replay_gate — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 198 | 39% | 15% |
| 40%-60% | 43 | 48% | 7% |
| 60%-80% | 27 | 68% | 26% |
| 80%-90% | 11 | 86% | 36% |
| 90%-100% | 7 | 95% | 57% |

Calibration error 29.5%. Finished within own P50/P80/P90: 11% / 15% / 16% (targets 50 / 80 / 90). Realised -2.5m of 7.7m predicted gp (-33%).

#### overnight / replay_gate_stable — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 190 | 39% | 15% |
| 40%-60% | 40 | 48% | 5% |
| 60%-80% | 23 | 68% | 26% |
| 80%-90% | 9 | 87% | 56% |
| 90%-100% | 6 | 94% | 67% |

Calibration error 28.2%. Finished within own P50/P80/P90: 12% / 15% / 17% (targets 50 / 80 / 90). Realised -2.2m of 6.5m predicted gp (-33%).

#### overnight / replay_gate_stable — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 190 | 39% | 19% |
| 40%-60% | 40 | 48% | 5% |
| 60%-80% | 23 | 68% | 26% |
| 80%-90% | 9 | 87% | 67% |
| 90%-100% | 6 | 94% | 67% |

Calibration error 25.2%. Finished within own P50/P80/P90: 15% / 18% / 20% (targets 50 / 80 / 90). Realised -1.7m of 6.5m predicted gp (-26%).

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

#### overnight / replay_portfolio_mean — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 176 | 39% | 16% |
| 40%-60% | 56 | 49% | 5% |
| 60%-80% | 41 | 68% | 24% |
| 80%-90% | 21 | 87% | 38% |
| 90%-100% | 9 | 94% | 56% |

Calibration error 31.2%. Finished within own P50/P80/P90: 11% / 16% / 18% (targets 50 / 80 / 90). Realised -2.4m of 8.8m predicted gp (-27%).

#### overnight / replay_portfolio_mean — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 176 | 39% | 19% |
| 40%-60% | 56 | 49% | 11% |
| 60%-80% | 41 | 68% | 32% |
| 80%-90% | 21 | 87% | 48% |
| 90%-100% | 9 | 94% | 56% |

Calibration error 27.3%. Finished within own P50/P80/P90: 13% / 20% / 22% (targets 50 / 80 / 90). Realised -1.8m of 8.8m predicted gp (-20%).

#### overnight / replay_portfolio_offer — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 134 | 39% | 17% |
| 40%-60% | 58 | 49% | 14% |
| 60%-80% | 59 | 68% | 29% |
| 80%-90% | 36 | 87% | 44% |
| 90%-100% | 13 | 93% | 69% |

Calibration error 30.2%. Finished within own P50/P80/P90: 11% / 21% / 24% (targets 50 / 80 / 90). Realised -973.3k of 6.4m predicted gp (-15%).

#### overnight / replay_portfolio_offer — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 134 | 39% | 22% |
| 40%-60% | 58 | 49% | 19% |
| 60%-80% | 59 | 68% | 34% |
| 80%-90% | 36 | 87% | 47% |
| 90%-100% | 13 | 93% | 77% |

Calibration error 25.6%. Finished within own P50/P80/P90: 13% / 26% / 29% (targets 50 / 80 / 90). Realised -354.2k of 6.4m predicted gp (-6%).

#### profit / current — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 10 | 40% | 0% |
| 40%-60% | 9 | 52% | 11% |
| 60%-80% | 62 | 73% | 5% |
| 80%-90% | 45 | 86% | 31% |
| 90%-100% | 193 | 98% | 67% |

Calibration error 42.2%. Finished within own P50/P80/P90: 10% / 24% / 33% (targets 50 / 80 / 90). Realised -2.5m of 1555.1m predicted gp (-0%).

#### profit / current — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 9 | 40% | 11% |
| 40%-60% | 12 | 51% | 25% |
| 60%-80% | 107 | 73% | 79% |
| 80%-90% | 48 | 85% | 77% |
| 90%-100% | 224 | 98% | 71% |

Calibration error 18.9%. Finished within own P50/P80/P90: 39% / 52% / 59% (targets 50 / 80 / 90). Realised 22.1m of 1566.2m predicted gp (1%).

#### profit / browser_baseline — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 39 | 39% | 36% |
| 40%-60% | 30 | 49% | 43% |
| 60%-80% | 86 | 72% | 45% |
| 80%-90% | 45 | 86% | 51% |
| 90%-100% | 48 | 96% | 67% |

Calibration error 22.3%. Finished within own P50/P80/P90: 29% / 45% / 47% (targets 50 / 80 / 90). Realised 1.8m of 8.3m predicted gp (21%).

#### profit / browser_baseline — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 40 | 39% | 45% |
| 40%-60% | 28 | 48% | 54% |
| 60%-80% | 88 | 72% | 52% |
| 80%-90% | 52 | 85% | 63% |
| 90%-100% | 57 | 96% | 67% |

Calibration error 18.7%. Finished within own P50/P80/P90: 38% / 54% / 55% (targets 50 / 80 / 90). Realised 3.9m of 8.6m predicted gp (45%).

#### profit / ev_per_offer — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 10 | 39% | 0% |
| 40%-60% | 24 | 51% | 8% |
| 60%-80% | 22 | 70% | 14% |
| 80%-90% | 29 | 85% | 21% |
| 90%-100% | 245 | 98% | 55% |

Calibration error 45.6%. Finished within own P50/P80/P90: 9% / 19% / 25% (targets 50 / 80 / 90). Realised -13.4m of 1553.2m predicted gp (-1%).

#### profit / ev_per_offer — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 8 | 39% | 0% |
| 40%-60% | 19 | 51% | 16% |
| 60%-80% | 42 | 73% | 55% |
| 80%-90% | 33 | 85% | 61% |
| 90%-100% | 301 | 98% | 72% |

Calibration error 25.7%. Finished within own P50/P80/P90: 32% / 42% / 49% (targets 50 / 80 / 90). Realised 2.3m of 1560.5m predicted gp (0%).

#### profit / ev_roi — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 62 | 5% | 5% |
| 20%-40% | 71 | 34% | 8% |
| 40%-60% | 148 | 48% | 11% |
| 60%-80% | 29 | 65% | 10% |

Calibration error 28.4%. Finished within own P50/P80/P90: 9% / 9% / 9% (targets 50 / 80 / 90). Realised -409.5k of 1539.5m predicted gp (-0%).

#### profit / ev_roi — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 72 | 5% | 42% |
| 20%-40% | 81 | 34% | 42% |
| 40%-60% | 127 | 48% | 37% |
| 60%-80% | 29 | 65% | 62% |

Calibration error 15.4%. Finished within own P50/P80/P90: 42% / 42% / 42% (targets 50 / 80 / 90). Realised -338.5k of 1539.7m predicted gp (-0%).

#### profit / gp_slot_hour — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 2 | 40% | 0% |
| 40%-60% | 14 | 52% | 0% |
| 60%-80% | 10 | 69% | 0% |
| 80%-90% | 13 | 86% | 8% |
| 90%-100% | 317 | 98% | 57% |

Calibration error 43.9%. Finished within own P50/P80/P90: 5% / 16% / 22% (targets 50 / 80 / 90). Realised -12.2m of 1254.0m predicted gp (-1%).

#### profit / gp_slot_hour — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 2 | 40% | 0% |
| 40%-60% | 14 | 52% | 7% |
| 60%-80% | 11 | 69% | 27% |
| 80%-90% | 12 | 86% | 50% |
| 90%-100% | 400 | 98% | 78% |

Calibration error 22.3%. Finished within own P50/P80/P90: 29% / 39% / 45% (targets 50 / 80 / 90). Realised -5.5m of 1052.4m predicted gp (-1%).

#### profit / gp_capital_hour — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 54 | 5% | 6% |
| 20%-40% | 65 | 35% | 8% |
| 40%-60% | 154 | 48% | 11% |
| 60%-80% | 33 | 66% | 18% |
| 80%-90% | 5 | 85% | 20% |
| 90%-100% | 1 | 97% | 0% |

Calibration error 30.6%. Finished within own P50/P80/P90: 10% / 10% / 10% (targets 50 / 80 / 90). Realised -459.3k of 1044.2m predicted gp (-0%).

#### profit / gp_capital_hour — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 0%-20% | 67 | 5% | 43% |
| 20%-40% | 74 | 35% | 39% |
| 40%-60% | 151 | 48% | 40% |
| 60%-80% | 32 | 66% | 59% |
| 80%-90% | 2 | 81% | 100% |
| 90%-100% | 1 | 97% | 100% |

Calibration error 13.7%. Finished within own P50/P80/P90: 43% / 43% / 43% (targets 50 / 80 / 90). Realised -300.9k of 1540.1m predicted gp (-0%).

#### profit / gated — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 7 | 39% | 14% |
| 40%-60% | 24 | 52% | 21% |
| 60%-80% | 66 | 72% | 48% |
| 80%-90% | 42 | 85% | 62% |
| 90%-100% | 159 | 97% | 69% |

Calibration error 26.2%. Finished within own P50/P80/P90: 23% / 44% / 51% (targets 50 / 80 / 90). Realised -451.5k of 10.9m predicted gp (-4%).

#### profit / gated — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 8 | 39% | 25% |
| 40%-60% | 25 | 53% | 40% |
| 60%-80% | 66 | 72% | 48% |
| 80%-90% | 41 | 85% | 66% |
| 90%-100% | 173 | 97% | 71% |

Calibration error 23.3%. Finished within own P50/P80/P90: 28% / 48% / 54% (targets 50 / 80 / 90). Realised 1.8m of 11.4m predicted gp (16%).

#### profit / reach — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 46 | 39% | 20% |
| 40%-60% | 70 | 51% | 24% |
| 60%-80% | 64 | 69% | 38% |
| 80%-90% | 31 | 85% | 61% |
| 90%-100% | 54 | 96% | 59% |

Calibration error 28.0%. Finished within own P50/P80/P90: 25% / 36% / 38% (targets 50 / 80 / 90). Realised -813.6k of 13.9m predicted gp (-6%).

#### profit / reach — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 48 | 39% | 23% |
| 40%-60% | 73 | 51% | 34% |
| 60%-80% | 57 | 69% | 40% |
| 80%-90% | 32 | 85% | 62% |
| 90%-100% | 55 | 96% | 62% |

Calibration error 23.4%. Finished within own P50/P80/P90: 28% / 40% / 42% (targets 50 / 80 / 90). Realised -132.8k of 14.0m predicted gp (-1%).

#### profit / replay_gate — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 37 | 39% | 16% |
| 40%-60% | 69 | 50% | 25% |
| 60%-80% | 63 | 69% | 38% |
| 80%-90% | 33 | 85% | 67% |
| 90%-100% | 65 | 96% | 66% |

Calibration error 26.2%. Finished within own P50/P80/P90: 24% / 37% / 39% (targets 50 / 80 / 90). Realised 409.4k of 13.3m predicted gp (3%).

#### profit / replay_gate — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 40 | 39% | 22% |
| 40%-60% | 63 | 49% | 32% |
| 60%-80% | 66 | 69% | 50% |
| 80%-90% | 34 | 85% | 59% |
| 90%-100% | 68 | 96% | 65% |

Calibration error 22.2%. Finished within own P50/P80/P90: 30% / 41% / 44% (targets 50 / 80 / 90). Realised 1.5m of 13.5m predicted gp (11%).

#### profit / replay_gate_stable — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 36 | 39% | 14% |
| 40%-60% | 70 | 51% | 27% |
| 60%-80% | 72 | 69% | 39% |
| 80%-90% | 30 | 86% | 63% |
| 90%-100% | 64 | 96% | 67% |

Calibration error 26.6%. Finished within own P50/P80/P90: 27% / 36% / 39% (targets 50 / 80 / 90). Realised 1.9m of 13.1m predicted gp (14%).

#### profit / replay_gate_stable — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 35 | 39% | 26% |
| 40%-60% | 73 | 51% | 37% |
| 60%-80% | 65 | 69% | 46% |
| 80%-90% | 31 | 85% | 55% |
| 90%-100% | 68 | 96% | 66% |

Calibration error 21.8%. Finished within own P50/P80/P90: 30% / 41% / 44% (targets 50 / 80 / 90). Realised 2.8m of 13.3m predicted gp (21%).

#### profit / replay_portfolio — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 47 | 39% | 13% |
| 40%-60% | 74 | 52% | 26% |
| 60%-80% | 102 | 68% | 46% |
| 80%-90% | 27 | 85% | 59% |
| 90%-100% | 11 | 93% | 91% |

Calibration error 23.3%. Finished within own P50/P80/P90: 28% / 36% / 38% (targets 50 / 80 / 90). Realised 3.5m of 21.3m predicted gp (16%).

#### profit / replay_portfolio — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 47 | 39% | 15% |
| 40%-60% | 75 | 52% | 32% |
| 60%-80% | 104 | 68% | 53% |
| 80%-90% | 27 | 85% | 56% |
| 90%-100% | 10 | 93% | 90% |

Calibration error 19.2%. Finished within own P50/P80/P90: 33% / 41% / 42% (targets 50 / 80 / 90). Realised 4.1m of 21.6m predicted gp (19%).

#### profit / replay_portfolio_mean — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 48 | 39% | 12% |
| 40%-60% | 80 | 51% | 35% |
| 60%-80% | 101 | 68% | 42% |
| 80%-90% | 21 | 85% | 57% |
| 90%-100% | 9 | 94% | 89% |

Calibration error 22.8%. Finished within own P50/P80/P90: 29% / 37% / 37% (targets 50 / 80 / 90). Realised 3.7m of 22.1m predicted gp (17%).

#### profit / replay_portfolio_mean — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 53 | 39% | 9% |
| 40%-60% | 75 | 51% | 36% |
| 60%-80% | 101 | 68% | 52% |
| 80%-90% | 23 | 85% | 61% |
| 90%-100% | 10 | 94% | 80% |

Calibration error 19.0%. Finished within own P50/P80/P90: 33% / 40% / 41% (targets 50 / 80 / 90). Realised 4.4m of 22.4m predicted gp (19%).

#### profit / replay_portfolio_offer — calibration under `strict_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 47 | 39% | 13% |
| 40%-60% | 74 | 52% | 26% |
| 60%-80% | 102 | 68% | 46% |
| 80%-90% | 27 | 85% | 59% |
| 90%-100% | 11 | 93% | 91% |

Calibration error 23.3%. Finished within own P50/P80/P90: 28% / 36% / 38% (targets 50 / 80 / 90). Realised 3.5m of 21.3m predicted gp (16%).

#### profit / replay_portfolio_offer — calibration under `touch_0.10`

| predicted P(full trip) | offers | mean predicted | observed |
|---|---|---|---|
| 20%-40% | 47 | 39% | 15% |
| 40%-60% | 75 | 52% | 32% |
| 60%-80% | 104 | 68% | 53% |
| 80%-90% | 27 | 85% | 56% |
| 90%-100% | 10 | 93% | 90% |

Calibration error 19.2%. Finished within own P50/P80/P90: 33% / 41% / 42% (targets 50 / 80 / 90). Realised 4.1m of 21.6m predicted gp (19%).
