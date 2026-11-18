# Model and research notes

Design notes for the model. Numerical examples illustrate it; they are not
live quotes or verified returns. Setup and usage are documented in the
[README](../README.md).

## The strategy

The first-time profile is **Members**: members items are available and the
planner derives **8 GE slots**. Selecting **Free-to-play** changes both rules
to F2P-only items and 3 slots. Slot count and item access are not separate
settings, so `members + 3 slots` cannot exist in the UI, CLI or Python
configuration.

There are three flip strategies. Active and Away are the two ends of one
question — how long until you next look at the Grand Exchange; Max profit
(section 1d) asks which single flip makes the most money:

- **Active** — you are watching and relist the sell as soon as the buy fills.
  Ranks expected GP per occupied slot-hour, rewarding fast round trips and
  capital recycling.
- **Away** (stored as `overnight`; `away` is accepted everywhere) — your next
  check is 1, 2, 4, 6, 8, 10 or 12 hours off: an errand, a work day or a night
  (8h by default). The buy offer rests unattended; bought items land in the
  collection box and cannot create a sell offer by themselves. The model
  therefore estimates partial inventory on return across the rolling 4-hour
  limit windows, followed by a separate 4-hour liquidation window. Expected
  value subtracts stress loss for inventory still unsold after that window.
  Volatility, falling drift, seller-heavy flow, the alch floor (as far as you
  can cast it), regime/mean-reversion context over the whole holding period,
  update risk across the absence, quote age and historical reach all affect
  that result.

Before you switch to Away, leave listed sell offers in place — they need no
watching — and cancel Active buys that have not filled: they were priced for
someone who relists immediately. A saved Active flip in the browser says this
on its card when the strategy changes.

A quoted margin is not profit. It is profit *if* both legs of the flip fill,
and nothing guarantees that. Everything here exists to turn a quoted margin
into an expected value, and then to be honest about how far that expectation
can be trusted.

### 0. How the plan is chosen

Sections 1–7 describe the *rate model*: a quoted spread, an assumed share of
the traded volume, and the timing and risk that follow from them. It scores
every item and produces the time band on each card. It does not decide what
gets bank on its own: in a walk-forward backtest on five weeks of real prices
(November 2026, [audit notes](audit-2026-11.md)) it could not tell whether the
price would ever cross the offer. On the held-out fortnight it promised an
82–97% chance of a complete Active round trip and delivered 22–50%, and a bank
run on its ranking lost money.

The browser, the CLI and the agent choose the plan in the same way:

1. **Quality gates** (`filters.automatic_profile`). A quote no older than 10
   minutes (15 for Away), a minimum of traded volume and net ROI, at least one
   gp of room inside the spread, no bot-supplied staples, and at most 25% of
   the bank in one new offer (the bank-risk setting).
2. **Measured reach.** For the 45 leading candidates the item's own recent
   5-minute buckets are read. An offer is credited only with volume that
   traded at a price it *beats*: a buy at B with the instant-sells that went
   through below B, a sell at S with the instant-buys above S. Volume at
   exactly the offer's price counts for nothing by default
   (`touch_fill_weight`), because there the offer queues behind older ones
   and the queue cannot be seen. The execution optimiser therefore prices
   inside the spread when that reaches volume, and an item whose spread is a
   single gp reaches none. Of the volume its price does beat, an offer is
   sized on the queue share (one sixteenth or less) by default (order size
   `careful`), or on 15% or 30% with `balanced` or `large`, in every
   strategy.
3. **Replay.** The concrete offer — those prices, that quantity, the
   strategy's deadline — is placed at many start times across the last day
   and played forward on the buckets that followed each one: a unit is sold
   only after it was bought, and stock unsold at the deadline is sold at the
   going instant-sell price, less tax. This measures what a rate cannot: the
   buy that fills because the price fell through it and the sell that then
   waits above the market.
4. **Evidence before bank** (`filters.has_funding_evidence`). A row is funded
   only if that replay made money in *both* halves of its window. An edge
   that shows in one half came from one move of the price; requiring both
   was the single largest gain in the backtest. Funded rows are ranked and
   sized on the replayed result (the weaker half), in the strategy's own
   unit: per slot-hour for Active, per flip for Away and Max profit.
5. **Slots and bank together.** The funded sizes are the ones that maximise
   that objective under both constraints (`engine.select_portfolio`, an exact
   small knapsack), with at most three rows from one family of related items
   (`filters.category_full`; "other" is not a family) and one row per
   connected potion-dose limit. Ranking each item alone and funding from the
   top is right only when slots are what runs out; when the bank runs out
   first, a flip that earns slightly less on a tenth of the coins beats one
   that crowds three others out. The plan says which of the two decided it,
   and leaves a slot or part of the bank open when no further candidate made
   money in its replay.

