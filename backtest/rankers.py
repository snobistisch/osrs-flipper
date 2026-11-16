"""Ranking methods under test, all fed the same point-in-time snapshot.

A method has two stages. ``candidates`` is the expensive, state-independent
part: score the market at ``t`` and order it. ``allocate`` then funds the free
slots from the coins a particular bank history has left. Splitting them means
one ranking per decision time serves every simulated bank, whatever fill
assumption that bank lives under.

Families:

- ``current``: the Python pipeline as it was before the November 2026 audit
  (default ``FilterConfig``, the old queue constant). The baseline.
- ``browser_baseline``: the web app before the audit, a saved copy of
  ``docs/index.html`` run under Node. ``browser`` is the working tree's page.
- ``policy``: the shipped selection policy, ``filters.automatic_profile``.
- the ladder from one to the other (``gated``, ``reach``, ``replay_gate``,
  ``replay_gate_stable``, ``replay_portfolio`` and its variants): each rung
  adds one thing, so a gain can be attributed.
- model re-rankers (``ev_per_offer``, ``ev_roi``, ``gp_slot_hour``,
  ``gp_capital_hour``): the old scoring and sizing with another objective
  choosing which rows are deep-checked and funded. They separate "is the
  objective wrong" from "are its inputs wrong".
- naive baselines: quoted ROI, quoted margin and a seeded random pick with an
  equal split of the free coins. No fill model at all.
- ``ROBUSTNESS_GRID``: the policy under other values of the two constants
  public data cannot pin down.
- ``CAPTURE_GRID``: the policy sized on other shares of the volume crossing
  its price.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, FrozenSet, List, Optional

import engine
import filters

from . import browser
from .panel import Panel, Snapshot
from .simulate import Offer

DEEP_TOP_K = 15          # same budget as cli.py / app.py / the browser


@dataclass(frozen=True)
class SlotConfig(filters.FilterConfig):
    """FilterConfig for a bank with some slots already in use."""
    free_slots: Optional[int] = None

    @property
    def slots(self) -> int:
        return (self.account.slots if self.free_slots is None
                else max(0, int(self.free_slots)))


@dataclass(frozen=True)
class Planned:
    """One funded offer, whatever produced it, plus what was predicted."""
    offer: Offer
    name: str
    unit_capital: int
    pred: Dict[str, float] = field(default_factory=dict)


def prediction(row: filters.FlipRow) -> Dict[str, float]:
    """What the model claimed, kept for the calibration tables."""
    return {
        "p_fill": row.p_fill, "expected_gp": row.expected_gp,
        "p50": row.round_trip_p50_seconds, "p80": row.round_trip_p80_seconds,
        "p90": row.round_trip_p90_seconds,
        "margin": row.margin, "roi": row.roi,
        "volume": row.thin_volume_1h, "age": row.quote_age,
        "deep": int(bool(row.deep_checked)),
        "depth": row.undercut_depth,
        "replay_profit": None if row.replay is None else row.replay.mean_profit,
        "replay_done": (None if row.replay is None
                        else row.replay.completion_rate),
    }


def _planned(rows: List[filters.FlipRow]) -> List[Planned]:
    return [Planned(
        Offer(item_id=row.item_id, buy=row.buy, sell=row.sell,
              qty=int(row.allocated_quantity or 0), tax_exempt=row.tax_exempt,
              bond=row.bond, limit=row.limit),
        row.name, engine.unit_capital(row.buy, row.sell, row.bond),
        prediction(row)) for row in rows if row.allocated_quantity]


class Context:
    """One decision time: the snapshot, the config and the shared screen."""

    def __init__(self, panel: Panel, snapshot: Snapshot,
                 config: filters.FilterConfig, exempt, seed: int,
                 planners: Optional[Dict[str, browser.BrowserPlanner]] = None):
        self.panel, self.snapshot, self.config = panel, snapshot, config
        self.exempt, self.seed = exempt, seed
        self.now = snapshot.now
        self.planners = planners or {}
        self._screens: Dict[tuple, filters.ScreenResult] = {}

    def screen_for(self, config: filters.FilterConfig) -> filters.ScreenResult:
        """Stage-1 screen, shared by every method whose config scores alike."""
        # touch_fill_weight and crossing_capture_share only act on measured
        # reach, never in stage 1.
        key = (config.capital, config.account, config.trade_mode,
               config.overnight_hours, config.nature_rune_cost,
               replace(config.calibration, touch_fill_weight=0.0,
                       crossing_capture_share=0.0,
                       resting_capture_share=0.0),
               config.max_position_capital)
        if key not in self._screens:
            s = self.snapshot
            self._screens[key] = filters.screen(
                s.items, s.quotes, s.activity_5m, s.activity_1h, config,
                self.now, self.exempt)
        return self._screens[key]

    @property
    def screened(self) -> filters.ScreenResult:
        return self.screen_for(self.config)

    def history(self, item_id: int):
        return self.panel.history_6h(item_id, self.now)

    def recent(self, item_id: int):
        # The live /timeseries route returns 365 five-minute buckets; the
        # execution evidence, the reach and the replay all read that series.
        return self.panel.recent_5m(item_id, self.now, browser.RECENT_HOURS)

    reach = recent

    def refine(self, result: filters.ScreenResult,
               config: Optional[filters.FilterConfig] = None,
               reach: bool = False) -> filters.ScreenResult:
        return filters.refine_with_history(
            result, self.history, config or self.config, self.now, DEEP_TOP_K,
            fetch_recent=self.recent,
            fetch_reach=self.reach if reach else None)

    def slot_config(self, capital: int, slots: int,
                    base: Optional[filters.FilterConfig] = None) -> SlotConfig:
        base = base or self.config
        values = {name: getattr(base, name)
                  for name in filters.FilterConfig.__dataclass_fields__}
        values["capital"] = int(capital)
        return SlotConfig(free_slots=slots, **values)


class Method:
    """``candidates`` once per decision time, ``allocate`` once per bank."""
    name = ""

    def candidates(self, context: Context):
        raise NotImplementedError

    def allocate(self, cand, context: Context, capital: int, slots: int,
                 exclude: FrozenSet[int]) -> List[Planned]:
        raise NotImplementedError


class Pipeline(Method):
    """The shipped pipeline, optionally with another objective on top."""

    def __init__(self, name: str,
                 key: Optional[Callable[[filters.FlipRow], float]] = None,
                 config: Optional[Callable[[filters.FilterConfig],
                                           filters.FilterConfig]] = None,
                 reach: bool = False):
        self.name, self.key, self.configure = name, key, config
        self.reach = reach

    def _ordered(self, result: filters.ScreenResult) -> filters.ScreenResult:
        if self.key is None:
            return result
        rows = [replace(row, ranking_value=self.key(row)) for row in result.rows]
        rows.sort(key=lambda row: row.ranking_value, reverse=True)
        return replace(result, rows=rows)

    def config_for(self, context: Context) -> filters.FilterConfig:
        return self.configure(context.config) if self.configure else context.config

    def candidates(self, context: Context) -> filters.ScreenResult:
        config = self.config_for(context)
        screened = context.screen_for(config)
        # The deep-check budget goes to this objective's own leaders among the
        # rows the preferences allow (filters._deep_targets), which is what a
        # live implementation of it would do.
        refined = context.refine(self._ordered(screened), config, self.reach)
        return filters.apply_preferences(self._ordered(refined), config)

    def allocate(self, cand, context, capital, slots, exclude):
        rows = [row for row in cand.rows if row.item_id not in exclude]
        config = context.slot_config(capital, slots, self.config_for(context))
        result = filters.allocate(replace(cand, rows=rows), config)
        return _planned(result.rows)


def _occupancy_hours(row: filters.FlipRow) -> float:
    seconds = row.expected_occupancy_seconds or row.expected_total_seconds
    return max(seconds, 60.0) / engine.SECONDS_PER_HOUR


KEYS: Dict[str, Callable[[filters.FlipRow], float]] = {
    # Expected profit of the one offer, time ignored: Max profit's objective.
    "ev_per_offer": lambda r: r.expected_gp,
    # Model ROI: expected profit over the coins the offer locks.
    "ev_roi": lambda r: r.expected_gp / max(1, r.capital_needed),
    # Slot-hours scarce: the Active objective, without shrinkage.
    "gp_slot_hour": lambda r: r.expected_gp / _occupancy_hours(r),
    # Capital-hours scarce.
    "gp_capital_hour": lambda r: (r.expected_gp / max(1, r.capital_needed)
                                  / _occupancy_hours(r)),
    # Risk-adjusted: completion odds penalise a fragile fill a second time.
    "gp_slot_hour_risk": lambda r: (r.expected_gp * r.p_fill
                                    / _occupancy_hours(r)),
}


class Naive(Method):
    """Order by one quoted number, split the free coins equally."""

    def __init__(self, name: str, order: Callable[[List[filters.FlipRow],
                                                   Context], List[filters.FlipRow]]):
        self.name, self.order = name, order

    def candidates(self, context: Context) -> List[filters.FlipRow]:
        return self.order(list(context.screened.rows), context)

    def allocate(self, cand, context, capital, slots, exclude):
        if slots <= 0:
            return []
        per_slot = capital // slots
        funded = []
        for row in cand:
            if len(funded) >= slots:
                break
            if row.item_id in exclude:
                continue
            buy, sell = row.base_buy or row.buy, row.base_sell or row.sell
            unit = engine.unit_capital(buy, sell, row.bond)
            qty = per_slot // unit if unit > 0 else 0
            if row.limit is not None:
                qty = min(qty, row.limit)
            if qty <= 0:
                continue
            funded.append(replace(
                row, buy=buy, sell=sell, allocated_quantity=int(qty),
                margin=engine.net_margin(buy, sell, row.tax_exempt, row.bond)))
        return _planned(funded)


def _shuffled(rows: List[filters.FlipRow], context: Context
              ) -> List[filters.FlipRow]:
    rows.sort(key=lambda r: r.item_id)
    random.Random("{}:{}".format(context.seed, context.now)).shuffle(rows)
    return rows


class Browser(Method):
    """The web app's own planner, run under Node."""

    def __init__(self, name: str):
        self.name = name

    def candidates(self, context: Context) -> int:
        planner = context.planners.get(self.name)
        if planner is None:
            raise RuntimeError("{} needs Node.js".format(self.name))
        config = context.config
        return planner.prepare(context.panel, context.snapshot, config.capital,
                               config.account.value, config.trade_mode.value,
                               config.horizon_hours, config.nature_rune_cost)

    def allocate(self, cand, context, capital, slots, exclude):
        rows = context.planners[self.name].allocate(cand, capital, slots,
                                                    sorted(exclude))
        out = []
        for row in rows:
            offer = Offer(item_id=row["id"], buy=row["buy"], sell=row["sell"],
                          qty=int(row["qty"]), tax_exempt=row["exempt"],
                          bond=row["bond"], limit=row["limit"])
            out.append(Planned(offer, row["name"], engine.unit_capital(
                row["buy"], row["sell"], row["bond"]), {
                "p_fill": row["pFill"], "expected_gp": row["expected"],
                "p50": row["p50"], "p80": row["p80"], "p90": row["p90"],
                "margin": row["margin"], "roi": row["roi"],
                "volume": row["volume"], "age": row["age"],
                "deep": int(row["deep"]), "depth": row["depth"]}))
        return out

    def release(self, cand, context: Context) -> None:
        context.planners[self.name].release(cand)


