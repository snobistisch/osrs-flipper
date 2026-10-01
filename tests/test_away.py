"""Away (formerly Overnight): unattended buys, dip bids, sizing and exposure.

Regressions guarded here, each measured on live data before the fix:
- the alch floor zeroed the downside of 20,000 stranded bolts that would take
  seventeen hours to cast;
- quantity filled the horizon at the mean rate, so the full buy completed 38%
  of the time and about 30% of it was left unsold;
- update and mean-reversion exposure were measured over the sell leg alone
  for inventory held all night;
- the model never bid below today's price, which is the point of waiting.
"""
import math
import unittest
from dataclasses import replace

import engine
import filters
import stats

CAL = engine.DEFAULT_CALIBRATION
NOW = 1_785_000_000          # a Sunday, away from the weekly update
AWAY = engine.TradeMode.OVERNIGHT


def reverting_fit(kappa=3.0, sigma=0.08):
    return stats.OUFit(kappa=kappa, mu=math.log(1_000), sigma=sigma,
                       t_stat=-6.0, n=56, dt_days=0.25)


def trending_fit(sigma=0.08):
    return stats.OUFit(kappa=0.01, mu=math.log(1_000), sigma=sigma,
                       t_stat=-0.5, n=56, dt_days=0.25)


def away_score(**overrides):
    values = dict(buy=1_000, sell=1_080, margin=58, qty=2_000, depth=0,
                  buy_volume_1h=600.0, sell_volume_1h=150.0, quote_age=60,
                  ofi=0.0, drift=0.0, now=NOW, buy_share=0.125,
                  sell_share=0.125, mode=AWAY, horizon_hours=8.0)
    values.update(overrides)
    return engine.score_flip(**values)


def optimise(mode=AWAY, hours=8.0, ou=None, sigma=None, **overrides):
    config = filters.FilterConfig(capital=50_000_000, trade_mode=mode,
                                  overnight_hours=hours)
    values = dict(base_buy=1_000, base_sell=1_080, tax_exempt=False,
                  limit=20_000, available_capital=config.capital,
                  buy_volume_1h=3_000.0, sell_volume_1h=2_500.0,
                  quote_age=60, ofi=0.0, drift=0.0, now=NOW, highalch=None,
                  competitors=9.0, config=config, sigma_daily=sigma,
                  ou_fit=ou)
    values.update(overrides)
    return filters._optimise_execution(**values)


class AwayModeNamingTests(unittest.TestCase):
    def test_away_is_the_same_mode_and_short_absences_exist(self):
        self.assertIs(engine.TradeMode("away"), AWAY)
        self.assertIs(engine.TradeMode("overnight"), AWAY)
        for hours in (1.0, 2.0, 4.0, 8.0, 12.0):
            self.assertIn(hours, engine.OVERNIGHT_HORIZON_PRESETS)
        self.assertEqual(filters.FilterConfig(
            trade_mode="away", overnight_hours=2).horizon_hours, 2.0)


class AlchFloorCapacityTests(unittest.TestCase):
    def test_floor_protects_only_what_you_can_cast(self):
        # Trading right at its alch floor, almost nothing sells back.
        floor_gp = 1_000 + 100
        result = away_score(qty=20_000, buy_volume_1h=50_000.0,
                            sell_volume_1h=20.0, highalch=floor_gp,
                            nature_rune_cost=100, sigma_daily=0.10)
        stranded = result.expected_buy_qty - result.expected_sell_qty
        protected = engine.alch_protected_units(CAL.overnight_liquidation_hours)
        self.assertGreater(stranded, protected)
        self.assertGreater(result.downside_risk_gp, 0)
        # Every unit past the casting capacity carries the full stress move.
        unprotected_share = (stranded - protected) / stranded
        no_floor = away_score(qty=20_000, buy_volume_1h=50_000.0,
                              sell_volume_1h=20.0, sigma_daily=0.10)
        self.assertAlmostEqual(result.downside_risk_gp,
                               no_floor.downside_risk_gp * unprotected_share,
                               delta=no_floor.downside_risk_gp * 1e-6)

    def test_a_small_position_is_fully_covered_by_the_floor(self):
        result = away_score(qty=500, buy_volume_1h=50_000.0,
                            sell_volume_1h=5.0, highalch=1_100,
                            nature_rune_cost=100, sigma_daily=0.10)
        self.assertEqual(result.downside_risk_gp, 0.0)


