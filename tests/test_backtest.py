"""The backtest harness: no look-ahead, a conservative fill simulator,
deterministic output, and honest metrics.

Synthetic panels are built in memory so each rule is tested in isolation; the
committed fixture (real prices, a small slice) is used for the end-to-end run.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
except ImportError:                      # the CLI and agent stay stdlib-only
    np = None

if np is not None:
    from backtest import metrics, panel as panel_module, rankers, run, simulate
    from backtest.panel import Panel
    from backtest.simulate import Offer, SimConfig

T0 = 1_790_000_000 // 21600 * 21600      # aligned to a 6h edge
FIXTURE = Path(__file__).parent / "fixtures" / "backtest_panel.npz"
MAPPING = [
    {"id": 1, "name": "Alpha", "members": True, "limit": 1000, "value": 1,
     "highalch": 60},
    {"id": 2, "name": "Beta", "members": False, "limit": 100, "value": 1,
     "highalch": None},
]


def make_panel(hours=72, low=100, high=110, volume=50, seed=0):
    """Two items, constant prices, steady two-sided volume."""
    rng = np.random.default_rng(seed)
    n5, n1 = hours * 12, hours
    shape5, shape1 = (n5, len(MAPPING)), (n1, len(MAPPING))
    a5 = {"hp": np.full(shape5, high, np.uint32),
          "lp": np.full(shape5, low, np.uint32),
          "hv": rng.integers(volume, volume + 5, shape5).astype(np.uint32),
          "lv": rng.integers(volume, volume + 5, shape5).astype(np.uint32)}
    a1 = {"hp": np.full(shape1, high, np.uint32),
          "lp": np.full(shape1, low, np.uint32),
          "hv": np.full(shape1, volume * 12, np.uint32),
          "lv": np.full(shape1, volume * 12, np.uint32)}
    return Panel(np.array([1, 2]), panel_module.parse_mapping(MAPPING),
                 T0, a5, T0, a1)


def one_item(lp, lv, hp, hv, limit=None):
    """A one-item panel from explicit 5m series, for the simulator."""
    def column(values):
        return np.array(values, dtype=np.uint32).reshape(-1, 1)
    a5 = {"lp": column(lp), "lv": column(lv), "hp": column(hp), "hv": column(hv)}
    hours = max(1, len(lp) // 12)
    a1 = {key: np.zeros((hours, 1), np.uint32) for key in a5}
    mapping = [{"id": 7, "name": "Solo", "members": True, "limit": limit,
                "value": 1, "highalch": None}]
    return Panel(np.array([7]), panel_module.parse_mapping(mapping),
                 T0, a5, T0, a1)


@unittest.skipIf(np is None, "numpy is required for the backtest harness")
class LookAheadTests(unittest.TestCase):
    def test_snapshot_ignores_every_bucket_that_had_not_closed(self):
        panel = make_panel()
        t = T0 + 20 * 3600 + 900
        before = panel.snapshot(t)
        history = panel.history_6h(1, t)
        recent = panel.recent_5m(1, t)
        row5, row1 = panel.closed_5m(t), panel.closed_1h(t)
        for arrays, row in ((panel.a5, row5), (panel.a1, row1)):
            for field in panel_module.FIELDS:
                arrays[field][row:] = 4_000_000       # poison the future
        panel._six_hour = None
        after = panel.snapshot(t)
        self.assertEqual(before.quotes, after.quotes)
        self.assertEqual(before.activity_5m, after.activity_5m)
        self.assertEqual(before.activity_1h, after.activity_1h)
        self.assertEqual(history, panel.history_6h(1, t))
        self.assertEqual(recent, panel.recent_5m(1, t))

    def test_a_bucket_is_visible_only_once_it_has_closed(self):
        panel = make_panel()
        panel.a5["lp"][30, 0] = 77                    # bucket [T0+9000, T0+9300)
        open_time = T0 + 30 * 300
        self.assertEqual(panel.snapshot(open_time + 299)
                         .activity_5m[1].avg_low, 100)
        seen = panel.snapshot(open_time + 300)
        self.assertEqual(seen.activity_5m[1].avg_low, 77)
        self.assertEqual(seen.quotes[1].low, 77)
        self.assertLessEqual(seen.quotes[1].low_time, open_time + 300)

    def test_history_holds_only_complete_six_hour_buckets(self):
        panel = make_panel()
        points = panel.history_6h(1, T0 + 13 * 3600)
        self.assertEqual([p["timestamp"] for p in points], [T0, T0 + 21600])
        self.assertEqual(points[0]["lowPriceVolume"], 6 * 600)

    def test_simulator_reads_only_buckets_from_the_decision_time_on(self):
        panel = make_panel()
        t = T0 + 5 * 3600
        future = panel.future_5m(1, t, 3600)
        self.assertEqual(future["lp"].shape[0], 12)
        panel.a5["lp"][:panel.closed_5m(t)] = 1       # the past changes
        again = panel.future_5m(1, t, 3600)
        self.assertTrue((future["lp"] == again["lp"]).all())


@unittest.skipIf(np is None, "numpy is required for the backtest harness")
class SimulatorTests(unittest.TestCase):
    def run_offer(self, panel, buy, sell, qty, limit=None, **config):
        return simulate.simulate(
            panel, Offer(7, buy, sell, qty, limit=limit), T0,
            SimConfig(**{"capture": 1.0, **config}))

    def test_never_fills_at_a_price_the_market_did_not_reach(self):
        panel = one_item([101] * 48, [500] * 48, [110] * 48, [500] * 48)
        outcome = self.run_offer(panel, 100, 110, 50)
        self.assertEqual((outcome.bought, outcome.sold, outcome.pnl), (0, 0, 0.0))
        self.assertFalse(outcome.completed)
        # The slot is still held until the buy is cancelled at half the window.
        self.assertAlmostEqual(outcome.slot_hours, 2.0)

    def test_sell_never_fills_above_where_buyers_traded(self):
        panel = one_item([100] * 48, [500] * 48, [109] * 48, [500] * 48)
        outcome = self.run_offer(panel, 100, 110, 50)
        self.assertEqual((outcome.bought, outcome.sold, outcome.dumped),
                         (50, 0, 50))
        # Dumped at the next instant-sell price, 100, less 2% tax.
        self.assertEqual(outcome.dump_price, 100)
        self.assertEqual(outcome.pnl, 50 * (100 - 2) - 50 * 100)
        # A patient seller is eventually lifted at 109, less tax.
        self.assertEqual(outcome.pnl_patient, 50 * (109 - 2) - 50 * 100)

    def test_completed_flip_earns_the_margin_after_tax(self):
        panel = one_item([100] * 48, [500] * 48, [110] * 48, [500] * 48)
        outcome = self.run_offer(panel, 100, 110, 50)
        self.assertTrue(outcome.completed)
        self.assertEqual(outcome.pnl, 50 * (110 - 2 - 100))
        self.assertEqual(outcome.completion_seconds, 600)   # buy, then sell
        self.assertAlmostEqual(outcome.slot_hours, 2 / 12)

    def test_strict_rule_needs_the_price_to_trade_through(self):
        panel = one_item([100] * 48, [500] * 48, [110] * 48, [500] * 48)
        self.assertEqual(self.run_offer(panel, 100, 110, 50, strict=True).bought, 0)
        through = self.run_offer(panel, 101, 109, 50, strict=True)
        self.assertTrue(through.completed)

    def test_fills_are_capped_by_crossing_volume_and_the_haircut(self):
        panel = one_item([100] * 48, [10] * 48, [110] * 48, [10] * 48)
        full = self.run_offer(panel, 100, 110, 10_000)
        self.assertEqual(full.bought, 24 * 10)          # buy open for 2 of 4h
        tenth = self.run_offer(panel, 100, 110, 10_000, capture=0.10)
        self.assertLess(tenth.bought, 0.25 * full.bought)
        self.assertEqual(self.run_offer(panel, 100, 110, 10_000,
                                        capture=0.0).bought, 0)

    def test_a_unit_is_sold_only_after_it_was_bought(self):
        # Buyers only appear in bucket 0; sellers only from bucket 1.
        panel = one_item([0] + [100] * 47, [0] + [500] * 47,
                         [110] + [0] * 47, [500] + [0] * 47)
        outcome = self.run_offer(panel, 100, 110, 50)
        self.assertEqual((outcome.bought, outcome.sold), (50, 0))

    def test_buy_limit_caps_each_four_hour_window(self):
        panel = one_item([100] * 144, [500] * 144, [110] * 144, [500] * 144)
        outcome = self.run_offer(panel, 100, 110, 1000, limit=70,
                                 mode="overnight", horizon_hours=8.0)
        self.assertEqual(outcome.bought, 140)            # two windows of 70

    def test_away_cannot_sell_before_the_player_is_back(self):
        hp = [110] * 96 + [0] * 48                       # buyers leave at 8h
        hv = [500] * 96 + [0] * 48
        panel = one_item([100] * 144, [500] * 144, hp, hv)
        outcome = self.run_offer(panel, 100, 110, 50, mode="overnight",
                                 horizon_hours=8.0)
        self.assertEqual((outcome.bought, outcome.sold), (50, 0))
        self.assertAlmostEqual(outcome.slot_hours, 12.0)

    def test_same_seed_same_outcome_and_shared_luck_across_prices(self):
        rng = np.random.default_rng(3)
        lv = rng.integers(1, 40, 48)
        panel = one_item([100] * 48, lv, [110] * 48, lv)
        first = self.run_offer(panel, 100, 110, 500, capture=0.3)
        again = self.run_offer(panel, 100, 110, 500, capture=0.3)
        self.assertEqual(first, again)
        other = self.run_offer(panel, 100, 110, 500, capture=0.3, seed=1)
        self.assertNotEqual(first.bought, other.bought)
        # A higher bid sees the same draws, so it can never buy fewer units.
        higher = self.run_offer(panel, 105, 110, 500, capture=0.3)
        self.assertGreaterEqual(higher.bought, first.bought)

    def test_capital_and_slot_time_are_accounted(self):
        panel = one_item([100] * 48, [500] * 48, [110] * 48, [500] * 48)
        outcome = self.run_offer(panel, 100, 110, 50)
        self.assertEqual(outcome.capital, 5000)
        # Coins locked in the offer for one bucket, then inventory at cost
        # for one bucket: 5,000 gp for ten minutes.
        self.assertAlmostEqual(outcome.capital_gp_hours, 2 * 5000 / 12)


@unittest.skipIf(np is None, "numpy is required for the backtest harness")
class ScheduleAndMetricTests(unittest.TestCase):
    def test_tuning_offers_end_before_the_holdout_starts(self):
        panel = make_panel(hours=24 * 30)
        split = run.holdout_start(panel)
        for strategy, (_, _, lifetime, _) in run.STRATEGIES.items():
            tune = [t for seg in run.segments(panel, strategy, "tune") for t in seg]
            hold = [t for seg in run.segments(panel, strategy, "holdout")
                    for t in seg]
            self.assertTrue(tune and hold, strategy)
            # Embargo: the last tuning offer has been dumped before the split.
            self.assertTrue(all(t + lifetime * 3600 <= split for t in tune))
            self.assertTrue(all(t >= split for t in hold))
            self.assertTrue(all(t + lifetime * 3600 <= panel.end for t in hold))
            self.assertEqual(run.segments(panel, strategy, "tune"),
                             run.segments(panel, strategy, "tune"))

    def test_bank_frees_slots_on_release_and_tracks_the_buy_limit(self):
        bank = run.Bank(1000, slots=2)
        plan = rankers.Planned(Offer(7, 100, 110, 6, limit=10), "Solo", 100, {})
        outcome = simulate.Outcome(6, 6, 6, 0, 48.0, 600, 50.0, 0.5, True,
                                   1800.0, 300.0, 300.0, None)
        bank.place(0, plan, outcome)
        self.assertEqual((bank.cash, bank.free_slots), (400.0, 1))
        self.assertEqual(bank.excluded({7: 10}), frozenset({7}))   # still open
        bank.collect(1799)
        self.assertEqual(bank.free_slots, 1)          # not released yet
        bank.collect(1800)
        self.assertEqual((bank.cash, bank.free_slots), (1048.0, 2))
        # Released, and 4 of the 10-unit limit are left inside the window.
        self.assertEqual(bank.excluded({7: 10}), frozenset())
        self.assertEqual(bank.limit_left(7, 10), 4)
        self.assertEqual(bank.excluded({7: 6}), frozenset({7}))
        self.assertIsNone(bank.limit_left(7, None))
        bank.collect(4 * 3600)
        self.assertEqual(bank.limit_left(7, 10), 10)

    def record(self, pnls, method="m"):
        flips = [{"t": day * 86400, "buy": 100, "bought": 10, "locked": 1000,
                  "pnl": pnl, "pnl_patient": pnl + 10, "slot_h": 1.0,
                  "cap_h": 1e6, "done": int(pnl > 0),
                  "done_s": 600.0 if pnl > 0 else None,
                  "pred": {"p_fill": 0.8, "expected_gp": 50.0, "p50": 300,
                           "p80": 900, "p90": 1200}}
                 for day, pnl in enumerate(pnls)]
        equity, total = [], 1000.0
        for day, pnl in enumerate(pnls):
            equity.append((day * 86400, total, 1, 500))
            total += pnl
        bank = {"final": total, "equity": equity, "flips": flips}
        return {"strategy": "active", "step_hours": 4.0, "steps": len(pnls),
                "banks": {method: {"v": bank}, "base": {"v": bank}}}

    def test_ratios_drawdown_and_calibration(self):
        records = [self.record([100, -300, 50, 200])]
        point = metrics.summarise(records, "m", "v", capital=1000, slots=2)
        self.assertAlmostEqual(point["bank_gp_hour"], 50 / 16)
        self.assertAlmostEqual(point["bank_gp_hour_patient"], 90 / 16)
        self.assertAlmostEqual(point["gp_slot_hour"], 50 / 4)
        self.assertAlmostEqual(point["gp_capital_hour"], 50 / 4)
        self.assertAlmostEqual(point["roi"], 50 / 4000)
        self.assertAlmostEqual(point["win_rate"], 0.75)
        self.assertAlmostEqual(point["max_drawdown"], 0.3)
        self.assertAlmostEqual(point["slots_used"], 0.5)
        table = metrics.reliability(records, "m", "v")
        self.assertEqual(table[0]["n"], 4)
        self.assertAlmostEqual(metrics.calibration_error(table), 0.05)
        self.assertAlmostEqual(metrics.time_band(records, "m", "v")["p80"], 0.75)
        self.assertAlmostEqual(metrics.ev_capture(records, "m", "v")["capture"],
                               50 / 200)

    def test_bootstrap_is_seeded_and_pairs_methods_by_day(self):
        records = [self.record([100, -300, 50, 200, 80, -20])]
        first = metrics.bootstrap(records, "m", "v", "base", draws=200)
        self.assertEqual(first, metrics.bootstrap(records, "m", "v", "base",
                                                  draws=200))
        interval = first["bank_gp_hour"]
        self.assertLess(interval["lo"], interval["hi"])
        # Identical methods: the paired difference is exactly zero, and a
        # method that is no better than the baseline gets p = 1.
        self.assertEqual((interval["diff_lo"], interval["diff_hi"]), (0.0, 0.0))
        self.assertEqual(interval["p_worse"], 1.0)


@unittest.skipIf(np is None or not FIXTURE.exists(),
                 "numpy and the committed fixture are required")
class FixtureRunTests(unittest.TestCase):
    METHODS = ["current", "naive_roi", "random"]

    def test_walk_forward_on_the_fixture_is_deterministic_and_solvent(self):
        with tempfile.TemporaryDirectory() as folder:
            outputs = []
            for name in ("a", "b"):
                out = Path(folder) / (name + ".jsonl")
                run.run(FIXTURE, out, ("active",), "all", 2_000_000,
                        "members", self.METHODS, 1)
                outputs.append(out.read_text(encoding="utf-8"))
            self.assertEqual(outputs[0], outputs[1])
            meta, records = run.load(Path(folder) / "a.jsonl")
            self.assertEqual(meta["methods"], self.METHODS)
            self.assertEqual(len(meta["variants"]), 6)
            self.assertTrue(records)
            placed = 0
            for record in records:
                for by_variant in record["banks"].values():
                    self.assertEqual(set(by_variant), set(meta["variants"]))
                    for bank in by_variant.values():
                        for _, equity, used, locked in bank["equity"]:
                            self.assertLessEqual(used, 8)
                            self.assertLessEqual(locked, equity + 1e-6)
                        for flip in bank["flips"]:
                            placed += 1
                            self.assertLessEqual(flip["sold"], flip["bought"])
                            self.assertLessEqual(flip["bought"], flip["qty"])
                        # The books balance: final equity is the bank plus
                        # every flip's realised profit.
                        self.assertAlmostEqual(
                            bank["final"], 2_000_000 + sum(
                                flip["pnl"] for flip in bank["flips"]), 0)
            self.assertGreater(placed, 0)

    def test_no_item_exceeds_its_buy_limit_inside_one_window(self):
        panel = Panel.load(FIXTURE)
        times = run.segments(panel, "active", "all")[0]
        record = run.run_segment(panel, "active", times, 2_000_000,
                                 "free-to-play", self.METHODS, None)
        json.dumps(record)                 # the record must be serialisable
        for by_variant in record["banks"].values():
            for bank in by_variant.values():
                placed = {}
                for flip in bank["flips"]:
                    limit = panel.items[flip["id"]].limit
                    window = [qty for t, qty in placed.get(flip["id"], [])
                              if t + 4 * 3600 > flip["t"]]
                    if limit is not None:
                        self.assertLessEqual(sum(window) + flip["qty"], limit)
                    placed.setdefault(flip["id"], []).append(
                        (flip["t"], flip["qty"]))
                self.assertTrue(all(used <= 3 for _, _, used, _ in bank["equity"]))


if __name__ == "__main__":
    unittest.main()
