"""Unit tests for filters.py — run with: python3 -m unittest test_filters -v"""
import dataclasses
from datetime import date
import math
import unittest

import engine
import exemptions
import filters
from api import Activity, Item, Quote

NOW = 1_785_000_000.0        # a Sunday, well away from the weekly update
NO_EXEMPTIONS = exemptions.ExemptionSet(())


def item(item_id=1, members=False, limit=100_000, name="Test item",
         highalch=None):
    return Item(id=item_id, name=name, members=members, limit=limit,
                value=100, highalch=highalch)


def quote(high=1_250, low=950, age=60):
    ts = int(NOW - age)
    return Quote(high=high, high_time=ts, low=low, low_time=ts)


def act_5m(avg_high=1_250, avg_low=950, high_volume=400, low_volume=380):
    return Activity(avg_high=avg_high, high_volume=high_volume,
                    avg_low=avg_low, low_volume=low_volume)


def act_1h(avg_high=1_250, avg_low=950, high_volume=5_000, low_volume=4_800):
    return Activity(avg_high=avg_high, high_volume=high_volume,
                    avg_low=avg_low, low_volume=low_volume)


def screen(items, quotes, acts_5m, acts_1h, **config):
    cfg = filters.FilterConfig(**config)
    return filters.screen(items, quotes, acts_5m, acts_1h, cfg, NOW,
                          NO_EXEMPTIONS)


def one(**overrides):
    """A single healthy item through the pipeline."""
    kwargs = dict(items={1: item()}, quotes={1: quote()},
                  acts_5m={1: act_5m()}, acts_1h={1: act_1h()})
    config = {k: v for k, v in overrides.items() if k not in kwargs}
    for key in list(overrides):
        if key in kwargs:
            kwargs[key] = overrides[key]
    return screen(kwargs["items"], kwargs["quotes"], kwargs["acts_5m"],
                  kwargs["acts_1h"], **config)


class StructuralGateTests(unittest.TestCase):
    """These reject. Everything else is scoring."""

    def test_missing_mapping_entry(self):
        result = screen({}, {1: quote()}, {1: act_5m()}, {1: act_1h()})
        self.assertEqual(result.rows, [])
        self.assertEqual(result.funnel["no mapping entry"], 1)

    def test_members_item_included_by_default(self):
        result = screen({1: item(members=True)}, {1: quote()},
                        {1: act_5m()}, {1: act_1h()})
        self.assertEqual(result.funnel["scored"], 1)

    def test_members_item_excluded_by_f2p_profile(self):
        result = screen({1: item(members=True)}, {1: quote()},
                        {1: act_5m()}, {1: act_1h()},
                        account=engine.AccountType.FREE_TO_PLAY)
        self.assertEqual(result.funnel["members-only"], 1)

    def test_null_price_side(self):
        result = screen({1: item()}, {1: Quote(high=None, high_time=None,
                                               low=950, low_time=int(NOW))},
                        {1: act_5m()}, {1: act_1h()})
        self.assertEqual(result.funnel["null price side"], 1)

    def test_one_sided_book_is_not_a_flip(self):
        result = screen({1: item()}, {1: quote()}, {1: act_5m()},
                        {1: act_1h(low_volume=0)})
        self.assertEqual(result.funnel["nothing traded"], 1)

    def test_margin_that_cannot_cover_tax(self):
        result = screen({1: item()}, {1: quote(low=1_000, high=1_001)},
                        {1: act_5m(avg_low=1_000, avg_high=1_001)},
                        {1: act_1h(avg_low=1_000, avg_high=1_001)})
        self.assertEqual(result.funnel["margin not positive"], 1)

    def test_cannot_afford_a_single_unit(self):
        result = screen({1: item()}, {1: quote()}, {1: act_5m()},
                        {1: act_1h()}, capital=100,
                        account=engine.AccountType.FREE_TO_PLAY)
        self.assertEqual(result.funnel["cannot afford one"], 1)

    def test_affordability_uses_the_whole_bank_not_an_equal_slot_split(self):
        result = screen(
            {1: item(limit=8)}, {1: quote(low=200_000, high=250_000)},
            {1: act_5m(avg_low=200_000, avg_high=250_000)},
            {1: act_1h(avg_low=200_000, avg_high=250_000)},
            capital=1_000_000)
        self.assertEqual(result.funnel["scored"], 1)

    def test_funnel_always_sums_to_the_quote_count(self):
        items = {1: item(1), 2: item(2, members=True), 3: item(3)}
        quotes = {1: quote(), 2: quote(), 3: quote(low=1_000, high=1_001),
                  4: quote()}
        acts5 = {i: act_5m() for i in (1, 2, 3, 4)}
        acts1 = {i: act_1h() for i in (1, 2, 3, 4)}
        result = screen(items, quotes, acts5, acts1)
        total = sum(v for k, v in result.funnel.items() if k != "in /latest")
        self.assertEqual(total, len(quotes))
        self.assertEqual(result.funnel["in /latest"], len(quotes))


