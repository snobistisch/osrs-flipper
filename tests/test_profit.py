"""Max profit: the most risk-adjusted gp per flip, however long it takes.

Guarded here:
- the ranking is profit per flip, so a slow high-margin flip beats a fast
  low-margin one that Active (gp per slot-hour) prefers;
- one flip is one buy offer of at most one buy-limit window, even though the
  24-hour deadline spans six windows;
- inventory still unsold at the deadline is charged as a stress loss, and the
  quantity is the one with the best expected value after that charge;
- time, completion odds and warnings are still reported, and the stored
  values of the other two strategies keep their meaning.
"""
import json
import math
import unittest
from dataclasses import replace
from unittest import mock

import agent
import cli
import engine
import filters

NOW = 1_785_000_000          # a Sunday, away from the weekly update
PROFIT = engine.TradeMode.PROFIT
ACTIVE = engine.TradeMode.ACTIVE
FAST = dict(base_buy=1_000, base_sell=1_030, volume=6_000.0, limit=2_000)
SLOW = dict(base_buy=20_000, base_sell=21_500, volume=30.0, limit=100)
# Slow with a thinner margin: here the stress on unsold units binds.
THIN = dict(base_buy=20_000, base_sell=20_800, volume=30.0, limit=100)


def optimise(mode, base_buy, base_sell, volume, limit, capital=50_000_000,
             **overrides):
    config = filters.FilterConfig(capital=capital, trade_mode=mode)
    values = dict(base_buy=base_buy, base_sell=base_sell, tax_exempt=False,
                  limit=limit, available_capital=capital,
                  buy_volume_1h=volume, sell_volume_1h=volume, quote_age=60,
                  ofi=0.0, drift=0.0, now=NOW, highalch=None,
                  competitors=8.0, config=config)
    values.update(overrides)
    return filters._optimise_execution(**values)


def profit_score(**overrides):
    values = dict(buy=1_000, sell=1_080, margin=58, qty=2_000, depth=0,
                  buy_volume_1h=150.0, sell_volume_1h=150.0, quote_age=60,
                  ofi=0.0, drift=0.0, now=NOW, buy_share=0.125,
                  sell_share=0.125, mode=PROFIT)
    values.update(overrides)
    return engine.score_flip(**values)


class ProfitModeNamingTests(unittest.TestCase):
    def test_stored_values_keep_their_meaning(self):
        self.assertIs(engine.TradeMode("profit"), PROFIT)
        self.assertIs(engine.TradeMode("away"), engine.TradeMode.OVERNIGHT)
        self.assertIs(engine.TradeMode("overnight"), engine.TradeMode.OVERNIGHT)
        self.assertIs(engine.TradeMode("active"), ACTIVE)

    def test_the_deadline_is_the_longest_supported_horizon(self):
        self.assertEqual(engine.PROFIT_HORIZON_HOURS, 24.0)
        profile = engine.TradingProfile(mode="profit")
        self.assertEqual(profile.horizon_hours, 24.0)
        # The Away slider does not move it.
        config = filters.FilterConfig(trade_mode="profit", overnight_hours=2)
        self.assertEqual(config.horizon_hours, 24.0)
        self.assertEqual(profit_score().horizon_hours, 24.0)

    def test_cli_and_agent_accept_the_strategy(self):
        opts = cli.parse_args(["--capital", "20m", "--strategy", "profit"])
        config = cli.config_from(opts, 100)
        self.assertIs(config.trade_mode, PROFIT)
        opts = agent.build_parser().parse_args(
            ["flips", "--json", "--strategy", "profit"])
        self.assertEqual(opts.strategy, "profit")


class ProfitRankingTests(unittest.TestCase):
    def test_slow_high_profit_beats_fast_low_profit_unlike_active(self):
        fast_active = optimise(ACTIVE, **FAST).breakdown
        slow_active = optimise(ACTIVE, **SLOW).breakdown
        self.assertGreater(fast_active.ranking_value,
                           slow_active.ranking_value)
        fast = optimise(PROFIT, **FAST).breakdown
        slow = optimise(PROFIT, **SLOW).breakdown
        self.assertGreater(slow.ranking_value, fast.ranking_value)
        # The ranking value is the profit itself, not a rate.
        self.assertEqual(slow.ranking_value, slow.expected_profit)
        self.assertGreater(slow.round_trip_p50_seconds,
                           fast.round_trip_p50_seconds)

    def test_time_is_still_reported_from_one_distribution(self):
        slow = optimise(PROFIT, **SLOW).breakdown
        self.assertLess(slow.round_trip_p50_seconds,
                        slow.round_trip_p80_seconds)
        self.assertLess(slow.round_trip_p80_seconds,
                        slow.round_trip_p90_seconds)
        self.assertGreater(slow.p_fill_both, 0.0)
        self.assertLess(slow.p_fill_both, 1.0)
        self.assertGreater(slow.gp_per_slot_hour, 0.0)
        self.assertLessEqual(slow.cancel_by_seconds,
                             24 * engine.SECONDS_PER_HOUR)
        self.assertLessEqual(slow.reprice_check_seconds, 45 * 60)
        self.assertIn("holding_risk", slow.factors())


