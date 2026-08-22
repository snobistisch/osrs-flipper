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
from typing import Callable, Dict, List, Optional, Tuple, Union

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
        if not 0 < int(self.capital) <= engine.MAX_CASH_STACK:
            raise ValueError("capital must fit in the OSRS cash stack")

    @property
    def slots(self) -> int:
        return self.account.slots

    @property
    def include_members(self) -> bool:
        return self.account.allows_members_items

    @property
    def horizon_hours(self) -> float:
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
    sell_listed_at: int      # where to actually list: free undercut at tax steps

    # fill model
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
    raw_ranking_value: float      # active: gp/slot/h; overnight: horizon EV
    ranking_value: float          # same metric after shrinkage
    downside_risk_gp: float
    trade_mode: engine.TradeMode
    horizon_hours: float

    factors: Dict[str, float] = field(default_factory=dict)
    warnings: Tuple[str, ...] = field(default=())

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
    # Affordability still uses the equal split: what one flip can absorb has to
    # be known before it is scored, and the score-weighted allocation needs the
    # scores. The equal split is the cap used for sizing; allocate() reports
    # the proportional split that should actually be deployed.
    per_slot = engine.capital_per_slot(config.capital, config.slots)
    for item_id, quote in quotes.items():
        result = _evaluate(item_id, quote, items.get(item_id),
                           activity_5m.get(item_id), activity_1h.get(item_id),
                           config, per_slot, now, exempt, volume_lookup)
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