class AccountConfigurationTests(unittest.TestCase):
    def test_default_is_members_with_eight_slots(self):
        config = filters.FilterConfig()
        self.assertEqual(config.account, engine.AccountType.MEMBERS)
        self.assertEqual(config.slots, engine.MEMBER_SLOTS)
        self.assertTrue(config.include_members)

    def test_f2p_derives_both_restrictions(self):
        config = filters.FilterConfig(account=engine.AccountType.FREE_TO_PLAY)
        self.assertEqual(config.slots, engine.F2P_SLOTS)
        self.assertFalse(config.include_members)


class NoLongerAGateTests(unittest.TestCase):
    """The old pipeline eliminated on these. They are now scoring inputs, so
    the item still reaches the ranking and simply scores what it is worth."""

    def test_a_stale_quote_is_scored_not_dropped(self):
        result = one(quotes={1: quote(age=7_200)})
        self.assertEqual(result.funnel["scored"], 1)
        self.assertGreater(result.rows[0].quote_age, 3_600)

    def test_no_undercut_room_is_scored_not_dropped(self):
        # The air rune trap: a 1 gp spread you can never queue-jump.
        result = one(quotes={1: quote(low=5, high=6)},
                     acts_5m={1: act_5m(avg_low=5, avg_high=6)},
                     acts_1h={1: act_1h(avg_low=5, avg_high=6)})
        self.assertEqual(result.funnel["scored"], 1)
        self.assertEqual(result.rows[0].undercut_depth, 0)

    def test_thin_volume_is_scored_not_dropped(self):
        result = one(acts_1h={1: act_1h(high_volume=3, low_volume=2)})
        self.assertEqual(result.funnel["scored"], 1)

    def test_low_roi_is_scored_not_dropped(self):
        result = one(quotes={1: quote(low=1_000, high=1_025)},
                     acts_5m={1: act_5m(avg_low=1_000, avg_high=1_025)},
                     acts_1h={1: act_1h(avg_low=1_000, avg_high=1_025)})
        self.assertEqual(result.funnel["scored"], 1)
        self.assertLess(result.rows[0].roi, 0.01)


