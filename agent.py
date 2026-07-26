"""Machine-readable and cron-driven access to the ranking.

`cli.py` prints a table for a person to read. This prints for a program: JSON
on demand, and — the part that matters — *nothing at all* when there is nothing
worth saying.

That silence is the whole design. An agent wired to a chat app is only useful
while its messages are still worth opening, and a job that reports twenty rows
every hour trains you to ignore it inside two days. So `watch` holds state
between runs and speaks only when something crossed a line it had not already
crossed:

    python3 agent.py watch            # usually prints nothing, exit 0
    python3 agent.py watch --json     # same decision, machine-readable

Commands:

    flips        rank flips now (the same numbers cli.py shows)
    merch        the watchlist over a year: trend, crash depth, supply
    watch        new signals only, for cron
    portfolio    positions you are holding, and what they are worth
    status       what is cached, how old it is, whether the archive is running

Stdlib only. It has to run from cron on a machine with no virtualenv activated,
so nothing here may import pandas, streamlit, or anything else from
requirements.txt.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import api
import archive
import engine
import exemptions
import filters
import merch

# State lives outside the repo so a git pull cannot wipe your positions, and
# defaults to a plain dotfile directory rather than anything Hermes-specific —
# the tool is useful without an agent attached. The Hermes recipes in README.md
# pass --state-dir ~/.hermes/state to keep everything in one place.
DEFAULT_STATE_DIR = Path(os.path.expanduser("~/.osrs-flipper"))
WATCH_STATE_FILE = "watch_state.json"
PORTFOLIO_FILE = "portfolio.json"

# How many consecutive failed runs before the silence itself is the alert. A
# job that has been unable to reach the API for an hour should say so, or a
# broken cron looks exactly like a quiet market.
MAX_SILENT_FAILURES = 3

# Alert scales, per signal kind. A signal fires when its magnitude crosses an
# integer multiple of the scale that it has not already reported: a 40% crash
# alerts once, and only speaks again if it reaches 70%. Below HYSTERESIS x the
# scale the item resets and may alert afresh later. Lifted wholesale from the
# NOCK monitor, which learned it the hard way.
ALERT_SCALE = {
    merch.CRASH: 0.35,
    merch.DIP: 0.20,
    merch.DIPPED_STABLE: 0.30,
    merch.PUMPED: 0.15,
    merch.SUPPLY_CRUNCH: 0.80,
    merch.SUPPLY_DROP: 0.50,
    "PULLBACK": 0.05,
}
HYSTERESIS = 0.5


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------

def _read_json(path: Path, fallback):
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return fallback


def _write_json(path: Path, payload) -> None:
    """Atomic write: a killed cron job must not leave half a state file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    temporary.replace(path)


# ---------------------------------------------------------------------------
# signals
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    item_id: int
    name: str
    kind: str
    magnitude: float          # compared against ALERT_SCALE to tier it
    price: Optional[int]
    message: str
    detail: Dict[str, object] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return "{}:{}".format(self.item_id, self.kind)


