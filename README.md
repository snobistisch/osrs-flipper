# OSRS Grand Exchange Flipper

Find Grand Exchange flips you can actually execute. Live prices from the
[OSRS Wiki real-time price API](https://prices.runescape.wiki), filtered for
data freshness and traded volume, with margins shown after GE tax and capped
by buy limits and your budget.

Most margin tools read the `/latest` endpoint literally. That endpoint reports
the last single trade on each side of the book, so one outlier offer can make
a dead item look like a 40% margin. This tool prices conservatively instead:
your buy estimate is the higher of (last instant-sell, 5-minute volume-weighted
average) and your sell estimate the lower of (last instant-buy, 5-minute
average), with the 1-hour average standing in when a 5-minute bucket had no
trades. A single weird trade cannot inflate a margin.

## Run it

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
| `api.py` | Wiki API client: bulk endpoints only, 30s poll floor, daily disk cache for `/mapping` |
| `engine.py` | Pure math: tax, margins, volume, score. No I/O |
| `filters.py` | The gate pipeline that turns raw quotes into ranked flips |
| `app.py` | Streamlit dashboard |
| `cli.py` | Terminal table |
| `journal.py` | Flip log |

Tests: `python3 -m unittest test_engine test_filters test_journal`

## API etiquette

The wiki's [acceptable use policy](https://prices.runescape.wiki) asks for a
descriptive User-Agent and no per-item polling. This client fetches bulk
endpoints only, at most once per 30 seconds, and caches item metadata for a
day. If you fork or deploy this, change `USER_AGENT` in `api.py` so the wiki
team can reach *you*.

Not affiliated with Jagex or the OSRS Wiki. Prices are estimates — flip at
your own risk.
