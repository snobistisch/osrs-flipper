"""Filter pipeline: raw market data in, ranked executable flips out.

api.py already validated shapes at the boundary; here Items/Quotes/Activity
are well-typed but prices and timestamps can still be None, and items can be
missing from /mapping, /5m, or /1h.

Pricing: margins are computed from engine.executable_prices — a conservative
blend of the /latest quote with the volume-weighted 5m (fallback 1h) averages
— not from /latest alone, which one outlier trade can set anywhere.
Throughput: estimated from the 1h volumes (x4 per window); a single 5m bucket
is too noisy to extrapolate x48.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import engine
from api import Activity, Item, Quote


@dataclass(frozen=True)
class FilterConfig:
    capital: int = 1_000_000       # gp available to invest
    include_members: bool = False  # user plays F2P
    max_quote_age: int = 300       # s since the OLDER side of the /latest quote
    min_thin_volume_1h: int = 120  # units/h on the thin side of the book
    min_roi: float = 0.01          # net margin / buy price


@dataclass(frozen=True)
class FlipRow:
    item_id: int
    name: str
    buy: int                 # conservative estimate of where your buy fills
    sell: int                # conservative estimate of where your sell fills
    latest_low: int          # raw last instant-sell from /latest
    latest_high: int         # raw last instant-buy from /latest
    tax: int
    margin: int
    roi: float
    limit: Optional[int]     # None = wiki publishes no buy limit
    thin_volume_1h: int
    qty_per_window: int
    profit_per_window: int
    quote_age: int
    score: float


# Rejection reasons, in the order the gates run. Every item in /latest lands
# in exactly one bucket, so the funnel always sums to len(quotes).
FUNNEL_STAGES = (
    "in /latest", "no mapping entry", "members-only", "null price side",
    "quote too old", "volume too thin", "roi too low", "cannot afford one",
    "passed",
)


def rank_flips(
    items: Dict[int, Item],
    quotes: Dict[int, Quote],
    activity_5m: Dict[int, Activity],
    activity_1h: Dict[int, Activity],
    config: FilterConfig,
    now: float,
) -> Tuple[List[FlipRow], Dict[str, int]]:
    """Apply every gate to every quoted item; rank survivors by score."""
    rows: List[FlipRow] = []
    funnel = {stage: 0 for stage in FUNNEL_STAGES}
    funnel["in /latest"] = len(quotes)
    for item_id, quote in quotes.items():
        result = _evaluate(item_id, quote, items.get(item_id),
                           activity_5m.get(item_id), activity_1h.get(item_id),
                           config, now)
        if isinstance(result, str):
            funnel[result] += 1
        else:
            funnel["passed"] += 1
            rows.append(result)
    rows.sort(key=lambda r: r.score, reverse=True)
    return rows, funnel


def _evaluate(
    item_id: int,
    quote: Quote,
    item: Optional[Item],
    act_5m: Optional[Activity],
    act_1h: Optional[Activity],
    config: FilterConfig,
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
    buy, sell = engine.executable_prices(
        quote.low, quote.high,
        act_5m.avg_low if act_5m else None,
        act_5m.avg_high if act_5m else None,
        act_1h.avg_low if act_1h else None,
        act_1h.avg_high if act_1h else None)
    tax_exempt = item_id in engine.TAX_EXEMPT_ITEM_IDS
    margin = engine.net_margin(buy, sell, tax_exempt)
    item_roi = engine.roi(buy, sell, tax_exempt)
    if item_roi < config.min_roi:
        return "roi too low"
    affordable = config.capital // buy
    if affordable == 0:
        return "cannot afford one"
    qty = engine.flippable_qty(
        item.limit,
        engine.window_volume(high_vol_1h, low_vol_1h,
                             engine.HOUR_BUCKETS_PER_WINDOW),
        affordable)
    profit = engine.profit_per_window(margin, qty)
    return FlipRow(
        item_id=item_id, name=item.name, buy=buy, sell=sell,
        latest_low=quote.low, latest_high=quote.high,
        tax=engine.ge_tax(sell, tax_exempt), margin=margin, roi=item_roi,
        limit=item.limit, thin_volume_1h=thin_volume, qty_per_window=qty,
        profit_per_window=profit, quote_age=age,
        score=engine.score(profit, age),
    )
