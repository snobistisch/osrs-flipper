"""Measured reach, offer replay and the slot-and-bank portfolio selection.

These are the pieces the November 2026 audit added after the walk-forward
backtest showed where the old ranking lost money: an offer priced at the last
traded price was assumed to fill, unsold stock cost nothing, and the bank was
handed out from the top of a per-item ranking.
"""
from __future__ import annotations

import itertools
import unittest
from dataclasses import replace

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

    def test_without_recent_buckets_nothing_is_funded(self):
        rows = self.plan(reach=False).rows
        self.assertEqual({r.name for r in rows}, {"Steady", "Fluke"})
        self.assertTrue(all(r.buy_reach is None and r.replay is None
                            and r.allocated_quantity is None for r in rows))

    def test_reach_moves_the_prices_inside_what_traded(self):
        rows = {r.name: r for r in self.plan().rows}
        steady = rows["Steady"]
        self.assertGreater(steady.buy, 100)
        self.assertLess(steady.sell, 110)
        self.assertEqual((steady.buy_reach, steady.sell_reach), (1.0, 1.0))
        self.assertIsNotNone(steady.replay)

    def test_replay_evidence_drops_the_offer_that_only_looked_good(self):
        result = self.plan()
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
        for field, value in (("max_position_capital", 0),
                             ("max_position_capital", True)):
            with self.assertRaises(ValueError):
                filters.FilterConfig(**{field: value})


class CrossingShareTests(unittest.TestCase):
    """Volume that trades through an offer's price reaches it by price
    priority. Sharing it out like a touch queue kept every offer at a
    fraction of the buy limit, however much traded. Since 16 November 2026
    the default order size is "careful" (the queue share), so these select
    "large" explicitly."""

    LARGE = engine.with_order_size(engine.DEFAULT_CALIBRATION, "large")

    def test_the_share_is_price_priority_not_a_place_in_a_queue(self):
        share = self.LARGE.crossing_capture_share
        self.assertGreater(share, 1.0 / self.LARGE.competitors_at_touch)
        self.assertLessEqual(share, 1.0)
        # A crowd of any size leaves it alone: the crowd is in the price.
        self.assertEqual(engine.crossing_share(self.LARGE, 16), share)
        self.assertEqual(engine.crossing_share(self.LARGE, 134), share)

    def test_an_offer_nobody_watches_keeps_the_queue_share(self):
        # Away and Max profit: nobody reprices the offer when it is outbid.
        for mode in (engine.TradeMode.OVERNIGHT, engine.TradeMode.PROFIT):
            self.assertAlmostEqual(
                engine.crossing_share(competitors=16, mode=mode), 1 / 16)
            self.assertAlmostEqual(
                engine.crossing_share(competitors=134, mode=mode), 1 / 134)
        resting = replace(self.LARGE, resting_capture_share=0.2)
        self.assertEqual(engine.crossing_share(
            resting, 16, engine.TradeMode.OVERNIGHT), 0.2)
        self.assertEqual(engine.crossing_share(resting, 16),
                         self.LARGE.crossing_capture_share)

    def test_switched_off_it_is_the_old_queue_share(self):
        queue = replace(engine.DEFAULT_CALIBRATION, crossing_capture_share=0.0)
        self.assertAlmostEqual(engine.crossing_share(queue, 16), 1 / 16)
        self.assertAlmostEqual(engine.crossing_share(queue, 134), 1 / 134)
        whole = replace(engine.DEFAULT_CALIBRATION, crossing_capture_share=3.0)
        self.assertEqual(engine.crossing_share(whole, 16), 1.0)

    def plan(self, calibration=None, mode=engine.TradeMode.ACTIVE):
        calibration = self.LARGE if calibration is None else calibration
        # 4,000 units a side every five minutes: 192 buy limits a window.
        items = {1: Item(1, "Busy", True, 1000, 1, None)}
        quotes = {1: Quote(110, NOW - 30, 100, NOW - 30)}
        activity = {1: Activity(110, 48_000, 100, 48_000)}
        history = [{"timestamp": NOW - (60 - i) * 21600, "avgHighPrice": 110,
                    "highPriceVolume": 288_000, "avgLowPrice": 100,
                    "lowPriceVolume": 288_000} for i in range(60)]
        config = filters.FilterConfig(capital=1_000_000, trade_mode=mode,
                                      calibration=calibration)
        result = filters.screen(items, quotes, activity, activity, config, NOW)
        result = filters.refine_with_history(
            result, lambda _: history, config, NOW,
            fetch_reach=lambda _: flat(count=365, volume=4000))
        return filters.allocate(result, config).rows[0]

    def test_a_busy_item_is_sized_to_its_buy_limit(self):
        row = self.plan()
        self.assertEqual(row.buy_share, self.LARGE.crossing_capture_share)
        self.assertEqual(row.sell_share, row.buy_share)
        self.assertEqual(row.qty_per_window, 1000)
        self.assertEqual(row.allocated_quantity, 1000)
        self.assertGreaterEqual(row.replay.completion_rate, 0.99)

    def test_the_queue_share_left_it_at_a_sixth_of_the_limit(self):
        # The regression: one buy limit per window as the mean rate, halved
        # for the round trip and cut again for an 80% completion.
        queue = replace(engine.DEFAULT_CALIBRATION, crossing_capture_share=0.0)
        row = self.plan(queue)
        self.assertAlmostEqual(row.buy_share, 1000 / (48_000 * 4))
        self.assertLess(row.qty_per_window, 200)

    def test_away_and_max_profit_rows_carry_the_queue_share(self):
        for mode in (engine.TradeMode.OVERNIGHT, engine.TradeMode.PROFIT):
            row = self.plan(mode=mode)
            self.assertAlmostEqual(row.buy_share, 1000 / (48_000 * 4))
            self.assertEqual(row.sell_share, row.buy_share)

    def test_an_offer_at_the_traded_price_still_reaches_nothing(self):
        # Price priority needs a better price. At the same price the offer
        # is behind the queue, whatever the capture share.
        view = engine.reach_view(flat())
        self.assertEqual(view.buy_volume_per_hour(100), 0.0)
        replayed = engine.replay_offer(
            flat(), buy=100, sell=110, qty=50, buy_share=1.0, sell_share=1.0,
            mode=engine.TradeMode.ACTIVE, horizon_hours=4.0)
        self.assertEqual(replayed.bought_share, 0.0)


