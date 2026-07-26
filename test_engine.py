"""Unit tests for engine.py — run with: python3 -m unittest test_engine -v"""
import unittest

import engine


class TaxTests(unittest.TestCase):
    def test_30gp_item_is_untaxed(self):
        self.assertEqual(engine.ge_tax(30), 0)

    def test_49gp_is_the_last_untaxed_price(self):
        self.assertEqual(engine.ge_tax(49), 0)
        self.assertEqual(engine.ge_tax(50), 1)

    def test_1250gp_item_pays_25(self):
        self.assertEqual(engine.ge_tax(1_250), 25)

    def test_tax_rounds_down(self):
        self.assertEqual(engine.ge_tax(1_299), 25)  # 2% = 25.98

    def test_1_8b_item_hits_the_5m_cap(self):
        self.assertEqual(engine.ge_tax(1_800_000_000), 5_000_000)

    def test_cap_starts_at_250m(self):
        self.assertEqual(engine.ge_tax(250_000_000), 5_000_000)
        self.assertEqual(engine.ge_tax(249_999_999), 4_999_999)

    def test_bond_exemption(self):
        self.assertEqual(engine.ge_tax(10_000_000, tax_exempt=True), 0)


class MarginTests(unittest.TestCase):
    def test_net_margin_subtracts_tax(self):
        # buy 950, sell 1250: 1250 - 25 - 950
        self.assertEqual(engine.net_margin(950, 1_250), 275)

    def test_margin_can_go_negative_on_tax(self):
        # 1 gp spread, 2 gp tax
        self.assertEqual(engine.net_margin(100, 101), -1)

    def test_crossed_market_is_negative(self):
        self.assertEqual(engine.net_margin(120, 100), -22)

    def test_roi(self):
        self.assertAlmostEqual(engine.roi(950, 1_250), 275 / 950)


class GpParsingTests(unittest.TestCase):
    def test_plain_and_separated_numbers(self):
        self.assertEqual(engine.parse_gp("1000000"), 1_000_000)
        self.assertEqual(engine.parse_gp("1,000,000"), 1_000_000)

    def test_suffixes(self):
        self.assertEqual(engine.parse_gp("250k"), 250_000)
        self.assertEqual(engine.parse_gp("1.5m"), 1_500_000)
        self.assertEqual(engine.parse_gp("2B"), 2_000_000_000)

    def test_gp_suffix_and_spaces(self):
        self.assertEqual(engine.parse_gp(" 500k gp "), 500_000)

    def test_rejects_junk(self):
        for bad in ("", "abc", "-5", "0", "1.5", "k", "5kk"):
            with self.assertRaises(ValueError, msg=bad):
                engine.parse_gp(bad)

    def test_format_round_trip_style(self):
        self.assertEqual(engine.format_gp(250_000), "250k")
        self.assertEqual(engine.format_gp(1_500_000), "1.5m")
        self.assertEqual(engine.format_gp(2_147_483_647), "2.1b")
        self.assertEqual(engine.format_gp(999), "999")
        self.assertEqual(engine.format_gp(50_000_000), "50m")


class ReferencePriceTests(unittest.TestCase):
    def test_thin_5m_bucket_barely_moves_the_estimate(self):
        # the real Lobster case: 13 units at 34 vs 36,170 units at 58
        self.assertEqual(engine.reference_price(34, 13, 58, 36_170), 58)

    def test_busy_5m_bucket_pulls_the_estimate(self):
        # equal volume on both buckets: the midpoint
        self.assertEqual(engine.reference_price(40, 1_000, 60, 1_000), 50)

    def test_1h_alone_when_5m_is_silent(self):
        self.assertEqual(engine.reference_price(None, 0, 58, 36_170), 58)

    def test_5m_alone_when_1h_is_missing(self):
        self.assertEqual(engine.reference_price(34, 500, None, 0), 34)

    def test_zero_volume_on_both_falls_back_to_a_price(self):
        # priced at some point, nothing traded: no weighting possible
        self.assertEqual(engine.reference_price(34, 0, 58, 0), 34)
        self.assertEqual(engine.reference_price(None, 0, 58, 0), 58)

    def test_no_data_at_all(self):
        self.assertIsNone(engine.reference_price(None, 0, None, 0))


