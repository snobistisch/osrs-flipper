"""Estimators the scoring engine needs. Pure stdlib, no numpy or scipy.

Three jobs live here:

1. Ornstein-Uhlenbeck fits, so "is this item above its normal price" becomes a
   per-item measurement instead of one hardcoded decay constant applied to
   4,454 items that behave nothing alike.
2. Empirical-Bayes shrinkage, which is the only defence against the optimizer's
   curse: rank 4,454 noisy estimates and the winners are the ones with the
   largest positive errors, not the largest true values.
3. The posterior probability that an item's true score beats the market-wide
   average, which answers "could this rank plausibly be noise" rather than
   assuming every positive number is an opportunity.

   The design document specifies a two-component spike-and-slab mixture here,
   on the reasoning that most items have no edge at all and a few do. That
   holds over the whole item universe, but not over the set this pipeline
   scores: items whose margin cannot survive the tax are already gone, so the
   spike at zero has been filtered out before the mixture would ever see it.
   Fitted anyway, EM put 95% of items in the "has an edge" component and
   assigned every row on the shortlist a probability of 1.0 — a number that
   looked like a measurement and carried none. The posterior from the
   hierarchical model answers the same question using the data that is
   actually there.

Everything returns its own diagnostics (t-statistics, shrinkage weights,
posterior probabilities) because the point of the rebuild is that each step can
be checked against outcomes separately.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence


def median(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def median_absolute_deviation(values: Sequence[float]) -> Optional[float]:
    """Robust spread. A handful of spiked buckets barely move it, so a pump
    reads as a large deviation from a stable centre rather than as a new normal."""
    centre = median(values)
    if centre is None:
        return None
    return median([abs(v - centre) for v in values])


def mean(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


# ---------------------------------------------------------------------------
# Ordinary least squares on one regressor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OLSFit:
    intercept: float
    slope: float
    residual_variance: float
    slope_stderr: float
    n: int

    @property
    def t_stat(self) -> float:
        if self.slope_stderr <= 0:
            return 0.0
        return self.slope / self.slope_stderr


def ols(x: Sequence[float], y: Sequence[float]) -> Optional[OLSFit]:
    """Fit y = a + b*x. Returns None when x has no variation to regress on."""
    n = len(x)
    if n < 3 or n != len(y):
        return None
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    sxx = sum((xi - mean_x) ** 2 for xi in x)
    if sxx <= 0:
        return None
    sxy = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    residuals = [yi - (intercept + slope * xi) for xi, yi in zip(x, y)]
    dof = n - 2
    residual_variance = sum(r * r for r in residuals) / dof if dof > 0 else 0.0
    slope_stderr = math.sqrt(residual_variance / sxx) if residual_variance > 0 else 0.0
    return OLSFit(intercept=intercept, slope=slope,
                  residual_variance=residual_variance,
                  slope_stderr=slope_stderr, n=n)


# ---------------------------------------------------------------------------
# Ornstein-Uhlenbeck
# ---------------------------------------------------------------------------

# |t| threshold for calling the slope significantly negative. With ~56 buckets
# the t distribution is close enough to normal that 2.0 is the 2.5% one-sided
# tail; no scipy needed for a decision this coarse.
MEAN_REVERSION_T = 2.0


@dataclass(frozen=True)
class OUFit:
    """dp = kappa*(mu - p)*dt + sigma*dW, fitted on LOG prices.

    Log prices because the item universe spans five orders of magnitude and an
    absolute-price fit would let one 200m item dominate any pooled statistic.
    mu is therefore a log price: exp(mu) is the level in gp.
    """
    kappa: float          # reversion speed, per day
    mu: float             # long-run mean of log price
    sigma: float          # volatility of log price, per sqrt(day)
    t_stat: float         # on the regression slope; negative = reverting
    n: int
    dt_days: float

    @property
    def mean_reverting(self) -> bool:
        return self.kappa > 0 and self.t_stat <= -MEAN_REVERSION_T

    @property
    def half_life_days(self) -> Optional[float]:
        if self.kappa <= 0:
            return None
        return math.log(2.0) / self.kappa

    @property
    def level_gp(self) -> float:
        return math.exp(self.mu)

    def expected_log_return(self, price: float, days: float) -> float:
        """Expected log return from mean reversion over `days`.

        Uses the exact OU solution rather than the Euler step: over a long
        horizon the linear form kappa*(mu-p)*t overshoots the mean, which for a
        fast-reverting item at 20% below its level would predict a return of
        several hundred percent.
        """
        if price <= 0 or days <= 0 or self.kappa <= 0:
            return 0.0
        gap = self.mu - math.log(price)
        return gap * (1.0 - math.exp(-self.kappa * days))


def fit_ou(prices: Sequence[float], dt_days: float) -> Optional[OUFit]:
    """Fit an OU process to evenly spaced prices (oldest first).

    Regress the log-price change on the previous log price, per Appendix B:
        dp_t = a + b*p_{t-1} + e   ->   kappa = -b/dt, mu = -a/b
    """
    usable = [p for p in prices if p is not None and p > 0]
    if len(usable) < 12 or dt_days <= 0:
        return None
    logs = [math.log(p) for p in usable]
    lagged = logs[:-1]
    deltas = [logs[i + 1] - logs[i] for i in range(len(logs) - 1)]
    fit = ols(lagged, deltas)
    if fit is None:
        return None
    b = fit.slope
    kappa = -b / dt_days
    # b >= 0 is a random walk or an explosive series; mu is then undefined and
    # the caller should treat the item as trending, not reverting.
    mu = (-fit.intercept / b) if b < 0 else (sum(logs) / len(logs))
    sigma = math.sqrt(fit.residual_variance / dt_days) if fit.residual_variance > 0 else 0.0
    return OUFit(kappa=kappa, mu=mu, sigma=sigma, t_stat=fit.t_stat,
                 n=len(usable), dt_days=dt_days)


def regime_shift(prices: Sequence[float]) -> float:
    """How far the second half of the series sits from the first, in units of
    the first half's own spread.

    A game update that re-prices an item shows up as a level shift no
    mean-reversion model should be trusted through: the pre-update mean is not
    the level the price is heading back to.
    """
    usable = [p for p in prices if p is not None and p > 0]
    if len(usable) < 12:
        return 0.0
    split = len(usable) // 2
    first, second = usable[:split], usable[split:]
    centre_first = median(first)
    centre_second = median(second)
    spread = median_absolute_deviation(first)
    if not centre_first or centre_second is None:
        return 0.0
    # MAD of zero means a perfectly flat first half; fall back to 1% of level
    # so a genuine shift is not divided by zero into infinity.
    scale = spread if spread and spread > 0 else 0.01 * centre_first
    return abs(centre_second - centre_first) / scale


# ---------------------------------------------------------------------------
# Empirical Bayes — the optimizer's curse correction
# ---------------------------------------------------------------------------

def normal_cdf(z: float) -> float:
    """Standard normal CDF via erf — enough for reporting a probability."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