class OrderSizeTests(unittest.TestCase):
    """The Active order-size setting (audit F-01): careful is the default."""

    def shares(self, order_size):
        calibration = engine.with_order_size(engine.DEFAULT_CALIBRATION,
                                             order_size)
        return {mode: engine.crossing_share(calibration, 16, mode)
                for mode in engine.TradeMode}

    def test_default_is_careful_the_queue_share(self):
        self.assertEqual(engine.DEFAULT_ORDER_SIZE, "careful")
        self.assertEqual(engine.DEFAULT_CALIBRATION.crossing_capture_share, 0.0)
        self.assertEqual(engine.DEFAULT_CALIBRATION.resting_capture_share, 0.0)

    def test_careful(self):
        shares = self.shares("careful")
        for mode in engine.TradeMode:
            self.assertAlmostEqual(shares[mode], 1 / 16, msg=mode)

    def test_balanced(self):
        shares = self.shares("balanced")
        self.assertEqual(shares[engine.TradeMode.ACTIVE], 0.15)
        self.assertAlmostEqual(shares[engine.TradeMode.OVERNIGHT], 1 / 16)
        self.assertAlmostEqual(shares[engine.TradeMode.PROFIT], 1 / 16)

    def test_large(self):
        shares = self.shares("large")
        self.assertEqual(shares[engine.TradeMode.ACTIVE], 0.30)
        self.assertAlmostEqual(shares[engine.TradeMode.OVERNIGHT], 1 / 16)
        self.assertAlmostEqual(shares[engine.TradeMode.PROFIT], 1 / 16)

    def test_unknown_order_size_is_rejected(self):
        with self.assertRaises(ValueError):
            engine.with_order_size(engine.DEFAULT_CALIBRATION, "huge")

    def test_cli_flag_sets_the_calibration(self):
        import cli
        for name, share in engine.ORDER_SIZES.items():
            opts = cli.parse_args(["--order-size", name])
            config = cli.config_from(opts, 100)
            self.assertEqual(config.calibration.crossing_capture_share, share)
        opts = cli.parse_args([])
        self.assertEqual(cli.config_from(opts, 100).calibration
                         .crossing_capture_share, 0.0)


