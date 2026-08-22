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
        with mock.patch("api.time.monotonic", return_value=999.0):
            value = client._cached(
                "latest", 30, lambda: (_ for _ in ()).throw(api.ApiError("down")))
        self.assertEqual(value, {1: "complete"})
        self.assertIn("latest", client.stale_keys)

    def test_cold_start_still_reports_the_outage(self):
        client = api.WikiClient(cache_dir="/tmp/osrs-api-test")
        with self.assertRaises(api.ApiError):
            client._cached("latest", 30,
                           lambda: (_ for _ in ()).throw(api.ApiError("down")))


if __name__ == "__main__":
    unittest.main()
