"""Unit tests for engine.py — run with: python3 -m unittest test_engine -v"""
import calendar
import math
import unittest

import engine
import stats

CAL = engine.DEFAULT_CALIBRATION
HOUR = engine.SECONDS_PER_HOUR


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

    def test_exempt_items_pay_nothing(self):
        self.assertEqual(engine.ge_tax(10_000_000, tax_exempt=True), 0)


class MarginTests(unittest.TestCase):
    def test_net_margin_subtracts_tax(self):
        # buy 950, sell 1250: 1250 - 25 - 950
        self.assertEqual(engine.net_margin(950, 1_250), 275)

    def test_margin_can_go_negative_on_tax(self):
        self.assertEqual(engine.net_margin(100, 101), -1)

    def test_roi_is_margin_over_capital(self):
        self.assertAlmostEqual(engine.roi(950, 1_250), 275 / 950)

    def test_roi_of_a_zero_price_does_not_divide_by_zero(self):
        self.assertEqual(engine.roi(0, 100), 0.0)


class TaxBoundaryTests(unittest.TestCase):
    """The tax rounds down, so net revenue is a staircase with 50 gp treads."""

    def test_undercutting_a_multiple_of_50_is_free(self):
        self.assertEqual(engine.net_revenue(100), engine.net_revenue(99))
        self.assertEqual(engine.tax_boundary_undercut(100), 99)

    def test_already_at_the_bottom_of_the_band(self):
        # 99 nets 98; 98 nets 97, so 99 cannot be improved on for free.
        self.assertEqual(engine.tax_boundary_undercut(99), 99)

    def test_a_full_band_is_walked(self):
        self.assertEqual(engine.net_revenue(1_000), 980)
        self.assertEqual(engine.net_revenue(999), 980)
        self.assertEqual(engine.tax_boundary_undercut(1_000), 999)

    def test_exempt_items_have_no_boundary_to_exploit(self):
        self.assertEqual(engine.tax_boundary_undercut(1_000, tax_exempt=True),
                         1_000)

    def test_never_returns_a_worse_price(self):
        for price in range(1, 600):
            listed = engine.tax_boundary_undercut(price)
            self.assertLessEqual(listed, price)
            self.assertGreaterEqual(engine.net_revenue(listed),
                                    engine.net_revenue(price))


class BreakEvenTests(unittest.TestCase):
    def test_break_even_clears_exactly_one_gp(self):
        for buy in (50, 100, 500, 1_000, 10_000, 100_000, 1_000_000):
            sell = engine.break_even_sell(buy)
            self.assertGreater(engine.net_margin(buy, sell), 0, buy)
            self.assertLessEqual(engine.net_margin(buy, sell - 1), 0, buy)

    def test_exempt_items_break_even_one_gp_up(self):
        self.assertEqual(engine.break_even_sell(1_000, tax_exempt=True), 1_001)


class UndercutDepthTests(unittest.TestCase):
    def test_air_rune_one_tick_spread_has_no_room(self):
        self.assertEqual(engine.undercut_depth(5, 6), 0)

    def test_leather_has_room_to_pay_for_priority(self):
        self.assertEqual(engine.undercut_depth(173, 192), 7)

    def test_depth_is_the_largest_profitable_improvement(self):
        depth = engine.undercut_depth(173, 192)
        self.assertGreater(engine.net_margin(173 + depth, 192 - depth), 0)
        self.assertLessEqual(engine.net_margin(173 + depth + 1,
                                               192 - depth - 1), 0)

    def test_unprofitable_spread_has_no_room(self):
        self.assertEqual(engine.undercut_depth(100, 101), 0)


class AggressivenessTests(unittest.TestCase):
    def test_no_room_leaves_you_at_your_queue_share(self):
        share = engine.aggressiveness(0.0, CAL)
        self.assertAlmostEqual(share, 1.0 / CAL.competitors_at_touch)

    def test_conceding_the_whole_spread_takes_almost_everything(self):
        self.assertGreater(engine.aggressiveness(1.0, CAL), 0.9)

    def test_share_rises_with_room_and_is_bounded(self):
        previous = 0.0
        for edge in (0.0, 0.1, 0.25, 0.5, 1.0, 5.0):
            share = engine.aggressiveness(edge, CAL)
            self.assertGreaterEqual(share, previous)
            self.assertLessEqual(share, 1.0)
            previous = share

    def test_edge_is_measured_against_the_spread_not_the_price(self):
        # 2 gp of room out of a 4 gp spread is the same queue position whether
        # the item costs 50 gp or 50,000 — which a fraction-of-price version
        # and the old fixed-gp constant both got wrong.
        self.assertAlmostEqual(engine.price_edge(2, 4), 0.5)
        self.assertEqual(engine.price_edge(2, 0), 0.0)


