# OSRS Flipper

Plan Grand Exchange flips using live OSRS Wiki prices, estimated profit after
tax, buy limits, fill estimates, and risk-aware slot allocation.

**[Open the app](https://snobistisch.github.io/osrs-flipper/)** ·
[Model](docs/model.md) · [Local tools](docs/operations.md) ·
[Development](docs/development.md)

## Using the app

1. Enter your available bank and choose **Members** or **Free-to-play**.
2. Choose **Active** for trading while playing, or **Overnight** for resting
   buy offers while away.
3. Review each suggested item's buy price, quantity, sell price, estimated
   profit, and risk before placing the offer in-game.
4. Save offers to track them. Saved commitments reserve bank across strategy
   changes; keep their status up to date as you trade.

The planner uses eight GE slots for Members and three for Free-to-play.
Active ranks expected profit per occupied slot-hour. Overnight estimates
inventory bought while away and a separate selling phase after you return.
**Merch** shows longer-term watchlist signals; **Crash** highlights price
dislocations. The app provides guidance; all in-game orders are manual.

Prices come from reported trades, not a public order book. Fill times,
probabilities, and profits are estimates. The model includes integer GP
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

### Python dashboard

Requires Python 3.9 or later. Run from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

These commands use macOS/Linux virtual-environment paths. On Windows, use
`.venv\Scripts\python.exe` and `.venv\Scripts\streamlit.exe` instead.

### Command line and agent output

The CLI and agent use only the Python standard library:

```bash
python3 cli.py --capital 1m --account members --strategy active
python3 cli.py --capital 20m --strategy overnight --overnight-hours 8
python3 agent.py flips --json --capital 1.5m
python3 agent.py portfolio list
```

Use `--account free-to-play` for the F2P profile and `--help` for available
options. The browser applies additional selection gates, while Python display
filters default to off; their portfolios can differ despite a shared model.

For the tick collector, trade journal, watch alerts, and storage details, see
[Local tools and storage](docs/operations.md).

## Repository map

| Path | Purpose |
|---|---|
| `docs/index.html` | Standalone browser app served by GitHub Pages |
| `engine.py`, `stats.py`, `filters.py`, `merch.py` | Calculations, statistics, selection, and long-horizon signals |
| `api.py`, `exemptions.py`, `tax_exempt.json` | Market data and tax exemptions |
| `app.py`, `cli.py`, `agent.py` | Dashboard, terminal, and agent interfaces |
| `archive.py`, `collect.py`, `journal.py`, `storage.py` | Local history, outcomes, and safe persistence |
| `tests/` | Python regression tests and executable browser tests |
| `docs/*.md` | Model, operations, development, and historical audit notes |
| `skills/osrs-flipper/` | Agent usage and output contract |
| `.github/workflows/` | Automated repository checks |

## Development

With the virtual environment above and Node.js 22 or later:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/ruff check .
.venv/bin/python -m unittest -q
node --test tests/browser.test.cjs
```

GitHub Actions checks Python 3.9 and 3.13. There is no npm build. Calculation
changes need matching Python and JavaScript updates; see
[Development](docs/development.md) for test coverage and maintenance guidance.
The [September 2026 audit](docs/audit-2026-09-13.md) records fixes and remaining
limitations (in Dutch).

Not affiliated with Jagex or the OSRS Wiki.