class ProfitQuantityTests(unittest.TestCase):
    def test_quantity_is_capped_at_one_buy_limit_window(self):
        choice = optimise(PROFIT, base_buy=1_000, base_sell=1_100,
                          volume=200_000.0, limit=500)
        self.assertEqual(choice.qty, 500)
        self.assertEqual(engine.effective_buy_limit(500, 24.0, PROFIT), 500)
        # Away over the same 24 hours would reach six windows.
        self.assertEqual(engine.effective_buy_limit(
            500, 24.0, engine.TradeMode.OVERNIGHT), 3_000)

    def test_allocation_never_funds_more_than_one_window(self):
        from tests.test_filters import act_1h, act_5m, item, quote
        config = filters.FilterConfig(capital=100_000_000, trade_mode="profit")
        result = filters.rank_flips(
            {1: item(limit=700)}, {1: quote()}, {1: act_5m()}, {1: act_1h()},
            config, NOW, exempt=frozenset())
        row = result.rows[0]
        self.assertIs(row.trade_mode, PROFIT)
        self.assertGreater(row.allocated_quantity, 0)
        self.assertLessEqual(row.allocated_quantity, 700)
        self.assertTrue(math.isfinite(row.ranking_value))
        self.assertIn(filters.confidence_label(row),
                      ("High", "Medium", "Speculative"))

    def test_quantity_is_the_best_expected_value_not_the_capacity(self):
        choice = optimise(PROFIT, **THIN)
        self.assertLess(choice.qty, choice.capacity_qty)
        # The same prices at the full mean-rate capacity are worth less once
        # the inventory left unsold at the deadline is charged.
        at_capacity = profit_score(
            buy=choice.buy, sell=choice.sell, margin=choice.breakdown.margin,
            qty=choice.capacity_qty, buy_volume_1h=choice.buy_volume_1h,
            sell_volume_1h=THIN["volume"],
            buy_share=choice.breakdown.buy_share,
            sell_share=choice.breakdown.sell_share,
            buy_improvement=choice.buy_improvement,
            sell_improvement=choice.sell_improvement, competitors=8.0)
        self.assertLess(at_capacity.ranking_value,
                        choice.breakdown.ranking_value)
        self.assertGreater(at_capacity.downside_risk_gp,
                           choice.breakdown.downside_risk_gp)


class ProfitStrandedInventoryTests(unittest.TestCase):
    def test_unsold_inventory_at_the_deadline_is_charged(self):
        small = profit_score(qty=50)
        large = profit_score(qty=450)
        self.assertGreaterEqual(large.p_stranded, 0.2)
        self.assertGreater(large.downside_risk_gp, 0.0)
        self.assertLess(small.downside_risk_gp, large.downside_risk_gp)
        completed = (large.margin * large.expected_sell_qty
                     * large.adverse_selection * large.holding_risk
                     * large.staleness * large.mean_reversion * large.alch
                     * large.update_risk)
        self.assertAlmostEqual(large.expected_profit,
                               completed - large.downside_risk_gp, places=6)
        # Buying more than can be sold makes the flip worth less, not more.
        self.assertLess(profit_score(qty=1_000).ranking_value,
                        profit_score(qty=200).ranking_value)

    def test_active_does_not_charge_and_is_unchanged(self):
        active = profit_score(qty=20_000, mode=ACTIVE)
        self.assertEqual(active.downside_risk_gp, 0.0)
        self.assertEqual(active.horizon_hours, 4.0)

    def test_the_risk_is_stated_in_warnings(self):
        breakdown = profit_score(qty=450)
        notes = filters._timing_warnings(breakdown, engine.DEFAULT_CALIBRATION)
        self.assertTrue(any(note.startswith("inventory risk:") and "24h deadline"
                            in note for note in notes), notes)
        self.assertTrue(any(note.startswith("fill odds:") for note in notes),
                        notes)
        self.assertFalse(any("automatic funding" in note for note in notes))


class ProfitOutputTests(unittest.TestCase):
    def test_agent_json_reports_profit_as_the_ranking_value(self):
        from tests.test_filters import act_1h, act_5m, item, quote
        config = filters.FilterConfig(capital=20_000_000, trade_mode="profit")
        result = filters.rank_flips(
            {1: item(limit=700)}, {1: quote()}, {1: act_5m()}, {1: act_1h()},
            config, NOW, exempt=frozenset())
        payload = json.loads(json.dumps(agent.flip_to_dict(result.rows[0])))
        self.assertEqual(payload["strategy"], "profit")
        self.assertEqual(payload["horizon_hours"], 24.0)
        self.assertEqual(payload["ranking_value"],
                         round(result.rows[0].ranking_value))
        for key in ("round_trip_p50_seconds", "round_trip_p90_seconds",
                    "p_fill", "p_stranded", "downside_risk_gp",
                    "gp_per_slot_hour", "edge_probability", "warnings"):
            self.assertIn(key, payload)

    def test_quote_age_limits_match_active(self):
        self.assertEqual(filters.quote_age_limits(PROFIT),
                         filters.quote_age_limits(ACTIVE))

    def test_meets_completion_target_has_no_target_for_profit(self):
        from tests.test_filters import one
        row = replace(one(capital=10_000_000).rows[0], p_fill=0.1,
                      trade_mode=PROFIT)
        config = filters.FilterConfig(trade_mode="profit")
        self.assertTrue(filters.meets_completion_target(row, config))

    def test_cli_table_labels_the_profit_metric(self):
        from tests.test_filters import act_1h, act_5m, item, quote
        opts = cli.parse_args(["--capital", "20m", "--strategy", "profit"])
        config = cli.config_from(opts, 100)
        result = filters.rank_flips(
            {1: item(limit=700)}, {1: quote()}, {1: act_5m()}, {1: act_1h()},
            config, NOW, exempt=frozenset())
        exempt = mock.Mock(unmatched_names=(), __len__=lambda self: 0)
        with mock.patch("builtins.print") as printed:
            cli.print_table(result, opts, config, exempt, 100, "no archive")
        text = "\n".join(" ".join(str(a) for a in call.args)
                         for call in printed.call_args_list)
        self.assertIn("PROFIT/FLIP", text)
        self.assertIn("TRIP P50-P90", text)
        self.assertIn("24h deadline", text)


if __name__ == "__main__":
    unittest.main()