def signals_from_view(item_id: int, name: str,
                      view: merch.DailyView) -> List[Signal]:
    """Everything about one item that might be worth waking someone for."""
    found = []

    if view.crash is not None:
        found.append(Signal(
            item_id=item_id, name=name, kind=view.crash.kind,
            magnitude=abs(view.crash.depth), price=view.price,
            message="{:+.0%} against its {}-day median on {:.1f}x volume".format(
                view.crash.depth, merch.MEDIAN_WINDOW_DAYS,
                view.crash.volume_ratio),
            detail={"depth": round(view.crash.depth, 4),
                    "volume_ratio": round(view.crash.volume_ratio, 2),
                    "median_14d": view.median_14d}))

    if view.supply is not None and view.volume_change_relative is not None:
        found.append(Signal(
            item_id=item_id, name=name, kind=view.supply,
            magnitude=abs(view.volume_change_relative), price=view.price,
            message="volume {:+.0%} against six months ago, {:+.0%} once the "
                    "market's own {:+.0%} is divided out".format(
                        view.volume_change_6m, view.volume_change_relative,
                        view.market_drift),
            detail={"volume_change_6m": round(view.volume_change_6m, 4),
                    "volume_change_vs_market":
                        round(view.volume_change_relative, 4),
                    "market_drift": round(view.market_drift, 4)}))

    entry = merch.entry_signal(view.price, view.trend, view.median_14d)
    if entry is not None and entry.kind == "PULLBACK":
        found.append(Signal(
            item_id=item_id, name=name, kind="PULLBACK",
            magnitude=entry.strength, price=view.price,
            message="{} while trending {:+.0f}%/yr (R2 {:.2f})".format(
                entry.message, view.trend.annualised_pct,
                view.trend.r_squared),
            detail={"deviation": round(view.trend.deviation, 4),
                    "annualised_pct": round(view.trend.annualised_pct, 1),
                    "r_squared": round(view.trend.r_squared, 3)}))

    return found


def new_signals(found: Sequence[Signal],
                state: dict) -> Tuple[List[Signal], dict]:
    """Filter to what has not already been reported, and update the state.

    Tiering rather than a cooldown: time-based re-alerts would fire on the same
    unchanged crash every morning, while a tier only advances when the thing
    actually got worse.
    """
    tiers = dict(state.get("tiers", {}))
    by_key = {signal.key: signal for signal in found}
    fired = []

    for key, signal in by_key.items():
        scale = ALERT_SCALE.get(signal.kind)
        if not scale:
            continue
        tier = int(signal.magnitude / scale)
        previous = tiers.get(key, {}).get("tier", 0)
        if tier > previous:
            fired.append(signal)
            tiers[key] = {"tier": tier, "at": int(time.time())}

    # Anything that fell back below the hysteresis band is cleared, so the same
    # item may alert again if it comes back later.
    for key in list(tiers):
        signal = by_key.get(key)
        scale = ALERT_SCALE.get(key.split(":", 1)[1])
        if not scale:
            tiers.pop(key, None)
            continue
        if signal is None or signal.magnitude < scale * HYSTERESIS:
            tiers.pop(key, None)

    updated = dict(state)
    updated["tiers"] = tiers
    return fired, updated


def trend_changes(views: Dict[int, merch.DailyView], names: Dict[int, str],
                  state: dict) -> Tuple[List[Signal], dict]:
    """A watchlist item that changed direction since the last run.

    Separate from the tiered signals because there is no magnitude to escalate:
    a trend flips once, and that single event is the whole message.
    """
    previous = dict(state.get("directions", {}))
    fired, current = [], {}

    for item_id, view in views.items():
        if view.trend is None:
            continue
        direction = view.trend.direction
        current[str(item_id)] = direction
        was = previous.get(str(item_id))
        if was is not None and was != direction:
            fired.append(Signal(
                item_id=item_id, name=names.get(item_id, str(item_id)),
                kind="TREND_CHANGE", magnitude=1.0, price=view.price,
                message="trend turned {} (was {}), now {:+.0f}%/yr".format(
                    direction, was, view.trend.annualised_pct),
                detail={"from": was, "to": direction,
                        "annualised_pct": round(view.trend.annualised_pct, 1)}))

    updated = dict(state)
    updated["directions"] = current
    return fired, updated


# ---------------------------------------------------------------------------
# data loading
# ---------------------------------------------------------------------------