class FillModelTests(unittest.TestCase):
    def test_fill_rate_scales_with_volume_and_share(self):
        self.assertAlmostEqual(engine.fill_rate(3_600, 1.0), 1.0)
        self.assertAlmostEqual(engine.fill_rate(3_600, 0.25), 0.25)
        self.assertEqual(engine.fill_rate(0, 1.0), 0.0)

    def test_expected_fill_time_is_quantity_over_rate(self):
        self.assertAlmostEqual(engine.expected_fill_seconds(1_000, 1.0, CAL),
                               1_000.0)

    def test_a_tiny_offer_still_costs_a_minimum_of_human_time(self):
        self.assertEqual(engine.expected_fill_seconds(1, 1_000.0, CAL),
                         CAL.min_leg_seconds)

    def test_no_volume_means_never(self):
        self.assertEqual(engine.expected_fill_seconds(10, 0.0, CAL),
                         float("inf"))

    def test_fill_probability_is_exponential(self):
        # At exactly the mean fill time, an exponential has cleared 1 - 1/e.
        self.assertAlmostEqual(engine.fill_probability(3_600, 3_600),
                               1 - math.exp(-1), places=9)
        self.assertEqual(engine.fill_probability(float("inf"), 3_600), 0.0)
        self.assertEqual(engine.fill_probability(600, 0), 0.0)

    def test_fillable_quantity_uses_the_rate_not_a_flat_multiple(self):
        # 1,000 units/h at full queue share over 4h is 4,000 units — but at a
        # quarter share it is 1,000, which the old "volume x 4" ignored.
        self.assertEqual(engine.fillable_quantity(1_000, 1.0, 4), 4_000)
        self.assertEqual(engine.fillable_quantity(1_000, 0.25, 4), 1_000)

    def test_flippable_qty_takes_the_binding_cap(self):
        self.assertEqual(engine.flippable_qty(100, 5_000, 4_000), 100)
        self.assertEqual(engine.flippable_qty(None, 5_000, 4_000), 4_000)
        self.assertEqual(engine.flippable_qty(None, 5_000, None), 5_000)


class AdverseSelectionTests(unittest.TestCase):
    def test_balanced_flow_and_flat_price_is_no_discount(self):
        self.assertAlmostEqual(
            engine.adverse_selection_factor(0.0, 0.0, CAL), 1.0)

    def test_seller_pressure_is_penalised(self):
        self.assertLess(engine.adverse_selection_factor(-0.8, 0.0, CAL), 1.0)

    def test_buyer_pressure_is_not_a_bonus(self):
        self.assertLessEqual(
            engine.adverse_selection_factor(0.8, 0.0, CAL), 1.0)

    def test_falling_prices_hurt_more_than_rising_ones(self):
        falling = engine.adverse_selection_factor(0.0, -0.01, CAL)
        rising = engine.adverse_selection_factor(0.0, 0.01, CAL)
        self.assertLess(falling, rising)

    def test_discount_has_a_floor(self):
        self.assertGreaterEqual(
            engine.adverse_selection_factor(-1.0, -1.0, CAL),
            CAL.adverse_selection_floor)

    def test_order_flow_imbalance(self):
        self.assertAlmostEqual(engine.order_flow_imbalance(100, 100), 0.0)
        self.assertAlmostEqual(engine.order_flow_imbalance(100, 0), 1.0)
        self.assertAlmostEqual(engine.order_flow_imbalance(0, 100), -1.0)
        self.assertEqual(engine.order_flow_imbalance(0, 0), 0.0)


class RiskOverTimeTests(unittest.TestCase):
    def test_holding_longer_costs_more(self):
        short = engine.holding_risk(0.1, 600, CAL)
        long_hold = engine.holding_risk(0.1, 6 * HOUR, CAL)
        self.assertGreater(short, long_hold)

    def test_more_volatile_costs_more(self):
        calm = engine.holding_risk(0.02, HOUR, CAL)
        wild = engine.holding_risk(0.40, HOUR, CAL)
        self.assertGreater(calm, wild)

    def test_no_volatility_no_discount(self):
        self.assertEqual(engine.holding_risk(0.0, HOUR, CAL), 1.0)

    def test_never_filling_is_worth_nothing(self):
        self.assertEqual(engine.holding_risk(0.1, float("inf"), CAL), 0.0)

    def test_staleness_depends_on_the_items_own_volatility(self):
        # The point of replacing the fixed 600s half-life: the same
        # 20-minute-old quote means different things on different items.
        calm = engine.staleness_factor(1_200, 0.01, CAL)
        wild = engine.staleness_factor(1_200, 0.50, CAL)
        self.assertGreater(calm, wild)
        self.assertGreater(calm, 0.98)

    def test_a_fresh_quote_is_undiscounted(self):
        self.assertEqual(engine.staleness_factor(0, 0.2, CAL), 1.0)


