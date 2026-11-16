# OSRS Flipper

Plan Grand Exchange flips using live OSRS Wiki prices, estimated profit after
tax, buy limits, fill estimates, and risk-aware slot allocation.

**[Open the app](https://snobistisch.github.io/osrs-flipper/)** ·
[Model](docs/model.md) · [Local tools](docs/operations.md) ·
[Development](docs/development.md)

## Using the app

1. Enter your available bank and choose **Members** or **Free-to-play**.
2. Choose **Active** for trading while you watch the GE, **Away** for
   resting buy offers until your next check (1–12 hours, overnight included),
   or **Max profit** for the flips that make the most per offer, however long
   they take.
3. Review each suggested item's buy price, quantity, sell price, estimated
   profit, and risk before placing the offer in-game.
4. Save offers to track them. Saved commitments reserve bank across strategy
   changes; keep their status up to date as you trade.

The planner uses eight GE slots for Members and three for Free-to-play. A
flip gets bank only if its exact offer, replayed on the item's own last day
of 5-minute trading, made money in both halves of that day; the funded sizes
are then chosen under the slot and the bank limit together, and the plan says
which of the two decided it. That can leave slots or part of the bank
unused. Active ranks that replayed profit per occupied slot-hour while you
watch. Its order size is a setting: `careful` (the default, and the only
one tested on held-out data) sizes each offer on a queue share of the volume
that trades through its price, `balanced` and `large` on 15% and 30%. Larger
orders earn more if your offers fill quickly and lose more if they do not
([order size](docs/model.md#order-size); `--order-size` in
`cli.py` and `agent.py`). Away
(next check in 1–12 hours, overnight included) estimates inventory bought
while you are gone — including bids under today's price on items that
measurably bounce back (a mean-reversion test with about 5% false positives on
random walks) — and a separate selling phase after you return.
Max profit ranks risk-adjusted expected profit per flip — one buy offer of at
most one buy limit, relisted as soon as it fills — with a 24-hour deadline; a
slow flip can rank first, and its time band says how slow.
**Merch** shows longer-term watchlist signals; **Crash** highlights price
dislocations. The app provides guidance; all in-game orders are manual.

Prices come from reported trades, not a public order book. Fill times,
probabilities, and profits are estimates: the replay is measured on public
trades, and how much of the passing volume reaches *your* offer is an
assumption until you log real offers (see
[what the backtest can and cannot show](docs/audit-2026-11.md)). An Active flip shows a time band —
typical (median), 80% and 90% — with the chance the whole quantity is bought
and sold within the window, and a time after which an untouched offer should
be re-checked and repriced. None of these is a guarantee. The model includes integer GP
rounding, a capped GE tax, exemptions, and shared buy limits. See the
[model notes](docs/model.md) for assumptions and calibration limits.

Saved browser data stays in that browser and origin. It does not synchronize
with another device or the Python tools.

## Run locally

The browser app is a single HTML file with no build step or package install:

```bash
git clone https://github.com/snobistisch/osrs-flipper.git
cd osrs-flipper
python3 -m http.server 8000 --directory docs
```

Open [localhost:8000](http://localhost:8000). The browser requests market data
directly from the OSRS Wiki API.

### Command line and agent output

The CLI and agent need Python 3.9 or later and use only the standard
library. Run them from the repository root:

```bash
python3 cli.py --capital 1m --account members --strategy active
python3 cli.py --capital 20m --strategy away --overnight-hours 8
python3 cli.py --capital 20m --strategy profit
python3 agent.py flips --json --capital 1.5m
python3 agent.py portfolio list
```

Use `--account free-to-play` for the F2P profile and `--help` for available
options. The CLI and the agent apply the same selection policy as the
browser, so the same market gives the same plan; a display-filter flag
replaces one of its gates.

### Backtest

A walk-forward backtest replays the planner on real price history: decide on
data up to a moment, realise the offers on what traded afterwards. It needs
numpy and about 2.5 hours for the first download, which is resumable:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m backtest fetch      # 35 days of 5m + 90 days of 1h buckets into data/
.venv/bin/python -m backtest build      # raw buckets -> data/panel
.venv/bin/python -m backtest run --period tune       # or: --period holdout
.venv/bin/python -m backtest smoke      # seconds, on the committed fixture
```

`run` writes a result file and a Markdown report under `data/results/`;
`--method`, `--strategy`, `--capital` and `--account` narrow it. Every result is produced under six fill assumptions, because
public trades cannot say what a private offer would have filled. Method,
results and limits are in the
[November 2026 audit](docs/audit-2026-11.md) (in Dutch).

For the tick collector, trade journal, watch alerts, and storage details, see
[Local tools and storage](docs/operations.md).

## Repository map

| Path | Purpose |
|---|---|
| `docs/index.html` | Standalone browser app served by GitHub Pages |
| `engine.py`, `stats.py`, `filters.py`, `merch.py` | Calculations, statistics, selection, and long-horizon signals |
| `api.py`, `exemptions.py`, `tax_exempt.json` | Market data and tax exemptions |
| `cli.py`, `agent.py` | Terminal and agent interfaces |
| `archive.py`, `collect.py`, `journal.py`, `storage.py` | Local history, outcomes, and safe persistence |
| `backtest/` | Walk-forward backtest on real price history |
| `tests/` | Python regression tests and executable browser tests; `tests/fixtures/` holds a slice of real price history |
| `docs/*.md` | Model, operations and development notes, and the November 2026 audit |
| `docs/backtest-2026-11/` | Raw tables of the November 2026 backtest |
| `requirements-dev.txt` | numpy for the backtest, ruff for linting |
| `skills/osrs-flipper/` | Agent usage and output contract |
| `.github/workflows/` | Automated repository checks |

## Development

With the virtual environment above and Node.js 22 or later:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/ruff check .
.venv/bin/python -m unittest -q
node --test tests/browser.test.cjs
.venv/bin/python -m backtest smoke
```

GitHub Actions checks Python 3.9 and 3.13. There is no npm build. Calculation
changes need matching Python and JavaScript updates; see
[Development](docs/development.md) for test coverage and maintenance guidance.
The [November 2026 audit](docs/audit-2026-11.md) records the backtest, its
results and its limitations (in Dutch).

Not affiliated with Jagex or the OSRS Wiki.
