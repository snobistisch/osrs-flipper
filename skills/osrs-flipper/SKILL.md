---
name: osrs-flipper
description: Read Old School RuneScape Grand Exchange market signals from the local osrs-flipper tool. Use when asked what to flip, what to buy and hold, whether an item has crashed, or to report on open positions. Never invents prices — every number comes from the tool.
---

# OSRS Grand Exchange flipper

A local Python tool that ranks Grand Exchange flips and tracks long-horizon
merch positions. You call it and report what it says. You do not estimate
prices, you do not recall them from training data, and you do not fill a gap
with a plausible number.

Set `FLIPPER` to wherever the repository is checked out. All commands are run
from that directory.

## Commands

| Ask | Command |
|-----|---------|
| What should I actively flip now? | `python3 agent.py flips --json --capital <gp> --account members --strategy active` |
| What should I leave overnight? | `python3 agent.py flips --json --capital <gp> --account members --strategy overnight --overnight-hours 8` |
| What should I buy and hold? | `python3 agent.py merch --json` |
| Anything new since last time? | `python3 agent.py watch` |
| What am I holding? | `python3 agent.py portfolio --json` |
| Is the tool healthy? | `python3 agent.py status` |

`--capital` accepts how players write it: `250k`, `1.5m`, `2b`. Members is the
default and coherently means 8 slots plus members items. `--account
free-to-play` coherently means 3 slots and F2P items only.

## Reading the output

**`gp_per_slot_hour` is the ranking number.** It is expected profit per Grand
Exchange offer slot per hour, not per flip. A 200k margin that takes six hours
loses to a 20k margin that clears in twenty minutes, and that is the whole
point of the metric.

That statement applies to `strategy: active`. For `strategy: overnight`, read
`ranking_value` as risk-adjusted expected profit over `horizon_hours`. Always
report `p_fill`, `p_stranded` and `downside_risk_gp` with an overnight pick;
fast recycling after completion is not available while the player is offline.

**`gp_per_slot_hour_before_shrinkage` is the raw estimate.** When the two are
far apart, the raw number was mostly the thinness of the data. Say so rather
than quoting the bigger one.

**`edge_probability`** is the chance the item's score is not noise. Below about
0.6, present it as a coin flip.

**`noise_probability` on a trend is the number to read first.** It is the share
of items with *no trend at all* that would look at least this trendy. An item
showing `+57%/yr` with `noise_probability: 0.41` has not been shown to be
trending — four in ten trendless items look like that. Report the rate and the
noise together or not at all.

**`direction: SIDEWAYS` on a big-looking rate is not a bug.** It is the tool
declining to call a wandering price a trend. Do not talk the user past it.

**`volume_change_vs_market`, not `volume_change_6m`.** The whole market's volume
drifts; the raw number was down 50–86% on every item measured. Only the
market-adjusted figure says anything about one item's supply.

**`warnings` are not decoration.** If a row carries warnings, they go in the
answer next to the number.

## Reporting

Lead with the answer. One or two lines when nothing much happened; never a
table when a sentence will do.

- Prices in gp with player shorthand: `2.4m`, `365 gp`.
- Name the item and its id the first time it appears.
- No investment advice, no urgency, no "act fast". This is a game economy and
  the tool is a calculator.

If the tool returns nothing for `watch`, that means nothing crossed a
threshold. Reply `[SILENT]` and send no message.

If a command fails or the API is unreachable, say exactly that and stop. Do not
substitute remembered prices. `python3 agent.py status` tells you how stale the
caches are.

## What not to do

- Do not run `collect.py` yourself. It is a long-lived poller with its own cron
  entry; starting a second one doubles the request rate for nothing.
- Do not raise the fetch rate to "get fresher data". The bulk routes are cached
  at the wiki's own TTLs and polling faster returns identical bytes.
- Do not add positions to the portfolio unless the user says they bought
  something. `portfolio add` records a real trade, not a suggestion.
- Do not compare `gp_per_slot_hour` against `merch_score`. Different horizons,
  different units, no common scale.
