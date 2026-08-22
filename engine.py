"""Flip math. No I/O, no API types, no third-party imports — all unit-testable.

A quoted margin is not profit. It is profit *if* both legs fill, and the Grand
Exchange guarantees nothing. Everything here turns a quoted margin into an
expected value per slot-hour.

What changed from the first version, and why:

- The old score multiplied nine hand-tuned factors together and divided by four
  hours. Nine multiplicative constants against one observable outcome cannot be
  calibrated: when a flip underdelivers, no amount of journal data can say
  which factor was wrong, because they only ever appear as a product. Worse,
  four hours was assumed, not modelled — an item that fills in twelve minutes
  and one that takes the whole window were treated as differing only in size.
- Fill time is now a random variable with a rate estimated from traded volume,
  so gp/slot/hour is profit divided by the time a slot is actually occupied.
- Undercut depth feeds the fill rate instead of being its own invented
  multiplier: the gp of price improvement you can afford *is* how far you can
  jump the queue, which is what changes your fill rate.
- Level and volatility come from a per-item Ornstein-Uhlenbeck fit rather than
  from one exponential decay constant applied to every item in the game.
- Every remaining free parameter lives in `Calibration` below, each marked
  DERIVED (forced by game mechanics or arithmetic) or CALIBRATE (a prior, to be
  fitted from journal and archive data). Nothing is tuned by feel in the body
  of a function.

Conventions:
- The buy side of a flip fills near the instant-sell price ("low"); the sell
  side fills near the instant-buy price ("high").
- Tax as of 29 May 2025: seller pays 2% rounded down, capped at 5m per item.
  Sub-50 gp sells are untaxed because floor(price * 0.02) is 0 there.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

import stats

TAX_RATE = 0.02
TAX_CAP = 5_000_000

# The GE tax rounds down, so every 50 gp of sell price is one more gp of tax.
# Between two multiples of 50 the seller's net revenue is flat, which makes
# undercutting inside that band free. See tax_boundary_undercut.
TAX_STEP = int(round(1 / TAX_RATE))    # 50 gp per 1 gp of tax — DERIVED

WINDOW_HOURS = 4                  # the buy-limit window

# There used to be constants here for extrapolating one bucket's volume across
# the window (x48 for 5m buckets, x4 for 1h). The fill model replaced them:
# throughput is now a rate scaled by your queue share, not one sample multiplied
# by a number.

# Offer slots cap how many flips you can run at once — the real bottleneck long
# before gp is. Free-to-play gets three; members get eight.
F2P_SLOTS = 3
MEMBER_SLOTS = 8


class AccountType(str, Enum):
    """A coherent GE account profile.

    Slot count and members-item access are game rules, not independent user
    preferences.  Keeping them behind one value makes contradictory states
    unrepresentable in the normal application flow.
    """

    MEMBERS = "members"
    FREE_TO_PLAY = "free-to-play"

    @property
    def slots(self) -> int:
        return MEMBER_SLOTS if self is AccountType.MEMBERS else F2P_SLOTS

    @property
    def allows_members_items(self) -> bool:
        return self is AccountType.MEMBERS


class TradeMode(str, Enum):
    """The decision horizon changes the utility function, not just the copy."""

    ACTIVE = "active"
    OVERNIGHT = "overnight"


DEFAULT_ACCOUNT = AccountType.MEMBERS
DEFAULT_TRADE_MODE = TradeMode.ACTIVE
DEFAULT_OVERNIGHT_HOURS = 8.0
OVERNIGHT_HORIZON_PRESETS = (6.0, 8.0, 10.0, 12.0)


@dataclass(frozen=True)
class TradingProfile:
    """Player/account state shared by the CLI, Streamlit and browser ports."""

    account: AccountType = DEFAULT_ACCOUNT
    mode: TradeMode = DEFAULT_TRADE_MODE
    overnight_hours: float = DEFAULT_OVERNIGHT_HOURS

    def __post_init__(self) -> None:
        object.__setattr__(self, "account", AccountType(self.account))
        object.__setattr__(self, "mode", TradeMode(self.mode))
        if not 1.0 <= float(self.overnight_hours) <= 24.0:
            raise ValueError("overnight horizon must be between 1 and 24 hours")

    @property
    def slots(self) -> int:
        return self.account.slots

    @property
    def include_members(self) -> bool:
        return self.account.allows_members_items

    @property
    def horizon_hours(self) -> float:
        return (float(self.overnight_hours)
                if self.mode is TradeMode.OVERNIGHT else float(WINDOW_HOURS))

MAX_CASH_STACK = 2_147_483_647    # the game's coin cap

# Prices are whole gp, so this is the smallest move the market can make and the
# resolution of every percentage computed from two prices. DERIVED.
PRICE_TICK = 1

SECONDS_PER_HOUR = 3600.0
HOURS_PER_DAY = 24.0

# A flip is two sequential legs sharing one window: you cannot list the sell
# until the buy has filled. Sizing an offer against the whole window therefore
# guarantees the sell leg has no time left in it — the buy consumes the horizon
# and the round trip never completes. Each leg gets half. DERIVED.
LEGS_PER_ROUND_TRIP = 2

# /timeseries at 6h buckets, two weeks back. Kept as the default lookback, but
# the OU fit reports its own half-life so an item whose dynamics run faster or
# slower than this window is now visible rather than silently mismodelled.
HISTORY_TIMESTEP = "6h"
HISTORY_BUCKET_HOURS = 6.0
HISTORY_BUCKET_DAYS = HISTORY_BUCKET_HOURS / HOURS_PER_DAY
HISTORY_WINDOW_BUCKETS = 56       # 14 days of 6h buckets
MIN_HISTORY_BUCKETS = 8           # fewer traded buckets: refuse to refine
RECENT_TREND_BUCKETS = 12         # ~3 days
FILL_TOLERANCE = 0.01             # prices within 1% count as reachable

_GP_SUFFIXES = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


# ---------------------------------------------------------------------------
# Free parameters, all in one place
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Calibration:
    """Every number the model cannot derive from game mechanics.

    DERIVED  — forced by the rules of the game or by arithmetic; not free.
    MEASURED — read from the data at runtime, not stored here.
    CALIBRATE — a prior. Fit it from journal outcomes (journal.py records the
                inputs) or from the tick archive (archive.py). Until then it is
                a stated belief, and it is stated *here* rather than buried in
                a function body so it can be changed in one place and so the
                journal can record which values produced a prediction.
    """

    # -- fill model ---------------------------------------------------------
    # FLOOR on how many offers you are queued behind at the touch price; your
    # share of arriving volume there is 1/competitors. This was a flat constant
    # and it was the single worst assumption in the model: four competitors on
    # every item in the game, including fire runes, where it handed you a
    # quarter of 1.7 million units an hour and called a day-long flip a
    # two-hour one. touch_competitors now raises it per item from the volume
    # the item actually has to move against its buy limit, and this value only
    # applies where that crowd term does not bind — a quiet item nobody else is
    # watching. CALIBRATE: from the tick archive, as observed fill rate divided
    # by total volume at the touch.
    competitors_at_touch: float = 4.0

    # How much of the spread you must concede before you have essentially
    # jumped the whole queue. Expressed as a fraction of the spread rather than
    # of the price: 1 gp of improvement is decisive on a 3 gp spread and
    # meaningless on a 300 gp one, and normalising by the mid instead would
    # rank cheap items and expensive ones on different scales — which is how
    # the old fixed-gp queue constant misranked them.
    # CALIBRATE: regress observed fill rate on distance from the touch.
    aggressiveness_scale: float = 0.25

    # How far the volume-weighted reference may sit from the last print before
    # the two stop being estimates of the same price. Only consulted when the
    # last two prints show no spread at all and the reference is the only
    # two-sided evidence left — see executable_prices. Measured on live data on
    # 2026-07-27 across the 359 items where that happens: the divergence
    # between the two mids has a median of 3%, a 75th percentile of 10% and a
    # 90th of 25%. Above that the population is items trading a handful of
    # units an hour, where the average rests on one or two trades: yellow boots
    # at 1 unit/hour printed 1918/2013 against a reference of 3145/5000.
    # CALIBRATE: from the journal, as the fill rate of flips admitted this way.
    reference_fallback_max_divergence: float = 0.25

    # Floor on how long one leg can take. Not a market property: placing an
    # offer, returning to the GE and collecting takes a human about a minute,
    # so no flip cycles faster than this however thick the book is. DERIVED
    # from the interaction, not from prices.
    min_leg_seconds: float = 60.0

    # -- adverse selection --------------------------------------------------
    # Sensitivity to order-flow imbalance running against the position.
    # CALIBRATE: regress holding-period return on OFI at entry.
    adverse_selection_gamma: float = 0.5
    # Sensitivity to price drift between the 5m and 1h mids. Falling markets
    # are penalised harder than rising ones: a resting buy fills fastest
    # exactly when someone is dumping into it, and then the sell leg is
    # stranded above the market. CALIBRATE alongside gamma.
    drift_penalty_falling: float = 8.0
    drift_penalty_rising: float = 4.0
    adverse_selection_floor: float = 0.2

    # -- holding-period risk ------------------------------------------------
    # Risk aversion over the price move between the two legs. eta = 1 prices a
    # one-sigma adverse move as a full sigma of discount. CALIBRATE: choose to
    # hit a target Sharpe on journal outcomes.
    risk_aversion_eta: float = 1.0
    # Same idea applied to the age of the quote you are trading against: the
    # price may already have moved since that print. CALIBRATE.
    staleness_eta: float = 1.0
    # Volatility (per sqrt-day, log scale) assumed when no OU fit exists yet.
    # CALIBRATE: the cross-sectional median of fitted sigmas.
    default_sigma_daily: float = 0.05

    # -- mean reversion and trend ------------------------------------------
    # Weight on the OU-implied expected return over the holding period.
    # CALIBRATE: regress realised holding-period return on the OU prediction.
    mean_reversion_omega: float = 1.0
    # Cap on how much mean reversion may move a score, either way. Keeps a
    # badly conditioned fit on a thin item from dominating the ranking.
    mean_reversion_cap: float = 0.5
    # Trending items get a much smaller, capped credit than reverting ones: a
    # rising price and a merch-clan pump are indistinguishable from price data
    # alone, so this stays deliberately timid. CALIBRATE.
    trend_tau: float = 0.5
    trend_cap: float = 0.10
    # Above this regime-shift score the OU fit spans two different markets and
    # its mean is meaningless. CALIBRATE.
    regime_shift_threshold: float = 4.0

    # -- structural ---------------------------------------------------------
    # Credit for buying near the high-alchemy floor, which caps the downside.
    # CALIBRATE: the most you should overpay for that protection.
    alch_alpha: float = 2.0
    # Ignore the alch floor further than this below the buy price — protection
    # 40% below the market is not protection you will ever use. DERIVED-ish.
    alch_relevant_distance: float = 0.40

    # -- update risk --------------------------------------------------------
    # Discount for a flip whose sell leg is still open when the weekly update
    # lands. CALIBRATE: compare realised returns across updates.
    update_risk_penalty: float = 0.35
    # Hours before the update at which the discount starts to bite.
    update_risk_lead_hours: float = 6.0

    # -- shrinkage ----------------------------------------------------------
    # Estimation noise on a log score has two parts.
    #
    # Sampling noise falls as 1/sqrt(observed volume): this is the scale at one
    # unit per hour. CALIBRATE: from the dispersion of repeated scores for the
    # same item in the tick archive.
    score_noise_scale: float = 3.0
    # Irreducible noise that no amount of volume removes. A margin is inferred
    # from two prints, and the question a score really answers is whether that
    # spread will still be there when your offer is resting — which the volume
    # behind those prints says nothing about. Without this floor the busiest
    # items are treated as measured almost exactly, and shrinkage stops doing
    # anything at the top of the list, which is the one place it matters.
    # CALIBRATE: from how far an item's score moves between consecutive polls.
    # 0.35 on a log scale is roughly +/-40%, which is about how much a liquid
    # item's computed score wanders poll to poll. Setting it much higher starts
    # declaring genuine 3x differences to be noise.
    score_noise_floor: float = 0.35

    # -- merching (see merch.py) --------------------------------------------
    # These govern a different horizon from everything above: weeks of holding
    # rather than hours of flipping. They live here anyway, because "every free
    # parameter in one place" is worth more than a tidy split by module.
    #
    # How much of the price movement the trend has to explain before the label
    # is allowed to mean anything. Below this the item wandered and finished
    # higher. CALIBRATE: from how often an UPTREND label survives the next
    # quarter.
    merch_min_r2: float = 0.10
    # Annual rate a trend must clear in either direction. Statistical
    # significance is not enough on 365 points — a 2%/yr drift clears any t.
    merch_min_annual_pct: float = 8.0
    # |t| on the daily slope, after the autocorrelation correction in
    # merch._autocorrelation_robust_t. It is far above the 2.0 used for mean
    # reversion, and that is not timidity — it is measured. A year of daily
    # prices with NO drift at all still wanders far enough to show an apparent
    # annual trend of tens of percent. Simulating driftless random walks:
    #
    #     |t| >= 1.5   61% of pure noise labelled a trend
    #     |t| >= 2.5   42%
    #     |t| >= 5.0   16%
    #     |t| >= 8.0    6%
    #
    # The curve is scale-free — repeating it at 1.2%, 2.1% and 3.5% daily
    # volatility moves it by under a point — so one threshold serves every item.
    # At the 2.1% median volatility measured across the watchlist, |t| >= 5.0
    # finds 34% of genuine +73%/yr trends, 58% of +150%/yr, and 89% of +334%/yr.
    #
    # That low power on modest trends is not a defect to tune away. It is what
    # a year of daily prices can support, and the honest consequence is that
    # several watchlist items with headline rates near +50%/yr are reported as
    # SIDEWAYS: 40% of trendless items would look exactly that trendy. Every
    # item still carries merch.Trend.noise_probability so the user sees the
    # strength rather than only the verdict. test_merch.py locks both the
    # false-positive rate and the survival curve.
    merch_trend_t: float = 5.0
    # How far under its own trend line an item must sit to call it an entry.
    merch_entry_threshold: float = -0.03
    # Discount on a bot-supplied item's merch score. The supply curve is a
    # script, not a player, and it answers a price rise by producing more.
    # CALIBRATE.
    merch_botted_penalty: float = 0.60

    # -- crash detection ----------------------------------------------------
    # Depth is HistoryView.elevation: negative means below the 14-day median.
    # A crash is deep AND loud; a quiet slide of the same depth is classified
    # separately because there is no forced seller to wait out.
    crash_depth: float = -0.35
    crash_volume_spike: float = 3.0
    dip_depth: float = -0.20
    dip_volume_spike: float = 2.0
    quiet_dip_depth: float = -0.30
    quiet_volume_ratio: float = 1.50
    # The mirror image: trading well above its median on thin volume, which is
    # what a pump looks like from the outside.
    pumped_elevation: float = 0.15
    pumped_volume_ratio: float = 0.30
    # Percentile of daily volume taken as "normal". A mean would be dragged up
    # by the very spike the ratio exists to detect.
    volume_baseline_percentile: float = 0.70

    # -- supply crunch ------------------------------------------------------
    # Fractional change in traded volume against six months earlier.
    supply_crunch_decline: float = -0.80
    supply_drop_decline: float = -0.50
    # Below this price the pool of players who can fund the catch-up is much
    # larger, which is what makes the thesis work faster. CALIBRATE.
    raid_catch_up_gp: float = 10_000_000.0

    # -- horizon ------------------------------------------------------------
    horizon_hours: float = float(WINDOW_HOURS)


DEFAULT_CALIBRATION = Calibration()


# ---------------------------------------------------------------------------
# gp formatting
# ---------------------------------------------------------------------------

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
        if abs(amount) >= size:
            text = "{:.1f}".format(amount / size).rstrip("0").rstrip(".")
            return text + suffix
    return "{:,}".format(amount)


def format_duration(seconds: float) -> str:
    """'40s', '12m', '3.5h', '2d' — for expected fill times."""
    if seconds != seconds or seconds == float("inf"):
        return "never"
    if seconds < 90:
        return "{:.0f}s".format(seconds)
    if seconds < 5400:
        return "{:.0f}m".format(seconds / 60)
    if seconds < 48 * SECONDS_PER_HOUR:
        return "{:.1f}h".format(seconds / SECONDS_PER_HOUR).replace(".0h", "h")
    return "{:.0f}d".format(seconds / (24 * SECONDS_PER_HOUR))


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------

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


class Executable(NamedTuple):
    buy: int
    sell: int
    # True when the pessimistic blend collapsed and the prices came from the
    # volume-weighted averages instead. The caller warns; the score does not
    # change, because the reliability machinery downstream already prices thin
    # or contradictory evidence.
    from_reference: bool = False


def executable_prices(
    latest_low: int,
    latest_high: int,
    ref_low: Optional[int] = None,
    ref_high: Optional[int] = None,
    calibration: Calibration = DEFAULT_CALIBRATION,
) -> Executable:
    """Conservative (buy, sell) estimate for what will actually fill.

    /latest is the single most recent trade per side, so one outlier offer can
    set it anywhere. Take the pessimistic combination per side: you buy at the
    HIGHER of (last instant-sell, reference low) and sell at the LOWER of
    (last instant-buy, reference high).

    That blend is right while the two sides of /latest are independent
    observations of the two sides of the book. It is wrong when they are not,
    and it fails in a way that used to discard the best flips in the game. If
    the last instant-buy and the last instant-sell are the same price — one
    trade that crossed, or two prints from moments when the price had moved —
    the blend returns buy >= sell, the margin comes out zero, and the item is
    rejected before anything scores it. Measured on live data on 2026-07-27:
    248 free-to-play items were rejected that way, and the volume-weighted
    averages showed a real spread on 88 of them. Salmon was one — /latest said
    24/24 with both sides printed at the same instant, while the hour's
    averages said 24 -> 27, a 12.5% tax-free margin on 2,652 units an hour.

    Two prints that show no spread are not evidence that there is no spread.
    They are the absence of evidence, and the 5m/1h volume-weighted averages
    measure both sides over many trades, which is the better estimator. So when
    the blend collapses, fall back to the reference pair.

    One guard survives, and it is not a quality judgement: the two sources must
    still be describing the same market. Raw shrimps printed 30/27 against a
    reference of 5/6 — the two estimates of the same price are 81% apart, so
    one of them is about something that is no longer true and there is nothing
    to trade on. Measured across the 359 items where the blend collapsed, the
    divergence between the two mids has a median of 3% and a 90th percentile of
    25%; past that the population is items trading a handful of units an hour,
    whose "average" rests on one or two prints. See
    `reference_fallback_max_divergence`.

    Everything that is merely *unreliable* rather than contradictory is scored
    and then discounted by shrinkage and the deep check, which is the division
    of labour the rest of the model already assumes.
    """
    buy = latest_low if ref_low is None else max(latest_low, ref_low)
    sell = latest_high if ref_high is None else min(latest_high, ref_high)
    if buy < sell:
        return Executable(buy, sell, False)

    if ref_low is None or ref_high is None:
        return Executable(buy, sell, False)
    reference_buy = int(round(ref_low))
    reference_sell = int(round(ref_high))
    if reference_buy >= reference_sell:
        return Executable(buy, sell, False)      # not two-sided either

    latest_mid = (latest_low + latest_high) / 2.0
    if latest_mid <= 0:
        return Executable(buy, sell, False)
    reference_mid = (reference_buy + reference_sell) / 2.0
    divergence = abs(reference_mid / latest_mid - 1.0)
    if divergence > calibration.reference_fallback_max_divergence:
        return Executable(buy, sell, False)      # the sources contradict
    return Executable(reference_buy, reference_sell, True)


def ge_tax(sell_price: int, tax_exempt: bool = False) -> int:
    """Tax the seller pays on one item."""
    if tax_exempt:
        return 0
    return min(TAX_CAP, math.floor(sell_price * TAX_RATE))


def net_revenue(sell_price: int, tax_exempt: bool = False) -> int:
    """What the seller actually receives."""
    return sell_price - ge_tax(sell_price, tax_exempt)


def net_margin(buy_price: int, sell_price: int, tax_exempt: bool = False) -> int:
    """Profit on one item after tax. Negative when the spread can't cover tax."""
    return net_revenue(sell_price, tax_exempt) - buy_price