The highest expected profit per offer is usually not the highest return on
coins or per hour: on a live snapshot the two top-eights shared one item in
eight. In the backtest, re-ranking the rate model on EV per offer, on ROI, on
gp per slot-hour or on gp per capital-hour changed nothing or deployed
nothing; what mattered was whether margin and fill had been checked against
the item's actual price path. With that in place, ranking Active on profit
per offer or per slot-hour gave the same result within noise.

**What this rests on.** The replay is measured on public trades, not on your
fills. Two things about a private offer cannot be read from them: whether an
offer at exactly the last traded price fills, and what share of the volume
that crosses your price reaches you rather than someone else. The model
assumes "no", and a queue share of one sixteenth in every strategy by default;
the backtest was run with the share at 3%, 10% and 30% under both answers to
the first question. The plan beat the rate-model ranking under most of those
assumptions, and its worst case over them was better in every strategy; but
for Max profit the rate-model ranking earns more *if* offers at the traded
price do fill, and the plan was not shown to beat the browser plan of commit
`92cee13` there. For Active it beat that browser plan only on the
conservative assumptions: with a 30% share, or if unsold stock is left
standing rather than sold at the deadline, that plan did as well or better,
because it puts four times as much of the bank to work. The amounts the
backtest reports are what a deliberately conservative simulator allows, not a
profit forecast. Logging real offers with `journal.py` is what turns these
assumptions into measurements.

#### Order size

The Grand Exchange matches on price first: a sale executes against the highest
buy offer, a purchase against the lowest sell offer, and age only decides
between offers at the *same* price (OSRS Wiki, *Grand Exchange*, read
2026-11-16). Volume that traded through an offer's price therefore reached
offers this one would have been served before, and the order size says how
much of it the plan sizes on, in every strategy: `careful` (the queue share,
the default and the only value evaluated on held-out data), `balanced` (15%)
and `large` (30%), in the browser next to the strategy and as `--order-size`
in `cli.py` and `agent.py` (`crossing_capture_share` for Active,
`resting_capture_share` for Away and Max profit). Larger orders earn more if
your offers fill quickly and lose more if they do not: a larger buy fills in
full exactly when the price is falling through it. On the tuning
period (10–29 October 2026, 925 decisions, 20m bank, members), bank gp per
hour against the six fill assumptions of the simulator (`strict`: only volume
through the price fills; `touch`: volume at the price as well; then the share
of it that really arrives); these are six 3.5-day bank histories with wide
intervals, not out-of-sample evidence:

| Active sized on | strict 3% | strict 10% | strict 30% | touch 3% | touch 10% | touch 30% | mean |
|---|---|---|---|---|---|---|---|
| **queue share (`careful`, default)** | −2.4k | 3.8k | 11.6k | 3.4k | 7.2k | 16.0k | 6.6k |
| 15% (`balanced`) | −7.7k | 8.5k | 25.2k | −1.4k | 14.4k | 35.8k | 12.5k |
| 30% (`large`) | −15.1k | −1.0k | 32.3k | −6.2k | 15.1k | 51.3k | 12.7k |

For an offer that rests unwatched the evidence points the other way: nobody
reprices it when it is outbid, and every larger share earned less on average
over the same six assumptions:

| sized on | Away, mean of six | Max profit, mean of six |
|---|---|---|
| queue share (`careful`) | 2.0k | 13.5k |
| 15% (`balanced`) | 0.2k | 7.9k |
| 30% (`large`) | −1.9k | 6.4k |

Larger Away and Max profit orders are therefore a choice for more gp in play,
not for more expected profit.

`python3 -m backtest run --method policy_x00 --method policy_x15 --method
policy_x30` runs these settings; a new held-out period that starts on or after
14 November 2026 has to be used once to evaluate them
(`docs/audit-2026-11.md`, addendum).

### 1. A slot is time, not a container

Free-to-play has 3 GE offer slots, members 8. The binding constraint is not
gold, it is slots — and a slot is occupied for however long the flip takes, not
for a fixed window. A flip that clears in twelve minutes for 5,000 gp earns
25,000 gp per slot-hour; one that ties the slot up for the full four hours to
make 40,000 earns 10,000.

Fill throughput is a distribution rather than one all-or-nothing batch event.
Traded volume on each side gives an arrival rate, but the public feed contains
executions—not queue depth, offer position or transaction batch sizes. The
realised rate is therefore the forecast rate times an uncertain multiplier
`M`, and one leg takes `about a minute of your time + quantity / (rate × M)`.
Everything about timing comes from that one distribution:

- the **time band**: typical (median), 80% and 90% round-trip times;
- **P(full trip)**: the chance the whole quantity is bought *and* sold before
  the 4-hour deadline;
- the expected completed quantity and its 80% range;
- the ranking denominator: expected slot **occupancy**, with an unfinished
  trip cancelled at the deadline;
