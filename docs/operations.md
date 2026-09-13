# Local tools and storage

Run these commands from the repository root with Python 3.9 or later. See the
[README](../README.md) for installation and the browser app.

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

Once it has data, the Python dashboard and CLI use it automatically, replacing the
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

Rows opened from a recommendation also preserve its strategy, horizon,
round-trip probability, stranded-inventory probability, downside stress,
ranking value, individual factors and timestamps. That makes future Active and
Overnight calibration possible without pretending public market prints reveal
private player fills.

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
python3 agent.py flips --json --capital 1.5m --account members --strategy active
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

## Data locations and recovery

| Data | Default location |
|---|---|
| Python API cache and tick archive | `cache/`, including `cache/ticks.db` |
| Flip journal | `journal.db` |
| Agent positions and watch state | `~/.osrs-flipper/`; override with `--state-dir` |
| Browser preferences and saved offers | localStorage in the current browser origin |
| Browser long-horizon history cache | IndexedDB in the current browser origin |

The browser app does not read the Python archive or synchronize positions
with the Python tools. Changing browser, device, or origin gives separate
storage. Back up durable positions, the journal, and the archive before moving
or clearing them; price caches can be fetched again.

Unreadable durable state is preserved and affected edits are blocked. Inspect
and back up the affected data before attempting recovery. Agent state writes
are atomic and serialized across processes. Browser edits across multiple tabs
can still conflict; use one tab when editing saved offers.

Portfolio JSON uses `null` for unavailable current prices and P&L. The field
`total_pnl_partial: true` means unquoted positions were excluded from the total.
Consumers must support unknown values. See the
[agent contract](../skills/osrs-flipper/SKILL.md) before changing output formats.
