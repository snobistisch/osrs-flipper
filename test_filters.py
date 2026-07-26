"""Unit tests for filters.py — run with: python3 -m unittest test_filters -v"""
import unittest

import engine
import filters
from api import Activity, Item, Quote

NOW = 1_000_000.0


def item(item_id=1, members=False, limit=100, name="Test item"):
    return Item(id=item_id, name=name, members=members, limit=limit,
                value=100, highalch=60)


def quote(high=1_250, low=950, age=60):
    ts = int(NOW - age)
    return Quote(high=high, high_time=ts, low=low, low_time=ts)


def act_5m(avg_high=1_250, avg_low=950, high_volume=40, low_volume=30):
    return Activity(avg_high=avg_high, high_volume=high_volume,
                    avg_low=avg_low, low_volume=low_volume)


def act_1h(avg_high=1_250, avg_low=950, high_volume=500, low_volume=400):
    return Activity(avg_high=avg_high, high_volume=high_volume,
                    avg_low=avg_low, low_volume=low_volume)


def rank(items, quotes, acts_5m, acts_1h, **config):
    cfg = filters.FilterConfig(**config)
    return filters.rank_flips(items, quotes, acts_5m, acts_1h, cfg, now=NOW)


class GateTests(unittest.TestCase):
    def test_missing_mapping_entry(self):
        rows, funnel = rank({}, {1: quote()}, {1: act_5m()}, {1: act_1h()})
        self.assertEqual(rows, [])
        self.assertEqual(funnel["no mapping entry"], 1)

    def test_members_item_rejected_by_default(self):
        rows, funnel = rank({1: item(members=True)}, {1: quote()},
                            {1: act_5m()}, {1: act_1h()})
        self.assertEqual(rows, [])
        self.assertEqual(funnel["members-only"], 1)

    def test_members_item_passes_when_included(self):
        rows, _ = rank({1: item(members=True)}, {1: quote()},
                       {1: act_5m()}, {1: act_1h()}, include_members=True)
        self.assertEqual(len(rows), 1)

    def test_null_price_side(self):
        broken = Quote(high=None, high_time=None, low=950, low_time=int(NOW))
        rows, funnel = rank({1: item()}, {1: broken}, {1: act_5m()}, {1: act_1h()})
        self.assertEqual(rows, [])
        self.assertEqual(funnel["null price side"], 1)

    def test_age_uses_the_older_quote_side(self):
        fresh_high_stale_low = Quote(high=1_250, high_time=int(NOW - 10),
                                     low=950, low_time=int(NOW - 4_000))
        rows, funnel = rank({1: item()}, {1: fresh_high_stale_low},
                            {1: act_5m()}, {1: act_1h()})
        self.assertEqual(rows, [])
        self.assertEqual(funnel["quote too old"], 1)

    def test_item_absent_from_1h_counts_as_zero_volume(self):
        rows, funnel = rank({1: item()}, {1: quote()}, {1: act_5m()}, {})
        self.assertEqual(rows, [])
        self.assertEqual(funnel["volume too thin"], 1)

    def test_thin_side_below_minimum(self):
        rows, funnel = rank({1: item()}, {1: quote()}, {1: act_5m()},
                            {1: act_1h(high_volume=500, low_volume=50)})
        self.assertEqual(rows, [])
        self.assertEqual(funnel["volume too thin"], 1)

    def test_zero_volume_floor_does_not_crash_on_missing_1h(self):
        rows, funnel = rank({1: item()}, {1: quote()}, {}, {},
                            min_thin_volume_1h=0)
        # no averages at all: priced on /latest alone, qty 0, still a row
        self.assertEqual(funnel["passed"], 1)
        self.assertEqual(rows[0].qty_per_window, 0)

    def test_roi_gate_drops_taxed_out_margins(self):
        rows, funnel = rank({1: item()}, {1: quote(high=101, low=100)},
                            {1: act_5m(avg_high=101, avg_low=100)},
                            {1: act_1h(avg_high=101, avg_low=100)})
        self.assertEqual(rows, [])
        self.assertEqual(funnel["roi too low"], 1)

    def test_unaffordable_item(self):
        rows, funnel = rank({1: item()}, {1: quote(high=2_000_000, low=1_500_000)},
                            {1: act_5m(avg_high=2_000_000, avg_low=1_500_000)},
                            {1: act_1h(avg_high=2_000_000, avg_low=1_500_000)},
                            capital=1_000_000)
        self.assertEqual(rows, [])
        self.assertEqual(funnel["cannot afford one"], 1)

    def test_price_range_gates_on_the_buy_estimate(self):
        cheap = {1: item(1, name="cheap"), 2: item(2, name="dear")}
        quotes = {1: quote(high=45, low=40), 2: quote(high=1_250, low=950)}
        acts5 = {1: act_5m(avg_high=45, avg_low=40), 2: act_5m()}
        acts1h = {1: act_1h(avg_high=45, avg_low=40), 2: act_1h()}
        rows, funnel = rank(cheap, quotes, acts5, acts1h, min_price=100)
        self.assertEqual([r.name for r in rows], ["dear"])
        self.assertEqual(funnel["price out of range"], 1)
        rows, funnel = rank(cheap, quotes, acts5, acts1h, max_price=100)
        self.assertEqual([r.name for r in rows], ["cheap"])
        self.assertEqual(funnel["price out of range"], 1)

    def test_tax_free_only_keeps_the_sub_50gp_flips(self):
        # sell at 45: floor(45 * 2%) = 0, the whole spread is yours
        items = {1: item(1, name="untaxed"), 2: item(2, name="taxed")}
        quotes = {1: quote(high=45, low=40), 2: quote(high=1_250, low=950)}
        acts5 = {1: act_5m(avg_high=45, avg_low=40), 2: act_5m()}
        acts1h = {1: act_1h(avg_high=45, avg_low=40), 2: act_1h()}
        rows, funnel = rank(items, quotes, acts5, acts1h, tax_free_only=True)
        self.assertEqual([r.name for r in rows], ["untaxed"])
        self.assertEqual(rows[0].tax, 0)
        self.assertEqual(funnel["pays tax"], 1)

    def test_tax_exempt_bond_passes_the_tax_free_filter(self):
        bond_id = 13190
        rows, _ = rank({bond_id: item(bond_id, limit=100)},
                       {bond_id: quote(high=5_000_000, low=4_800_000)},
                       {bond_id: act_5m(avg_high=5_000_000, avg_low=4_800_000)},
                       {bond_id: act_1h(avg_high=5_000_000, avg_low=4_800_000)},
                       capital=100_000_000, slots=1, tax_free_only=True)
        self.assertEqual(len(rows), 1)

    def test_funnel_sums_to_input(self):
        items = {1: item(1), 2: item(2, members=True), 3: item(3)}
        quotes = {1: quote(), 2: quote(), 3: quote(age=9_999), 4: quote()}
        _, funnel = rank(items, quotes, {1: act_5m()}, {1: act_1h()})
        total = sum(v for k, v in funnel.items() if k != "in /latest")
        self.assertEqual(total, funnel["in /latest"])
        self.assertEqual(total, 4)


