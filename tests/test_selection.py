"""Measured reach, offer replay and the slot-and-bank portfolio selection.

These are the pieces the November 2026 audit added after the walk-forward
backtest showed where the old ranking lost money: an offer priced at the last
traded price was assumed to fill, unsold stock cost nothing, and the bank was
handed out from the top of a per-item ranking.
"""
from __future__ import annotations

import itertools
import unittest

import engine
import filters
from api import Activity, Item, Quote

NOW = 1_785_000_000


def bucket(index, low, low_volume, high, high_volume):
    return {"timestamp": NOW - (400 - index) * 300, "avgLowPrice": low,
            "lowPriceVolume": low_volume, "avgHighPrice": high,
            "highPriceVolume": high_volume}


def flat(count=120, low=100, high=110, volume=40):
    return [bucket(i, low, volume, high, volume) for i in range(count)]


class ReachTests(unittest.TestCase):
    def test_offer_at_the_traded_price_has_no_priority(self):
        view = engine.reach_view(flat())
        self.assertEqual(view.buy_volume_per_hour(100), 0.0)
        self.assertEqual(view.sell_volume_per_hour(110), 0.0)
        # One tick better outranks everything that traded.
        self.assertAlmostEqual(view.buy_volume_per_hour(101), 480.0)
        self.assertAlmostEqual(view.sell_volume_per_hour(109), 480.0)
        self.assertAlmostEqual(view.low_volume_per_hour, 480.0)

    def test_touch_weight_credits_part_of_the_volume_at_the_same_price(self):
        view = engine.reach_view(flat())
        self.assertAlmostEqual(view.buy_volume_per_hour(100, 0.25), 120.0)
        self.assertAlmostEqual(view.sell_volume_per_hour(110, 1.0), 480.0)

    def test_only_volume_at_a_worse_price_is_reached(self):
        points = [bucket(i, 100 if i % 2 else 104, 40, 110, 40)
                  for i in range(120)]
        view = engine.reach_view(points)
        self.assertAlmostEqual(view.buy_volume_per_hour(102), 240.0)
        self.assertAlmostEqual(view.buy_volume_per_hour(105), 480.0)

    def test_window_is_what_the_series_covers_and_ends_at_the_newest(self):
        view = engine.reach_view(flat(count=400))
        self.assertAlmostEqual(view.hours, 24.0)
        self.assertEqual(len(view.lows), 288)
        short = engine.reach_view(flat(count=24))
        self.assertAlmostEqual(short.hours, 2.0)

    def test_thin_or_one_sided_series_gives_no_verdict(self):
        self.assertIsNone(engine.reach_view([]))
        self.assertIsNone(engine.reach_view(flat(count=11)))
        one_sided = [bucket(i, 100, 40, None, 0) for i in range(120)]
        self.assertIsNone(engine.reach_view(one_sided))

    def test_fractional_prices_round_half_up_like_the_browser(self):
        points = [bucket(i, 100.5, 40, 110.5, 40) for i in range(20)]
        view = engine.reach_view(points)
        self.assertEqual(view.lows[0][0], 101)
        self.assertEqual(view.highs[0][0], 111)


