"""Unit tests for stats.py — run with: python3 -m unittest test_stats -v"""
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
