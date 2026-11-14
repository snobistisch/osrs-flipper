"""Walk-forward evaluation: decide at t on data before t, realise after t.

Design
------
Each ranking method runs a *bank*: a fixed starting stack of coins and the
account's GE slots, carried forward through time. At every step the bank

1. collects the offers that have finished (fully sold, or cancelled at their
   deadline with the leftover dumped), which returns coins and frees slots;
2. asks the method to fund the free slots from the free coins, using a
   snapshot built only from buckets that had closed by then;
3. hands each new offer to the fill simulator, which realises it on the
   5-minute buckets after the decision time.

That is what "gp per hour for the bank and slots I actually use" means: slow
flips block a slot, expensive ones block coins, quick ones recycle both, and
one number — the bank's realised gp per hour — arbitrates between objectives
that a per-offer comparison cannot rank without choosing the answer first.

Step and deadline per strategy (STRATEGIES): Active re-plans free slots every
half hour and gives an offer four hours; Max profit every four hours with a
24-hour deadline; Away places once per 12-hour cycle (8 hours away, then the
4-hour selling window), so its bank is flat again before each decision.

Buy limits are tracked per bank: an item is not offered again while its
offer is open, and a new offer is cut to what the item's four-hour limit has
left after the quantities placed in the last four hours.

Fill assumptions cannot be settled from public data, so every method runs one
bank per simulator variant (two crossing rules by three capture shares). The
expensive ranking is computed once per decision time and shared by all of
them.

Periods: the last ``HOLDOUT_DAYS`` of the panel are held out. The earlier days
are the tuning period and stop early enough that every tuning offer has ended
before the hold-out begins (an embargo). Each period is cut into segments that
start with a full bank; they are independent, which is what lets them run in
parallel and be resampled by day.
"""
from __future__ import annotations

import json
import multiprocessing
import random
import time
from dataclasses import replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import engine
import exemptions
import filters

from . import browser, rankers, simulate
from .panel import STEP_5M, Panel

HOLDOUT_DAYS = 14
DAY = 86400
SEED = 20261113
SEGMENT_DAYS = 3.5
LIMIT_COOLDOWN = engine.WINDOW_HOURS * 3600
WARMUP_SECONDS = 31 * 3600

# strategy -> (trade mode, offer horizon h, hours until the slot is surely
#              free, hours between planning steps)
STRATEGIES = {
    "active": ("active", 4.0, 4.0, 0.5),
    "overnight": ("overnight", 8.0, 12.0, 12.0),   # 8h away + 4h selling
    "profit": ("profit", 24.0, 24.0, 4.0),
}
CAPTURES = (0.03, 0.10, 0.30)


def sim_variants() -> Dict[str, dict]:
    """Both crossing rules across the capture haircut.

    ``strict``: instant trades on that side went through at a price strictly
    worse than the offer, so the offer had price priority over what traded.
    ``touch``: the average traded price was at or better than the offer, which
    also counts the buckets where the offer would merely have joined the queue
    at the same price. Neither the rule nor the capture share can be settled
    from public data; a conclusion only counts if it holds across the grid.
    """
    variants = {}
    for rule, strict in (("strict", True), ("touch", False)):
        for capture in CAPTURES:
            variants["{}_{:.2f}".format(rule, capture)] = {
                "capture": capture, "strict": strict}
    return variants


DEFAULT_VARIANT = "strict_0.10"
TOUCH_VARIANT = "touch_0.10"


def holdout_start(panel: Panel) -> int:
    return panel.end - HOLDOUT_DAYS * DAY