class ExecutablePriceTests(unittest.TestCase):
    def test_pessimistic_side_per_book_side(self):
        # buy at the higher of (latest low, ref low); sell at the lower of
        # (latest high, ref high) — a one-off spike cannot inflate the margin
        self.assertEqual(engine.executable_prices(100, 200, 110, 160), (110, 160))

    def test_latest_kept_when_it_is_the_pessimistic_one(self):
        self.assertEqual(engine.executable_prices(100, 200, 90, 250), (100, 200))

    def test_sides_fall_back_independently(self):
        self.assertEqual(engine.executable_prices(100, 200, 120, None), (120, 200))

    def test_latest_stands_alone_without_references(self):
        self.assertEqual(engine.executable_prices(100, 200), (100, 200))

    def test_estimates_can_cross_on_a_dead_spread(self):
        # ref low above ref high: the ROI gate downstream rejects this
        buy, sell = engine.executable_prices(100, 200, 180, 120)
        self.assertGreater(buy, sell)


class VolumeAndQtyTests(unittest.TestCase):
    def test_window_volume_uses_thin_side(self):
        self.assertEqual(engine.window_volume(120, 30, 48), 30 * 48)

    def test_window_volume_hourly_buckets(self):
        self.assertEqual(engine.window_volume(2_000, 1_600, 4), 6_400)

    def test_qty_capped_by_limit(self):
        self.assertEqual(engine.flippable_qty(100, 1_440), 100)

    def test_qty_capped_by_volume(self):
        self.assertEqual(engine.flippable_qty(100, 50), 50)

    def test_null_limit_leaves_volume_uncapped(self):
        self.assertEqual(engine.flippable_qty(None, 1_440), 1_440)

    def test_qty_capped_by_capital(self):
        self.assertEqual(engine.flippable_qty(100, 1_440, affordable=10), 10)

    def test_zero_limit_means_zero(self):
        self.assertEqual(engine.flippable_qty(0, 1_440), 0)


class FreshnessTests(unittest.TestCase):
    def test_fresh_data_keeps_full_confidence(self):
        self.assertEqual(engine.freshness(0), 1.0)

    def test_confidence_halves_at_half_life(self):
        self.assertAlmostEqual(engine.freshness(600), 0.5)


class UndercutDepthTests(unittest.TestCase):
    def test_air_rune_has_no_room_to_queue_jump(self):
        # 5/6 is a one-tick spread: improving means buying at 6 to sell at 5
        self.assertEqual(engine.undercut_depth(5, 6), 0)

    def test_wide_spread_gives_room(self):
        # Leather 173/192: bidding 180 to sell at 185 clears 2 gp after tax
        self.assertEqual(engine.undercut_depth(173, 192), 7)
        self.assertEqual(engine.net_margin(180, 185), 2)

    def test_depth_shrinks_as_the_spread_closes(self):
        self.assertGreater(engine.undercut_depth(100, 140),
                           engine.undercut_depth(100, 120))

    def test_negative_margin_has_no_depth(self):
        self.assertEqual(engine.undercut_depth(200, 100), 0)

    def test_every_step_of_depth_stays_profitable(self):
        buy, sell = 173, 192
        depth = engine.undercut_depth(buy, sell)
        self.assertGreater(engine.net_margin(buy + depth, sell - depth), 0)
        self.assertLessEqual(engine.net_margin(buy + depth + 1,
                                               sell - depth - 1), 0)

    def test_tax_exempt_item_gets_more_room(self):
        self.assertGreater(engine.undercut_depth(4_800_000, 5_000_000,
                                                 tax_exempt=True),
                           engine.undercut_depth(4_800_000, 5_000_000))


