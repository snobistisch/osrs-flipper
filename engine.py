"""Pure flip math. No I/O, no API types — everything is unit-testable.

The central idea: a quoted margin is not profit. It is profit *if* both legs
of the flip actually fill, and the Grand Exchange gives you no guarantee of
that. Everything below exists to turn a quoted margin into an expected value.

Conventions:
- The buy side of a flip fills near the instant-sell price ("low"); the sell
  side fills near the instant-buy price ("high").
- Tax rules as of 29 May 2025: seller pays 2% rounded down, capped at 5m per
  item. Sub-50 gp items are untaxed because floor(price * 0.02) is 0 there.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

TAX_RATE = 0.02
TAX_CAP = 5_000_000

# Old school bond — exempt from GE tax entirely.
TAX_EXEMPT_ITEM_IDS = frozenset({13190})

FIVE_MIN_BUCKETS_PER_WINDOW = 48  # 4h buy-limit window / 5-minute bucket
HOUR_BUCKETS_PER_WINDOW = 4       # 4h buy-limit window / 1-hour bucket
WINDOW_HOURS = 4                  # the buy-limit window

# Offer slots cap how many flips you can run at once — the real bottleneck
# long before gp is. Free-to-play gets three; members get eight.
F2P_SLOTS = 3
MEMBER_SLOTS = 8

MAX_CASH_STACK = 2_147_483_647    # the game's coin cap

_GP_SUFFIXES = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


def parse_gp(text: str) -> int:
    """Parse a gp amount the way players write it: '250k', '1.5m', '2b',
    '1,000,000', '500k gp'. Raises ValueError for anything else."""
    cleaned = (text.strip().lower()
               .replace(",", "").replace("_", "").replace(" ", ""))
    if cleaned.endswith("gp"):
        cleaned = cleaned[:-2]
    if not cleaned:
        raise ValueError("empty amount")
    multiplier = 1
    if cleaned[-1] in _GP_SUFFIXES:
        multiplier = _GP_SUFFIXES[cleaned[-1]]
        cleaned = cleaned[:-1]
    try:
        # decimals ('1.5') only make sense together with a k/m/b suffix
        value = float(cleaned) if multiplier > 1 else int(cleaned)
    except ValueError:
        raise ValueError("not a gp amount: {!r}".format(text)) from None
    amount = int(round(value * multiplier))
    if amount <= 0:
        raise ValueError("amount must be positive")
    return amount


def format_gp(amount: int) -> str:
    """Format gp the way players read it: '1.5m', '250k', '999'. Rounds to
    one decimal, so use the exact number wherever precision matters."""
    for suffix, size in (("b", 10 ** 9), ("m", 10 ** 6), ("k", 10 ** 3)):
        if amount >= size:
            text = "{:.1f}".format(amount / size).rstrip("0").rstrip(".")
            return text + suffix
    return "{:,}".format(amount)


def reference_price(
    avg_5m: Optional[int], volume_5m: int,
    avg_1h: Optional[int], volume_1h: int,
) -> Optional[int]:
    """Volume-weighted reference price for one side of the book.

    The 5-minute average is fresher, but it can rest on a handful of trades:
    13 units dumped cheap will set it as readily as 13,000 will. The 1-hour
    average has real volume behind it but lags. Weighting each bucket by its
    own traded volume lets a busy 5-minute bucket move the estimate while a
    tiny one barely budges it. Returns None when neither side ever traded.
    """
    parts = [(avg, vol) for avg, vol in ((avg_5m, volume_5m), (avg_1h, volume_1h))
             if avg is not None and vol > 0]
    if not parts:
        # priced at some point but nothing traded in either bucket
        return avg_5m if avg_5m is not None else avg_1h
    total_volume = sum(vol for _, vol in parts)
    return int(round(sum(avg * vol for avg, vol in parts) / total_volume))


def executable_prices(
    latest_low: int,
    latest_high: int,
    ref_low: Optional[int] = None,
    ref_high: Optional[int] = None,
) -> Tuple[int, int]:
    """Conservative (buy, sell) estimate for what will actually fill.

    /latest is the single most recent trade per side, so one outlier offer can
    set it anywhere. Take the pessimistic combination per side: you buy at the
    HIGHER of (last instant-sell, reference low) and sell at the LOWER of
    (last instant-buy, reference high).
    """
    buy = latest_low if ref_low is None else max(latest_low, ref_low)
    sell = latest_high if ref_high is None else min(latest_high, ref_high)
    return buy, sell


def ge_tax(sell_price: int, tax_exempt: bool = False) -> int:
    """Tax the seller pays on one item."""
    if tax_exempt:
        return 0
    return min(TAX_CAP, math.floor(sell_price * TAX_RATE))


def net_margin(buy_price: int, sell_price: int, tax_exempt: bool = False) -> int:
    """Profit on one item after tax. Negative when the spread can't cover tax."""
    return (sell_price - ge_tax(sell_price, tax_exempt)) - buy_price