@dataclass(frozen=True)
class ShrinkageResult:
    values: List[float]        # posterior means, same order as the input
    prior_mean: float
    prior_variance: float      # tau^2; 0 means "all spread is noise"
    weights: List[float]       # per item: how much of its own estimate survived
    posterior_variances: List[float] = field(default_factory=list)

    @property
    def shrank_everything(self) -> bool:
        return self.prior_variance <= 0

    def probability_above_mean(self, index: int) -> float:
        """P(this item's true value exceeds the cross-sectional mean).

        The honest reading of a rank. A big estimate on thin data produces a
        posterior barely distinguishable from the average, and this reports
        that as roughly a coin flip rather than as a top-of-the-list finding.
        """
        if not self.posterior_variances or index >= len(self.posterior_variances):
            return 0.5
        variance = self.posterior_variances[index]
        if variance <= 0:
            return 1.0 if self.values[index] > self.prior_mean else 0.0
        return normal_cdf((self.values[index] - self.prior_mean)
                          / math.sqrt(variance))


def empirical_bayes(estimates: Sequence[float],
                    noise_variances: Sequence[float]) -> ShrinkageResult:
    """Normal-normal shrinkage with method-of-moments hyperparameters.

    Each estimate is treated as its true value plus noise whose size we know up
    to a scale: thin-volume items carry much larger noise than staples. The
    posterior pulls every estimate toward the common mean, and pulls the noisy
    ones much further. That is the correction the ranking needs — the items
    that top an unshrunken list are the ones whose noise happened to be
    positive, and those are disproportionately the thin ones.

    The centre is the UNWEIGHTED mean, deliberately. The textbook choice is the
    inverse-variance weighted mean, which is the efficient estimator when every
    value really is drawn from one distribution. Here it is not safe: noise is
    tied to traded volume, so weighting by precision hands almost all the
    weight to a handful of the most liquid items in the game. Measured on live
    data that put the "market average" at the score of the single busiest item,
    and every thin item was then shrunk *upward* toward it — inflating exactly
    the estimates this function exists to deflate. The unweighted mean
    represents the typical item, which is what the rest are being compared to.

    tau^2 = 0 (no spread beyond what noise explains) collapses every item to
    that mean, which is the honest answer to "none of these differences are
    real".
    """
    n = len(estimates)
    if n == 0:
        return ShrinkageResult([], 0.0, 0.0, [], [])
    if n != len(noise_variances):
        raise ValueError("estimates and noise_variances must be the same length")
    safe_noise = [max(v, 1e-12) for v in noise_variances]
    centre = sum(estimates) / n

    if n < 3:
        return ShrinkageResult(list(estimates), centre, float("inf"),
                               [1.0] * n, list(safe_noise))

    # Observed spread is true spread plus average noise, so subtracting the
    # average noise leaves an estimate of the true spread. Negative means the
    # observed differences are smaller than noise alone would produce: there is
    # nothing to tell apart.
    observed_variance = sum((e - centre) ** 2 for e in estimates) / (n - 1)
    mean_noise = sum(safe_noise) / n
    tau_squared = max(0.0, observed_variance - mean_noise)

    posterior, kept, variances = [], [], []
    for estimate, noise in zip(estimates, safe_noise):
        weight = tau_squared / (tau_squared + noise) if tau_squared > 0 else 0.0
        posterior.append(weight * estimate + (1.0 - weight) * centre)
        kept.append(weight)
        # Posterior variance of the normal-normal model. Shrinking hard also
        # means being uncertain, and this is what carries that through to the
        # probability reported next to each row.
        variances.append(weight * noise)
    return ShrinkageResult(posterior, centre, tau_squared, kept, variances)