class AwayExposureTests(unittest.TestCase):
    def test_update_risk_covers_the_whole_absence(self):
        # Seven hours before the update: a quick Active trip clears in time,
        # inventory held over an eight-hour absence does not.
        when = NOW + engine.seconds_until_market_event(NOW) - 7 * 3_600
        self.assertAlmostEqual(engine.seconds_until_market_event(when),
                               7 * 3_600)
        active = engine.score_flip(
            buy=1_000, sell=1_080, margin=58, qty=20, depth=0,
            buy_volume_1h=5_000.0, sell_volume_1h=5_000.0, quote_age=60,
            ofi=0.0, drift=0.0, now=when, buy_share=0.125, sell_share=0.125)
        away = away_score(qty=20, buy_volume_1h=5_000.0,
                          sell_volume_1h=5_000.0, now=when)
        self.assertLess(away.update_risk, active.update_risk)

    def test_mean_reversion_is_credited_over_the_holding_period(self):
        fit = reverting_fit(kappa=1.0)
        below = 900        # mid well under the fitted level of 1,000
        active = engine.score_flip(
            buy=below - 40, sell=below + 40, margin=58, qty=20, depth=0,
            buy_volume_1h=5_000.0, sell_volume_1h=5_000.0, quote_age=60,
            ofi=0.0, drift=0.0, now=NOW, buy_share=0.125, sell_share=0.125,
            ou_fit=fit)
        away = away_score(buy=below - 40, sell=below + 40, qty=20,
                          buy_volume_1h=5_000.0, sell_volume_1h=5_000.0,
                          ou_fit=fit)
        self.assertGreater(away.mean_reversion, active.mean_reversion)


class DipBidTests(unittest.TestCase):
    def test_dip_multiplier_shape(self):
        self.assertEqual(engine.dip_fill_multiplier(0.0, 0.05, 8), 1.0)
        shallow = engine.dip_fill_multiplier(0.01, 0.05, 8)
        deep = engine.dip_fill_multiplier(0.05, 0.05, 8)
        self.assertGreater(shallow, deep)
        self.assertGreater(deep, 0.0)
        self.assertGreater(engine.dip_fill_multiplier(0.03, 0.05, 12),
                           engine.dip_fill_multiplier(0.03, 0.05, 2))
        self.assertGreater(engine.dip_fill_multiplier(0.03, 0.10, 8),
                           engine.dip_fill_multiplier(0.03, 0.05, 8))

    def test_only_a_reverting_item_gives_a_dip_back(self):
        self.assertEqual(engine.dip_exit_retention(None, 6), 0.0)
        self.assertEqual(engine.dip_exit_retention(trending_fit(), 6), 0.0)
        self.assertEqual(engine.dip_exit_retention(
            reverting_fit(), 6, regime_score=CAL.regime_shift_threshold), 0.0)
        kept = engine.dip_exit_retention(reverting_fit(kappa=3.0), 6)
        self.assertAlmostEqual(kept, 1 - math.exp(-3.0 * 6 / 24))

    def test_without_reversion_evidence_away_never_bids_under_the_market(self):
        for ou in (None, trending_fit()):
            choice = optimise(ou=ou, sigma=0.08)
            self.assertGreaterEqual(choice.buy, 1_000)
            self.assertEqual(choice.dip_depth, 0.0)

    def test_active_never_bids_under_the_market(self):
        choice = optimise(mode=engine.TradeMode.ACTIVE, ou=reverting_fit(),
                          sigma=0.08)
        self.assertGreaterEqual(choice.buy, 1_000)

    def test_a_reverting_item_can_be_bid_under_the_market(self):
        choice = optimise(ou=reverting_fit(kappa=6.0, sigma=0.12), sigma=0.12,
                          base_sell=1_040, buy_volume_1h=40_000.0,
                          sell_volume_1h=40_000.0)
        self.assertLess(choice.buy, 1_000)
        self.assertGreater(choice.dip_depth, 0)
        # The dip is sold into the market that dipped, less what came back.
        carried = math.floor((1_000 - choice.buy)
                             * (1 - choice.dip_retention) + 0.5)
        listed = 1_040 - choice.sell_improvement
        self.assertEqual(choice.sell, listed - carried)
        # And it only fills on a dip: the buy-side rate is scaled down.
        self.assertLess(choice.buy_volume_1h, 40_000.0)