def roi(buy_price: int, sell_price: int, tax_exempt: bool = False) -> float:
    """Net margin as a fraction of capital tied up per item."""
    return net_margin(buy_price, sell_price, tax_exempt) / buy_price


def window_volume(high_volume: int, low_volume: int,
                  buckets_per_window: int) -> int:
    """Estimated flippable units per 4h window.

    A flip needs both sides of the book: someone instant-selling to fill your
    buy, someone instant-buying to fill your sell. The thin side of the bucket
    bounds throughput; extrapolated over the window (48 for 5m buckets, 4 for
    1h buckets).
    """
    return min(high_volume, low_volume) * buckets_per_window


def flippable_qty(buy_limit, volume: int, affordable=None) -> int:
    """Units realistically flippable in one window.

    buy_limit None means the wiki doesn't publish a limit — leave uncapped
    rather than guessing. affordable caps by capital (capital // buy_price).
    """
    qty = volume
    if buy_limit is not None:
        qty = min(qty, buy_limit)
    if affordable is not None:
        qty = min(qty, affordable)
    return max(qty, 0)


def profit_per_window(margin: int, qty: int) -> int:
    """Expected gp per 4h window at the given per-item margin."""
    return margin * qty


def freshness(age_seconds: float, half_life: float = 600.0) -> float:
    """Confidence in a quote: 1.0 when brand new, halving every half_life s.

    /latest reports the LAST trade on each side, which can be hours old; a
    wide margin on stale data usually means a dead item, not free money.
    """
    if age_seconds <= 0:
        return 1.0
    return 0.5 ** (age_seconds / half_life)


# ---------------------------------------------------------------------------
# Queue position — why a wide-volume, one-tick spread is a trap
# ---------------------------------------------------------------------------

