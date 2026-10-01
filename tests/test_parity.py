"""Executable parity between the Python model and the browser port.

test_docs_port.py checks that constants and structures were copied. This file
checks that the two implementations compute the same numbers: every case runs
through engine/stats/filters here and through the real inline script of
docs/index.html under Node, and the results must agree.

Tolerances: integer GP arithmetic must match exactly. Probabilities use a
relative tolerance of 1e-5, because the browser's normal CDF is the
Abramowitz-Stegun approximation (absolute error below 1.5e-7) rather than erf;
model gp values additionally allow 0.01 gp.
"""
from __future__ import annotations

import json
import math
import random
import shutil
import subprocess
import unittest
from pathlib import Path

import engine
import filters
import stats

NODE = shutil.which("node")
RUNNER = Path(__file__).with_name("js_eval.cjs")
NOW = 1_785_000_000          # a Sunday, away from the weekly update
TOLERANCE = 1e-5


def js(*expressions: str) -> list:
    completed = subprocess.run(
        [NODE, str(RUNNER)], input=json.dumps(list(expressions)),
        capture_output=True, text=True, timeout=60, check=True)
    return json.loads(completed.stdout)


def number(value):
    """Undo the runner's encoding of non-finite numbers."""
    if value in ("Infinity", "-Infinity", "NaN"):
        return float(value.replace("Infinity", "inf"))
    return value


def history(seed: int, buckets: int = 56, start: float = 1_000.0) -> list:
    rng = random.Random(seed)
    price, points = start, []
    for index in range(buckets):
        price *= math.exp(rng.gauss(0.0, 0.02) - 0.1 * math.log(price / start))
        spread = max(2, int(price * 0.03))
        quiet = index % 9 == 0
        points.append({
            "timestamp": NOW - (buckets - index) * 21_600,
            "avgHighPrice": int(price + spread / 2),
            "avgLowPrice": None if quiet else int(price - spread / 2),
            "highPriceVolume": rng.randint(50, 900),
            "lowPriceVolume": 0 if quiet else rng.randint(50, 900),
        })
    return points