- the Active **quantity**: the largest whose whole round trip completes before
  the deadline with 80% probability;
- the **re-check time**: if not one unit has bought by then, the forecast has
  failed — re-check the live margin and reprice or cancel.

Away reports the buy fill by return separately from liquidation.

In Active the rate model sets `downside_risk` to 0: an unfinished trip is
cancelled at the deadline and only its occupancy is charged. Stock left over
is priced by the replay the plan ranks and sizes on, which sells whatever is
unsold at the deadline at the last instant-sell price, after tax.

### 1b. How wide the time band is

Time is quantity *divided* by an uncertain rate, so even with an unbiased rate
the time is skewed upward: within the model's own distribution only about 35%
of trips finish by the time at the mean rate, and the 90th percentile is about
3.5× it. The band is therefore built from the distribution, not from
`quantity / rate`:

- **One distribution, both legs.** The legs share the multiplier: a quiet
  evening or an under-counted crowd slows the buy and the sell of the same
  item together. Treating them as independent would average the error away
  and shorten the tail — the optimistic direction for a deadline. With one
  multiplier every number above is a closed form that the Python engine and
  the browser compute identically.
- **The width includes the volume forecast** (`volume_forecast_log_sigma
  = 0.6`, in quadrature with the queue term). On cached `/timeseries` data the
  error of forecasting the next two hours' volume from the last hour alone has
  a log standard deviation of 0.46–0.81 per series. A row whose reach was
  never checked against 14-day history gets a further
  `unverified_fill_log_sigma`. Thin evidence therefore widens the band and —
  through the 80% sizing — shrinks the quantity and the score.
- **Only the queue term is centred to mean one.** The measured volume error
  is median-unbiased (log median −0.07 to +0.16 across tiers), so the extra
  width lengthens the tails without inflating the typical time.
- **Active sizing targets an 80% complete round trip by the deadline**
  (`active_target_completion`). A flip that cannot reach it even at one unit
  is still listed, with a "fill odds" warning and a worse score, but is never
  funded automatically.
- **Every Active flip carries a re-check time**: the buy leg's own P90, capped
  at 45 minutes. A buy cannot complete before it starts, so if not one unit
  has filled by its P90, the forecast has failed whatever the hidden queue
  looks like. Cards also give a cancel-by time (the round trip's P90, at most
  the deadline). Saved browser flips show both as timers.

Fast flips stay recognisably fast: a small order on a deep book shows a band
of minutes, not hours.

### 1c. What Away does differently

- **The alch floor covers only what can be cast.** High Alchemy is capped at
  1,200 casts an hour (five 0.6 s ticks), so the floor covers at most
  `1,200 × liquidation hours` units; the rest carries the full stress move.
- **Quantity is the best expected value**, after stranded-inventory stress,
  chosen from 25/50/75/100% of the mean-rate capacity at the optimal prices.
  Everything the mean rate could buy completed the full buy 38% of the time
  and left about 30% of the order unsold after the selling window (live data,
  2026-10-01, 20m bank, 8h).
- **Exposure is measured over the holding time.** Update risk and mean
  reversion use the absence plus the sell (update risk: the absence plus the
  whole selling window).
- **It may bid below today's price.** Time is what an unattended buy has, and
  a lower bid fills if the price dips to it. For depths of 1–8% under the
  touch the fill rate is scaled by the expected share of the absence a
  driftless walk with the item's own volatility spends at or below the bid.
  A dip fill is sold into the market that dipped, so the exit price is
  lowered by the dip minus what a *significantly mean-reverting* item is
  expected to recover by the sale (`1 − exp(−κ·t)` from its OU fit). Without
  reversion evidence the dip carries through to the exit, a lower bid only
  fills more slowly, and the optimiser never chooses it — dip bids therefore
  appear only after the 14-day check, and are labelled.

Away is also sized on the **14-day average rate** of each side rather than on
the one live hour the snapshot happened to land in: an 8-hour absence spans a
good part of the daily cycle. On the cached 1-hour series (5 items, 15 days)
the next eight hours ran at 0.73–0.81× the snapshot hour after midnight UTC
and 1.3–1.8× from late morning; the daily average takes the cycle out without
inventing an hourly profile that five items cannot support.

### 1d. Max profit: the best flip, whatever it takes

**Max profit** (stored as `profit`; `--strategy profit`) is for a player who
cares how much a flip makes, not how fast the slot turns over. Active's
gp-per-slot-hour rightly prefers a 20k margin that clears in twenty minutes
to a 200k one that takes six hours — but only if the slot is refilled with
another good flip. When it is not, the slow flip is the better trade.