class MeanReversionTests(unittest.TestCase):
    def reverting(self, level_gp):
        return stats.OUFit(kappa=2.0, mu=math.log(level_gp), sigma=0.05,
                           t_stat=-5.0, n=100, dt_days=0.25)

    def test_buying_below_the_long_run_level_is_a_bonus(self):
        factor = engine.mean_reversion_factor(
            self.reverting(1_000), 800.0, 4 * HOUR, 0.0, CAL)
        self.assertGreater(factor, 1.0)

    def test_buying_above_the_long_run_level_is_a_penalty(self):
        factor = engine.mean_reversion_factor(
            self.reverting(1_000), 1_300.0, 4 * HOUR, 0.0, CAL)
        self.assertLess(factor, 1.0)

    def test_the_adjustment_is_capped(self):
        factor = engine.mean_reversion_factor(
            self.reverting(1_000_000), 1.0, 4 * HOUR, 0.0, CAL)
        self.assertLessEqual(factor, 1.0 + CAL.mean_reversion_cap)

    def test_a_regime_shift_suspends_the_model(self):
        # An update re-priced the item: its pre-update mean is not a target.
        factor = engine.mean_reversion_factor(
            self.reverting(1_000), 800.0, 4 * HOUR,
            CAL.regime_shift_threshold + 1, CAL)
        self.assertEqual(factor, 1.0)

    def test_no_fit_is_neutral(self):
        self.assertEqual(
            engine.mean_reversion_factor(None, 100.0, HOUR, 0.0, CAL), 1.0)

    def test_a_trending_item_is_not_pulled_to_its_median(self):
        # Rare gear trends; "above its 14-day median" is its normal state, and
        # the old universal level penalty punished it for that every time.
        trending = stats.OUFit(kappa=-0.5, mu=math.log(1_000), sigma=0.05,
                               t_stat=1.2, n=100, dt_days=0.25)
        self.assertFalse(trending.mean_reverting)
        factor = engine.mean_reversion_factor(trending, 1_300.0, 4 * HOUR,
                                              0.0, CAL)
        self.assertGreater(factor, 0.9)


class AlchemyTests(unittest.TestCase):
    def test_floor_is_alch_value_minus_the_rune(self):
        self.assertEqual(engine.alch_floor(630, 150), 480)
        self.assertIsNone(engine.alch_floor(None, 150))

    def test_trading_below_the_floor_is_an_arbitrage(self):
        distance = engine.alch_distance(400, engine.alch_floor(630, 150))
        self.assertLess(distance, 0)

    def test_profit_from_alching(self):
        self.assertEqual(engine.alch_profit(630, 400, 150), 80)
        self.assertIsNone(engine.alch_profit(None, 400, 150))

    def test_a_floor_far_below_the_price_is_no_protection(self):
        distance = engine.alch_distance(10_000, 100)
        self.assertEqual(engine.alch_bonus(distance, CAL), 1.0)

    def test_a_nearby_floor_earns_a_bonus(self):
        near = engine.alch_bonus(0.05, CAL)
        far = engine.alch_bonus(0.35, CAL)
        self.assertGreater(near, far)
        self.assertGreaterEqual(far, 1.0)

    def test_unalchable_items_are_neutral(self):
        self.assertEqual(engine.alch_bonus(None, CAL), 1.0)


class UpdateRiskTests(unittest.TestCase):
    def wednesday(self, hour_utc):
        # 2026-07-29 is a Wednesday.
        return calendar.timegm((2026, 7, 29, hour_utc, 0, 0, 0, 0, 0))

    def test_a_flip_far_from_an_update_is_unaffected(self):
        thursday_noon = self.wednesday(11) + 25 * HOUR
        self.assertEqual(
            engine.update_risk_factor(thursday_noon, 2 * HOUR, CAL), 1.0)

    def test_a_flip_running_into_the_update_is_discounted(self):
        just_before = self.wednesday(11) - 2 * HOUR
        factor = engine.update_risk_factor(just_before, 4 * HOUR, CAL)
        self.assertLess(factor, 1.0)
        self.assertGreaterEqual(factor, 1.0 - CAL.update_risk_penalty)

    def test_a_fast_flip_before_an_update_is_less_exposed(self):
        just_before = self.wednesday(11) - 3 * HOUR
        fast = engine.update_risk_factor(just_before, 600, CAL)
        slow = engine.update_risk_factor(just_before, 6 * HOUR, CAL)
        self.assertGreater(fast, slow)

    def test_next_update_is_always_within_a_week_and_ahead(self):
        for offset in range(0, 8 * 24, 7):
            when = self.wednesday(11) + offset * HOUR
            self.assertGreater(engine.seconds_until_update(when), 0)
            self.assertLessEqual(engine.seconds_until_update(when),
                                 7 * 24 * HOUR)


