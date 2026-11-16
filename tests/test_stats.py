"""Unit tests for stats.py — run with: python3 -m unittest tests.test_stats -v"""
import math
import random
import unittest

import stats


class OLSTests(unittest.TestCase):
    def test_recovers_a_known_line(self):
        x = list(range(20))
        y = [3.0 + 2.0 * xi for xi in x]
        fit = stats.ols(x, y)
        self.assertAlmostEqual(fit.intercept, 3.0, places=6)
        self.assertAlmostEqual(fit.slope, 2.0, places=6)

    def test_no_variation_in_x_is_unfittable(self):
        self.assertIsNone(stats.ols([5.0] * 10, list(range(10))))

    def test_too_few_points(self):
        self.assertIsNone(stats.ols([1, 2], [1, 2]))


class OUTests(unittest.TestCase):
    def test_recovers_mean_reversion_from_a_simulated_process(self):
        # Simulate dp = kappa*(mu - p)dt + sigma*dW on log prices.
        random.seed(7)
        kappa, mu, sigma, dt = 4.0, math.log(1000.0), 0.20, 0.25
        p = mu
        prices = []
        for _ in range(400):
            p += kappa * (mu - p) * dt + sigma * math.sqrt(dt) * random.gauss(0, 1)
            prices.append(math.exp(p))
        fit = stats.fit_ou(prices, dt)
        self.assertTrue(fit.mean_reverting)
        self.assertLess(abs(fit.level_gp - 1000.0), 120.0)
        # kappa is noisy from a single path; an order of magnitude is enough to
        # separate "reverts within days" from "random walk".
        self.assertGreater(fit.kappa, 1.0)
        self.assertLess(fit.kappa, 12.0)

    def test_random_walk_is_not_called_mean_reverting(self):
        random.seed(11)
        price = 1000.0
        prices = []
        for _ in range(300):
            price *= math.exp(0.02 * random.gauss(0, 1))
            prices.append(price)
        fit = stats.fit_ou(prices, 0.25)
        self.assertFalse(fit.mean_reverting)

    def test_random_walk_false_positive_rate_is_about_five_percent(self):
        # Under a random walk the slope's t follows Dickey-Fuller, not
        # Student's t; at the old threshold of 2.0 this rate was 28%.
        random.seed(20261116)
        hits = 0
        walks = 2000
        for _ in range(walks):
            log_price = math.log(1000.0)
            prices = []
            for _ in range(56):
                log_price += random.gauss(0, 0.02)
                prices.append(math.exp(log_price))
            fit = stats.fit_ou(prices, 0.25)
            hits += bool(fit is not None and fit.mean_reverting)
        self.assertLessEqual(hits / walks, 0.08)

    def test_expected_return_does_not_overshoot_the_mean(self):
        # A fast-reverting item 30% below its level, held for a long time,
        # must converge on the gap and never exceed it. The naive Euler form
        # kappa*(mu-p)*t would predict several hundred percent here.
        fit = stats.OUFit(kappa=8.0, mu=math.log(1000.0), sigma=0.1,
                          t_stat=-5.0, n=100, dt_days=0.25)
        gap = math.log(1000.0) - math.log(700.0)
        for days in (0.1, 1.0, 10.0, 1000.0):
            self.assertLessEqual(fit.expected_log_return(700.0, days), gap + 1e-9)
        self.assertGreater(fit.expected_log_return(700.0, 10.0), 0)

    def test_half_life_matches_kappa(self):
        fit = stats.OUFit(kappa=math.log(2.0), mu=0.0, sigma=0.1, t_stat=-4.0,
                          n=50, dt_days=0.25)
        self.assertAlmostEqual(fit.half_life_days, 1.0, places=6)

    def test_too_short_a_series_returns_none(self):
        self.assertIsNone(stats.fit_ou([100.0] * 5, 0.25))


def _fit_ou_before_gaps(prices, dt_days):
    """fit_ou as it was before gaps were kept (audit F-14), for comparison."""
    usable = [p for p in prices if p is not None and p > 0]
    if len(usable) < 12 or dt_days <= 0:
        return None
    logs = [math.log(p) for p in usable]
    fit = stats.ols(logs[:-1], [logs[i + 1] - logs[i]
                                for i in range(len(logs) - 1)])
    if fit is None:
        return None
    b = fit.slope
    mu = (-fit.intercept / b) if b < 0 else (sum(logs) / len(logs))
    sigma = (math.sqrt(fit.residual_variance / dt_days)
             if fit.residual_variance > 0 else 0.0)
    return stats.OUFit(kappa=-b / dt_days, mu=mu, sigma=sigma,
                       t_stat=fit.t_stat, n=len(usable), dt_days=dt_days)