def load_watchlist(client: api.WikiClient, item_ids: Sequence[int],
                   quotes: Optional[dict] = None
                   ) -> Tuple[Dict[int, merch.DailyView], Dict[int, str],
                              List[str]]:
    """One year of daily history per item. Disk-cached, so cron is cheap.

    Errors are collected rather than raised: one item whose history is
    unavailable must not cost you the other twenty.
    """
    items = client.mapping()
    if quotes is None:
        quotes = client.latest()

    views, names, problems = {}, {}, []
    for item_id in item_ids:
        item = items.get(item_id)
        if item is None:
            problems.append("{}: not in /mapping".format(item_id))
            continue
        names[item_id] = item.name
        quote = quotes.get(item_id)
        price = None
        if quote is not None and quote.high and quote.low:
            price = (quote.high + quote.low) / 2.0
        try:
            points = client.timeseries(item_id, merch.TREND_TIMESTEP)
        except api.ApiError as exc:
            problems.append("{}: {}".format(item.name, exc))
            continue
        views[item_id] = merch.daily_view(points, price=price)
    # Supply verdicts need the whole basket: see merch.market_volume_drift.
    return merch.apply_market_context(views), names, problems


def rank(client: api.WikiClient, capital: int, slots: int, members: bool,
         deep: int = 15) -> filters.ScreenResult:
    """The flip ranking, identical to what cli.py and the browser produce."""
    items = client.mapping()
    quotes = client.latest()
    activity_5m = client.interval("5m")
    activity_1h = client.interval("1h")
    exempt = exemptions.resolve(items)
    nature_cost = exemptions.nature_rune_cost(quotes)
    config = filters.FilterConfig(
        capital=capital, slots=slots, include_members=members,
        nature_rune_cost=nature_cost)

    store = _open_archive()
    volume_lookup = _archive_lookup(store) if store is not None else None

    def fetch(item_id):
        try:
            return client.timeseries(item_id, engine.HISTORY_TIMESTEP)
        except api.ApiError:
            return None

    try:
        return filters.rank_flips(
            items, quotes, activity_5m, activity_1h, config, now=time.time(),
            fetch_history=fetch if deep > 0 else None, top_k=deep,
            exempt=exempt, volume_lookup=volume_lookup)
    finally:
        if store is not None:
            store.close()


# ---------------------------------------------------------------------------
# serialisation
# ---------------------------------------------------------------------------

def _open_archive() -> Optional["archive.Archive"]:
    """The tick archive if it holds anything, else None. Never fatal."""
    try:
        store = archive.Archive(archive.DEFAULT_DB)
    except Exception:
        return None
    try:
        if store.summary()["buckets"]:
            return store
    except Exception:
        pass
    store.close()
    return None


def _archive_lookup(store: "archive.Archive"):
    """(buyer-initiated, seller-initiated) units/hour, smoothed over days."""
    def lookup(item_id):
        estimate = store.volume_ewma(item_id)
        if estimate is None or not estimate.usable:
            return None
        return estimate.high_per_hour, estimate.low_per_hour
    return lookup


def flip_to_dict(row: filters.FlipRow) -> dict:
    """The fields an agent can act on. Not every field — a wall of floats is
    harder to reason about than a short list of the ones that decide."""
    return {
        "item_id": row.item_id, "name": row.name,
        "buy": row.buy, "sell": row.sell, "list_at": row.sell_listed_at,
        "margin": row.margin, "roi": round(row.roi, 4),
        "quantity": row.qty_per_window, "capital_needed": row.capital_needed,
        "gp_per_slot_hour": round(row.gp_per_slot_hour),
        "gp_per_slot_hour_before_shrinkage": round(row.raw_gp_per_slot_hour),
        "round_trip_seconds": round(row.expected_total_seconds),
        "p_fill": round(row.p_fill, 3),
        "edge_probability": round(row.edge_probability, 3),
        "buy_limit": row.limit, "volume_1h": row.thin_volume_1h,
        "tax_exempt": row.tax_exempt,
        "deep_checked": row.deep_checked,
        "allocated_capital": row.allocated_capital,
        "warnings": list(row.warnings),
    }


