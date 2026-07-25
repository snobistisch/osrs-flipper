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


class ExecutablePriceTests(unittest.TestCase):
    def test_conservative_blend_with_5m_averages(self):
        # buy at the higher of (latest low, avg low); sell at the lower of
        # (latest high, avg high) — a one-off spike cannot inflate the margin
        self.assertEqual(
            engine.executable_prices(100, 200, avg_low_5m=110, avg_high_5m=160,
                                     avg_low_1h=90, avg_high_1h=150),
            (110, 160))

    def test_1h_average_fills_a_silent_5m_bucket(self):
        self.assertEqual(
            engine.executable_prices(100, 200, avg_low_5m=None, avg_high_5m=None,
                                     avg_low_1h=90, avg_high_1h=150),
            (100, 150))

    def test_sides_fall_back_independently(self):
        self.assertEqual(
            engine.executable_prices(100, 200, avg_low_5m=120, avg_high_5m=None,
                                     avg_low_1h=90, avg_high_1h=150),
            (120, 150))

    def test_latest_stands_alone_without_averages(self):
        self.assertEqual(engine.executable_prices(100, 200), (100, 200))

    def test_estimates_can_cross_on_a_dead_spread(self):
        # avg low above avg high: the ROI gate downstream rejects this
        buy, sell = engine.executable_prices(100, 200, avg_low_5m=180,
                                             avg_high_5m=120)
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


class ScoreTests(unittest.TestCase):
    def test_fresh_data_keeps_full_confidence(self):
        self.assertEqual(engine.freshness(0), 1.0)

    def test_confidence_halves_at_half_life(self):
        self.assertAlmostEqual(engine.freshness(600), 0.5)

    def test_staler_data_scores_lower(self):
        fresh = engine.score(10_000, age_seconds=30)
        stale = engine.score(10_000, age_seconds=3_000)
        self.assertGreater(fresh, stale)


if __name__ == "__main__":
    unittest.main()