def _evaluate(
    item_id: int,
    quote: Quote,
    item: Optional[Item],
    act_5m: Optional[Activity],
    act_1h: Optional[Activity],
    config: FilterConfig,
    per_slot: int,
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
            or quote.low <= 0):
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
    margin = engine.net_margin(buy, sell, tax_exempt)
    if margin <= 0:
        return "margin not positive"

    affordable = per_slot // buy if buy > 0 else 0
    if affordable == 0:
        return "cannot afford one"

    depth = engine.undercut_depth(buy, sell, tax_exempt)
    # Sizing uses the same queue share the score will: on a crowded item you
    # cannot fill more than the crowd leaves you, so pretending otherwise here
    # would size an offer the fill model then has to discount back down.
    crowd = engine.touch_competitors(thin_volume, item.limit,
                                     config.calibration)
    share = engine.aggressiveness(engine.price_edge(depth, sell - buy),
                                  config.calibration, crowd)

    qty = engine.flippable_qty(
        item.limit,
        engine.fillable_quantity(thin_volume, share,
                                 config.horizon_hours / engine.LEGS_PER_ROUND_TRIP),
        affordable)
    if qty <= 0:
        # The market cannot hand over a single unit inside the horizon at this
        # queue position. Not a rejection of the item, but there is nothing to
        # size, so score it at one unit and let the fill model discount it.
        qty = 1

    drift = engine.price_drift(_mid(act_5m), _mid(act_1h))
    ofi = engine.order_flow_imbalance(high_vol_1h, low_vol_1h)

    breakdown = engine.score_flip(
        buy=buy, sell=sell, margin=margin, qty=qty, depth=depth,
        buy_volume_1h=low_vol_1h, sell_volume_1h=high_vol_1h,
        quote_age=age, ofi=ofi, drift=drift, now=now,
        highalch=item.highalch, nature_rune_cost=config.nature_rune_cost,
        competitors=crowd, mode=config.trade_mode,
        horizon_hours=config.horizon_hours, calibration=config.calibration)

    floor = engine.alch_floor(item.highalch, config.nature_rune_cost)
    return FlipRow(
        item_id=item_id, name=item.name, buy=buy, sell=sell,
        latest_low=quote.low, latest_high=quote.high,
        tax=engine.ge_tax(sell, tax_exempt), margin=margin,
        roi=engine.roi(buy, sell, tax_exempt),
        limit=item.limit, members=bool(item.members),
        thin_volume_1h=thin_volume, qty_per_window=qty,
        volume_1h_total=int(high_vol_1h + low_vol_1h),
        capital_needed=breakdown.capital_needed,
        gross_profit=breakdown.raw_profit, undercut_depth=depth,
        drift=drift, ofi=ofi, quote_age=age, tax_exempt=tax_exempt,
        sell_listed_at=engine.tax_boundary_undercut(sell, tax_exempt),
        expected_buy_seconds=breakdown.buy_seconds,
        expected_sell_seconds=breakdown.sell_seconds,
        expected_total_seconds=breakdown.total_seconds,
        p_fill=breakdown.p_fill_both,
        p_stranded=breakdown.p_stranded,
        expected_round_trip_qty=breakdown.expected_round_trip_qty,
        expected_gp=breakdown.expected_profit,
        raw_gp_per_slot_hour=breakdown.gp_per_slot_hour,
        gp_per_slot_hour=breakdown.gp_per_slot_hour,
        edge_probability=1.0,
        raw_ranking_value=breakdown.ranking_value,
        ranking_value=breakdown.ranking_value,
        downside_risk_gp=breakdown.downside_risk_gp,
        trade_mode=breakdown.mode, horizon_hours=breakdown.horizon_hours,
        factors=breakdown.factors(),
        alch_floor=floor,
        alch_distance=engine.alch_distance(buy, floor),
        alch_arbitrage_gp=breakdown.alch_arbitrage_gp,
        warnings=_warnings(depth, drift, ofi, affordable, qty, item.limit,
                           priced.from_reference,
                           breakdown, sell, tax_exempt),
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
        rows[index] = _rescore_with_history(row, view, config, now)

    rows, shrinkage = _apply_shrinkage(rows, config)
    rows.sort(key=lambda r: r.ranking_value, reverse=True)
    return ScreenResult(rows=rows, funnel=result.funnel,
                        shrinkage=shrinkage, deep_checked=refined_count)


def _rescore_with_history(row: FlipRow, view: engine.HistoryView,
                          config: FilterConfig, now: float) -> FlipRow:
    """Recompute one row with the OU fit and the reachable-volume estimate."""
    # The share of multi-day volume that traded at your prices is evidence
    # about the rate your offer fills at, not a separate penalty on profit. A
    # price only 5% of the market ever reached is not a flip earning 5% of its
    # margin — it is a flip that takes twenty times as long.
    reachable_buy = max(0.0, row.thin_volume_1h * max(view.buy_fill_share, 0.01))
    reachable_sell = max(0.0, row.thin_volume_1h * max(view.sell_fill_share, 0.01))

    depth = row.undercut_depth
    # Crowd from the item's REAL volume, not the reachable slice: a low fill
    # share means fewer units arrive at your price, not fewer rivals queued.
    crowd = engine.touch_competitors(row.thin_volume_1h, row.limit,
                                     config.calibration)
    share = engine.aggressiveness(engine.price_edge(depth, row.sell - row.buy),
                                  config.calibration, crowd)
    qty = engine.flippable_qty(
        row.limit,
        engine.fillable_quantity(min(reachable_buy, reachable_sell), share,
                                 config.horizon_hours / engine.LEGS_PER_ROUND_TRIP),
        row.capital_needed // row.buy if row.buy > 0 else None)
    qty = max(1, qty)

    sigma = view.ou.sigma if view.ou is not None else None
    breakdown = engine.score_flip(
        buy=row.buy, sell=row.sell, margin=row.margin, qty=qty, depth=depth,
        buy_volume_1h=reachable_buy, sell_volume_1h=reachable_sell,
        quote_age=row.quote_age, ofi=row.ofi, drift=row.drift, now=now,
        sigma_daily=sigma, ou_fit=view.ou, regime_score=view.regime_score,
        competitors=crowd,
        highalch=None if row.alch_floor is None
        else row.alch_floor + config.nature_rune_cost,
        nature_rune_cost=config.nature_rune_cost,
        mode=config.trade_mode, horizon_hours=config.horizon_hours,
        calibration=config.calibration)

    return replace(
        row,
        qty_per_window=qty, capital_needed=breakdown.capital_needed,
        gross_profit=breakdown.raw_profit,
        expected_buy_seconds=breakdown.buy_seconds,
        expected_sell_seconds=breakdown.sell_seconds,
        expected_total_seconds=breakdown.total_seconds,
        p_fill=breakdown.p_fill_both,
        p_stranded=breakdown.p_stranded,
        expected_round_trip_qty=breakdown.expected_round_trip_qty,
        expected_gp=breakdown.expected_profit,
        raw_gp_per_slot_hour=breakdown.gp_per_slot_hour,
        gp_per_slot_hour=breakdown.gp_per_slot_hour,
        raw_ranking_value=breakdown.ranking_value,
        ranking_value=breakdown.ranking_value,
        downside_risk_gp=breakdown.downside_risk_gp,
        trade_mode=breakdown.mode, horizon_hours=breakdown.horizon_hours,
        factors=breakdown.factors(),
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
        warnings=row.warnings + _history_warnings(view),
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
    """Construct an executable plan, leaving non-positive slots open."""
    rows = list(result.rows)
    if not rows:
        return result
    count = min(len(rows), config.slots)
    candidates = rows[:count]
    amounts = engine.allocate_portfolio(
        [row.ranking_value if row.expected_gp > 0 else 0.0
         for row in candidates],
        config.capital, [row.buy for row in candidates],
        [row.capital_needed for row in candidates], config.slots)
    for index, amount in enumerate(amounts):
        row = rows[index]
        quantity = amount // row.buy if amount > 0 and row.buy > 0 else 0
        scale = quantity / row.qty_per_window if row.qty_per_window > 0 else 0.0
        rows[index] = replace(
            row, allocated_capital=amount, allocated_quantity=quantity,
            allocated_expected_gp=row.expected_gp * scale)
    return ScreenResult(rows=rows, funnel=result.funnel,
                        shrinkage=result.shrinkage,
                        deep_checked=result.deep_checked, hidden=result.hidden)


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
) -> ScreenResult:
    """The whole pipeline: score, shrink, deep-check, filter, allocate."""
    result = screen(items, quotes, activity_5m, activity_1h, config, now, exempt,
                    volume_lookup)
    if fetch_history is not None and top_k > 0:
        result = refine_with_history(result, fetch_history, config, now, top_k)
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


def _warnings(depth: int, drift: float, ofi: float, affordable: int, qty: int,
              limit: Optional[int], from_reference: bool,
              breakdown: engine.ScoreBreakdown,
              sell: int, tax_exempt: bool) -> Tuple[str, ...]:
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
    if breakdown.total_seconds == float("inf"):
        notes.append("no realistic fill on one side — the book is one-sided")
    elif breakdown.total_seconds > 8 * engine.SECONDS_PER_HOUR:
        notes.append("expected round trip {} — the slot is the cost, not the gp"
                     .format(engine.format_duration(breakdown.total_seconds)))
    if breakdown.p_fill_both < 0.25:
        notes.append("only {:.0%} chance both legs clear inside {:.0f}h"
                     .format(breakdown.p_fill_both,
                             breakdown.horizon_hours))
    if (breakdown.mode is engine.TradeMode.OVERNIGHT
            and breakdown.p_stranded >= 0.20):
        notes.append("{:.0%} chance you return holding bought inventory; "
                     "stress downside is {:,.0f} gp"
                     .format(breakdown.p_stranded,
                             breakdown.downside_risk_gp))
    if drift <= -0.02:
        notes.append("price falling {:.1%} — your buy fills, your sell may not"
                     .format(abs(drift)))
    elif drift >= 0.02:
        notes.append("price rising {:.1%} — your buy may not fill".format(drift))
    if ofi <= -0.3:
        notes.append("sellers are {:.0%} of aggressor volume — you would be "
                     "catching what they are dumping".format(abs(ofi)))
    if qty and affordable <= qty:
        notes.append("capital-bound, not limit-bound — a bigger slot buys more")
    if limit is None:
        notes.append("no published buy limit")
    listed = engine.tax_boundary_undercut(sell, tax_exempt)
    if listed < sell:
        notes.append("list the sell at {:,}, not {:,} — identical net revenue "
                     "after tax, better queue position".format(listed, sell))
    return tuple(notes)