class ScoringTests(unittest.TestCase):
    def test_a_healthy_flip_gets_a_fill_estimate_and_a_score(self):
        row = one().rows[0]
        self.assertGreater(row.gp_per_slot_hour, 0)
        self.assertGreater(row.expected_total_seconds, 0)
        self.assertLess(row.expected_total_seconds, float("inf"))
        self.assertGreater(row.p_fill, 0)
        self.assertTrue(row.factors)

    def test_the_sell_listing_price_is_the_bottom_of_its_tax_band(self):
        row = one().rows[0]
        self.assertLessEqual(row.sell_listed_at, row.sell)
        self.assertEqual(engine.net_revenue(row.sell_listed_at),
                         engine.net_revenue(row.sell))

    def test_alch_floor_is_carried_through(self):
        row = one(items={1: item(highalch=2_000)},
                  nature_rune_cost=100).rows[0]
        self.assertEqual(row.alch_floor, 1_900)
        self.assertIsNotNone(row.alch_distance)
        self.assertIsNotNone(row.alch_arbitrage_gp)

    def test_unalchable_items_have_no_floor(self):
        self.assertIsNone(one().rows[0].alch_floor)

    def test_order_flow_imbalance_is_recorded(self):
        row = one(acts_1h={1: act_1h(high_volume=1_000,
                                     low_volume=9_000)}).rows[0]
        self.assertLess(row.ofi, 0)

    def test_ranking_is_by_score_not_by_margin(self):
        # Big margin, almost no volume against small margin, deep volume.
        items = {1: item(1, name="Thin"), 2: item(2, name="Liquid")}
        quotes = {1: quote(low=1_000, high=1_400), 2: quote(low=100, high=104)}
        acts5 = {1: act_5m(avg_low=1_000, avg_high=1_400,
                           high_volume=1, low_volume=1),
                 2: act_5m(avg_low=100, avg_high=104,
                           high_volume=900, low_volume=900)}
        acts1 = {1: act_1h(avg_low=1_000, avg_high=1_400,
                           high_volume=2, low_volume=2),
                 2: act_1h(avg_low=100, avg_high=104,
                           high_volume=20_000, low_volume=20_000)}
        result = screen(items, quotes, acts5, acts1, capital=10_000_000)
        by_name = {r.name: r for r in result.rows}
        self.assertGreater(by_name["Thin"].margin, by_name["Liquid"].margin)
        self.assertEqual(result.rows[0].name, "Liquid")


class ShrinkageStageTests(unittest.TestCase):
    def make(self, count):
        items, quotes, acts5, acts1 = {}, {}, {}, {}
        for i in range(1, count + 1):
            spread = 20 + i
            items[i] = item(i, name="Item {}".format(i))
            quotes[i] = quote(low=1_000, high=1_000 + spread)
            acts5[i] = act_5m(avg_low=1_000, avg_high=1_000 + spread,
                              high_volume=100, low_volume=100)
            acts1[i] = act_1h(avg_low=1_000, avg_high=1_000 + spread,
                              high_volume=100 * i, low_volume=100 * i)
        return items, quotes, acts5, acts1

    def test_shrinkage_runs_over_everything_scored(self):
        result = screen(*self.make(40), capital=100_000_000)
        self.assertIsNotNone(result.shrinkage)
        self.assertTrue(result.shrinkage.applied)
        self.assertEqual(len(result.shrinkage.values), len(result.rows))

    def gap_closed(self, row, centre):
        """How much of the distance to the market average the shrinkage ate.

        Shrinkage pulls toward the centre from BOTH sides — an item below the
        average is revised up, not down. What is being tested is the pull
        itself and its dependence on evidence, not a haircut.
        """
        before = abs(math.log(row.raw_gp_per_slot_hour) - math.log(centre))
        after = abs(math.log(row.gp_per_slot_hour) - math.log(centre))
        return 1.0 - (after / before) if before > 1e-9 else 0.0

    def test_no_score_is_pushed_away_from_the_market_average(self):
        result = screen(*self.make(40), capital=100_000_000)
        centre = result.shrinkage.prior_mean_gp
        scored = [r for r in result.rows if r.raw_gp_per_slot_hour > 0]
        self.assertTrue(scored)
        for row in scored:
            self.assertGreaterEqual(self.gap_closed(row, centre), -1e-9)

    def test_the_thinnest_item_is_pulled_furthest(self):
        result = screen(*self.make(40), capital=100_000_000)
        centre = result.shrinkage.prior_mean_gp
        scored = [r for r in result.rows if r.raw_gp_per_slot_hour > 0]
        thinnest = min(scored, key=lambda r: r.thin_volume_1h)
        thickest = max(scored, key=lambda r: r.thin_volume_1h)
        self.assertGreater(self.gap_closed(thinnest, centre),
                           self.gap_closed(thickest, centre))

    def test_rows_are_sorted_by_the_shrunk_score(self):
        result = screen(*self.make(40), capital=100_000_000)
        scores = [r.gp_per_slot_hour for r in result.rows]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_an_inflated_thin_score_is_cut(self):
        # The optimizer's-curse case: a spread far above the market's, resting
        # on almost no traded volume. It must be revised down.
        items, quotes, acts5, acts1 = self.make(40)
        quotes[1] = quote(low=1_000, high=2_400)
        acts5[1] = act_5m(avg_low=1_000, avg_high=2_400,
                          high_volume=4, low_volume=4)
        acts1[1] = act_1h(avg_low=1_000, avg_high=2_400,
                          high_volume=40, low_volume=40)
        result = screen(items, quotes, acts5, acts1, capital=100_000_000)
        thin = next(r for r in result.rows if r.item_id == 1)
        self.assertGreater(thin.raw_gp_per_slot_hour,
                           result.shrinkage.prior_mean_gp)
        self.assertLess(thin.gp_per_slot_hour, thin.raw_gp_per_slot_hour)

    def test_a_hard_cut_is_explained_on_the_row(self):
        # A score that survives shrinkage largely intact says nothing; one that
        # is gutted has to say why, because the number the user was reading a
        # moment ago was mostly the thinness of the data behind it.
        #
        # The noise scale is raised here rather than relying on the default: at
        # the shipped defaults a cut this hard is uncommon, because thin volume
        # is already penalised once through the fill time before shrinkage sees
        # it. What is under test is the explanation, not the constant.
        noisy = dataclasses.replace(engine.DEFAULT_CALIBRATION,
                                    score_noise_scale=40.0)
        items, quotes, acts5, acts1 = self.make(40)
        quotes[1] = quote(low=1_000, high=2_400)
        acts5[1] = act_5m(avg_low=1_000, avg_high=2_400,
                          high_volume=6, low_volume=6)
        acts1[1] = act_1h(avg_low=1_000, avg_high=2_400,
                          high_volume=60, low_volume=60)
        result = screen(items, quotes, acts5, acts1, capital=100_000_000,
                        calibration=noisy)
        thin = next(r for r in result.rows if r.item_id == 1)
        kept = thin.gp_per_slot_hour / thin.raw_gp_per_slot_hour
        self.assertLess(kept, 0.85)
        self.assertTrue(any("shrinkage" in w for w in thin.warnings))


