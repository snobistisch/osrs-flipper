"""Unit tests for journal.py — run with: python3 -m unittest test_journal -v"""
import unittest

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

    def test_bond_flip_is_tax_free(self):
        flip_id = self.j.open_flip("Old school bond", quantity=1,
                                   buy_price=4_800_000, item_id=13190)
        self.j.close_flip(flip_id, sell_price=5_000_000)
        self.assertEqual(journal.realised_profit(self.j.rows()[0]), 200_000)

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
        self.j.close_flip(b, 91)             # realised 2/item, predicted 10
        self.j.open_flip("Coal", 10, 150)    # still open, excluded
        s = self.j.stats()
        self.assertEqual(s["flips_closed"], 2)
        self.assertEqual(s["realised_profit"], 27_500 + 200)
        self.assertEqual(s["flips_with_prediction"], 2)
        self.assertEqual(s["predicted_profit"], 27_500 + 1_000)
        self.assertEqual(s["realised_on_predicted"], 27_500 + 200)


if __name__ == "__main__":
    unittest.main()
