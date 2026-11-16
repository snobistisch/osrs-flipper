"""Reliability tests for the Wiki boundary and stale-data fallback."""
from __future__ import annotations

import unittest
import urllib.error
from unittest import mock

import api


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.body


class RetryTests(unittest.TestCase):
    def test_transient_transport_errors_are_retried(self):
        client = api.WikiClient(cache_dir="/tmp/osrs-api-test")
        effects = [urllib.error.URLError("busy"),
                   urllib.error.URLError("busy"),
                   _Response(b'{"data": {}}')]
        with mock.patch("urllib.request.urlopen", side_effect=effects) as opened:
            with mock.patch("api.time.sleep"):
                self.assertEqual(client._get("/latest"), {"data": {}})
        self.assertEqual(opened.call_count, 3)

    def test_invalid_json_is_a_boundary_error(self):
        client = api.WikiClient(cache_dir="/tmp/osrs-api-test")
        with mock.patch("urllib.request.urlopen",
                        return_value=_Response(b"not json")):
            with self.assertRaises(api.ApiError):
                client._get("/latest")


class StaleFallbackTests(unittest.TestCase):
    def test_expired_complete_snapshot_survives_a_brief_outage(self):
        client = api.WikiClient(cache_dir="/tmp/osrs-api-test")
        client._memory["latest"] = (0.0, {1: "complete"})
        with mock.patch("api.time.monotonic", return_value=60.0):
            value = client._cached(
                "latest", 30, lambda: (_ for _ in ()).throw(api.ApiError("down")))
        self.assertEqual(value, {1: "complete"})
        self.assertIn("latest", client.stale_keys)

    def test_cold_start_still_reports_the_outage(self):
        client = api.WikiClient(cache_dir="/tmp/osrs-api-test")
        with self.assertRaises(api.ApiError):
            client._cached("latest", 30,
                           lambda: (_ for _ in ()).throw(api.ApiError("down")))


class DecimalAverageTests(unittest.TestCase):
    """API v2 averages carry up to two decimals (audit F-02)."""

    def test_decimal_average_keeps_its_side_and_volume(self):
        rows = api.clean_history([{
            "timestamp": 1794825000, "avgHighPrice": 649036.25,
            "avgLowPrice": 643121, "highPriceVolume": 4, "lowPriceVolume": 7}])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["avgHighPrice"], 649036)
        self.assertEqual(rows[0]["highPriceVolume"], 4)
        self.assertEqual(rows[0]["avgLowPrice"], 643121)
        self.assertEqual(rows[0]["lowPriceVolume"], 7)

    def test_average_price_parser(self):
        cases = ((648416.5, 648417), (0.4, None), (-3, None), ("12", None),
                 (True, None), (float("nan"), None), (float("inf"), None),
                 (0, None), (12, 12), (0.5, 1), (2 ** 53, None))
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(api._avg_price(raw), expected)
                row = api.clean_history([{"timestamp": 1, "avgHighPrice": raw,
                                          "highPriceVolume": 5}])[0]
                self.assertEqual(row["avgHighPrice"], expected)
                self.assertEqual(row["highPriceVolume"], 5 if expected else 0)

    def test_volumes_and_latest_prices_stay_whole_numbers(self):
        row = api.clean_history([{"timestamp": 1, "avgHighPrice": 100.5,
                                  "highPriceVolume": 2.5}])[0]
        self.assertEqual(row["avgHighPrice"], 101)
        self.assertEqual(row["highPriceVolume"], 0)
        client = api.WikiClient(cache_dir="/tmp/osrs-api-test")
        with mock.patch.object(client, "_get", return_value={"data": {
                "1": {"high": 100.5, "low": 99, "highTime": 1, "lowTime": 1}}}):
            quote = client._fetch_latest()[1]
        self.assertIsNone(quote.high)
        self.assertEqual(quote.low, 99)

    def test_history_with_many_unreadable_prices_raises(self):
        rows = [{"timestamp": index + 1, "avgHighPrice": "100",
                 "avgLowPrice": 99.5, "highPriceVolume": 1, "lowPriceVolume": 1}
                for index in range(10)]
        with self.assertRaisesRegex(api.ApiError, "/timeseries"):
            api.clean_history(rows)
        # Below 20 present sides the guard does not apply.
        self.assertEqual(len(api.clean_history(rows[:9])), 9)
        # Exactly 20% unreadable is tolerated.
        tolerated = [{"timestamp": index + 1, "avgHighPrice": 100,
                      "avgLowPrice": "x" if index < 4 else 99}
                     for index in range(10)]
        self.assertEqual(len(api.clean_history(tolerated)), 10)

    def test_interval_with_many_unreadable_prices_raises(self):
        client = api.WikiClient(cache_dir="/tmp/osrs-api-test")
        data = {str(index + 1): {"avgHighPrice": None if index % 2 else "1",
                                 "avgLowPrice": 10.25, "highPriceVolume": 1,
                                 "lowPriceVolume": 1} for index in range(40)}
        with mock.patch.object(client, "_get", return_value={"data": data}):
            with self.assertRaisesRegex(api.ApiError, "/5m"):
                client._fetch_interval("5m")
        for row in data.values():
            row["avgHighPrice"] = None
        with mock.patch.object(client, "_get", return_value={"data": data}):
            activity = client._fetch_interval("1h")
        self.assertEqual(activity[1].avg_low, 10)
        self.assertEqual(activity[1].low_volume, 1)
        self.assertIsNone(activity[1].avg_high)


if __name__ == "__main__":
    unittest.main()