class PreferenceTests(unittest.TestCase):
    """Preferences hide rows after scoring; they must not reorder survivors."""

    def build(self):
        items, quotes, acts5, acts1 = {}, {}, {}, {}
        for i in range(1, 21):
            items[i] = item(i, name="Item {}".format(i))
            quotes[i] = quote(low=100 * i, high=int(100 * i * 1.05),
                              age=60 * i)
            acts5[i] = act_5m(avg_low=100 * i, avg_high=int(100 * i * 1.05),
                              high_volume=50 * i, low_volume=50 * i)
            acts1[i] = act_1h(avg_low=100 * i, avg_high=int(100 * i * 1.05),
                              high_volume=600 * i, low_volume=600 * i)
        return items, quotes, acts5, acts1

    def run_with(self, **config):
        cfg = filters.FilterConfig(capital=50_000_000, **config)
        result = filters.screen(*self.build(), config=cfg, now=NOW,
                                exempt=NO_EXEMPTIONS)
        return filters.apply_preferences(result, cfg)

    def test_hiding_rows_does_not_reorder_the_rest(self):
        unfiltered = self.run_with()
        filtered = self.run_with(min_price=500)
        kept = [r.name for r in unfiltered.rows if r.buy >= 500]
        self.assertEqual([r.name for r in filtered.rows], kept)

    def test_quote_age_preference(self):
        result = self.run_with(max_quote_age=300)
        self.assertTrue(all(r.quote_age <= 300 for r in result.rows))
        self.assertGreater(result.hidden["quote too old"], 0)

    def test_volume_preference(self):
        result = self.run_with(min_thin_volume_1h=5_000)
        self.assertTrue(all(r.thin_volume_1h >= 5_000 for r in result.rows))

    def test_price_range_preference(self):
        result = self.run_with(min_price=500, max_price=1_200)
        self.assertTrue(all(500 <= r.buy <= 1_200 for r in result.rows))

    def test_undercut_room_preference(self):
        result = self.run_with(min_undercut_depth=5)
        self.assertTrue(all(r.undercut_depth >= 5 for r in result.rows))

    def test_tax_free_preference(self):
        result = self.run_with(tax_free_only=True)
        self.assertTrue(all(r.tax == 0 for r in result.rows))

    def test_hidden_counts_add_up(self):
        result = self.run_with(min_price=500)
        total = sum(v for k, v in result.hidden.items() if k != "shown")
        self.assertEqual(total + result.hidden["shown"], 20)


