"""Guards the browser port against drifting from the Python engine.

docs/index.html carries its own JavaScript copy of the ranking math, because
it runs with no Python available. That duplication is deliberate but it is also
exactly how the port went stale last time: the instruction was "change it in
both", enforced by nothing.

These tests do not check the JS arithmetic — a Python test cannot run it. They
check the things that silently rot: the tax-exempt list and the calibration
constants, which are the two places where a divergence produces plausible
numbers that are simply wrong. If a formula changes, the port still has to be
updated by hand.

Run with: python3 -m unittest test_docs_port -v
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import engine
import exemptions

DOCS = Path(__file__).parent / "docs" / "index.html"


def js_block(source: str, opener: str, closer: str) -> str:
    start = source.index(opener) + len(opener)
    return source[start:source.index(closer, start)]


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


class PortSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = DOCS.read_text()
        cls.config = exemptions.load_config()

    # -- tax exemptions ----------------------------------------------------

    def js_exempt_names(self):
        block = js_block(self.source, "const EXEMPT_NAMES = new Set([", "]);")
        return {name.lower() for name in re.findall(r'"([^"]+)"', block)}

    def test_exempt_names_match_the_json_config(self):
        expected = {str(n).strip().lower() for n in self.config["names"]}
        self.assertEqual(self.js_exempt_names(), expected,
                         "docs/index.html EXEMPT_NAMES has drifted from "
                         "tax_exempt.json — the browser would tax items that "
                         "owe nothing, or exempt items that do")

    def test_exempt_ids_match_the_json_config(self):
        block = js_block(self.source, "const EXEMPT_IDS = new Set([", "]);")
        found = {int(n) for n in re.findall(r"\d+", block)}
        self.assertEqual(found, {int(i) for i in self.config["ids"]})

    def test_the_list_is_not_back_to_just_the_bond(self):
        # The specific regression this file exists to catch.
        self.assertGreater(len(self.js_exempt_names()), 50)

    # -- calibration -------------------------------------------------------

    def js_calibration(self):
        block = strip_comments(js_block(self.source, "const CAL = {", "\n};"))
        values = {}
        for name, raw in re.findall(r"(\w+)\s*:\s*([^,\n]+),", block):
            try:
                values[name] = float(raw.strip())
            except ValueError:
                continue          # a reference to another constant, not a literal
        return values

    def test_every_python_parameter_exists_in_the_port(self):
        missing = set(engine.DEFAULT_CALIBRATION.__dict__) - set(self.js_calibration())
        # horizon_hours is expressed in the port as WINDOW_HOURS, not a literal.
        missing.discard("horizon_hours")
        self.assertEqual(missing, set(),
                         "the port is missing calibration parameters the "
                         "Python engine uses")

    def test_calibration_values_match(self):
        js = self.js_calibration()
        for name, value in engine.DEFAULT_CALIBRATION.__dict__.items():
            if name not in js:
                continue
            self.assertAlmostEqual(
                js[name], float(value), places=9,
                msg="{} is {} in the browser port and {} in engine.py".format(
                    name, js[name], value))

    # -- constants the tax maths depends on --------------------------------

    def test_tax_constants_match(self):
        for js_name, expected in (("TAX_RATE", engine.TAX_RATE),
                                  ("TAX_CAP", engine.TAX_CAP),
                                  ("WINDOW_HOURS", engine.WINDOW_HOURS),
                                  ("LEGS_PER_ROUND_TRIP", engine.LEGS_PER_ROUND_TRIP)):
            match = re.search(
                r"const {}\s*=\s*([0-9_.]+)".format(js_name), self.source)
            self.assertIsNotNone(match, "{} missing from the port".format(js_name))
            self.assertAlmostEqual(
                float(match.group(1).replace("_", "")), float(expected), places=9,
                msg="{} differs between the port and engine.py".format(js_name))

    def test_history_window_matches(self):
        for js_name, expected in (
                ("HISTORY_WINDOW_BUCKETS", engine.HISTORY_WINDOW_BUCKETS),
                ("MIN_HISTORY_BUCKETS", engine.MIN_HISTORY_BUCKETS),
                ("RECENT_TREND_BUCKETS", engine.RECENT_TREND_BUCKETS)):
            match = re.search(r"const {}\s*=\s*(\d+)".format(js_name), self.source)
            self.assertIsNotNone(match)
            self.assertEqual(int(match.group(1)), expected, js_name)

    def test_nature_rune_id_matches(self):
        match = re.search(r"const NATURE_RUNE_ID\s*=\s*(\d+)", self.source)
        self.assertEqual(int(match.group(1)), exemptions.NATURE_RUNE_ID)

    # -- the stale-port warning must be gone now the port is current -------

    def test_no_leftover_stale_banner(self):
        self.assertNotIn("runs an older version of the ranking", self.source)

    def test_removed_factors_are_not_still_referenced(self):
        # Functions the rebuild deleted. Their presence means a half-done port.
        for gone in ("queueFactor", "levelFactor", "stabilityFactor",
                     "momentumFactor", "FRESHNESS_HALF_LIFE", "windowVolume"):
            self.assertNotIn(gone, self.source,
                             "{} survived the port".format(gone))


if __name__ == "__main__":
    unittest.main()