class LimitUsageTests(unittest.TestCase):
    """Units bought in the last four hours count against the buy limit
    (audit F-05). Sized on a large capture share so the limit binds."""

    LARGE = replace(engine.DEFAULT_CALIBRATION, crossing_capture_share=0.30)

    def plan(self, entries=(), items=None, limit=10_000):
        items = items or {1: Item(1, "Busy", True, limit, 1, None)}
        quotes = {i: Quote(110, NOW - 30, 100, NOW - 30) for i in items}
        scale = limit / 1000
        activity = {i: Activity(110, int(48_000 * scale), 100,
                                int(48_000 * scale)) for i in items}
        history = [{"timestamp": NOW - (60 - i) * 21600, "avgHighPrice": 110,
                    "highPriceVolume": int(288_000 * scale),
                    "avgLowPrice": 100,
                    "lowPriceVolume": int(288_000 * scale)} for i in range(60)]
        config = filters.FilterConfig(capital=100_000_000,
                                      calibration=self.LARGE)
        usage = filters.limit_usage(entries, NOW) if entries else None
        return filters.rank_flips(
            items, quotes, activity, activity, config, NOW,
            fetch_history=lambda _: history,
            fetch_reach=lambda _: flat(count=365, volume=int(4000 * scale)),
            limit_used=usage).rows

    def test_without_usage_the_whole_limit_is_planned(self):
        row = self.plan()[0]
        self.assertEqual(row.allocated_quantity, 10_000)
        self.assertNotIn(filters.LIMIT_USED_WARNING, row.warnings)

    def test_a_limit_used_up_an_hour_ago_is_not_funded(self):
        entries = [{"item_id": 1, "limit_group": None, "qty": 10_000,
                    "at": NOW - 3600}]
        row = self.plan(entries)[0]
        self.assertIsNone(row.allocated_quantity)
        self.assertIn(filters.LIMIT_USED_WARNING, row.warnings)

    def test_part_of_the_limit_used_caps_the_offer(self):
        entries = [{"item_id": 1, "limit_group": None, "qty": 4_000,
                    "at": NOW - 3600}]
        row = self.plan(entries)[0]
        self.assertGreater(row.allocated_quantity, 0)
        self.assertLessEqual(row.allocated_quantity, 6_000)
        self.assertLessEqual(row.qty_per_window, 6_000)

    def test_purchases_older_than_four_hours_do_not_count(self):
        entries = [{"item_id": 1, "limit_group": None, "qty": 10_000,
                    "at": NOW - 4 * 3600 - 60}]
        used = self.plan(entries)[0]
        fresh = self.plan()[0]
        self.assertEqual(used, fresh)

    def test_doses_of_one_potion_share_what_is_left(self):
        items = {2: Item(2, "Prayer potion(3)", True, 2_000, 1, None)}
        entries = [{"item_id": 1, "limit_group": "potion:prayer potion",
                    "qty": 1_500, "at": NOW - 1800}]
        row = self.plan(entries, items=items, limit=2_000)[0]
        self.assertEqual(row.limit_used, 1_500)
        self.assertGreater(row.allocated_quantity, 0)
        self.assertLessEqual(row.allocated_quantity, 500)

    def test_usage_is_summed_by_item_and_by_family(self):
        usage = filters.limit_usage([
            {"item_id": 1, "limit_group": "potion:x", "qty": 100, "at": NOW},
            {"item_id": 2, "limit_group": "potion:x", "qty": 50, "at": NOW},
            {"item_id": 3, "limit_group": None, "qty": 7, "at": NOW - 100},
            {"item_id": 3, "limit_group": None, "qty": 9,
             "at": NOW - 4 * 3600},
            {"item_id": 3, "limit_group": None, "qty": 0, "at": NOW},
        ], NOW)
        self.assertEqual(usage.used(1, "potion:x"), 150)
        self.assertEqual(usage.used(2, "potion:x"), 150)
        self.assertEqual(usage.used(3, None), 7)
        self.assertEqual(usage.used(4, None), 0)