class ExemptionTests(unittest.TestCase):
    def test_an_exempt_item_keeps_the_whole_spread(self):
        exempt = exemptions.ExemptionSet((1,))
        cfg = filters.FilterConfig(capital=10_000_000)
        taxed = filters.screen({1: item()}, {1: quote()}, {1: act_5m()},
                               {1: act_1h()}, cfg, NOW, NO_EXEMPTIONS)
        free = filters.screen({1: item()}, {1: quote()}, {1: act_5m()},
                              {1: act_1h()}, cfg, NOW, exempt)
        self.assertEqual(taxed.rows[0].tax, engine.ge_tax(taxed.rows[0].sell))
        self.assertEqual(free.rows[0].tax, 0)
        self.assertGreater(free.rows[0].margin, taxed.rows[0].margin)
        self.assertTrue(free.rows[0].tax_exempt)

    def test_hand_maintained_list_has_a_freshness_guard(self):
        config = {"_verified_date": "2026-01-01"}
        warning = exemptions.freshness_warning(
            config, max_age_days=90, today=date(2026, 8, 22))
        self.assertIn("re-check", warning)


class HistoryStageTests(unittest.TestCase):
    def buckets(self, level, volume=2_000, count=56):
        return [{"avgHighPrice": int(level * 1.02),
                 "avgLowPrice": int(level * 0.98),
                 "highPriceVolume": volume, "lowPriceVolume": volume}
                for _ in range(count)]

    def deep(self, points, **config):
        cfg = filters.FilterConfig(capital=10_000_000, **config)
        result = filters.screen({1: item()}, {1: quote()}, {1: act_5m()},
                                {1: act_1h()}, cfg, NOW, NO_EXEMPTIONS)
        return filters.refine_with_history(result, lambda _: points, cfg, NOW,
                                           top_k=5)

    def test_history_populates_the_deep_fields(self):
        result = self.deep(self.buckets(1_100))
        row = result.rows[0]
        self.assertTrue(row.deep_checked)
        self.assertEqual(result.deep_checked, 1)
        self.assertIsNotNone(row.fill_share)
        self.assertIsNotNone(row.median_mid)
        self.assertIsNotNone(row.regime_score)

    def test_missing_history_is_flagged_not_fatal(self):
        result = self.deep(None)
        row = result.rows[0]
        self.assertFalse(row.deep_checked)
        self.assertEqual(result.deep_checked, 0)
        self.assertTrue(any("no usable 14-day history" in w
                            for w in row.warnings))

    def test_too_little_history_is_flagged(self):
        result = self.deep(self.buckets(1_100, count=3))
        self.assertFalse(result.rows[0].deep_checked)

    def oscillating(self, level, count=56):
        """A mean-reverting series whose buckets all have the same internal
        spread, so the detrended fill shares stay put while the OU level moves.

        The high/low ratios are wide enough that the quoted 950/1250 is inside
        what the market reached, which is what separates this from a price only
        one dumper ever hit.
        """
        points = []
        for i in range(count):
            centre = level * (1.06 if i % 2 else 0.94)
            points.append({"avgHighPrice": int(centre * 1.19),
                           "avgLowPrice": int(centre * 0.81),
                           "highPriceVolume": 2_000, "lowPriceVolume": 2_000})
        return points

    def test_the_deep_stage_can_raise_a_score_as_well_as_lower_it(self):
        # The old pipeline multiplied by four factors that were all <= 1, so
        # history could only ever demote an item. Here an item quoted at 1,100
        # is re-scored against two histories with identical liquidity and
        # identical detrended fill shares, differing only in the long-run level
        # the price reverts to. Buying below that level must score higher than
        # buying at it.
        at_level = self.deep(self.oscillating(1_100)).rows[0]
        below_level = self.deep(self.oscillating(2_000)).rows[0]
        self.assertTrue(at_level.mean_reverting)
        self.assertTrue(below_level.mean_reverting)
        self.assertEqual(at_level.fill_share, below_level.fill_share)
        self.assertGreater(below_level.raw_gp_per_slot_hour,
                           at_level.raw_gp_per_slot_hour)

    def test_history_can_also_cut_a_score(self):
        # Prices that only ever traded in a narrow band nowhere near the quote:
        # the reachable volume is a fraction of the headline volume, so the
        # fill takes far longer than the intraday snapshot implied.
        narrow = [{"avgHighPrice": 1_105, "avgLowPrice": 1_095,
                   "highPriceVolume": 2_000, "lowPriceVolume": 2_000}] * 56
        result = self.deep(narrow)
        row = result.rows[0]
        self.assertTrue(row.deep_checked)
        self.assertLess(row.fill_share, 0.05)

    def test_a_shortlist_wider_than_the_display_is_fetched(self):
        # top_k * breadth, so the deep stage sees candidates that are not
        # already at the top and can promote them.
        seen = []
        items = {i: item(i, name="Item {}".format(i)) for i in range(1, 31)}
        quotes = {i: quote() for i in range(1, 31)}
        acts5 = {i: act_5m() for i in range(1, 31)}
        acts1 = {i: act_1h() for i in range(1, 31)}
        cfg = filters.FilterConfig(capital=100_000_000)
        result = filters.screen(items, quotes, acts5, acts1, cfg, NOW,
                                NO_EXEMPTIONS)

        def fetch(item_id):
            seen.append(item_id)
            return self.buckets(1_100)

        filters.refine_with_history(result, fetch, cfg, NOW, top_k=5)
        self.assertEqual(len(seen), 15)

    def test_recent_repeating_spread_is_attached_and_changes_rank(self):
        cfg = filters.FilterConfig(capital=10_000_000)
        result = filters.screen({1: item()}, {1: quote()}, {1: act_5m()},
                                {1: act_1h()}, cfg, NOW, NO_EXEMPTIONS)
        recent = [{"timestamp": index * 300,
                   "avgHighPrice": 1_250, "avgLowPrice": 950,
                   "highPriceVolume": 2_000, "lowPriceVolume": 2_000}
                  for index in range(72)]
        refined = filters.refine_with_history(
            result, lambda _: self.buckets(1_100), cfg, NOW, top_k=1,
            fetch_recent=lambda _: recent)
        row = refined.rows[0]
        self.assertIsNotNone(row.recent_execution)
        self.assertGreater(row.execution_quality, 0.70)
        self.assertGreater(row.execution_factor, 1.0)


