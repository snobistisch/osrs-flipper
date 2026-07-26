"""Tests for the agent layer, with no network access.

Run with: python3 -m unittest test_agent -v

What matters here is the state machine. An agent that re-reports the same
crash every fifteen minutes is worse than no agent, and that failure is
invisible in a single run — it only shows up on the second one. So most of
these tests run the logic twice and assert on the silence.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import agent
import merch


def view(depth=None, volume_ratio=1.0, raw_change=None, relative=None,
         trend=None, price=1000):
    return merch.DailyView(
        days=365, trend=trend, price=price, median_14d=price, depth=depth,
        volume_today=100.0, volume_baseline=100.0, volume_ratio=volume_ratio,
        volume_change_6m=raw_change,
        crash=merch.crash_signal(depth, volume_ratio),
        volume_change_relative=relative, market_drift=-0.5,
        supply=merch.supply_crunch_badge(relative))


class SignalExtractionTests(unittest.TestCase):
    def test_a_crash_becomes_a_signal(self):
        signals = agent.signals_from_view(329, "Salmon",
                                          view(depth=-0.55, volume_ratio=15.0))
        self.assertEqual([s.kind for s in signals], [merch.CRASH])
        self.assertAlmostEqual(signals[0].magnitude, 0.55, places=6)

    def test_a_quiet_ordinary_item_produces_nothing(self):
        self.assertEqual(agent.signals_from_view(1, "x", view(depth=-0.01)), [])

    def test_a_supply_badge_reports_both_numbers(self):
        signals = agent.signals_from_view(
            21079, "Arcane prayer scroll",
            view(raw_change=-0.95, relative=-0.90))
        self.assertEqual(signals[0].kind, merch.SUPPLY_CRUNCH)
        self.assertIn("market", signals[0].message)
        self.assertIn("market_drift", signals[0].detail)


class WatchStateTests(unittest.TestCase):
    """A signal fires once. It fires again only when it gets worse."""

    def setUp(self):
        self.crash = agent.Signal(
            item_id=329, name="Salmon", kind=merch.CRASH, magnitude=0.55,
            price=15, message="down a lot")

    def test_the_first_sighting_fires(self):
        fired, _ = agent.new_signals([self.crash], {})
        self.assertEqual(len(fired), 1)

    def test_the_second_sighting_is_silent(self):
        _, state = agent.new_signals([self.crash], {})
        fired, _ = agent.new_signals([self.crash], state)
        self.assertEqual(fired, [])

    def test_getting_worse_fires_again(self):
        _, state = agent.new_signals([self.crash], {})
        deeper = agent.Signal(**{**self.crash.__dict__, "magnitude": 0.80})
        fired, _ = agent.new_signals([deeper], state)
        self.assertEqual(len(fired), 1)

    def test_getting_slightly_worse_within_the_tier_stays_silent(self):
        _, state = agent.new_signals([self.crash], {})
        nudged = agent.Signal(**{**self.crash.__dict__, "magnitude": 0.60})
        fired, _ = agent.new_signals([nudged], state)
        self.assertEqual(fired, [])

    def test_recovery_clears_the_state_so_it_can_fire_again(self):
        _, state = agent.new_signals([self.crash], {})
        _, state = agent.new_signals([], state)          # item recovered
        self.assertEqual(state["tiers"], {})
        fired, _ = agent.new_signals([self.crash], state)
        self.assertEqual(len(fired), 1)

    def test_hovering_inside_the_band_does_not_re_arm(self):
        """Anti-flapper: sitting just under the line must not reset the tier."""
        _, state = agent.new_signals([self.crash], {})
        inside = agent.Signal(**{**self.crash.__dict__, "magnitude": 0.30})
        _, state = agent.new_signals([inside], state)
        self.assertIn("329:CRASH", state["tiers"])
        fired, _ = agent.new_signals([self.crash], state)
        self.assertEqual(fired, [])

    def test_an_unknown_kind_is_ignored_rather_than_crashing(self):
        odd = agent.Signal(item_id=1, name="x", kind="NOT_A_KIND",
                           magnitude=99.0, price=1, message="")
        fired, state = agent.new_signals([odd], {})
        self.assertEqual(fired, [])
        self.assertEqual(state["tiers"], {})


class TrendChangeTests(unittest.TestCase):
    def _views(self, direction):
        trend = merch.Trend(
            slope_per_day=0.001, intercept=0.0, r_squared=0.8, t_stat=6.0,
            annualised_pct=44.0, deviation=0.0, consistency=0.6, n=365,
            direction=direction)
        return {565: view(trend=trend)}

    def test_the_first_run_never_fires(self):
        """Nothing changed yet — there is no previous direction to differ from."""
        fired, state = agent.trend_changes(
            self._views(merch.UPTREND), {565: "Blood rune"}, {})
        self.assertEqual(fired, [])
        self.assertEqual(state["directions"], {"565": merch.UPTREND})

    def test_a_flip_fires_once(self):
        _, state = agent.trend_changes(
            self._views(merch.UPTREND), {565: "Blood rune"}, {})
        fired, state = agent.trend_changes(
            self._views(merch.DOWNTREND), {565: "Blood rune"}, state)
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0].kind, "TREND_CHANGE")
        again, _ = agent.trend_changes(
            self._views(merch.DOWNTREND), {565: "Blood rune"}, state)
        self.assertEqual(again, [])


class StateFileTests(unittest.TestCase):
    def test_a_corrupt_state_file_is_not_fatal(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "watch_state.json"
            path.write_text("{ this is not json")
            self.assertEqual(agent._read_json(path, {}), {})

    def test_writes_are_atomic(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "state.json"
            agent._write_json(path, {"a": 1})
            self.assertEqual(json.loads(path.read_text()), {"a": 1})
            self.assertFalse(path.with_suffix(".tmp").exists())


class AlertScaleTests(unittest.TestCase):
    def test_every_signal_kind_the_agent_emits_has_a_scale(self):
        """A kind with no scale is silently dropped, which is a trap."""
        kinds = {merch.CRASH, merch.DIP, merch.DIPPED_STABLE, merch.PUMPED,
                 merch.SUPPLY_CRUNCH, merch.SUPPLY_DROP, "PULLBACK"}
        self.assertEqual(set(agent.ALERT_SCALE), kinds)


class ParserTests(unittest.TestCase):
    def test_json_works_on_either_side_of_the_subcommand(self):
        parser = agent.build_parser()
        self.assertTrue(parser.parse_args(["--json", "merch"]).json)
        self.assertTrue(parser.parse_args(["merch", "--json"]).json)

    def test_portfolio_defaults_to_listing(self):
        opts = agent.build_parser().parse_args(["portfolio"])
        self.assertEqual(opts.action, "list")

    def test_capital_accepts_how_players_write_it(self):
        opts = agent.build_parser().parse_args(["flips", "--capital", "1.5m"])
        self.assertEqual(opts.capital, 1_500_000)


class ItemResolutionTests(unittest.TestCase):
    class FakeItem:
        def __init__(self, name):
            self.name = name

    def setUp(self):
        self.items = {565: self.FakeItem("Blood rune"),
                      560: self.FakeItem("Death rune"),
                      13441: self.FakeItem("Anglerfish"),
                      13439: self.FakeItem("Raw anglerfish")}

    def test_an_id_resolves(self):
        self.assertEqual(agent._resolve_item("565", self.items), 565)

    def test_an_exact_name_beats_a_substring(self):
        """'Anglerfish' is inside 'Raw anglerfish', so exact has to win."""
        self.assertEqual(agent._resolve_item("Anglerfish", self.items), 13441)

    def test_case_does_not_matter(self):
        self.assertEqual(agent._resolve_item("blood RUNE", self.items), 565)

    def test_an_ambiguous_substring_refuses_to_guess(self):
        self.assertIsNone(agent._resolve_item("rune", self.items))

    def test_an_unknown_name_is_none(self):
        self.assertIsNone(agent._resolve_item("Twisted bow", self.items))


if __name__ == "__main__":
    unittest.main()