class CategoryCapTests(unittest.TestCase):
    """Three rows per family of related items; "other" is not a family."""

    NAMES = ("Alpha", "Bravo", "Charlie", "Delta", "Echo",
             "Fire rune", "Water rune", "Earth rune", "Air rune", "Mind rune")

    def plan(self):
        items = {i: Item(i, name, True, 1000, 1, None)
                 for i, name in enumerate(self.NAMES, 1)}
        quotes = {i: Quote(130, NOW - 30, 100, NOW - 30) for i in items}
        activity = {i: Activity(130, 1000, 100, 1000) for i in items}
        history = [{"timestamp": NOW - (60 - i) * 21600, "avgHighPrice": 130,
                    "highPriceVolume": 6000, "avgLowPrice": 100,
                    "lowPriceVolume": 6000} for i in range(60)]
        config = filters.FilterConfig(
            capital=10_000_000, account=engine.AccountType.MEMBERS)
        result = filters.rank_flips(
            items, quotes, activity, activity, config, NOW,
            fetch_history=lambda _: history,
            fetch_reach=lambda _: flat(count=365, high=130, volume=100))
        return [row for row in result.rows if row.allocated_quantity]

    def test_uncategorised_items_are_not_capped_together(self):
        counts = {}
        for row in self.plan():
            counts[row.category] = counts.get(row.category, 0) + 1
        # Eight slots: every uncategorised row, and three of the runes.
        self.assertEqual(counts, {"other": 5, "runes": 3})

    def test_category_full(self):
        self.assertFalse(filters.category_full({"other": 40}, "other"))
        self.assertFalse(filters.category_full({"runes": 2}, "runes"))
        self.assertTrue(filters.category_full({"runes": 3}, "runes"))
        self.assertFalse(filters.category_full({}, "potions"))


class DeepTargetTests(unittest.TestCase):
    """Which rows the per-item history budget is spent on."""

    def rows(self, count=60, reference_every=3):
        items = {1: Item(1, "Base", True, 1000, 1, None)}
        quotes = {1: Quote(110, NOW - 30, 100, NOW - 30)}
        activity = {1: Activity(110, 4000, 100, 4000)}
        base = filters.screen(items, quotes, activity, activity,
                              filters.FilterConfig(), NOW).rows[0]
        return [replace(base, item_id=index, name="Item {}".format(index),
                        priced_from_reference=index % reference_every == 0,
                        ranking_value=float(count - index))
                for index in range(count)]

    def test_a_third_of_the_budget_goes_to_reference_priced_rows(self):
        rows = self.rows()
        targets = filters._deep_targets(rows, 45, filters.FilterConfig())
        self.assertEqual(len(targets), 45)
        reference = [i for i in targets if rows[i].priced_from_reference]
        # Regression, audit 2026-11: 45 * (1 - 1/3) is 30.000000000000004 in
        # floating point, and rounding that up gave 31 direct rows here where
        # the browser's Math.ceil(45 * 2 / 3) gives 30.
        self.assertEqual((len(targets) - len(reference), len(reference)),
                         (30, 15))
        self.assertEqual(targets[:3], [1, 2, 4])     # the best direct rows

    def test_rows_the_preferences_hide_do_not_use_the_budget(self):
        rows = self.rows(count=10, reference_every=1000)
        rows[0] = replace(rows[0], quote_age=5_000)
        rows[1] = replace(rows[1], thin_volume_1h=3)
        config = filters.FilterConfig(max_quote_age=600, min_thin_volume_1h=40)
        self.assertEqual(filters._deep_targets(rows, 4, config), [2, 3, 4, 5])
        self.assertEqual(filters.preference_stage(rows[0], config),
                         "quote too old")
        self.assertEqual(filters.preference_stage(rows[1], config),
                         "volume too thin")
        self.assertIsNone(filters.preference_stage(rows[2], config))

    def test_short_lists_are_checked_in_full(self):
        rows = self.rows(count=7)
        self.assertEqual(sorted(filters._deep_targets(
            rows, 45, filters.FilterConfig())),
                         list(range(7)))