class PricingTests(unittest.TestCase):
    def test_spike_in_latest_cannot_inflate_the_margin(self):
        # last insta-buy spiked to 1,400 but both averages say 1,250:
        # the sell estimate is 1,250, and the raw quote is kept for display
        rows, _ = rank({1: item()}, {1: quote(high=1_400, low=950)},
                       {1: act_5m(avg_high=1_250, avg_low=950)},
                       {1: act_1h(avg_high=1_250, avg_low=950)})
        row = rows[0]
        self.assertEqual((row.buy, row.sell), (950, 1_250))
        self.assertEqual((row.latest_low, row.latest_high), (950, 1_400))
        self.assertEqual(row.margin, 275)
        self.assertEqual(row.tax, 25)

    def test_optimistic_stale_low_is_raised_to_the_reference(self):
        rows, _ = rank({1: item()}, {1: quote(high=1_250, low=900)},
                       {1: act_5m(avg_high=1_250, avg_low=950)},
                       {1: act_1h(avg_high=1_250, avg_low=950)})
        self.assertEqual(rows[0].buy, 950)

    def test_1h_average_used_when_5m_bucket_is_silent(self):
        rows, _ = rank({1: item()}, {1: quote(high=1_400, low=950)},
                       {},
                       {1: act_1h(avg_high=1_250, avg_low=950)})
        self.assertEqual(rows[0].sell, 1_250)

    def test_thin_5m_bucket_cannot_set_the_buy_price(self):
        # the real Lobster case: /latest and a 13-unit 5m bucket both say the
        # buy side is 34, but 36,170 units traded at 58 in the last hour.
        # Buying at 34 is not executable, so the flip must be rejected.
        rows, funnel = rank(
            {1: item(name="Lobster")},
            {1: quote(high=50, low=34)},
            {1: act_5m(avg_high=50, high_volume=25_396,
                       avg_low=34, low_volume=13)},
            {1: act_1h(avg_high=70, high_volume=125_764,
                       avg_low=58, low_volume=36_170)},
            min_thin_volume_1h=100)
        self.assertEqual(rows, [])
        self.assertEqual(funnel["roi too low"], 1)

    def test_busy_5m_bucket_still_moves_the_estimate(self):
        # same volume in both buckets: the reference is the midpoint, so a
        # genuinely moving market is tracked rather than ignored
        rows, _ = rank({1: item()}, {1: quote(high=1_400, low=900)},
                       {1: act_5m(avg_high=1_200, high_volume=1_000,
                                  avg_low=1_000, low_volume=1_000)},
                       {1: act_1h(avg_high=1_300, high_volume=1_000,
                                  avg_low=900, low_volume=1_000)})
        self.assertEqual((rows[0].buy, rows[0].sell), (950, 1_250))


