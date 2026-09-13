"""Optional Streamlit smoke tests; the core suite remains stdlib-only."""
import importlib.util
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import api


@unittest.skipUnless(importlib.util.find_spec("streamlit"), "install requirements.txt for dashboard tests")
class DashboardTests(unittest.TestCase):
    def test_landing_and_market_with_sidebar_render(self):
        from streamlit.testing.v1 import AppTest

        client = Mock(stale_keys=set())
        client.mapping.return_value = {1: api.Item(1, "Test item", False, 100, 100, None)}
        client.latest.return_value = {1: api.Quote(120, int(time.time()), 100, int(time.time()))}
        client.interval.return_value = {1: api.Activity(120, 1000, 100, 1000)}
        client.timeseries.return_value = []
        with patch("api.WikiClient", return_value=client), patch("archive.Archive") as archive:
            archive.return_value.__enter__.return_value.summary.return_value = {"buckets": 0}
            app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run(timeout=20)
            self.assertEqual(list(app.exception), [])
            app.session_state["capital"] = 1_000_000
            app.run(timeout=20)
            self.assertEqual(list(app.exception), [])
            self.assertTrue(app.sidebar.radio)
