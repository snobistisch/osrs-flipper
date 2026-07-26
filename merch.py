"""Long-horizon signals: trend, crash, and supply crunch.

`engine.py` answers one question — is this worth flipping in the next four
hours. Everything in it is built around that horizon: fill times in seconds,
mean reversion over a 14-day window, a slot freed sooner being worth more than
a slot held longer.

This module answers a different question: is this worth *buying and holding*
for weeks. The two do not share a scale and should never be added together. An
item can be a terrible flip (nobody trades it, the spread is one gp) and an
excellent hold (its price has doubled in a year), and the flip ranking is right
to bury it while the merch ranking is right to surface it.

Three signals live here:

- **Trend** — a regression through a year of daily prices. Rising, falling, or
  neither, with a measure of how much of the movement is trend rather than
  noise.
- **Crash** — a price far under its own recent median. The depth already comes
  from `engine.history_view`; what this adds is the volume context that tells a
  dump apart from a drift, and the discipline to shut up when the price level
  shifted because the game changed.
- **Supply crunch** — a collapse in traded volume on an item that is still
  wanted. Raid uniques stop entering the game when players move to the newest
  raid, and the price follows the supply months later.

Stdlib only, like `engine` and `stats`: the agent layer has to run from cron
without a virtualenv.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import engine
import stats

# ---------------------------------------------------------------------------
# window
# ---------------------------------------------------------------------------

# /timeseries serves at most 365 points per call, so a 24h step is exactly one
# year and there is no paging to do.
TREND_TIMESTEP = "24h"
TREND_WINDOW_POINTS = 365

# Below this many *traded* days a regression is fitting noise. Two months is
# not a year, but it is enough to see a direction, and demanding the full year
# would silently exclude every item released since.
TREND_MIN_POINTS = 30

# Annualising a daily log slope compounds it 365 times, so a steep run turns
# into a number like +40,000%/yr that is arithmetically correct and completely
# useless. Report is capped here; scoring is capped separately and lower.
ANNUALISED_REPORT_CAP = 999.0
ANNUALISED_SCORE_CAP = 200.0

# Volume comparison for supply crunch: mean daily volume over the most recent
# month against the same length of month, six months earlier. Comparing single
# days would measure which day of the week each end landed on.
VOLUME_RECENT_DAYS = 30
VOLUME_LOOKBACK_DAYS = 180

# "Normal volume" is measured over the trailing month, not the whole year. See
# volume_baseline for why a year-long baseline breaks on a drifting market.
VOLUME_BASELINE_DAYS = 30

# The final 24h bucket does not measure the same thing as the ones before it,
# so every volume calculation here drops it.
#
# Verified against the API on 2026-07-26, cross-checking /timeseries at 24h
# against the same item at 6h: for every historical day the 24h bucket's
# volume equals the FIRST 6h bucket of that day exactly — not the day's total,
# which is roughly four times larger. The most recent 24h bucket is the
# exception and does carry the full day. Prices behave the same way (the 24h
# price is the first 6h bucket's price, within about 2% of the daily mean),
# which is harmless for a trend because it is a consistent daily sample.
#
# Left in, this makes today look like an 8x volume spike on every item in the
# game simultaneously, which is exactly what the first run of the crash scanner
# reported. Dropping one bucket costs a day of latency on the volume signals
# and is the only way to compare like with like.
VOLUME_SKIP_LAST = 1

# A supply crunch is item-specific, so it has to be measured against the rest
# of the market rather than in absolute terms. Below this many items in the
# basket the median is not a market estimate, and the module refuses to badge
# anything rather than guess.
MIN_BASKET_FOR_DRIFT = 8

DAYS_PER_YEAR = 365.0


# ---------------------------------------------------------------------------
# trend
# ---------------------------------------------------------------------------

UPTREND = "UPTREND"
DOWNTREND = "DOWNTREND"
SIDEWAYS = "SIDEWAYS"


@dataclass(frozen=True)
class Trend:
    """A least-squares fit through the log of one item's daily price.

    Log prices, not raw. Two reasons: the slope is then a growth *rate* that
    means the same thing on a 5 gp herb and a 60m wand, and R-squared becomes
    comparable across items instead of being dominated by absolute scale.
    """
    slope_per_day: float      # in log gp; 0.001 is about +0.1%/day
    intercept: float
    r_squared: float
    t_stat: float
    annualised_pct: float     # compounded, capped at ANNUALISED_REPORT_CAP
    deviation: float          # today's price vs the fitted line, as a fraction
    consistency: float        # share of days that closed up
    n: int
    direction: str
    first_price: Optional[int] = None
    last_price: Optional[int] = None

    @property
    def noise_probability(self) -> float:
        """How often a trendless item would look at least this trendy."""
        return noise_probability(self.t_stat)

    @property
    def verdict(self) -> str:
        """One line a person can act on, instead of three statistics."""
        if self.direction == SIDEWAYS:
            return ("{:+.0f}%/yr, but {:.0%} of trendless items would look "
                    "this trendy — not evidence of a trend".format(
                        self.annualised_pct, self.noise_probability))
        return "{} {:+.0f}%/yr, only {:.0%} of trendless items reach this".format(
            self.direction.lower(), self.annualised_pct, self.noise_probability)


def _point_mid(point: dict) -> Optional[float]:
    """Volume-weighted mid of one bucket, or the side that traded."""
    if not isinstance(point, dict):
        return None
    high, low = point.get("avgHighPrice"), point.get("avgLowPrice")
    hv = point.get("highPriceVolume") or 0
    lv = point.get("lowPriceVolume") or 0
    value = ((high or 0) * hv) + ((low or 0) * lv)
    vol = (hv if high is not None else 0) + (lv if low is not None else 0)
    if vol > 0:
        return value / vol
    if high is not None and low is not None:
        return (high + low) / 2.0
    return high if high is not None else low


def compute_trend(
        points: Sequence[dict],
        calibration: engine.Calibration = engine.DEFAULT_CALIBRATION,
        window: int = TREND_WINDOW_POINTS) -> Optional[Trend]:
    """Fit a trend through /timeseries 24h buckets (wiki keys, oldest first).

    Returns None when too few days actually traded.

    The regressor is elapsed days taken from each bucket's own timestamp, not
    the index of the point. Days on which nothing traded are dropped, and using
    the index would then quietly compress those gaps and steepen the slope.
    """
    usable = []
    for p in points[-window:]:
        mid = _point_mid(p)
        ts = p.get("timestamp") if isinstance(p, dict) else None
        if mid is None or mid <= 0 or ts is None:
            continue
        usable.append((float(ts), float(mid)))
    if len(usable) < TREND_MIN_POINTS:
        return None

    usable.sort(key=lambda pair: pair[0])
    t0 = usable[0][0]
    xs = [(ts - t0) / 86400.0 for ts, _ in usable]
    ys = [math.log(mid) for _, mid in usable]

    fit = stats.ols(xs, ys)
    if fit is None:
        return None

    residuals = [y - (fit.intercept + fit.slope * x) for x, y in zip(xs, ys)]
    mean_y = sum(ys) / len(ys)
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum(r * r for r in residuals)
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    t_stat = _autocorrelation_robust_t(fit, residuals)

    annualised = (math.exp(fit.slope * DAYS_PER_YEAR) - 1.0) * 100.0
    annualised = max(-100.0, min(ANNUALISED_REPORT_CAP, annualised))

    fitted_last = fit.intercept + fit.slope * xs[-1]
    deviation = math.exp(ys[-1] - fitted_last) - 1.0

    ups = sum(1 for i in range(1, len(ys)) if ys[i] > ys[i - 1])
    consistency = ups / (len(ys) - 1) if len(ys) > 1 else 0.0

    direction = _direction(t_stat, annualised, calibration)

    return Trend(
        slope_per_day=fit.slope, intercept=fit.intercept, r_squared=r_squared,
        t_stat=t_stat, annualised_pct=annualised, deviation=deviation,
        consistency=consistency, n=len(usable),
        first_price=int(round(usable[0][1])),
        last_price=int(round(usable[-1][1])),
        direction=direction)


# Survival curve of |t| for price series with NO trend in them at all, measured
# over 3,000 simulated driftless random walks of 365 days each (see
# test_merch.py, which regenerates and checks it). It is scale-free: repeating
# the simulation at 1.2%, 2.1% and 3.5% daily volatility gives the same curve to
# within a percentage point, because both the slope and its standard error
# scale with volatility.
#
# This exists to turn an unreadable statistic into a sentence. "t = 2.6" means
# nothing to anyone; "41% of items with no trend would look at least this
# trendy" is the actual content, and it is what stops a +57%/yr headline number
# from being mistaken for a finding.
NOISE_SURVIVAL = (
    (0.0, 1.00), (1.0, 0.73), (1.5, 0.61), (2.0, 0.51), (2.5, 0.42),
    (3.0, 0.35), (4.0, 0.24), (5.0, 0.16), (6.0, 0.12), (8.0, 0.06),
    (10.0, 0.03), (12.0, 0.01), (15.0, 0.006), (20.0, 0.001),
)


def noise_probability(t_stat: float) -> float:
    """Share of trendless items that would show a |t| at least this large.

    Linear interpolation on the measured curve. Not a p-value: the null here is
    a random walk rather than independent draws, which is the whole reason the
    textbook p-value is unusable on price data.
    """
    magnitude = abs(t_stat)
    previous_t, previous_p = NOISE_SURVIVAL[0]
    for threshold, share in NOISE_SURVIVAL:
        if magnitude <= threshold:
            if threshold == previous_t:
                return share
            weight = (magnitude - previous_t) / (threshold - previous_t)
            return previous_p + weight * (share - previous_p)
        previous_t, previous_p = threshold, share
    return NOISE_SURVIVAL[-1][1]


def _autocorrelation_robust_t(fit: "stats.OLSFit",
                              residuals: Sequence[float]) -> float:
    """The slope's t-statistic, corrected for autocorrelated residuals.

    Textbook OLS standard errors assume the residuals are independent. Prices
    are not: today's deviation from the trend line is nearly the same as
    yesterday's, because prices move in steps rather than being redrawn each
    day. Left uncorrected, a pure random walk with no drift at all comes out at
    |t| of thirty or more, and every item in the game gets labelled trending.

    The fix is the standard AR(1) inflation of the variance by (1+rho)/(1-rho),
    with rho the lag-1 autocorrelation of the residuals. That is the cheap
    version of a Newey-West correction, and this is a direction label rather
    than a wager, so the cheap version is the right amount of machinery.

    Only positive rho inflates. Negative autocorrelation would *shrink* the
    standard error, which is a claim of extra precision this is not confident
    enough to make.
    """
    n = len(residuals)
    if fit.slope_stderr <= 0 or n < 3:
        return fit.t_stat

    denominator = sum(r * r for r in residuals)
    if denominator <= 0:
        return fit.t_stat
    numerator = sum(residuals[i] * residuals[i - 1] for i in range(1, n))
    rho = numerator / denominator
    rho = max(0.0, min(0.99, rho))

    inflation = math.sqrt((1.0 + rho) / (1.0 - rho))
    return fit.slope / (fit.slope_stderr * inflation)


def _direction(t_stat: float, annualised_pct: float,
               calibration: engine.Calibration) -> str:
    """A direction needs both statistical and economic significance.

    The t-statistic alone would label a dead-flat item as trending once it has
    enough points, because with 365 observations even a 2%/yr drift clears any
    reasonable t. The size threshold is what keeps the label meaning something.
    """
    if (t_stat >= calibration.merch_trend_t
            and annualised_pct >= calibration.merch_min_annual_pct):
        return UPTREND
    if (t_stat <= -calibration.merch_trend_t
            and annualised_pct <= -calibration.merch_min_annual_pct):
        return DOWNTREND
    return SIDEWAYS


# ---------------------------------------------------------------------------
# merch score
# ---------------------------------------------------------------------------

def merch_score(trend: Optional[Trend], buy_limit: Optional[int] = None,
                botted: bool = False,
                calibration: engine.Calibration = engine.DEFAULT_CALIBRATION
                ) -> float:
    """How attractive this item is to buy and hold. Zero unless it is rising.

    The base is the annual rate discounted by how much of the price movement
    the trend actually explains: 30%/yr with R-squared 0.8 is a better hold
    than 60%/yr with R-squared 0.15, because the second one is mostly a price
    that wandered and happened to end up higher.
    """
    if trend is None or trend.direction != UPTREND:
        return 0.0
    if trend.r_squared < calibration.merch_min_r2:
        return 0.0

    base = min(trend.annualised_pct, ANNUALISED_SCORE_CAP) * trend.r_squared

    # Buying below the line is the whole edge in a trend that is already known.
    entry_bonus = 0.0
    if trend.deviation < calibration.merch_entry_threshold:
        entry_bonus = min(0.5, -trend.deviation * 3.0)

    # A high buy limit means the position can actually be built. A 5-per-4h
    # limit on a 6m scroll caps you at a handful of units a day whatever the
    # trend says.
    limit_bonus = 0.0
    if buy_limit and buy_limit > 1:
        limit_bonus = min(0.3, math.log10(buy_limit) / 20.0)

    penalty = calibration.merch_botted_penalty if botted else 0.0

    return base * max(0.0, 1.0 + entry_bonus + limit_bonus - penalty)


@dataclass(frozen=True)
class EntrySignal:
    kind: str
    message: str
    strength: float


def entry_signal(price: float, trend: Optional[Trend],
                 median_mid: Optional[float] = None,
                 calibration: engine.Calibration = engine.DEFAULT_CALIBRATION
                 ) -> Optional[EntrySignal]:
    """When to start buying an item you have already decided you want.

    Only fires on items in an uptrend: "it is cheap against its own trend" is
    not a reason to buy something whose trend is down.
    """
    if trend is None or trend.direction != UPTREND:
        return None
    if trend.deviation < calibration.merch_entry_threshold:
        return EntrySignal(
            kind="PULLBACK",
            message="{}% below its own trend line".format(
                int(round(-trend.deviation * 100))),
            strength=abs(trend.deviation))
    if median_mid and price < median_mid * 0.95:
        return EntrySignal(
            kind="BELOW_MEDIAN",
            message="{}% below the 14-day median".format(
                int(round((1 - price / median_mid) * 100))),
            strength=(median_mid - price) / median_mid)
    return None


# ---------------------------------------------------------------------------
# crash detection
# ---------------------------------------------------------------------------

def _comparable_volume_points(points: Sequence[dict]) -> List[dict]:
    """The 24h buckets whose volume fields mean the same thing as each other.

    That is all of them except the last — see VOLUME_SKIP_LAST.
    """
    usable = [p for p in points if isinstance(p, dict)]
    return usable[:-VOLUME_SKIP_LAST] if len(usable) > VOLUME_SKIP_LAST else []


def latest_comparable_volume(points: Sequence[dict]) -> Optional[float]:
    """Most recent day's volume, on the same footing as the baseline."""
    usable = _comparable_volume_points(points)
    if not usable:
        return None
    last = usable[-1]
    return float((last.get("highPriceVolume") or 0)
                 + (last.get("lowPriceVolume") or 0))


