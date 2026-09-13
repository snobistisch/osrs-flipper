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
.venv/bin/python -m compileall -q -x '/\.venv/' .
.venv/bin/python -m pip check
```

On Windows, replace `.venv/bin/python` and `.venv/bin/ruff` with their
`.venv\Scripts\` equivalents. GitHub Actions runs lint, Python tests, browser
tests, and compilation on Python 3.9 and 3.13 with Node 22.

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
| `test_api.py`, `test_agent.py`, `test_journal.py` | API behavior, agent output/state, and trade outcomes |
| `test_audit.py` | Regression cases for invalid data, arithmetic, archive integrity, and persistence |
| `test_app.py` | Streamlit landing page and dashboard smoke tests |
| `test_docs_port.py` | Shared Python/JavaScript constants and static browser guards |
| `browser.test.cjs` | Executable browser behavior and compilation of the complete inline script |

The Streamlit tests skip when dashboard dependencies are missing. Install
`requirements-dev.txt` to run the complete suite. The Node tests use the built-in
test runner and need no npm dependencies.

## Two implementations

Python interfaces share `engine.py`, `stats.py`, and `filters.py`. The standalone
browser app carries its own JavaScript implementation in `docs/index.html`.
Update both when changing formulas or shared configuration. Static guards
check constants and key structures; executable tests cover critical behavior,
but do not prove complete numerical parity of every statistical model.

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
[repository audit](audit-2026-09-13.md) for known limitations.