class ProfileTests(unittest.TestCase):
    def test_profile_values_by_bank_and_strategy(self):
        low = filters.automatic_profile(filters.FilterConfig(capital=5_000_000))
        self.assertEqual((low.max_quote_age, low.min_thin_volume_1h,
                          low.min_roi, low.min_undercut_depth),
                         (600, 100, 0.003, 1))
        self.assertEqual((low.max_price, low.max_position_capital),
                         (1_250_000, 1_250_000))
        self.assertTrue(low.hide_botted)
        away = filters.automatic_profile(filters.FilterConfig(
            capital=20_000_000, trade_mode="away"), bank_risk_percent=50)
        self.assertEqual((away.max_quote_age, away.min_thin_volume_1h,
                          away.min_roi, away.max_position_capital),
                         (900, 20, 0.008, 10_000_000))
        profit = filters.automatic_profile(filters.FilterConfig(
            capital=20_000_000, trade_mode="profit"))
        self.assertEqual((profit.max_quote_age, profit.min_thin_volume_1h,
                          profit.min_roi), (600, 20, 0.003))

    def test_the_bank_binding_is_reported_when_coins_cut_a_row_short(self):
        # The market supports 20 units of 101 gp, but other offers hold most
        # of the bank and only 1,000 gp is free. The selection never sees the
        # sizes it cannot afford; the plan must still say the bank decided.
        items = {1: Item(1, "Only", True, 1000, 1, None)}
        quotes = {1: Quote(130, NOW - 30, 100, NOW - 30)}
        activity = {1: Activity(130, 1000, 100, 1000)}
        history = [{"timestamp": NOW - (60 - i) * 21600, "avgHighPrice": 130,
                    "highPriceVolume": 6000, "avgLowPrice": 100,
                    "lowPriceVolume": 6000} for i in range(60)]
        config = filters.FilterConfig(capital=10_000)
        screened = filters.refine_with_history(
            filters.screen(items, quotes, activity, activity, config, NOW),
            lambda _: history, config, NOW,
            fetch_reach=lambda _: flat(count=365, high=130, volume=40))
        self.assertEqual(screened.rows[0].qty_per_window, 20)
        roomy = filters.allocate(screened, config)
        self.assertEqual(roomy.selection.binding, "none")
        self.assertEqual(roomy.rows[0].allocated_quantity, 20)
        tight = filters.allocate(screened, replace(config, capital=1_000))
        row = tight.rows[0]
        self.assertLess(row.allocated_quantity, 20)
        self.assertLessEqual(row.allocated_capital, 1_000)
        self.assertEqual(tight.selection.binding, "capital")
        self.assertGreater(tight.selection.capital_price, 0)
        self.assertIn("bank is the limit", row.plan_reason)

    def test_cli_flags_replace_single_gates_of_the_policy(self):
        import cli
        opts = cli.parse_args(["--capital", "20m"])
        config = cli.config_from(opts, 100)
        self.assertEqual(config, filters.automatic_profile(
            filters.FilterConfig(capital=20_000_000, nature_rune_cost=100)))
        opts = cli.parse_args(["--capital", "20m", "--min-vol", "500",
                               "--bank-risk", "50", "--max-price", "2m"])
        config = cli.config_from(opts, 100)
        self.assertEqual((config.min_thin_volume_1h, config.max_price,
                          config.max_position_capital, config.min_roi),
                         (500, 2_000_000, 10_000_000, 0.003))
        with self.assertRaises(ValueError):
            cli.config_from(cli.parse_args(["--bank-risk", "5"]), 100)


if __name__ == "__main__":
    unittest.main()
