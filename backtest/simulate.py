"""Fill simulator: what one resting offer would plausibly have done.

The public feed has trades, not an order book, so no simulator can know
whether *your* offer would have filled. This one is deliberately conservative
and, more importantly, explicit about its one unknowable assumption.

Rules (all applied on 5-minute buckets *after* the decision time):

1. A buy at price ``B`` can only fill in a bucket where instant-sells traded
   at an average price at or below ``B``; a sell at ``S`` only where
   instant-buys traded at or above ``S``. An offer therefore never fills at a
   price the data shows was not reached. ``strict`` requires the price to
   trade *through* the offer, which is the textbook conservative rule for a
   limit order without queue information.
2. Of the units that traded on that side in such a bucket, you receive a
   Binomial(volume, capture) draw. ``capture`` is the queue/competition
   haircut: the share of crossing volume that reaches your offer rather than
   the offers ahead of or beside it. Its true value is unknown without real
   fills, so every result is reported across a sweep of it.
3. The sell leg can only sell units already bought in an earlier bucket.
4. The four-hour buy limit caps units bought per window.
5. At the deadline the unfilled buy is cancelled and unsold inventory is
   dumped at the instant-sell price that traded next, net of tax. No fill is
   ever credited at the quoted margin unless both legs actually crossed.
   ``pnl_patient`` values the same leftover at the next instant-BUY price
   instead (a seller who keeps waiting and is eventually lifted): the two
   bracket what unsold stock is worth, and the gap between them is how much
   of a result depends on that choice.

Randomness is seeded per (seed, item, time, side) and drawn for every bucket
before the price test, so two ranking methods that pick the same item at the
same time face the same market luck (common random numbers).

The simulator takes prices and a quantity, never a model's predictions: a
method cannot improve its own outcome by being optimistic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

import engine

from .panel import STEP_5M, Panel

BUCKETS_PER_HOUR = 3600 // STEP_5M
LIMIT_WINDOW_BUCKETS = engine.WINDOW_HOURS * BUCKETS_PER_HOUR
DUMP_LOOKAHEAD_BUCKETS = (12, 72)        # 1h, then 6h
DEFAULT_CAPTURE = 0.10


@dataclass(frozen=True)
class Offer:
    item_id: int
    buy: int
    sell: int
    qty: int
    tax_exempt: bool = False
    bond: bool = False
    limit: Optional[int] = None


@dataclass(frozen=True)
class SimConfig:
    mode: str = "active"                 # active | overnight | profit
    horizon_hours: float = 4.0
    liquidation_hours: float = 4.0       # Away: selling window after return
    capture: float = DEFAULT_CAPTURE
    strict: bool = False
    # Active / Max profit: the buy stays open for this share of the horizon,
    # then its remainder is cancelled so the sell has time left. A policy
    # assumption applied identically to every ranking method.
    buy_cutoff_fraction: float = 0.5
    seed: int = 20261113


@dataclass(frozen=True)
class Outcome:
    qty: int
    bought: int
    sold: int
    dumped: int
    pnl: float
    capital: int                 # coins the offer locks when placed
    capital_gp_hours: float      # integral of coins + inventory at cost
    slot_hours: float
    completed: bool              # whole quantity bought and sold in time
    completion_seconds: Optional[float]
    buy_seconds: Optional[float]     # whole quantity bought
    first_fill_seconds: Optional[float]
    dump_price: Optional[int]
    truncated: bool = False      # the panel ended before the deadline
    pnl_patient: float = 0.0     # leftover valued at the next instant-buy price


def _draw(volume: np.ndarray, capture: float, seed: int, item_id: int,
          t: int, side: int) -> np.ndarray:
    rng = np.random.default_rng([int(seed), int(item_id), int(t), side])
    return rng.binomial(volume.astype(np.int64), min(1.0, max(0.0, capture)))


def _capped_buys(capacity: np.ndarray, qty: int,
                 limit: Optional[int]) -> np.ndarray:
    """Cumulative units bought, honouring the per-window buy limit."""
    bought = np.zeros(capacity.shape[0], dtype=np.int64)
    done = 0
    for start in range(0, capacity.shape[0], LIMIT_WINDOW_BUCKETS):
        window = capacity[start:start + LIMIT_WINDOW_BUCKETS]
        room = qty - done if limit is None else min(qty - done, int(limit))
        filled = np.minimum(room, np.cumsum(window))
        bought[start:start + window.shape[0]] = done + filled
        done += int(filled[-1]) if filled.size else 0
    return bought


def simulate(panel: Panel, offer: Offer, t: int, config: SimConfig) -> Outcome:
    mode = config.mode
    horizon = int(round(config.horizon_hours * BUCKETS_PER_HOUR))
    if mode == "overnight":
        buy_until = horizon
        sell_from = horizon
        total = horizon + int(round(config.liquidation_hours * BUCKETS_PER_HOUR))
    else:
        buy_until = max(1, int(horizon * config.buy_cutoff_fraction))
        sell_from = 0
        total = horizon

    future = panel.future_5m(offer.item_id, t,
                             (total + DUMP_LOOKAHEAD_BUCKETS[1]) * STEP_5M)
    available = future["lp"].shape[0]
    n = min(total, available)
    truncated = available < total
    qty = max(0, int(offer.qty))
    unit_capital = engine.unit_capital(offer.buy, offer.sell, offer.bond)
    capital = qty * unit_capital
    if qty <= 0 or n <= 0:
        return Outcome(qty, 0, 0, 0, 0.0, capital, 0.0, 0.0, False, None, None,
                       None, None, truncated, 0.0)

    lp, lv = future["lp"][:n], future["lv"][:n]
    hp, hv = future["hp"][:n], future["hv"][:n]
    index = np.arange(n)

    if config.strict:
        buy_cross = (lv > 0) & (lp < offer.buy)
        sell_cross = (hv > 0) & (hp > offer.sell)
    else:
        buy_cross = (lv > 0) & (lp <= offer.buy)
        sell_cross = (hv > 0) & (hp >= offer.sell)
    buy_capacity = (_draw(lv, config.capture, config.seed, offer.item_id, t, 0)
                    * (buy_cross & (index < buy_until)))
    sell_capacity = (_draw(hv, config.capture, config.seed, offer.item_id, t, 1)
                     * (sell_cross & (index >= sell_from)))

    bought = _capped_buys(buy_capacity, qty, offer.limit)
    # Units sold by the end of bucket j: S_j = min(B_{j-1}, S_{j-1} + c_j).
    # Unrolled: S_j = C_j + min(0, min_{k<=j}(B_{k-1} - C_k)), C = cumsum(c).
    previous = np.concatenate(([0], bought[:-1]))
    cumulative = np.cumsum(sell_capacity)
    sold = cumulative + np.minimum(0, np.minimum.accumulate(previous - cumulative))

    total_bought, total_sold = int(bought[-1]), int(sold[-1])
    leftover = total_bought - total_sold
    dump_price = patient_price = None
    if leftover > 0:
        dump_price = _exit_price(future, n, "l")
        patient_price = _exit_price(future, n, "h") or dump_price
    sold_proceeds = total_sold * engine.net_revenue(
        offer.sell, offer.tax_exempt, offer.bond)

    def value(price: Optional[int]) -> float:
        left = (leftover * engine.net_revenue(price, offer.tax_exempt,
                                              offer.bond)
                if leftover > 0 and price else 0)
        return float(sold_proceeds + left - total_bought * offer.buy)
    pnl = value(dump_price)
    # Never better than selling at the listed price would have been.
    pnl_patient = value(min(patient_price, offer.sell)
                        if patient_price else dump_price)

    # State at the START of each bucket: what was true when it opened.
    bought_before = previous
    sold_before = np.concatenate(([0], sold[:-1]))
    inventory_before = bought_before - sold_before
    buy_open = (index < buy_until) & (bought_before < qty)
    locked = (np.where(buy_open, (qty - bought_before) * offer.buy, 0)
              + inventory_before * offer.buy)
    if mode == "overnight":
        # Nobody is at the keyboard: the slot is held for the whole absence,
        # then until the inventory is gone or the selling window ends.
        occupied = (index < horizon) | (inventory_before > 0)
    else:
        occupied = buy_open | (inventory_before > 0)
    last = int(np.max(np.nonzero(occupied)[0])) + 1 if occupied.any() else 1
    slot_hours = last / BUCKETS_PER_HOUR
    capital_gp_hours = float(locked[:last].sum()) / BUCKETS_PER_HOUR

    completed = total_sold >= qty
    return Outcome(
        qty=qty, bought=total_bought, sold=total_sold, dumped=leftover,
        pnl=pnl, capital=capital, capital_gp_hours=capital_gp_hours,
        slot_hours=slot_hours, completed=completed,
        completion_seconds=_first(sold >= qty) if completed else None,
        buy_seconds=_first(bought >= qty) if total_bought >= qty else None,
        first_fill_seconds=_first(bought > 0) if total_bought > 0 else None,
        dump_price=dump_price, truncated=truncated, pnl_patient=pnl_patient)


def _first(mask: np.ndarray) -> float:
    return float((int(np.argmax(mask)) + 1) * STEP_5M)


def _exit_price(future, n: int, side: str) -> Optional[int]:
    """Price after the deadline on one side: the next traded hour's VWAP,
    widening to six hours, then the last trade inside the offer's window."""
    prices, volumes = future[side + "p"], future[side + "v"]
    for ahead in DUMP_LOOKAHEAD_BUCKETS:
        price = prices[n:n + ahead].astype(np.float64)
        volume = volumes[n:n + ahead].astype(np.float64)
        if volume.sum() > 0:
            return int(round(float((price * volume).sum() / volume.sum())))
    traded = np.nonzero(volumes[:n] > 0)[0]
    return int(prices[traded[-1]]) if traded.size else None
