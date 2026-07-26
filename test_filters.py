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