class ReplayTests(unittest.TestCase):
    def replay(self, points, **overrides):
        options = dict(buy=101, sell=109, qty=10, buy_share=0.5,
                       sell_share=0.5, mode=engine.TradeMode.ACTIVE,
                       horizon_hours=4.0)
        options.update(overrides)
        return engine.replay_offer(points, **options)

    def test_steady_two_sided_market_completes_at_the_margin(self):
        view = self.replay(flat())
        self.assertEqual(view.completion_rate, 1.0)
        # 109 less 2 gp tax, less 101 paid: 6 gp on each of 10 units.
        self.assertAlmostEqual(view.mean_profit, 60.0)
        self.assertEqual(view.loss_rate, 0.0)
        # Bought in the first bucket, sold in the second.
        self.assertAlmostEqual(view.mean_slot_hours, 2 / 12)
        self.assertAlmostEqual(view.stable_profit, 60.0)

    def test_offers_at_the_traded_price_never_fill(self):
        view = self.replay(flat(), buy=100, sell=110)
        self.assertEqual((view.bought_share, view.mean_profit), (0.0, 0.0))
        # The slot is held until the buy is cancelled at half the window.
        self.assertAlmostEqual(view.mean_slot_hours, 2.0)

    def test_unsold_stock_is_dumped_at_the_instant_sell_price_less_tax(self):
        points = [bucket(i, 100, 40, 108, 40) for i in range(120)]
        view = self.replay(points)                 # buyers never reach 109
        self.assertEqual((view.bought_share, view.sold_share), (1.0, 0.0))
        self.assertAlmostEqual(view.mean_profit, 10 * (98 - 101))
        self.assertEqual(view.loss_rate, 1.0)
        self.assertEqual(view.completion_rate, 0.0)

    def test_a_unit_is_sold_only_after_it_was_bought(self):
        # A one-bucket deadline: the buy fills, but the buyers of that same
        # bucket came before there was anything to sell them.
        view = self.replay(flat(), horizon_hours=5 / 60)
        self.assertEqual((view.bought_share, view.sold_share), (1.0, 0.0))
        self.assertAlmostEqual(view.mean_profit, 10 * (98 - 101))

    def test_edge_in_one_half_of_the_window_is_not_stable(self):
        points = ([bucket(i, 100, 40, 108, 40) for i in range(180)]
                  + [bucket(i, 100, 40, 110, 40) for i in range(180, 360)])
        view = self.replay(points)
        self.assertLess(view.older_profit, 0)
        self.assertGreater(view.newer_profit, 0)
        self.assertEqual(view.stable_profit, view.older_profit)
        self.assertGreater(view.mean_profit, view.stable_profit)

    def test_away_buys_all_absence_and_sells_only_after_return(self):
        view = self.replay(flat(count=200), mode=engine.TradeMode.OVERNIGHT,
                           horizon_hours=8.0)
        self.assertEqual(view.completion_rate, 1.0)
        # Eight hours away, then sold in the first bucket back.
        self.assertAlmostEqual(view.mean_slot_hours, 8.0 + 1 / 12)

    def test_too_little_history_gives_no_verdict(self):
        self.assertIsNone(self.replay(flat(count=47)))       # under one window
        self.assertIsNone(self.replay(flat(count=60)))       # too few starts
        self.assertIsNone(self.replay(flat(), qty=0))


class SelectPortfolioTests(unittest.TestCase):
    def test_slots_binding_is_the_plain_top_ranking(self):
        selection = engine.select_portfolio(
            [[(10.0, 5)], [(8.0, 5)], [(7.0, 1)]], capital=100, slots=2)
        self.assertEqual(selection.choices, [0, 0, -1])
        self.assertEqual((selection.capital_price, selection.binding),
                         (0.0, "slots"))

    def test_bank_binding_prefers_return_on_coins(self):
        # The top-value candidate would take the whole bank for 10; the other
        # two together earn 11 from the same coins.
        selection = engine.select_portfolio(
            [[(10.0, 10)], [(6.0, 5)], [(5.0, 5)]], capital=10, slots=3)
        self.assertEqual(selection.choices, [-1, 0, 0])
        # The least productive funded coin earns 1 per coin.
        self.assertEqual(selection.capital_price, 1.0)
        self.assertEqual(selection.binding, "capital")

    def test_sizes_are_chosen_jointly(self):
        selection = engine.select_portfolio(
            [[(3.0, 2), (5.0, 4), (6.0, 8)], [(4.0, 4), (7.0, 8)]],
            capital=12, slots=2)
        self.assertEqual(selection.choices, [1, 1])
        # Both candidates fit in two slots; only the bank held the plan back.
        self.assertEqual(selection.binding, "capital")
        both = engine.select_portfolio(
            [[(3.0, 2)], [(4.0, 4)], [(9.0, 9)]], capital=6, slots=2)
        self.assertEqual((both.choices, both.binding), ([0, 0, -1], "both"))

    def test_nothing_scarce(self):
        selection = engine.select_portfolio([[(3.0, 2)], [(1.0, 2)]], 100, 8)
        self.assertEqual((selection.choices, selection.binding), ([0, 0], "none"))

    def test_never_funds_a_loss_or_overspends(self):
        selection = engine.select_portfolio([[(-1.0, 1)], [(2.0, 50)]], 10, 8)
        self.assertEqual(selection.choices, [-1, -1])
        self.assertEqual(engine.select_portfolio([], 10, 8).choices, [])
        self.assertEqual(engine.select_portfolio([[(1.0, 1)]], 10, 0).choices,
                         [-1])

    def test_matches_brute_force_on_small_cases(self):
        import random
        rng = random.Random(11)
        worst = 1.0
        for _ in range(150):
            options = []
            for _ in range(rng.randint(1, 5)):
                value = coins = 0
                sizes = []
                for _ in range(rng.randint(1, 3)):
                    coins += rng.randint(1, 40)
                    value += rng.uniform(1, 30)
                    sizes.append((value, coins))
                options.append(sizes)
            capital, slots = rng.randint(10, 120), rng.randint(1, 4)
            selection = engine.select_portfolio(options, capital, slots)
            got = spent = funded = 0
            for sizes, choice in zip(options, selection.choices):
                if choice >= 0:
                    got += sizes[choice][0]
                    spent += sizes[choice][1]
                    funded += 1
            self.assertLessEqual(spent, capital)
            self.assertLessEqual(funded, slots)
            best = 0.0
            for combo in itertools.product(*[range(-1, len(s)) for s in options]):
                picked = [(s[c][0], s[c][1]) for s, c in zip(options, combo)
                          if c >= 0]
                if (len(picked) <= slots
                        and sum(c for _, c in picked) <= capital):
                    best = max(best, sum(v for v, _ in picked))
            if best > 0:
                worst = min(worst, got / best)
        # Exact up to the coin step: with these small banks the step is one
        # coin, so the optimum itself must be found every time.
        self.assertGreaterEqual(worst, 1.0 - 1e-12)