- **Ranks on profit per flip**, not per hour: risk-adjusted expected profit
  for the funded quantity after GE tax, the bond fee, the fill distribution,
  adverse selection, holding risk, quote staleness, mean reversion, the alch
  floor, update risk and the stress cost of unsold inventory.
- **Relists like Active**: the sell goes in as soon as the buy fills, so it
  uses the same sequential round-trip distribution. The deadline is 24 hours,
  the longest horizon the profile accepts. A trip not finished by then is
  cancelled.
- **Charges unsold inventory like Away.** Units bought but not sold by the
  deadline carry the same stress move (1.65σ over the horizon plus falling
  drift and seller flow, capped at 50%), with the alch floor covering at
  most what can be cast in Away's four-hour clearing window.
- **One flip is one buy offer of at most one buy-limit window**, although 24
  hours span six windows. The quantity is Away's expected-value choice, so a
  size whose tail would sit unsold loses to a smaller one.
- **Prices and sizes on the 14-day average volume** after the deep check, as
  Away does.
- **Never bids under the touch.** Dip bids are an Away tool for an offer
  nobody watches; a Max profit buy is relisted and repriced instead.

Whether this strategy's picks are good depends on something public data
cannot settle. In the November 2026 backtest the plan of section 0 beat the
rate-model per-flip ranking when an offer needs to beat the traded price to
fill, and lost to it clearly when an offer at exactly the traded price fills
as well; in the first case the rate-model ranking drew the bank down by 29%.
Treat Max profit as the least validated of the three.

Time is information here, not the ranking. Every pick still shows the
P50/P80/P90 band, P(full trip within 24h), the re-check and cancel-by times,
expected slot-hours, downside risk and warnings ("fill odds" below 50%,
"inventory risk" from 20% unsold). A slow pick can have a median past the
deadline: its expected value already counts the cancelled remainder, and the
band says so plainly. Quote-age confidence uses Active's limits, because the
offer is placed at the live quote. The automatic plan keeps Active's freshness
and ROI floors but Away's lower volume floor — admitting slow items is the
point — and has no completion target; the stress charge is what keeps a
fragile slow flip down.

### 2. You have to get to the front of the queue, and you are not alone in it

The crowd you are queued behind is sized per item. Every participant is capped
at the buy limit per window, so producing the observed volume takes at least
`volume_per_window / buy_limit` of them. Fire runes: 6.7m units a window
against a 50,000 limit, so 134 participants at minimum. Limpwurt root comes to
9.5, close to the quiet-market floor (`competitors_at_touch`).

Where the crowd term binds, your share is `buy_limit / volume_per_window`, so
your fill rate is exactly one buy limit per window. **On a crowded item you
cannot beat your own buy limit** — which is the answer an hour of watching the
Grand Exchange gives you. Conceding spread still jumps the queue, so this only
bites where it should: items whose spread is a single gp and where there is
nothing to concede.

The GE matches offers **on price first, then on offer age**. At the same price
an offer placed days ago has near-absolute priority. So there are two ways to
fill: outbid the queue, or wait in it. Air runes quoted at 5/6 read as a 20%
return across a 50,000 buy limit — but jumping the queue would mean buying at
6 to sell at 5, a guaranteed loss. There is **zero room to compete**, so you
sit behind thousands of offers for one coin.

Every item carries an **undercut room** number, but room is not free priority.
The optimiser enumerates concrete buy and sell concessions, recalculates tax,
margin, quantity and partial-fill EV for each, and prints the exact winning
prices. Leather quoted at 173/192 may justify paying inside that spread, but
its card then shows the dearer buy and/or cheaper sell; the model never
combines an aggressive fill rate with untouched passive-price profit. Items
with no room are not filtered out; they fill slowly, and the ranking says so.

### 3. Your offer fills when you least want it to

A resting buy fills fastest exactly when the price is falling — someone is
dumping into it — and then your sell leg is stranded above the market. Two
independent readings of that hazard are scored: **order-flow imbalance** (which
side is being aggressive right now, from the split of hourly volume between
buyer- and seller-initiated trades) and **drift** (where the price has been
going, from the 5-minute against the 1-hour mid). Both are penalised only in
the direction that hurts someone who is long between the legs.

### 4. Every item is not the same item

One exponential penalty for trading above a 14-day median would be right for
a rune and wrong for a raid unique: supply of rare gear is fixed, demand grows,
and "above its two-week median" is that item's permanent condition. Each
deep-checked item gets its own **Ornstein-Uhlenbeck fit** on 14 days of 6-hour
buckets, which separates the cases and reports its own half-life:

- Where reversion is real and statistically significant, the expected return
  over the *actual* holding period is credited or charged. Significant means
  a regression t of −2.93 or lower. Under a random walk that statistic follows
  the Dickey-Fuller distribution, not Student's t: −2.0 labels 28% of
  simulated random walks of 56 buckets as reverting, −2.93 about 5%. The
  price is power: a half-life of 17 hours is detected about 56% of the time,
  one of two days about 11%. Buckets without trades stay in the series as
  gaps, so a gap is not read as one 6-hour step.