class AllocationStageTests(unittest.TestCase):
    def test_capital_is_split_by_score_across_the_slots(self):
        items = {i: item(i, name="Item {}".format(i)) for i in (1, 2, 3)}
        quotes = {1: quote(low=100, high=110), 2: quote(low=100, high=106),
                  3: quote(low=100, high=104)}
        acts5 = {i: act_5m(avg_low=100, avg_high=q.high,
                           high_volume=500, low_volume=500)
                 for i, q in quotes.items()}
        acts1 = {i: act_1h(avg_low=100, avg_high=q.high,
                           high_volume=6_000, low_volume=6_000)
                 for i, q in quotes.items()}
        cfg = filters.FilterConfig(
            capital=3_000_000, account=engine.AccountType.FREE_TO_PLAY)
        result = filters.screen(items, quotes, acts5, acts1, cfg, NOW,
                                NO_EXEMPTIONS)
        result = filters.allocate(result, cfg)
        allocated = [r.allocated_capital for r in result.rows[:3]]
        self.assertTrue(all(a is not None for a in allocated))
        self.assertLessEqual(sum(allocated), 3_000_000)
        self.assertGreaterEqual(allocated[0], allocated[-1])

    def test_allocation_on_an_empty_list_is_harmless(self):
        cfg = filters.FilterConfig()
        empty = filters.ScreenResult(rows=[], funnel={})
        self.assertEqual(filters.allocate(empty, cfg).rows, [])

    def test_final_quantity_is_rescored_not_linearly_scaled(self):
        items = {i: item(i, name="Item {}".format(i), limit=100_000)
                 for i in (1, 2)}
        quotes = {1: quote(low=100, high=130), 2: quote(low=100, high=125)}
        acts5 = {i: act_5m(avg_low=100, avg_high=q.high) for i, q in quotes.items()}
        acts1 = {i: act_1h(avg_low=100, avg_high=q.high,
                           high_volume=500, low_volume=500)
                 for i, q in quotes.items()}
        cfg = filters.FilterConfig(capital=20_000)
        screened = filters.screen(items, quotes, acts5, acts1, cfg, NOW,
                                  NO_EXEMPTIONS)
        before = {r.item_id: r for r in screened.rows}
        allocated = filters.allocate(screened, cfg)
        row = next(r for r in allocated.rows if (r.allocated_quantity or 0) > 0)
        old = before[row.item_id]
        linear = old.expected_gp * row.allocated_quantity / old.qty_per_window
        self.assertNotAlmostEqual(row.allocated_expected_gp, linear, places=4)

    def test_active_allocation_uses_the_conservative_fill_bound(self):
        cfg = filters.FilterConfig(capital=10_000_000,
                                   trade_mode=engine.TradeMode.ACTIVE)
        row = one(capital=cfg.capital).rows[0]
        row = dataclasses.replace(
            row, fill_low_qty=3.9, fill_high_qty=100.0,
            capital_needed=100 * row.buy)
        result = filters.allocate(
            filters.ScreenResult(rows=[row], funnel={}), cfg)
        self.assertEqual(result.rows[0].allocated_quantity, 3)

    def test_overnight_allocation_can_use_the_upper_fill_bound(self):
        cfg = filters.FilterConfig(capital=10_000_000,
                                   trade_mode=engine.TradeMode.OVERNIGHT)
        row = one(capital=cfg.capital).rows[0]
        row = dataclasses.replace(
            row, fill_low_qty=3.9, fill_high_qty=7.9,
            capital_needed=100 * row.buy)
        result = filters.allocate(
            filters.ScreenResult(rows=[row], funnel={}), cfg)
        self.assertEqual(result.rows[0].allocated_quantity, 7)