class ScoreTests(unittest.TestCase):
    def score(self, **overrides):
        kwargs = dict(
            buy=200, sell=250, margin=45, qty=500, depth=20,
            buy_volume_1h=5_000, sell_volume_1h=5_000, quote_age=30,
            ofi=0.0, drift=0.0,
            now=calendar.timegm((2026, 7, 27, 12, 0, 0, 0, 0, 0)),
            calibration=CAL)
        kwargs.update(overrides)
        return engine.score_flip(**kwargs)

    def test_a_clean_flip_scores_positive(self):
        result = self.score()
        self.assertGreater(result.gp_per_slot_hour, 0)
        self.assertEqual(result.raw_profit, 45 * 500)

    def test_a_faster_flip_beats_a_bigger_one_per_slot_hour(self):
        # The headline failure of the old metric: dividing everything by four
        # hours meant it could not see that a small quick flip uses the slot
        # better than a large slow one.
        quick = self.score(margin=10, qty=100, buy_volume_1h=100_000,
                           sell_volume_1h=100_000)
        slow = self.score(margin=80, qty=100, buy_volume_1h=60,
                          sell_volume_1h=60)
        self.assertGreater(slow.raw_profit, quick.raw_profit)
        self.assertGreater(quick.gp_per_slot_hour, slow.gp_per_slot_hour)

    def test_one_sided_book_never_completes(self):
        result = self.score(sell_volume_1h=0)
        self.assertEqual(result.total_seconds, float("inf"))
        self.assertEqual(result.gp_per_slot_hour, 0.0)
        self.assertEqual(result.p_fill_both, 0.0)

    def test_no_undercut_room_slows_the_fill(self):
        with_room = self.score(depth=25)
        without = self.score(depth=0)
        self.assertGreater(without.total_seconds, with_room.total_seconds)

    def test_every_factor_is_reported_separately(self):
        factors = self.score().factors()
        for name in ("p_fill_both", "adverse_selection", "holding_risk",
                     "staleness", "mean_reversion", "alch", "update_risk"):
            self.assertIn(name, factors)

    def test_selling_pressure_lowers_the_score(self):
        calm = self.score(ofi=0.0)
        dumped = self.score(ofi=-0.9)
        self.assertLess(dumped.expected_profit, calm.expected_profit)

    def test_an_item_below_its_alch_floor_is_flagged(self):
        result = self.score(highalch=500, nature_rune_cost=100)
        self.assertEqual(result.alch_arbitrage_gp, 400 - 200)

    def test_an_item_above_its_alch_floor_is_not(self):
        self.assertIsNone(self.score(highalch=100).alch_arbitrage_gp)


class ShrinkageTests(unittest.TestCase):
    def test_thin_evidence_is_cut_harder_than_thick(self):
        raw = [50_000.0, 50_000.0] + [1_000.0] * 30
        counts = [100_000.0, 3.0] + [500.0] * 30
        result = engine.shrink_scores(raw, counts, CAL)
        self.assertGreater(result.values[0], result.values[1])
        self.assertLess(result.values[1], raw[1])

    def test_a_precise_estimate_survives_nearly_intact(self):
        raw = [8_000.0] * 40
        counts = [50_000.0] * 40
        result = engine.shrink_scores(raw, counts, CAL)
        self.assertAlmostEqual(result.values[0], 8_000.0, delta=400.0)

    def test_zero_scores_stay_zero(self):
        raw = [0.0, 0.0, 5_000.0] * 10
        counts = [10.0] * 30
        result = engine.shrink_scores(raw, counts, CAL)
        self.assertEqual(result.values[0], 0.0)
        self.assertEqual(result.edge_probability[0], 0.0)

    def test_nothing_scored(self):
        result = engine.shrink_scores([0.0, 0.0], [1.0, 1.0], CAL)
        self.assertFalse(result.applied)

    def test_order_is_kept_when_evidence_is_equal(self):
        raw = [50_000.0, 5_000.0, 500.0] * 10
        counts = [1_000.0] * 30
        result = engine.shrink_scores(raw, counts, CAL)
        self.assertGreater(result.values[0], result.values[1])
        self.assertGreater(result.values[1], result.values[2])

    def test_differences_smaller_than_the_noise_are_declared_noise(self):
        # Scores within a whisker of each other, all resting on thin data:
        # the honest posterior is that none of them is distinguishable, and
        # collapsing them to the common mean says exactly that.
        raw = [1_000.0, 1_100.0, 900.0, 1_050.0] * 8
        counts = [5.0] * 32
        result = engine.shrink_scores(raw, counts, CAL)
        self.assertEqual(result.tau_squared, 0.0)
        self.assertFalse(result.informative)
        self.assertAlmostEqual(result.values[0], result.values[1], places=6)