def volume_baseline(points: Sequence[dict],
                    calibration: engine.Calibration = engine.DEFAULT_CALIBRATION,
                    days: int = VOLUME_BASELINE_DAYS) -> Optional[float]:
    """Normal daily volume for this item lately, as a high percentile.

    A percentile rather than a mean, because the mean of a series containing
    one 15x day is dragged up by that day — and that day is exactly the event
    the ratio exists to detect. P70 sits above ordinary variation and below the
    spikes.

    Only the trailing month, not the whole year. Total trade volume in the game
    drifts a long way over twelve months, and a baseline taken across all of it
    answers "normal at some point last year", which is not the question. On a
    market whose volume has halved, a year-long baseline reports every item as
    trading suspiciously thin, and the ratio stops meaning anything.
    """
    volumes = []
    for p in _comparable_volume_points(points)[-days:]:
        hv = p.get("highPriceVolume") or 0
        lv = p.get("lowPriceVolume") or 0
        if hv > 0 or lv > 0:
            volumes.append(hv + lv)
    if not volumes:
        return None
    volumes.sort()
    index = int(len(volumes) * calibration.volume_baseline_percentile)
    return float(volumes[min(index, len(volumes) - 1)])


def volume_ratio(current: Optional[float], baseline: Optional[float]) -> float:
    """Today's volume as a multiple of normal. 1.0 when it cannot be measured."""
    if not baseline or baseline <= 0 or current is None:
        return 1.0
    return current / baseline