def roi(buy_price: int, sell_price: int, tax_exempt: bool = False) -> float:
    """Net margin as a fraction of capital tied up per item."""
    if buy_price <= 0:
        return 0.0
    return net_margin(buy_price, sell_price, tax_exempt) / buy_price


def tax_boundary_undercut(sell_price: int, tax_exempt: bool = False) -> int:
    """Lowest sell price with the same net revenue as `sell_price`.

    Because the tax rounds down, net revenue is a staircase: selling at 100
    nets 98, and so does 99. Every gp between two multiples of 50 is priced
    identically to the seller, so undercutting inside that band buys queue
    priority for nothing. A flipper listing at exactly 1,000 when 999 nets the
    same is giving away position for free.

    Returns the price unchanged when it is already at the bottom of its band,
    when it is exempt, or when it is below the taxable threshold.
    """
    if tax_exempt or sell_price <= 0:
        return sell_price
    target = net_revenue(sell_price, tax_exempt)
    # The band cannot be wider than one tax step, so this walks at most TAX_STEP
    # prices even at the 5m cap.
    candidate = sell_price
    while candidate > 1 and net_revenue(candidate - 1, tax_exempt) >= target:
        candidate -= 1
    return candidate


def break_even_sell(buy_price: int, tax_exempt: bool = False) -> int:
    """Cheapest sell price that clears a profit of at least 1 gp per item."""
    if tax_exempt:
        return buy_price + 1
    # net(p) ~ 0.98p, so start just above the analytic solution and walk up.
    candidate = max(buy_price + 1, int(buy_price / (1 - TAX_RATE)))
    while net_margin(buy_price, candidate, tax_exempt) <= 0:
        candidate += 1
    return candidate