class AllocationTests(unittest.TestCase):
    def test_capital_follows_the_scores(self):
        self.assertEqual(engine.allocate_capital([300.0, 100.0], 4_000, 2),
                         [3_000, 1_000])

    def test_a_flip_that_cannot_absorb_its_share_hands_it_back(self):
        # The exact failure of the equal split: a cheap item capped by its buy
        # limit left a third of the bank idle while a costly one was starved.
        allocation = engine.allocate_capital([100.0, 100.0], 1_000_000, 2,
                                             needs=[50_000, 5_000_000])
        self.assertEqual(allocation[0], 50_000)
        self.assertGreater(allocation[1], 500_000)
        self.assertLessEqual(sum(allocation), 1_000_000)

    def test_negative_scores_get_nothing(self):
        self.assertEqual(engine.allocate_capital([100.0, -5.0], 1_000, 2)[1], 0)

    def test_no_positive_scores_deploys_nothing(self):
        self.assertEqual(engine.allocate_capital([0.0, -1.0], 1_000, 2), [0, 0])

    def test_equal_split_is_still_available_for_the_headline(self):
        self.assertEqual(engine.capital_per_slot(999, 3), 333)
        self.assertEqual(engine.capital_per_slot(1, 8), 1)

    def test_executable_portfolio_funds_whole_items_and_leaves_bad_slots_open(self):
        amounts = engine.allocate_portfolio(
            [100.0, 50.0, -1.0], 1_000, [100, 250, 10],
            [500, 1_000, 100], 3)
        self.assertEqual(amounts[0] % 100, 0)
        self.assertEqual(amounts[1] % 250, 0)
        self.assertEqual(amounts[2], 0)
        self.assertLessEqual(sum(amounts), 1_000)


class ProfileTests(unittest.TestCase):
    def test_first_time_profile_is_members_with_eight_slots(self):
        profile = engine.TradingProfile()
        self.assertEqual(profile.account, engine.AccountType.MEMBERS)
        self.assertEqual(profile.slots, 8)
        self.assertTrue(profile.include_members)

    def test_f2p_profile_is_coherent(self):
        profile = engine.TradingProfile(account=engine.AccountType.FREE_TO_PLAY)
        self.assertEqual(profile.slots, 3)
        self.assertFalse(profile.include_members)

    def test_overnight_horizon_is_validated(self):
        with self.assertRaises(ValueError):
            engine.TradingProfile(mode=engine.TradeMode.OVERNIGHT,
                                  overnight_hours=30)


class ModeTests(unittest.TestCase):
    def score(self, **overrides):
        values = dict(
            buy=1_000, sell=1_100, margin=78, qty=10, depth=20,
            buy_volume_1h=1_000, sell_volume_1h=1_000, quote_age=0,
            ofi=0.0, drift=0.0, now=1_700_000_000,
            highalch=None, nature_rune_cost=100)
        values.update(overrides)
        return engine.score_flip(**values)

    def test_round_trip_probability_respects_sequential_legs(self):
        joint = engine.round_trip_probability(HOUR, HOUR, 2 * HOUR)
        independent = engine.fill_probability(HOUR, 2 * HOUR) ** 2
        self.assertLess(joint, independent)

    def test_active_and_overnight_rank_genuinely_different_objectives(self):
        fast_small = self.score(qty=2, margin=100, buy_volume_1h=20_000,
                                sell_volume_1h=20_000,
                                mode=engine.TradeMode.ACTIVE)
        slow_large = self.score(qty=30, margin=200, buy_volume_1h=40,
                                sell_volume_1h=40,
                                mode=engine.TradeMode.ACTIVE)
        self.assertGreater(fast_small.ranking_value,
                           slow_large.ranking_value)

        fast_night = self.score(qty=2, margin=100, buy_volume_1h=20_000,
                                sell_volume_1h=20_000,
                                mode=engine.TradeMode.OVERNIGHT,
                                horizon_hours=8)
        slow_night = self.score(qty=30, margin=200, buy_volume_1h=40,
                                sell_volume_1h=40,
                                mode=engine.TradeMode.OVERNIGHT,
                                horizon_hours=8)
        self.assertGreater(slow_night.ranking_value,
                           fast_night.ranking_value)

    def test_overnight_penalises_stranded_volatile_inventory(self):
        safe = self.score(mode=engine.TradeMode.OVERNIGHT, horizon_hours=8,
                          sigma_daily=0.02, drift=0.0, ofi=0.0)
        dangerous = self.score(mode=engine.TradeMode.OVERNIGHT,
                               horizon_hours=8, sigma_daily=0.35,
                               drift=-0.08, ofi=-0.8, margin=300,
                               qty=100, buy_volume_1h=100,
                               sell_volume_1h=100)
        self.assertGreater(dangerous.downside_risk_gp, safe.downside_risk_gp)
        self.assertLess(dangerous.ranking_value, dangerous.raw_profit)


