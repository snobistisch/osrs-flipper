# OSRS Grand Exchange Flipper

Find Grand Exchange flips you can actually execute. Live prices from the
[OSRS Wiki real-time price API](https://prices.runescape.wiki), ranked by
**expected gp per offer slot per hour** — not by the margin on the screen.

**[▶ Open the flipper](https://snobistisch.github.io/osrs-flipper/)** — runs in
your browser, nothing to install. Same model as the Python tools; see
[Two implementations](#two-implementations) for how they are kept in step.

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

### 2. You have to get to the front of the queue, and you are not alone in it

How many offers you are queued behind used to be a constant: four, on every
item in the game. That was the worst assumption in the model. On fire runes it
handed you a quarter of 1.7 million units an hour and reported a two-hour round
trip on a flip that takes a day, which put bot-supplied runes at the top of the
ranking where they do not belong.

The crowd is now sized per item, from data already in hand. Every participant
is capped at the buy limit per window, so producing the observed volume takes
at least `volume_per_window / buy_limit` of them. Fire runes: 6.7m units a
window against a 50,000 limit, so 134 participants at minimum, not four.
Limpwurt root comes to 9.5, and the floor of four keeps quiet items where they
were.

The formula has one property that makes it believable rather than merely
pessimistic: where the crowd term binds, your share is
`buy_limit / volume_per_window`, so your fill rate is exactly one buy limit per
window. **On a crowded item you cannot beat your own buy limit** — which is the
answer an hour of watching the Grand Exchange gives you. Conceding spread still
jumps the queue, so this only bites where it should: items whose spread is a
single gp and where there is nothing to concede.



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

A twelvefold gap produced by nothing but the price grid. Fed into the adverse
selection discount at four to eight times the drift, it removed most of the
expected profit from every cheap item in the game and left expensive ones
untouched — which is how the top of the ranking filled with 1%-margin flips on
dear items. Salmon printed a five-minute mid of 28.5 against an hour of 25.5:
three gp on a 26 gp item, read as 11.8% of momentum, discounting the flip to
27% of its profit. Drift is now measured net of one tick, so the same 1 gp
wobble reads as nothing whether the item costs 10 gp or 10,000.

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

### 8. A year is a different question from an hour

Everything above prices a round trip measured in hours. Holding an item for
weeks is a different bet with a different unit, and `merch.py` scores it
separately. The two numbers never get added together: an item can be a terrible
flip (nobody trades it, the spread is one gp) and an excellent hold (its price
has doubled in a year).

- **Trends are fitted on log prices.** The slope is then a growth *rate* that
  means the same thing on a 5 gp herb and a 60m wand, and R² is comparable
  across items rather than dominated by absolute scale.
- **Most apparent trends are not trends.** This is the headline result and it
  is measured, not assumed. A year of daily prices with no drift in it at all
  still wanders far enough to look like a 40%/yr riser. Simulating driftless
  random walks: `|t| >= 1.5` labels 61% of pure noise a trend, `|t| >= 2.5`
  labels 42%, `|t| >= 5.0` labels 16%. The curve is scale-free — repeat it at
  1.2%, 2.1% or 3.5% daily volatility and it moves under a point.

  So the threshold is 5.0, and the honest consequence is that several
  watchlist items with headline rates near +50%/yr are reported SIDEWAYS. Every
  row also carries a **noise probability**: the share of trendless items that
  would look at least this trendy. Read that column before the trend column.
  "+57%/yr, R² 0.71" sounds like a finding; "41% of items with no trend look
  like this" is the same row telling you it is not one.
- **Textbook t-statistics do not apply to prices.** Today's distance from the
  trend line is nearly yesterday's, so OLS standard errors are far too small —
  a pure random walk comes out at `|t|` of thirty. The slope's t is widened for
  AR(1) residual autocorrelation before anything is concluded from it.
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

## Filters no longer decide what gets scored

The old pipeline was a chain of gates: too stale, too thin, ROI too low, no
undercut room — rejected, in that order, before anything deeper could speak for
the item. A filter that only subtracts cannot find edge; it can only shorten
the list.

Now only structural facts reject: no mapping entry, a missing side of the quote,
nothing traded on one side, a margin that cannot survive the tax, or a single
unit you cannot afford.

One of those gates was still lying. `/latest` gives the last trade per side, and
when both sides print at the same price — one trade that crossed, or two prints
from moments when the price had moved — the conservative blend of the last
print and the volume-weighted reference returns buy ≥ sell, and the item is
rejected as having no margin. Measured on live data, that discarded 248
free-to-play items in one snapshot, and the hour's averages showed a real spread
on 88 of them. Two prints showing no spread are not evidence that there is no
spread; they are the absence of evidence. The averages measure both sides over
many trades and are now used when the blend collapses, guarded only by the two
sources still describing the same market. Everything else is scored, and the filters in the
sidebar and on the command line hide rows **after** scoring and shrinkage — so
narrowing the view never reorders what is left.

## Run it

Nothing to install: the [hosted
version](https://snobistisch.github.io/osrs-flipper/) is one self-contained
HTML file and runs the same ranking. Enter a budget and it goes, and the first
thing it shows is one card per offer slot: what to buy, how many, what to list
it at, and how much of the bank to commit. The table underneath is the working
out.

It is laid out as a trading terminal wearing RuneScape's clothes: the palette,
the bevels and the gold Cinzel headings stay, while the data is set the way a
dealing screen sets data — monospace figures that line up digit for digit, tight
rows, a status line carrying the clock and whether the feed is still live, and a
tape of the busiest items along the top. `F1`/`F2`/`F3` switch tabs, `R`
refreshes, `Esc` closes the detail panel. Three tabs:
**Flip** ranks by gp per slot per hour, **Merch** pulls a year of daily prices
for a watchlist and is the only view that fetches per item (once, on demand,
cached six hours in IndexedDB), **Crash** reads the deep-checked candidates for
price dislocation.

For the local tools:

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
`--min-depth`) all default to off, as does `--no-bots`, which hides
bot-supplied free-to-play staples — under 100 gp, buy limit over 10,000. They
rank well and clear fast; the supply curve is a script that answers a price
rise by producing more. Like every filter here it hides rows after scoring, so
turning it on never reorders what is left. `--mode crash` reads the same fetch for
price dislocation instead of throughput; the long-horizon merch view lives in
`agent.py merch`, because it needs a different set of requests.

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

## Run it from an agent

`cli.py` prints for a person. `agent.py` prints for a program, and — the part
that makes it usable — prints *nothing at all* when there is nothing to say.

```bash
python3 agent.py flips --json --capital 1.5m --slots 3
python3 agent.py merch                 # the watchlist over a year
python3 agent.py watch                 # new signals only; usually silent
python3 agent.py portfolio list
python3 agent.py status                # cache ages, archive, last watch run
```

Stdlib only, so it runs from cron with no virtualenv activated. State lives in
`~/.osrs-flipper/` (override with `--state-dir`), outside the repo, so a
`git pull` cannot wipe your positions.

### Why `watch` is quiet

An agent wired to a chat app is only worth having while its messages are still
worth opening. `watch` holds state between runs and speaks only when something
crossed a line it had not already crossed: a crash that deepens from 40% to
70% alerts twice, a crash that sits at 55% for a week alerts once. Below half
the alert threshold an item resets and may fire again later, so hovering around
the line does not flap. If the API has been unreachable for three consecutive
runs it says so — a broken cron should not look like a quiet market.

### Hermes Agent

Copy `skills/osrs-flipper/` into your skills directory, then:

```bash
hermes cron create "every 4h" "Run the osrs-flipper watch command. If it prints nothing, reply exactly [SILENT] and send no message. Otherwise summarise each signal in one line, in plain language, with the item name and price. Do not add advice." --script ~/osrs-flipper/agent.py --skill osrs-flipper --deliver telegram
```

A daily digest instead of alerts:

```bash
hermes cron create "0 9 * * *" "Run: python3 agent.py merch --json. Report only items whose trend noise_probability is below 0.20, plus anything carrying a crash or supply badge. If none qualify, reply [SILENT]." --skill osrs-flipper --deliver telegram
```

Keep the tick archive filling on its own schedule:

```bash
hermes cron create "every 30m" "Run: python3 collect.py --once. Reply [SILENT] unless it reports an error." --deliver local
```

The skill file is what stops the agent inventing prices when a command fails,
and what tells it to read `noise_probability` before the headline trend number.
Read it before changing the output formats — they are a contract.

### Host it on your own machine

The browser app is a single file and needs no server, so opening
`docs/index.html` is enough. To reach it from your phone on the same network:

```bash
python3 -m http.server 8000 --directory docs
```

There is no backend to deploy and nothing to configure. Every request goes from
your browser straight to the wiki API.

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
| `merch.py` | Long-horizon signals: trend, crash, supply crunch. Pure stdlib |
| `filters.py` | The pipeline: score, shrink, deep-check, filter, allocate |
| `exemptions.py`, `tax_exempt.json` | Which items pay no GE tax |
| `api.py` | Wiki API client: bulk endpoints, 30s poll floor, disk-cached history |
| `archive.py`, `collect.py` | The private tick archive and its poller |
| `journal.py` | Flip log and calibration diagnostics |
| `app.py` / `cli.py` | Dashboard / terminal table |
| `agent.py` | JSON and cron output for an agent; silent by default |
| `skills/osrs-flipper/` | Hermes skill: how an agent should read the output |
| `docs/index.html` | Browser app — self-contained, no build step, no deps |

```bash
python3 -m unittest test_engine test_stats test_merch test_filters test_journal test_agent test_docs_port
```

`engine.py` and `stats.py` deliberately import nothing outside the standard
library, so the terminal tool and the whole test suite run without the venv.

### Two implementations

`docs/index.html` carries its own JavaScript port of `engine.py`, `stats.py`
and `filters.py`, because it has to run with no Python available. That
duplication is the price of a zero-install version, and it is a real
maintenance hazard: the port went stale once already, and the only thing
guarding it was a README line saying "change it in both".

`test_docs_port.py` now guards the parts that rot silently — the tax-exempt
list, every calibration constant, the history window, the raid-unique and
watchlist id lists, the merch windows, the measured noise curve, and the
absence of functions the rebuild deleted. It also asserts that the port never
sets a `User-Agent` header: browsers forbid scripts from setting one, and the
custom header trips a CORS preflight the wiki answers with 400, so "add a
descriptive User-Agent like the Python client does" takes the whole page down.

A Python test cannot execute the JavaScript, so formula changes still have to
be made by hand in both files; what it catches is the class of drift that
produces plausible numbers that are quietly wrong.

Checked against live data, the two agree to within a fraction of a percent on
the pre-shrinkage score, the remaining gap being that they poll `/latest`
seconds apart. Shrunken scores drift slightly more, because shrinkage depends
on the whole cross-section and the two runs see a marginally different one.

## API etiquette

The wiki's [acceptable use policy](https://prices.runescape.wiki) asks for a
descriptive User-Agent and no per-item polling. The Python client sets one — if
you fork or deploy this, change `USER_AGENT` in `api.py` so the wiki team can
reach *you*. `/timeseries` is per-item and is only ever called for a shortlist,
cached 30 minutes; the bulk routes are polled no faster than their own cache
TTLs, which is what `collect.py` respects too.

v1 and v2 of the API return byte-identical payloads on every route used here,
so the client stays on v1 with the base URL configurable.

### The 24h series does not mean what it looks like

Worth knowing before you trust a volume number off `/timeseries?timestep=24h`.
Cross-checked against the same item at `6h` on 2026-07-26: for every historical
day, the 24h bucket's **volume is the first 6h bucket of that day**, not the
day's total, which is roughly four times larger. The most recent bucket is the
exception and does carry the whole day.

Prices behave the same way and that is harmless — a consistent daily sample,
within about 2% of the daily mean, which is fine to fit a trend through. The
volumes are not comparable, and leaving the final bucket in reports an 8x
volume spike on every item in the game simultaneously. That is exactly what the
first live run of the crash scanner did. Every volume calculation in `merch.py`
drops the last bucket for this reason (`VOLUME_SKIP_LAST`), which costs a day
of latency on the volume signals and is the only way to compare like with like.

Not affiliated with Jagex or the OSRS Wiki. Prices are estimates — flip at your
own risk.
