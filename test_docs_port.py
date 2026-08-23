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
import merch

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

    def test_account_profiles_are_members_first_and_coherent(self):
        self.assertIn('const DEFAULT_ACCOUNT = "members"', self.source)
        self.assertIn("const MEMBER_SLOTS = 8", self.source)
        self.assertIn("const F2P_SLOTS = 3", self.source)
        self.assertIn('accountSlots(account)', self.source)
        self.assertNotIn('id="f-members"', self.source)
        self.assertNotIn('id="f-slots"', self.source)

    def test_active_and_overnight_math_is_ported(self):
        for function in ("roundTripProbability", "strandedInventoryProbability",
                         "confidenceLabel"):
            self.assertIn("function {}(".format(function), self.source)
        self.assertIn('mode === "overnight" ? expected : perSlotHour',
                      self.source)
        self.assertIn("downsideRisk", self.source)
        for function in ("fillEstimate", "optimiseExecution",
                         "rescoreAllocated", "effectiveBuyLimit"):
            self.assertIn("function {}(".format(function), self.source)

    def test_live_execution_workflow_is_present(self):
        self.assertIn("My saved flips", self.source)
        self.assertIn("SAVE &amp; MONITOR", self.source)
        self.assertIn('status: "watching"', self.source)
        self.assertIn("TARGET SELL", self.source)
        self.assertIn("LIVE NOW", self.source)
        self.assertIn("60_000", self.source)

    def test_quick_flow_uses_automatic_quality_and_concentration_gates(self):
        self.assertIn("function automaticFilterProfile(", self.source)
        self.assertIn("maxQuoteAge: overnight ? 900 : 600", self.source)
        self.assertIn("minVolume1h: overnight ?", self.source)
        self.assertIn("minRoi: overnight ? 0.008 : 0.003", self.source)
        self.assertIn("maxPositionCapital", self.source)
        self.assertIn("config.maxPositionCapital", self.source)
        self.assertIn("quickPlanRiskTier", self.source)
        self.assertIn("function isAutomaticPlanCandidate(", self.source)
        self.assertIn('confidence !== "high"', self.source)
        self.assertIn("state.deepReady = true", self.source)
        self.assertIn("kept: eligible", self.source)
        self.assertIn("eligible.map((row)", self.source)
        self.assertIn('id="filter-details" class="hidden"', self.source)

    def test_slot_locks_survive_refresh_and_reserve_capital(self):
        self.assertIn('const LOCK_KEY = "osrs-flipper.slot-locks.v1"', self.source)
        self.assertIn("function lockSlot(", self.source)
        self.assertIn("function unlockSlot(", self.source)
        self.assertIn("lockedCommit", self.source)
        self.assertIn("config.capital - lockedCommit", self.source)
        self.assertIn("LIVE SCANNER NOW", self.source)
        self.assertIn("SELL OFFER", self.source)

    def test_plan_uses_the_derived_slot_count_not_a_three_card_constant(self):
        self.assertNotIn("const PLAN_SIZE = 3", self.source)
        self.assertIn("Array(config.slots).fill(null)", self.source)
        self.assertIn("config.slots - state.slotLocks.length", self.source)

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

    # -- merch, crash and supply signals -----------------------------------
    #
    # These live in merch.py on the Python side and in the "merch:
    # long-horizon signals" block of the port. Same rule as the calibration:
    # a Python test cannot run the JavaScript, so what is guarded here is the
    # data that silently rots — id lists, window lengths, and the measured
    # noise curve.

    def test_the_raid_unique_list_matches(self):
        block = js_block(self.source, "const RAID_UNIQUE_IDS = new Set([", "]);")
        found = {int(n) for n in re.findall(r"\d+", strip_comments(block))}
        self.assertEqual(found, set(merch.RAID_UNIQUE_IDS))

    def test_the_must_have_list_matches(self):
        block = js_block(self.source, "const PVM_MUST_HAVE_IDS = new Set([", "]);")
        found = {int(n) for n in re.findall(r"\d+", strip_comments(block))}
        self.assertEqual(found, set(merch.PVM_MUST_HAVE_IDS))

    def test_the_watchlist_matches(self):
        block = js_block(self.source, "const WATCHLIST = [", "\n];")
        found = [int(n) for n in re.findall(r"\[(\d+),", block)]
        self.assertEqual(found, list(merch.WATCHLIST_IDS),
                         "the browser watchlist has drifted from merch.py")

    def test_merch_windows_match(self):
        for js_name, expected in (
                ("TREND_WINDOW_POINTS", merch.TREND_WINDOW_POINTS),
                ("TREND_MIN_POINTS", merch.TREND_MIN_POINTS),
                ("MEDIAN_WINDOW_DAYS", merch.MEDIAN_WINDOW_DAYS),
                ("VOLUME_BASELINE_DAYS", merch.VOLUME_BASELINE_DAYS),
                ("VOLUME_RECENT_DAYS", merch.VOLUME_RECENT_DAYS),
                ("VOLUME_LOOKBACK_DAYS", merch.VOLUME_LOOKBACK_DAYS),
                ("MIN_BASKET_FOR_DRIFT", merch.MIN_BASKET_FOR_DRIFT),
                ("VOLUME_SKIP_LAST", merch.VOLUME_SKIP_LAST),
                ("ANNUALISED_REPORT_CAP", merch.ANNUALISED_REPORT_CAP),
                ("ANNUALISED_SCORE_CAP", merch.ANNUALISED_SCORE_CAP)):
            match = re.search(r"const {}\s*=\s*([0-9_.]+)".format(js_name),
                              self.source)
            self.assertIsNotNone(match, "{} missing from the port".format(js_name))
            self.assertAlmostEqual(
                float(match.group(1).replace("_", "")), float(expected), places=9,
                msg="{} differs between the port and merch.py".format(js_name))

    def test_the_trend_timestep_matches(self):
        match = re.search(r'const TREND_TIMESTEP\s*=\s*"([^"]+)"', self.source)
        self.assertEqual(match.group(1), merch.TREND_TIMESTEP)

    def test_the_noise_curve_matches(self):
        """The measured null distribution. A drifted copy misreports confidence."""
        block = js_block(self.source, "const NOISE_SURVIVAL = [", "\n];")
        pairs = [(float(t), float(p)) for t, p in
                 re.findall(r"\[([0-9.]+),\s*([0-9.]+)\]", block)]
        self.assertEqual(len(pairs), len(merch.NOISE_SURVIVAL))
        for (js_t, js_p), (py_t, py_p) in zip(pairs, merch.NOISE_SURVIVAL):
            self.assertAlmostEqual(js_t, py_t, places=9)
            self.assertAlmostEqual(js_p, py_p, places=9)

    def test_the_botted_thresholds_match(self):
        for js_name, expected in (("BOTTED_MAX_PRICE", merch.BOTTED_MAX_PRICE),
                                  ("BOTTED_MIN_LIMIT", merch.BOTTED_MIN_LIMIT)):
            match = re.search(r"const {}\s*=\s*([0-9_]+)".format(js_name),
                              self.source)
            self.assertIsNotNone(match)
            self.assertEqual(int(match.group(1).replace("_", "")), expected)

    def test_the_port_does_not_set_a_user_agent(self):
        """Browsers forbid it, and a custom header trips a CORS preflight the
        wiki answers with 400 — so adding one takes the whole page down."""
        self.assertNotIn("'User-Agent'", self.source)
        self.assertNotIn('"User-Agent"', self.source)

    # -- the stale-port warning must be gone now the port is current -------

    def test_no_leftover_stale_banner(self):
        self.assertNotIn("runs an older version of the ranking", self.source)

    def test_the_queue_is_sized_per_item_in_the_port_too(self):
        """A port still dividing by a flat competitors_at_touch would rank
        botted commodities top while the Python side buries them."""
        self.assertIn("function touchCompetitors(", self.source)
        self.assertIn("touchCompetitors(thinVolume, item.limit)", self.source)
        self.assertIn("touchCompetitors(row.volume, row.limit)", self.source)

    def test_removed_factors_are_not_still_referenced(self):
        # Functions the rebuild deleted. Their presence means a half-done port.
        for gone in ("queueFactor", "levelFactor", "stabilityFactor",
                     "momentumFactor", "FRESHNESS_HALF_LIFE", "windowVolume"):
            self.assertNotIn(gone, self.source,
                             "{} survived the port".format(gone))


if __name__ == "__main__":
    unittest.main()
