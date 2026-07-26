# OSRS Grand Exchange Flipper

**[▶ Open the flipper](https://snobistisch.github.io/osrs-flipper/)** — runs in
your browser, nothing to install.

Find Grand Exchange flips you can actually execute. Live prices from the
[OSRS Wiki real-time price API](https://prices.runescape.wiki), filtered for
data freshness and traded volume, with margins shown after GE tax and capped
by buy limits and your budget.

## Why the margins here are smaller than other tools show

Most margin tools read the `/latest` endpoint literally. That endpoint reports
the last single trade on each side of the book, so one outlier offer can make a
dead item look like a 40% margin.

Averaging fixes less than it looks. Take a real case: lobsters showed a last
instant-sell of 34 gp, and the 5-minute average agreed — but that average rested
on **13 units**, while 36,170 units traded at 58 gp over the same hour. Buying
lobsters at 34 was not something you could actually do.

So the reference price for each side of the book is the 5-minute and 1-hour
average **weighted by how much traded in each**. A busy 5-minute bucket moves
the estimate; a 13-unit blip barely does. The final estimate then takes the
pessimistic side: you buy at the higher of (last instant-sell, reference low)
and sell at the lower of (last instant-buy, reference high).

The result is a shorter list than other flippers show. That's the point — the
entries that survive are ones where both sides of the book have real volume
behind them.

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
python3 cli.py --capital 1000000
```

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
- Qty/4h = min(buy limit, hourly thin-side volume ×4, budget ÷ buy price).
  The thin side of the book bounds throughput: a flip needs both a seller to
  fill your buy and a buyer to fill your sell.
- Score = expected 4h profit, halved for every 10 minutes of quote age.
  Stale quotes mean dead items, not free money.

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
