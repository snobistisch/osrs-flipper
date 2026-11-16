"""Unit tests for journal.py — run with: python3 -m unittest tests.test_journal -v"""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import engine
import journal


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.j = journal.Journal(":memory:")

    def tearDown(self):
        self.j.close()

    def test_open_then_close_realises_taxed_profit(self):
        flip_id = self.j.open_flip("Steel bar", quantity=100, buy_price=950)
        self.j.close_flip(flip_id, sell_price=1_250)
        row = self.j.rows()[0]
        # per item: 1250 - 25 tax - 950 = 275
        self.assertEqual(journal.realised_profit(row), 27_500)

    def test_open_position_has_no_realised_profit(self):
        self.j.open_flip("Lobster", quantity=50, buy_price=88)
        self.assertIsNone(journal.realised_profit(self.j.rows()[0]))

    def test_bond_flip_includes_conversion_fee(self):
        flip_id = self.j.open_flip("Old school bond", quantity=1,
                                   buy_price=4_800_000, item_id=13190)
        self.j.close_flip(flip_id, sell_price=5_000_000)
        self.assertEqual(journal.realised_profit(self.j.rows()[0]), -300_000)

    def test_recent_buys_feed_the_buy_limit_usage(self):
        now = 1_790_000_000
        self.j.open_flip("Prayer potion(4)", quantity=300, buy_price=9_000,
                         item_id=2434, bought_at=now - 3_600)
        self.j.open_flip("Steel bar", quantity=50, buy_price=500,
                         item_id=2353, bought_at=now - 4 * 3_600 - 60)
        never = self.j.place_offer("Steel bar", quantity=40, buy_price=500,
                                   item_id=2353, placed_at=now - 600)
        self.j.cancel_flip(never, cancelled_at=now - 300)
        self.j.place_offer("Steel bar", quantity=20, buy_price=500,
                           item_id=2353, placed_at=now - 300)
        self.assertEqual(
            sorted((e["item_id"], e["limit_group"], e["qty"])
                   for e in self.j.recent_buys(now)),
            [(2353, None, 20), (2434, "potion:prayer potion", 300)])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.db"
            self.assertIsNone(journal.recent_limit_usage(path, now))
            with journal.Journal(path) as store:
                store.open_flip("Steel bar", quantity=7, buy_price=500,
                                item_id=2353, bought_at=now - 60)
            usage = journal.recent_limit_usage(path, now)
            self.assertEqual(usage.used(2353, None), 7)

    def test_unrecorded_exemption_is_resolved_by_name(self):
        flip_id = self.j.open_flip("Lobster", quantity=10, buy_price=100)
        self.j.close_flip(flip_id, sell_price=110)
        self.assertEqual(journal.realised_profit(self.j.rows()[0]), 100)

    def test_cli_records_the_exemption_in_force_at_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "journal.db")
            with redirect_stdout(io.StringIO()):
                journal.main(["--db", db, "open", "--name", "Lobster",
                              "--qty", "10", "--buy", "100"])
                journal.main(["--db", db, "open", "--name", "Steel bar",
                              "--qty", "10", "--buy", "100"])
                journal.main(["--db", db, "open", "--name", "Lobster",
                              "--qty", "10", "--buy", "100",
                              "--no-tax-exempt"])
            with journal.Journal(db) as stored:
                self.assertEqual([row["tax_exempt"] for row in stored.rows()],
                                 [1, 0, 0])

    def test_closing_twice_fails(self):
        flip_id = self.j.open_flip("Coal", quantity=10, buy_price=150)
        self.j.close_flip(flip_id, sell_price=160)
        with self.assertRaises(ValueError):
            self.j.close_flip(flip_id, sell_price=170)

    def test_closing_unknown_id_fails(self):
        with self.assertRaises(ValueError):
            self.j.close_flip(999, sell_price=100)

    def test_invalid_open_rejected(self):
        with self.assertRaises(ValueError):
            self.j.open_flip("Air rune", quantity=0, buy_price=5)
        with self.assertRaises(ValueError):
            self.j.open_flip("Air rune", quantity=10, buy_price=0)

    def test_stats_compare_predicted_with_realised(self):
        a = self.j.open_flip("Steel bar", 100, 950, predicted_margin=275)
        self.j.close_flip(a, 1_250)          # realised 275/item, as predicted
        b = self.j.open_flip("Lobster", 100, 88, predicted_margin=10)
        # Lobster is GE-tax exempt: realised 3/item, predicted 10. This
        # asserted 2/item while unrecorded exemptions fell back to ids only.
        self.j.close_flip(b, 91)
        self.j.open_flip("Coal", 10, 150)    # still open, excluded
        s = self.j.stats()
        self.assertEqual(s["flips_closed"], 2)
        self.assertEqual(s["realised_profit"], 27_500 + 300)
        self.assertEqual(s["flips_with_prediction"], 2)
        self.assertEqual(s["predicted_profit"], 27_500 + 1_000)
        self.assertEqual(s["realised_on_predicted"], 27_500 + 300)

    def test_row_snapshot_keeps_overnight_risk_prediction(self):
        prediction = SimpleNamespace(
            item_id=4151, margin=25_000, buy=2_400_000, sell=2_475_000,
            expected_gp=18_000, gp_per_slot_hour=2_250,
            expected_buy_seconds=1_200, expected_sell_seconds=3_600,
            p_fill=0.71, trade_mode=engine.TradeMode.OVERNIGHT,
            horizon_hours=8, ranking_value=18_000, p_stranded=0.29,
            downside_risk_gp=7_500, tax_exempt=False, factors={"edge": 0.9})
        self.j.open_flip("Abyssal whip", 1, 2_400_000, row=prediction)
        row = self.j.rows()[0]
        self.assertEqual(row["trade_mode"], "overnight")
        self.assertEqual(row["prediction_horizon_hours"], 8)
        self.assertAlmostEqual(row["predicted_stranded_probability"], 0.29)
        self.assertEqual(row["predicted_downside_risk_gp"], 7_500)


if __name__ == "__main__":
    unittest.main()
