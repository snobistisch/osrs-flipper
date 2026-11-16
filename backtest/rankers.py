"""Ranking methods under test, all fed the same point-in-time snapshot.

A method has two stages. ``candidates`` is the expensive, state-independent
part: score the market at ``t`` and order it. ``allocate`` then funds the free
slots from the coins a particular bank history has left. Splitting them means
one ranking per decision time serves every simulated bank, whatever fill
assumption that bank lives under.

Methods:

- ``policy``: the shipped pipeline under ``filters.automatic_profile``.
- ``CAPTURE_GRID`` (``policy_x00``, ``policy_x15``, ``policy_x30``): the
  policy sized on other shares of the volume crossing its price.
- ``browser``: the web app's own planner, ``docs/index.html`` run under Node.
- naive baselines: quoted margin and a seeded random pick with an equal split
  of the free coins. No fill model at all.
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

DEEP_TOP_K = 15          # same budget as cli.py and the browser


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
               config: Optional[filters.FilterConfig] = None
               ) -> filters.ScreenResult:
        return filters.refine_with_history(
            result, self.history, config or self.config, self.now, DEEP_TOP_K,
            fetch_recent=self.recent, fetch_reach=self.reach)

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
    """The shipped pipeline under a given configuration."""

    def __init__(self, name: str,
                 config: Callable[[filters.FilterConfig],
                                  filters.FilterConfig]):
        self.name, self.configure = name, config

    def config_for(self, context: Context) -> filters.FilterConfig:
        return self.configure(context.config)

    def candidates(self, context: Context) -> filters.ScreenResult:
        config = self.config_for(context)
        refined = context.refine(context.screen_for(config), config)
        return filters.apply_preferences(refined, config)

    def allocate(self, cand, context, capital, slots, exclude):
        rows = [row for row in cand.rows if row.item_id not in exclude]
        config = context.slot_config(capital, slots, self.config_for(context))
        result = filters.allocate(replace(cand, rows=rows), config)
        return _planned(result.rows)


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


def policy(config: filters.FilterConfig) -> filters.FilterConfig:
    """The shipped selection policy: filters.automatic_profile."""
    return filters.automatic_profile(config)


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
# sized on, in every strategy. 0 is the queue share; the default is
# policy_x00 (order size "careful"); 0.15 and 0.30 are the Active order sizes
# "balanced" and "large".
CAPTURE_GRID = {
    "policy_x00": 0.0,
    "policy_x15": 0.15,
    "policy_x30": 0.30,
}


def _registry() -> Dict[str, Method]:
    methods: List[Method] = [
        Naive("naive_margin", lambda rows, _: sorted(
            rows, key=lambda r: r.margin, reverse=True)),
        Naive("random", _shuffled),
        Pipeline("policy", config=policy),
    ]
    methods += [Pipeline(name, config=policy_capture(share))
                for name, share in CAPTURE_GRID.items()]
    methods += [Browser("browser")]
    return {method.name: method for method in methods}


METHODS: Dict[str, Method] = _registry()
BROWSER_METHODS = ("browser",)
DEFAULT_METHODS = [name for name in METHODS if name not in BROWSER_METHODS
                   and name not in CAPTURE_GRID]