# ---------------------------------------------------------------------------
# Queue position
# ---------------------------------------------------------------------------

def undercut_depth(buy: int, sell: int, tax_exempt: bool = False) -> int:
    """How many gp of price improvement you can afford on each side at once
    while the flip still profits.

    The Grand Exchange matches on price first, then on offer age: at the same
    price, offers that are days old take near-absolute priority. So there are
    exactly two ways to get filled — outbid the queue, or wait behind a queue
    you cannot see and cannot measure.

    Depth 0 means every gp of price improvement costs more than the flip earns,
    so your offer sits behind everyone else's at the same tick. Air runes quoted
    at 5/6 are the canonical case: buying at 6 to sell at 5 is a guaranteed
    loss, so a 1 gp margin can only ever be won by waiting.

    Leather quoted at 173/192 has depth 7: bidding 180 to sell at 185 still
    clears 2 gp after tax, so you can pay for priority and still profit.

    Depth is no longer a score multiplier of its own. It is the input to the
    fill rate — how far ahead of the queue you can buy your way is precisely
    what determines how fast you fill.
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


def touch_competitors(volume_per_hour: float, buy_limit: Optional[int],
                      calibration: Calibration = DEFAULT_CALIBRATION) -> float:
    """How many offers you are queued behind at the touch price.

    This used to be the constant `competitors_at_touch`, and that constant was
    the model's worst assumption. It said four — on every item, including the
    ones where the spread is a single gp and every flipper in the game is
    looking at the same free money. On fire runes it therefore handed you 25%
    of 1.7 million units an hour and reported a two-hour round trip on a flip
    that takes a day.

    There is an observable lower bound on the size of the crowd, and it needs
    no new data. Every participant is capped at `buy_limit` units per window,
    so producing the window's observed volume takes at least
    `volume_per_window / buy_limit` of them. Fire runes: 6.7m units a window
    against a 50,000 limit, so at minimum 134 participants, not four. An
    ordinary item — limpwurt root, 124,000 a window against a 13,000 limit —
    comes to 9.5, and the floor keeps it near the old behaviour.

    The formula has a property worth stating, because it is what makes it
    believable rather than merely pessimistic: where the crowd term binds,
    your share is `buy_limit / volume_per_window`, so your fill rate is exactly
    one buy limit per window. On a crowded item you cannot beat your own buy
    limit, which is the correct answer and the one an hour of watching the
    Grand Exchange gives you.

    It is a lower bound, not a count: volume includes consumers and bots, and
    not everyone trading is queued at the touch. CALIBRATE against the journal
    once it holds enough censored observations to fit fill times properly.
    """
    base = max(1.0, calibration.competitors_at_touch)
    if not buy_limit or buy_limit <= 0 or volume_per_hour <= 0:
        return base
    per_window = volume_per_hour * calibration.horizon_hours
    return max(base, per_window / float(buy_limit))


def aggressiveness(edge: float,
                   calibration: Calibration = DEFAULT_CALIBRATION,
                   competitors: Optional[float] = None) -> float:
    """Share of arriving volume your offer captures, given how far inside the
    touch you are willing to price.

    At the touch you are one of N offers at that price and take roughly 1/N of
    what arrives, where N comes from touch_competitors. Concede some of the
    spread and you move ahead of them; concede enough and you are taking
    essentially everything that arrives.

    `edge` is the concession as a fraction of the spread, so an item with no
    room to improve — the air rune at 5/6, where the spread is one gp and the
    gp is the tick — sits at its queue share and cannot buy its way out. That
    is the trap this exists to price, and it only bites once N reflects how
    crowded the item really is.
    """
    crowd = competitors if competitors is not None else calibration.competitors_at_touch
    share = 1.0 / max(1.0, crowd)
    if edge <= 0:
        return share
    scale = max(calibration.aggressiveness_scale, 1e-9)
    return share + (1.0 - share) * (1.0 - math.exp(-edge / scale))


def price_edge(depth: int, spread: float) -> float:
    """Undercut room as a fraction of the spread it is being taken out of."""
    if spread <= 0:
        return 0.0
    return max(0.0, depth / spread)


# ---------------------------------------------------------------------------
# Fill time
# ---------------------------------------------------------------------------

def fill_rate(volume_per_hour: float, share: float) -> float:
    """Units per second your offer can expect to absorb."""
    if volume_per_hour <= 0 or share <= 0:
        return 0.0
    return (volume_per_hour / SECONDS_PER_HOUR) * share


def expected_fill_seconds(qty: int, rate: float,
                          calibration: Calibration = DEFAULT_CALIBRATION) -> float:
    """Mean time for one leg of `qty` units at `rate` units/second.

    Floored at min_leg_seconds: on a very liquid item the arithmetic says a
    small offer clears in under a second, but you still have to walk to the
    Grand Exchange and collect it.
    """
    if qty <= 0:
        return calibration.min_leg_seconds
    if rate <= 0:
        return float("inf")
    return max(calibration.min_leg_seconds, qty / rate)


def fill_probability(expected_seconds: float, horizon_seconds: float) -> float:
    """P(leg completes within the horizon), treating fill time as exponential.

    Exponential because offers are matched by an arrival process we cannot
    observe: memorylessness is the honest assumption when queue position is
    invisible. It has the right shape — most of the probability mass early,
    a long tail of offers that simply never fill.
    """
    if expected_seconds == float("inf") or expected_seconds <= 0:
        return 0.0
    if horizon_seconds <= 0:
        return 0.0
    return 1.0 - math.exp(-horizon_seconds / expected_seconds)


def round_trip_probability(buy_seconds: float, sell_seconds: float,
                           horizon_seconds: float) -> float:
    """Probability that two sequential exponential legs finish by ``horizon``.

    Multiplying two independent ``P(leg < horizon)`` values overstates the
    result because the sell cannot start until the buy completes.  This is the
    CDF of the sum of two exponentials (an Erlang when their rates match).
    """
    if (horizon_seconds <= 0 or buy_seconds <= 0 or sell_seconds <= 0
            or not math.isfinite(buy_seconds)
            or not math.isfinite(sell_seconds)):
        return 0.0
    buy_rate = 1.0 / buy_seconds
    sell_rate = 1.0 / sell_seconds
    if math.isclose(buy_rate, sell_rate, rel_tol=1e-9, abs_tol=1e-12):
        x = buy_rate * horizon_seconds
        return max(0.0, min(1.0, 1.0 - math.exp(-x) * (1.0 + x)))
    survival = ((sell_rate * math.exp(-buy_rate * horizon_seconds)
                 - buy_rate * math.exp(-sell_rate * horizon_seconds))
                / (sell_rate - buy_rate))
    return max(0.0, min(1.0, 1.0 - survival))


def stranded_inventory_probability(buy_seconds: float, sell_seconds: float,
                                    horizon_seconds: float) -> float:
    """Chance the buy completes but the round trip does not before return."""
    bought = fill_probability(buy_seconds, horizon_seconds)
    completed = round_trip_probability(buy_seconds, sell_seconds,
                                       horizon_seconds)
    return max(0.0, min(1.0, bought - completed))


def fillable_quantity(volume_per_hour: float, share: float,
                      horizon_hours: float) -> int:
    """Units the market can hand you on ONE leg inside the horizon.

    This replaces multiplying one bucket's thin-side volume by four. That
    extrapolation assumed the last hour repeats, ignored that you only get your
    share of the queue, and ignored that volume is strongly U-shaped over the
    day. Scaling the observed rate by your queue share prices the first two
    honestly; archive.py's EWMA addresses the third by smoothing the rate over
    days rather than trusting one bucket.

    Pass the per-leg horizon, not the whole window — see LEGS_PER_ROUND_TRIP.
    """
    rate = fill_rate(volume_per_hour, share)
    return max(0, int(rate * horizon_hours * SECONDS_PER_HOUR))


def leg_horizon_hours(calibration: "Calibration") -> float:
    """How long one leg may take if the round trip is to fit in the window."""
    return calibration.horizon_hours / LEGS_PER_ROUND_TRIP


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


# ---------------------------------------------------------------------------
# Adverse selection
# ---------------------------------------------------------------------------

def order_flow_imbalance(high_volume: float, low_volume: float) -> float:
    """Signed share of aggressor volume, in [-1, 1].

    Trades at the high price are buyer-initiated (someone lifted an ask);
    trades at the low price are seller-initiated (someone hit a bid). Positive
    means buyers were the aggressors. For a flipper the dangerous sign is
    negative: heavy seller-initiated flow is the flow that fills your resting
    buy right before the price keeps going down.
    """
    total = high_volume + low_volume
    if total <= 0:
        return 0.0
    return (high_volume - low_volume) / total


def resolvable_drift(mid_price: float) -> float:
    """Smallest price change the game's own grid can express, as a fraction.

    Prices are whole gp. A 10 gp item cannot move less than 10%; a 7,000 gp
    item cannot move less than 0.014%. Any measured drift at or below this is
    the grid, not the market.
    """
    if mid_price <= 0:
        return 0.0
    return PRICE_TICK / mid_price


def price_drift(mid_5m: Optional[float], mid_1h: Optional[float]) -> float:
    """Recent momentum, as a fraction of price. Negative means falling.

    Net of what the price grid can resolve, and that correction is the whole
    reason this is not a one-line subtraction. Measured across free-to-play
    items on 2026-07-27, the median absolute drift by price quartile was:

        cheapest quarter (median 10 gp)      7.07%
        second           (median 109 gp)     1.97%
        third            (median 495 gp)     0.93%
        dearest quarter  (median 7,396 gp)   0.61%

    A twelvefold difference produced by nothing but price. Prices move in whole
    gp, so on a 10 gp item the smallest possible change is 10% and on a 7,000
    gp item it is 0.014% — the raw percentage was mostly a measure of how cheap
    the item is. Fed into adverse_selection_factor at a penalty of 4 to 8 times
    the drift, it wiped most of the expected profit from every cheap item in
    the game and left expensive ones untouched, which is precisely the bias
    that filled the top of the ranking with 1%-margin flips on dear items.

    Salmon printed a 5-minute mid of 28.5 against an hour of 25.5: three gp,
    read as 11.8% of momentum, discounting the flip to 27% of its profit. Three
    gp on a 26 gp item is three ticks.
    """
    if mid_5m is None or mid_1h is None or mid_1h <= 0:
        return 0.0
    raw = (mid_5m - mid_1h) / mid_1h
    floor = resolvable_drift(mid_1h)
    if abs(raw) <= floor:
        return 0.0
    return math.copysign(abs(raw) - floor, raw)


def adverse_selection_factor(
    ofi: float, drift: float,
    calibration: Calibration = DEFAULT_CALIBRATION,
) -> float:
    """Discount for trading against informed flow.

    Two independent readings of the same hazard: order-flow imbalance says who
    is being aggressive right now, drift says where the price has been going.
    Both are penalised only in the direction that hurts a flipper — you are
    long between the legs, so selling pressure is the risk and buying pressure
    is not a symmetric gift.
    """
    penalty = 0.0
    if ofi < 0:
        penalty += calibration.adverse_selection_gamma * abs(ofi)
    if drift < 0:
        penalty += calibration.drift_penalty_falling * abs(drift)
    else:
        penalty += calibration.drift_penalty_rising * drift
    return max(calibration.adverse_selection_floor, 1.0 - penalty)


# ---------------------------------------------------------------------------
# Risk over time
# ---------------------------------------------------------------------------

def holding_risk(sigma_daily: float, hold_seconds: float,
                 calibration: Calibration = DEFAULT_CALIBRATION) -> float:
    """Discount for the price moving against you while you hold inventory.

    The buy leg fills first; until the sell leg fills you are long. The
    standard deviation of the price move over that window scales with the
    square root of its length, so a flip that sits for a day on a volatile item
    is a different proposition from the same margin cleared in ten minutes.
    The old model had one volatility discount that knew nothing about how long
    the position would be open.
    """
    if hold_seconds == float("inf"):
        return 0.0
    if sigma_daily <= 0 or hold_seconds <= 0:
        return 1.0
    days = hold_seconds / (SECONDS_PER_HOUR * HOURS_PER_DAY)
    return math.exp(-calibration.risk_aversion_eta * sigma_daily * math.sqrt(days))


def staleness_factor(age_seconds: float, sigma_daily: float,
                     calibration: Calibration = DEFAULT_CALIBRATION) -> float:
    """Confidence in a quote, given how far the price could have moved since.

    The old version halved confidence every 600 seconds for every item alike.
    That is too harsh on a liquid staple, where a 20-minute-old print is still
    the market, and too kind on a thin volatile one, where a 30-second-old
    print may already be gone. What actually decays is not time but price
    certainty, so the discount is driven by the item's own volatility over the
    elapsed time.
    """
    if age_seconds <= 0:
        return 1.0
    sigma = sigma_daily if sigma_daily > 0 else calibration.default_sigma_daily
    days = age_seconds / (SECONDS_PER_HOUR * HOURS_PER_DAY)
    return math.exp(-calibration.staleness_eta * sigma * math.sqrt(days))


# ---------------------------------------------------------------------------
# Mean reversion, from a per-item OU fit
# ---------------------------------------------------------------------------

def mean_reversion_factor(
    fit: Optional["stats.OUFit"], mid_price: float, hold_seconds: float,
    regime_score: float = 0.0,
    calibration: Calibration = DEFAULT_CALIBRATION,
) -> float:
    """EV multiplier from where the price sits relative to its own level.

    Replaces the old level and momentum factors. Those applied one exponential
    penalty above a 14-day median to every item in the game, which is right for
    a rune and wrong for a raid unique: supply of rare gear is fixed, demand
    grows, and "above its two-week median" is that item's permanent condition.

    An OU fit separates the two cases per item. Where reversion is real and
    statistically significant, the expected return over the *actual* holding
    period is credited or charged. Where it is not — a trending item, or one
    whose history straddles a game update that re-priced it — the fit is not
    trusted, and only a small capped trend term applies.
    """
    if fit is None or mid_price <= 0 or hold_seconds <= 0:
        return 1.0
    if hold_seconds == float("inf"):
        return 1.0
    days = hold_seconds / (SECONDS_PER_HOUR * HOURS_PER_DAY)

    if regime_score >= calibration.regime_shift_threshold:
        # The series spans two different markets; its mean is an average of a
        # level that no longer exists and one that has not settled.
        return 1.0

    if fit.mean_reverting:
        expected = fit.expected_log_return(mid_price, days)
        adjustment = calibration.mean_reversion_omega * expected
        cap = calibration.mean_reversion_cap
        return 1.0 + max(-cap, min(cap, adjustment))

    # Not significantly reverting: treat as a trend, timidly. A rising price
    # and a merch-clan pump look identical in price data, so the upside credit
    # is capped hard and the downside is not.
    drift_per_day = -fit.kappa * (fit.mu - math.log(mid_price))
    move = drift_per_day * days
    capped = max(-calibration.trend_cap, min(calibration.trend_cap, move))
    return max(0.5, 1.0 + calibration.trend_tau * capped)


# ---------------------------------------------------------------------------
# High alchemy — the floor under the price
# ---------------------------------------------------------------------------

def alch_floor(highalch: Optional[int], nature_rune_cost: int) -> Optional[int]:
    """Guaranteed gp per item from casting High Level Alchemy, net of the rune.

    No rational holder sells below this on the GE, because the spell pays it
    unconditionally. For a flipper it is a free put: the worst case on the sell
    leg is the floor, not zero.
    """
    if highalch is None or highalch <= 0:
        return None
    return highalch - nature_rune_cost


def alch_distance(buy_price: int, floor: Optional[int]) -> Optional[float]:
    """How far the buy price sits above the alchemy floor, as a fraction.

    Negative means the item is trading below what alching pays — a risk-free
    arbitrage that does not need a GE sell leg at all.
    """
    if floor is None or buy_price <= 0:
        return None
    return (buy_price - floor) / buy_price


def alch_bonus(distance: Optional[float],
               calibration: Calibration = DEFAULT_CALIBRATION) -> float:
    """Credit for downside that is capped by the alchemy floor.

    The old engine loaded highalch from /mapping into the Item dataclass and
    then never referenced it again.
    """
    if distance is None or distance >= calibration.alch_relevant_distance:
        return 1.0
    if distance <= 0:
        # Handled as an arbitrage by the caller, not as a multiplier — an
        # unbounded bonus here would swamp the ranking.
        return 1.0
    return math.exp(calibration.alch_alpha * (calibration.alch_relevant_distance
                                              - distance) / 10.0)


def alch_profit(highalch: Optional[int], buy_price: int,
                nature_rune_cost: int) -> Optional[int]:
    """Profit per item from buying on the GE and alching, or None if not alchable."""
    floor = alch_floor(highalch, nature_rune_cost)
    if floor is None:
        return None
    return floor - buy_price


# ---------------------------------------------------------------------------
# Weekly update risk
# ---------------------------------------------------------------------------

# OSRS ships its weekly update on Wednesday, historically around 11:00 UTC.
# Times slip, so this is a scheduling prior, not a guarantee.
UPDATE_WEEKDAY = 2        # Monday = 0
UPDATE_HOUR_UTC = 11


def seconds_until_update(now: float) -> float:
    """Seconds from `now` (unix) to the next weekly update window."""
    current = datetime.fromtimestamp(now, tz=timezone.utc)
    days_ahead = (UPDATE_WEEKDAY - current.weekday()) % 7
    target = current.replace(hour=UPDATE_HOUR_UTC, minute=0, second=0,
                             microsecond=0) + timedelta(days=days_ahead)
    if target <= current:
        target += timedelta(days=7)
    return (target - current).total_seconds()


def update_risk_factor(now: float, expected_hold_seconds: float,
                       calibration: Calibration = DEFAULT_CALIBRATION) -> float:
    """Discount for a position that is still open when the update lands.

    Patch notes are read by players faster than prices adjust, so anyone
    holding inventory across an update is the uninformed side of every trade
    that follows it. The penalty applies only when the flip is not expected to
    be closed in time — a ten-minute flip on Wednesday morning is unaffected.
    """
    if expected_hold_seconds <= 0:
        return 1.0
    horizon = expected_hold_seconds
    if horizon == float("inf"):
        horizon = calibration.horizon_hours * SECONDS_PER_HOUR
    until = seconds_until_update(now)
    lead = calibration.update_risk_lead_hours * SECONDS_PER_HOUR
    exposure = horizon + lead
    if until >= exposure:
        return 1.0
    # Ramps from no penalty at the edge of the exposure window to the full
    # penalty at the update itself.
    closeness = 1.0 - (until / exposure) if exposure > 0 else 1.0
    return max(0.0, 1.0 - calibration.update_risk_penalty * closeness)


# ---------------------------------------------------------------------------
# The score
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoreBreakdown:
    """Every term that produced a score, kept separately.

    The point of storing the decomposition rather than only the product: a
    nine-factor product against one realised number is unidentifiable, so the
    journal records each factor at entry and the error can afterwards be
    attributed to the factor that caused it.
    """
    qty: int
    margin: int
    raw_profit: int
    capital_needed: int

    buy_share: float
    sell_share: float
    buy_rate: float                 # units/second
    sell_rate: float
    buy_seconds: float
    sell_seconds: float
    total_seconds: float
    p_fill_buy: float
    p_fill_sell: float
    p_fill_both: float
    p_stranded: float
    expected_round_trip_qty: float

    adverse_selection: float
    holding_risk: float
    staleness: float
    mean_reversion: float
    alch: float
    update_risk: float

    expected_profit: float
    gp_per_slot_hour: float
    ranking_value: float
    downside_risk_gp: float
    mode: TradeMode
    horizon_hours: float

    alch_arbitrage_gp: Optional[int] = None   # per item, if below the floor

    def factors(self) -> Dict[str, float]:
        """Flat name -> value map, for journal recording and error attribution."""
        values = {
            "p_fill_both": self.p_fill_both,
            "adverse_selection": self.adverse_selection,
            "staleness": self.staleness,
            "mean_reversion": self.mean_reversion,
            "alch": self.alch,
            "update_risk": self.update_risk,
        }
        if self.mode is TradeMode.ACTIVE:
            values["holding_risk"] = self.holding_risk
        return values


def score_flip(
    *,
    buy: int,
    sell: int,
    margin: int,
    qty: int,
    depth: int,
    buy_volume_1h: float,
    sell_volume_1h: float,
    quote_age: float,
    ofi: float,
    drift: float,
    now: float,
    sigma_daily: Optional[float] = None,
    ou_fit: Optional["stats.OUFit"] = None,
    regime_score: float = 0.0,
    highalch: Optional[int] = None,
    nature_rune_cost: int = 100,
    competitors: Optional[float] = None,
    mode: TradeMode = DEFAULT_TRADE_MODE,
    horizon_hours: Optional[float] = None,
    calibration: Calibration = DEFAULT_CALIBRATION,
) -> ScoreBreakdown:
    """Expected gp per slot-hour for one flip, with its decomposition.

    `buy_volume_1h` is seller-initiated volume (what fills your buy offer);
    `sell_volume_1h` is buyer-initiated volume (what fills your sell offer).
    `competitors` is how many offers you are queued behind at the touch, from
    touch_competitors. The caller computes it because it has to be sized on the
    item's real traded volume: the deep check passes REACHABLE volume for the
    two legs, and deriving the crowd from that would let a low fill share make
    the queue look shorter, which is exactly backwards.
    """
    mid = (buy + sell) / 2.0
    share = aggressiveness(price_edge(depth, sell - buy), calibration,
                           competitors)
    buy_share = sell_share = share

    buy_rate = fill_rate(buy_volume_1h, buy_share)
    sell_rate = fill_rate(sell_volume_1h, sell_share)
    buy_seconds = expected_fill_seconds(qty, buy_rate, calibration)
    sell_seconds = expected_fill_seconds(qty, sell_rate, calibration)
    total_seconds = buy_seconds + sell_seconds

    mode = TradeMode(mode)
    effective_horizon = (float(horizon_hours) if horizon_hours is not None
                         else (DEFAULT_OVERNIGHT_HOURS
                               if mode is TradeMode.OVERNIGHT
                               else calibration.horizon_hours))
    if effective_horizon <= 0:
        raise ValueError("horizon_hours must be positive")
    horizon_seconds = effective_horizon * SECONDS_PER_HOUR
    p_buy = fill_probability(buy_seconds, horizon_seconds)
    p_both = round_trip_probability(buy_seconds, sell_seconds, horizon_seconds)
    p_stranded = stranded_inventory_probability(
        buy_seconds, sell_seconds, horizon_seconds)
    # Conditional display value: the probability that the sell finishes in
    # time after a buy has occurred.  The joint value above drives the model.
    p_sell = p_both / p_buy if p_buy > 0 else 0.0

    sigma = sigma_daily if sigma_daily is not None else (
        ou_fit.sigma if ou_fit is not None else calibration.default_sigma_daily)
    if sigma is None or sigma <= 0:
        sigma = calibration.default_sigma_daily

    adverse = adverse_selection_factor(ofi, drift, calibration)
    hold = holding_risk(sigma, sell_seconds, calibration)
    stale = staleness_factor(quote_age, sigma, calibration)
    reversion = mean_reversion_factor(ou_fit, mid, sell_seconds, regime_score,
                                      calibration)
    floor = alch_floor(highalch, nature_rune_cost)
    distance = alch_distance(buy, floor)
    alch = alch_bonus(distance, calibration)
    update = update_risk_factor(now, total_seconds, calibration)

    raw_profit = margin * qty
    if mode is TradeMode.ACTIVE:
        expected = (raw_profit * p_both * adverse * hold * stale * reversion
                    * alch * update)
        downside_risk = 0.0
    else:
        # An unattended buy that fills without its sell is inventory, not a
        # successful flip.  Price risk grows with sqrt(time); falling drift and
        # seller-heavy flow widen the stress move.  The alch floor caps that
        # move where it is genuinely close enough to matter.
        horizon_days = effective_horizon / HOURS_PER_DAY
        stress_move = 1.65 * sigma * math.sqrt(horizon_days)
        stress_move += max(0.0, -drift) * math.sqrt(effective_horizon)
        stress_move += max(0.0, -ofi) * 0.025
        stress_move = max(0.0, min(0.50, stress_move))
        floor_loss = None if floor is None else max(0.0, (buy - floor) / buy)
        if (floor_loss is not None
                and floor_loss < calibration.alch_relevant_distance):
            stress_move = min(stress_move, floor_loss)
        downside_risk = qty * buy * p_stranded * stress_move
        completed_value = (raw_profit * p_both * adverse * stale * reversion
                           * alch * update)
        expected = completed_value - downside_risk

    hours = total_seconds / SECONDS_PER_HOUR
    per_slot_hour = expected / hours if hours > 0 and hours != float("inf") else 0.0
    ranking_value = (per_slot_hour if mode is TradeMode.ACTIVE else expected)

    arbitrage = None
    if distance is not None and distance <= 0 and floor is not None:
        arbitrage = floor - buy

    return ScoreBreakdown(
        qty=qty, margin=margin, raw_profit=raw_profit, capital_needed=qty * buy,
        buy_share=buy_share, sell_share=sell_share,
        buy_rate=buy_rate, sell_rate=sell_rate,
        buy_seconds=buy_seconds, sell_seconds=sell_seconds,
        total_seconds=total_seconds, p_fill_buy=p_buy, p_fill_sell=p_sell,
        p_fill_both=p_both, p_stranded=p_stranded,
        expected_round_trip_qty=qty * p_both,
        adverse_selection=adverse, holding_risk=hold,
        staleness=stale, mean_reversion=reversion, alch=alch, update_risk=update,
        expected_profit=expected, gp_per_slot_hour=per_slot_hour,
        ranking_value=ranking_value, downside_risk_gp=downside_risk,
        mode=mode, horizon_hours=effective_horizon,
        alch_arbitrage_gp=arbitrage)


# ---------------------------------------------------------------------------
# Shrinkage across the whole scored universe
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ShrunkScores:
    values: List[float]              # gp/slot/hour after shrinkage
    edge_probability: List[float]    # P(true score beats the market average)
    prior_mean_gp: float
    tau_squared: float
    applied: bool = True

    @property
    def informative(self) -> bool:
        """False when no difference between these scores survives the noise."""
        return self.tau_squared > 0


def shrink_scores(
    raw: Sequence[float],
    observation_counts: Sequence[float],
    calibration: Calibration = DEFAULT_CALIBRATION,
) -> ShrunkScores:
    """Correct a ranking of thousands of noisy estimates.

    Ranking N noisy estimates and reading off the top does not find the best
    items; it finds the items whose estimation error happened to be largest and
    positive. With N in the thousands and each estimate resting on a handful of
    trades, that bias is not a nuisance term — it is most of what the top of
    the list is made of. The bias is worst exactly where the data is thinnest,
    so the correction has to be per-item, not a flat haircut.

    The correction is a normal-normal posterior on the log scale, so items
    spanning five orders of magnitude are comparable: each score is pulled
    toward the cross-sectional mean, and thin-volume scores are pulled much
    further because their evidence is thinner.

    `observation_counts` is the volume each estimate rests on. Noise falls as
    1/sqrt(count), so a staple quoted off 40,000 traded units keeps almost all
    of its estimate and a 12-unit curiosity keeps almost none.

    Alongside the shrunk value, each item gets the posterior probability that
    its true score beats the market-wide average. Ranking alone cannot say
    whether the item on top is genuinely better or merely luckier; that
    probability can, and it collapses toward 50% exactly where the evidence is
    too thin to tell.
    """
    positive_index = [i for i, value in enumerate(raw) if value > 0]
    if not positive_index:
        return ShrunkScores(list(raw), [0.0] * len(raw), 0.0, 0.0, False)

    logs = [math.log(raw[i]) for i in positive_index]
    variances = []
    for i in positive_index:
        count = max(1.0, float(observation_counts[i]))
        sampling = calibration.score_noise_scale / math.sqrt(count)
        floor = calibration.score_noise_floor
        variances.append(max(sampling * sampling + floor * floor, 1e-9))

    shrunk = stats.empirical_bayes(logs, variances)

    values = list(raw)
    edge = [0.0] * len(raw)
    for position, i in enumerate(positive_index):
        values[i] = math.exp(shrunk.values[position])
        edge[i] = shrunk.probability_above_mean(position)
    return ShrunkScores(values=values, edge_probability=edge,
                        prior_mean_gp=math.exp(shrunk.prior_mean),
                        tau_squared=shrunk.prior_variance, applied=True)


# ---------------------------------------------------------------------------
# Capital allocation
# ---------------------------------------------------------------------------

def capital_per_slot(capital: int, slots: int) -> int:
    """Equal split. Kept for the sidebar's headline number and as the fallback
    when nothing has been scored yet; allocate_capital is what the ranking uses."""
    return max(1, capital // max(1, slots))


def allocate_capital(scores: Sequence[float], capital: int, slots: int,
                     needs: Optional[Sequence[int]] = None) -> List[int]:
    """Split capital across the top flips in proportion to their scores.

    An equal split leaves capital stranded: a 10 gp item with a 10,000 buy
    limit can absorb 100k gp and no more, so a third of a 3m bank sitting on it
    is a third of the bank doing nothing, while the 50k gp item that could have
    used it is capped at a fraction of its limit.

    Allocation is proportional to score, then clipped to what each flip can
    actually absorb (`needs`), and anything freed by the clip is redistributed.
    Only positive scores are funded — an empty slot beats a negative-expectancy
    flip taken to look busy.
    """
    count = min(len(scores), max(1, slots))
    ranked = list(scores)[:count]
    total = sum(s for s in ranked if s > 0)
    if total <= 0:
        return [0] * len(ranked)

    allocation = [int(capital * (s / total)) if s > 0 else 0 for s in ranked]
    if needs is None:
        return allocation

    caps = list(needs)[:count]
    for _ in range(3):        # a couple of passes converge; this is not an LP
        spare = 0
        for i, amount in enumerate(allocation):
            cap = caps[i] if i < len(caps) else None
            if cap is not None and amount > cap:
                spare += amount - cap
                allocation[i] = cap
        if spare <= 0:
            break
        hungry = [i for i, amount in enumerate(allocation)
                  if ranked[i] > 0 and (i >= len(caps) or caps[i] > amount)]
        if not hungry:
            break
        weight = sum(ranked[i] for i in hungry)
        if weight <= 0:
            break
        for i in hungry:
            allocation[i] += int(spare * (ranked[i] / weight))
    return allocation


def allocate_portfolio(scores: Sequence[float], capital: int,
                       unit_costs: Sequence[int], needs: Sequence[int],
                       slots: int) -> List[int]:
    """Build an executable, integer-unit portfolio for at most ``slots`` rows.

    Each funded slot first receives one affordable unit.  Remaining capital is
    distributed by decision value, clipped at the quantity/buy-limit cap and
    rounded down to whole items.  This prevents a score-weighted split from
    producing a visually occupied slot whose allocation cannot buy one item.
    Non-positive candidates are deliberately left open.
    """
    count = min(len(scores), len(unit_costs), len(needs), max(0, slots))
    allocation = [0] * count
    eligible = [i for i in range(count)
                if scores[i] > 0 and unit_costs[i] > 0
                and needs[i] >= unit_costs[i]]
    # Candidate order is ranking order.  If the bank cannot seed every slot,
    # fund the best rows first instead of creating impossible fractional buys.
    seeded = []
    remaining = max(0, int(capital))
    for i in eligible:
        cost = int(unit_costs[i])
        if remaining < cost:
            continue
        allocation[i] = cost
        remaining -= cost
        seeded.append(i)
    if not seeded or remaining <= 0:
        return allocation

    # Water-fill by score. Rounding may leave a sub-unit residue; leaving a few
    # gp liquid is more honest than reporting a quantity the GE cannot accept.
    for _ in range(count + 3):
        hungry = [i for i in seeded if allocation[i] + unit_costs[i] <= needs[i]]
        if not hungry or remaining < min(unit_costs[i] for i in hungry):
            break
        weight = sum(scores[i] for i in hungry)
        progressed = False
        for i in hungry:
            target = int(remaining * scores[i] / weight)
            room = needs[i] - allocation[i]
            grant = min(room, target)
            grant -= grant % unit_costs[i]
            if grant <= 0 and remaining >= unit_costs[i]:
                grant = unit_costs[i]
            grant = min(grant, remaining)
            grant -= grant % unit_costs[i]
            if grant > 0:
                allocation[i] += grant
                remaining -= grant
                progressed = True
        if not progressed:
            break
    return allocation


# ---------------------------------------------------------------------------
# Multi-day history
# ---------------------------------------------------------------------------
# Intraday data cannot tell a real spread from a transient dump: a few hundred
# salmon sold at 30 gp in the last minutes looks like a buy at 30, but if the
# last two weeks of seller volume went at 40, a large offer at 30 fills only
# against that one dumper and then sits. These functions read ~14 days of 6h
# timeseries buckets and answer: at your prices, what share of the market's
# real volume would actually have filled you, how does this item behave, and
# is it in the middle of a regime change?


@dataclass(frozen=True)
class HistoryView:
    """Multi-day metrics for one item at one (buy, sell) estimate."""
    buckets: int
    baseline_low: Optional[int]
    baseline_high: Optional[int]
    buy_fill_share: float
    sell_fill_share: float
    fill_share: float
    trend: float
    dislocation: float
    median_mid: Optional[int]
    elevation: float
    volatility: float
    ou: Optional["stats.OUFit"] = None
    regime_score: float = 0.0
    mean_volume: float = 0.0

    @property
    def mean_reverting(self) -> bool:
        return self.ou is not None and self.ou.mean_reverting

    @property
    def half_life_hours(self) -> Optional[float]:
        if self.ou is None:
            return None
        half_life = self.ou.half_life_days
        return half_life * HOURS_PER_DAY if half_life is not None else None

    @property
    def regime_changed(self) -> bool:
        return self.regime_score >= DEFAULT_CALIBRATION.regime_shift_threshold


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


def history_view(points: List[dict], buy: int, sell: int,
                 window: int = HISTORY_WINDOW_BUCKETS) -> Optional[HistoryView]:
    """Read a slice of /timeseries buckets (wiki key names, oldest first).

    Returns None when fewer than MIN_HISTORY_BUCKETS buckets traded — too
    little history to say anything, so the caller keeps its stage-1 numbers.
    """
    points = [p for p in points[-window:] if isinstance(p, dict)]
    lows, highs = [], []
    buckets = 0
    volumes = []
    for p in points:
        hv = p.get("highPriceVolume") or 0
        lv = p.get("lowPriceVolume") or 0
        if hv > 0 or lv > 0:
            buckets += 1
            volumes.append(hv + lv)
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

    recent = _bucket_vwap(points[-RECENT_TREND_BUCKETS:])
    prior = _bucket_vwap(points[:-RECENT_TREND_BUCKETS])
    trend = ((recent - prior) / prior
             if recent is not None and prior is not None and prior > 0 else 0.0)

    dislocation = ((buy - baseline_low) / baseline_low
                   if baseline_low is not None and baseline_low > 0 else 0.0)

    median_mid = stats.median(mids)
    elevation = ((mid_now - median_mid) / median_mid
                 if median_mid else 0.0)
    volatility = 0.0
    if median_mid:
        deviation = stats.median_absolute_deviation(mids)
        volatility = (deviation / median_mid) if deviation is not None else 0.0

    ou = stats.fit_ou(mids, HISTORY_BUCKET_DAYS)
    regime = stats.regime_shift(mids)

    return HistoryView(
        buckets=buckets,
        baseline_low=int(round(baseline_low)) if baseline_low is not None else None,
        baseline_high=int(round(baseline_high)) if baseline_high is not None else None,
        buy_fill_share=buy_fill_share, sell_fill_share=sell_fill_share,
        fill_share=min(buy_fill_share, sell_fill_share), trend=trend,
        dislocation=dislocation,
        median_mid=int(round(median_mid)) if median_mid else None,
        elevation=elevation, volatility=volatility, ou=ou, regime_score=regime,
        mean_volume=(sum(volumes) / len(volumes)) if volumes else 0.0)


def gp_per_slot_hour(expected_gp: float, total_seconds: float) -> float:
    """Expected gp per offer slot per hour — the metric worth maximising.

    Offer slots, not gp, are the binding constraint: three in free-to-play,
    eight for members. The old version divided by a flat four hours, which
    assumed every flip occupies a slot for exactly the buy-limit window. It
    does not: a flip that clears in twelve minutes for 5k gp earns 25k per
    slot-hour, while one that ties the slot up all four hours for 40k earns
    10k. The first is the better use of the slot and the old metric ranked it
    eighth as well.
    """
    if total_seconds <= 0 or total_seconds == float("inf"):
        return 0.0
    return expected_gp / (total_seconds / SECONDS_PER_HOUR)
