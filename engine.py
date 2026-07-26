"""Pure flip math. No I/O, no API types — everything is unit-testable.

Conventions:
- The buy side of a flip fills near the instant-sell price ("low"); the sell
  side fills near the instant-buy price ("high").
- Tax rules as of 29 May 2025: seller pays 2% rounded down, capped at 5m per
  item. Sub-50 gp items are untaxed because floor(price * 0.02) is 0 there.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

TAX_RATE = 0.02
TAX_CAP = 5_000_000

# Old school bond — exempt from GE tax entirely.
TAX_EXEMPT_ITEM_IDS = frozenset({13190})

FIVE_MIN_BUCKETS_PER_WINDOW = 48  # 4h buy-limit window / 5-minute bucket
HOUR_BUCKETS_PER_WINDOW = 4       # 4h buy-limit window / 1-hour bucket

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


def score(profit_window: int, age_seconds: float) -> float:
    """Ranking score: expected 4h profit discounted by data staleness."""
    return profit_window * freshness(age_seconds)