class ExecutionDecisionTests(unittest.TestCase):
    def test_queue_priority_is_present_in_the_shown_prices(self):
        result = one(
            quotes={1: quote(low=173, high=192)},
            acts_5m={1: act_5m(avg_low=173, avg_high=192)},
            acts_1h={1: act_1h(avg_low=173, avg_high=192,
                              high_volume=1_000, low_volume=1_000)})
        row = result.rows[0]
        self.assertEqual(row.buy, row.base_buy + row.buy_improvement)
        self.assertEqual(row.sell, row.base_sell - row.sell_improvement)
        self.assertEqual(row.margin,
                         engine.net_margin(row.buy, row.sell, row.tax_exempt))
        self.assertAlmostEqual(row.buy_share, engine.aggressiveness(
            engine.price_edge(row.buy_improvement,
                              row.base_sell - row.base_buy),
            competitors=row.competitors))

    def test_connected_potion_doses_share_a_limit_group(self):
        self.assertEqual(filters.connected_limit_group("Prayer potion(4)"),
                         filters.connected_limit_group("Prayer potion(1)"))
        self.assertIsNone(filters.connected_limit_group("Games necklace(4)"))

    def test_reference_fallback_can_never_be_high_confidence(self):
        result = one(
            quotes={1: quote(low=100, high=100)},
            acts_5m={1: act_5m(avg_low=95, avg_high=110)},
            acts_1h={1: act_1h(avg_low=95, avg_high=110)})
        row = dataclasses.replace(
            result.rows[0], deep_checked=True, edge_probability=.99,
            p_fill=.99, fill_low_qty=95, fill_high_qty=100,
            qty_per_window=100, raw_ranking_value=100,
            ranking_value=100)
        self.assertTrue(row.priced_from_reference)
        self.assertNotEqual(filters.confidence_label(row), "High")


