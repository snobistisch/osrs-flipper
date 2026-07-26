"""Tests for the long-horizon signals in merch.py.

Run with: python3 -m unittest test_merch -v

The interesting tests here are not the arithmetic ones. They are:

- `TrendFalsePositiveTests`, which simulates price series with no trend in them
  at all and asserts that the labeller mostly says so. That is the property the
  module exists to get right, and it is the one that silently degrades if
  someone lowers `merch_trend_t` to make more items show up.
- `CrashPrecedenceTests`, which pins the order of the badge rules. The rules
  overlap, so the order is the specification.
"""
from __future__ import annotations

import math
import random
import unittest
from dataclasses import replace
from pathlib import Path

import engine
import merch
import stats


def price_series(drift: float, sigma: float, n: int = 365, seed: int = 0,
                 start: float = 1000.0, volume: int = 500):
    """A synthetic /timeseries response: geometric random walk with drift."""
    rng = random.Random(seed)
    price = start
    points = []
    for i in range(n):
        price *= math.exp(drift + rng.gauss(0.0, sigma))
        points.append({
            "timestamp": 1_700_000_000 + i * 86400,
            "avgHighPrice": price * 1.005,
            "avgLowPrice": price * 0.995,
            "highPriceVolume": volume,
            "lowPriceVolume": volume,
        })
    return points


class TrendShapeTests(unittest.TestCase):
    def test_a_strong_uptrend_is_labelled_up(self):
        trend = merch.compute_trend(price_series(0.002, 0.005, seed=1))
        self.assertEqual(trend.direction, merch.UPTREND)
        self.assertGreater(trend.r_squared, 0.8)
        self.assertGreater(trend.annualised_pct, 50)

    def test_a_strong_downtrend_is_labelled_down(self):
        trend = merch.compute_trend(price_series(-0.002, 0.005, seed=2))
        self.assertEqual(trend.direction, merch.DOWNTREND)
        self.assertLess(trend.annualised_pct, -30)

    def test_a_flat_series_is_sideways(self):
        trend = merch.compute_trend(price_series(0.0, 0.002, seed=3))
        self.assertEqual(trend.direction, merch.SIDEWAYS)

    def test_too_few_traded_days_returns_none(self):
        self.assertIsNone(merch.compute_trend(price_series(0.002, 0.01, n=20)))

    def test_untraded_days_are_dropped_not_interpolated(self):
        points = price_series(0.002, 0.004, n=120, seed=4)
        for p in points[40:70]:            # a month with no trades at all
            p["avgHighPrice"] = None
            p["avgLowPrice"] = None
            p["highPriceVolume"] = 0
            p["lowPriceVolume"] = 0
        trend = merch.compute_trend(points)
        self.assertEqual(trend.n, 90)
        # The slope is per elapsed DAY, so dropping the middle month must not
        # steepen it. Index-based regression would report roughly 120/90 of the
        # true rate here.
        self.assertAlmostEqual(trend.slope_per_day, 0.002, delta=0.0008)

    def test_annualised_is_compounded_from_the_log_slope(self):
        trend = merch.compute_trend(price_series(0.001, 0.001, seed=5))
        expected = (math.exp(trend.slope_per_day * 365) - 1) * 100
        self.assertAlmostEqual(trend.annualised_pct, expected, places=6)

    def test_annualised_is_capped_rather_than_absurd(self):
        # 3%/day compounds to something like 5,000,000%/yr.
        trend = merch.compute_trend(price_series(0.03, 0.002, seed=6))
        self.assertEqual(trend.annualised_pct, merch.ANNUALISED_REPORT_CAP)

    def test_deviation_is_measured_against_the_fitted_line(self):
        points = price_series(0.002, 0.001, seed=7)
        points[-1]["avgHighPrice"] *= 0.80
        points[-1]["avgLowPrice"] *= 0.80
        trend = merch.compute_trend(points)
        self.assertLess(trend.deviation, -0.15)

    def test_scale_does_not_change_the_fit(self):
        """A 5 gp herb and a 60m wand with the same shape must score alike."""
        cheap = merch.compute_trend(price_series(0.002, 0.004, seed=8, start=5))
        rich = merch.compute_trend(
            price_series(0.002, 0.004, seed=8, start=60_000_000))
        self.assertAlmostEqual(cheap.r_squared, rich.r_squared, places=6)
        self.assertAlmostEqual(cheap.annualised_pct, rich.annualised_pct,
                               places=6)