class OUGapTests(unittest.TestCase):
    """Buckets without trades stay in the series as gaps (audit F-14)."""

    def series(self, seed, n=56, kappa=0.0):
        rng = random.Random(seed)
        log_price, prices = math.log(1000.0), []
        for _ in range(n):
            log_price += (kappa * (math.log(1000.0) - log_price) * 0.25
                          + rng.gauss(0, 0.02))
            prices.append(math.exp(log_price))
        return prices

    def test_a_series_without_gaps_fits_exactly_as_before(self):
        cases = [self.series(seed) for seed in range(20)]
        cases += [self.series(seed, n=300, kappa=4.0) for seed in range(5)]
        cases += [[100.0 + (i % 3) for i in range(40)], [100.0] * 5]
        for prices in cases:
            new = stats.fit_ou(prices, 0.25)
            old = _fit_ou_before_gaps(prices, 0.25)
            if old is None:
                self.assertIsNone(new)
                continue
            for name in ("kappa", "mu", "sigma", "t_stat"):
                self.assertTrue(math.isclose(getattr(new, name),
                                             getattr(old, name),
                                             rel_tol=1e-12, abs_tol=1e-12),
                                name)
            self.assertEqual(new.n, old.n)

    def test_only_consecutive_traded_buckets_form_pairs(self):
        prices = self.series(3)
        for index in range(0, 56, 3):
            prices[index] = None
        fit = stats.fit_ou(prices, 0.25)
        self.assertEqual(fit.n, 18 + 1)

    def test_fewer_than_eleven_pairs_is_no_fit(self):
        prices = self.series(4, n=12)
        self.assertEqual(stats.fit_ou(prices, 0.25).n, 12)     # 11 pairs
        prices[5] = None                                        # 9 pairs
        self.assertIsNone(stats.fit_ou(prices, 0.25))
        self.assertIsNone(stats.fit_ou(self.series(4, n=11), 0.25))

    def test_a_gap_is_not_read_as_one_step(self):
        # A thin item that trades every other bucket. Closing the gaps reads
        # two steps of noise as one and overstates the volatility.
        prices = self.series(9, n=112)
        gapped = [p if i % 2 else None for i, p in enumerate(prices)]
        closed = [p for p in gapped if p is not None]
        self.assertIsNone(stats.fit_ou(gapped, 0.25))
        self.assertIsNotNone(stats.fit_ou(closed, 0.25))


class RegimeTests(unittest.TestCase):
    def test_flat_series_has_no_shift(self):
        prices = [100.0 + (i % 3) for i in range(40)]
        self.assertLess(stats.regime_shift(prices), 4.0)

    def test_level_change_is_detected(self):
        prices = [100.0 + (i % 3) for i in range(20)] + [400.0] * 20
        self.assertGreater(stats.regime_shift(prices), 4.0)

    def test_flat_first_half_does_not_divide_by_zero(self):
        prices = [100.0] * 20 + [130.0] * 20
        value = stats.regime_shift(prices)
        self.assertTrue(math.isfinite(value))
        self.assertGreater(value, 0)


class EmpiricalBayesTests(unittest.TestCase):
    def test_noisy_estimates_are_pulled_further_than_precise_ones(self):
        estimates = [10.0, 10.0]
        # Same estimate, wildly different evidence behind each.
        result = stats.empirical_bayes(estimates + [0.0] * 8,
                                       [0.01, 5.0] + [0.01] * 8)
        precise, noisy = result.values[0], result.values[1]
        self.assertGreater(precise, noisy)
        self.assertGreater(result.weights[0], result.weights[1])

    def test_all_spread_explained_by_noise_collapses_to_the_mean(self):
        # Estimates scattered no more than their own noise would scatter them.
        estimates = [0.0, 0.1, -0.1, 0.05, -0.05, 0.0, 0.02, -0.02]
        result = stats.empirical_bayes(estimates, [1.0] * len(estimates))
        self.assertEqual(result.prior_variance, 0.0)
        self.assertTrue(result.shrank_everything)
        for value in result.values:
            self.assertAlmostEqual(value, result.prior_mean, places=9)

    def test_centre_is_unweighted_so_one_precise_item_cannot_define_average(self):
        # One extremely precise, extremely high estimate among many ordinary
        # ones. An inverse-variance weighted centre would sit near 100 and drag
        # every other item upward; the unweighted centre must not.
        estimates = [100.0] + [1.0] * 20
        noise = [1e-6] + [1.0] * 20
        result = stats.empirical_bayes(estimates, noise)
        self.assertLess(result.prior_mean, 20.0)

    def test_posterior_probability_is_uncertain_when_evidence_is_thin(self):
        estimates = [5.0] + [0.0] * 30
        noise = [9.0] + [0.05] * 30       # the leader rests on almost nothing
        result = stats.empirical_bayes(estimates, noise)
        self.assertLess(result.probability_above_mean(0), 0.95)

    def test_length_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            stats.empirical_bayes([1.0, 2.0], [1.0])

    def test_empty_input(self):
        result = stats.empirical_bayes([], [])
        self.assertEqual(result.values, [])


class NormalTests(unittest.TestCase):
    def test_cdf_endpoints(self):
        self.assertAlmostEqual(stats.normal_cdf(0.0), 0.5, places=9)
        self.assertGreater(stats.normal_cdf(4.0), 0.999)
        self.assertLess(stats.normal_cdf(-4.0), 0.001)


class RobustStatTests(unittest.TestCase):
    def test_median_of_even_length(self):
        self.assertEqual(stats.median([1, 2, 3, 4]), 2.5)

    def test_mad_ignores_one_spike(self):
        calm = [100] * 20
        spiked = calm + [10_000]
        self.assertEqual(stats.median_absolute_deviation(calm), 0)
        self.assertEqual(stats.median_absolute_deviation(spiked), 0)

    def test_median_of_empty(self):
        self.assertIsNone(stats.median([]))


if __name__ == "__main__":
    unittest.main()