class QueueStrategyTests(unittest.TestCase):
    """The air rune problem: a huge-volume, one-tick spread is not a flip."""

    def _air_rune(self, **config):
        return rank({1: item(name="Air rune", limit=50_000)},
                    {1: quote(high=6, low=5)},
                    {1: act_5m(avg_high=6, high_volume=40_000,
                               avg_low=5, low_volume=38_000)},
                    {1: act_1h(avg_high=6, high_volume=800_000,
                               avg_low=5, low_volume=760_000)},
                    capital=1_000_000, **config)

    def test_one_tick_spread_is_rejected_by_default(self):
        rows, funnel = self._air_rune()
        self.assertEqual(rows, [])
        self.assertEqual(funnel["no undercut room"], 1)

    def test_it_can_be_shown_but_ranks_badly(self):
        rows, _ = self._air_rune(min_undercut_depth=0)
        self.assertEqual(len(rows), 1)
        air = rows[0]
        self.assertEqual(air.undercut_depth, 0)
        self.assertIn("no room to outbid the queue — you wait your turn",
                      air.warnings)
        # only the queue discount's 15% of the quoted profit survives,
        # less again for the age of the quote
        self.assertAlmostEqual(
            air.expected_gp,
            air.gross_profit * 0.15 * engine.freshness(air.quote_age),
            delta=1.0)

    def test_a_wide_spread_outranks_it_despite_less_volume(self):
        items = {1: item(1, name="Air rune", limit=50_000),
                 2: item(2, name="Leather", limit=13_000)}
        quotes = {1: quote(high=6, low=5), 2: quote(high=192, low=173)}
        acts_5m = {1: act_5m(avg_high=6, high_volume=40_000,
                             avg_low=5, low_volume=38_000),
                   2: act_5m(avg_high=192, high_volume=90,
                             avg_low=173, low_volume=80)}
        acts_1h = {1: act_1h(avg_high=6, high_volume=800_000,
                             avg_low=5, low_volume=760_000),
                   2: act_1h(avg_high=192, high_volume=1_100,
                             avg_low=173, low_volume=1_000)}
        rows, _ = rank(items, quotes, acts_5m, acts_1h,
                       capital=1_000_000, min_undercut_depth=0)
        self.assertEqual(rows[0].name, "Leather")


