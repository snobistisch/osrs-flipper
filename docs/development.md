# Development

Work from the repository root and follow [AGENTS.md](../AGENTS.md). Setup and
application usage are in the [README](../README.md).

## Checks

Install Python 3.9+ and Node.js 22+, then run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/ruff check .
.venv/bin/python -m unittest -q
node --test tests/browser.test.cjs
.venv/bin/python -m backtest smoke
.venv/bin/python -m compileall -q -x '/\.venv/' .
.venv/bin/python -m pip check
```

On Windows, replace `.venv/bin/python` and `.venv/bin/ruff` with their
`.venv\Scripts\` equivalents. GitHub Actions runs lint, dependency checks,
Python tests, browser tests, and compilation on Python 3.9 and 3.13 with
Node 22.

There is no separate build step or configured static type checker. Ruff checks
correctness rules for imports, syntax, and undefined names without imposing a
repository-wide formatting migration.

## Test layout

All tests live in `tests/`. The package marker keeps default unittest discovery
working from the repository root. To run one module:

```bash
.venv/bin/python -m unittest tests.test_engine -v
```

| Tests | Coverage |
|---|---|
| `test_engine.py`, `test_stats.py`, `test_filters.py`, `test_merch.py` | Pricing, tax, statistics, limits, selection, and signals |
| `test_fill_time.py` | Fill-time distribution: P50/P80/P90 bands, completion odds, sequential legs, sizing, consistency, and the censored journal backtest |
| `test_api.py`, `test_agent.py`, `test_journal.py` | API behavior, agent output/state, and trade outcomes |
| `test_audit.py` | Regression cases for invalid data, arithmetic, archive integrity, and persistence |
| `test_docs_port.py` | Shared Python/JavaScript constants and static browser guards |
| `test_parity.py` | Executable Python/JavaScript parity: tax, fees, fills, scores, shrinkage, history, execution choice, rounding, reach, replay, portfolio selection, and the whole funded plan on a slice of real prices, equal to the gp (needs Node; skipped without it) |
| `test_selection.py` | Measured reach, offer replay, slot-and-bank selection against brute force, the automatic profile, deep-check targeting and CLI overrides |
| `test_backtest.py` | The backtest harness: no look-ahead, simulator rules, buy limits, balanced books, deterministic output |
| `browser.test.cjs` | Executable browser behavior and compilation of the complete inline script |

Install `requirements-dev.txt` (numpy and ruff) to run the complete suite. The
Node tests use the built-in test runner and need no npm dependencies.

## Two implementations

Python interfaces share `engine.py`, `stats.py`, and `filters.py`. The standalone
browser app carries its own JavaScript implementation in `docs/index.html`.
Update both when changing formulas or shared configuration. Static guards
check constants and key structures. `test_parity.py` runs the same inputs
through both implementations and compares the results; extend it whenever a
shared formula changes. Plan selection is shared too:
`filters.automatic_profile` and `automaticFilterProfile` are one policy, and
`PlanParityTests` runs both on the fixture (`tests/js_plan.cjs` drives the
page's own code under Node). Two details bite when porting: Python's
`round()` rounds halves to even where `Math.round` rounds them up, so use
`engine.round_half_up`; and a float product such as `45 * (1 - 1/3)` is not
30. Saved reservations and the bank-risk slider exist only in the browser;
the CLI has `--bank-risk`.

`backtest/` may import numpy; `engine.py`, `stats.py`, `filters.py`, the CLI
and the agent stay on the standard library. `tests/fixtures/backtest_panel.npz`
is a slice of real OSRS Wiki price history, cut with
`python3 -m backtest fixture`; the numbers a run on it prints mean nothing.
Before changing the selection policy, run the backtest on the tuning period
and compare against the `policy` result of the previous commit and against
`random`; evaluate on the held-out period once, after the change is final
([method](audit-2026-11.md)).

Keep browser requests compatible with CORS: do not add a `User-Agent` header.
The Python client supplies one; customize `USER_AGENT` in `api.py` when deploying
a fork so the API operator can identify your client.

Preserve existing storage formats and the
[agent output contract](../skills/osrs-flipper/SKILL.md). Missing market values
are unknown (`null`), not zero. Never replace unreadable durable data with an
empty portfolio. See [operations](operations.md) for storage and recovery.

## Manual verification

For UI changes, serve `docs/` locally and check both desktop and narrow mobile
layouts. Exercise keyboard navigation, refresh failures, saved offers, account
and strategy switches, and rapid chart changes. The Node suite tests browser
logic in a harness; it does not replace visual or accessibility checks in a
real browser.

Model parameters remain assumptions until calibrated against recorded fills.
See [model notes](model.md) and the historical
repository audits of [September](audit-2026-09-13.md),
[October](audit-2026-10-01.md) and [November 2026](audit-2026-11.md) for
known limitations.