class SlotHourTests(unittest.TestCase):
    def test_profit_over_occupied_time(self):
        self.assertAlmostEqual(engine.gp_per_slot_hour(1_000, 2 * HOUR), 500.0)

    def test_never_filling_earns_nothing(self):
        self.assertEqual(engine.gp_per_slot_hour(1_000, float("inf")), 0.0)
        self.assertEqual(engine.gp_per_slot_hour(1_000, 0), 0.0)


class HistoryTests(unittest.TestCase):
    def buckets(self, prices, volume=1_000):
        return [{"avgHighPrice": int(p * 1.02), "avgLowPrice": int(p * 0.98),
                 "highPriceVolume": volume, "lowPriceVolume": volume}
                for p in prices]

    def test_too_little_history_refuses_to_speak(self):
        self.assertIsNone(engine.history_view(self.buckets([100] * 3), 98, 102))

    def test_a_stable_item_fits_and_reports_its_level(self):
        prices = [1_000 + (i % 5) * 4 for i in range(56)]
        view = engine.history_view(self.buckets(prices), 980, 1_020)
        self.assertIsNotNone(view)
        self.assertGreater(view.buckets, 40)
        self.assertLess(abs(view.median_mid - 1_008), 40)
        self.assertLess(view.volatility, 0.05)

    def test_fill_shares_are_detrended(self):
        # A steadily rising item: prices two weeks ago were far below today's,
        # but each seller's aggressiveness relative to their own market was the
        # same throughout, so the fill share must not collapse.
        prices = [500 * (1.02 ** i) for i in range(56)]
        view = engine.history_view(self.buckets(prices),
                                   int(prices[-1] * 0.98),
                                   int(prices[-1] * 1.02))
        self.assertGreater(view.buy_fill_share, 0.5)
        self.assertGreater(view.sell_fill_share, 0.5)

    def test_a_regime_change_is_reported(self):
        view = engine.history_view(self.buckets([100] * 28 + [400] * 28),
                                   392, 408)
        self.assertGreater(view.regime_score, 4.0)
        self.assertTrue(view.regime_changed)

    def test_malformed_buckets_are_tolerated(self):
        points = self.buckets([100] * 20) + [None, {}, {"avgHighPrice": None}]
        self.assertIsNotNone(engine.history_view(points, 98, 102))


class FormattingTests(unittest.TestCase):
    def test_parse_player_shorthand(self):
        self.assertEqual(engine.parse_gp("250k"), 250_000)
        self.assertEqual(engine.parse_gp("1.5m"), 1_500_000)
        self.assertEqual(engine.parse_gp("2b"), 2_000_000_000)
        self.assertEqual(engine.parse_gp("1,000,000"), 1_000_000)
        self.assertEqual(engine.parse_gp(" 500k gp "), 500_000)

    def test_reject_nonsense(self):
        for bad in ("", "abc", "-5", "0", "1.5"):
            with self.assertRaises(ValueError, msg=bad):
                engine.parse_gp(bad)

    def test_format_reads_like_the_game(self):
        self.assertEqual(engine.format_gp(1_500_000), "1.5m")
        self.assertEqual(engine.format_gp(250_000), "250k")
        self.assertEqual(engine.format_gp(999), "999")

    def test_durations(self):
        self.assertEqual(engine.format_duration(45), "45s")
        self.assertEqual(engine.format_duration(600), "10m")
        self.assertEqual(engine.format_duration(3 * HOUR), "3h")
        self.assertEqual(engine.format_duration(float("inf")), "never")


class PriceTests(unittest.TestCase):
    def test_reference_price_weights_by_traded_volume(self):
        # A 13-unit 5m bucket must not outvote a 13,000-unit hour.
        self.assertGreater(engine.reference_price(100, 13, 200, 13_000), 190)

    def test_reference_price_with_nothing_traded(self):
        self.assertEqual(engine.reference_price(100, 0, None, 0), 100)
        self.assertIsNone(engine.reference_price(None, 0, None, 0))

    def test_executable_prices_are_pessimistic_on_both_sides(self):
        priced = engine.executable_prices(950, 1_250, ref_low=1_000,
                                          ref_high=1_200)
        self.assertEqual((priced.buy, priced.sell), (1_000, 1_200))
        self.assertFalse(priced.from_reference)


