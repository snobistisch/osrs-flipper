"""Reliability tests for the Wiki boundary and stale-data fallback."""
from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.parse
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


class ApiFallbackTests(unittest.TestCase):
    """v1 while it works; v2 per kind of request once v1 answers 4xx."""

    def client(self, answer):
        """A client whose transport is ``answer(version, url) -> body``.

        ``answer`` returns a JSON-serialisable body, an int HTTP status, or
        raises; ``self.urls`` records every request.
        """
        self.urls = []

        def urlopen(request, timeout=None):
            url = request.full_url
            self.urls.append(url)
            result = answer(2 if "/api/v2/" in url else 1,
                            urllib.parse.urlparse(url))
            if isinstance(result, int):
                raise urllib.error.HTTPError(url, result, "status", {}, None)
            return _Response(json.dumps(result).encode())
        patcher = mock.patch("urllib.request.urlopen", side_effect=urlopen)
        patcher.start()
        self.addCleanup(patcher.stop)
        sleeper = mock.patch("api.time.sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        return api.WikiClient(cache_dir=self.tmp.name)

    @staticmethod
    def series(url, timestep=None):
        lookback = urllib.parse.parse_qs(url.query).get("lookback", [""])[0]
        return {"data": [{"timestamp": 1, "avgHighPrice": 10.5, "avgLowPrice": 9,
                          "highPriceVolume": 1, "lowPriceVolume": 1}],
                "itemId": 4151,
                "timestep": timestep or {"24h": 300, "7d": 3600, "6m": 21600,
                                         "1y": 86400}.get(lookback)}

    def test_v1_that_works_is_the_only_api_used(self):
        client = self.client(lambda version, url: {"data": []}
                             if url.path.endswith("/timeseries") else {"data": {}})
        client._fetch_latest()
        client._fetch_timeseries(4151, "6h")
        self.assertTrue(all("/api/v1/" in url for url in self.urls))
        self.assertEqual(len(self.urls), 2)

    def test_v1_that_answers_404_moves_each_kind_to_v2(self):
        def answer(version, url):
            if version == 1:
                return 404
            return (self.series(url) if url.path.endswith("/timeseries")
                    else {"data": {}})
        client = self.client(answer)
        client._fetch_latest()
        self.assertEqual([urllib.parse.urlparse(u).path for u in self.urls],
                         ["/api/v1/osrs/latest", "/api/v2/osrs/latest"])
        client._fetch_interval("5m")
        self.assertEqual(urllib.parse.urlparse(self.urls[2]).path,
                         "/api/v2/osrs/5m")
        rows = client._fetch_timeseries(4151, "6h")
        self.assertEqual(rows[0]["avgHighPrice"], 11)
        asked = urllib.parse.urlparse(self.urls[-1])
        query = urllib.parse.parse_qs(asked.query)
        self.assertEqual(asked.path, "/api/v2/osrs/timeseries")
        self.assertEqual(query["lookback"], ["6m"])
        self.assertNotIn("timestep", query)

    def test_a_v2_series_with_the_wrong_timestep_is_not_used(self):
        client = self.client(lambda version, url: 404 if version == 1
                             else self.series(url, timestep=3600))
        with self.assertRaisesRegex(api.ApiError, "api/v1/.*timestep=6h"):
            client._fetch_timeseries(4151, "6h")
        self.assertEqual(client._bases["timeseries"], api.BASE_URL)

    def test_server_and_network_errors_never_move_to_v2(self):
        def network(version, url):
            raise urllib.error.URLError("down")
        for answer in (lambda version, url: 500, network):
            client = self.client(answer)
            with self.assertRaises(api.ApiError):
                client._fetch_latest()
            self.assertEqual(len(self.urls), 3)
            self.assertTrue(all("/api/v1/" in url for url in self.urls))
            self.assertEqual(client._bases["bulk"], api.BASE_URL)

    def test_an_unknown_item_on_both_apis_keeps_timeseries_on_v1(self):
        client = self.client(lambda version, url: 404 if "id=999999" in url.query
                             else {"data": []})
        with self.assertRaises(api.ApiError):
            client._fetch_timeseries(999999, "5m")
        self.assertEqual(client._bases["timeseries"], api.BASE_URL)
        client._fetch_timeseries(4151, "5m")
        self.assertIn("/api/v1/osrs/timeseries?id=4151&timestep=5m",
                      self.urls[-1])

    def test_a_client_on_another_base_does_not_fall_back(self):
        self.client(lambda version, url: 404)
        client = api.WikiClient(cache_dir=self.tmp.name,
                                base_url="https://example.invalid/api")
        with self.assertRaises(api.ApiError):
            client._fetch_latest()
        self.assertEqual(len(self.urls), 1)


if __name__ == "__main__":
    unittest.main()