def undercut_depth(buy: int, sell: int, tax_exempt: bool = False) -> int:
    """How many gp of price improvement you can afford on each side at once
    while the flip still profits.

    The Grand Exchange matches on price first, then on offer age: at the same
    price, offers that are days old take near-absolute priority. So there are
    exactly two ways to get filled — outbid the queue, or wait behind a queue
    you cannot see and cannot measure.

    Depth is how much room you have to do the first. Depth 0 means every gp of
    price improvement costs more than the flip earns, so you have no way to
    jump ahead: your offer sits behind everyone else's at the same tick. Air
    runes quoted at 5/6 are the canonical case — buying at 6 to sell at 5 is a
    guaranteed loss, so a 1 gp margin can only ever be won by waiting.

    Leather quoted at 173/192 has depth 7: bidding 180 to sell at 185 still
    clears 2 gp after tax, so you can pay for priority and still profit.
    """
    if net_margin(buy, sell, tax_exempt) <= 0:
        return 0
    lo, hi = 0, max(0, (sell - buy) // 2 + 1)
    while lo < hi:                      # binary search: margin falls with k
        mid = (lo + hi + 1) // 2
        if net_margin(buy + mid, sell - mid, tax_exempt) > 0:
            lo = mid
        else:
            hi = mid - 1
    return lo


def queue_factor(depth: int) -> float:
    """Fraction of the quoted margin you should expect to actually capture,
    given how much room you have to buy your way to the front of the queue.

    Depth 0 keeps a small non-zero weight rather than zero: those flips do
    sometimes fill, you just cannot influence whether they do.
    """
    if depth <= 0:
        return 0.15
    return 1.0 - math.exp(-depth / 3.0)


# ---------------------------------------------------------------------------
# Adverse selection — passive orders fill when you least want them to
# ---------------------------------------------------------------------------

def price_drift(mid_5m: Optional[float], mid_1h: Optional[float]) -> float:
    """Recent momentum, as a fraction of price. Negative means falling."""
    if mid_5m is None or mid_1h is None or mid_1h <= 0:
        return 0.0
    return (mid_5m - mid_1h) / mid_1h


def drift_factor(drift: float) -> float:
    """Discount for trading against a moving market.

    A resting buy offer fills fastest exactly when the price is falling —
    someone is dumping into it — and then the sell leg is stranded above the
    market. That asymmetry is why passive orders realise less than they quote.
    A falling market is penalised harder than a rising one because you are the
    one holding inventory between the two legs.
    """
    penalty = 8.0 * abs(drift) if drift < 0 else 4.0 * drift
    return max(0.2, 1.0 - penalty)


# ---------------------------------------------------------------------------
# Expected value
# ---------------------------------------------------------------------------

def expected_value(margin: int, qty: int, depth: int, drift: float,
                   age_seconds: float) -> float:
    """Expected gp from one 4-hour window on this item.

    The quoted margin times the quantity is the best case: both legs fill at
    the quoted prices. Each factor below is a reason that does not happen.
    """
    return (margin * qty
            * queue_factor(depth)
            * drift_factor(drift)
            * freshness(age_seconds))


# ---------------------------------------------------------------------------
# Multi-day history — the last print is not the market
# ---------------------------------------------------------------------------
# Intraday data cannot tell a real spread from a transient dump: a few hundred
# salmon sold at 30 gp in the last minutes looks like a buy at 30, but if the
# last two weeks of seller volume went at 40, a large offer at 30 fills only
# against that one dumper and then sits. These functions read ~14 days of 6h
# timeseries buckets and answer: at your prices, what share of the market's
# real volume would actually have filled you, and which way is it moving?

HISTORY_TIMESTEP = "6h"
HISTORY_WINDOW_BUCKETS = 56       # 14 days of 6h buckets
MIN_HISTORY_BUCKETS = 8           # fewer traded buckets: refuse to refine
RECENT_TREND_BUCKETS = 12         # ~3 days
FILL_FLOOR = 0.05                 # even "never traded there" keeps 5%
FILL_TOLERANCE = 0.01             # prices within 1% count as reachable
LEVEL_TOLERANCE = 0.03            # this far above the median is still normal
LEVEL_FLOOR = 0.10
STABILITY_TOLERANCE = 0.02        # swings within ±2% of the median are calm
STABILITY_FLOOR = 0.30


class HistoryView:
    """Multi-day metrics for one item at one (buy, sell) estimate."""
    __slots__ = ("buckets", "baseline_low", "baseline_high", "buy_fill_share",
                 "sell_fill_share", "fill_factor", "trend", "momentum",
                 "dislocation", "median_mid", "elevation", "volatility",
                 "level", "stability")

    def __init__(self, buckets, baseline_low, baseline_high, buy_fill_share,
                 sell_fill_share, fill_factor, trend, momentum, dislocation,
                 median_mid, elevation, volatility, level, stability):
        self.buckets = buckets
        self.baseline_low = baseline_low
        self.baseline_high = baseline_high
        self.buy_fill_share = buy_fill_share
        self.sell_fill_share = sell_fill_share
        self.fill_factor = fill_factor
        self.trend = trend
        self.momentum = momentum
        self.dislocation = dislocation
        self.median_mid = median_mid
        self.elevation = elevation
        self.volatility = volatility
        self.level = level
        self.stability = stability


def _weighted_avg(pairs: List[Tuple[float, int]]) -> Optional[float]:
    total = sum(vol for _, vol in pairs)
    if total <= 0:
        return None
    return sum(price * vol for price, vol in pairs) / total


def _bucket_vwap(points: List[dict]) -> Optional[float]:
    """Volume-weighted mid price over a run of buckets."""
    pairs = []
    for p in points:
        high, low = p.get("avgHighPrice"), p.get("avgLowPrice")
        hv = p.get("highPriceVolume") or 0
        lv = p.get("lowPriceVolume") or 0
        value = (high or 0) * hv + (low or 0) * lv
        vol = (hv if high is not None else 0) + (lv if low is not None else 0)
        if vol > 0:
            pairs.append((value / vol, vol))
    return _weighted_avg(pairs)


def momentum_factor(trend: float) -> float:
    """Bounded EV multiplier from the multi-day trend.

    Decline is penalised: you hold depreciating inventory between the legs.
    A rise earns NO bonus: from price data alone, a genuine update-driven
    demand shift and a merch-clan pump are indistinguishable — both are a
    rising price with rising volume — so rewarding rises means chasing
    manipulations. The safe entry is after the price settles at its new
    level, which the level and stability factors recognise on their own.
    """
    if trend >= 0:
        return 1.0
    return max(0.5, 1 + 3.0 * trend)


def level_factor(elevation: float) -> float:
    """Mean-reversion discount for trading above the item's normal level.

    Supply and demand for game commodities are roughly constant, so price
    shocks revert toward the multi-day median. Buying above that median puts
    the reversion against the inventory you hold — and a price spiked above
    its median is the classic manipulation signature (the "margin trap").
    Below the median is not penalised: buying under the normal level is where
    a flipper wants to be, and the fill and momentum factors already guard
    the falling-knife case.
    """
    if elevation <= LEVEL_TOLERANCE:
        return 1.0
    return max(LEVEL_FLOOR, math.exp(-8.0 * (elevation - LEVEL_TOLERANCE)))


def stability_factor(volatility: float) -> float:
    """Discount for jumpy prices.

    A flip is a round trip that holds inventory in between; the wider an item
    swings around its median, the more the trip can eat the margin. Stable
    staples inside a settled range are the flipper's bread and butter —
    that is where buy-low/sell-high within the band actually works.
    """
    if volatility <= STABILITY_TOLERANCE:
        return 1.0
    return max(STABILITY_FLOOR, 1 - 8.0 * (volatility - STABILITY_TOLERANCE))


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def history_view(points: List[dict], buy: int, sell: int) -> Optional[HistoryView]:
    """Read a slice of /timeseries buckets (wiki key names, oldest first).

    Returns None when fewer than MIN_HISTORY_BUCKETS buckets traded — too
    little history to say anything, so the caller keeps its stage-1 numbers.
    """
    points = points[-HISTORY_WINDOW_BUCKETS:]
    lows, highs = [], []
    buckets = 0
    for p in points:
        if not isinstance(p, dict):
            continue
        hv = p.get("highPriceVolume") or 0
        lv = p.get("lowPriceVolume") or 0
        if hv > 0 or lv > 0:
            buckets += 1
        if p.get("avgLowPrice") is not None and lv > 0:
            lows.append((p["avgLowPrice"], lv))
        if p.get("avgHighPrice") is not None and hv > 0:
            highs.append((p["avgHighPrice"], hv))
    if buckets < MIN_HISTORY_BUCKETS:
        return None

    baseline_low = _weighted_avg(lows)
    baseline_high = _weighted_avg(highs)

    # Fill shares are computed on DETRENDED prices. A seller's aggressiveness
    # is their price relative to the market at that moment, so each bucket's
    # prices are divided by that bucket's own mid, and your prices by the
    # current quote mid. A dump stays visible (27% under its market is a dump
    # whenever it happened), but an item marching upward is not punished for
    # trading above last week's absolute prices. The 1% tolerance treats
    # prices within a tick-or-so as reachable.
    mid_now = (buy + sell) / 2
    low_ratios, high_ratios, mids = [], [], []
    for p in points:
        if not isinstance(p, dict):
            continue
        high_price, low_price = p.get("avgHighPrice"), p.get("avgLowPrice")
        hv = p.get("highPriceVolume") or 0
        lv = p.get("lowPriceVolume") or 0
        value = ((high_price or 0) * hv) + ((low_price or 0) * lv)
        vol = (hv if high_price is not None else 0) + \
              (lv if low_price is not None else 0)
        if vol <= 0:
            continue
        bucket_mid = value / vol
        mids.append(bucket_mid)
        if low_price is not None and lv > 0:
            low_ratios.append((low_price / bucket_mid, lv))
        if high_price is not None and hv > 0:
            high_ratios.append((high_price / bucket_mid, hv))

    low_total = sum(v for _, v in low_ratios)
    high_total = sum(v for _, v in high_ratios)
    buy_ratio = buy / mid_now * (1 + FILL_TOLERANCE)
    sell_ratio = sell / mid_now * (1 - FILL_TOLERANCE)
    buy_fill_share = (sum(v for r, v in low_ratios if r <= buy_ratio)
                      / low_total if low_total > 0 else 0.0)
    sell_fill_share = (sum(v for r, v in high_ratios if r >= sell_ratio)
                       / high_total if high_total > 0 else 0.0)
    fill_factor = max(FILL_FLOOR, min(1.0, min(buy_fill_share, sell_fill_share)))

    recent = _bucket_vwap(points[-RECENT_TREND_BUCKETS:])
    prior = _bucket_vwap(points[:-RECENT_TREND_BUCKETS])
    trend = ((recent - prior) / prior
             if recent is not None and prior is not None and prior > 0 else 0.0)

    dislocation = ((buy - baseline_low) / baseline_low
                   if baseline_low is not None and baseline_low > 0 else 0.0)

    # Where does today's quote sit against the item's normal level, and how
    # calm is that level? The median of the bucket mids is robust: a few
    # spiked buckets barely move it, so a pump shows up as a large elevation
    # rather than as a new normal.
    median_mid = _median(mids)
    elevation = ((mid_now - median_mid) / median_mid
                 if median_mid is not None and median_mid > 0 else 0.0)
    volatility = 0.0
    if median_mid is not None and median_mid > 0:
        deviation = _median([abs(m - median_mid) for m in mids])
        volatility = (deviation / median_mid) if deviation is not None else 0.0

    return HistoryView(
        buckets=buckets,
        baseline_low=int(round(baseline_low)) if baseline_low is not None else None,
        baseline_high=int(round(baseline_high)) if baseline_high is not None else None,
        buy_fill_share=buy_fill_share, sell_fill_share=sell_fill_share,
        fill_factor=fill_factor, trend=trend,
        momentum=momentum_factor(trend), dislocation=dislocation,
        median_mid=int(round(median_mid)) if median_mid is not None else None,
        elevation=elevation, volatility=volatility,
        level=level_factor(elevation), stability=stability_factor(volatility))


def gp_per_slot_hour(expected_gp: float) -> float:
    """Expected gp per offer slot per hour — the metric worth maximising.

    Offer slots, not gp, are the binding constraint: three in free-to-play,
    eight for members. A flip occupies one slot for the buy-limit window
    whether it earns 1 gp or 100k, so the question is never "which item has
    the biggest margin" but "what is the best use of a slot for four hours".
    """
    return expected_gp / WINDOW_HOURS


def capital_per_slot(capital: int, slots: int) -> int:
    """Gp to commit to any one flip.

    Putting the whole bank into the single best-looking item ignores that you
    have several slots and that buy limits cap what any one item can absorb.
    Splitting evenly is not optimal, but it is much closer than betting it all
    on the top row.
    """
    return max(1, capital // max(1, slots))