class DegenerateQuoteTests(unittest.TestCase):
    """Two prints showing no spread are not evidence that there is no spread.

    This gate used to reject 248 free-to-play items outright, 88 of which the
    volume-weighted averages showed a real spread for — salmon among them, at a
    12.5% tax-free margin. These tests pin both halves: what is now recovered,
    and what stays rejected so the recovery is not a loophole.
    """

    def test_a_crossed_print_falls_back_to_the_averages(self):
        # Salmon as it actually printed: 24/24 at the same instant, while the
        # hour's averages said 24 -> 27.
        priced = engine.executable_prices(24, 24, ref_low=24, ref_high=27)
        self.assertEqual((priced.buy, priced.sell), (24, 27))
        self.assertTrue(priced.from_reference)
        self.assertGreater(engine.net_margin(priced.buy, priced.sell, True), 0)

    def test_an_inverted_print_falls_back_too(self):
        priced = engine.executable_prices(245, 245, ref_low=247, ref_high=255)
        self.assertEqual((priced.buy, priced.sell), (247, 255))
        self.assertTrue(priced.from_reference)

    def test_contradictory_sources_stay_rejected(self):
        """Raw shrimps: 30/27 against a reference of 5/6, 81% apart. One of the
        two is about a market that no longer exists."""
        priced = engine.executable_prices(30, 27, ref_low=5, ref_high=6)
        self.assertFalse(priced.from_reference)
        self.assertLessEqual(engine.net_margin(priced.buy, priced.sell, True), 0)

    def test_a_thin_item_whose_average_rests_on_two_trades_is_rejected(self):
        """Yellow boots, 1 unit an hour: printed 1918/2013 against a reference
        of 3145/5000. A 'spread' of 59% is not a spread."""
        priced = engine.executable_prices(1918, 2013, ref_low=3145, ref_high=5000)
        self.assertFalse(priced.from_reference)

    def test_the_divergence_limit_is_where_the_line_sits(self):
        cal = engine.DEFAULT_CALIBRATION
        limit = cal.reference_fallback_max_divergence
        # A reference just inside the limit is trusted, just outside is not.
        inside = int(round(100 * (1 + limit * 0.9)))
        outside = int(round(100 * (1 + limit * 1.5)))
        self.assertTrue(engine.executable_prices(
            100, 100, ref_low=inside - 2, ref_high=inside + 2).from_reference)
        self.assertFalse(engine.executable_prices(
            100, 100, ref_low=outside - 2, ref_high=outside + 2).from_reference)

    def test_a_genuinely_spreadless_item_stays_rejected(self):
        """The counter-example that keeps the fallback honest: if the averages
        agree there is no spread, there is no flip."""
        priced = engine.executable_prices(100, 100, ref_low=100, ref_high=100)
        self.assertFalse(priced.from_reference)
        self.assertLessEqual(engine.net_margin(priced.buy, priced.sell, False), 0)

    def test_without_a_reference_nothing_is_invented(self):
        priced = engine.executable_prices(24, 24)
        self.assertEqual((priced.buy, priced.sell), (24, 24))
        self.assertFalse(priced.from_reference)

    def test_a_healthy_quote_never_takes_the_fallback(self):
        priced = engine.executable_prices(100, 110, ref_low=101, ref_high=109)
        self.assertEqual((priced.buy, priced.sell), (101, 109))
        self.assertFalse(priced.from_reference)


class PriceDriftTests(unittest.TestCase):
    """Drift net of what the price grid can express.

    Measured across free-to-play items, median absolute drift ran 7.07% in the
    cheapest price quartile against 0.61% in the dearest — a twelvefold gap
    produced by nothing but price. At a penalty of 4 to 8 times the drift, that
    wiped most of the expected profit from every cheap item in the game, which
    is the bias that filled the top of the ranking with 1%-margin flips on
    expensive items.
    """

    def test_drift_is_net_of_one_tick(self):
        # 2 gp on a 100 gp item: one of those gp is the grid.
        self.assertAlmostEqual(engine.price_drift(102, 100), 0.01)

    def test_a_single_tick_on_a_cheap_item_is_not_momentum(self):
        self.assertEqual(engine.price_drift(11, 10), 0.0)
        self.assertEqual(engine.price_drift(9, 10), 0.0)

    def test_the_same_absolute_move_is_read_the_same_way(self):
        """A 1 gp wobble reads as nothing whether the item costs 10 or 10,000."""
        self.assertEqual(engine.price_drift(11, 10), 0.0)
        self.assertEqual(engine.price_drift(10_001, 10_000), 0.0)

    def test_a_real_fall_on_a_dear_item_survives(self):
        self.assertAlmostEqual(engine.price_drift(6_800, 7_000), -0.0284, places=4)

    def test_salmon_is_no_longer_read_as_a_12_percent_move(self):
        """Three gp on a 26 gp item was 11.8% of momentum and cost the flip
        three quarters of its expected profit."""
        before = engine.adverse_selection_factor(-0.50, (28.5 - 25.5) / 25.5)
        after = engine.adverse_selection_factor(-0.50, engine.price_drift(28.5, 25.5))
        self.assertAlmostEqual(before, 0.279, places=2)
        self.assertGreater(after, before * 1.5)

    def test_direction_is_preserved(self):
        self.assertGreater(engine.price_drift(110, 100), 0)
        self.assertLess(engine.price_drift(90, 100), 0)

    def test_missing_or_zero_inputs_are_not_drift(self):
        self.assertEqual(engine.price_drift(None, 100), 0.0)
        self.assertEqual(engine.price_drift(102, 0), 0.0)
        self.assertEqual(engine.price_drift(102, None), 0.0)


