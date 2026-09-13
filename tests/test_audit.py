"""Regression tests for data integrity, trading arithmetic and outage handling."""
import contextlib
import io
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import agent
import api
import archive
import collect
import engine
import filters
import journal
from storage import state_lock, write_json


class ArithmeticTests(unittest.TestCase):
    def test_minimum_profitable_sell_at_every_tax_boundary(self):
        for buy in [*range(1, 2000), 244_999_999, 245_000_000, 250_000_000,
                    1_000_000_000, engine.MAX_CASH_STACK]:
            sell = engine.break_even_sell(buy)
            self.assertEqual(engine.net_margin(buy, sell), 1)
            self.assertLessEqual(engine.net_margin(buy, sell - 1), 0)

    def test_gp_input_rejects_nonfinite_and_nondecimal_values(self):
        for text in ("infm", "NaNk", "1e9m", "0x10", "-2k", "1.2"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                engine.parse_gp(text)
        self.assertEqual(engine.parse_gp("1.0005k"), 1001)

    def test_capital_must_be_integral(self):
        for value in (True, float("nan"), float("inf"), 100.5, "100"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                filters.FilterConfig(capital=value)


class BoundaryTests(unittest.TestCase):
    def test_invalid_numbers_do_not_crash_or_become_prices(self):
        for value in (True, float("nan"), float("inf"), -1, 1.5, "100", 10 ** 500):
            self.assertIsNone(api._opt_int(value))

    def test_history_sorts_deduplicates_and_sanitizes(self):
        rows = api.clean_history([
            {"timestamp": 2, "avgHighPrice": 0, "highPriceVolume": 100},
            None, {"timestamp": "bad"},
            {"timestamp": 1, "avgLowPrice": 10, "lowPriceVolume": -2},
            {"timestamp": 2, "avgHighPrice": 20, "highPriceVolume": 3},
        ])
        self.assertEqual([r["timestamp"] for r in rows], [1, 2])
        self.assertEqual(rows[0]["lowPriceVolume"], 0)
        self.assertEqual(rows[1]["highPriceVolume"], 3)

    def test_corrupt_mapping_shape_is_a_cache_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "mapping.json").write_text('{}')
            client = api.WikiClient(directory)
            with mock.patch.object(client, "_get", return_value=[
                {"id": 1, "name": "Test", "members": False}
            ]) as fetch:
                self.assertFalse(client.mapping()[1].members)
                fetch.assert_called_once()

    def test_stale_fallback_expires_and_failures_obey_poll_floor(self):
        client = api.WikiClient()
        client._memory["latest"] = (0, {1: "snapshot"})
        fetch = mock.Mock(side_effect=api.ApiError("offline"))
        with mock.patch("api.time.monotonic", return_value=60):
            self.assertEqual(client._cached("latest", 30, fetch), {1: "snapshot"})
            client._cached("latest", 30, fetch)
        self.assertEqual(fetch.call_count, 1)
        with mock.patch("api.time.monotonic", return_value=400):
            with self.assertRaises(api.ApiError):
                client._cached("latest", 30, fetch)


class PersistenceTests(unittest.TestCase):
    def test_parallel_state_updates_do_not_lose_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "state.json"
            write_json(path, [])
            def add(index):
                with state_lock(root):
                    values = json.loads(path.read_text())
                    values.append(index)
                    write_json(path, values)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(add, range(12)))
            self.assertEqual(sorted(json.loads(path.read_text())), list(range(12)))

    def test_failed_serialization_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "state.json")
            write_json(path, {"position": 1})
            with self.assertRaises(ValueError):
                write_json(path, {"position": float("nan")})
            self.assertEqual(json.loads(path.read_text()), {"position": 1})
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_portfolio_api_failure_cannot_remove_position(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, agent.PORTFOLIO_FILE)
            position = {"item_id": 1, "name": "Test", "qty": 1,
                        "buy_price": 100, "opened_at": 1}
            write_json(path, [position])
            opts = SimpleNamespace(state_dir=Path(directory), action="close", index=1, price=200)
            with mock.patch("agent.api.WikiClient") as client, contextlib.redirect_stderr(io.StringIO()):
                client.return_value.mapping.side_effect = api.ApiError("offline")
                self.assertEqual(agent.cmd_portfolio(opts), 1)
            self.assertEqual(json.loads(path.read_text()), [position])

    def test_missing_watch_item_does_not_rearm_alert(self):
        state = {"tiers": {"329:CRASH": {"tier": 1, "at": 1}}}
        _, updated = agent.new_signals([], state, observed_ids={1})
        self.assertEqual(updated["tiers"], state["tiers"])

    def test_empty_watch_run_records_a_failure_without_resetting_alerts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, agent.WATCH_STATE_FILE)
            write_json(path, {"tiers": {"329:CRASH": {"tier": 1, "at": 1}}})
            with mock.patch("agent.load_watchlist", return_value=({}, {}, ["offline"])):
                agent.cmd_watch(SimpleNamespace(state_dir=Path(directory), json=False))
            state = json.loads(path.read_text())
            self.assertEqual(state["consecutive_failures"], 1)
            self.assertIn("329:CRASH", state["tiers"])

    def test_missing_portfolio_quote_is_unknown_in_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, agent.PORTFOLIO_FILE)
            write_json(path, [{"item_id": 1, "name": "Test", "qty": 1,
                              "buy_price": 100, "opened_at": 1}])
            output = io.StringIO()
            with mock.patch("agent.api.WikiClient") as client, contextlib.redirect_stdout(output):
                client.return_value.latest.return_value = {}
                client.return_value.mapping.return_value = {}
                agent.cmd_portfolio(SimpleNamespace(state_dir=Path(directory), action="list", json=True))
            result = json.loads(output.getvalue())
            self.assertIsNone(result["positions"][0]["pnl"])
            self.assertTrue(result["total_pnl_partial"])

    def test_concurrent_journal_transition_cannot_overwrite_a_cancellation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "journal.db")
            with journal.Journal(path) as first, journal.Journal(path) as second:
                flip = first.open_flip("Test", 1, 100)
                old_row = first._row(flip)
                second.cancel_flip(flip)
                with mock.patch.object(first, "_row", return_value=old_row):
                    with self.assertRaises(ValueError):
                        first.close_flip(flip, 120)
                self.assertEqual(first._row(flip)["outcome"], "cancelled")

    def test_journal_invalid_values_and_time_order(self):
        with journal.Journal(":memory:") as store:
            for quantity in (True, 0.5, float("nan")):
                with self.assertRaises(ValueError):
                    store.open_flip("Test", quantity, 100)
            flip = store.open_flip("Test", 1, 100, bought_at=200)
            with self.assertRaises(ValueError):
                store.close_flip(flip, 120, sold_at=100)
            store.cancel_flip(flip)
            with self.assertRaises(ValueError):
                store.cancel_flip(flip)