- Where it is not — a trending item — only a small capped trend term applies.
  A rising price and a merch-clan pump look identical in price data, so the
  upside credit stays deliberately timid.
- Where the price level shifted mid-history, usually a game update re-pricing
  the item, the fit spans two different markets and is not trusted at all.

Quote staleness works the same way. What decays is not time but price
certainty, so the discount is driven by the item's own fitted volatility over
the elapsed time: a 20-minute-old print on a liquid staple is still the
market, a 30-second-old one on a thin volatile item may already be gone.

### 4b. A percentage of a cheap price is not a percentage of an expensive one

Prices are whole gp, so a 10 gp item cannot move less than 10% and a 7,000 gp
item cannot move less than 0.014%. Momentum measured as a raw percentage is
therefore mostly a measure of how cheap the item is. Across free-to-play items,
median absolute drift by price quartile:

| price quartile | median price | median absolute drift |
|---|---|---|
| cheapest | 10 gp | 7.07% |
| second | 109 gp | 1.97% |
| third | 495 gp | 0.93% |
| dearest | 7,396 gp | 0.61% |

A twelvefold gap produced by nothing but the price grid. Salmon printed a
five-minute mid of 28.5 against an hour of 25.5: three gp on a 26 gp item,
which as a raw percentage reads as 11.8% of momentum. Drift is therefore
measured net of one tick, so the same 1 gp wobble reads as nothing whether
the item costs 10 gp or 10,000.

### 5. The last print is not the market

A few hundred salmon dumped at 30 gp reads as "buy at 30" to every intraday
number, while two weeks of sellers accepted ~40. So the intraday reference per
side is the 5-minute and 1-hour average **weighted by how much traded in each**,
and the estimate takes the worse of that and the last real trade.

When both sides of `/latest` print at the same price — one trade that crossed,
or two prints from moments when the price had moved — that blend returns
buy ≥ sell. Measured on live data, that happened on 248 free-to-play items in
one snapshot, and the hour's averages showed a real spread on 88 of them. Two
prints showing no spread are the absence of evidence, so the averages are used
when the blend collapses, guarded only by the two sources still describing the
same market (`reference_fallback_max_divergence`).

The shortlist then gets a second pass against 14 days of history, measuring what
share of real volume traded at your prices — computed on **detrended** prices,
so a dump stays visible whenever it happened but a steadily rising item is not
punished for trading above last week. That share feeds the fill *rate*: a price
only 5% of the market ever reached is not a flip earning 5% of its margin, it is
a flip that takes twenty times as long.

### 5b. A good spread repeats

One wide print is not an edge. The deep check measures the spread in every
two-sided 6-hour bucket over 14 days and, for the leading 15 candidates, every
traded 5-minute bucket over the latest 6 hours. It asks three separate
questions: how often the average high/low spread remained positive after GE
tax, how much of the live per-item margin the historical median supports, and
how much positive-margin volume actually appeared on the thinner side of the
market.

Those readings form a bounded execution-evidence factor (0.7–1.3, with neutral
evidence equal to 1). It adjusts rank and plan confidence, not the quoted
profit or fill quantity. Twelve separate traded buckets are required for full
evidence weight, so a few lucky transactions cannot earn a **REPEATABLE EDGE**
badge.

### 6. The list itself is the biggest source of error

The tool scores a few hundred items and shows you the top. Ranking noisy
estimates does not surface the best items — it surfaces the items whose
estimation error happened to be largest and positive. With hundreds of
candidates and each estimate resting on a handful of trades, that bias is most
of what the top of an uncorrected list is made of, and it is worst exactly
where the data is thinnest.

So every score is shrunk toward the market-wide average by an amount set by how
much volume it rests on, using a hierarchical (empirical-Bayes) posterior. The
output shows both numbers: **MEASURED** is the score before shrinkage;
**EV/SLOT/H** (Active), **HORIZON EV** (Away) or **PROFIT/FLIP** (Max profit)
is after. A wide gap means the measured number was mostly the thinness of the
data behind it. When no difference between the day's scores survives the noise
at all, the tool says so instead of ranking anyway.

### 7. Things the game gives you for free

- **High alchemy is a floor.** No rational holder sells below `highalch` minus
  a nature rune, because the spell pays that unconditionally. For a flipper it
  is a free put: the worst case on the sell leg is the floor, not zero. Items
  trading *below* it are flagged — alching is capped at roughly 1,200 casts an
  hour, so this caps downside rather than being scalable free money.