class AwaySizingTests(unittest.TestCase):
    def test_away_quantity_is_the_expected_value_choice(self):
        choice = optimise(sigma=0.30, buy_volume_1h=3_000.0,
                          sell_volume_1h=150.0)
        config = filters.FilterConfig(capital=50_000_000, trade_mode=AWAY,
                                      overnight_hours=8.0)
        full = engine.score_flip(
            buy=choice.buy, sell=choice.sell,
            margin=engine.net_margin(choice.buy, choice.sell),
            qty=engine.flippable_qty(
                engine.effective_buy_limit(20_000, 8.0, AWAY),
                engine.fillable_quantity(choice.buy_volume_1h,
                                         choice.breakdown.buy_share, 8.0),
                50_000_000 // choice.buy),
            depth=0, buy_volume_1h=choice.buy_volume_1h,
            sell_volume_1h=150.0, quote_age=60, ofi=0.0, drift=0.0, now=NOW,
            sigma_daily=0.30, competitors=9.0,
            buy_improvement=choice.buy_improvement,
            sell_improvement=choice.sell_improvement,
            buy_share=choice.breakdown.buy_share,
            sell_share=choice.breakdown.sell_share, mode=AWAY,
            horizon_hours=8.0, calibration=config.calibration)
        # With a thin exit and a volatile price, buying everything the mean
        # rate allows strands inventory; a smaller order is worth more.
        self.assertLess(choice.qty, full.qty)
        self.assertGreater(choice.breakdown.ranking_value, full.ranking_value)
        stranded = (choice.breakdown.expected_buy_qty
                    - choice.breakdown.expected_sell_qty)
        self.assertLess(stranded, full.expected_buy_qty - full.expected_sell_qty)


class AwayVolumeTests(unittest.TestCase):
    def test_away_deep_check_uses_the_daily_average_rate(self):
        points = [{"timestamp": NOW - (56 - i) * 21_600,
                   "avgHighPrice": 1_080, "avgLowPrice": 1_000,
                   "highPriceVolume": 600, "lowPriceVolume": 600}
                  for i in range(56)]
        view = engine.history_view(points, 1_000, 1_080)
        self.assertAlmostEqual(view.low_volume_per_hour, 100.0)
        self.assertAlmostEqual(view.high_volume_per_hour, 100.0)
        from api import Activity, Item, Quote
        items = {1: Item(id=1, name="Test", members=True, limit=10_000,
                         value=1_000, highalch=None)}
        quotes = {1: Quote(high=1_080, high_time=NOW - 30, low=1_000,
                           low_time=NOW - 30)}
        hour = {1: Activity(avg_high=1_080, high_volume=2_400, avg_low=1_000,
                            low_volume=2_400)}
        five = {1: Activity(avg_high=1_080, high_volume=200, avg_low=1_000,
                            low_volume=200)}
        for mode, expected in ((AWAY, 100.0), (engine.TradeMode.ACTIVE,
                                               2_400.0)):
            config = filters.FilterConfig(capital=50_000_000, trade_mode=mode)
            screened = filters.screen(items, quotes, five, hour, config, NOW,
                                      frozenset())
            refined = filters.refine_with_history(
                screened, lambda _: points, config, NOW, top_k=1)
            row = refined.rows[0]
            self.assertTrue(row.deep_checked)
            share = engine.history_view(points, row.buy, row.sell)
            self.assertAlmostEqual(
                row.model_sell_volume_1h,
                expected * max(share.sell_fill_share, 0.01), places=6)


class ScoreFlipStillConsistentTests(unittest.TestCase):
    def test_away_p_fill_means_the_full_buy_by_return(self):
        result = away_score()
        self.assertEqual(result.p_fill_both, result.p_fill_buy)
        self.assertEqual(replace(result).mode, AWAY)


class AwayConfidenceTests(unittest.TestCase):
    def test_quote_age_limits_follow_the_mode(self):
        from tests.test_filters import one
        row = replace(one(capital=10_000_000).rows[0], quote_age=400,
                      edge_probability=0.9, p_fill=0.6,
                      execution_quality=0.7, fill_low_qty=90.0,
                      fill_high_qty=100.0, qty_per_window=100)
        self.assertEqual(filters.confidence_label(
            replace(row, trade_mode=engine.TradeMode.ACTIVE)), "Speculative")
        self.assertEqual(filters.confidence_label(
            replace(row, trade_mode=AWAY)), "Medium")
        self.assertEqual(filters.confidence_label(
            replace(row, trade_mode=AWAY, quote_age=1_000)), "Speculative")


if __name__ == "__main__":
    unittest.main()