class TrendFalsePositiveTests(unittest.TestCase):
    """The property that matters: noise must not read as a trend.

    A year of daily prices with zero drift still wanders far enough to look
    like a 25%/yr trend. These bounds are what `merch_trend_t = 5.0` was chosen
    to deliver; if a change moves them, the threshold has to be re-argued, not
    the test loosened.
    """

    SAMPLES = 300

    def _label_rate(self, drift, sigma, calibration=None):
        cal = calibration or engine.DEFAULT_CALIBRATION
        labelled = 0
        for seed in range(self.SAMPLES):
            trend = merch.compute_trend(
                price_series(drift, sigma, seed=seed), calibration=cal)
            if trend is not None and trend.direction != merch.SIDEWAYS:
                labelled += 1
        return labelled / self.SAMPLES

    def test_driftless_walks_are_mostly_called_sideways(self):
        rate = self._label_rate(0.0, 0.012)
        self.assertLess(rate, 0.25,
                        "{:.0%} of pure random walks were labelled a trend — "
                        "merch_trend_t is too low".format(rate))

    def test_genuine_trends_are_still_found(self):
        rate = self._label_rate(0.0015, 0.010)
        self.assertGreater(rate, 0.60,
                           "only {:.0%} of real trends were found — "
                           "merch_trend_t is too high".format(rate))

    def test_the_autocorrelation_correction_is_what_buys_that(self):
        """Without it, the same threshold would pass most of the noise."""
        naive, corrected = [], []
        for seed in range(60):
            points = price_series(0.0, 0.012, seed=seed)
            trend = merch.compute_trend(points)
            xs, ys = [], []
            t0 = points[0]["timestamp"]
            for p in points:
                xs.append((p["timestamp"] - t0) / 86400.0)
                ys.append(math.log(merch._point_mid(p)))
            fit = stats.ols(xs, ys)
            naive.append(abs(fit.t_stat))
            corrected.append(abs(trend.t_stat))
        self.assertGreater(sum(naive) / len(naive),
                           4 * sum(corrected) / len(corrected))


class MerchScoreTests(unittest.TestCase):
    def setUp(self):
        self.up = merch.compute_trend(price_series(0.002, 0.005, seed=11))
        self.down = merch.compute_trend(price_series(-0.002, 0.005, seed=12))

    def test_only_uptrends_score(self):
        self.assertEqual(merch.merch_score(self.down, 10_000), 0.0)
        self.assertEqual(merch.merch_score(None, 10_000), 0.0)
        self.assertGreater(merch.merch_score(self.up, 10_000), 0.0)

    def test_a_weak_fit_scores_nothing_even_when_rising(self):
        cal = replace(engine.DEFAULT_CALIBRATION, merch_min_r2=0.99)
        self.assertEqual(merch.merch_score(self.up, 10_000, calibration=cal),
                         0.0)

    def test_a_high_buy_limit_helps(self):
        small = merch.merch_score(self.up, 5)
        large = merch.merch_score(self.up, 25_000)
        self.assertGreater(large, small)

    def test_botted_items_are_discounted(self):
        clean = merch.merch_score(self.up, 25_000, botted=False)
        botted = merch.merch_score(self.up, 25_000, botted=True)
        self.assertLess(botted, clean)

    def test_the_score_never_goes_negative(self):
        cal = replace(engine.DEFAULT_CALIBRATION, merch_botted_penalty=5.0)
        self.assertGreaterEqual(
            merch.merch_score(self.up, 25_000, botted=True, calibration=cal),
            0.0)

    def test_a_wild_riser_cannot_dominate_the_ranking(self):
        wild = merch.compute_trend(price_series(0.03, 0.002, seed=13))
        steady = merch.compute_trend(price_series(0.002, 0.002, seed=14))
        self.assertLess(merch.merch_score(wild, 10_000),
                        20 * merch.merch_score(steady, 10_000))


class EntrySignalTests(unittest.TestCase):
    def test_a_pullback_below_the_trend_line_is_an_entry(self):
        points = price_series(0.002, 0.002, seed=15)
        points[-1]["avgHighPrice"] *= 0.90
        points[-1]["avgLowPrice"] *= 0.90
        trend = merch.compute_trend(points)
        signal = merch.entry_signal(points[-1]["avgLowPrice"], trend)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.kind, "PULLBACK")

    def test_no_entry_signal_on_a_falling_item(self):
        trend = merch.compute_trend(price_series(-0.002, 0.005, seed=16))
        self.assertIsNone(merch.entry_signal(100, trend, median_mid=200))

    def test_below_the_median_counts_when_the_trend_line_does_not(self):
        trend = merch.compute_trend(price_series(0.002, 0.002, seed=17))
        signal = merch.entry_signal(80, trend, median_mid=100)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.kind, "BELOW_MEDIAN")