- **The tax rounds down.** At each 50 gp tax step, the preceding price nets
  the seller the same: 1,000 and 999 both net 980 gp. **List at** takes that
  single free tick when available. Cutting to 998 loses a gp; above the tax
  cap there is no free tick.
- **~57 items pay no tax at all** (`tax_exempt.json`): cooked food, low-level
  ammo, tools, teleport tablets. Charging them 2% would take most of the
  spread on a 200 gp lobster.
- **A bond is not free to flip.** Bonds pay no GE tax, but a bond bought from
  the GE must be converted back to tradeable status before resale. The model
  deducts the 10% conversion fee from net revenue and reserves that fee in the
  required capital: candidate sizing, the slot allocation, the committed bank
  shown in the plan and saved-offer reservations all count buy price plus fee
  per bond. The game charges 10% of the guide price; the model estimates it
  from the planned sell price, which is the closest per-offer figure.
- **Updates generally ship Wednesday around 11:30 UTC**, with a recurring
  Tuesday maintenance risk window and announced exceptions. A position still
  open when either prior lands is discounted; the app does not claim this
  static prior is a live Jagex calendar.

### Execution is part of the decision

The browser is deliberately one-click. It derives freshness, minimum volume,
net ROI, undercut room, maximum unit price and bot-supply gates from the bank,
account and strategy; the Python tools apply the same profile unless a flag
replaces one of its gates. The **Max bank per trade** slider sets how much of
the total bank one new recommendation may commit, from 10% to 100% (25% by
default). Raising it lets one position grow, and concentrates more of the
bank in one item; the total plan can never commit more than the available
bank. Nothing is funded before the deep check has run, because the evidence a
row is funded on (section 0) does not exist until then. Each Active card
states when to re-check an untouched offer (its buy leg's P90, at most 45
minutes) and when to cancel what is left; a saved flip shows these as
reminders.

The plan is not the whole market. **All flip options** keeps every candidate
that passed the automatic freshness, liquidity, ROI, queue-room and
affordability gates in a searchable table. Each row has its own **Save &
monitor** action. A manually chosen row uses the same per-position bank cap,
takes the first free GE slot and remains visibly labelled with its confidence
and risk flags instead of being presented as an automatic recommendation.

**Save & monitor** records the suggested item, quantity, buy and target sell in
local browser storage and pins the slot. A gold card at the top then compares
that target with the newest live buy/sell prices after every refresh. The
values can be edited to the player's actual fill; Done or Remove releases the
reserved slot and bank. Units recorded as bought count against the item's buy
limit for four hours, in the browser and, through the journal, in the CLI and
the agent. **Export offers** downloads the saved offers for
`python3 journal.py import-browser`. Nothing places or automates an in-game
offer.

Replaceable mapping and 14-day series caches are capped and evicted before a
saved flip, lock, preference or holding is allowed to fail for storage quota.
If the browser blocks site storage entirely, the page reports that explicitly
instead of silently ignoring Save. Browser storage is origin-specific: the
local `file://` copy and the GitHub Pages URL keep separate lists.

The confidence badge means confidence in the model evidence, not certainty of
execution. A price reconstructed from hourly averages can never be High;
stale quotes and detected regime shifts are Speculative. Journal capture and
factor diagnostics compare realised profit with the risk-adjusted expected GP
that drove the decision, not with best-case margin × quantity.

### 8. A year is a different question from an hour

Everything above prices a round trip measured in hours. Holding an item for
weeks is a different bet with a different unit, and `merch.py` scores it
separately. The two numbers never get added together: an item can be a terrible
flip (nobody trades it, the spread is one gp) and an excellent hold (its price
has doubled in a year).

- **Trends are fitted on log prices.** The slope is then a growth *rate* that
  means the same thing on a 5 gp herb and a 60m wand, and R² is comparable
  across items rather than dominated by absolute scale.
- **Most apparent trends are not trends.** A year of daily prices with no
  drift in it at all still wanders far enough to look like a 40%/yr riser.
  Simulating driftless random walks: `|t| >= 1.5` labels 61% of pure noise a
  trend, `|t| >= 2.5` labels 42%, `|t| >= 5.0` labels 16%. The curve is
  scale-free — repeat it at 1.2%, 2.1% or 3.5% daily volatility and it moves
  under a point.

  So the threshold is 5.0, and several watchlist items with headline rates
  near +50%/yr are reported SIDEWAYS. Every row also carries a **noise
  probability**: the share of trendless items that would look at least this
  trendy. Read that column before the trend column.
- **Textbook t-statistics do not apply to prices.** Today's distance from the
  trend line is nearly yesterday's, so OLS standard errors are far too small —
  a pure random walk comes out at `|t|` of thirty. The slope's t is widened for
  AR(1) residual autocorrelation before anything is concluded from it.
