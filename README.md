# OSRS Grand Exchange Flipper

Find Grand Exchange flips you can actually execute. Live prices from the
[OSRS Wiki real-time price API](https://prices.runescape.wiki), ranked by
**expected gp per offer slot per hour** — not by the margin on the screen.

> **The browser version in `docs/` runs the older scoring model** and has not
> been ported to the rebuild described below. Use `cli.py` or `app.py` for the
> current one. See [The browser app is stale](#the-browser-app-is-stale).

## The strategy

A quoted margin is not profit. It is profit *if* both legs of the flip fill,
and nothing guarantees that. Everything here exists to turn a quoted margin
into an expected value, and then to be honest about how far that expectation
can be trusted.

### 1. A slot is time, not a container

Free-to-play has 3 GE offer slots, members 8. The binding constraint is not
gold, it is slots — and a slot is occupied for however long the flip takes, not
for a fixed window.

This is where the previous version of this tool was most wrong. It divided
every expected profit by four hours, the buy-limit window, as though every flip
occupied a slot for exactly that long. A flip that clears in twelve minutes for
5,000 gp earns 25,000 gp per slot-hour; one that ties the slot up for the full
four hours to make 40,000 earns 10,000. The old metric ranked the second one
four times higher.

Fill time is now a modelled random variable. Traded volume on each side of the
book gives an arrival rate, undercut room gives your share of it, and the two
together give an expected time for each leg and a probability that both clear
inside the window. **Round trip** in the output is that estimate, and it is the
denominator of the ranking.

### 2. You have to get to the front of the queue

The GE matches offers **on price first, then on offer age**. At the same price
an offer placed days ago has near-absolute priority. So there are two ways to
fill: outbid the queue, or wait in it.

This is why flipping air runes is a mistake. Quoted at 5/6, that 1 gp margin
reads as a 20% return across a 50,000 buy limit — but jumping the queue would
mean buying at 6 to sell at 5, a guaranteed loss. There is **zero room to
compete**, so you sit behind thousands of offers for one coin.

Every item carries an **undercut room** number: how many gp of price
improvement it can absorb on each side while still profiting. Leather at
173/192 has 7 gp of room; air runes have 0. That number is no longer a score
multiplier of its own — it feeds the fill rate, because how far ahead of the
queue you can buy your way is precisely what determines how fast you fill.
Items with no room are not filtered out; they fill slowly, and the ranking says
so.

### 3. Your offer fills when you least want it to

A resting buy fills fastest exactly when the price is falling — someone is
dumping into it — and then your sell leg is stranded above the market. Two
independent readings of that hazard are scored: **order-flow imbalance** (which
side is being aggressive right now, from the split of hourly volume between
buyer- and seller-initiated trades) and **drift** (where the price has been
going, from the 5-minute against the 1-hour mid). Both are penalised only in
the direction that hurts someone who is long between the legs.

### 4. Every item is not the same item

The old version applied one exponential penalty for trading above a 14-day
median to every item in the game. That is right for a rune and wrong for a raid
unique: supply of rare gear is fixed, demand grows, and "above its two-week
median" is that item's permanent condition.

Each deep-checked item now gets its own **Ornstein-Uhlenbeck fit** on 14 days of
6-hour buckets, which separates the cases and reports its own half-life:

- Where reversion is real and statistically significant, the expected return
  over the *actual* holding period is credited or charged.
- Where it is not — a trending item — only a small capped trend term applies.
  A rising price and a merch-clan pump look identical in price data, so the
  upside credit stays deliberately timid.
- Where the price level shifted mid-history, usually a game update re-pricing
  the item, the fit spans two different markets and is not trusted at all.

Quote staleness works the same way. A fixed 600-second half-life was too harsh
on a liquid staple, where a 20-minute-old print is still the market, and too
kind on a thin volatile one. What decays is not time but price certainty, so
the discount is driven by the item's own fitted volatility over the elapsed
time.

### 5. The last print is not the market

A few hundred salmon dumped at 30 gp reads as "buy at 30" to every intraday
number, while two weeks of sellers accepted ~40. So the intraday reference per
side is the 5-minute and 1-hour average **weighted by how much traded in each**,
and the estimate takes the worse of that and the last real trade.

The shortlist then gets a second pass against 14 days of history, measuring what
share of real volume traded at your prices — computed on **detrended** prices,
so a dump stays visible whenever it happened but a steadily rising item is not
punished for trading above last week. That share feeds the fill *rate*: a price
only 5% of the market ever reached is not a flip earning 5% of its margin, it is
a flip that takes twenty times as long.

### 6. The list itself is the biggest source of error

This is the correction that matters most, and no amount of better factors
substitutes for it.

The tool scores a few hundred items and shows you the top. Ranking noisy
estimates does not surface the best items — it surfaces the items whose
estimation error happened to be largest and positive. With hundreds of
candidates and each estimate resting on a handful of trades, that bias is not a
rounding error; it is most of what the top of an uncorrected list is made of,
and it is worst exactly where the data is thinnest.

So every score is shrunk toward the market-wide average by an amount set by how
much volume it rests on, using a hierarchical (empirical-Bayes) posterior. The
output shows both numbers: **MEASURED** is the score before shrinkage,
**EV/SLOT/H** is after. A wide gap means the measured number was mostly the
thinness of the data behind it. When no difference between the day's scores
survives the noise at all, the tool says so instead of ranking anyway.

### 7. Things the game gives you for free

- **High alchemy is a floor.** No rational holder sells below `highalch` minus
  a nature rune, because the spell pays that unconditionally. For a flipper it
  is a free put: the worst case on the sell leg is the floor, not zero. Items
  trading *below* it are flagged — alching is capped at roughly 1,200 casts an
  hour, so this caps downside rather than being scalable free money. The
  previous version loaded `highalch` from the API and never used it.
- **The tax rounds down**, so net revenue is a staircase with 50 gp treads.
  Every price inside a band nets the seller the same, which makes undercutting
  inside it free. **List at** is the bottom of the band — listing at exactly
  1,000 when 999 nets identically is giving away queue position for nothing.
- **~57 items pay no tax at all** (`tax_exempt.json`). The previous version
  exempted one: the bond. Everything else — cooked food, low-level ammo, tools,
  teleport tablets — was charged 2% it does not owe, which is most of the
  spread on a 200 gp lobster, and biased the ranking against exactly the items
  a capital-constrained free-to-play flipper lives on.
- **Updates ship on Wednesdays.** A position still open when one lands is the
  uninformed side of every trade that follows, so flips whose expected round
  trip runs into an update are discounted.

## Filters no longer decide what gets scored

The old pipeline was a chain of gates: too stale, too thin, ROI too low, no
undercut room — rejected, in that order, before anything deeper could speak for
the item. A filter that only subtracts cannot find edge; it can only shorten
the list.

Now only structural facts reject: no mapping entry, a missing side of the quote,
nothing traded on one side, a margin that cannot survive the tax, or a single
unit you cannot afford. Everything else is scored, and the filters in the
sidebar and on the command line hide rows **after** scoring and shrinkage — so
narrowing the view never reorders what is left.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Dashboard:

```bash
.venv/bin/streamlit run app.py
```

Terminal, same numbers:

```bash
python3 cli.py --capital 1m --slots 3
```

`--members` for members items, `--slots 8` if you have them, `--top 40` for a
longer list. The display filters (`--min-roi`, `--min-vol`, `--max-age`,
`--min-depth`) all default to off.

## Start the tick archive today

```bash
python3 collect.py
```

Every flipper polling the wiki sees the same numbers at the same latency, so
any signal read off the current snapshot has already been read by everyone
else. What nobody else has is *your* history at higher resolution than the API
serves: `/timeseries` hands out 6-hour buckets, and polling `/latest` every 30
seconds records individual trades the API will never give you retroactively.

The archive is worth nothing today and a great deal in three months. That is
the whole argument for starting it now. It writes a row only when an item's
trade timestamps actually change, so it tracks real trading activity instead of
accumulating 13 million identical rows a day.

Once it has data, both front-ends use it automatically, replacing the
single-live-hour volume estimate with one smoothed over days — the difference
between extrapolating a bucket sampled at peak and one sampled at 4am.
`python3 collect.py --status` shows what it holds.

## Log your flips

The point of predictions is checking them.

```bash
python3 journal.py open --name "Steel bar" --qty 1000 --buy 558 --predicted 6
python3 journal.py close 1 --sell 575
python3 journal.py cancel 2 --reason "never filled"
python3 journal.py stats
python3 journal.py calibration
```

Record the offers that **never filled**, not only the ones that worked. Keeping
only completed flips is the textbook way to conclude that every flip works, and
the fill-time model needs the censored observations.

`calibration` is the diagnostic the old journal could not produce:

- **Capture by predicted rank.** If capture falls as you go up the ranking, the
  top is still mostly estimation error and the shrinkage is too weak.
- **Fill time, predicted against actual.** The old ranking assumed four hours
  for every flip. This says by how much it was wrong.
- **Factor values on flips that beat versus missed their prediction.** A factor
  that differs sharply between the two columns is the one carrying the error.

## Calibration, and what is still a guess

Every free parameter lives in one place: `engine.Calibration`. Each is marked
either DERIVED (forced by game mechanics or arithmetic) or CALIBRATE (a stated
prior, to be fitted from journal and archive data). None is tuned by feel inside
a function body, and the journal records which values produced each prediction.

The ones most worth fitting first, because they do the most work:

| Parameter | What it claims | Fit it from |
|---|---|---|
| `competitors_at_touch` | You are one of ~4 offers at the touch price | Archive: observed fill rate over volume at the touch |
| `aggressiveness_scale` | Conceding ~25% of the spread jumps the queue | Archive: fill rate against distance from the touch |
| `score_noise_scale`, `score_noise_floor` | How much of a score is noise — this sets how hard shrinkage bites | Archive: how far an item's score moves between polls |
| `adverse_selection_gamma` | Sensitivity to order flow running against you | Journal: holding-period return against OFI at entry |
| `risk_aversion_eta` | Price risk between the legs | Journal, against a target Sharpe |

Until then the model's *structure* is defensible and its *constants* are
beliefs. That distinction is the point of the rebuild: the old nine-factor
multiplicative chain could not be calibrated even in principle, because nine
constants against one realised number are unidentifiable — no amount of journal
data could say which factor was wrong.

## Project layout

| File | Role |
|---|---|
| `engine.py` | Flip math and scoring. Pure stdlib, no I/O |
| `stats.py` | OU fits, empirical-Bayes shrinkage. Pure stdlib |
| `filters.py` | The pipeline: score, shrink, deep-check, filter, allocate |
| `exemptions.py`, `tax_exempt.json` | Which items pay no GE tax |
| `api.py` | Wiki API client: bulk endpoints, 30s poll floor, daily `/mapping` cache |
| `archive.py`, `collect.py` | The private tick archive and its poller |
| `journal.py` | Flip log and calibration diagnostics |
| `app.py` / `cli.py` | Dashboard / terminal table |
| `docs/index.html` | Browser app — **runs the older model**, see below |

```bash
python3 -m unittest test_engine test_stats test_filters test_journal
```

`engine.py` and `stats.py` deliberately import nothing outside the standard
library, so the terminal tool and the whole test suite run without the venv.

### The browser app is stale

`docs/index.html` carries its own JavaScript port of the ranking math, because
it runs with no Python available. It has **not** been updated for the rebuild:
it still exempts only the bond from tax, divides by a flat four hours, applies
the nine-factor multiplicative chain, and has no shrinkage, no fill-time model
and no alchemy floor. Its numbers will disagree with the Python tools, and the
Python ones are the ones to trust.

Porting it is a self-contained piece of work. Until that happens the honest
options are to port it or to stop publishing it.

## API etiquette

The wiki's [acceptable use policy](https://prices.runescape.wiki) asks for a
descriptive User-Agent and no per-item polling. The Python client sets one — if
you fork or deploy this, change `USER_AGENT` in `api.py` so the wiki team can
reach *you*. `/timeseries` is per-item and is only ever called for a shortlist,
cached 30 minutes; the bulk routes are polled no faster than their own cache
TTLs, which is what `collect.py` respects too.

v1 and v2 of the API return byte-identical payloads on every route used here,
so the client stays on v1 with the base URL configurable.

Not affiliated with Jagex or the OSRS Wiki. Prices are estimates — flip at your
own risk.