def segments(panel: Panel, strategy: str, period: str, seed: int = SEED,
             segment_days: float = SEGMENT_DAYS, stride: int = 1
             ) -> List[List[int]]:
    """Decision times per segment for one strategy and period.

    ``stride`` keeps every n-th segment, for a fast smoke run.
    """
    _, _, lifetime_hours, step_hours = STRATEGIES[strategy]
    step = int(step_hours * 3600)
    tail = int(lifetime_hours * 3600) + simulate.DUMP_LOOKAHEAD_BUCKETS[1] * STEP_5M
    split = holdout_start(panel)
    # Warm-up: methods that read an item's recent 5-minute buckets need the
    # 365 buckets the live /timeseries route returns, so nobody trades before
    # the panel holds them.
    first = -(-(panel.start + WARMUP_SECONDS) // 3600) * 3600
    if period == "tune":
        begin, end = first, split - tail
    elif period == "holdout":
        begin, end = split, panel.end - tail
    else:
        begin, end = first, panel.end - tail
    rng = random.Random("{}:{}:{}".format(seed, strategy, period))
    length = max(step, int(segment_days * DAY) // step * step)
    out = []
    start = begin
    while start + step <= end:
        # A seeded 0-55 minute offset: the live hour bucket is on average half
        # an hour stale, so decisions must not all sit exactly on the hour.
        jitter = rng.randrange(0, 12) * STEP_5M
        times = [t + jitter for t in range(start, min(start + length, end), step)
                 if t + jitter < end]
        if times:
            out.append(times)
        start += length
    return out[::max(1, stride)]


class Bank:
    """One method under one fill assumption: coins, slots, open offers."""

    def __init__(self, capital: int, slots: int):
        self.cash = float(capital)
        self.slots = slots
        # (release time, coins coming back, item id, coins locked)
        self.open: List[Tuple[int, float, int, int]] = []
        self.bought: Dict[int, List[Tuple[int, int]]] = {}   # item -> (t, qty)
        self.flips: List[dict] = []
        self.equity: List[Tuple[int, float, int, int]] = []

    def collect(self, t: int) -> None:
        still = []
        for offer in self.open:
            if offer[0] <= t:
                self.cash += offer[1]
            else:
                still.append(offer)
        self.open = still
        for item in list(self.bought):
            recent = [entry for entry in self.bought[item]
                      if entry[0] + LIMIT_COOLDOWN > t]
            if recent:
                self.bought[item] = recent
            else:
                del self.bought[item]

    @property
    def free_slots(self) -> int:
        return self.slots - len(self.open)

    def limit_left(self, item_id: int, limit: Optional[int]) -> Optional[int]:
        """Units of the four-hour buy limit still available; None = no limit.

        Counts the quantity placed, not the quantity filled: the cautious
        reading, since the game counts what was bought.
        """
        if limit is None:
            return None
        used = sum(qty for _, qty in self.bought.get(item_id, ()))
        return max(0, int(limit) - used)

    def excluded(self, limits: Optional[Dict[int, Optional[int]]] = None
                 ) -> frozenset:
        """Items with an open offer or with no buy limit left."""
        out = {offer[2] for offer in self.open}
        for item in self.bought:
            if limits is None:
                out.add(item)                 # no limits known: one window
                continue
            limit = limits.get(item)
            if limit is not None and self.limit_left(item, limit) <= 0:
                out.add(item)
        return frozenset(out)

    def mark(self, t: int) -> None:
        """(time, realised equity, slots in use, coins locked in offers)."""
        locked = sum(offer[3] for offer in self.open)
        self.equity.append((t, round(self.cash + locked, 2), len(self.open),
                            locked))

    def place(self, t: int, plan: rankers.Planned,
              outcome: simulate.Outcome) -> None:
        locked = plan.offer.qty * plan.unit_capital
        self.cash -= locked
        release = t + int(round(outcome.slot_hours * 3600))
        self.open.append((release, locked + outcome.pnl, plan.offer.item_id,
                          locked))
        self.bought.setdefault(plan.offer.item_id, []).append(
            (t, plan.offer.qty))
        self.flips.append({
            "t": t, "id": plan.offer.item_id, "name": plan.name,
            "buy": plan.offer.buy, "sell": plan.offer.sell,
            "qty": plan.offer.qty, "locked": locked,
            "bought": outcome.bought, "sold": outcome.sold,
            "dumped": outcome.dumped, "pnl": round(outcome.pnl, 2),
            "pnl_patient": round(outcome.pnl_patient, 2),
            "cap_h": round(outcome.capital_gp_hours, 2),
            "slot_h": round(outcome.slot_hours, 4),
            "done": int(outcome.completed), "done_s": outcome.completion_seconds,
            "first_s": outcome.first_fill_seconds,
            "pred": {key: (round(value, 6) if isinstance(value, float) else value)
                     for key, value in plan.pred.items()},
        })

    def finish(self) -> float:
        return self.cash + sum(offer[1] for offer in self.open)


def run_segment(panel: Panel, strategy: str, times: Sequence[int], capital: int,
                account: str, methods: Sequence[str], exempt,
                seed: int = SEED, planners: Optional[dict] = None) -> dict:
    """One segment: every method's bank under every fill variant."""
    mode, horizon, _, step_hours = STRATEGIES[strategy]
    account_type = engine.AccountType(account)
    variants = sim_variants()
    banks = {name: {variant: Bank(capital, account_type.slots)
                    for variant in variants} for name in methods}
    limits = {item_id: item.limit for item_id, item in panel.items.items()}
    for t in times:
        config = filters.FilterConfig(
            capital=capital, account=account_type, trade_mode=mode,
            overnight_hours=(horizon if mode == "overnight"
                             else engine.DEFAULT_OVERNIGHT_HOURS))
        snapshot = panel.snapshot(t)
        nature = snapshot.quotes.get(exemptions.NATURE_RUNE_ID)
        if nature is not None and nature.high:
            config = replace(config, nature_rune_cost=nature.high)
        context = rankers.Context(panel, snapshot, config, exempt, seed,
                                  planners)
        for name in methods:
            method = rankers.METHODS[name]
            for bank in banks[name].values():
                bank.collect(t)
            if all(bank.free_slots <= 0 or bank.cash < 1
                   for bank in banks[name].values()):
                for bank in banks[name].values():
                    bank.mark(t)
                continue
            candidates = method.candidates(context)
            for variant, bank in banks[name].items():
                if bank.free_slots > 0 and bank.cash >= 1:
                    sim = simulate.SimConfig(mode=mode, horizon_hours=horizon,
                                             seed=seed, **variants[variant])
                    for plan in method.allocate(candidates, context,
                                                int(bank.cash), bank.free_slots,
                                                bank.excluded(limits)):
                        left = bank.limit_left(plan.offer.item_id,
                                               plan.offer.limit)
                        if left is not None and plan.offer.qty > left:
                            plan = replace(plan, offer=replace(plan.offer,
                                                               qty=left))
                        locked = plan.offer.qty * plan.unit_capital
                        if (plan.offer.qty <= 0 or locked > bank.cash
                                or bank.free_slots <= 0):
                            continue        # never spend coins it does not have
                        bank.place(t, plan, simulate.simulate(
                            panel, plan.offer, t, sim))
                bank.mark(t)
            release = getattr(method, "release", None)
            if release is not None:
                release(candidates, context)
    return {
        "strategy": strategy, "start": int(times[0]), "end": int(times[-1]),
        "steps": len(times), "step_hours": step_hours,
        "banks": {name: {variant: {"final": round(bank.finish(), 2),
                                   "equity": bank.equity, "flips": bank.flips}
                         for variant, bank in by_variant.items()}
                  for name, by_variant in banks.items()},
    }


# -- parallel driver ---------------------------------------------------------

_WORKER: dict = {}


def _init(panel_path: str, methods: Sequence[str] = (),
          baseline_html: Optional[str] = None) -> None:
    panel = Panel.load(panel_path)
    _WORKER["panel"] = panel
    _WORKER["exempt"] = exemptions.resolve(panel.items)
    planners = {}
    if "browser" in methods:
        planners["browser"] = browser.BrowserPlanner()
    if "browser_baseline" in methods:
        if not baseline_html:
            raise ValueError("browser_baseline needs --baseline-html")
        planners["browser_baseline"] = browser.BrowserPlanner(baseline_html)
    _WORKER["planners"] = planners


def _task(args) -> dict:
    strategy, index, times, capital, account, methods, seed = args
    record = run_segment(_WORKER["panel"], strategy, times, capital, account,
                         methods, _WORKER["exempt"], seed, _WORKER["planners"])
    record["segment"] = index
    return record


def run(panel_path: "str | Path", out_path: "str | Path",
        strategies: Iterable[str] = ("active", "overnight", "profit"),
        period: str = "tune", capital: int = 20_000_000,
        account: str = "members", methods: Optional[Sequence[str]] = None,
        workers: int = 0, seed: int = SEED, stride: int = 1,
        progress=None, baseline_html: Optional[str] = None,
        segment_days: float = SEGMENT_DAYS) -> dict:
    """Run the walk-forward and write one JSON line per segment."""
    panel = Panel.load(panel_path)
    methods = list(methods or rankers.DEFAULT_METHODS)
    tasks = []
    for strategy in strategies:
        for index, times in enumerate(segments(panel, strategy, period, seed,
                                               segment_days, stride)):
            tasks.append((strategy, index, times, capital, account, methods,
                          seed))
    # Longest first, so the slow Active segments start before the quick ones.
    tasks.sort(key=lambda task: -len(task[2]))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    records = []
    pool = None
    if workers == 1 or len(tasks) < 2:
        _init(str(panel_path), methods, baseline_html)
        iterator = map(_task, tasks)
    else:
        pool = multiprocessing.get_context("spawn").Pool(
            min(len(tasks), workers or max(1, multiprocessing.cpu_count() - 2)),
            initializer=_init,
            initargs=(str(panel_path), methods, baseline_html))
        iterator = pool.imap_unordered(_task, tasks)
    try:
        for done, record in enumerate(iterator, 1):
            records.append(record)
            if progress:
                progress("{}/{} segments, {:.0f}s".format(
                    done, len(tasks), time.time() - started))
    finally:
        if pool is not None:
            pool.close()
            pool.join()
        for planner in _WORKER.get("planners", {}).values():
            planner.close()
        _WORKER.pop("planners", None)
    # Deterministic file order regardless of worker scheduling.
    records.sort(key=lambda r: (r["strategy"], r["start"]))
    with out_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "meta": {"period": period, "capital": capital, "account": account,
                     "seed": seed, "methods": methods, "stride": stride,
                     "segment_days": segment_days,
                     "panel_start": panel.start, "panel_end": panel.end,
                     "holdout_start": holdout_start(panel),
                     "variants": list(sim_variants())}}) + "\n")
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    return {"segments": len(records), "seconds": time.time() - started,
            "out": str(out_path)}


def load(path: "str | Path") -> Tuple[dict, List[dict]]:
    with Path(path).open(encoding="utf-8") as handle:
        meta = json.loads(handle.readline())["meta"]
        return meta, [json.loads(line) for line in handle if line.strip()]