def view_to_dict(item_id: int, name: str, view: merch.DailyView) -> dict:
    trend = view.trend
    return {
        "item_id": item_id, "name": name,
        "thesis": merch.THESIS_BY_ID.get(item_id),
        "price": view.price, "days_of_history": view.days,
        "median_14d": view.median_14d,
        "depth_vs_median": round(view.depth, 4) if view.depth is not None else None,
        "volume_today": view.volume_today,
        "volume_baseline": view.volume_baseline,
        "volume_ratio": round(view.volume_ratio, 2),
        "volume_change_6m": (round(view.volume_change_6m, 4)
                             if view.volume_change_6m is not None else None),
        "volume_change_vs_market": (round(view.volume_change_relative, 4)
                                    if view.volume_change_relative is not None
                                    else None),
        "market_volume_drift": (round(view.market_drift, 4)
                                if view.market_drift is not None else None),
        "trend": None if trend is None else {
            "direction": trend.direction,
            "annualised_pct": round(trend.annualised_pct, 1),
            "r_squared": round(trend.r_squared, 3),
            "t_stat": round(trend.t_stat, 2),
            # Share of items with no trend at all that would look this trendy.
            # Read this before the headline rate, not after it.
            "noise_probability": round(trend.noise_probability, 3),
            "verdict": trend.verdict,
            "deviation": round(trend.deviation, 4),
            "consistency": round(trend.consistency, 3),
            "days": trend.n,
        },
        "merch_score": round(merch.merch_score(trend), 2),
        "crash_badge": view.crash.kind if view.crash else None,
        "supply_badge": view.supply,
        "tags": merch.classify_item(
            item_id, view.price or 0, members=True, buy_limit=None,
            trend=trend, crash=view.crash, supply=view.supply),
    }


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_flips(opts) -> int:
    client = api.WikiClient()
    try:
        result = rank(client, opts.capital, opts.slots, opts.members,
                      deep=opts.deep)
    except api.ApiError as exc:
        print("API error: {}".format(exc), file=sys.stderr)
        return 1

    rows = result.rows[:opts.top]
    if opts.json:
        print(json.dumps({
            "generated_at": int(time.time()),
            "capital": opts.capital, "slots": opts.slots,
            "members": opts.members,
            "scored": result.funnel.get("scored", 0),
            "deep_checked": result.deep_checked,
            "flips": [flip_to_dict(row) for row in rows],
        }, indent=2))
        return 0

    if not rows:
        print("Nothing worth flipping at this capital right now.")
        return 0
    for index, row in enumerate(rows, 1):
        print("{:>2}. {:<26} buy {:>10} sell {:>10} x{:<6} {:>10} gp/slot/h".format(
            index, row.name[:26], engine.format_gp(row.buy),
            engine.format_gp(row.sell), row.qty_per_window,
            engine.format_gp(int(row.gp_per_slot_hour))))
    return 0


def cmd_merch(opts) -> int:
    client = api.WikiClient()
    try:
        views, names, problems = load_watchlist(client, merch.WATCHLIST_IDS)
    except api.ApiError as exc:
        print("API error: {}".format(exc), file=sys.stderr)
        return 1

    ranked = sorted(
        views.items(),
        key=lambda pair: merch.merch_score(pair[1].trend), reverse=True)

    if opts.json:
        print(json.dumps({
            "generated_at": int(time.time()),
            "problems": problems,
            "items": [view_to_dict(item_id, names.get(item_id, ""), view)
                      for item_id, view in ranked],
        }, indent=2))
        return 0

    print("{:<26} {:>9} {:>9} {:>6} {:>7} {:>7} {:>10}  {}".format(
        "ITEM", "PRICE", "TREND/YR", "R2", "NOISE", "VS 14D", "VOL vs MKT",
        "SIGNALS"))
    for item_id, view in ranked:
        trend = view.trend
        badges = [b for b in (view.crash.kind if view.crash else None,
                              view.supply) if b]
        print("{:<26.26} {:>9} {:>9} {:>6} {:>7} {:>7} {:>10}  {}".format(
            names.get(item_id, str(item_id)),
            engine.format_gp(view.price) if view.price else "-",
            "{:+.0f}%".format(trend.annualised_pct) if trend else "-",
            "{:.2f}".format(trend.r_squared) if trend else "-",
            "{:.0%}".format(trend.noise_probability) if trend else "-",
            "{:+.0%}".format(view.depth) if view.depth is not None else "-",
            "{:+.0%}".format(view.volume_change_relative)
            if view.volume_change_relative is not None else "-",
            " ".join(badges) or ("" if not trend else trend.direction)))

    drift = next((v.market_drift for v in views.values()
                  if v.market_drift is not None), None)
    print("\nNOISE is the share of items with NO trend that would look at "
          "least this trendy. Read it before the trend column: a headline "
          "+50%/yr at 40% noise is not a finding.")
    if drift is not None:
        print("Market-wide volume moved {:+.0%} over six months; VOL vs MKT "
              "has that divided out, so it shows only what belongs to the "
              "item.".format(drift))
    for problem in problems:
        print("  ! {}".format(problem), file=sys.stderr)
    return 0