@unittest.skipIf(NODE is None, "Node.js is required for parity tests")
class ParityTests(unittest.TestCase):
    maxDiff = None

    def assertClose(self, python, javascript, label, abs_tol=TOLERANCE):
        javascript = number(javascript)
        if python is None or javascript is None:
            self.assertEqual(python, javascript, label)
        elif isinstance(python, bool) or isinstance(javascript, bool):
            self.assertEqual(bool(python), bool(javascript), label)
        elif math.isinf(python):
            self.assertEqual(python, javascript, label)
        else:
            self.assertTrue(math.isclose(python, javascript, rel_tol=TOLERANCE,
                                         abs_tol=abs_tol),
                            "{}: python {} != browser {}".format(
                                label, python, javascript))

    def test_tax_fee_and_undercut_arithmetic_is_identical(self):
        prices = [1, 2, 49, 50, 51, 99, 100, 101, 999, 1_000, 10_009, 10_010,
                  249_999_999, 250_000_000, 250_000_049, 2_000_000_000,
                  engine.MAX_CASH_STACK]
        flags = [(False, False), (True, False), (True, True)]
        expressions, expected = [], []
        for sell in prices:
            for exempt, bond in flags:
                args = "{}, {}, {}".format(sell, str(exempt).lower(),
                                           str(bond).lower())
                expressions += ["netRevenue({})".format(args),
                                "taxBoundaryUndercut({})".format(args),
                                "bondConversionFee({}, {})".format(
                                    sell, str(bond).lower())]
                expected += [engine.net_revenue(sell, exempt, bond),
                             engine.tax_boundary_undercut(sell, exempt, bond),
                             engine.bond_conversion_fee(sell, bond)]
                buy = max(1, sell * 9 // 10)
                expressions.append("undercutDepth({}, {}, {}, {})".format(
                    buy, sell, str(exempt).lower(), str(bond).lower()))
                expected.append(engine.undercut_depth(buy, sell, exempt, bond))
        self.assertEqual(js(*expressions), expected)

    def test_price_and_queue_primitives_match(self):
        cases = [
            ("referencePrice(100, 5, 110, 50)", engine.reference_price(100, 5, 110, 50)),
            ("referencePrice(null, 0, 110, 0)", engine.reference_price(None, 0, 110, 0)),
            ("executablePrices(24, 24, 24, 27)", list(engine.executable_prices(24, 24, 24, 27))),
            ("executablePrices(30, 27, 5, 6)", list(engine.executable_prices(30, 27, 5, 6))),
            ("executablePrices(173, 192, 175, 190)", list(engine.executable_prices(173, 192, 175, 190))),
            ("priceDrift(28.5, 25.5)", engine.price_drift(28.5, 25.5)),
            ("priceDrift(7000.5, 7000)", engine.price_drift(7000.5, 7000)),
            ("touchCompetitors(1700000, 50000)", engine.touch_competitors(1_700_000, 50_000)),
            ("touchCompetitors(10, null)", engine.touch_competitors(10, None)),
            ("aggressiveness(0.2, 30)", engine.aggressiveness(0.2, competitors=30)),
            ("aggressiveness(0, 8)", engine.aggressiveness(0, competitors=8)),
            ("adverseSelectionFactor(-0.4, -0.03)", engine.adverse_selection_factor(-0.4, -0.03)),
            ("holdingRisk(0.05, 7200)", engine.holding_risk(0.05, 7200)),
            ("stalenessFactor(600, 0)", engine.staleness_factor(600, 0)),
            ("roundTripProbability(1800, 1800, 7200)", engine.round_trip_probability(1800, 1800, 7200)),
            ("roundTripProbability(900, 3600, 14400)", engine.round_trip_probability(900, 3600, 14400)),
            ("updateRiskFactor({}, 7200)".format(NOW - 4 * 86400),
             engine.update_risk_factor(NOW - 4 * 86400, 7200)),
            ("alchBonus(0.1)", engine.alch_bonus(0.1)),
        ]
        results = js(*(expression for expression, _ in cases))
        for (expression, python), browser in zip(cases, results):
            if isinstance(python, list):
                self.assertEqual(python[:2], browser[:2], expression)
                self.assertEqual(bool(python[2]), bool(browser[2]), expression)
            else:
                self.assertClose(python, browser, expression)

    def test_partial_fill_distribution_matches(self):
        cases = [(100, 0.05, 7200), (5_000, 0.05, 7200), (1, 0.0, 7200),
                 (250, 1.5, 60), (40_000, 2.0, 14_400)]
        results = js(*("fillEstimate({}, {}, {})".format(*case) for case in cases))
        for case, browser in zip(cases, results):
            python = engine.fill_estimate(*case)
            for field, key in (("expected", "expected"),
                               ("p_complete", "pComplete"),
                               ("low", "low"), ("high", "high")):
                self.assertClose(getattr(python, field), browser[key],
                                 "{} {}".format(case, field))

    def test_score_flip_matches_in_both_strategies(self):
        mids = [p for p in (engine._bucket_vwap([point]) for point in history(3))
                if p is not None]
        base = dict(buy=1_000, sell=1_080, margin=58, qty=600, depth=3,
                    buy_volume_1h=2_400.0, sell_volume_1h=1_900.0,
                    quote_age=240, ofi=-0.2, drift=-0.004, now=NOW,
                    highalch=1_100, nature_rune_cost=110, competitors=12.0,
                    buy_improvement=2, sell_improvement=1)
        cases = [
            dict(base, mode=engine.TradeMode.ACTIVE),
            dict(base, mode=engine.TradeMode.OVERNIGHT, horizon_hours=8.0),
            dict(base, mode=engine.TradeMode.ACTIVE, sigma_daily=0.08,
                 regime_score=1.0, capital_per_unit=1_100),
            dict(base, mode=engine.TradeMode.OVERNIGHT, horizon_hours=12.0,
                 qty=5_000, buy_volume_1h=40.0),
        ]
        expressions = []
        for case in cases:
            expressions.append(
                "scoreFlip({{buy:{buy}, sell:{sell}, margin:{margin}, qty:{qty},"
                " depth:{depth}, buyVolume1h:{buy_volume_1h},"
                " sellVolume1h:{sell_volume_1h}, quoteAge:{quote_age},"
                " ofi:{ofi}, drift:{drift}, now:{now}, sigmaDaily:{sigma},"
                " ou:fitOU({mids}, HISTORY_BUCKET_DAYS), regimeScore:{regime},"
                " highalch:{highalch}, natureCost:{nature_rune_cost},"
                " competitors:{competitors}, buyImprovement:{buy_improvement},"
                " sellImprovement:{sell_improvement}, mode:\"{mode}\","
                " horizonHours:{horizon}, capitalPerUnit:{capital}}})".format(
                    **dict(case, mids=json.dumps(mids), mode=case["mode"].value,
                           sigma=json.dumps(case.get("sigma_daily")),
                           regime=case.get("regime_score", 0.0),
                           horizon=json.dumps(case.get("horizon_hours")),
                           capital=json.dumps(case.get("capital_per_unit")))))
        fit = stats.fit_ou(mids, engine.HISTORY_BUCKET_DAYS)
        for case, browser in zip(cases, js(*expressions)):
            python = engine.score_flip(ou_fit=fit, **case)
            label = "{} qty {}".format(case["mode"].value, case["qty"])
            for field, key in (
                    ("capital_needed", "capitalNeeded"),
                    ("buy_seconds", "buySeconds"), ("sell_seconds", "sellSeconds"),
                    ("p_fill_both", "pFill"), ("p_stranded", "pStranded"),
                    ("expected_buy_qty", "expectedBuyQty"),
                    ("expected_sell_qty", "expectedSellQty"),
                    ("fill_low_qty", "fillLowQty"), ("fill_high_qty", "fillHighQty"),
                    ("expected_profit", "expected"),
                    ("gp_per_slot_hour", "perSlotHour"),
                    ("ranking_value", "rankingValue"),
                    ("downside_risk_gp", "downsideRisk")):
                # A hundredth of a gp: a difference of two near-equal fill
                # quantities magnifies the CDF approximation, never a real gp.
                self.assertClose(getattr(python, field), browser[key],
                                 "{} {}".format(label, field), abs_tol=0.01)

    def test_shrinkage_and_edge_probability_match(self):
        for estimates, noise in (([1.0, 2.0, 4.0, 8.0, 3.0], [0.2, 1.5, 0.3, 4.0, 0.9]),
                                 ([5.0, 5.0, 5.0], [1.0, 1.0, 1.0]),
                                 ([1.0, 9.0], [0.5, 0.5])):
            python = stats.empirical_bayes(estimates, noise)
            fit = "empiricalBayes({}, {})".format(estimates, noise)
            browser = js(fit, *("probabilityAboveMean({}, {})".format(fit, index)
                                for index in range(len(estimates))))
            for index, value in enumerate(python.values):
                self.assertClose(value, browser[0]["values"][index], "posterior")
                self.assertClose(python.probability_above_mean(index),
                                 browser[1 + index], "edge probability")

    def test_history_and_execution_evidence_match(self):
        for seed in (1, 7, 42):
            points = history(seed)
            buy, sell = 985, 1_030
            python = engine.history_view(points, buy, sell)
            long_python = engine.execution_evidence_view(
                points, False, 25, 6.0, 336.0)
            view, long_browser = js(
                "historyView({}, {}, {})".format(json.dumps(points), buy, sell),
                "executionEvidenceView({}, false, 25, 6, 336)".format(
                    json.dumps(points)))
            for field, key in (("buckets", "buckets"),
                               ("baseline_low", "baselineLow"),
                               ("buy_fill_share", "buyFillShare"),
                               ("sell_fill_share", "sellFillShare"),
                               ("trend", "trend"), ("dislocation", "dislocation"),
                               ("median_mid", "medianMid"),
                               ("elevation", "elevation"),
                               ("volatility", "volatility"),
                               ("regime_score", "regimeScore"),
                               ("mean_volume", "meanVolume")):
                self.assertClose(getattr(python, field), view[key],
                                 "seed {} {}".format(seed, field))
            for field, key in (("kappa", "kappa"), ("mu", "mu"),
                               ("sigma", "sigma"), ("t_stat", "tStat")):
                self.assertClose(getattr(python.ou, field), view["ou"][key],
                                 "seed {} ou {}".format(seed, field))
            for field, key in (("buckets", "buckets"),
                               ("profitable_buckets", "profitableBuckets"),
                               ("positive_share", "positiveShare"),
                               ("median_net_margin", "medianNetMargin"),
                               ("edge_throughput_gp_hour", "edgeThroughputGpHour")):
                self.assertClose(getattr(long_python, field), long_browser[key],
                                 "seed {} evidence {}".format(seed, field))

    def test_execution_choice_matches_including_bond_capital(self):
        cases = [
            dict(base_buy=1_000, base_sell=1_100, tax_exempt=False, bond=False,
                 limit=10_000, capital=5_000_000, mode="active", hours=4.0),
            dict(base_buy=180, base_sell=215, tax_exempt=True, bond=False,
                 limit=13_000, capital=1_000_000, mode="overnight", hours=8.0),
            dict(base_buy=9_000_000, base_sell=10_600_000, tax_exempt=True,
                 bond=True, limit=100, capital=50_000_000, mode="active",
                 hours=4.0),
        ]
        expressions = []
        for case in cases:
            expressions.append(
                "optimiseExecution({{baseBuy:{base_buy}, baseSell:{base_sell},"
                " exempt:{exempt}, bond:{bond}, limit:{limit},"
                " config:{{capital:{capital}, maxPositionCapital:{capital},"
                " strategy:\"{mode}\", horizonHours:{hours}}},"
                " buyVolume1h:3000, sellVolume1h:2500, quoteAge:60, ofi:0.1,"
                " drift:0, now:{now}, competitors:9, highalch:null,"
                " natureCost:100}})".format(
                    **dict(case, exempt=str(case["tax_exempt"]).lower(),
                           bond=str(case["bond"]).lower(), now=NOW)))
        for case, browser in zip(cases, js(*expressions)):
            config = filters.FilterConfig(
                capital=case["capital"], trade_mode=case["mode"],
                overnight_hours=case["hours"] if case["mode"] == "overnight"
                else engine.DEFAULT_OVERNIGHT_HOURS)
            buy, sell, _, _, qty, breakdown = filters._optimise_execution(
                base_buy=case["base_buy"], base_sell=case["base_sell"],
                tax_exempt=case["tax_exempt"], bond=case["bond"],
                limit=case["limit"], available_capital=case["capital"],
                buy_volume_1h=3000, sell_volume_1h=2500, quote_age=60,
                ofi=0.1, drift=0.0, now=NOW, highalch=None, competitors=9,
                config=config)
            label = "{} {}".format(case["mode"], case["base_buy"])
            self.assertEqual((buy, sell, qty),
                             (browser["buy"], browser["sell"], browser["qty"]),
                             label)
            self.assertClose(breakdown.capital_needed,
                             browser["breakdown"]["capitalNeeded"], label)
            self.assertClose(breakdown.ranking_value,
                             browser["breakdown"]["rankingValue"], label)


if __name__ == "__main__":
    unittest.main()
