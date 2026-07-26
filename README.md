# OSRS Grand Exchange Flipper

**[▶ Open the flipper](https://snobistisch.github.io/osrs-flipper/)** — runs in
your browser, nothing to install.

Find Grand Exchange flips you can actually execute. Live prices from the
[OSRS Wiki real-time price API](https://prices.runescape.wiki), ranked by
**expected gp per offer slot per hour** — not by the margin on the screen.

## The strategy

A quoted margin is not profit. It is profit *if* both legs of the flip fill at
the quoted prices, and nothing guarantees that. Four things stop it, and each
one is a discount applied to the quoted number.

### 1. You have to get to the front of the queue

The Grand Exchange matches offers **on price first, then on offer age**. At the
same price, an offer placed days ago has near-absolute priority over yours. So
there are exactly two ways to get filled: outbid the queue, or wait in it.

This is why flipping air runes is a mistake. Quoted at 5 buy / 6 sell, that
1 gp margin reads as a 20% return across a 50,000 buy limit. But to jump the
queue you would have to buy at 6 and sell at 5 — a guaranteed loss. You have
**zero room to compete**, so you sit behind thousands of offers and bots for a
margin of one coin.

Every item therefore carries an **undercut room** number: how many gp of price
improvement it can absorb on each side while still profiting. Leather at
173/192 has 7 gp of room — bidding 180 to sell at 185 still clears 2 gp after
tax, so you can buy priority. Air runes have 0. Flips with no room are filtered
out by default, and score 15% of their quoted profit when you switch them on.

### 2. Your offer fills when you least want it to

A resting buy offer fills fastest exactly when the price is falling — someone is
dumping into it — and then your sell leg is stranded above the market. Passive
orders are selected against. The tool measures drift between the 1-hour and
5-minute averages and penalises a falling market harder than a rising one,
because you are the one holding inventory between the two legs.

### 3. Slots are scarcer than gold

Free-to-play has **3** GE slots, members **8**. You cannot run fifty flips at
once, so "profit if I put my entire bank into this one item" is the wrong
question. Your budget is divided across your slots, and the ranking is by what
one slot earns per hour.

### 4. The last print is not the market — and neither is a spike

A few hundred salmon dumped at 30 gp in the last minutes reads as "buy at 30"
to every intraday number, while two weeks of sellers accepted ~40. The mirror
image is the **manipulation trap**: an item pumped above its normal level shows
a juicy margin exactly while whoever pumped it is waiting to dump on you.
Flipping is market making — earning a spread on stable, liquid items inside an
established range — not trend-chasing, and the guides are unanimous: consistent
volume, realistic margins, and "if a margin looks too good to be true, it
probably is."

So the top 15 candidates get a second pass against **14 days of 6h history**
(`/timeseries`, per-item, cached 30 minutes — never swept across all items):

- **Fill probability in size**: what share of two weeks' volume traded at your
  prices, measured *relative to the market of the moment* — a dump is a dump
  whenever it happened, but a genuine riser is not punished for being above
  last week. A price nobody ever traded at keeps 5%.
- **Price level**: how far today's quote sits above the item's **14-day
  median**. The median is robust — a few pumped buckets barely move it — so a
  spike shows up as elevation, and elevation is discounted hard (down to 10%).
  Game commodity supply and demand barely move, so shocks revert; buying above
  the median puts that reversion against you. Below the median costs nothing.
- **Stability**: the median swing around that median. A flip is a round trip
  holding inventory in between; jumpy items get discounted (down to 30%).
- **Momentum**: decline is penalised (you hold falling inventory). A rise
  earns **no bonus**: from price data alone, an update-driven demand shift and
  a merch-clan pump are identical. The tool waits for a new level to settle —
  at which point the level and stability factors like it on their own.
- Items with under 8 traded buckets are flagged and left on intraday numbers.

### The intraday prices themselves

Most tools read `/latest` literally — the last single trade per side, which one
outlier can set anywhere. Averaging alone does not fix it: lobsters once showed
a 5-minute average of 34 gp resting on **13 units**, while 36,170 units traded
at 58 gp that hour. So the intraday reference per side is the 5-minute and
1-hour average **weighted by how much traded in each**, and the estimate takes
the worse of that and the last real trade.

The result is a much shorter list than other flippers show. That is the point.

## Run it locally

The web version needs nothing. To run the Python tools:

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

Enter your flipping budget (`250k`, `1.5m`, `1,000,000` — whatever you have)
and the dashboard ranks flips that fit it. F2P items only by default; members
items are a checkbox away.

Terminal version, same numbers:

```
python3 cli.py --capital 1m --slots 3
```

Add `--min-depth 0` to see the flips with no undercut room and watch them rank
at the bottom, `--members` for members items, `--slots 8` if you have them.

## Log your flips

The point of predictions is checking them. `journal.py` keeps a SQLite log of
what you actually bought and sold:

```
python3 journal.py open --name "Steel bar" --qty 1000 --buy 571 --predicted 16
python3 journal.py close 1 --sell 598
python3 journal.py stats
```

`stats` compares predicted margins against realised profit after tax.

## How the numbers work

- Tax (29 May 2025 rules): seller pays 2% per item, rounded down, capped at
  5m. Items under 50 gp are untaxed; bonds are exempt.
- Margin = sell estimate − tax − buy estimate.
- Qty/4h = min(buy limit, hourly thin-side volume ×4, slot budget ÷ buy price).
  The thin side of the book bounds throughput: a flip needs both a seller to
  fill your buy and a buyer to fill your sell.
- Expected gp = margin × qty × queue × drift × freshness × 14-day fill ×
  price level × stability × momentum, where freshness halves for every
  10 minutes of quote age.
- EV/slot/hour = expected gp ÷ 4, the buy-limit window. This is the ranking.

The discount factors are a model, not measurements. The shape of each is argued
above and the constants are tuned by judgement; `journal.py` exists so you can
check them against what you actually realise.

## Project layout

| File | Role |
|---|---|
| `docs/index.html` | The hosted web app — self-contained, no build step, no dependencies |
| `api.py` | Wiki API client: bulk endpoints only, 30s poll floor, daily disk cache for `/mapping` |
| `engine.py` | Pure math: tax, margins, volume, score. No I/O |
| `filters.py` | The gate pipeline that turns raw quotes into ranked flips |
| `app.py` | Streamlit dashboard |
| `cli.py` | Terminal table |
| `journal.py` | Flip log |

Tests: `python3 -m unittest test_engine test_filters test_journal`

The web app carries its own copy of the ranking math, ported from `engine.py`
and `filters.py`, because it runs with no Python available. The two are kept
in step deliberately; when you change a formula, change it in both.

## API etiquette

The wiki's [acceptable use policy](https://prices.runescape.wiki) asks for a
descriptive User-Agent and no per-item polling.

The Python client sets one — if you fork or deploy this, change `USER_AGENT` in
`api.py` so the wiki team can reach *you*. The browser app **cannot**: browsers
forbid scripts from setting `User-Agent`, and the wiki API rejects a preflight
that tries. It complies with everything else instead — bulk endpoints only,
never per-item polling, at most one refresh per 30 seconds, and item metadata
cached for a day. The API's `Access-Control-Allow-Origin: *` header is what
makes a browser client possible at all.

Not affiliated with Jagex or the OSRS Wiki. Prices are estimates — flip at
your own risk.