def cmd_watch(opts) -> int:
    """Cron entry point. Prints nothing when there is nothing to say."""
    state_path = opts.state_dir / WATCH_STATE_FILE
    state = _read_json(state_path, {})
    client = api.WikiClient()

    try:
        views, names, problems = load_watchlist(client, merch.WATCHLIST_IDS)
        failures = 0
    except api.ApiError as exc:
        failures = state.get("consecutive_failures", 0) + 1
        state["consecutive_failures"] = failures
        _write_json(state_path, state)
        if failures >= MAX_SILENT_FAILURES:
            print("OSRS FLIPPER — no data for {} consecutive runs: {}".format(
                failures, exc))
        return 0

    found = []
    for item_id, view in views.items():
        found.extend(signals_from_view(item_id, names.get(item_id, ""), view))

    fired, state = new_signals(found, state)
    changed, state = trend_changes(views, names, state)
    fired.extend(changed)

    state["consecutive_failures"] = failures
    state["last_run"] = int(time.time())
    _write_json(state_path, state)

    if opts.json:
        print(json.dumps({
            "generated_at": int(time.time()),
            "signals": [asdict(signal) for signal in fired],
            "problems": problems,
        }, indent=2))
        return 0

    if not fired:
        return 0                       # the normal case: say nothing

    fired.sort(key=lambda s: -s.magnitude)
    print("OSRS FLIPPER — {} new signal{}".format(
        len(fired), "" if len(fired) == 1 else "s"))
    for signal in fired:
        print("{:<14} {} ({}) at {} — {}".format(
            signal.kind, signal.name, signal.item_id,
            engine.format_gp(signal.price) if signal.price else "?",
            signal.message))
        thesis = merch.THESIS_BY_ID.get(signal.item_id)
        if thesis:
            print("{:<14} why it is on the list: {}".format("", thesis))
    return 0