class ArchiveTests(unittest.TestCase):
    def test_collector_uses_source_timestamp_and_refuses_stale_snapshot(self):
        client = mock.Mock(stale_keys=set(), interval_timestamps={"5m": 300, "1h": 3600})
        store = mock.Mock()
        with mock.patch("collect.time.time", return_value=10000):
            collect.poll_once(client, store, {})
        self.assertEqual(store.record_buckets.call_args_list[0].kwargs["bucket_start"], 300)
        store.reset_mock()
        client.stale_keys = {"latest", "5m", "1h"}
        with mock.patch("collect.time.time", return_value=10000):
            result = collect.poll_once(client, store, {})
        self.assertEqual(len(result["errors"]), 3)
        store.record_latest.assert_not_called()
        store.record_buckets.assert_not_called()

    def test_zero_volume_observations_count_in_average(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("archive.time.time", return_value=10000):
            with archive.Archive(Path(directory, "test.db")) as store:
                store.record_buckets("1h", {1: api.Activity(100, 100, 90, 100)}, 3600)
                store.record_buckets("1h", {1: api.Activity(None, 0, None, 0)}, 7200)
                estimate = store.volume_ewma(1)
                self.assertEqual(estimate.buckets, 2)
                self.assertLess(estimate.high_per_hour, 50)
