"""Screening pipeline: raw market data in, ranked executable flips out.

The old pipeline could only ever remove. Every stage was a gate that rejected
an item outright or a factor bounded above by 1.0, so an item the intraday
snapshot happened to misrepresent — a stale print, one thin bucket — was
eliminated before any deeper data could speak for it, and nothing downstream
could ever argue it back up. A filter that only subtracts cannot find edge; it
can only shorten the list.

This version separates three things the old one conflated:

  Structural gates    reasons an item is not a flip at all: no mapping entry,
                      a missing side of the quote, nothing traded, a margin
                      that does not survive tax, or one unit you cannot afford.
                      These reject.
  Scoring             everything else — ROI, undercut room, quote age, price
                      level, volatility — enters the score. A thin margin is
                      not disqualifying, it is worth less.
  View preferences    what the user asked to see. Applied last, after the whole
                      universe has been scored and shrunk, so narrowing the
                      view never changes the ranking of what remains.

Ranking is by expected gp per slot-hour after empirical-Bayes shrinkage. The
shrinkage matters more than any single factor: ranking several thousand noisy
estimates surfaces the largest errors, not the largest values.

api.py already validated shapes at the boundary; here Items/Quotes/Activity are
well-typed but prices and timestamps can still be None, and items can be
missing from /mapping, /5m, or /1h.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
import re
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple, Union

import engine
import exemptions
import merch
from api import Activity, Item, Quote


@dataclass(frozen=True)
class FilterConfig:
    # -- structural ---------------------------------------------------------
    capital: int = 1_000_000       # gp available to invest, across all slots
    account: engine.AccountType = engine.DEFAULT_ACCOUNT
    trade_mode: engine.TradeMode = engine.DEFAULT_TRADE_MODE
    overnight_hours: float = engine.DEFAULT_OVERNIGHT_HOURS
    nature_rune_cost: int = exemptions.NATURE_RUNE_FALLBACK
    calibration: engine.Calibration = engine.DEFAULT_CALIBRATION

    # -- view preferences, applied after scoring -----------------------------
    # All default to permissive. These used to be gates with opinionated
    # defaults (300s, 120 units/h, 1% ROI, 1 gp of undercut room), which meant
    # the tool never scored most of the game and its "shorter list" was mostly
    # a narrower one.
    max_quote_age: Optional[int] = None    # s since the OLDER /latest side
    min_thin_volume_1h: int = 0            # units/h on the thin side
    min_roi: float = 0.0                   # net margin / buy price
    min_undercut_depth: int = 0
    min_price: int = 1                     # gp per item, on the buy estimate
    max_price: Optional[int] = None        # None = no cap
    tax_free_only: bool = False            # only flips whose sell pays no tax
    # Hide bot-supplied f2p staples: cheap, high buy limit, free-to-play. They
    # rank well and clear fast, and some people would rather not trade against
    # a script whose supply curve answers a price rise by producing more. A
    # preference, so it hides rows like every other one here — the items are
    # still scored, and turning this on never reorders what is left.
    hide_botted: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "account", engine.AccountType(self.account))
        object.__setattr__(self, "trade_mode",
                           engine.TradeMode(self.trade_mode))
        if not 1.0 <= float(self.overnight_hours) <= 24.0:
            raise ValueError("overnight horizon must be between 1 and 24 hours")
        if (isinstance(self.capital, bool) or not isinstance(self.capital, int)
                or not 0 < self.capital <= engine.MAX_CASH_STACK):
            raise ValueError("capital must fit in the OSRS cash stack")

    @property
    def slots(self) -> int:
        return self.account.slots

    @property
    def include_members(self) -> bool:
        return self.account.allows_members_items

    @property
    def horizon_hours(self) -> float:
        if self.trade_mode is engine.TradeMode.PROFIT:
            return engine.PROFIT_HORIZON_HOURS
        return (float(self.overnight_hours)
                if self.trade_mode is engine.TradeMode.OVERNIGHT
                else float(self.calibration.horizon_hours))


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
    members: bool            # needed to tell a botted f2p staple from an item
    thin_volume_1h: int
    qty_per_window: int
    capital_needed: int      # gp this flip ties up in one slot
    gross_profit: int        # margin * qty — the best case, before discounts
    undercut_depth: int      # gp of price improvement you can afford per side
    drift: float             # 5m mid vs 1h mid, as a fraction
    ofi: float               # order-flow imbalance over the last hour
    quote_age: int
    tax_exempt: bool
    bond: bool
    bond_fee: int
    sell_listed_at: int      # where to actually list: free undercut at tax steps

    # fill model. The three *_seconds are MEDIANS of the fill-time
    # distribution; the round-trip band and the occupancy below come from the
    # same distribution, and p_fill is its probability of finishing the whole
    # quantity before the deadline.
    expected_buy_seconds: float
    expected_sell_seconds: float
    expected_total_seconds: float
    p_fill: float
    p_stranded: float
    expected_round_trip_qty: float

    expected_gp: float       # gross profit after every discount
    raw_gp_per_slot_hour: float   # before shrinkage
    gp_per_slot_hour: float       # after shrinkage — the ranking metric
    edge_probability: float       # P(this score is not noise)
    raw_ranking_value: float      # active: gp/slot/h; overnight: horizon EV;
                                  # profit: risk-adjusted gp per flip
    ranking_value: float          # same metric after shrinkage
    downside_risk_gp: float
    trade_mode: engine.TradeMode
    horizon_hours: float

    factors: Dict[str, float] = field(default_factory=dict)
    warnings: Tuple[str, ...] = field(default=())
    expected_buy_qty: float = 0.0
    expected_sell_qty: float = 0.0
    fill_low_qty: float = 0.0
    fill_high_qty: float = 0.0
    liquidation_hours: float = 0.0
    fill_log_sigma: float = 0.0
    dip_depth: float = 0.0        # Away bid under the touch, as a fraction
    dip_retention: float = 0.0    # share of that dip expected back by the sale
    round_trip_p50_seconds: float = 0.0
    round_trip_p80_seconds: float = 0.0
    round_trip_p90_seconds: float = 0.0
    expected_occupancy_seconds: float = 0.0
    reprice_check_seconds: float = 0.0
    cancel_by_seconds: float = 0.0

    # Concrete execution and inputs retained for quantity-aware allocation.
    base_buy: Optional[int] = None
    base_sell: Optional[int] = None
    buy_improvement: int = 0
    sell_improvement: int = 0
    buy_share: float = 0.0
    sell_share: float = 0.0
    model_buy_volume_1h: float = 0.0
    model_sell_volume_1h: float = 0.0
    competitors: float = 1.0
    priced_from_reference: bool = False
    sigma_daily: Optional[float] = None
    ou_fit: Optional[object] = None
    scored_at: float = 0.0
    category: str = "other"
    limit_group: Optional[str] = None

    # High alchemy
    alch_floor: Optional[int] = None
    alch_distance: Optional[float] = None
    alch_arbitrage_gp: Optional[int] = None

    # Filled by refine_with_history for the top candidates; None = not checked
    deep_checked: bool = False
    fill_share: Optional[float] = None   # binding leg's share of 14d volume
    trend: Optional[float] = None        # recent vs prior multi-day VWAP
    baseline_low: Optional[int] = None   # 14d volume-weighted seller price
    median_mid: Optional[int] = None     # 14d median price level
    elevation: Optional[float] = None    # quote mid vs median; + = above
    volatility: Optional[float] = None   # median swing around the median
    mean_reverting: Optional[bool] = None
    half_life_hours: Optional[float] = None
    ou_level: Optional[int] = None       # OU long-run level, in gp
    regime_score: Optional[float] = None
    # Both sides of the book this hour, and the 14-day average bucket volume.
    # The crash badge compares the two as rates, so it needs the total rather
    # than thin_volume_1h — that one is the right number for fill times and the
    # wrong one for a spike ratio.
    volume_1h_total: int = 0
    history_mean_volume: Optional[float] = None
    long_execution: Optional[engine.ExecutionEvidenceView] = None
    recent_execution: Optional[engine.ExecutionEvidenceView] = None
    execution_quality: float = 0.5
    execution_factor: float = 1.0
    shrink_retention: float = 1.0

    # Capital allocation, filled by allocate()
    allocated_capital: Optional[int] = None
    allocated_quantity: Optional[int] = None
    allocated_expected_gp: Optional[float] = None


# Structural rejections, in the order the gates run. Every item in /latest
# lands in exactly one bucket, so the funnel always sums to len(quotes).
FUNNEL_STAGES = (
    "in /latest", "no mapping entry", "members-only", "null price side",
    "nothing traded", "margin not positive", "cannot afford one", "scored",
)

PREFERENCE_STAGES = (
    "quote too old", "volume too thin", "price out of range", "pays tax",
    "roi too low", "no undercut room", "bot-supplied", "shown",
)


@dataclass(frozen=True)
class ScreenResult:
    rows: List[FlipRow]
    funnel: Dict[str, int]
    shrinkage: Optional[engine.ShrunkScores] = None
    deep_checked: int = 0
    hidden: Dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Stage 1 + 2: structural gates, then score everything that survives
# ---------------------------------------------------------------------------

VolumeLookup = Callable[[int], Optional[Tuple[float, float]]]


def screen(
    items: Dict[int, Item],
    quotes: Dict[int, Quote],
    activity_5m: Dict[int, Activity],
    activity_1h: Dict[int, Activity],
    config: FilterConfig,
    now: float,
    exempt: Optional[exemptions.ExemptionSet] = None,
    volume_lookup: Optional[VolumeLookup] = None,
) -> ScreenResult:
    """Score every item that is structurally a flip, then shrink the scores.

    `volume_lookup` maps an item id to smoothed (buyer-initiated,
    seller-initiated) units per hour — archive.Archive.volume_ewma if a tick
    archive exists. Without one the live 1-hour bucket is used, which is a
    single sample of a strongly time-of-day-dependent quantity.
    """
    if exempt is None:
        exempt = exemptions.resolve(items)
    rows: List[FlipRow] = []
    funnel = {stage: 0 for stage in FUNNEL_STAGES}
    funnel["in /latest"] = len(quotes)
    for item_id, quote in quotes.items():
        result = _evaluate(item_id, quote, items.get(item_id),
                           activity_5m.get(item_id), activity_1h.get(item_id),
                           config, config.capital, now, exempt, volume_lookup)
        if isinstance(result, str):
            funnel[result] += 1
        else:
            funnel["scored"] += 1
            rows.append(result)

    rows, shrinkage = _apply_shrinkage(rows, config)
    rows.sort(key=lambda r: r.ranking_value, reverse=True)
    return ScreenResult(rows=rows, funnel=funnel, shrinkage=shrinkage)


def _mid(activity: Optional[Activity]) -> Optional[float]:
    """Midpoint of a bucket, or whichever side traded if only one did."""
    if activity is None:
        return None
    high, low = activity.avg_high, activity.avg_low
    if high is not None and low is not None:
        return (high + low) / 2
    return high if high is not None else low


def connected_limit_group(name: str) -> Optional[str]:
    """Known shared-limit family, conservatively inferred from item names.

    The Wiki documents connected limits but the mapping endpoint does not
    expose a group id. Potion dose variants are the material flipping case and
    are safe to infer; unrelated charged jewellery is deliberately not merged.
    """
    lower = name.lower().strip()
    dose = re.search(r"\(([1-4])\)$", lower)
    potion_words = ("potion", "brew", "restore", "antipoison", "antidote",
                    "serum", "mix", "overload")
    if dose and any(word in lower for word in potion_words):
        return "potion:" + re.sub(r"\([1-4]\)$", "", lower).strip()
    return None


def item_category(name: str) -> str:
    lower = name.lower()
    families = (
        ("potions", ("potion", "brew", "restore", "antipoison", "antidote")),
        ("runes", (" rune", "rune ")),
        ("food", ("shark", "karambwan", "manta ray", "lobster", "salmon", "tuna")),
        ("logs", (" logs",)),
        ("ores-bars", (" ore", " bar")),
        ("armour", ("platebody", "platelegs", "helm", "armour", "shield")),
        ("weapons", ("sword", "bow", "staff", "whip", "scimitar", "godsword")),
    )
    for category, words in families:
        if any(word in " " + lower for word in words):
            return category
    return "other"


def _concession_points(maximum: int) -> List[int]:
    if maximum <= 0:
        return [0]
    if maximum <= 12:
        return list(range(maximum + 1))
    values = {0, 1, 2, maximum}
    values.update(int(round(maximum * fraction))
                  for fraction in (0.05, 0.10, 0.20, 0.35, 0.50, 0.75))
    return sorted(max(0, min(maximum, value)) for value in values)


class ExecutionChoice(NamedTuple):
    """The concrete offer the optimiser settled on, and what it assumed."""
    buy: int
    sell: int                  # expected exit price per item
    buy_improvement: int       # negative: an Away bid under the touch
    sell_improvement: int      # queue priority bought on the sell side
    qty: int
    breakdown: engine.ScoreBreakdown
    buy_volume_1h: float       # the buy-side volume the score used
    dip_depth: float = 0.0     # fraction under the touch, Away bids only
    dip_retention: float = 0.0  # share of that dip recovered by the sale
    capacity_qty: int = 0      # Active: size that only clears at the mean rate


# Away and Max profit quantity is chosen by expected value, stranded-inventory
# stress included, among these shares of the mean-rate capacity. A search grid.
AWAY_QTY_FRACTIONS = (0.25, 0.5, 0.75, 1.0)


def _optimise_execution(
    *, base_buy: int, base_sell: int, tax_exempt: bool, bond: bool = False,
    limit: Optional[int], available_capital: int,
    buy_volume_1h: float, sell_volume_1h: float,
    quote_age: int, ofi: float, drift: float, now: float,
    highalch: Optional[int], competitors: float, config: FilterConfig,
    sigma_daily: Optional[float] = None, ou_fit: Optional[object] = None,
    regime_score: float = 0.0, fill_log_sigma: Optional[float] = None,
) -> Optional[ExecutionChoice]:
    """Choose concrete order prices and quantity as one decision.

    Every queue-share benefit is paid for in ``buy``/``sell`` first. This
    closes the old loophole where maximum affordable priority supplied the fill
    probability while untouched prices supplied the profit.

    Active quantity is the largest whose whole round trip completes before the
    deadline with ``active_target_completion`` probability. It used to fill
    each half of the window at the mean rate, so every candidate was ranked,
    and its prices chosen, at a size that completed about one time in eight.

    Away has two more choices. It may bid under the touch and wait for a dip
    (dip_fill_multiplier), which pays only on items that measurably revert
    (dip_exit_retention). And its quantity is the one with the best expected
    value after stranded-inventory stress, rather than everything the mean
    rate could buy — that sizing completed the full buy 38% of the time and
    left about 30% of it unsold after the selling window.

    Max profit sizes the same way, from the round trip's mean-rate capacity
    before its 24-hour deadline, capped at one buy-limit window. It does not
    bid under the touch: its buy is relisted at once, not left to wait for a
    dip.
    """
    if fill_log_sigma is None:
        fill_log_sigma = engine.fill_log_sigma(config.calibration)
    calibration = config.calibration
    away = config.trade_mode is engine.TradeMode.OVERNIGHT
    profit = config.trade_mode is engine.TradeMode.PROFIT
    free_sell = engine.tax_boundary_undercut(base_sell, tax_exempt, bond)
    max_total = max(0, base_sell - base_buy - 1)
    sell_points = _concession_points(max(0, max_total - (base_sell - free_sell)))
    effective_limit = engine.effective_buy_limit(
        limit, config.horizon_hours, config.trade_mode)
    original_spread = max(1, base_sell - base_buy)
    usable = (config.horizon_hours * engine.SECONDS_PER_HOUR
              - engine.LEGS_PER_ROUND_TRIP * calibration.min_leg_seconds)

    # (buy price, improvement, buy-side volume, dip depth, dip retention)
    bids = [(base_buy + step, step, buy_volume_1h, 0.0, 0.0)
            for step in _concession_points(max_total)]
    if away:
        hold_hours = (config.horizon_hours
                      + calibration.overnight_liquidation_hours) / 2
        retention = engine.dip_exit_retention(ou_fit, hold_hours,
                                              regime_score, calibration)
        price_sigma = (sigma_daily if sigma_daily and sigma_daily > 0
                       else getattr(ou_fit, "sigma", None)
                       or calibration.default_sigma_daily)
        if retention > 0:
            seen = {bid[0] for bid in bids}
            for depth in engine.AWAY_BID_DEPTHS:
                bid = int(base_buy * (1 - depth))
                if bid < 1 or bid >= base_buy or bid in seen:
                    continue
                seen.add(bid)
                share = engine.dip_fill_multiplier(
                    math.log(base_buy / bid), price_sigma, config.horizon_hours)
                if share > 0:
                    bids.append((bid, bid - base_buy, buy_volume_1h * share,
                                 depth, retention))

    def evaluate(bid, extra_sell, fraction=1.0):
        buy, step, volume, depth, kept = bid
        listed = free_sell - extra_sell
        # A dip fill is sold into the market that dipped, less what it is
        # expected to have recovered by then.
        # floor(x + 0.5), not round(): Python rounds halves to even and the
        # browser port must produce the identical integer price.
        sell = listed - int(math.floor(max(0, -step) * (1.0 - kept) + 0.5))
        if sell <= buy:
            return None
        unit_capital = engine.unit_capital(buy, sell, bond)
        affordable = (available_capital // unit_capital
                      if unit_capital > 0 else 0)
        margin = engine.net_margin(buy, sell, tax_exempt, bond)
        if affordable <= 0 or margin <= 0:
            return None
        sell_improvement = base_sell - listed
        buy_share = engine.aggressiveness(
            engine.price_edge(max(0, step), original_spread),
            calibration, competitors)
        sell_share = engine.aggressiveness(
            engine.price_edge(sell_improvement, original_spread),
            calibration, competitors)
        trip_rate = engine.round_trip_rate(
            engine.fill_rate(volume, buy_share),
            engine.fill_rate(sell_volume_1h, sell_share))
        mean_capacity = engine.flippable_qty(
            effective_limit, int(trip_rate * max(0.0, usable)), affordable)
        if away:
            capacity = engine.fillable_quantity(volume, buy_share,
                                                config.horizon_hours)
            qty = engine.flippable_qty(effective_limit, capacity, affordable)
            qty = max(1, int(qty * fraction))
        elif profit:
            qty = max(1, int(mean_capacity * fraction))
        else:
            capacity = engine.target_quantity(
                trip_rate, usable, calibration.active_target_completion,
                fill_log_sigma, engine.fill_log_mu(calibration))
            qty = max(1, engine.flippable_qty(effective_limit, capacity,
                                              affordable))
        breakdown = engine.score_flip(
            buy=buy, sell=sell, margin=margin, qty=qty, depth=0,
            buy_volume_1h=volume, sell_volume_1h=sell_volume_1h,
            quote_age=quote_age, ofi=ofi, drift=drift, now=now,
            sigma_daily=sigma_daily, ou_fit=ou_fit,
            regime_score=regime_score,
            highalch=highalch, nature_rune_cost=config.nature_rune_cost,
            competitors=competitors,
            buy_improvement=step, sell_improvement=sell_improvement,
            buy_share=buy_share, sell_share=sell_share,
            mode=config.trade_mode, horizon_hours=config.horizon_hours,
            capital_per_unit=unit_capital,
            fill_log_sigma=fill_log_sigma,
            calibration=calibration)
        return ExecutionChoice(buy, sell, step, sell_improvement, qty,
                               breakdown, volume, depth, kept,
                               max(qty, mean_capacity))

    best = None
    for bid in bids:
        for extra_sell in sell_points:
            choice = evaluate(bid, extra_sell)
            if choice is not None and (
                    best is None or choice.breakdown.ranking_value
                    > best[0].breakdown.ranking_value):
                best = (choice, bid, extra_sell)
    if best is None:
        return None
    choice, bid, extra_sell = best
    if away or profit:
        # Prices first at full size, then the size at those prices.
        for fraction in AWAY_QTY_FRACTIONS[:-1]:
            smaller = evaluate(bid, extra_sell, fraction)
            if (smaller is not None and smaller.breakdown.ranking_value
                    > choice.breakdown.ranking_value):
                choice = smaller
    return choice


def _evaluate(
    item_id: int,
    quote: Quote,
    item: Optional[Item],
    act_5m: Optional[Activity],
    act_1h: Optional[Activity],
    config: FilterConfig,
    available_capital: int,
    now: float,
    exempt: exemptions.ExemptionSet,
    volume_lookup: Optional["VolumeLookup"] = None,
) -> Union[FlipRow, str]:
    """One item through the structural gates and the score."""
    if item is None:
        return "no mapping entry"
    if item.members and not config.include_members:
        return "members-only"
    if (quote.high is None or quote.low is None
            or quote.high_time is None or quote.low_time is None
            or quote.low <= 0 or quote.high <= 0
            or quote.high_time <= 0 or quote.low_time <= 0
            or max(quote.high_time, quote.low_time) > now + 60):
        return "null price side"

    age = max(0, int(now - min(quote.high_time, quote.low_time)))

    high_vol_1h = float(act_1h.high_volume if act_1h else 0)
    low_vol_1h = float(act_1h.low_volume if act_1h else 0)
    if volume_lookup is not None:
        smoothed = volume_lookup(item_id)
        if smoothed is not None:
            # A single 1-hour bucket is one draw from a strongly U-shaped
            # daily volume curve: sampled at peak it flatters the item,
            # sampled at 4am it buries it. The archive's exponentially
            # weighted rate is the same quantity measured over days.
            high_vol_1h, low_vol_1h = smoothed
    thin_volume = int(min(high_vol_1h, low_vol_1h))
    if high_vol_1h <= 0 or low_vol_1h <= 0:
        # A flip needs both sides of the book. One-sided volume means there is
        # no round trip to make, whatever the quoted spread says.
        return "nothing traded"

    ref_low = engine.reference_price(
        act_5m.avg_low if act_5m else None,
        act_5m.low_volume if act_5m else 0,
        act_1h.avg_low if act_1h else None, low_vol_1h)
    ref_high = engine.reference_price(
        act_5m.avg_high if act_5m else None,
        act_5m.high_volume if act_5m else 0,
        act_1h.avg_high if act_1h else None, high_vol_1h)
    priced = engine.executable_prices(quote.low, quote.high, ref_low, ref_high,
                                      config.calibration)
    buy, sell = priced.buy, priced.sell

    tax_exempt = item_id in exempt
    bond = item_id == exemptions.BOND_ID
    margin = engine.net_margin(buy, sell, tax_exempt, bond)
    if margin <= 0:
        return "margin not positive"

    affordable = available_capital // engine.unit_capital(
        buy, sell, bond) if buy > 0 else 0
    if affordable == 0:
        return "cannot afford one"

    depth = engine.undercut_depth(buy, sell, tax_exempt, bond)
    crowd = engine.touch_competitors(thin_volume, item.limit,
                                     config.calibration)
    drift = engine.price_drift(_mid(act_5m), _mid(act_1h))
    ofi = engine.order_flow_imbalance(high_vol_1h, low_vol_1h)
    choice = _optimise_execution(
        base_buy=buy, base_sell=sell, tax_exempt=tax_exempt, bond=bond,
        limit=item.limit, available_capital=available_capital,
        buy_volume_1h=low_vol_1h, sell_volume_1h=high_vol_1h,
        quote_age=age, ofi=ofi, drift=drift, now=now,
        highalch=item.highalch, competitors=crowd, config=config,
        fill_log_sigma=engine.fill_log_sigma(config.calibration,
                                             verified=False))
    if choice is None:
        return "margin not positive"
    buy, sell, buy_improvement, sell_improvement, qty, breakdown = choice[:6]
    margin = engine.net_margin(buy, sell, tax_exempt, bond)
    affordable = available_capital // engine.unit_capital(buy, sell, bond)

    floor = engine.alch_floor(item.highalch, config.nature_rune_cost)
    return FlipRow(
        item_id=item_id, name=item.name, buy=buy, sell=sell,
        latest_low=quote.low, latest_high=quote.high,
        tax=engine.ge_tax(sell, tax_exempt), margin=margin,
        roi=engine.roi(buy, sell, tax_exempt, bond),
        limit=item.limit, members=bool(item.members),
        thin_volume_1h=thin_volume, qty_per_window=qty,
        volume_1h_total=int(high_vol_1h + low_vol_1h),
        capital_needed=breakdown.capital_needed,
        gross_profit=breakdown.raw_profit, undercut_depth=depth,
        drift=drift, ofi=ofi, quote_age=age, tax_exempt=tax_exempt,
        bond=bond,
        bond_fee=engine.bond_conversion_fee(sell, bond),
        sell_listed_at=sell,
        expected_buy_seconds=breakdown.buy_seconds,
        expected_sell_seconds=breakdown.sell_seconds,
        expected_total_seconds=breakdown.total_seconds,
        p_fill=breakdown.p_fill_both,
        p_stranded=breakdown.p_stranded,
        expected_round_trip_qty=breakdown.expected_round_trip_qty,
        expected_buy_qty=breakdown.expected_buy_qty,
        expected_sell_qty=breakdown.expected_sell_qty,
        fill_low_qty=breakdown.fill_low_qty,
        fill_high_qty=breakdown.fill_high_qty,
        liquidation_hours=breakdown.liquidation_hours,
        **_timing_fields(breakdown),
        expected_gp=breakdown.expected_profit,
        raw_gp_per_slot_hour=breakdown.gp_per_slot_hour,
        gp_per_slot_hour=breakdown.gp_per_slot_hour,
        edge_probability=1.0,
        raw_ranking_value=breakdown.ranking_value,
        ranking_value=breakdown.ranking_value,
        downside_risk_gp=breakdown.downside_risk_gp,
        trade_mode=breakdown.mode, horizon_hours=breakdown.horizon_hours,
        factors=breakdown.factors(),
        base_buy=priced.buy, base_sell=priced.sell,
        buy_improvement=buy_improvement,
        sell_improvement=sell_improvement,
        buy_share=breakdown.buy_share, sell_share=breakdown.sell_share,
        model_buy_volume_1h=choice.buy_volume_1h,
        dip_depth=choice.dip_depth, dip_retention=choice.dip_retention,
        model_sell_volume_1h=high_vol_1h,
        competitors=crowd,
        priced_from_reference=priced.from_reference,
        scored_at=now,
        category=item_category(item.name),
        limit_group=connected_limit_group(item.name),
        alch_floor=floor,
        alch_distance=engine.alch_distance(buy, floor),
        alch_arbitrage_gp=breakdown.alch_arbitrage_gp,
        warnings=_warnings(depth, drift, ofi, affordable, qty, item.limit,
                           priced.from_reference,
                           breakdown, priced.sell, tax_exempt,
                           config.calibration),
    )


# ---------------------------------------------------------------------------
# Stage 3: empirical-Bayes shrinkage
# ---------------------------------------------------------------------------

def _apply_shrinkage(
    rows: List[FlipRow], config: FilterConfig,
) -> Tuple[List[FlipRow], Optional[engine.ShrunkScores]]:
    """Replace each raw score with its posterior, given the whole cross-section.

    Run over every scored item, not the shortlist: the correction is a
    statement about the distribution the top of the list was drawn from, so
    shrinking only the survivors of a truncation would miss the point entirely.
    """
    if not rows:
        return rows, None
    raw = [row.raw_ranking_value for row in rows]
    # Volume is the sample size behind each estimate: an item quoted off 40,000
    # traded units is measured, one quoted off twelve is a rumour.
    counts = [max(1.0, float(row.thin_volume_1h)) for row in rows]
    shrunk = engine.shrink_scores(raw, counts, config.calibration)
    out = []
    for row, value, probability in zip(rows, shrunk.values,
                                       shrunk.edge_probability):
        # Screening and deep refinement each shrink the cross-section. Replace
        # the earlier explanation instead of stacking two stale percentages.
        warnings = tuple(note for note in row.warnings
                         if not note.startswith("score cut "))
        if row.raw_ranking_value > 0:
            kept = value / row.raw_ranking_value
            # A display threshold, not a model parameter: below this the number
            # the user is reading is materially not what was measured.
            if kept < 0.85:
                warnings = warnings + (
                    "score cut {:.0%} by shrinkage — it rests on {:,} units/h "
                    "of volume, too little to take at face value".format(
                        1 - kept, row.thin_volume_1h),)
        gp_per_hour = (value if config.trade_mode is engine.TradeMode.ACTIVE
                       else row.gp_per_slot_hour)
        out.append(replace(row, ranking_value=value,
                           gp_per_slot_hour=gp_per_hour,
                           shrink_retention=(value / row.raw_ranking_value
                                             if row.raw_ranking_value > 0
                                             else 0.0),
                           edge_probability=probability, warnings=warnings))
    return out, shrunk


# ---------------------------------------------------------------------------
# Stage 4: deep verification against multi-day history
# ---------------------------------------------------------------------------

def refine_with_history(
    result: ScreenResult,
    fetch_history: Callable[[int], Optional[List[dict]]],
    config: FilterConfig,
    now: float,
    top_k: int = 15,
    breadth: int = 3,
    fetch_recent: Optional[Callable[[int], Optional[List[dict]]]] = None,
) -> ScreenResult:
    """Re-score the leading candidates against ~14 days of 6h history.

    /timeseries is a per-item route the wiki forbids sweeping, so deep data is
    spent on a shortlist. The shortlist is deliberately wider than the number
    of rows shown (top_k * breadth): the point of the deep stage is that it can
    change the order, which it cannot do if it only ever sees the items that
    are already on top.

    Unlike the old version this recomputes the score rather than multiplying
    the old one by further sub-1.0 factors. History replaces estimates instead
    of only penalising them: the OU fit can find an item trading *below* its
    long-run level, which raises its score, and the reachable-volume estimate
    can be more generous than the intraday guess as well as less.
    """
    rows = list(result.rows)
    shortlist = min(len(rows), max(0, top_k * breadth))
    refined_count = 0
    for index in range(shortlist):
        row = rows[index]
        points = fetch_history(row.item_id)
        view = (engine.history_view(points, row.buy, row.sell)
                if points else None)
        if view is None:
            rows[index] = replace(row, warnings=row.warnings + (
                "no usable 14-day history — ranked on intraday data only",))
            continue
        refined_count += 1
        rescored = _rescore_with_history(row, view, config, now)
        long_execution = engine.execution_evidence_view(
            points, rescored.tax_exempt, rescored.margin,
            engine.HISTORY_BUCKET_HOURS,
            engine.HISTORY_WINDOW_BUCKETS * engine.HISTORY_BUCKET_HOURS,
            rescored.bond)
        rows[index] = replace(rescored, long_execution=long_execution)

    if fetch_recent is not None:
        leaders = sorted(
            (row for row in rows if row.deep_checked),
            key=lambda row: row.raw_ranking_value, reverse=True,
        )[:engine.RECENT_EXECUTION_TOP_K]
        by_id = {row.item_id: index for index, row in enumerate(rows)}
        for row in leaders:
            points = fetch_recent(row.item_id)
            if not points:
                continue
            recent = engine.execution_evidence_view(
                points, row.tax_exempt, row.margin, 5 / 60,
                engine.RECENT_EXECUTION_HOURS, row.bond)
            rows[by_id[row.item_id]] = replace(row, recent_execution=recent)

    rows, shrinkage = _apply_shrinkage(rows, config)
    rows = [_apply_execution_evidence(row) for row in rows]
    rows.sort(key=lambda r: r.ranking_value, reverse=True)
    return ScreenResult(rows=rows, funnel=result.funnel,
                        shrinkage=shrinkage, deep_checked=refined_count)


def _apply_execution_evidence(row: FlipRow) -> FlipRow:
    if not row.deep_checked or row.long_execution is None:
        return row
    quality, factor = engine.combined_execution_evidence(
        row.long_execution, row.recent_execution,
        row.raw_ranking_value, row.raw_gp_per_slot_hour,
        row.trade_mode, row.horizon_hours)
    warnings = row.warnings
    if row.recent_execution is not None:
        recent_quality = engine.execution_evidence_quality(
            row.recent_execution, row.raw_ranking_value,
            row.raw_gp_per_slot_hour, row.trade_mode, row.horizon_hours)
        if recent_quality < 0.38:
            warnings += ("recent spread rarely survived tax — the live quote "
                         "is not repeating",)
    ranking = row.ranking_value * factor
    return replace(
        row, execution_quality=quality, execution_factor=factor,
        ranking_value=ranking,
        gp_per_slot_hour=(ranking if row.trade_mode is engine.TradeMode.ACTIVE
                          else row.gp_per_slot_hour),
        warnings=warnings)


def _rescore_with_history(row: FlipRow, view: engine.HistoryView,
                          config: FilterConfig, now: float) -> FlipRow:
    """Recompute one row with the OU fit and the reachable-volume estimate."""
    # The share of multi-day volume that traded at your prices is evidence
    # about the rate your offer fills at, not a separate penalty on profit. A
    # price only 5% of the market ever reached is not a flip earning 5% of its
    # margin — it is a flip that takes twenty times as long.
    # Away and Max profit span hours of the daily cycle (Max profit's deadline
    # is a whole day), so they are sized on the 14-day average rate rather
    # than on the one live hour the snapshot happened to land in. Active is
    # executed now, at the live rate.
    base_volume = float(row.thin_volume_1h)
    if (config.trade_mode is not engine.TradeMode.ACTIVE
            and view.low_volume_per_hour > 0 and view.high_volume_per_hour > 0):
        base_volume = min(view.low_volume_per_hour, view.high_volume_per_hour)
    reachable_buy = max(0.0, base_volume * max(view.buy_fill_share, 0.01))
    reachable_sell = max(0.0, base_volume * max(view.sell_fill_share, 0.01))

    # Crowd from the item's REAL volume, not the reachable slice: a low fill
    # share means fewer units arrive at your price, not fewer rivals queued.
    crowd = engine.touch_competitors(base_volume, row.limit,
                                     config.calibration)
    sigma = view.ou.sigma if view.ou is not None else None
    highalch = (None if row.alch_floor is None
                else row.alch_floor + config.nature_rune_cost)
    choice = _optimise_execution(
        base_buy=row.base_buy or row.buy, base_sell=row.base_sell or row.sell,
        tax_exempt=row.tax_exempt, bond=row.bond, limit=row.limit,
        available_capital=config.capital,
        buy_volume_1h=reachable_buy, sell_volume_1h=reachable_sell,
        quote_age=row.quote_age, ofi=row.ofi, drift=row.drift, now=now,
        highalch=highalch, competitors=crowd, config=config,
        sigma_daily=sigma, ou_fit=view.ou, regime_score=view.regime_score,
        fill_log_sigma=engine.fill_log_sigma(config.calibration,
                                             verified=True))
    if choice is None:
        return replace(row, deep_checked=True, warnings=row.warnings + (
            "history left no positive concrete execution price",))
    buy, sell, buy_improvement, sell_improvement, qty, breakdown = choice[:6]
    margin = engine.net_margin(buy, sell, row.tax_exempt, row.bond)
    dip_notes: Tuple[str, ...] = ()
    if choice.dip_depth > 0:
        half_life = view.half_life_hours
        dip_notes = ((
            "away bid {:.0%} under the market ({:,} vs {:,}): it fills only if "
            "the price dips while you are away; the exit assumes {:.0%} of the "
            "dip is recovered by the sale{}".format(
                choice.dip_depth, buy, row.base_buy or row.buy,
                choice.dip_retention,
                " (mean-reverting, half-life {:.0f}h)".format(half_life)
                if half_life else "")),)

    return replace(
        row,
        buy=buy, sell=sell, sell_listed_at=sell,
        tax=engine.ge_tax(sell, row.tax_exempt),
        bond_fee=engine.bond_conversion_fee(sell, row.bond), margin=margin,
        roi=engine.roi(buy, sell, row.tax_exempt, row.bond),
        qty_per_window=qty, capital_needed=breakdown.capital_needed,
        gross_profit=breakdown.raw_profit,
        expected_buy_seconds=breakdown.buy_seconds,
        expected_sell_seconds=breakdown.sell_seconds,
        expected_total_seconds=breakdown.total_seconds,
        p_fill=breakdown.p_fill_both,
        p_stranded=breakdown.p_stranded,
        expected_round_trip_qty=breakdown.expected_round_trip_qty,
        expected_buy_qty=breakdown.expected_buy_qty,
        expected_sell_qty=breakdown.expected_sell_qty,
        fill_low_qty=breakdown.fill_low_qty,
        fill_high_qty=breakdown.fill_high_qty,
        liquidation_hours=breakdown.liquidation_hours,
        **_timing_fields(breakdown),
        expected_gp=breakdown.expected_profit,
        raw_gp_per_slot_hour=breakdown.gp_per_slot_hour,
        gp_per_slot_hour=breakdown.gp_per_slot_hour,
        raw_ranking_value=breakdown.ranking_value,
        ranking_value=breakdown.ranking_value,
        downside_risk_gp=breakdown.downside_risk_gp,
        trade_mode=breakdown.mode, horizon_hours=breakdown.horizon_hours,
        factors=breakdown.factors(),
        buy_improvement=buy_improvement,
        sell_improvement=sell_improvement,
        buy_share=breakdown.buy_share, sell_share=breakdown.sell_share,
        model_buy_volume_1h=choice.buy_volume_1h,
        dip_depth=choice.dip_depth, dip_retention=choice.dip_retention,
        model_sell_volume_1h=reachable_sell,
        competitors=crowd, sigma_daily=sigma, ou_fit=view.ou, scored_at=now,
        alch_arbitrage_gp=breakdown.alch_arbitrage_gp,
        deep_checked=True, fill_share=view.fill_share, trend=view.trend,
        baseline_low=view.baseline_low, median_mid=view.median_mid,
        elevation=view.elevation, volatility=view.volatility,
        mean_reverting=view.mean_reverting,
        half_life_hours=view.half_life_hours,
        ou_level=int(round(view.ou.level_gp)) if view.ou is not None else None,
        regime_score=view.regime_score,
        volume_1h_total=row.volume_1h_total,
        history_mean_volume=view.mean_volume,
        warnings=_refresh_timing_warnings(row.warnings, breakdown,
                                          config.calibration)
        + _history_warnings(view) + dip_notes,
    )


# ---------------------------------------------------------------------------
# Stage 5: view preferences and capital allocation
# ---------------------------------------------------------------------------

def apply_preferences(result: ScreenResult,
                      config: FilterConfig) -> ScreenResult:
    """Hide rows the user asked not to see. Never reorders what remains."""
    hidden = {stage: 0 for stage in PREFERENCE_STAGES}
    kept: List[FlipRow] = []
    for row in result.rows:
        if (config.max_quote_age is not None
                and row.quote_age > config.max_quote_age):
            hidden["quote too old"] += 1
            continue
        if row.thin_volume_1h < config.min_thin_volume_1h:
            hidden["volume too thin"] += 1
            continue
        if row.buy < config.min_price or (config.max_price is not None
                                          and row.buy > config.max_price):
            hidden["price out of range"] += 1
            continue
        if config.tax_free_only and row.tax > 0:
            hidden["pays tax"] += 1
            continue
        if row.roi < config.min_roi:
            hidden["roi too low"] += 1
            continue
        if row.undercut_depth < config.min_undercut_depth:
            hidden["no undercut room"] += 1
            continue
        if config.hide_botted and merch.is_botted(row.buy, row.members,
                                                  row.limit):
            hidden["bot-supplied"] += 1
            continue
        kept.append(row)
    hidden["shown"] = len(kept)
    return ScreenResult(rows=kept, funnel=result.funnel,
                        shrinkage=result.shrinkage,
                        deep_checked=result.deep_checked, hidden=hidden)


def allocate(result: ScreenResult, config: FilterConfig) -> ScreenResult:
    """Construct an executable portfolio and re-score every final quantity.

    Candidate sizing already used the whole bank, not an equal split. This
    stage considers a wider shortlist, applies a small correlated-category cap,
    respects connected buy-limit families, then recomputes partial-fill EV at
    the exact integer quantity actually funded.
    """
    rows = list(result.rows)
    if not rows:
        return result
    shortlist = rows[:min(len(rows), max(40, config.slots * 6))]
    selected: List[FlipRow] = []
    category_count: Dict[str, int] = {}
    remaining_seed = config.capital
    for row in shortlist:
        if len(selected) >= config.slots:
            break
        if (row.ranking_value <= 0 or row.expected_gp <= 0
                or _unit_capital(row) > remaining_seed
                or not meets_completion_target(row, config)):
            continue
        # Three related slots is diversification, four is a concentrated bet.
        if category_count.get(row.category, 0) >= 3:
            continue
        selected.append(row)
        category_count[row.category] = category_count.get(row.category, 0) + 1
        remaining_seed -= _unit_capital(row)

    # Quantity was already chosen per mode: Active so the whole round trip
    # completes before the deadline with the target probability, Away and Max
    # profit by expected value after stranded-inventory stress. Funding a different
    # bound here would trade that choice away again.
    capital_caps = [row.capital_needed for row in selected]
    amounts = engine.allocate_portfolio(
        [row.ranking_value for row in selected], config.capital,
        [_unit_capital(row) for row in selected], capital_caps,
        config.slots)

    group_used: Dict[str, int] = {}
    funded: List[FlipRow] = []
    for row, amount in zip(selected, amounts):
        unit = _unit_capital(row)
        quantity = amount // unit if amount > 0 and unit > 0 else 0
        if row.limit_group and row.limit is not None:
            group_cap = engine.effective_buy_limit(
                row.limit, config.horizon_hours, config.trade_mode) or 0
            left = max(0, group_cap - group_used.get(row.limit_group, 0))
            quantity = min(quantity, left)
            group_used[row.limit_group] = group_used.get(row.limit_group, 0) + quantity
        if quantity <= 0:
            continue
        rescored = _rescore_quantity(row, quantity, config)
        funded.append(replace(
            rescored, allocated_capital=quantity * unit,
            allocated_quantity=quantity,
            allocated_expected_gp=rescored.expected_gp))

    funded.sort(key=lambda row: row.ranking_value, reverse=True)
    funded_ids = {row.item_id for row in funded}
    ordered = funded + [row for row in rows if row.item_id not in funded_ids]
    return ScreenResult(rows=ordered, funnel=result.funnel,
                        shrinkage=result.shrinkage,
                        deep_checked=result.deep_checked, hidden=result.hidden)


def _unit_capital(row: FlipRow) -> int:
    """Cash per unit, including the bond conversion fee where it applies."""
    return row.buy + row.bond_fee


def _timing_fields(breakdown: engine.ScoreBreakdown) -> Dict[str, float]:
    """The fill-time distribution, copied together so it cannot go stale."""
    return {
        "fill_log_sigma": breakdown.fill_log_sigma,
        "round_trip_p50_seconds": breakdown.round_trip_p50_seconds,
        "round_trip_p80_seconds": breakdown.round_trip_p80_seconds,
        "round_trip_p90_seconds": breakdown.round_trip_p90_seconds,
        "expected_occupancy_seconds": breakdown.expected_occupancy_seconds,
        "reprice_check_seconds": breakdown.reprice_check_seconds,
        "cancel_by_seconds": breakdown.cancel_by_seconds,
    }


def meets_completion_target(row: FlipRow, config: FilterConfig) -> bool:
    """Whether an Active flip may be funded automatically.

    Quantity is already sized to the target, so a row below it is one where
    even a single unit is unlikely to make the round trip before the deadline.
    Such a row stays listed, with a warning, but never receives bank. Away and
    Max profit have no completion target: their quantity is sized on expected
    value with the unsold remainder already charged.
    """
    if config.trade_mode is not engine.TradeMode.ACTIVE:
        return True
    return row.p_fill + 1e-9 >= config.calibration.active_target_completion


def _rescore_quantity(row: FlipRow, quantity: int,
                      config: FilterConfig) -> FlipRow:
    """Re-evaluate fill uncertainty and EV for the funded integer quantity."""
    breakdown = engine.score_flip(
        buy=row.buy, sell=row.sell, margin=row.margin, qty=quantity, depth=0,
        buy_volume_1h=row.model_buy_volume_1h,
        sell_volume_1h=row.model_sell_volume_1h,
        quote_age=row.quote_age, ofi=row.ofi, drift=row.drift,
        now=row.scored_at, sigma_daily=row.sigma_daily, ou_fit=row.ou_fit,
        regime_score=row.regime_score or 0.0,
        highalch=None if row.alch_floor is None
        else row.alch_floor + config.nature_rune_cost,
        nature_rune_cost=config.nature_rune_cost,
        competitors=row.competitors,
        buy_improvement=row.buy_improvement,
        sell_improvement=row.sell_improvement,
        buy_share=row.buy_share, sell_share=row.sell_share,
        mode=config.trade_mode, horizon_hours=config.horizon_hours,
        capital_per_unit=_unit_capital(row),
        fill_log_sigma=row.fill_log_sigma or None,
        calibration=config.calibration)
    retained = (row.ranking_value / row.raw_ranking_value
                if row.raw_ranking_value > 0 else 1.0)
    ranking = breakdown.ranking_value * max(0.0, retained)
    return replace(
        row, qty_per_window=quantity,
        capital_needed=breakdown.capital_needed,
        gross_profit=breakdown.raw_profit,
        expected_buy_seconds=breakdown.buy_seconds,
        expected_sell_seconds=breakdown.sell_seconds,
        expected_total_seconds=breakdown.total_seconds,
        p_fill=breakdown.p_fill_both, p_stranded=breakdown.p_stranded,
        expected_round_trip_qty=breakdown.expected_round_trip_qty,
        expected_buy_qty=breakdown.expected_buy_qty,
        expected_sell_qty=breakdown.expected_sell_qty,
        fill_low_qty=breakdown.fill_low_qty,
        fill_high_qty=breakdown.fill_high_qty,
        liquidation_hours=breakdown.liquidation_hours,
        **_timing_fields(breakdown),
        expected_gp=breakdown.expected_profit,
        raw_gp_per_slot_hour=breakdown.gp_per_slot_hour,
        gp_per_slot_hour=(ranking if config.trade_mode is engine.TradeMode.ACTIVE
                          else breakdown.gp_per_slot_hour),
        raw_ranking_value=breakdown.ranking_value,
        ranking_value=ranking,
        downside_risk_gp=breakdown.downside_risk_gp,
        factors=breakdown.factors(),
        alch_arbitrage_gp=breakdown.alch_arbitrage_gp,
        warnings=_refresh_timing_warnings(row.warnings, breakdown,
                                          config.calibration))


def rank_flips(
    items: Dict[int, Item],
    quotes: Dict[int, Quote],
    activity_5m: Dict[int, Activity],
    activity_1h: Dict[int, Activity],
    config: FilterConfig,
    now: float,
    fetch_history: Optional[Callable[[int], Optional[List[dict]]]] = None,
    top_k: int = 15,
    exempt: Optional[exemptions.ExemptionSet] = None,
    volume_lookup: Optional["VolumeLookup"] = None,
    fetch_recent: Optional[Callable[[int], Optional[List[dict]]]] = None,
) -> ScreenResult:
    """The whole pipeline: score, shrink, deep-check, filter, allocate."""
    result = screen(items, quotes, activity_5m, activity_1h, config, now, exempt,
                    volume_lookup)
    if fetch_history is not None and top_k > 0:
        result = refine_with_history(result, fetch_history, config, now, top_k,
                                     fetch_recent=fetch_recent)
    result = apply_preferences(result, config)
    return allocate(result, config)


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------

def _history_warnings(view: engine.HistoryView) -> Tuple[str, ...]:
    notes = []
    if view.regime_changed:
        notes.append("price level shifted mid-history — likely an update "
                     "re-pricing it; mean reversion is not modelled through it")
    if view.elevation >= 0.05 and view.mean_reverting:
        notes.append("trading {:.0%} above its own long-run level — expect "
                     "reversion against you".format(view.elevation))
    elif view.elevation >= 0.05:
        notes.append("trading {:.0%} above its 14-day median, and it does not "
                     "mean-revert — no reason to expect it back".format(
                         view.elevation))
    if view.volatility >= 0.05:
        notes.append("price swings ±{:.0%} around its 14-day median — risky "
                     "to hold".format(view.volatility))
    if view.dislocation <= -0.10:
        notes.append("buy price {:.0%} below the 14-day average — only the "
                     "dump fills there".format(abs(view.dislocation)))
    if view.fill_share <= 0.25:
        notes.append("only {:.0%} of 14-day volume traded at your prices"
                     .format(view.fill_share))
    if view.trend >= 0.03:
        notes.append("risen {:.0%} over recent days — don't chase, wait for "
                     "it to settle".format(view.trend))
    elif view.trend <= -0.03:
        notes.append("falling {:.0%} over recent days".format(abs(view.trend)))
    half_life = view.half_life_hours
    if view.mean_reverting and half_life is not None and half_life > 7 * 24:
        notes.append("mean-reverts, but with a {:.0f}-day half-life — too slow "
                     "to trade around".format(half_life / 24))
    return tuple(notes)


# Every note _timing_warnings can produce starts with one of these, so a
# re-score can replace them instead of stacking a stale probability.
_TIMING_NOTE_PREFIXES = (
    "no realistic fill on one side", "estimated buy plus post-return",
    "fill odds:", "inventory risk:",
)


def _timing_warnings(breakdown: engine.ScoreBreakdown,
                     calibration: engine.Calibration
                     ) -> Tuple[str, ...]:
    """Notes that depend on the fill-time distribution at this quantity."""
    notes = []
    if breakdown.total_seconds == float("inf"):
        notes.append("no realistic fill on one side — the book is one-sided")
    elif (breakdown.mode is engine.TradeMode.OVERNIGHT
          and breakdown.total_seconds > 8 * engine.SECONDS_PER_HOUR):
        notes.append("estimated buy plus post-return liquidation time {} — "
                     "plan for inventory management after login"
                     .format(engine.format_duration(breakdown.total_seconds)))
    # Active needs no separate "slow" note: quantity is sized so the P80 meets
    # the deadline, the band is shown on every row, and a row that cannot meet
    # the target even at one unit gets the fill-odds note below.
    if breakdown.mode is engine.TradeMode.OVERNIGHT:
        if breakdown.p_fill_both < 0.25:
            notes.append("fill odds: only {:.0%} chance the full buy order "
                         "fills before you return in {:.0f}h"
                         .format(breakdown.p_fill_both,
                                 breakdown.horizon_hours))
    elif breakdown.mode is engine.TradeMode.PROFIT:
        if breakdown.p_fill_both < 0.50:
            notes.append("fill odds: only {:.0%} chance the whole round trip "
                         "completes within {:.0f}h; what is left is cancelled "
                         "at the deadline".format(breakdown.p_fill_both,
                                                  breakdown.horizon_hours))
    elif (breakdown.p_fill_both + 1e-9
          < calibration.active_target_completion):
        notes.append("fill odds: only {:.0%} chance the whole round trip "
                     "completes within {:.0f}h even at this size — below the "
                     "{:.0%} needed for automatic funding".format(
                         breakdown.p_fill_both, breakdown.horizon_hours,
                         calibration.active_target_completion))
    if (breakdown.mode is engine.TradeMode.OVERNIGHT
            and breakdown.p_stranded >= 0.20):
        notes.append("inventory risk: about {:.0%} of the planned quantity "
                     "may remain after the post-return sell window; stress "
                     "downside is {:,.0f} gp"
                     .format(breakdown.p_stranded,
                             breakdown.downside_risk_gp))
    if (breakdown.mode is engine.TradeMode.PROFIT
            and breakdown.p_stranded >= 0.20):
        notes.append("inventory risk: about {:.0%} of the planned quantity "
                     "may still be unsold at the {:.0f}h deadline; stress "
                     "downside is {:,.0f} gp"
                     .format(breakdown.p_stranded, breakdown.horizon_hours,
                             breakdown.downside_risk_gp))
    return tuple(notes)


def _refresh_timing_warnings(warnings: Tuple[str, ...],
                             breakdown: engine.ScoreBreakdown,
                             calibration: engine.Calibration
                             ) -> Tuple[str, ...]:
    kept = tuple(note for note in warnings
                 if not note.startswith(_TIMING_NOTE_PREFIXES))
    return kept + _timing_warnings(breakdown, calibration)


def _warnings(depth: int, drift: float, ofi: float, affordable: int, qty: int,
              limit: Optional[int], from_reference: bool,
              breakdown: engine.ScoreBreakdown,
              sell: int, tax_exempt: bool,
              calibration: engine.Calibration = engine.DEFAULT_CALIBRATION
              ) -> Tuple[str, ...]:
    """Plain-language reasons this flip might not pay what it quotes."""
    notes = []
    if from_reference:
        notes.append(
            "the last two prints showed no spread, so these prices come from "
            "the hour's volume-weighted averages rather than from a live quote")
    if breakdown.alch_arbitrage_gp is not None and breakdown.alch_arbitrage_gp > 0:
        # Not free money, and worth being precise about why: alching is capped
        # at roughly 1,200 casts an hour and needs 55 Magic, so this is a
        # guaranteed exit at a known price rather than a scalable trade. That
        # guarantee is the point — it puts a floor under the sell leg.
        notes.append("trading below its high-alch value: alching nets {:,} gp "
                     "per item, about {} gp/h at ~1,200 casts. Caps the "
                     "downside on the sell leg rather than replacing it."
                     .format(breakdown.alch_arbitrage_gp,
                             engine.format_gp(breakdown.alch_arbitrage_gp * 1200)))
    if depth == 0:
        notes.append("no room to outbid the queue — you wait your turn, and "
                     "the fill estimate assumes you are one of several offers")
    elif depth <= 2:
        notes.append("only {} gp of undercut room".format(depth))
    notes.extend(_timing_warnings(breakdown, calibration))
    if drift <= -0.02:
        notes.append("price falling {:.1%} — your buy fills, your sell may not"
                     .format(abs(drift)))
    elif drift >= 0.02:
        notes.append("price rising {:.1%} — your buy may not fill".format(drift))
    if ofi <= -0.3:
        notes.append("sellers are {:.0%} of aggressor volume — you would be "
                     "catching what they are dumping".format(abs(ofi)))
    if limit is None:
        notes.append("no published buy limit")
    listed = engine.tax_boundary_undercut(sell, tax_exempt)
    if listed < sell:
        notes.append("list the sell at {:,}, not {:,} — identical net revenue "
                     "after tax, better queue position".format(listed, sell))
    return tuple(notes)


# Quote age at which confidence drops: (no longer Medium, Speculative). A
# display policy, by mode. Active trades the print now, so minutes matter. An
# Away bid rests for hours, where the price can move far more than in a few
# minutes of quote age — the staleness factor already discounts the score by
# the item's own volatility — and the automatic Away profile admits quotes up
# to 15 minutes old, which the Active limit then contradicted by declaring
# them all Speculative. Max profit places its offer at the live quote now,
# like Active, so it uses Active's limits.
QUOTE_AGE_LIMITS = {
    engine.TradeMode.ACTIVE: (180, 300),
    engine.TradeMode.OVERNIGHT: (600, 900),
    engine.TradeMode.PROFIT: (180, 300),
}


def quote_age_limits(mode: engine.TradeMode) -> Tuple[int, int]:
    return QUOTE_AGE_LIMITS[engine.TradeMode(mode)]


def confidence_label(row: FlipRow) -> str:
    """One confidence policy shared by the Python surfaces.

    This is model-evidence confidence, never a guarantee of execution. A quote
    reconstructed from bucket averages or a detected regime shift cannot be
    High however attractive its point estimate looks.
    """
    retained = row.shrink_retention
    interval_width = ((row.fill_high_qty - row.fill_low_qty) /
                      max(1.0, row.qty_per_window))
    regime = row.regime_score or 0.0
    fresh_limit, stale_limit = quote_age_limits(row.trade_mode)
    stale = row.quote_age > stale_limit
    if stale or regime >= engine.DEFAULT_CALIBRATION.regime_shift_threshold:
        return "Speculative"
    if (not row.priced_from_reference and row.deep_checked
            and row.edge_probability >= 0.80 and row.p_fill >= 0.50
            and row.thin_volume_1h >= 200 and retained >= 0.85
            and interval_width <= 0.55 and row.execution_quality >= 0.62):
        return "High"
    if (row.edge_probability >= 0.55 and row.p_fill >= 0.25
            and row.quote_age <= fresh_limit and interval_width <= 0.85
            and row.execution_quality >= 0.45):
        return "Medium"
    return "Speculative"