def cmd_portfolio(opts) -> int:
    path = opts.state_dir / PORTFOLIO_FILE
    positions = _read_json(path, [])
    client = api.WikiClient()

    if opts.action == "add":
        try:
            items = client.mapping()
        except api.ApiError as exc:
            print("API error: {}".format(exc), file=sys.stderr)
            return 1
        item_id = _resolve_item(opts.item, items)
        if item_id is None:
            print("No item matches {!r}".format(opts.item), file=sys.stderr)
            return 1
        positions.append({
            "item_id": item_id, "name": items[item_id].name,
            "qty": opts.qty, "buy_price": opts.price,
            "opened_at": int(time.time()),
        })
        _write_json(path, positions)
        print("Holding {:,} x {} at {} gp.".format(
            opts.qty, items[item_id].name, engine.format_gp(opts.price)))
        return 0

    if opts.action == "close":
        if not 1 <= opts.index <= len(positions):
            print("No position {}".format(opts.index), file=sys.stderr)
            return 1
        closed = positions.pop(opts.index - 1)
        _write_json(path, positions)
        exempt = exemptions.resolve(client.mapping())
        net = engine.net_revenue(opts.price, closed["item_id"] in exempt)
        profit = (net - closed["buy_price"]) * closed["qty"]
        held = (time.time() - closed["opened_at"]) / 86400
        print("Closed {:,} x {} after {:.0f} days: {} gp after tax.".format(
            closed["qty"], closed["name"], held, engine.format_gp(int(profit))))
        return 0

    # list
    if not positions:
        if not opts.json:
            print("No open positions.")
        else:
            print(json.dumps({"positions": [], "total_pnl": 0}, indent=2))
        return 0

    try:
        quotes = client.latest()
        exempt = exemptions.resolve(client.mapping())
    except api.ApiError as exc:
        print("API error: {}".format(exc), file=sys.stderr)
        return 1

    enriched, total = [], 0
    for index, position in enumerate(positions, 1):
        quote = quotes.get(position["item_id"])
        # Value the position at what a sale would actually net: the price a
        # buyer is bidding, minus GE tax. Marking to the instant-buy price and
        # ignoring tax is how a losing position reads as a winning one.
        current = quote.low if quote and quote.low else position["buy_price"]
        net = engine.net_revenue(current, position["item_id"] in exempt)
        pnl = (net - position["buy_price"]) * position["qty"]
        total += pnl
        enriched.append({
            "index": index, "item_id": position["item_id"],
            "name": position["name"], "qty": position["qty"],
            "buy_price": position["buy_price"], "current_price": current,
            "net_of_tax": net, "pnl": int(pnl),
            "pnl_pct": round((net / position["buy_price"] - 1) * 100, 1),
            "held_days": round((time.time() - position["opened_at"]) / 86400, 1),
        })

    if opts.json:
        print(json.dumps({"positions": enriched, "total_pnl": int(total)},
                         indent=2))
        return 0

    print("{:>2} {:<24} {:>8} {:>10} {:>10} {:>12} {:>7}".format(
        "#", "ITEM", "QTY", "PAID", "NET NOW", "P&L", "DAYS"))
    for row in enriched:
        print("{:>2} {:<24.24} {:>8,} {:>10} {:>10} {:>12} {:>7.0f}".format(
            row["index"], row["name"], row["qty"],
            engine.format_gp(row["buy_price"]), engine.format_gp(row["net_of_tax"]),
            engine.format_gp(row["pnl"]), row["held_days"]))
    print("\nTotal: {} gp".format(engine.format_gp(int(total))))
    return 0


def _resolve_item(text: str, items: Dict[int, api.Item]) -> Optional[int]:
    """Accept an id or a name. Names are what people actually type."""
    if text.isdigit() and int(text) in items:
        return int(text)
    wanted = text.strip().lower()
    for item_id, item in items.items():
        if item.name.lower() == wanted:
            return item_id
    matches = [i for i, item in items.items() if wanted in item.name.lower()]
    return matches[0] if len(matches) == 1 else None