- **The feed changed source on 30 September 2026.** Before that day the OSRS
  Wiki prices came from RuneLite clients only; since then they come from
  Jagex and cover every game client, so volumes on the two sides of the day
  are not comparable. The six-month volume comparison straddles it until
  about April 2027. The market-median normalisation below removes the part of
  the jump every item shares; it cannot remove a part that differs per item,
  so a supply badge whose comparison spans the change carries the note
  "Volume comparison spans the 30 September 2026 data-source change."
  (`merch.volume_change_spans_source_change`). Calibrations measured before
  that day (`volume_forecast_log_sigma`, `reference_fallback_max_divergence`)
  should be re-measured on later data.
- **A supply crunch is measured against the market, not in absolute terms.**
  Total trade volume in the game moves a long way over six months. Measured on
  live data every item on the watchlist — blood runes, diamonds and raid
  uniques alike — was down between 50% and 86%. Read absolutely that badges the
  entire game as a supply crunch, which is the same as badging none of it. The
  median of the basket is the market; what survives dividing it out belongs to
  the item. With fewer than eight items there is no market estimate and no
  badge is given.
- **A crash is deep *and* loud.** A price far below its own 14-day median on
  heavy volume is a dump. The same depth on quiet volume is a different animal
  and a better one — no forced seller to wait out — so it is classified
  separately. Nothing fires through a regime shift: a level that moved because
  the game changed has no median left to revert to.
- **Depth is ranked by how much of it you can trade.** A 70% collapse nobody
  deals in is worth less than a 25% dip on a liquid item that mean-reverts.

## What rejects an item, and what only hides it

Only structural facts reject: no mapping entry, a missing side of the quote,
nothing traded on one side, a margin that cannot survive the tax, or a single
unit you cannot afford. Everything else is scored, and the quality gates and
the command-line filters hide rows **after** scoring and shrinkage — so
narrowing the view never reorders what is left.

## Calibration, and what is still a guess

Every free parameter lives in one place: `engine.Calibration`. Each is marked
either DERIVED (forced by game mechanics or arithmetic) or CALIBRATE (a stated
prior, to be fitted from journal and archive data). None is tuned by feel inside
a function body, and the journal records which values produced each prediction.

The ones most worth fitting first, because they do the most work:

| Parameter | What it claims | Fit it from |
|---|---|---|
| `crossing_capture_share` | The share of the volume that trades strictly through an Active offer's price that reaches it. Default 0, the queue share below (order size `careful`); `balanced` and `large` set 15% and 30%. The largest single lever on order size | Journal: units filled over units that traded through the price while the offer was open |
| `resting_capture_share` | The same for Away and Max profit offers, which nobody reprices. Default 0; the order size sets it like the Active share | The same, for offers left unwatched |
| `competitors_at_touch` | Quiet-market floor of the queue share: you are one of 16 offers sharing the volume at your price | Journal: observed fill rate over volume at the offer's price |
| `touch_fill_weight` | An offer at exactly the last traded price earns none of the volume traded there (0) | Journal: fill rate of offers at the traded price against offers one tick inside it |
| `aggressiveness_scale` | How quickly price improvement reaches its capture ceiling | Journal: fill rate against distance from the touch |
| `fill_rate_log_sigma` | Queue-position uncertainty in the fill rate, centred to mean one | `journal.py calibration`: censored fit of the log error |
| `volume_forecast_log_sigma` | Error of forecasting the next hours' volume (0.6; measured 0.46–0.81 on cached series) | Tick archive, once it holds weeks |
| `unverified_fill_log_sigma` | Extra width before the 14-day reach check (a prior) | Spread of `log(fill_share)` across deep checks |
| `active_target_completion` | Active sizing/funding policy: 80% complete round trip by the deadline | Journal: P80 exceedance should come out near 20% |
| `reprice_check_max_minutes` | Latest "nothing filled — re-check" time (45) | Journal: time to first fill, once recorded |
| `priority_capture_ceiling` | In crowded items, re-pricing captures at most 3% of total side volume; a higher quiet-market touch share is preserved | Journal: realised share after improving the price |
| `score_noise_scale`, `score_noise_floor` | How much of a score is noise — this sets how hard shrinkage bites | Archive: how far an item's score moves between polls |
| `adverse_selection_gamma` | Sensitivity to order flow running against you | Journal: holding-period return against OFI at entry |
| `risk_aversion_eta` | Price risk between the legs | Journal, against a target Sharpe |