class VolumeTests(unittest.TestCase):
    def test_baseline_ignores_the_spike_it_has_to_detect(self):
        points = price_series(0.0, 0.005, n=100, seed=18, volume=1000)
        for p in points[-3:]:                      # a three-day dump
            p["highPriceVolume"] = 200_000
            p["lowPriceVolume"] = 200_000
        baseline = merch.volume_baseline(points)
        self.assertAlmostEqual(baseline, 2000, delta=1)
        self.assertGreater(merch.volume_ratio(400_000, baseline), 100)

    def test_volume_ratio_is_one_when_unmeasurable(self):
        self.assertEqual(merch.volume_ratio(500, None), 1.0)
        self.assertEqual(merch.volume_ratio(500, 0), 1.0)
        self.assertEqual(merch.volume_ratio(None, 100), 1.0)

    def test_volume_change_measures_the_collapse(self):
        points = price_series(0.0, 0.005, n=365, seed=19, volume=1000)
        # 31 days, because the final bucket is dropped as incomparable.
        for p in points[-31:]:
            p["highPriceVolume"] = 100
            p["lowPriceVolume"] = 100
        change = merch.volume_change(points)
        self.assertAlmostEqual(change, -0.9, delta=0.02)

    def test_the_final_bucket_is_excluded_from_volume_maths(self):
        """The wiki's last 24h bucket is a full day; the rest are 6h samples.

        Leaving it in reported an 8x volume spike on every item in the game at
        once — which is what the first live run of the crash scanner did.
        """
        points = price_series(0.0, 0.005, n=120, seed=32, volume=1000)
        points[-1]["highPriceVolume"] = 8_000_000
        points[-1]["lowPriceVolume"] = 8_000_000
        baseline = merch.volume_baseline(points)
        self.assertAlmostEqual(baseline, 2000, delta=1)
        self.assertAlmostEqual(merch.latest_comparable_volume(points), 2000,
                               delta=1)
        view = merch.daily_view(points)
        self.assertAlmostEqual(view.volume_ratio, 1.0, delta=0.01)
        self.assertIsNone(view.crash)

    def test_a_real_spike_is_still_seen_a_day_later(self):
        points = price_series(0.0, 0.005, n=120, seed=33, volume=1000)
        points[-2]["highPriceVolume"] = 15_000
        points[-2]["lowPriceVolume"] = 15_000
        self.assertGreater(merch.daily_view(points).volume_ratio, 10)

    def test_volume_change_refuses_a_short_history(self):
        self.assertIsNone(
            merch.volume_change(price_series(0.0, 0.005, n=60, seed=20)))

    def test_the_baseline_only_looks_at_the_trailing_window(self):
        """A year-long baseline breaks on a market whose volume is drifting.

        Volume here decays steadily, as it did on every watchlist item measured
        against live data. The baseline has to mean "normal lately", or every
        item in a quiet market reads as trading suspiciously thin.
        """
        points = price_series(0.0, 0.005, n=365, seed=30)
        for index, point in enumerate(points):
            volume = int(100_000 * (0.5 ** (index / 120)))
            point["highPriceVolume"] = volume
            point["lowPriceVolume"] = volume
        baseline = merch.volume_baseline(points)
        recent = points[-1]["highPriceVolume"] + points[-1]["lowPriceVolume"]
        # Normal-for-now, so today sits near 1x rather than far below it.
        self.assertGreater(merch.volume_ratio(recent, baseline), 0.7)