class VolumeLookupTests(unittest.TestCase):
    def test_archive_volume_overrides_the_live_bucket(self):
        cfg = filters.FilterConfig(capital=10_000_000)
        live = filters.screen({1: item()}, {1: quote()}, {1: act_5m()},
                              {1: act_1h()}, cfg, NOW, NO_EXEMPTIONS)
        smoothed = filters.screen({1: item()}, {1: quote()}, {1: act_5m()},
                                  {1: act_1h()}, cfg, NOW, NO_EXEMPTIONS,
                                  volume_lookup=lambda _: (200.0, 200.0))
        self.assertEqual(live.rows[0].thin_volume_1h, 4_800)
        self.assertEqual(smoothed.rows[0].thin_volume_1h, 200)
        self.assertGreater(smoothed.rows[0].expected_total_seconds,
                           live.rows[0].expected_total_seconds)

    def test_a_lookup_that_knows_nothing_falls_back(self):
        cfg = filters.FilterConfig(capital=10_000_000)
        result = filters.screen({1: item()}, {1: quote()}, {1: act_5m()},
                                {1: act_1h()}, cfg, NOW, NO_EXEMPTIONS,
                                volume_lookup=lambda _: None)
        self.assertEqual(result.rows[0].thin_volume_1h, 4_800)


class WarningTests(unittest.TestCase):
    def test_no_undercut_room_is_explained(self):
        result = one(quotes={1: quote(low=5, high=6)},
                     acts_5m={1: act_5m(avg_low=5, avg_high=6)},
                     acts_1h={1: act_1h(avg_low=5, avg_high=6)})
        self.assertTrue(any("outbid the queue" in w
                            for w in result.rows[0].warnings))

    def test_a_free_undercut_is_pointed_out(self):
        # Sell lands on a multiple of 50, so a 1 gp undercut is free.
        result = one(quotes={1: quote(low=900, high=1_000)},
                     acts_5m={1: act_5m(avg_low=900, avg_high=1_000)},
                     acts_1h={1: act_1h(avg_low=900, avg_high=1_000)})
        self.assertTrue(any("list the sell at" in w
                            for w in result.rows[0].warnings))

    def test_selling_pressure_is_called_out(self):
        result = one(acts_1h={1: act_1h(high_volume=1_000, low_volume=9_000)})
        self.assertTrue(any("aggressor volume" in w
                            for w in result.rows[0].warnings))

    def test_an_alch_arbitrage_is_called_out(self):
        result = one(items={1: item(highalch=5_000)}, nature_rune_cost=100)
        self.assertTrue(any("high-alch value" in w
                            for w in result.rows[0].warnings))


class FullPipelineTests(unittest.TestCase):
    def test_rank_flips_runs_every_stage(self):
        items = {i: item(i, name="Item {}".format(i)) for i in range(1, 11)}
        quotes = {i: quote(low=100 * i, high=int(100 * i * 1.06))
                  for i in range(1, 11)}
        acts5 = {i: act_5m(avg_low=100 * i, avg_high=int(100 * i * 1.06))
                 for i in range(1, 11)}
        acts1 = {i: act_1h(avg_low=100 * i, avg_high=int(100 * i * 1.06))
                 for i in range(1, 11)}
        cfg = filters.FilterConfig(
            capital=20_000_000,
            account=engine.AccountType.FREE_TO_PLAY, min_price=200)
        result = filters.rank_flips(items, quotes, acts5, acts1, cfg, NOW,
                                    fetch_history=lambda _: None, top_k=3,
                                    exempt=NO_EXEMPTIONS)
        self.assertTrue(result.rows)
        self.assertIn("shown", result.hidden)
        self.assertTrue(all(r.buy >= 200 for r in result.rows))
        self.assertIsNotNone(result.rows[0].allocated_capital)


if __name__ == "__main__":
    unittest.main()