class AdverseSelectionTests(unittest.TestCase):
    def _with_drift(self, avg_5m_high, avg_5m_low):
        return rank({1: item(limit=10_000)}, {1: quote(high=1_250, low=950)},
                    {1: act_5m(avg_high=avg_5m_high, avg_low=avg_5m_low,
                               high_volume=500, low_volume=500)},
                    {1: act_1h(avg_high=1_250, avg_low=950,
                               high_volume=500, low_volume=500)},
                    capital=10_000_000)

    def test_falling_market_lowers_expected_value(self):
        falling, _ = self._with_drift(1_150, 850)
        flat, _ = self._with_drift(1_250, 950)
        self.assertLess(falling[0].drift, 0)
        self.assertLess(falling[0].expected_gp / falling[0].gross_profit,
                        flat[0].expected_gp / flat[0].gross_profit)

    def test_falling_market_is_flagged(self):
        falling, _ = self._with_drift(1_150, 850)
        self.assertTrue(any("falling" in w for w in falling[0].warnings))


class SlotAllocationTests(unittest.TestCase):
    def test_capital_is_split_across_slots(self):
        # 3 slots and 3m gp means 1m per flip, not 3m on the top row
        rows, _ = rank({1: item(limit=10_000)}, {1: quote(high=1_250, low=950)},
                       {1: act_5m()}, {1: act_1h(high_volume=5_000,
                                                 low_volume=5_000)},
                       capital=3_000_000, slots=3)
        self.assertEqual(rows[0].qty_per_window, 1_000_000 // 950)

    def test_more_slots_means_smaller_positions(self):
        def qty(slots):
            rows, _ = rank({1: item(limit=10_000)},
                           {1: quote(high=1_250, low=950)}, {1: act_5m()},
                           {1: act_1h(high_volume=5_000, low_volume=5_000)},
                           capital=3_000_000, slots=slots)
            return rows[0].qty_per_window
        self.assertGreater(qty(3), qty(8))

    def test_capital_needed_is_reported(self):
        rows, _ = rank({1: item(limit=100)}, {1: quote(high=1_250, low=950)},
                       {1: act_5m()}, {1: act_1h()}, capital=10_000_000, slots=1)
        self.assertEqual(rows[0].capital_needed, 100 * 950)


def history_bucket(avg_high, high_vol, avg_low, low_vol):
    return {"avgHighPrice": avg_high, "highPriceVolume": high_vol,
            "avgLowPrice": avg_low, "lowPriceVolume": low_vol}


class RefineTests(unittest.TestCase):
    """Stage 2: the salmon case — intraday says buy, 14 days say you won't."""

    def _salmon_rows(self):
        # Intraday: dumper active for the last hour, so the whole intraday
        # pipeline (latest, 5m, 1h) agrees the buy side is ~30.
        items = {1: item(1, name="Salmon", limit=15_000),
                 2: item(2, name="Leather", limit=13_000)}
        quotes = {1: quote(high=42, low=30), 2: quote(high=192, low=173)}
        acts_5m = {1: act_5m(avg_high=42, high_volume=900, avg_low=30,
                             low_volume=700),
                   2: act_5m(avg_high=192, high_volume=90, avg_low=173,
                             low_volume=80)}
        acts_1h = {1: act_1h(avg_high=42, high_volume=9_000, avg_low=30,
                             low_volume=7_000),
                   2: act_1h(avg_high=192, high_volume=1_100, avg_low=173,
                             low_volume=1_000)}
        return rank(items, quotes, acts_5m, acts_1h, capital=80_000, slots=1)

    def _histories(self):
        # 14 days of truth: salmon sellers accepted ~40 for all real volume;
        # leather traded exactly where it is quoted now.
        salmon = ([history_bucket(42, 5_000, 40, 5_000)] * 55
                  + [history_bucket(42, 5_000, 30, 700)])
        leather = [history_bucket(192, 1_000, 173, 1_000)] * 56
        return {1: salmon, 2: leather}

    def test_intraday_alone_loves_the_salmon_dump(self):
        rows, _ = self._salmon_rows()
        self.assertEqual(rows[0].name, "Salmon")

    def test_history_collapses_it(self):
        rows, _ = self._salmon_rows()
        refined, count = filters.refine_with_history(
            rows, lambda i: self._histories()[i], top_k=15)
        self.assertEqual(count, 2)
        self.assertEqual(refined[0].name, "Leather")
        salmon = next(r for r in refined if r.name == "Salmon")
        self.assertEqual(salmon.fill_factor, engine.FILL_FLOOR)
        self.assertTrue(any("below the 14-day average" in w
                            for w in salmon.warnings))
        self.assertTrue(any("14-day volume" in w for w in salmon.warnings))

    def test_flat_item_keeps_roughly_its_stage1_ev(self):
        rows, _ = self._salmon_rows()
        leather = next(r for r in rows if r.name == "Leather")
        refined, _ = filters.refine_with_history(
            rows, lambda i: self._histories()[i], top_k=15)
        leather_after = next(r for r in refined if r.name == "Leather")
        self.assertAlmostEqual(leather_after.expected_gp, leather.expected_gp)
        self.assertEqual(leather_after.fill_factor, 1.0)

    def test_flat_twin_outranks_the_riser(self):
        # identical intraday state, identical quotes: only the 14-day shape
        # differs. The riser ends at today's quote; the flat twin sat there
        # all along. The stable item wins: a riser is indistinguishable from
        # a pump in price data, so it carries reversion risk and no bonus.
        items = {1: item(1, name="flat"), 2: item(2, name="rising")}
        quotes = {n: quote(high=12_600, low=12_200) for n in (1, 2)}
        acts = {n: act_5m(avg_high=12_600, avg_low=12_200) for n in (1, 2)}
        acts1h = {n: act_1h(avg_high=12_600, avg_low=12_200) for n in (1, 2)}
        rows, _ = rank(items, quotes, acts, acts1h, capital=100_000_000)
        flat = [history_bucket(12_600, 1_000, 12_200, 1_000)] * 56
        growth = 1.004
        rising = [history_bucket(round(12_600 * growth ** (i - 55)), 1_000,
                                 round(12_200 * growth ** (i - 55)), 1_000)
                  for i in range(56)]
        refined, _ = filters.refine_with_history(
            rows, lambda i: {1: flat, 2: rising}[i], top_k=15)
        self.assertEqual(refined[0].name, "flat")
        flat_row = refined[0]
        self.assertEqual(flat_row.momentum, 1.0)
        self.assertEqual(flat_row.fill_factor, 1.0)
        self.assertEqual(flat_row.level_factor, 1.0)
        riser = next(r for r in refined if r.name == "rising")
        self.assertEqual(riser.momentum, 1.0)      # no bonus for rising
        self.assertLess(riser.level_factor, 1.0)   # reversion risk instead
        self.assertTrue(any("don't chase" in w for w in riser.warnings))

    def test_pumped_item_collapses_against_its_flat_twin(self):
        # the user's complaint: an item pumped well above its normal level
        # shows a juicy margin but is a manipulation trap
        items = {1: item(1, name="pumped"), 2: item(2, name="calm")}
        quotes = {n: quote(high=820, low=780) for n in (1, 2)}
        acts = {n: act_5m(avg_high=820, avg_low=780) for n in (1, 2)}
        acts1h = {n: act_1h(avg_high=820, avg_low=780) for n in (1, 2)}
        rows, _ = rank(items, quotes, acts, acts1h, capital=50_000_000)
        pumped = ([history_bucket(510, 1_000, 490, 1_000)] * 50
                  + [history_bucket(820, 3_000, 780, 3_000)] * 6)
        calm = [history_bucket(820, 1_000, 780, 1_000)] * 56
        refined, _ = filters.refine_with_history(
            rows, lambda i: {1: pumped, 2: calm}[i], top_k=15)
        self.assertEqual(refined[0].name, "calm")
        pump_row = next(r for r in refined if r.name == "pumped")
        self.assertEqual(pump_row.level_factor, engine.LEVEL_FLOOR)
        self.assertTrue(any("spike or manipulation" in w
                            for w in pump_row.warnings))
        self.assertLess(pump_row.expected_gp, refined[0].expected_gp / 5)

    def test_missing_history_keeps_stage1_and_flags_it(self):
        rows, _ = self._salmon_rows()
        refined, count = filters.refine_with_history(
            rows, lambda i: None, top_k=15)
        self.assertEqual(count, 0)
        self.assertEqual([r.name for r in refined], [r.name for r in rows])
        self.assertTrue(all("no usable 14-day history" in r.warnings[-1]
                            for r in refined))

    def test_top_k_zero_changes_nothing(self):
        rows, _ = self._salmon_rows()
        refined, count = filters.refine_with_history(rows, lambda i: [], 0)
        self.assertEqual(count, 0)
        self.assertEqual(refined, rows)


class PassingRowTests(unittest.TestCase):
    def test_row_fields(self):
        rows, funnel = rank({1: item(limit=10_000)},
                            {1: quote(high=1_250, low=950, age=60)},
                            {1: act_5m()},
                            {1: act_1h(high_volume=500, low_volume=400)},
                            capital=1_000_000, slots=1)
        self.assertEqual(funnel["passed"], 1)
        row = rows[0]
        self.assertEqual(row.tax, 25)
        self.assertEqual(row.margin, 275)
        self.assertAlmostEqual(row.roi, 275 / 950)
        self.assertEqual(row.thin_volume_1h, 400)
        # min(limit 10,000, 400*4=1,600, capital//950=1,052) = 1,052
        self.assertEqual(row.qty_per_window, 1_052)
        self.assertEqual(row.gross_profit, 275 * 1_052)
        self.assertEqual(row.quote_age, 60)
        self.assertEqual(row.gp_per_slot_hour, row.expected_gp / 4)

    def test_null_limit_capped_by_volume(self):
        rows, _ = rank({1: item(limit=None)}, {1: quote(high=1_250, low=950)},
                       {1: act_5m()},
                       {1: act_1h(high_volume=200, low_volume=150)},
                       capital=100_000_000)
        self.assertEqual(rows[0].qty_per_window, 150 * 4)
        self.assertIn("no published buy limit", rows[0].warnings)

    def test_bond_is_tax_exempt(self):
        bond_id = 13190
        rows, _ = rank({bond_id: item(bond_id, limit=100)},
                       {bond_id: quote(high=5_000_000, low=4_800_000)},
                       {bond_id: act_5m(avg_high=5_000_000, avg_low=4_800_000)},
                       {bond_id: act_1h(avg_high=5_000_000, avg_low=4_800_000)},
                       capital=100_000_000, slots=1)
        self.assertEqual(rows[0].tax, 0)
        self.assertEqual(rows[0].margin, 200_000)

    def test_rows_sorted_by_expected_value_desc(self):
        items = {1: item(1, name="small"), 2: item(2, name="big")}
        quotes = {1: quote(high=1_000, low=950), 2: quote(high=1_250, low=950)}
        acts_5m = {1: act_5m(avg_high=1_000), 2: act_5m()}
        acts_1h = {1: act_1h(avg_high=1_000), 2: act_1h()}
        rows, _ = rank(items, quotes, acts_5m, acts_1h)
        self.assertEqual([r.name for r in rows], ["big", "small"])
        self.assertGreater(rows[0].gp_per_slot_hour, rows[1].gp_per_slot_hour)


if __name__ == "__main__":
    unittest.main()