class PolicyTests(unittest.TestCase):
    """The selection policy on a hand-built two-item market."""

    def market(self):
        items = {1: Item(1, "Steady", True, 1000, 1, None),
                 2: Item(2, "Fluke", True, 1000, 1, None)}
        quotes = {i: Quote(110, NOW - 30, 100, NOW - 30) for i in items}
        activity = {i: Activity(110, 4000, 100, 4000) for i in items}
        return items, quotes, activity

    def history(self, _):
        return [{"timestamp": NOW - (60 - i) * 21600, "avgHighPrice": 110,
                 "highPriceVolume": 20000, "avgLowPrice": 100,
                 "lowPriceVolume": 20000} for i in range(60)]

    def recent(self, item_id):
        if item_id == 1:
            return flat(count=365, volume=400)
        # Buyers stopped paying the quoted price. Nothing trades high enough
        # above what sellers accept to leave a margin after tax.
        return [bucket(i, 100, 400, 102, 400) for i in range(365)]

    def plan(self, reach=True, **overrides):
        items, quotes, activity = self.market()
        config = filters.FilterConfig(capital=1_000_000, **overrides)
        result = filters.screen(items, quotes, activity, activity, config, NOW)
        result = filters.refine_with_history(
            result, self.history, config, NOW,
            fetch_reach=self.recent if reach else None)
        return filters.allocate(result, config)

    def test_without_recent_buckets_both_are_funded_on_the_quoted_spread(self):
        funded = [r for r in self.plan(reach=False).rows
                  if r.allocated_quantity]
        self.assertEqual({r.name for r in funded}, {"Steady", "Fluke"})
        self.assertTrue(all(r.buy_reach is None for r in funded))

    def test_reach_moves_the_prices_inside_what_traded(self):
        rows = {r.name: r for r in self.plan().rows}
        steady = rows["Steady"]
        self.assertGreater(steady.buy, 100)
        self.assertLess(steady.sell, 110)
        self.assertEqual((steady.buy_reach, steady.sell_reach), (1.0, 1.0))
        self.assertIsNotNone(steady.replay)

    def test_replay_evidence_drops_the_offer_that_only_looked_good(self):
        result = self.plan(funding_evidence="replay", replay_ranking=True,
                           replay_statistic="stable", allocation="portfolio")
        funded = [r for r in result.rows if r.allocated_quantity]
        self.assertEqual([r.name for r in funded], ["Steady"])
        row = funded[0]
        self.assertGreater(row.replay.stable_profit, 0)
        self.assertEqual(row.expected_gp, row.replay.stable_profit)
        self.assertIn("neither bank nor slots", row.plan_reason)
        self.assertEqual(result.selection.binding, "none")
        fluke = next(r for r in result.rows if r.name == "Fluke")
        self.assertIsNone(fluke.allocated_quantity)
        self.assertTrue(fluke.replay is None
                        or fluke.replay.stable_profit <= 0)

    def test_position_cap_sizes_candidates_inside_it(self):
        result = self.plan(max_position_capital=20_000)
        for row in result.rows:
            self.assertLessEqual(row.capital_needed, 20_000)
            if row.allocated_capital:
                self.assertLessEqual(row.allocated_capital, 20_000)

    def test_invalid_policy_values_are_rejected(self):
        for field, value in (("allocation", "greedy"),
                             ("funding_evidence", "vibes"),
                             ("replay_statistic", "median"),
                             ("active_objective", "fun"),
                             ("max_position_capital", 0)):
            with self.assertRaises(ValueError):
                filters.FilterConfig(**{field: value})


if __name__ == "__main__":
    unittest.main()