def gated(config: filters.FilterConfig) -> filters.FilterConfig:
    """Only the quality gates of the automatic profile, on the rate model.

    This and the ladder built on it keep the pre-audit queue constant, so
    each rung differs from the one below it in a single respect.
    """
    profile = filters.automatic_profile(legacy(config))
    return replace(profile, deep_reference_share=0.0,
                   funding_evidence="history", replay_statistic="mean",
                   replay_ranking=False, allocation="proportional")


def gated_reach(config: filters.FilterConfig) -> filters.FilterConfig:
    return replace(gated(config), funding_evidence="reach")


def replay_gate(config: filters.FilterConfig) -> filters.FilterConfig:
    return replace(gated(config), funding_evidence="replay")


def replay_gate_stable(config: filters.FilterConfig) -> filters.FilterConfig:
    return replace(replay_gate(config), replay_statistic="stable")


def replay_portfolio(config: filters.FilterConfig) -> filters.FilterConfig:
    return replace(replay_gate_stable(config), replay_ranking=True,
                   allocation="portfolio")


def replay_portfolio_mean(config: filters.FilterConfig) -> filters.FilterConfig:
    return replace(replay_gate(config), replay_ranking=True,
                   allocation="portfolio")


def replay_portfolio_offer(config: filters.FilterConfig
                           ) -> filters.FilterConfig:
    return replace(replay_portfolio(config), active_objective="offer")