class MarketContextTests(unittest.TestCase):
    """The regression that live data exposed.

    Measured over a year, every item on the watchlist showed volume down
    between 50% and 86% — the market as a whole had gone quiet. Read
    absolutely, that badges all twenty-one as a supply crunch, which is the
    same as badging none of them.
    """

    def _basket(self, item_changes):
        views = {}
        for item_id, change in enumerate(item_changes, start=1):
            views[item_id] = merch.DailyView(
                days=365, trend=None, price=100, median_14d=100, depth=0.0,
                volume_today=10.0, volume_baseline=10.0, volume_ratio=1.0,
                volume_change_6m=change, crash=None)
        return merch.apply_market_context(views)

    def test_a_market_wide_collapse_badges_nobody(self):
        views = self._basket([-0.74] * 12)
        self.assertTrue(all(view.supply is None for view in views.values()))

    def test_an_item_falling_faster_than_the_market_is_badged(self):
        views = self._basket([-0.70] * 11 + [-0.97])
        self.assertIsNone(views[1].supply)
        self.assertEqual(views[12].supply, merch.SUPPLY_CRUNCH)

    def test_the_market_move_is_reported_not_hidden(self):
        views = self._basket([-0.74] * 12)
        self.assertAlmostEqual(views[1].market_drift, -0.74, places=6)

    def test_drift_needs_a_basket_before_it_will_guess(self):
        self.assertIsNone(merch.market_volume_drift([-0.8, -0.7, -0.9]))
        self.assertIsNone(merch.market_volume_drift([None] * 20))

    def test_without_a_basket_no_item_is_badged(self):
        views = self._basket([-0.95] * 3)
        self.assertTrue(all(view.supply is None for view in views.values()))
        self.assertTrue(all(view.volume_change_relative is None
                            for view in views.values()))

    def test_relative_change_divides_the_market_out(self):
        # Down 80% while the market is down 60% is down 50% of what remains.
        self.assertAlmostEqual(
            merch.relative_volume_change(-0.80, -0.60), -0.5, places=6)
        self.assertAlmostEqual(
            merch.relative_volume_change(-0.60, -0.60), 0.0, places=6)


class NoiseProbabilityTests(unittest.TestCase):
    def test_it_falls_as_the_statistic_grows(self):
        values = [merch.noise_probability(t) for t in (0, 1, 2, 5, 10, 20)]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_it_is_symmetric_in_sign(self):
        self.assertEqual(merch.noise_probability(-4.2),
                         merch.noise_probability(4.2))

    def test_it_stays_a_probability(self):
        for t in (-100, -5, 0, 3.7, 50, 1000):
            self.assertTrue(0.0 <= merch.noise_probability(t) <= 1.0)

    def test_it_interpolates_between_measured_points(self):
        between = merch.noise_probability(3.5)
        self.assertLess(between, merch.noise_probability(3.0))
        self.assertGreater(between, merch.noise_probability(4.0))

    def test_the_curve_still_matches_a_fresh_simulation(self):
        """Regenerates the table the constant was measured from.

        Fewer samples than the original 3,000, so the tolerance is loose; this
        catches the curve being wrong, not the third decimal drifting.
        """
        magnitudes = sorted(
            abs(merch.compute_trend(price_series(0.0, 0.021, seed=seed)).t_stat)
            for seed in range(400))
        for threshold, expected in ((2.0, 0.51), (5.0, 0.16), (8.0, 0.06)):
            measured = sum(t >= threshold for t in magnitudes) / len(magnitudes)
            self.assertAlmostEqual(measured, expected, delta=0.08)

    def test_a_sideways_verdict_explains_itself(self):
        trend = merch.compute_trend(price_series(0.0008, 0.021, seed=31))
        self.assertEqual(trend.direction, merch.SIDEWAYS)
        self.assertIn("trendless", trend.verdict)


class CrashPrecedenceTests(unittest.TestCase):
    """The badge rules overlap, so their order is the specification."""

    def test_deep_and_loud_is_a_crash(self):
        signal = merch.crash_signal(-0.55, 15.0)
        self.assertEqual(signal.kind, merch.CRASH)

    def test_deep_and_quiet_is_not_a_crash(self):
        signal = merch.crash_signal(-0.40, 1.2)
        self.assertEqual(signal.kind, merch.DIPPED_STABLE)

    def test_shallow_and_loud_is_a_dip(self):
        signal = merch.crash_signal(-0.25, 2.5)
        self.assertEqual(signal.kind, merch.DIP)

    def test_high_and_thin_is_a_pump(self):
        signal = merch.crash_signal(0.30, 0.10)
        self.assertEqual(signal.kind, merch.PUMPED)
        self.assertLess(signal.score, 0)

    def test_an_ordinary_price_gets_no_badge(self):
        self.assertIsNone(merch.crash_signal(-0.02, 1.1))

    def test_nothing_fires_through_a_regime_shift(self):
        """A price level that moved because the game changed has not crashed."""
        self.assertIsNone(merch.crash_signal(-0.55, 15.0, regime_score=4.0))

    def test_missing_depth_is_not_a_signal(self):
        self.assertIsNone(merch.crash_signal(None, 15.0))

    def test_recovery_ranks_tradability_over_depth(self):
        deep_illiquid = merch.recovery_score(
            merch.crash_signal(-0.70, 5.0), fill_share=0.02)
        shallow_liquid = merch.recovery_score(
            merch.crash_signal(-0.25, 2.5), fill_share=0.90,
            mean_reverting=True)
        self.assertGreater(shallow_liquid, deep_illiquid)

    def test_a_pump_has_no_recovery_score(self):
        self.assertEqual(
            merch.recovery_score(merch.crash_signal(0.30, 0.10), 0.9), 0.0)


