"""Executable parity between the Python model and the browser port.

test_docs_port.py checks that constants and structures were copied. This file
checks that the two implementations compute the same numbers: every case runs
through engine/stats/filters here and through the real inline script of
docs/index.html under Node, and the results must agree.

Tolerances: integer GP arithmetic must match exactly. Probabilities use a
relative tolerance of 1e-5 for the transcendental functions the two runtimes
implement separately; model gp values additionally allow 0.01 gp.
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

    def test_decimal_average_history_is_cleaned_identically(self):
        import api
        rows = [
            {"timestamp": NOW - 5 * 300, "avgHighPrice": 649036.25,
             "avgLowPrice": 643121, "highPriceVolume": 4, "lowPriceVolume": 7},
            {"timestamp": NOW - 4 * 300, "avgHighPrice": 648416.5,
             "avgLowPrice": 641999.75, "highPriceVolume": 2, "lowPriceVolume": 1},
            {"timestamp": NOW - 3 * 300, "avgHighPrice": 0.4,
             "avgLowPrice": 640000.01, "highPriceVolume": 9, "lowPriceVolume": 3},
            {"timestamp": NOW - 2 * 300, "avgHighPrice": None,
             "avgLowPrice": 642500.49, "highPriceVolume": 0, "lowPriceVolume": 5},
            {"timestamp": NOW - 300, "avgHighPrice": 650000.5,
             "avgLowPrice": 99.99, "highPriceVolume": 1, "lowPriceVolume": 8},
        ]
        python = api.clean_history(rows)
        browser = js("cleanHistory({})".format(json.dumps(rows)))[0]
        self.assertEqual(python, browser)
        self.assertEqual([row["avgHighPrice"] for row in python],
                         [649036, 648417, None, None, 650001])

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
            ("crossingShare(8)", engine.crossing_share(competitors=8)),
            ("crossingShare(134, 'active')",
             engine.crossing_share(competitors=134)),
            ("crossingShare(134, 'overnight')", engine.crossing_share(
                competitors=134, mode=engine.TradeMode.OVERNIGHT)),
            ("crossingShare(20, 'profit')", engine.crossing_share(
                competitors=20, mode=engine.TradeMode.PROFIT)),
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

    def test_category_cap_matches(self):
        cases = [({"other": 40}, "other"), ({"runes": 2}, "runes"),
                 ({"runes": 3}, "runes"), ({}, "potions")]
        self.assertEqual(
            js(*("categoryFull({}, {})".format(json.dumps(counts),
                                               json.dumps(category))
                 for counts, category in cases)),
            [filters.category_full(counts, category)
             for counts, category in cases])
        self.assertEqual(js("[CATEGORY_CAP, UNCATEGORISED]")[0],
                         [filters.CATEGORY_CAP, filters.UNCATEGORISED])

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

    def test_fill_time_distribution_matches(self):
        sigma = engine.fill_log_sigma(verified=True)
        mu = engine.fill_log_mu()
        cases = []
        for p in (0.02, 0.1, 0.5, 0.8, 0.9, 0.975, 0.999):
            cases.append(("normalQuantile({})".format(p),
                          engine.normal_quantile(p)))
        for verified in (False, True):
            cases.append(("fillLogSigma({})".format(str(verified).lower()),
                          engine.fill_log_sigma(verified=verified)))
        for work in (0.0, 30.0, 1_800.0, 20_000.0):
            for p in engine.ETA_PERCENTILES:
                cases.append(("fillTimeQuantile({}, {}, {}, 120, {})".format(
                    work, p, sigma, mu),
                    engine.fill_time_quantile(work, p, sigma, 120, mu)))
            cases.append(("expectedOccupancySeconds({}, 14400, {}, 120, {})"
                          .format(work, sigma, mu),
                          engine.expected_occupancy_seconds(
                              work, 14_400, sigma, 120, mu)))
            cases.append(("repriceCheckSeconds({}, {})".format(work, sigma),
                          engine.reprice_check_seconds(work, sigma)))
        for rate in (0.0, 0.01, 0.4, 25.0):
            cases.append(("targetQuantity({}, 14280, 0.8, {}, {})".format(
                rate, sigma, mu),
                engine.target_quantity(rate, 14_280, 0.8, sigma, mu)))
        cases.append(("roundTripRate(0.5, 2)", engine.round_trip_rate(0.5, 2)))
        results = js(*(expression for expression, _ in cases))
        for (expression, python), browser in zip(cases, results):
            self.assertClose(python, browser, expression)

    def test_away_primitives_match(self):
        cases = [("alchProtectedUnits(4)", engine.alch_protected_units(4))]
        for depth, sigma, hours in ((0.0, 0.05, 8), (0.01, 0.05, 8),
                                    (0.05, 0.08, 2), (0.08, 0.2, 12)):
            cases.append(("dipFillMultiplier({}, {}, {})".format(
                depth, sigma, hours),
                engine.dip_fill_multiplier(depth, sigma, hours)))
        mids = [p for p in (engine._bucket_vwap([point]) for point in history(3))
                if p is not None]
        fit = stats.fit_ou(mids, engine.HISTORY_BUCKET_DAYS)
        cases.append(("dipExitRetention(fitOU({}, HISTORY_BUCKET_DAYS), 6)"
                      .format(json.dumps(mids)),
                      engine.dip_exit_retention(fit, 6)))
        points = history(5)
        view = engine.history_view(points, 985, 1_030)
        for field, key in (("low_volume_per_hour", "lowVolumePerHour"),
                           ("high_volume_per_hour", "highVolumePerHour")):
            cases.append(("historyView({}, 985, 1030).{}".format(
                json.dumps(points), key), getattr(view, field)))
        results = js(*(expression for expression, _ in cases))
        for (expression, python), browser in zip(cases, results):
            self.assertClose(python, browser, expression[:60])

    def test_away_execution_choice_matches_including_dip_bids(self):
        reverting = stats.OUFit(kappa=6.0, mu=math.log(1_000), sigma=0.12,
                                t_stat=-6.0, n=56, dt_days=0.25)
        cases = [
            # A reverting item where a dip bid wins, and one where it cannot.
            dict(ou=reverting, base_sell=1_040, volume=40_000.0, hours=8.0),
            dict(ou=None, base_sell=1_080, volume=3_000.0, hours=2.0),
            dict(ou=reverting, base_sell=1_080, volume=500.0, hours=12.0),
        ]
        for case in cases:
            ou = case["ou"]
            ou_js = ("null" if ou is None else
                     "{{kappa:{}, mu:{}, sigma:{}, tStat:{}, meanReverting:true,"
                     " expectedLogReturn(price, days) {{ return price <= 0 ||"
                     " days <= 0 || this.kappa <= 0 ? 0 : (this.mu -"
                     " Math.log(price)) * (1 - Math.exp(-this.kappa * days));"
                     " }}}}".format(ou.kappa, ou.mu, ou.sigma, ou.t_stat))
            expression = (
                "optimiseExecution({{baseBuy:1000, baseSell:{base_sell},"
                " exempt:false, bond:false, limit:20000,"
                " config:{{capital:50000000, maxPositionCapital:50000000,"
                " strategy:\"overnight\", horizonHours:{hours}}},"
                " buyVolume1h:{volume}, sellVolume1h:{volume}, quoteAge:60,"
                " ofi:0, drift:0, now:{now}, competitors:9, highalch:null,"
                " natureCost:100, sigmaDaily:{sigma}, ou:{ou}}})".format(
                    base_sell=case["base_sell"], hours=case["hours"],
                    volume=case["volume"], now=NOW,
                    sigma=json.dumps(ou.sigma if ou else None), ou=ou_js))
            browser = js(expression)[0]
            config = filters.FilterConfig(capital=50_000_000,
                                          trade_mode="overnight",
                                          overnight_hours=case["hours"])
            python = filters._optimise_execution(
                base_buy=1_000, base_sell=case["base_sell"], tax_exempt=False,
                limit=20_000, available_capital=50_000_000,
                buy_volume_1h=case["volume"], sell_volume_1h=case["volume"],
                quote_age=60, ofi=0.0, drift=0.0, now=NOW, highalch=None,
                competitors=9, config=config,
                sigma_daily=ou.sigma if ou else None, ou_fit=ou)
            label = "away {}".format(case)
            self.assertEqual((python.buy, python.sell, python.qty),
                             (browser["buy"], browser["sell"], browser["qty"]),
                             label)
            self.assertClose(python.dip_depth, browser["dipDepth"], label)
            self.assertClose(python.breakdown.ranking_value,
                             browser["breakdown"]["rankingValue"], label,
                             abs_tol=0.01)
            self.assertClose(python.breakdown.downside_risk_gp,
                             browser["breakdown"]["downsideRisk"], label,
                             abs_tol=0.01)
        self.assertLess(filters._optimise_execution(
            base_buy=1_000, base_sell=1_040, tax_exempt=False, limit=20_000,
            available_capital=50_000_000, buy_volume_1h=40_000.0,
            sell_volume_1h=40_000.0, quote_age=60, ofi=0.0, drift=0.0,
            now=NOW, highalch=None, competitors=9,
            config=filters.FilterConfig(capital=50_000_000,
                                        trade_mode="overnight"),
            sigma_daily=0.12, ou_fit=reverting).buy, 1_000,
            "the first case must exercise a dip bid")

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
                    ("downside_risk_gp", "downsideRisk"),
                    ("total_seconds", "totalSeconds"),
                    ("fill_log_sigma", "fillLogSigma"),
                    ("round_trip_p80_seconds", "roundTripP80Seconds"),
                    ("round_trip_p90_seconds", "roundTripP90Seconds"),
                    ("expected_occupancy_seconds", "expectedOccupancySeconds"),
                    ("reprice_check_seconds", "repriceCheckSeconds"),
                    ("cancel_by_seconds", "cancelBySeconds")):
                # A hundredth of a gp: a difference of two near-equal fill
                # quantities magnifies the CDF approximation, never a real gp.
                self.assertClose(getattr(python, field), browser[key],
                                 "{} {}".format(label, field), abs_tol=0.01)

    def test_max_profit_score_execution_and_warnings_match(self):
        mids = [p for p in (engine._bucket_vwap([point]) for point in history(3))
                if p is not None]
        fit = stats.fit_ou(mids, engine.HISTORY_BUCKET_DAYS)
        base = dict(buy=1_000, sell=1_080, margin=58, qty=600, depth=3,
                    buy_volume_1h=2_400.0, sell_volume_1h=1_900.0,
                    quote_age=240, ofi=-0.2, drift=-0.004, now=NOW,
                    highalch=1_100, nature_rune_cost=110, competitors=12.0,
                    buy_improvement=2, sell_improvement=1,
                    mode=engine.TradeMode.PROFIT)
        cases = [
            base,
            # Unsold at the deadline, alch floor close enough to protect.
            dict(base, qty=5_000, buy_volume_1h=400.0, sell_volume_1h=60.0),
            # Past the weekly update, explicit horizon, bond-style capital.
            dict(base, now=NOW + 3 * 86_400, horizon_hours=24.0,
                 sigma_daily=0.09, capital_per_unit=1_100),
        ]
        expressions = []
        for case in cases:
            expressions.append(
                "scoreFlip({{buy:{buy}, sell:{sell}, margin:{margin}, qty:{qty},"
                " depth:{depth}, buyVolume1h:{buy_volume_1h},"
                " sellVolume1h:{sell_volume_1h}, quoteAge:{quote_age},"
                " ofi:{ofi}, drift:{drift}, now:{now}, sigmaDaily:{sigma},"
                " ou:fitOU({mids}, HISTORY_BUCKET_DAYS), regimeScore:0,"
                " highalch:{highalch}, natureCost:{nature_rune_cost},"
                " competitors:{competitors}, buyImprovement:{buy_improvement},"
                " sellImprovement:{sell_improvement}, mode:\"profit\","
                " horizonHours:{horizon}, capitalPerUnit:{capital}}})".format(
                    **dict(case, mids=json.dumps(mids),
                           sigma=json.dumps(case.get("sigma_daily")),
                           horizon=json.dumps(case.get("horizon_hours")),
                           capital=json.dumps(case.get("capital_per_unit")))))
        browsers = js(*expressions)
        warnings = js(*("timingWarnings({})".format(json.dumps(browser))
                        for browser in browsers))
        for case, browser, notes in zip(cases, browsers, warnings):
            python = engine.score_flip(ou_fit=fit, **case)
            label = "profit qty {} now {}".format(case["qty"], case["now"])
            self.assertEqual(browser["mode"], "profit", label)
            self.assertEqual(browser["horizonHours"], 24, label)
            self.assertEqual(set(browser["factors"]), {
                "both legs fill", "adverse selection", "holding risk",
                "quote staleness", "mean reversion", "alch floor",
                "update risk"}, label)
            for field, key in (
                    ("capital_needed", "capitalNeeded"),
                    ("p_fill_both", "pFill"), ("p_stranded", "pStranded"),
                    ("expected_buy_qty", "expectedBuyQty"),
                    ("expected_sell_qty", "expectedSellQty"),
                    ("fill_low_qty", "fillLowQty"), ("fill_high_qty", "fillHighQty"),
                    ("holding_risk", None), ("update_risk", None),
                    ("expected_profit", "expected"),
                    ("gp_per_slot_hour", "perSlotHour"),
                    ("ranking_value", "rankingValue"),
                    ("downside_risk_gp", "downsideRisk"),
                    ("round_trip_p80_seconds", "roundTripP80Seconds"),
                    ("round_trip_p90_seconds", "roundTripP90Seconds"),
                    ("expected_occupancy_seconds", "expectedOccupancySeconds"),
                    ("reprice_check_seconds", "repriceCheckSeconds"),
                    ("cancel_by_seconds", "cancelBySeconds")):
                value = (browser[key] if key else browser["factors"][
                    "holding risk" if field == "holding_risk" else "update risk"])
                self.assertClose(getattr(python, field), value,
                                 "{} {}".format(label, field), abs_tol=0.01)
            prefixes = ("fill odds:", "inventory risk:")
            self.assertEqual(
                [note.split(":")[0] for note in filters._timing_warnings(
                    python, engine.DEFAULT_CALIBRATION)
                 if note.startswith(prefixes)],
                [note.split(":")[0] for note in notes
                 if note.startswith(prefixes)], label)
        self.assertGreater(engine.score_flip(ou_fit=fit, **cases[1])
                           .downside_risk_gp, 0, "case 2 must strand stock")

        executions = [
            dict(base_buy=1_000, base_sell=1_030, volume=6_000.0, limit=2_000,
                 tax_exempt=False, bond=False, capital=50_000_000),
            dict(base_buy=20_000, base_sell=21_500, volume=30.0, limit=100,
                 tax_exempt=False, bond=False, capital=50_000_000),
            dict(base_buy=20_000, base_sell=20_800, volume=30.0, limit=100,
                 tax_exempt=False, bond=False, capital=50_000_000),
            dict(base_buy=9_000_000, base_sell=10_600_000, volume=40.0,
                 limit=100, tax_exempt=True, bond=True, capital=50_000_000),
        ]
        expressions = [
            "optimiseExecution({{baseBuy:{base_buy}, baseSell:{base_sell},"
            " exempt:{exempt}, bond:{bond}, limit:{limit},"
            " config:{{capital:{capital}, maxPositionCapital:{capital},"
            " strategy:\"profit\", horizonHours:24}},"
            " buyVolume1h:{volume}, sellVolume1h:{volume}, quoteAge:60, ofi:0,"
            " drift:0, now:{now}, competitors:8, highalch:null,"
            " natureCost:100}})".format(
                **dict(case, exempt=str(case["tax_exempt"]).lower(),
                       bond=str(case["bond"]).lower(), now=NOW))
            for case in executions]
        for case, browser in zip(executions, js(*expressions)):
            config = filters.FilterConfig(capital=case["capital"],
                                          trade_mode="profit")
            python = filters._optimise_execution(
                base_buy=case["base_buy"], base_sell=case["base_sell"],
                tax_exempt=case["tax_exempt"], bond=case["bond"],
                limit=case["limit"], available_capital=case["capital"],
                buy_volume_1h=case["volume"], sell_volume_1h=case["volume"],
                quote_age=60, ofi=0.0, drift=0.0, now=NOW, highalch=None,
                competitors=8, config=config)
            label = "profit execution {}".format(case["base_buy"])
            self.assertEqual((python.buy, python.sell, python.qty),
                             (browser["buy"], browser["sell"], browser["qty"]),
                             label)
            self.assertLessEqual(python.qty, case["limit"], label)
            # The browser CDF's ~1e-8 error moves an expected quantity by a
            # few thousandths of a unit when the 24-hour capacity is large,
            # and the stress charge prices each stranded unit at up to half
            # its buy price. Quantities must agree to 0.005 units; gp values
            # may differ by what 0.005 units are worth, never more.
            unit_tol = 0.005
            for field, key in (("expected_buy_qty", "expectedBuyQty"),
                               ("expected_sell_qty", "expectedSellQty")):
                self.assertClose(getattr(python.breakdown, field),
                                 browser["breakdown"][key],
                                 "{} {}".format(label, field),
                                 abs_tol=unit_tol)
            for field, key in (("ranking_value", "rankingValue"),
                               ("downside_risk_gp", "downsideRisk"),
                               ("p_fill_both", "pFill"),
                               ("capital_needed", "capitalNeeded")):
                self.assertClose(getattr(python.breakdown, field),
                                 browser["breakdown"][key],
                                 "{} {}".format(label, field),
                                 abs_tol=max(0.01, unit_tol * python.buy))

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
                config=config)[:6]
            label = "{} {}".format(case["mode"], case["base_buy"])
            self.assertEqual((buy, sell, qty),
                             (browser["buy"], browser["sell"], browser["qty"]),
                             label)
            self.assertClose(breakdown.capital_needed,
                             browser["breakdown"]["capitalNeeded"], label)
            self.assertClose(breakdown.ranking_value,
                             browser["breakdown"]["rankingValue"], label)

    def test_half_way_values_round_the_same_way(self):
        """Regression, audit 2026-11: Python's round() sends halves to the
        even neighbour and Math.round sends them up, so the price grid and
        the reference price differed by one gp on exactly these inputs. On
        real data that changed one or two offers in a third of the simulated
        bank histories."""
        maxima = list(range(0, 401))
        browser = js(*["concessionPoints({})".format(m) for m in maxima])
        for maximum, points in zip(maxima, browser):
            self.assertEqual(filters._concession_points(maximum), points,
                             "concession grid for {}".format(maximum))
        # 30 * 0.35 = 10.5: the case that used to give 10 here, 11 there.
        self.assertIn(11, filters._concession_points(30))
        halves = [(100, 1, 101, 1), (7, 3, 8, 3), (2, 1, 5, 1), (10, 2, 11, 6)]
        self.assertEqual(
            js(*["referencePrice({}, {}, {}, {})".format(*case)
                 for case in halves]),
            [engine.reference_price(*case) for case in halves])
        self.assertEqual(engine.reference_price(100, 1, 101, 1), 101)
        self.assertEqual([engine.round_half_up(v) for v in
                          (0.5, 1.5, 2.5, 2.4999, -0.5)], [1, 2, 3, 2, 0])

    def recent(self, seed: int, buckets: int = 365) -> list:
        """A 5-minute series with gaps, drift and one-sided buckets."""
        rng = random.Random(seed)
        price, points = 1_000.0, []
        for index in range(buckets):
            price *= math.exp(rng.gauss(0.0, 0.004))
            quiet = index % 11 == 0
            points.append({
                "timestamp": NOW - (buckets - index) * 300,
                "avgHighPrice": int(price * 1.012),
                "avgLowPrice": None if quiet else int(price * 0.99),
                "highPriceVolume": rng.randint(0, 400),
                "lowPriceVolume": 0 if quiet else rng.randint(1, 400)})
        return points

    def test_reach_view_matches_exactly(self):
        expressions, expected = [], []
        for seed in (3, 4):
            points = self.recent(seed)
            view = engine.reach_view(points)
            prices = [(990, 0.0), (1_000, 0.0), (1_000, 0.5), (1_010, 1.0)]
            expressions.append(
                "(() => {{ const r = reachView({}); return [r.hours, "
                "r.lows.length, r.highs.length, r.lowVolumePerHour, "
                "r.highVolumePerHour, {}]; }})()".format(
                    json.dumps(points), ", ".join(
                        "r.buyVolumePerHour({0}, {1}), "
                        "r.sellVolumePerHour({0}, {1})".format(price, weight)
                        for price, weight in prices)))
            row = [view.hours, len(view.lows), len(view.highs),
                   view.low_volume_per_hour, view.high_volume_per_hour]
            for price, weight in prices:
                row += [view.buy_volume_per_hour(price, weight),
                        view.sell_volume_per_hour(price, weight)]
            expected.append(row)
        expressions.append("reachView({})".format(json.dumps(self.recent(1, 8))))
        expected.append(None)
        # Sums of integers divided by the same hours: no tolerance needed.
        self.assertEqual(js(*expressions), expected)

    def test_replay_matches_exactly_in_every_strategy(self):
        fields = (("placements", "placements"), ("mean_profit", "meanProfit"),
                  ("completion_rate", "completionRate"),
                  ("bought_share", "boughtShare"), ("sold_share", "soldShare"),
                  ("loss_rate", "lossRate"),
                  ("mean_slot_hours", "meanSlotHours"),
                  ("older_profit", "olderProfit"),
                  ("newer_profit", "newerProfit"),
                  ("stable_profit", "stableProfit"))
        cases = [dict(buy=995, sell=1_012, qty=300, buy_share=0.125,
                      sell_share=0.1, mode=mode, hours=hours, exempt=exempt,
                      seed=seed)
                 for mode, hours in (("active", 4.0), ("overnight", 8.0),
                                     ("profit", 24.0))
                 for exempt in (False, True) for seed in (3, 4)]
        cases.append(dict(buy=1_001, sell=1_009, qty=5, buy_share=0.5,
                          sell_share=0.5, mode="active", hours=4.0,
                          exempt=False, seed=9))
        expressions = [
            "replayOffer({points}, {{buy:{buy}, sell:{sell}, qty:{qty}, "
            "buyShare:{buy_share}, sellShare:{sell_share}, mode:\"{mode}\", "
            "horizonHours:{hours}, exempt:{flag}, bond:false}})".format(
                points=json.dumps(self.recent(case["seed"])),
                flag=str(case["exempt"]).lower(), **case)
            for case in cases]
        for case, browser in zip(cases, js(*expressions)):
            python = engine.replay_offer(
                self.recent(case["seed"]), buy=case["buy"], sell=case["sell"],
                qty=case["qty"], buy_share=case["buy_share"],
                sell_share=case["sell_share"], mode=case["mode"],
                horizon_hours=case["hours"], tax_exempt=case["exempt"])
            self.assertIsNotNone(python, case)
            for field, key in fields:
                # Same operations in the same order: bit-identical floats.
                self.assertEqual(getattr(python, field), browser[key],
                                 "{} {}".format(case, field))
        short = js("replayOffer({}, {{buy:995, sell:1012, qty:10, buyShare:0.1, "
                   "sellShare:0.1, mode:\"active\", horizonHours:4}})".format(
                       json.dumps(self.recent(3, 40))))
        self.assertEqual(short, [None])

    def test_portfolio_selection_matches_exactly(self):
        rng = random.Random(5)
        cases = []
        for _ in range(250):
            options = []
            for _ in range(rng.randint(0, 12)):
                value = coins = 0
                sizes = []
                for _ in range(rng.randint(0, 4)):
                    coins += rng.randint(1, 400_000)
                    value += rng.uniform(-5, 60)
                    sizes.append((value, coins))
                options.append(sizes)
            cases.append((options, rng.randint(0, 1_500_000),
                          rng.randint(0, 8)))
        browser = js(*["selectPortfolio({}, {}, {})".format(
            json.dumps(options), capital, slots)
            for options, capital, slots in cases])
        for (options, capital, slots), result in zip(cases, browser):
            python = engine.select_portfolio(options, capital, slots)
            self.assertEqual(
                (list(python.choices), python.capital_price, python.binding),
                (result["choices"], result["capitalPrice"], result["binding"]))


try:
    import numpy
except ImportError:                      # the CLI and agent stay stdlib-only
    numpy = None

FIXTURE = Path(__file__).parent / "fixtures" / "backtest_panel.npz"


@unittest.skipIf(NODE is None or numpy is None or not FIXTURE.exists(),
                 "Node.js, numpy and the committed fixture are required")
class PlanParityTests(unittest.TestCase):
    """The whole plan, both implementations, one real market.

    The fixture is a slice of real OSRS Wiki price history. Each case builds
    the market snapshot a player would have seen at one moment, runs
    filters.rank_flips under the automatic profile, runs the browser's own
    screen -> deep check -> buildPlan on the same snapshot under Node, and
    requires the same items at the same prices and quantities, the same
    expected profit to the gp, and the same stated reason.
    """

    @classmethod
    def setUpClass(cls):
        import exemptions
        from backtest import browser, run
        from backtest.panel import Panel
        cls.browser, cls.walk_forward = browser, run
        cls.panel = Panel.load(FIXTURE)
        cls.exempt = exemptions.resolve(cls.panel.items)
        cls.planner = browser.BrowserPlanner()
        cls.times = run.segments(cls.panel, "active", "all")[0]

    @classmethod
    def tearDownClass(cls):
        cls.planner.close()

    def plans(self, strategy, t, capital, account="members"):
        import exemptions
        mode, horizon, _, _ = self.walk_forward.STRATEGIES[strategy]
        panel = self.panel
        snapshot = panel.snapshot(t)
        nature = exemptions.nature_rune_cost(snapshot.quotes)
        config = filters.automatic_profile(filters.FilterConfig(
            capital=capital, account=account, trade_mode=mode,
            overnight_hours=horizon if mode == "overnight"
            else engine.DEFAULT_OVERNIGHT_HOURS, nature_rune_cost=nature))

        def series(item_id):
            return panel.recent_5m(item_id, t, self.browser.RECENT_HOURS)
        result = filters.rank_flips(
            snapshot.items, snapshot.quotes, snapshot.activity_5m,
            snapshot.activity_1h, config, t,
            fetch_history=lambda item_id: panel.history_6h(item_id, t),
            exempt=self.exempt, fetch_recent=series, fetch_reach=series)
        python = [row for row in result.rows if row.allocated_quantity]
        key = self.planner.prepare(panel, snapshot, capital, account, mode,
                                   horizon, nature)
        try:
            javascript = self.planner.allocate(key, capital, config.slots)
        finally:
            self.planner.release(key)
        return python, javascript, result

    def test_python_and_browser_fund_the_same_plan_to_the_gp(self):
        funded = 0
        bindings = set()
        for strategy in ("active", "overnight", "profit"):
            for t in (self.times[3], self.times[40]):
                for capital in (2_000_000, 150_000):
                    python, javascript, result = self.plans(strategy, t, capital)
                    label = "{} t={} bank={}".format(strategy, t, capital)
                    self.assertEqual(
                        sorted((r.item_id, r.buy, r.sell, r.allocated_quantity,
                                r.allocated_capital) for r in python),
                        sorted((r["id"], r["buy"], r["sell"], r["qty"],
                                r["capital"]) for r in javascript), label)
                    browser = {row["id"]: row for row in javascript}
                    for row in python:
                        other = browser[row.item_id]
                        self.assertEqual(round(row.allocated_expected_gp),
                                         round(other["expected"]), label)
                        self.assertClose(row.allocated_expected_gp,
                                         other["expected"], label, abs_tol=1e-6)
                        self.assertClose(row.replay.stable_profit,
                                         other["replayStable"], label,
                                         abs_tol=1e-6)
                        self.assertClose(row.p_fill, other["pFill"], label)
                        self.assertEqual(row.plan_reason, other["reason"], label)
                    self.assertLessEqual(
                        sum(row.allocated_capital for row in python), capital)
                    funded += len(python)
                    if result.selection is not None:
                        bindings.add(result.selection.binding)
        # The cases must actually exercise the plan, not agree on nothing.
        self.assertGreater(funded, 10)
        self.assertGreater(len(bindings), 1)

    def test_a_bank_above_one_coin_stack_plans_the_same(self):
        capital = 5_000_000_000
        self.assertEqual(js("MAX_GE_CAPITAL")[0], engine.MAX_GE_CAPITAL)
        python, javascript, _ = self.plans("active", self.times[3], capital)
        self.assertTrue(python)
        self.assertEqual(
            sorted((r.item_id, r.buy, r.sell, r.allocated_quantity,
                    r.allocated_capital) for r in python),
            sorted((r["id"], r["buy"], r["sell"], r["qty"], r["capital"])
                   for r in javascript))
        self.assertLessEqual(sum(r.allocated_capital for r in python), capital)

    def test_free_to_play_profile_matches_too(self):
        python, javascript, _ = self.plans("active", self.times[20], 500_000,
                                           account="free-to-play")
        self.assertLessEqual(len(python), 3)
        self.assertEqual(
            sorted((r.item_id, r.buy, r.sell, r.allocated_quantity)
                   for r in python),
            sorted((r["id"], r["buy"], r["sell"], r["qty"])
                   for r in javascript))

    assertClose = ParityTests.assertClose

    def test_profile_constants_are_the_same_policy(self):
        for capital, account, mode in ((5_000_000, "members", "active"),
                                       (20_000_000, "members", "overnight"),
                                       (20_000_000, "free-to-play", "profit")):
            profile = filters.automatic_profile(filters.FilterConfig(
                capital=capital, account=account, trade_mode=mode))
            browser = js("automaticFilterProfile({}, \"{}\", \"{}\", 25)".format(
                capital, account, mode))[0]
            self.assertEqual(
                (profile.max_quote_age, profile.min_thin_volume_1h,
                 profile.min_roi, profile.min_undercut_depth,
                 profile.max_price, profile.max_position_capital,
                 profile.hide_botted, profile.funding_evidence,
                 profile.replay_statistic, profile.replay_ranking,
                 profile.allocation, profile.active_objective),
                (browser["maxQuoteAge"], browser["minVolume1h"],
                 browser["minRoi"], browser["minUndercutDepth"],
                 browser["maxPrice"], browser["maxPositionCapital"],
                 browser["hideBotted"], browser["fundingEvidence"],
                 browser["replayStatistic"], browser["replayRanking"],
                 browser["allocation"], browser["activeObjective"]))


if __name__ == "__main__":
    unittest.main()