class QueueFactorTests(unittest.TestCase):
    def test_no_room_is_heavily_discounted(self):
        self.assertEqual(engine.queue_factor(0), 0.15)

    def test_more_room_captures_more_of_the_margin(self):
        self.assertLess(engine.queue_factor(1), engine.queue_factor(5))
        self.assertLess(engine.queue_factor(5), engine.queue_factor(20))

    def test_deep_room_approaches_the_full_margin(self):
        self.assertGreater(engine.queue_factor(30), 0.99)


class DriftTests(unittest.TestCase):
    def test_flat_market_is_undiscounted(self):
        self.assertEqual(engine.price_drift(100, 100), 0.0)
        self.assertEqual(engine.drift_factor(0.0), 1.0)

    def test_falling_market_penalised_harder_than_rising(self):
        self.assertLess(engine.drift_factor(-0.05), engine.drift_factor(0.05))

    def test_drift_factor_has_a_floor(self):
        self.assertEqual(engine.drift_factor(-10.0), 0.2)

    def test_missing_bucket_means_no_drift_signal(self):
        self.assertEqual(engine.price_drift(None, 100), 0.0)
        self.assertEqual(engine.price_drift(100, None), 0.0)


class ExpectedValueTests(unittest.TestCase):
    def test_every_discount_reduces_the_quoted_profit(self):
        gross = 275 * 100
        ev = engine.expected_value(275, 100, depth=8, drift=0.0, age_seconds=60)
        self.assertLess(ev, gross)
        self.assertGreater(ev, 0)

    def test_queue_room_dominates_a_thin_spread(self):
        # a 1 gp margin on 50,000 units with no undercut room, against a
        # 16 gp margin on 4,000 units with room: the second is worth more
        air_rune = engine.expected_value(1, 50_000, depth=0, drift=0.0,
                                         age_seconds=60)
        leather = engine.expected_value(16, 4_000, depth=8, drift=0.0,
                                        age_seconds=60)
        self.assertGreater(leather, air_rune)

    def test_staler_data_lowers_expected_value(self):
        fresh = engine.expected_value(100, 100, 5, 0.0, age_seconds=30)
        stale = engine.expected_value(100, 100, 5, 0.0, age_seconds=3_000)
        self.assertGreater(fresh, stale)


def bucket(avg_high=None, high_vol=0, avg_low=None, low_vol=0):
    return {"avgHighPrice": avg_high, "highPriceVolume": high_vol,
            "avgLowPrice": avg_low, "lowPriceVolume": low_vol}


def flat_history(n=56, low=40, high=42, low_vol=1_000, high_vol=1_000):
    return [bucket(high, high_vol, low, low_vol) for _ in range(n)]