class RaidCycleTests(unittest.TestCase):
    ARCANE = 21079          # in both the raid list and the must-have list
    RAPIER = 22324          # raid unique, not a must-have
    BLOOD_RUNE = 565        # not a raid unique at all

    def test_only_raid_uniques_score(self):
        self.assertEqual(
            merch.raid_cycle_score(self.BLOOD_RUNE, 300, -0.9), 0.0)

    def test_supply_has_to_have_actually_dropped(self):
        self.assertEqual(
            merch.raid_cycle_score(self.ARCANE, 5_000_000, -0.10), 0.0)
        self.assertEqual(
            merch.raid_cycle_score(self.ARCANE, 5_000_000, None), 0.0)

    def test_must_have_items_outrank_optional_ones(self):
        essential = merch.raid_cycle_score(self.ARCANE, 5_000_000, -0.85)
        optional = merch.raid_cycle_score(self.RAPIER, 5_000_000, -0.85)
        self.assertGreater(essential, optional)

    def test_cheaper_items_outrank_dearer_ones_on_the_same_collapse(self):
        cheap = merch.raid_cycle_score(self.RAPIER, 5_000_000, -0.85)
        dear = merch.raid_cycle_score(self.RAPIER, 90_000_000, -0.85)
        self.assertGreater(cheap, dear)

    def test_badges_step_with_the_decline(self):
        self.assertEqual(merch.supply_crunch_badge(-0.85), merch.SUPPLY_CRUNCH)
        self.assertEqual(merch.supply_crunch_badge(-0.60), merch.SUPPLY_DROP)
        self.assertIsNone(merch.supply_crunch_badge(-0.20))
        self.assertIsNone(merch.supply_crunch_badge(None))


class ClassificationTests(unittest.TestCase):
    def test_a_cheap_high_limit_f2p_item_is_botted(self):
        self.assertTrue(merch.is_botted(15, members=False, buy_limit=13_000))

    def test_members_items_are_never_called_botted(self):
        self.assertFalse(merch.is_botted(15, members=True, buy_limit=13_000))

    def test_a_low_limit_is_not_industrial_supply(self):
        self.assertFalse(merch.is_botted(15, members=False, buy_limit=100))

    def test_an_expensive_item_is_not_bot_farmed_for_the_gp(self):
        self.assertFalse(merch.is_botted(5_000, members=False,
                                         buy_limit=13_000))

    def test_tags_are_stable_and_combine(self):
        trend = merch.compute_trend(price_series(0.002, 0.005, seed=21))
        tags = merch.classify_item(
            21079, buy_price=5_000_000, members=True, buy_limit=5, trend=trend,
            crash=merch.crash_signal(-0.55, 15.0),
            supply=merch.SUPPLY_CRUNCH)
        self.assertEqual(tags, [merch.MERCH, merch.RAID, merch.SUPPLY_CRUNCH,
                                merch.CRASH])


class WatchlistTests(unittest.TestCase):
    def test_no_duplicate_ids(self):
        ids = [item.item_id for item in merch.WATCHLIST]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_entry_has_a_thesis(self):
        for item in merch.WATCHLIST:
            self.assertTrue(item.thesis.strip(), item.item_id)

    def test_no_names_or_prices_are_hardcoded(self):
        """Names come from /mapping and prices from /latest. Both rot in a day."""
        source = (Path(__file__).parent / "merch.py").read_text(encoding="utf-8")
        watchlist = source[source.index("WATCHLIST = ("):
                           source.index("WATCHLIST_IDS")]
        self.assertNotIn("gp", watchlist.replace("gp,", ""))
        self.assertNotIn("%/yr", watchlist)

    def test_the_untradeable_leagues_variants_are_absent(self):
        """They carry no buy limit and never appear in /latest."""
        for item_id in (28534, 28540, 28545, 28549):
            self.assertNotIn(item_id, merch.RAID_UNIQUE_IDS)
            self.assertNotIn(item_id, merch.WATCHLIST_IDS)

    def test_must_haves_are_a_subset_of_the_raid_uniques(self):
        self.assertTrue(merch.PVM_MUST_HAVE_IDS <= merch.RAID_UNIQUE_IDS)


if __name__ == "__main__":
    unittest.main()
