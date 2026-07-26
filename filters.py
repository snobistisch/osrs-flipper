"""Filter pipeline: raw market data in, ranked executable flips out.

The ranking is by expected value per offer slot, not by quoted margin. A
quoted margin is what you earn if both legs fill at the quoted prices; the
gates and discounts here exist because that often does not happen.

api.py already validated shapes at the boundary; here Items/Quotes/Activity
are well-typed but prices and timestamps can still be None, and items can be
missing from /mapping, /5m, or /1h.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional, Tuple, Union

import engine
from api import Activity, Item, Quote


@dataclass(frozen=True)
class FilterConfig:
    capital: int = 1_000_000       # gp available to invest, across all slots
    slots: int = engine.F2P_SLOTS  # concurrent offers you can run
    include_members: bool = False
    max_quote_age: int = 300       # s since the OLDER side of the /latest quote
    min_thin_volume_1h: int = 120  # units/h on the thin side of the book
    min_roi: float = 0.01          # net margin / buy price
    min_undercut_depth: int = 1    # 0 lets in flips you cannot queue-jump


@dataclass(frozen=True)
class FlipRow:
    item_id: int
    name: str
    buy: int                 # conservative estimate of where your buy fills
    sell: int                # conservative estimate of where your sell fills
    latest_low: int          # raw last instant-sell from /latest
    latest_high: int         # raw last instant-buy from /latest
    tax: int
    margin: int              # per item, after tax, at the quoted prices
    roi: float
    limit: Optional[int]     # None = wiki publishes no buy limit
    thin_volume_1h: int
    qty_per_window: int
    capital_needed: int      # gp this flip ties up in one slot
    gross_profit: int        # margin * qty — the best case, before discounts
    undercut_depth: int      # gp of price improvement you can afford per side
    drift: float             # 5m mid vs 1h mid, as a fraction
    quote_age: int
    expected_gp: float       # gross profit after every discount
    gp_per_slot_hour: float  # the ranking metric
    warnings: Tuple[str, ...] = field(default=())
    # Filled by refine_with_history for the top candidates; None = not checked
    deep_checked: bool = False
    fill_share: Optional[float] = None   # binding leg's share of 14d volume
    fill_factor: Optional[float] = None  # the EV multiplier (floored)
    trend: Optional[float] = None        # recent vs prior multi-day VWAP
    momentum: Optional[float] = None     # the EV multiplier from trend
    baseline_low: Optional[int] = None   # 14d volume-weighted seller price
    median_mid: Optional[int] = None     # 14d median price level
    elevation: Optional[float] = None    # quote mid vs median; + = above
    volatility: Optional[float] = None   # median swing around the median
    level_factor: Optional[float] = None
    stability_factor: Optional[float] = None


# Rejection reasons, in the order the gates run. Every item in /latest lands
# in exactly one bucket, so the funnel always sums to len(quotes).
FUNNEL_STAGES = (
    "in /latest", "no mapping entry", "members-only", "null price side",
    "quote too old", "volume too thin", "roi too low", "no undercut room",
    "cannot afford one", "passed",
)


def rank_flips(
    items: Dict[int, Item],
    quotes: Dict[int, Quote],
    activity_5m: Dict[int, Activity],
    activity_1h: Dict[int, Activity],
    config: FilterConfig,
    now: float,
) -> Tuple[List[FlipRow], Dict[str, int]]:
    """Apply every gate to every quoted item; rank survivors by expected value."""
    rows: List[FlipRow] = []
    funnel = {stage: 0 for stage in FUNNEL_STAGES}
    funnel["in /latest"] = len(quotes)
    per_slot = engine.capital_per_slot(config.capital, config.slots)
    for item_id, quote in quotes.items():
        result = _evaluate(item_id, quote, items.get(item_id),
                           activity_5m.get(item_id), activity_1h.get(item_id),
                           config, per_slot, now)
        if isinstance(result, str):
            funnel[result] += 1
        else:
            funnel["passed"] += 1
            rows.append(result)
    rows.sort(key=lambda r: r.gp_per_slot_hour, reverse=True)
    return rows, funnel


def _mid(activity: Optional[Activity]) -> Optional[float]:
    """Midpoint of a bucket, or whichever side traded if only one did."""
    if activity is None:
        return None
    high, low = activity.avg_high, activity.avg_low
    if high is not None and low is not None:
        return (high + low) / 2
    return high if high is not None else low


def _evaluate(
    item_id: int,
    quote: Quote,
    item: Optional[Item],
    act_5m: Optional[Activity],
    act_1h: Optional[Activity],
    config: FilterConfig,
    per_slot: int,
    now: float,
) -> Union[FlipRow, str]:
    """One item through all gates: a FlipRow, or the name of the failed gate."""
    if item is None:
        return "no mapping entry"
    if item.members and not config.include_members:
        return "members-only"
    if (quote.high is None or quote.low is None
            or quote.high_time is None or quote.low_time is None
            or quote.low <= 0):
        return "null price side"
    age = int(now - min(quote.high_time, quote.low_time))
    if age > config.max_quote_age:
        return "quote too old"

    high_vol_1h = act_1h.high_volume if act_1h else 0
    low_vol_1h = act_1h.low_volume if act_1h else 0
    thin_volume = min(high_vol_1h, low_vol_1h)
    if thin_volume < config.min_thin_volume_1h:
        return "volume too thin"

    ref_low = engine.reference_price(
        act_5m.avg_low if act_5m else None,
        act_5m.low_volume if act_5m else 0,
        act_1h.avg_low if act_1h else None, low_vol_1h)
    ref_high = engine.reference_price(
        act_5m.avg_high if act_5m else None,
        act_5m.high_volume if act_5m else 0,
        act_1h.avg_high if act_1h else None, high_vol_1h)
    buy, sell = engine.executable_prices(quote.low, quote.high, ref_low, ref_high)

    tax_exempt = item_id in engine.TAX_EXEMPT_ITEM_IDS
    item_roi = engine.roi(buy, sell, tax_exempt)
    if item_roi < config.min_roi:
        return "roi too low"

    depth = engine.undercut_depth(buy, sell, tax_exempt)
    if depth < config.min_undercut_depth:
        return "no undercut room"

    affordable = per_slot // buy
    if affordable == 0:
        return "cannot afford one"

    margin = engine.net_margin(buy, sell, tax_exempt)
    qty = engine.flippable_qty(
        item.limit,
        engine.window_volume(high_vol_1h, low_vol_1h,
                             engine.HOUR_BUCKETS_PER_WINDOW),
        affordable)
    gross = engine.profit_per_window(margin, qty)
    drift = engine.price_drift(_mid(act_5m), _mid(act_1h))
    expected = engine.expected_value(margin, qty, depth, drift, age)

    return FlipRow(
        item_id=item_id, name=item.name, buy=buy, sell=sell,
        latest_low=quote.low, latest_high=quote.high,
        tax=engine.ge_tax(sell, tax_exempt), margin=margin, roi=item_roi,
        limit=item.limit, thin_volume_1h=thin_volume, qty_per_window=qty,
        capital_needed=qty * buy, gross_profit=gross, undercut_depth=depth,
        drift=drift, quote_age=age, expected_gp=expected,
        gp_per_slot_hour=engine.gp_per_slot_hour(expected),
        warnings=_warnings(depth, drift, affordable, qty, item.limit),
    )


def refine_with_history(
    rows: List[FlipRow],
    fetch_history: Callable[[int], Optional[List[dict]]],
    top_k: int = 15,
) -> Tuple[List[FlipRow], int]:
    """Re-score the top candidates against ~14 days of price history.

    Only the top_k rows are checked: /timeseries is a per-item route and the
    wiki forbids sweeping it across all items, so deep data is spent on the
    flips that stage 1 already likes. fetch_history is injected (item_id ->
    list of wiki timeseries buckets, or None on failure) so tests can feed
    synthetic series. Returns the re-sorted list and how many were refined.
    """
    refined_rows: List[FlipRow] = []
    refined_count = 0
    for index, row in enumerate(rows):
        if index >= top_k:
            refined_rows.append(row)
            continue
        points = fetch_history(row.item_id)
        view = (engine.history_view(points, row.buy, row.sell)
                if points else None)
        if view is None:
            refined_rows.append(replace(row, warnings=row.warnings + (
                "no usable 14-day history — ranked on intraday data only",)))
            continue
        refined_count += 1
        expected = (row.expected_gp * view.fill_factor * view.momentum
                    * view.level * view.stability)
        binding = min(view.buy_fill_share, view.sell_fill_share)
        refined_rows.append(replace(
            row,
            deep_checked=True, fill_share=binding,
            fill_factor=view.fill_factor, trend=view.trend,
            momentum=view.momentum, baseline_low=view.baseline_low,
            median_mid=view.median_mid, elevation=view.elevation,
            volatility=view.volatility, level_factor=view.level,
            stability_factor=view.stability,
            expected_gp=expected,
            gp_per_slot_hour=engine.gp_per_slot_hour(expected),
            warnings=row.warnings + _history_warnings(view),
        ))
    refined_rows.sort(key=lambda r: r.gp_per_slot_hour, reverse=True)
    return refined_rows, refined_count


def _history_warnings(view: "engine.HistoryView") -> Tuple[str, ...]:
    notes = []
    if view.elevation >= 0.05:
        notes.append("trading {:.0%} above its 14-day median — spike or "
                     "manipulation, expect reversion".format(view.elevation))
    if view.volatility >= 0.05:
        notes.append("price swings ±{:.0%} around its 14-day median — risky "
                     "to hold".format(view.volatility))
    if view.dislocation <= -0.10:
        notes.append("buy price {:.0%} below the 14-day average — only the "
                     "dump fills there".format(abs(view.dislocation)))
    binding = min(view.buy_fill_share, view.sell_fill_share)
    if binding <= 0.25:
        notes.append("only {:.0%} of 14-day volume traded at your prices"
                     .format(binding))
    if view.trend >= 0.03:
        notes.append("risen {:.0%} over recent days — don't chase, wait for "
                     "it to settle".format(view.trend))
    elif view.trend <= -0.03:
        notes.append("falling {:.0%} over recent days"
                     .format(abs(view.trend)))
    return tuple(notes)


def _warnings(depth: int, drift: float, affordable: int, qty: int,
              limit: Optional[int]) -> Tuple[str, ...]:
    """Plain-language reasons this flip might not pay what it quotes."""
    notes = []
    if depth == 0:
        notes.append("no room to outbid the queue — you wait your turn")
    elif depth <= 2:
        notes.append("only {} gp of undercut room".format(depth))
    if drift <= -0.02:
        notes.append("price falling {:.1%} — your buy fills, your sell may not"
                     .format(abs(drift)))
    elif drift >= 0.02:
        notes.append("price rising {:.1%} — your buy may not fill".format(drift))
    if qty and affordable <= qty:
        notes.append("capital-bound, not limit-bound — a bigger slot buys more")
    if limit is None:
        notes.append("no published buy limit")
    return tuple(notes)
