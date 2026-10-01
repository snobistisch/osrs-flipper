"""Fill-time distribution: ETA bands, completion odds, sizing and calibration.

The regression these guard against: the displayed ETA was qty / mean rate,
which the model's own rate distribution beats only about a third of the time,
while p_fill came from a different calculation and the ranking divided by yet
another. A "69 minute" flip could have a four-hour P90.
"""
import math
import random
import unittest

import engine
import filters
import journal
from api import Activity, Item, Quote

CAL = engine.DEFAULT_CALIBRATION
HOUR = engine.SECONDS_PER_HOUR
NOW = 1_785_000_000          # a Sunday, away from the weekly update
NO_EXEMPTIONS = frozenset()


def score(**overrides):
    values = dict(buy=1_000, sell=1_080, margin=58, qty=200, depth=0,
                  buy_volume_1h=2_000.0, sell_volume_1h=2_000.0,
                  quote_age=60, ofi=0.0, drift=0.0, now=NOW,
                  buy_share=0.125, sell_share=0.125)
    values.update(overrides)
    return engine.score_flip(**values)


def pipeline_row(buy, sell, limit, volume, capital=10_000_000):
    items = {1: Item(id=1, name="Test item", members=True, limit=limit,
                     value=buy, highalch=None)}
    quotes = {1: Quote(high=sell, high_time=NOW - 30, low=buy,
                       low_time=NOW - 30)}
    five = {1: Activity(avg_high=sell, high_volume=max(1, volume // 12),
                        avg_low=buy, low_volume=max(1, volume // 12))}
    hour = {1: Activity(avg_high=sell, high_volume=volume, avg_low=buy,
                        low_volume=volume)}
    config = filters.FilterConfig(capital=capital)
    screened = filters.screen(items, quotes, five, hour, config, NOW,
                              NO_EXEMPTIONS)
    return filters.allocate(screened, config).rows[0], config


class DistributionPrimitiveTests(unittest.TestCase):
    def test_normal_quantile_matches_known_values(self):
        for p, z in ((0.5, 0.0), (0.8, 0.8416212335729143),
                     (0.9, 1.2815515655446004), (0.975, 1.959963984540054),
                     (0.01, -2.3263478740408408)):
            self.assertAlmostEqual(engine.normal_quantile(p), z, places=7)

    def test_mean_rate_time_is_beaten_only_a_third_of_the_time(self):
        """The root cause, stated as a test: qty / rate is not a median."""
        work = 3_600.0
        sigma = engine.fill_log_sigma(verified=True)
        mu = engine.fill_log_mu()
        p50 = engine.fill_time_quantile(work, 0.5, sigma, 0.0, mu)
        self.assertGreater(p50, work)
        # P(work / M <= work) = P(M >= 1)
        beaten = engine.fill_estimate(1.0, 1.0 / work, work, CAL,
                                      sigma, mu).p_complete
        self.assertLess(beaten, 0.40)

    def test_p50_p80_p90_are_ordered_and_follow_the_width(self):
        sigma = engine.fill_log_sigma(verified=True)
        mu = engine.fill_log_mu()
        p50, p80, p90 = (engine.fill_time_quantile(1_800, p, sigma, 0, mu)
                         for p in engine.ETA_PERCENTILES)
        self.assertLess(p50, p80)
        self.assertLess(p80, p90)
        self.assertAlmostEqual(p80 / p50, math.exp(
            sigma * engine.normal_quantile(0.8)), places=9)
        self.assertAlmostEqual(p90 / p50, math.exp(
            sigma * engine.normal_quantile(0.9)), places=9)

    def test_percentiles_are_the_inverse_of_completion_probability(self):
        """ETA and p_fill must come from one distribution."""
        sigma, mu, rate, qty = 1.1, engine.fill_log_mu(), 0.05, 300.0
        for p in (0.5, 0.8, 0.9):
            t = engine.fill_time_quantile(qty / rate, p, sigma, 0.0, mu)
            done = engine.fill_estimate(qty, rate, t, CAL, sigma, mu)
            self.assertAlmostEqual(done.p_complete, p, places=6)

    def test_less_evidence_means_a_wider_band(self):
        verified = engine.fill_log_sigma(verified=True)
        unverified = engine.fill_log_sigma(verified=False)
        self.assertGreater(unverified, verified)
        self.assertGreater(verified, CAL.fill_rate_log_sigma)

    def test_occupancy_is_capped_by_the_deadline(self):
        sigma, mu = 1.0, engine.fill_log_mu()
        quick = engine.expected_occupancy_seconds(60, 4 * HOUR, sigma, 120, mu)
        hopeless = engine.expected_occupancy_seconds(1e9, 4 * HOUR, sigma,
                                                     120, mu)
        self.assertLess(quick, 15 * 60)
        self.assertAlmostEqual(hopeless, 4 * HOUR, delta=1.0)
        self.assertEqual(engine.expected_occupancy_seconds(
            float("inf"), 4 * HOUR, sigma, 120, mu), 4 * HOUR)

    def test_target_quantity_completes_with_the_target_probability(self):
        sigma, mu = engine.fill_log_sigma(), engine.fill_log_mu()
        rate, usable = 0.5, 4 * HOUR - 120
        qty = engine.target_quantity(rate, usable, 0.8, sigma, mu)
        self.assertGreater(qty, 0)
        at = engine.fill_estimate(qty, rate, usable, CAL, sigma, mu)
        above = engine.fill_estimate(qty * 1.05 + 1, rate, usable, CAL,
                                     sigma, mu)
        self.assertGreaterEqual(at.p_complete, 0.8 - 1e-9)
        self.assertLess(above.p_complete, 0.8)


class ScoreFlipTimingTests(unittest.TestCase):
    def test_thin_market_has_a_long_tail_and_low_completion(self):
        thin = score(qty=5, buy_volume_1h=6.0, sell_volume_1h=6.0,
                     buy_share=0.125, sell_share=0.125)
        self.assertGreater(thin.round_trip_p90_seconds,
                           2.5 * thin.round_trip_p50_seconds)
        self.assertGreater(thin.round_trip_p90_seconds, 4 * HOUR)
        self.assertLess(thin.p_fill_both, CAL.active_target_completion)

    def test_busy_market_queue_delay_is_bound_by_the_crowd(self):
        """A crowded touch fills one buy limit per window however busy it is."""
        volume, limit = 1_681_042.0, 50_000
        crowd = engine.touch_competitors(volume, limit)
        busy = engine.score_flip(
            buy=5, sell=6, margin=1, qty=limit, depth=0,
            buy_volume_1h=volume, sell_volume_1h=volume, quote_age=10,
            ofi=0.0, drift=0.0, now=NOW, competitors=crowd)
        quiet = engine.score_flip(
            buy=5, sell=6, margin=1, qty=limit, depth=0,
            buy_volume_1h=volume, sell_volume_1h=volume, quote_age=10,
            ofi=0.0, drift=0.0, now=NOW)
        self.assertGreater(busy.round_trip_p50_seconds,
                           10 * quiet.round_trip_p50_seconds)
        # A full limit per leg takes the whole window at the mean rate, so
        # even the median round trip is well past it.
        self.assertGreater(busy.round_trip_p50_seconds, engine.WINDOW_HOURS * HOUR)
        self.assertLess(busy.p_fill_both, 0.5)
        self.assertEqual(busy.reprice_check_seconds,
                         CAL.reprice_check_max_minutes * 60)

    def test_sequential_legs_add_and_bind_completion(self):
        both = score(qty=400)
        self.assertAlmostEqual(
            both.round_trip_p50_seconds,
            both.buy_seconds + both.sell_seconds, places=6)
        self.assertLessEqual(both.p_fill_both, both.p_fill_buy + 1e-12)
        self.assertLessEqual(both.p_fill_both, both.p_fill_sell + 1e-12)
        self.assertLessEqual(both.expected_sell_qty, both.expected_buy_qty)
        # A slow sell leg holds the round trip back even if the buy is instant.
        slow_sell = score(qty=400, buy_volume_1h=200_000.0,
                          sell_volume_1h=150.0)
        self.assertGreater(slow_sell.p_fill_buy, 0.95)
        self.assertLess(slow_sell.p_fill_both, both.p_fill_both)
        self.assertGreater(slow_sell.p_stranded, 0)

    def test_larger_quantities_never_look_faster(self):
        previous = None
        for qty in (1, 10, 50, 200, 800, 3_000):
            result = score(qty=qty)
            if previous is not None:
                for name in ("round_trip_p50_seconds", "round_trip_p80_seconds",
                             "round_trip_p90_seconds",
                             "expected_occupancy_seconds",
                             "reprice_check_seconds"):
                    self.assertGreaterEqual(getattr(result, name),
                                            getattr(previous, name), name)
                self.assertLessEqual(result.p_fill_both,
                                     previous.p_fill_both + 1e-12)
            previous = result

    def test_lower_completion_odds_rank_lower(self):
        liquid = score(qty=100, buy_volume_1h=4_000.0, sell_volume_1h=4_000.0)
        sluggish = score(qty=100, buy_volume_1h=150.0, sell_volume_1h=150.0)
        self.assertLess(sluggish.p_fill_both, liquid.p_fill_both)
        self.assertLess(sluggish.ranking_value, liquid.ranking_value)

    def test_ranking_divides_expected_profit_by_expected_occupancy(self):
        result = score(qty=300)
        self.assertAlmostEqual(
            result.gp_per_slot_hour,
            result.expected_profit / (result.expected_occupancy_seconds / HOUR),
            places=6)

    def test_overnight_keeps_its_own_meaning(self):
        night = score(mode=engine.TradeMode.OVERNIGHT, horizon_hours=8,
                      qty=2_000, buy_volume_1h=500.0, sell_volume_1h=100.0)
        self.assertEqual(night.p_fill_both, night.p_fill_buy)
        self.assertGreater(night.round_trip_p90_seconds,
                           night.round_trip_p50_seconds)


class PipelineConsistencyTests(unittest.TestCase):
    def test_eta_p_fill_ranking_and_funded_quantity_agree(self):
        row, config = pipeline_row(1_000, 1_060, 10_000, 5_000)
        self.assertGreater(row.allocated_quantity or 0, 0)
        qty = row.allocated_quantity
        self.assertEqual(row.qty_per_window, qty)
        self.assertEqual(row.capital_needed, qty * (row.buy + row.bond_fee))
        buy_rate = engine.fill_rate(row.model_buy_volume_1h, row.buy_share)
        sell_rate = engine.fill_rate(row.model_sell_volume_1h, row.sell_share)
        sigma, mu = row.fill_log_sigma, engine.fill_log_mu()
        overhead = 2 * CAL.min_leg_seconds
        work = qty / buy_rate + qty / sell_rate
        # The shown band is the funded quantity's band ...
        self.assertAlmostEqual(row.round_trip_p50_seconds, engine.fill_time_quantile(
            work, 0.5, sigma, overhead, mu), places=4)
        self.assertAlmostEqual(row.expected_total_seconds,
                               row.round_trip_p50_seconds, places=4)
        # ... p_fill is the same distribution evaluated at the deadline ...
        deadline = row.horizon_hours * HOUR
        self.assertAlmostEqual(row.p_fill, engine.fill_estimate(
            qty, engine.round_trip_rate(buy_rate, sell_rate),
            deadline - overhead, CAL, sigma, mu).p_complete, places=9)
        self.assertGreaterEqual(row.p_fill + 1e-9,
                                CAL.active_target_completion)
        self.assertLessEqual(row.round_trip_p80_seconds, deadline + 1e-6)
        # ... and the ranking divides by that distribution's occupancy.
        self.assertAlmostEqual(
            row.raw_gp_per_slot_hour,
            row.expected_gp / (row.expected_occupancy_seconds / HOUR),
            places=6)
        self.assertEqual(row.allocated_expected_gp, row.expected_gp)

    def test_fast_liquid_flips_still_look_fast(self):
        # Capital, not the market, binds: a small order on a deep book.
        row, _ = pipeline_row(100_000, 103_000, 100, 2_000,
                              capital=1_000_000)
        self.assertLessEqual(row.allocated_quantity, 10)
        cheap, _ = pipeline_row(20, 24, 25_000, 400_000, capital=4_000)
        for fast in (cheap,):
            self.assertLess(fast.round_trip_p50_seconds, 20 * 60)
            self.assertLess(fast.round_trip_p90_seconds, HOUR)
            self.assertGreater(fast.p_fill, 0.95)
            self.assertLess(fast.reprice_check_seconds, 20 * 60)

    def test_unverified_rows_get_a_wider_band_than_deep_checked_ones(self):
        row, _ = pipeline_row(1_000, 1_060, 10_000, 5_000)
        self.assertAlmostEqual(row.fill_log_sigma,
                               engine.fill_log_sigma(verified=False))

    def test_a_row_below_the_target_is_listed_but_never_funded(self):
        row, _ = pipeline_row(200_000, 215_000, 8, 3)
        self.assertLess(row.p_fill, CAL.active_target_completion)
        self.assertFalse(row.allocated_quantity)
        self.assertTrue(any(note.startswith("fill odds:")
                            for note in row.warnings))


class CensoredCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.j = journal.Journal(":memory:")

    def tearDown(self):
        self.j.close()

    def prediction(self, buy=600.0, sell=600.0, sigma=1.0):
        from types import SimpleNamespace
        return SimpleNamespace(
            item_id=1, margin=10, buy=100, sell=115, expected_gp=1_000,
            gp_per_slot_hour=500, expected_buy_seconds=buy,
            expected_sell_seconds=sell, p_fill=0.8,
            trade_mode=engine.TradeMode.ACTIVE, horizon_hours=4,
            ranking_value=500, p_stranded=0.0, downside_risk_gp=0.0,
            tax_exempt=False, factors={}, fill_log_sigma=sigma,
            round_trip_p50_seconds=buy + sell, round_trip_p80_seconds=0,
            round_trip_p90_seconds=0, reprice_check_seconds=900,
            thin_volume_1h=500, competitors=8.0)

    def test_a_cancelled_offer_is_not_ignored(self):
        start = 1_000_000
        for index in range(4):
            flip = self.j.place_offer("Item", 10, 100, placed_at=start,
                                      row=self.prediction())
            self.j.mark_bought(flip, filled_at=start + 500 + index)
        never = self.j.place_offer("Item", 10, 100, placed_at=start,
                                   row=self.prediction())
        self.j.cancel_flip(never, "never filled", cancelled_at=start + 9_000)
        still = self.j.place_offer("Item", 10, 100, placed_at=start,
                                   row=self.prediction())
        summary = {(r["leg"], r["tier"]): r for r in
                   self.j.fill_time_backtest(now=start + 12_000)}
        buy = summary[("buy", "all")]
        self.assertEqual(buy["n"], 6)
        self.assertEqual(buy["censored"], 2)
        self.assertEqual(buy["never_filled"], 1)
        # Completed-only, the buys look quicker than predicted. With the two
        # offers that sat for hours, the honest median is slower.
        self.assertLess(buy["median_realised_completed"], 600)
        self.assertGreater(buy["km_median_realised_over_predicted"],
                           buy["median_realised_completed"] / 600)
        # Both long waits are past the predicted P90 and are counted as such.
        self.assertGreaterEqual(buy["p90_exceedance"], 2 / 6)
        self.assertIsNotNone(still)

    def test_open_and_cancelled_sells_are_censored_sell_legs(self):
        start = 2_000_000
        flip = self.j.place_offer("Item", 5, 100, placed_at=start,
                                  row=self.prediction())
        self.j.mark_bought(flip, filled_at=start + 300)
        self.j.cancel_flip(flip, "margin gone", cancelled_at=start + 20_000)
        summary = {(r["leg"], r["tier"]): r for r in
                   self.j.fill_time_backtest(now=start + 30_000)}
        self.assertEqual(summary[("sell", "all")]["censored"], 1)
        self.assertEqual(summary[("round_trip", "all")]["never_filled"], 1)

    def test_backtest_is_calibrated_when_reality_follows_the_model(self):
        rng = random.Random(7)
        sigma, mu = 1.0, engine.fill_log_mu()
        observations = []
        for _ in range(400):
            work = rng.uniform(300, 3_000)
            p50 = engine.fill_time_quantile(work, 0.5, sigma,
                                            CAL.min_leg_seconds, mu)
            realised = CAL.min_leg_seconds + work / math.exp(
                rng.gauss(mu, sigma))
            patience = rng.uniform(2, 6) * p50     # players give up
            censored = realised > patience
            observations.append(journal.FillObservation(
                "buy", p50, sigma, min(realised, patience), censored,
                censored, "liquid"))
        row = next(r for r in journal.backtest_summary(observations)
                   if r["tier"] == "all")
        self.assertAlmostEqual(row["km_median_realised_over_predicted"], 1.0,
                               delta=0.15)
        self.assertAlmostEqual(row["p80_exceedance"], 0.20, delta=0.06)
        self.assertAlmostEqual(row["p90_exceedance"], 0.10, delta=0.05)
        self.assertAlmostEqual(row["fitted_log_bias"], 0.0, delta=0.15)
        self.assertAlmostEqual(row["fitted_sigma"], sigma, delta=0.15)

    def test_backtest_detects_an_optimistic_model(self):
        rng = random.Random(11)
        observations = []
        for _ in range(200):
            p50 = 1_200.0
            realised = CAL.min_leg_seconds + 3 * (p50 - CAL.min_leg_seconds) \
                * math.exp(rng.gauss(0, 1.0))
            observations.append(journal.FillObservation(
                "round_trip", p50, 0.6, realised, False, False, "busy"))
        row = next(r for r in journal.backtest_summary(observations)
                   if r["tier"] == "all")
        self.assertLess(row["predicted_over_realised"], 0.5)
        self.assertGreater(row["p90_exceedance"], 0.3)
        self.assertGreater(row["fitted_log_bias"], 0.8)
        self.assertGreater(row["fitted_sigma"], 0.8)

    def test_kaplan_meier_uses_censoring(self):
        self.assertEqual(journal.kaplan_meier_median(
            [(1, False), (2, False), (3, False)]), 2)
        # Two of four only got as far as 1.5: the median cannot be 1.
        self.assertEqual(journal.kaplan_meier_median(
            [(1, False), (1.5, True), (1.5, True), (4, False)]), 4)
        self.assertIsNone(journal.kaplan_meier_median(
            [(1, True), (2, True)]))


if __name__ == "__main__":
    unittest.main()