def policy(config: filters.FilterConfig) -> filters.FilterConfig:
    """The shipped selection policy: filters.automatic_profile."""
    return filters.automatic_profile(config)


def calibrated(**values) -> Callable[[filters.FilterConfig],
                                     filters.FilterConfig]:
    """replay_portfolio with other values for the unknowable fill constants."""
    def configure(config: filters.FilterConfig) -> filters.FilterConfig:
        config = replay_portfolio(config)
        return replace(config, calibration=replace(config.calibration,
                                                   **values))
    return configure


# The two constants public data cannot pin down, on a small grid: what volume
# at exactly the offer's price is worth, and how many offers share a queue.
ROBUSTNESS_GRID = {
    "rp_w50": dict(touch_fill_weight=0.5),
    "rp_w100": dict(touch_fill_weight=1.0),
    "rp_c16": dict(competitors_at_touch=16.0),
    "rp_c32": dict(competitors_at_touch=32.0),
    "rp_w50_c16": dict(touch_fill_weight=0.5, competitors_at_touch=16.0),
}


def portfolio(config: filters.FilterConfig) -> filters.FilterConfig:
    return replace(gated_reach(config), allocation="portfolio")


LEGACY_COMPETITORS_AT_TOUCH = 8.0


def legacy(config: filters.FilterConfig) -> filters.FilterConfig:
    """The pre-audit Python pipeline: default FilterConfig, the old queue
    constant, crossing volume shared out like that queue. With this config
    filters reproduces commit 92cee13, except that the plan is no longer
    capped at three uncategorised items (filters.category_full)."""
    return replace(config, calibration=replace(
        config.calibration, competitors_at_touch=LEGACY_COMPETITORS_AT_TOUCH,
        crossing_capture_share=0.0, resting_capture_share=0.0))