def volume_change(points: Sequence[dict],
                  recent_days: int = VOLUME_RECENT_DAYS,
                  lookback_days: int = VOLUME_LOOKBACK_DAYS) -> Optional[float]:
    """Fractional change in mean daily volume against `lookback_days` ago.

    -0.85 means the item trades at 15% of the volume it did six months back.
    Needs both windows populated; returns None rather than guessing when the
    history does not reach that far.
    """
    daily = [(p.get("highPriceVolume") or 0) + (p.get("lowPriceVolume") or 0)
             for p in _comparable_volume_points(points)]
    if len(daily) < lookback_days + recent_days // 2:
        return None

    recent = daily[-recent_days:]
    start = max(0, len(daily) - lookback_days - recent_days // 2)
    past = daily[start:start + recent_days]
    if not recent or not past:
        return None
    past_mean = sum(past) / len(past)
    if past_mean <= 0:
        return None
    return (sum(recent) / len(recent) - past_mean) / past_mean


CRASH = "CRASH"
DIP = "DIP"
DIPPED_STABLE = "DIPPED_STABLE"
PUMPED = "PUMPED"

BADGE_LABELS = {
    CRASH: "CRASH",
    DIP: "DIP",
    DIPPED_STABLE: "DIPPED STABLE",
    PUMPED: "PUMPED",
}


@dataclass(frozen=True)
class CrashSignal:
    kind: str
    score: float
    depth: float
    volume_ratio: float

    @property
    def label(self) -> str:
        return BADGE_LABELS[self.kind]


def crash_signal(depth: Optional[float], vol_ratio: float,
                 regime_score: float = 0.0,
                 calibration: engine.Calibration = engine.DEFAULT_CALIBRATION
                 ) -> Optional[CrashSignal]:
    """Classify a price standing away from its own 14-day median.

    `depth` is `HistoryView.elevation` — negative means below the median. That
    number is already computed during the deep check, so this adds only the
    volume context and the classification.

    Nothing fires through a regime shift. A price level that moved because the
    game changed is not a price that fell: there is no median left to revert
    to, and calling it a crash is how you buy an item Jagex just made
    obtainable in bulk.

    The order of the tests matters and is deliberate. Deep-and-loud is a crash;
    deep-and-quiet is a different animal and a better one — a price that slid
    without a volume event has no forced seller to wait out.
    """
    if depth is None:
        return None
    if regime_score >= calibration.regime_shift_threshold:
        return None

    if (depth <= calibration.crash_depth
            and vol_ratio >= calibration.crash_volume_spike):
        return CrashSignal(CRASH, 5.0, depth, vol_ratio)
    if (depth <= calibration.quiet_dip_depth
            and vol_ratio <= calibration.quiet_volume_ratio):
        return CrashSignal(DIPPED_STABLE, 4.0, depth, vol_ratio)
    if (depth <= calibration.dip_depth
            and vol_ratio >= calibration.dip_volume_spike):
        return CrashSignal(DIP, 3.0, depth, vol_ratio)
    if (depth >= calibration.pumped_elevation
            and vol_ratio <= calibration.pumped_volume_ratio):
        return CrashSignal(PUMPED, -3.0, depth, vol_ratio)
    return None


def recovery_score(signal: Optional[CrashSignal], fill_share: float = 0.0,
                   mean_reverting: bool = False) -> float:
    """Rank crashed items by how tradable the recovery is, not by how far it fell.

    A 70% collapse you cannot buy into is worth less than a 25% dip on an item
    that trades all day. Mean reversion is the evidence that the price comes
    back at all; without it a cheap item is just cheap.
    """
    if signal is None or signal.score <= 0:
        return 0.0
    depth_term = abs(signal.depth) * 100.0
    liquidity = max(0.05, fill_share)
    reversion = 1.5 if mean_reverting else 1.0
    return depth_term * liquidity * reversion * (signal.score / 5.0)


# ---------------------------------------------------------------------------
# one item, one year, one fetch
# ---------------------------------------------------------------------------

# The median the crash depth is measured against. Two weeks is short enough to
# still be "recent" and long enough that a single bad day does not move it.
MEDIAN_WINDOW_DAYS = 14


@dataclass(frozen=True)
class DailyView:
    """Everything derivable from one year of 24h buckets for one item.

    This deliberately duplicates a *measurement* that `engine.history_view`
    also makes — the median a price is standing away from — and gets a slightly
    different number, because it reads 14 daily buckets where the flip path
    reads 56 six-hourly ones. That is not drift to be fixed. The flip path
    needs six-hour resolution to model fill times; the merch path needs a year
    of context and must not cost a second per-item request to get it. Two
    horizons, two fetches would be worse than two slightly different medians.
    """
    days: int
    trend: Optional[Trend]
    price: Optional[int]
    median_14d: Optional[int]
    depth: Optional[float]
    volume_today: Optional[float]
    volume_baseline: Optional[float]
    volume_ratio: float
    volume_change_6m: Optional[float]          # raw, before the market is out
    crash: Optional[CrashSignal]
    # Filled by apply_market_context once a basket is available. Until then the
    # supply verdict is unknowable, so it stays None rather than defaulting to
    # something reassuring.
    volume_change_relative: Optional[float] = None
    market_drift: Optional[float] = None
    supply: Optional[str] = None

    @property
    def has_signal(self) -> bool:
        return self.crash is not None or self.supply is not None


def daily_view(points: Sequence[dict], price: Optional[float] = None,
               calibration: engine.Calibration = engine.DEFAULT_CALIBRATION
               ) -> DailyView:
    """Read a year of 24h buckets into every long-horizon signal at once.

    `price` overrides the last traded bucket, so a caller holding a fresh
    /latest quote measures the crash depth against the price you can actually
    trade at rather than against yesterday's average.
    """
    traded = [p for p in points if isinstance(p, dict)
              and (_point_mid(p) or 0) > 0]
    mids = [_point_mid(p) for p in traded]

    trend = compute_trend(points, calibration=calibration)
    median_14d = stats.median(mids[-MEDIAN_WINDOW_DAYS:]) if mids else None
    current = price if price is not None else (mids[-1] if mids else None)

    depth = None
    if current is not None and median_14d and median_14d > 0:
        depth = (current - median_14d) / median_14d

    volume_today = latest_comparable_volume(points)
    baseline = volume_baseline(points, calibration=calibration)
    ratio = volume_ratio(volume_today, baseline)
    change_6m = volume_change(points)

    return DailyView(
        days=len(traded), trend=trend,
        price=int(round(current)) if current is not None else None,
        median_14d=int(round(median_14d)) if median_14d else None,
        depth=depth, volume_today=volume_today, volume_baseline=baseline,
        volume_ratio=ratio, volume_change_6m=change_6m,
        crash=crash_signal(depth, ratio, calibration=calibration))


def apply_market_context(
        views: Dict[int, DailyView],
        calibration: engine.Calibration = engine.DEFAULT_CALIBRATION
        ) -> Dict[int, DailyView]:
    """Second pass: divide out the market-wide volume move, then badge supply.

    Has to be a second pass, because the market estimate is the median across
    every item analysed and no single item can see it.
    """
    drift = market_volume_drift(
        [view.volume_change_6m for view in views.values()])
    updated = {}
    for item_id, view in views.items():
        relative = relative_volume_change(view.volume_change_6m, drift)
        updated[item_id] = dataclasses.replace(
            view, volume_change_relative=relative, market_drift=drift,
            supply=supply_crunch_badge(relative, calibration=calibration))
    return updated


@dataclass(frozen=True)
class FlipCrash:
    """Crash context for a flip row, from data the deep check already paid for."""
    signal: Optional[CrashSignal]
    volume_ratio: Optional[float]
    recovery: float

    @property
    def badge(self) -> Optional[str]:
        return self.signal.kind if self.signal is not None else None


NO_CRASH = FlipCrash(signal=None, volume_ratio=None, recovery=0.0)


def crash_context(row, bucket_hours: float = engine.HISTORY_BUCKET_HOURS,
                  calibration: engine.Calibration = engine.DEFAULT_CALIBRATION
                  ) -> FlipCrash:
    """Classify a deep-checked flip row without fetching anything new.

    Duck-typed on `filters.FlipRow` rather than importing it, so this stays
    usable from the CLI, the dashboard and the agent without any of them
    dragging in the pipeline.

    The baseline is the 14-day average bucket converted to an hourly rate, so
    both sides of the ratio are units per hour: `volume_1h_total` counts both
    sides of the book this hour, which `thin_volume_1h` deliberately does not.
    """
    if not getattr(row, "deep_checked", False):
        return NO_CRASH
    elevation = getattr(row, "elevation", None)
    mean_volume = getattr(row, "history_mean_volume", None)
    if elevation is None or not mean_volume:
        return NO_CRASH

    ratio = volume_ratio(getattr(row, "volume_1h_total", 0),
                         mean_volume / bucket_hours)
    signal = crash_signal(elevation, ratio,
                          getattr(row, "regime_score", 0.0) or 0.0,
                          calibration=calibration)
    return FlipCrash(
        signal=signal, volume_ratio=ratio,
        recovery=recovery_score(signal, getattr(row, "fill_share", 0.0) or 0.0,
                                bool(getattr(row, "mean_reverting", False))))


# ---------------------------------------------------------------------------
# raid cycle
# ---------------------------------------------------------------------------

# Raid uniques whose supply depends on how many people still run that raid.
# Verified against /mapping: every id here is tradeable and has a buy limit.
# The Leagues "Corrupted" variants are deliberately absent — they carry no buy
# limit and never appear in /latest, because they cannot be traded at all.
RAID_UNIQUE_IDS = frozenset({
    20997,  # Twisted bow
    21006,  # Kodai wand
    21012,  # Dragon hunter crossbow
    21018,  # Ancestral hat
    21021,  # Ancestral robe top
    21024,  # Ancestral robe bottom
    21034,  # Dexterous prayer scroll
    21047,  # Torn prayer scroll
    21079,  # Arcane prayer scroll
    13652,  # Dragon claws
    22324,  # Ghrazi rapier
    22477,  # Avernic defender hilt
    22486,  # Scythe of vitur (uncharged)
    22978,  # Dragon hunter lance
    26219,  # Osmumten's fang
    27277,  # Tumeken's shadow (uncharged)
})

# The subset nobody at the content they gate can do without. These hold their
# demand when the supply dries up; a cosmetic-tier unique does not.
PVM_MUST_HAVE_IDS = frozenset({
    20997,  # Twisted bow
    21034,  # Dexterous prayer scroll (Rigour)
    21079,  # Arcane prayer scroll (Augury)
    22486,  # Scythe of vitur
    27277,  # Tumeken's shadow
})

SUPPLY_CRUNCH = "SUPPLY_CRUNCH"
SUPPLY_DROP = "SUPPLY_DROP"


def market_volume_drift(changes: Sequence[Optional[float]]) -> Optional[float]:
    """How much the whole market's volume moved, as the median of a basket.

    Trade volume across the game is not constant. Measured over a year on live
    data, every item on the watchlist — blood runes, diamonds, raid uniques
    alike — showed volume down between 50% and 86%. Read absolutely, that says
    the entire game is in a supply crunch, which is another way of saying the
    measurement was not about supply at all.

    The median of a basket is the market. What is left after dividing it out is
    the part that belongs to the item.
    """
    usable = [change for change in changes if change is not None]
    if len(usable) < MIN_BASKET_FOR_DRIFT:
        return None
    return stats.median(usable)


def relative_volume_change(raw: Optional[float],
                           drift: Optional[float]) -> Optional[float]:
    """One item's volume change with the market-wide move divided out.

    Returns None when the market move is unknown. That is deliberate: from one
    item alone you cannot tell a supply crunch from a quiet game, and inventing
    a number here is how every item ends up wearing a badge.
    """
    if raw is None or drift is None or drift <= -1.0:
        return None
    return (1.0 + raw) / (1.0 + drift) - 1.0


def supply_crunch_badge(relative_change: Optional[float],
                        calibration: engine.Calibration = engine.DEFAULT_CALIBRATION
                        ) -> Optional[str]:
    """Label a collapse in traded volume, relative to the rest of the market.

    Takes the number from `relative_volume_change`, not the raw one.
    """
    if relative_change is None:
        return None
    if relative_change <= calibration.supply_crunch_decline:
        return SUPPLY_CRUNCH
    if relative_change <= calibration.supply_drop_decline:
        return SUPPLY_DROP
    return None


def raid_cycle_score(item_id: int, price: float,
                     relative_volume_change_6m: Optional[float],
                     trend: Optional[Trend] = None,
                     calibration: engine.Calibration = engine.DEFAULT_CALIBRATION
                     ) -> float:
    """Score a raid unique whose supply is drying up.

    This is a slow thesis and it is stated as one: players stop running the old
    raid, the drops stop entering the game, and the price of what is left grinds
    up over months. It is not a flip and the number is not gp per hour — it is a
    ranking within the raid uniques only.
    """
    if item_id not in RAID_UNIQUE_IDS:
        return 0.0
    if (relative_volume_change_6m is None
            or relative_volume_change_6m > calibration.supply_drop_decline):
        return 0.0

    # A cheaper item has more buyers who can reach it. The catch-up story on a
    # 60m weapon needs a far smaller pool of players to fund it.
    if price < calibration.raid_catch_up_gp:
        catch_up = 1.5
    elif price < calibration.raid_catch_up_gp * 5:
        catch_up = 1.0
    else:
        catch_up = 0.5

    essential = 1.3 if item_id in PVM_MUST_HAVE_IDS else 1.0
    base = abs(relative_volume_change_6m) * 100.0 * catch_up * essential
    if trend is not None and trend.annualised_pct > 0:
        base += trend.annualised_pct / 10.0
    return base


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

BOTTED = "BOTTED"
MERCH = "MERCH"
RAID = "RAID"

# A free-to-play item cheap enough that no human farms it for the gp, with a
# buy limit high enough that the supply is industrial. Neither condition means
# much alone: cheap f2p items exist that nobody bots, and high limits exist on
# items no bot can produce.
BOTTED_MAX_PRICE = 100
BOTTED_MIN_LIMIT = 10_000


def classify_item(item_id: int, buy_price: float, members: bool,
                  buy_limit: Optional[int],
                  trend: Optional[Trend] = None,
                  crash: Optional[CrashSignal] = None,
                  supply: Optional[str] = None,
                  calibration: engine.Calibration = engine.DEFAULT_CALIBRATION
                  ) -> List[str]:
    """Tags for one item. Order is stable so table cells do not jump around."""
    tags = []
    if is_botted(buy_price, members, buy_limit):
        tags.append(BOTTED)
    if (trend is not None and trend.direction == UPTREND
            and trend.r_squared >= calibration.merch_min_r2):
        tags.append(MERCH)
    if item_id in RAID_UNIQUE_IDS:
        tags.append(RAID)
    if supply is not None:
        tags.append(supply)
    if crash is not None:
        tags.append(crash.kind)
    return tags


def is_botted(buy_price: float, members: bool,
              buy_limit: Optional[int]) -> bool:
    """Bot-supplied f2p staple: the price is set by scripts, not by players."""
    return (not members
            and (buy_limit or 0) >= BOTTED_MIN_LIMIT
            and buy_price < BOTTED_MAX_PRICE)


# ---------------------------------------------------------------------------
# watchlist
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WatchItem:
    """An item worth pulling a year of history for, and why.

    Ids only — no names, no prices, no trend figures. Names come from /mapping
    and everything else is computed at runtime. A hardcoded price is wrong the
    day after it is written: checked against live data on 2026-07-26, a list
    written the previous day already had one raid unique 14% low and another
    10% high.
    """
    item_id: int
    thesis: str


WATCHLIST = (
    # Consumables and runes: demand grows with the PvM population, supply is
    # capped by how many people actually train the skill that makes them.
    WatchItem(565, "PvM magic demand; the cleanest long trend on the list"),
    WatchItem(560, "Same demand curve as blood runes, lower unit price"),
    WatchItem(536, "Prayer training sink; nothing else replaces it"),
    WatchItem(13441, "Best combo food in the game; cooked, not raw"),
    WatchItem(385, "PvM food staple below anglerfish"),
    WatchItem(28924, "Sunfire splinters: newer sink, momentum flattening"),
    WatchItem(5952, "Zulrah and CoX consumable; steady drain"),
    WatchItem(1601, "Crafting and bolt tips; f2p, constant demand"),
    WatchItem(11212, "Blowpipe and bow ammo; crashed hard from its peak"),
    WatchItem(221, "Herblore secondary; cheap with a high limit"),

    # Raid uniques: the supply-crunch thesis. Volume decline is the signal;
    # price follows months later, or does not, which is the risk.
    WatchItem(21079, "Augury scroll; supply falls as CoX empties out"),
    WatchItem(21034, "Rigour scroll; same thesis, higher entry price"),
    WatchItem(21047, "Cheapest raid scroll; smallest position to take"),
    WatchItem(26219, "ToA unique still in its supply phase"),
    WatchItem(22477, "ToB hilt; deeply crashed, volume gone"),
    WatchItem(13652, "Dragon claws; cheapest in years on collapsed volume"),
    WatchItem(22978, "Hydra and dragon slayer weapon; volume gone"),
    WatchItem(21012, "Dragon hunter crossbow; same story as the lance"),
    WatchItem(22324, "ToB rapier; bottom-fishing candidate"),
    WatchItem(21006, "CoX wand; best mage weapon at its price"),

    # Not a merch thesis: the best-known botted f2p item, kept so the
    # classification has something to prove itself against.
    WatchItem(11804, "Bandos godsword; BGS spec is still the PvM opener"),
)

WATCHLIST_IDS = tuple(item.item_id for item in WATCHLIST)

THESIS_BY_ID: Dict[int, str] = {item.item_id: item.thesis for item in WATCHLIST}