None of these constants is fitted to real fills yet: the journal holds no
outcomes. The backtest in [the audit notes](audit-2026-11.md) validates the
*selection* out of sample against public trades under stated fill
assumptions; it cannot validate the assumptions themselves. On the held-out
fortnight the funded Active rows realised 98% of their expected profit and the
predicted chance of a complete trip was off by 11 points on average (56 for
the rate model alone), but 70% of them finished inside their own 80% and 90%
time bounds rather than 80% and 90%, and Away and Max profit realised 31% and
44% of what was expected. The fallback is deliberately conservative: the
volume term is measured from public series, the unverified term widens rather
than narrows, and the sizing policy keeps a fifth of trips as the expected miss
rather than four fifths. What would turn the priors into measurements: roughly
20+ Active offers per liquidity tier logged with `place` / `bought` / `close` /
`cancel` (including the ones pulled unfilled) or exported from the browser, and
a few weeks of tick archive for the volume term and for time-to-first-fill.

Until then the model's *structure* is defensible and its *constants* are
beliefs: each constant enters on its own, so journal data can say which one is
wrong.

## Research basis

The execution model was checked against the current [OSRS Wiki Grand Exchange
mechanics](https://oldschool.runescape.wiki/w/Grand_Exchange): eight member or
three F2P slots, price-before-age matching, rolling four-hour buy limits,
connected potion-dose limits, no sell limit and the 2% floor-rounded/capped
sell tax. RuneLite's [Grand Exchange plugin
source](https://github.com/runelite/runelite/blob/master/runelite-client/src/main/java/net/runelite/client/plugins/grandexchange/GrandExchangePlugin.java)
confirms what can actually be observed client-side: offer states and executed
quantity deltas, not a public order book. The uncertainty model follows that
data boundary instead of inventing queue depth.

Operational guidance—timed partial fills, cancel/reprice discipline,
diversification and separate overnight buy/return/sell phases—was compared with
current community practice in a recent [active flipping
guide](https://www.reddit.com/r/OSRSflipping/comments/1uskrcb/beginner_guide_flipping_basics/)
and [overnight workflow
guide](https://www.reddit.com/r/OSRSflipping/comments/1vtt6qe/how_to_overnight_flip_for_complete_beginners/),
then kept manual to stay on the safe side of game rules. The broader case for
treating this as an intervened virtual economy, not an idealized frictionless
market, is consistent with the empirical OSRS economy study [*Grand Exchange:
An Analysis of a Virtual Economy*](https://arxiv.org/abs/2210.07970). Community
rules of thumb are never used as ground truth for a price; only live market
data and recorded user outcomes drive numbers.

## API etiquette

The wiki's [acceptable use policy](https://prices.runescape.wiki) asks for a
descriptive User-Agent and no per-item polling. The Python client sets one — if
you fork or deploy this, change `USER_AGENT` in `api.py` so the wiki team can
reach *you*. `/timeseries` is per-item and is only called for the selected
item and for a shortlist of at most 45 items per plan, cached 30 minutes; the
bulk routes are polled no faster than their own cache TTLs, which is what
`collect.py` respects too.

Both clients retry transient rate-limit/server/transport failures with bounded
exponential backoff. The Python client and the current browser session may use
a cached endpoint during a short outage and mark the feed stale, for at most
five extra minutes after its memory TTL. A cold start fails clearly. Concurrent
requests are coalesced. The collector never archives stale fallbacks, records
the API's bucket timestamp and exits nonzero when a one-shot poll fails.

The clients use API v1 while it works. When v1 answers a request with HTTP
400–499 other than 429, the same request is made once on v2; if that succeeds,
that kind of request — bulk (`/latest`, `/mapping`, `/5m`, `/1h`) or
`/timeseries` — uses v2 for the rest of the session (the browser then shows
"API v2" next to the feed status). Rate limits, server errors and network
failures never switch. v2 `/timeseries` takes `lookback` instead of
`timestep` (`5m` → `24h`, `1h` → `7d`, `6h` → `6m`, `24h` → `1y`), and a v2
series is used only when the `timestep` it returns is the one asked for; v2
averages carry two decimals, which both clients round half up to whole gp.
The v2 path was built from the wiki documentation and one observed response
and has not run against the live API. Its limit: on v2 the five-minute
history is expected to cover 24 hours instead of about 30, so Max profit,
which replays a 24-hour offer, has too few replay placements and funds
nothing until its replay is changed, which needs a backtest. The bulk routes
also serve any past bucket for every item at once (`/5m?timestamp=`,
`/1h?timestamp=`); the backtest builds its history from those, one request at
a time, and nothing in the live tools uses them.

### The 24h series and `VOLUME_SKIP_LAST`

Cross-checked against the same item at `6h` on 2026-07-26: for every
historical day, the 24h bucket's volume was the first 6h bucket of that day,
not the day's total, while the most recent bucket carried the whole day.
Leaving the final bucket in then reports an 8x volume spike on every item in
the game at once. Every volume calculation in `merch.py` drops the last bucket
(`VOLUME_SKIP_LAST`), which costs a day of latency on the volume signals.

Not affiliated with Jagex or the OSRS Wiki. Prices are estimates — flip at your
own risk.