class TouchCompetitorsTests(unittest.TestCase):
    """The queue at the touch is not four people on every item in the game.

    A constant here was what let the model report a two-hour round trip on a
    fire rune flip that takes a day, and these tests exist so that number
    cannot quietly become a constant again.
    """

    def test_a_quiet_item_keeps_the_floor(self):
        # 10,000 units a window against a 13,000 limit: under one participant.
        crowd = engine.touch_competitors(2_500, 13_000)
        self.assertEqual(crowd, engine.DEFAULT_CALIBRATION.competitors_at_touch)

    def test_a_botted_commodity_is_crowded(self):
        # Fire rune: 1.68m units an hour against a 50,000 limit.
        crowd = engine.touch_competitors(1_681_042, 50_000)
        self.assertAlmostEqual(crowd, 134.5, delta=0.5)

    def test_it_is_the_participants_the_volume_implies(self):
        self.assertAlmostEqual(
            engine.touch_competitors(1_000, 100),
            1_000 * engine.WINDOW_HOURS / 100)

    def test_an_item_with_no_published_limit_keeps_the_floor(self):
        crowd = engine.touch_competitors(1_000_000, None)
        self.assertEqual(crowd, engine.DEFAULT_CALIBRATION.competitors_at_touch)
        self.assertEqual(engine.touch_competitors(1_000_000, 0),
                         engine.DEFAULT_CALIBRATION.competitors_at_touch)

    def test_no_volume_keeps_the_floor(self):
        self.assertEqual(engine.touch_competitors(0, 50_000),
                         engine.DEFAULT_CALIBRATION.competitors_at_touch)

    def test_where_it_binds_you_fill_one_buy_limit_per_window(self):
        """The property that makes it believable rather than just pessimistic.

        On a crowded item your share is limit/volume_per_window, so your fill
        rate is one buy limit per window — you cannot beat your own buy limit,
        which is the answer an hour of watching the Grand Exchange gives you.
        """
        for volume, limit in ((1_681_042, 50_000), (673_628, 13_000),
                              (2_429_316, 30_000)):
            crowd = engine.touch_competitors(volume, limit)
            share = engine.aggressiveness(0.0, competitors=crowd)
            seconds = engine.expected_fill_seconds(
                limit, engine.fill_rate(volume, share))
            hours = seconds / engine.SECONDS_PER_HOUR
            self.assertAlmostEqual(hours, engine.WINDOW_HOURS, delta=0.01)

    def test_conceding_spread_still_jumps_the_queue(self):
        """Crowding is only binding at the touch. Undercut room still works."""
        crowd = engine.touch_competitors(1_681_042, 50_000)
        at_touch = engine.aggressiveness(0.0, competitors=crowd)
        inside = engine.aggressiveness(0.5, competitors=crowd)
        self.assertGreater(inside, 10 * at_touch)

    def test_the_crowd_makes_a_botted_flip_slower_than_a_quiet_one(self):
        """The regression the whole change exists to prevent."""
        botted = engine.score_flip(
            buy=5, sell=6, margin=1, qty=25_000, depth=0,
            buy_volume_1h=1_681_042, sell_volume_1h=1_681_042,
            quote_age=10, ofi=0.0, drift=0.0, now=1_700_000_000,
            competitors=engine.touch_competitors(1_681_042, 50_000))
        quiet = engine.score_flip(
            buy=5, sell=6, margin=1, qty=25_000, depth=0,
            buy_volume_1h=1_681_042, sell_volume_1h=1_681_042,
            quote_age=10, ofi=0.0, drift=0.0, now=1_700_000_000)
        self.assertGreater(botted.total_seconds, 10 * quiet.total_seconds)
        self.assertLess(botted.gp_per_slot_hour, quiet.gp_per_slot_hour)


if __name__ == "__main__":
    unittest.main()