class HistoryTests(unittest.TestCase):
    def test_salmon_dump_gets_almost_no_fill(self):
        # 14 days of sellers at 40; one bucket dumps 150 units at 30.
        # Buying at 31 reaches only that dumper's volume.
        points = flat_history(55) + [bucket(42, 800, 30, 150)]
        view = engine.history_view(points, buy=31, sell=41)
        # only the dump bucket's seller volume sits near the dumped price
        self.assertAlmostEqual(view.buy_fill_share, 150 / (55 * 1_000 + 150))
        self.assertEqual(view.fill_factor, engine.FILL_FLOOR)
        self.assertEqual(view.baseline_low, 40)
        self.assertLess(view.dislocation, -0.10)

    def test_flat_market_at_fair_prices_keeps_full_fill(self):
        view = engine.history_view(flat_history(), buy=40, sell=42)
        self.assertEqual(view.fill_factor, 1.0)
        self.assertAlmostEqual(view.trend, 0.0)
        self.assertEqual(view.momentum, 1.0)
        self.assertAlmostEqual(view.dislocation, 0.0)

    def test_a_rise_earns_no_bonus(self):
        # rises and pumps are indistinguishable in price data, so momentum
        # rewards nothing and only punishes decline
        rising = [bucket(100 + i, 1_000, 98 + i, 1_000) for i in range(56)]
        view = engine.history_view(rising, buy=150, sell=155)
        self.assertGreater(view.trend, 0.05)
        self.assertEqual(view.momentum, 1.0)

    def test_uptrend_quoted_at_the_band_keeps_full_fill(self):
        # fill shares are detrended: an item marching upward, quoted at its
        # usual spread around today's level, is not punished for trading
        # above last week's absolute prices — but the LEVEL factor still
        # discounts it for sitting above its own 14-day median
        growth = 1.004
        rising = [bucket(round(12_600 * growth ** (i - 55)), 1_000,
                         round(12_200 * growth ** (i - 55)), 1_000)
                  for i in range(56)]
        view = engine.history_view(rising, buy=12_200, sell=12_600)
        self.assertEqual(view.fill_factor, 1.0)
        self.assertEqual(view.momentum, 1.0)
        self.assertGreater(view.elevation, 0.05)
        self.assertLess(view.level, 1.0)

    def test_pump_is_crushed_by_the_level_factor(self):
        # 50 buckets at ~500, then a pump to 800: the median barely moves,
        # so the quote sits ~60% above it and the discount hits the floor
        calm = [bucket(510, 1_000, 490, 1_000) for _ in range(50)]
        pumped = calm + [bucket(815, 3_000, 785, 3_000) for _ in range(6)]
        view = engine.history_view(pumped, buy=785, sell=815)
        self.assertEqual(view.median_mid, 500)
        self.assertGreater(view.elevation, 0.5)
        self.assertEqual(view.level, engine.LEVEL_FLOOR)
        self.assertLessEqual(view.stability, 1.0)

    def test_stability_punishes_a_jumpy_item(self):
        # mids alternating 400/600: median 500, median swing 100 = 20%
        jumpy = [bucket(610, 1_000, 590, 1_000) if i % 2 else
                 bucket(410, 1_000, 390, 1_000) for i in range(56)]
        view = engine.history_view(jumpy, buy=490, sell=510)
        self.assertAlmostEqual(view.volatility, 0.2)
        self.assertEqual(view.stability, engine.STABILITY_FLOOR)

    def test_calm_item_at_its_median_keeps_both_factors(self):
        view = engine.history_view(flat_history(), buy=40, sell=42)
        self.assertEqual(view.level, 1.0)
        self.assertEqual(view.stability, 1.0)
        self.assertEqual(view.median_mid, 41)

    def test_below_median_is_not_penalised(self):
        # buying under the normal level is where a flipper wants to be
        self.assertEqual(engine.level_factor(-0.15), 1.0)

    def test_downtrend_penalised_harder(self):
        up = engine.momentum_factor(0.05)
        down = engine.momentum_factor(-0.05)
        self.assertGreater(1.0 - down, up - 1.0)
        self.assertEqual(engine.momentum_factor(-1.0), 0.5)

    def test_sparse_history_refuses_to_judge(self):
        self.assertIsNone(engine.history_view(flat_history(5), 40, 42))
        self.assertIsNone(engine.history_view([], 40, 42))

    def test_null_buckets_are_skipped_not_fatal(self):
        points = flat_history(30) + [bucket()] * 26
        view = engine.history_view(points, buy=40, sell=42)
        self.assertEqual(view.buckets, 30)

    def test_only_last_14_days_count(self):
        # 100 ancient buckets at 10 gp, then 56 recent at 40: the window
        # slices to the recent ones, so cheap ancient volume is invisible
        ancient = [bucket(12, 1_000, 10, 1_000) for _ in range(100)]
        view = engine.history_view(ancient + flat_history(56), buy=11, sell=41)
        self.assertAlmostEqual(view.buy_fill_share, 0.0)


class SlotTests(unittest.TestCase):
    def test_gp_per_slot_hour_spreads_over_the_window(self):
        self.assertEqual(engine.gp_per_slot_hour(40_000), 10_000)

    def test_capital_splits_across_slots(self):
        self.assertEqual(engine.capital_per_slot(3_000_000, 3), 1_000_000)
        self.assertEqual(engine.capital_per_slot(1_000_000, 8), 125_000)

    def test_capital_per_slot_never_zero(self):
        self.assertEqual(engine.capital_per_slot(2, 8), 1)
        self.assertEqual(engine.capital_per_slot(1_000, 0), 1_000)


if __name__ == "__main__":
    unittest.main()