def cmd_status(opts) -> int:
    client = api.WikiClient()
    lines = []

    mapping_file = client.cache_dir / "mapping.json"
    if mapping_file.exists():
        age = (time.time() - mapping_file.stat().st_mtime) / 3600
        lines.append("mapping cache: {:.1f} hours old".format(age))
    else:
        lines.append("mapping cache: absent, will fetch on first run")

    cached = sum(1 for item_id in merch.WATCHLIST_IDS
                 if client.cached_timeseries_age(
                     item_id, merch.TREND_TIMESTEP) is not None)
    lines.append("watchlist history: {}/{} items cached on disk".format(
        cached, len(merch.WATCHLIST_IDS)))

    try:
        store = archive.Archive(archive.DEFAULT_DB)
        summary = store.summary()
        store.close()
        if summary["buckets"]:
            lines.append("tick archive: {:.1f} days, {:,} bucket rows".format(
                summary["days"], summary["buckets"]))
        else:
            lines.append("tick archive: empty — run collect.py to start it")
    except Exception as exc:
        lines.append("tick archive: unavailable ({})".format(exc))

    watch_state = _read_json(opts.state_dir / WATCH_STATE_FILE, {})
    if watch_state.get("last_run"):
        age = (time.time() - watch_state["last_run"]) / 60
        lines.append("last watch run: {:.0f} minutes ago, {} signals held "
                     "open".format(age, len(watch_state.get("tiers", {}))))
    else:
        lines.append("last watch run: never")

    positions = _read_json(opts.state_dir / PORTFOLIO_FILE, [])
    lines.append("portfolio: {} open position{}".format(
        len(positions), "" if len(positions) == 1 else "s"))

    if opts.json:
        print(json.dumps({"status": lines}, indent=2))
    else:
        for line in lines:
            print(line)
    return 0


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    # The shared flags go on a parent parser so they work on either side of the
    # subcommand. `agent.py --json merch` and `agent.py merch --json` are the
    # same thing, because remembering which one argparse wanted is not a
    # reasonable thing to ask of anyone.
    # The shared flags are declared twice on purpose, so that both
    # `agent.py --json merch` and `agent.py merch --json` work — remembering
    # which side argparse wanted is not a reasonable thing to ask of anyone.
    #
    # The subparser copies default to SUPPRESS: a copy carrying default=False
    # would fire when the subcommand is parsed and overwrite a --json that was
    # already given on the left. Suppressed actions set nothing unless the flag
    # is really present, so the top-level declaration below owns the default.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state-dir", type=Path, default=argparse.SUPPRESS,
                        help="where watch state and the portfolio live "
                             "(default: ~/.osrs-flipper)")
    common.add_argument("--json", action="store_true",
                        default=argparse.SUPPRESS,
                        help="machine-readable output")

    parser = argparse.ArgumentParser(
        prog="agent.py", description=__doc__.splitlines()[0])
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR,
                        help="where watch state and the portfolio live "
                             "(default: ~/.osrs-flipper)")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    flips = sub.add_parser("flips", parents=[common],
                           help="rank flips right now")
    flips.add_argument("--capital", type=engine.parse_gp, default=1_000_000,
                       help="gp across all slots, e.g. 250k or 1.5m")
    flips.add_argument("--slots", type=int, default=engine.F2P_SLOTS,
                       help="concurrent offers: 3 free-to-play, 8 members")
    flips.add_argument("--members", action="store_true")
    flips.add_argument("--top", type=int, default=10)
    flips.add_argument("--deep", type=int, default=15,
                       help="candidates to deep-check against 14d history")
    flips.set_defaults(func=cmd_flips)

    merch_cmd = sub.add_parser("merch", parents=[common],
                               help="the watchlist over a year")
    merch_cmd.set_defaults(func=cmd_merch)

    watch = sub.add_parser(
        "watch", parents=[common],
        help="new signals only — silent when there are none")
    watch.set_defaults(func=cmd_watch)

    portfolio = sub.add_parser("portfolio", parents=[common],
                               help="positions you are holding")
    actions = portfolio.add_subparsers(dest="action")
    portfolio.set_defaults(func=cmd_portfolio, action="list")

    add = actions.add_parser("add", parents=[common], help="record a position")
    add.add_argument("item", help="item id or name")
    add.add_argument("--qty", type=int, required=True)
    add.add_argument("--price", type=engine.parse_gp, required=True,
                     help="what you paid per item")
    add.set_defaults(func=cmd_portfolio, action="add")

    close = actions.add_parser("close", parents=[common],
                               help="close a position by number")
    close.add_argument("index", type=int)
    close.add_argument("--price", type=engine.parse_gp, required=True,
                       help="what you sold at, before tax")
    close.set_defaults(func=cmd_portfolio, action="close")

    show = actions.add_parser("list", parents=[common],
                              help="open positions and their P&L")
    show.set_defaults(func=cmd_portfolio, action="list")

    status = sub.add_parser("status", parents=[common],
                            help="caches, archive, and watch state")
    status.set_defaults(func=cmd_status)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    opts = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return opts.func(opts)


if __name__ == "__main__":
    sys.exit(main())