def policy_capture(share: float) -> Callable[[filters.FilterConfig],
                                             filters.FilterConfig]:
    """The shipped policy sized on another share of crossing volume, in
    every strategy: resting offers get it too, which is how it was measured
    that they should not."""
    def configure(config: filters.FilterConfig) -> filters.FilterConfig:
        config = policy(config)
        return replace(config, calibration=replace(
            config.calibration, crossing_capture_share=share,
            resting_capture_share=share))
    return configure


# The policy under other values of the share of crossing volume an offer is
# sized on. 0 is the queue share every strategy used until 16 November 2026;
# the shipped policy is policy_x30 for Active and policy_x00 for the rest.
CAPTURE_GRID = {
    "policy_x00": 0.0,
    "policy_x15": 0.15,
    "policy_x30": 0.30,
    "policy_x50": 0.50,
}


def _registry() -> Dict[str, Method]:
    methods: List[Method] = [
        Pipeline("current", config=legacy),
        Naive("naive_roi", lambda rows, _: sorted(
            rows, key=lambda r: r.roi, reverse=True)),
        Naive("naive_margin", lambda rows, _: sorted(
            rows, key=lambda r: r.margin, reverse=True)),
        Naive("random", _shuffled),
    ]
    methods += [Pipeline(name, key, config=legacy) for name, key in KEYS.items()]
    methods += [Pipeline("gated", config=gated),
                Pipeline("reach", config=gated_reach, reach=True),
                Pipeline("portfolio", config=portfolio, reach=True),
                Pipeline("replay_gate", config=replay_gate, reach=True),
                Pipeline("replay_gate_stable", config=replay_gate_stable,
                         reach=True),
                Pipeline("replay_portfolio", config=replay_portfolio,
                         reach=True),
                Pipeline("replay_portfolio_mean", config=replay_portfolio_mean,
                         reach=True),
                Pipeline("replay_portfolio_offer",
                         config=replay_portfolio_offer, reach=True),
                Pipeline("policy", config=policy, reach=True)]
    methods += [Pipeline(name, config=calibrated(**values), reach=True)
                for name, values in ROBUSTNESS_GRID.items()]
    methods += [Pipeline(name, config=policy_capture(share), reach=True)
                for name, share in CAPTURE_GRID.items()]
    methods += [Browser("browser"), Browser("browser_baseline")]
    return {method.name: method for method in methods}


METHODS: Dict[str, Method] = _registry()
BROWSER_METHODS = ("browser", "browser_baseline")
DEFAULT_METHODS = [name for name in METHODS if name not in BROWSER_METHODS
                   and name not in ROBUSTNESS_GRID
                   and name not in CAPTURE_GRID]


def register(method: Method) -> None:
    METHODS[method.name] = method
