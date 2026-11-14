"""Metrics, calibration tables and day-block bootstrap intervals.

Definitions (all realised by the fill simulator, never predicted):

  bank gp/hour       sum(pnl) / wall-clock hours the bank was run: what the
                     whole bank earned per hour, idle slots and idle coins
                     included. The headline number.
  bank gp/hour (patient)  the same with unsold stock valued at the next
                     instant-buy price instead of dumped at the instant-sell
                     price; the two bracket what leftovers are worth
  gp/slot-hour       sum(pnl) / sum(hours a slot was occupied)
  gp/1m-capital-hour sum(pnl) / sum(coins + inventory at cost, in 1m gp-hours)
  roi                sum(pnl) / sum(coins actually spent on bought units)
  win / loss rate    offers with pnl > 0 (< 0) / offers placed
  fill rate          offers that bought anything / offers placed
  completion         offers fully bought and sold in time / offers placed
  p5 flip            5th percentile of per-offer pnl over the coins it locked
  max drawdown       worst peak-to-trough of a bank's realised equity inside a
                     segment, as a share of the starting bank
  slots used, deployed   time-average share of slots / of the bank in offers

Confidence intervals resample whole UTC days with replacement (a flip belongs
to the day it was placed), so offers that shared a market stay together.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

DAY = 86400
BOOTSTRAP_DRAWS = 2000
RATIO_METRICS = ("bank_gp_hour", "bank_gp_hour_patient", "gp_slot_hour",
                 "gp_capital_hour", "roi")
_PNL, _SLOT, _CAPITAL, _WALL, _SPENT, _PATIENT = range(6)


def flips(records: Iterable[dict], method: str, variant: str) -> List[dict]:
    """Every offer one method placed under one fill variant."""
    out = []
    for record in records:
        bank = record["banks"].get(method, {}).get(variant)
        if bank:
            out.extend(bank["flips"])
    return out


def _day_sums(records: Sequence[dict], method: str, variant: str
              ) -> Tuple[List[int], np.ndarray]:
    sums: Dict[int, List[float]] = defaultdict(lambda: [0.0] * 6)
    for record in records:
        bank = record["banks"].get(method, {}).get(variant)
        if not bank:
            continue
        for point in bank["equity"]:
            sums[point[0] // DAY][_WALL] += record["step_hours"]
        for flip in bank["flips"]:
            row = sums[flip["t"] // DAY]
            row[_PNL] += flip["pnl"]
            row[_SLOT] += flip["slot_h"]
            row[_CAPITAL] += flip["cap_h"] / 1e6
            row[_SPENT] += flip["bought"] * flip["buy"]
            row[_PATIENT] += flip["pnl_patient"]
    days = sorted(sums)
    return days, np.array([sums[day] for day in days], dtype=float).reshape(-1, 6)


def _ratios(total: np.ndarray) -> Dict[str, np.ndarray]:
    def div(a, b):
        return np.where(b > 0, a / np.where(b > 0, b, 1.0), 0.0)
    pnl = total[..., _PNL]
    return {"bank_gp_hour": div(pnl, total[..., _WALL]),
            "bank_gp_hour_patient": div(total[..., _PATIENT], total[..., _WALL]),
            "gp_slot_hour": div(pnl, total[..., _SLOT]),
            "gp_capital_hour": div(pnl, total[..., _CAPITAL]),
            "roi": div(pnl, total[..., _SPENT])}


def max_drawdown(records: Sequence[dict], method: str, variant: str,
                 capital: float) -> float:
    worst = 0.0
    for record in records:
        bank = record["banks"].get(method, {}).get(variant)
        if not bank:
            continue
        peak = float("-inf")
        for equity in [point[1] for point in bank["equity"]] + [bank["final"]]:
            peak = max(peak, equity)
            worst = max(worst, peak - equity)
    return worst / capital if capital else 0.0


def summarise(records: Sequence[dict], method: str, variant: str,
              capital: float, slots: int) -> Optional[dict]:
    days, sums = _day_sums(records, method, variant)
    if not days:
        return None
    placed = flips(records, method, variant)
    total = sums.sum(axis=0)
    point = {key: float(value) for key, value in _ratios(total).items()}
    pnls = np.array([f["pnl"] for f in placed], dtype=float)
    locked = np.array([max(1, f["locked"]) for f in placed], dtype=float)
    marks = [mark for record in records
             for mark in record["banks"].get(method, {}).get(variant, {})
             .get("equity", ())]
    point.update({
        "hours": float(total[_WALL]), "days": len(days), "offers": len(placed),
        "pnl_total": float(total[_PNL]),
        "offers_per_day": len(placed) / max(1e-9, total[_WALL] / 24.0),
        "win_rate": float((pnls > 0).mean()) if pnls.size else 0.0,
        "loss_rate": float((pnls < 0).mean()) if pnls.size else 0.0,
        "fill_rate": (float(np.mean([f["bought"] > 0 for f in placed]))
                      if placed else 0.0),
        "completion": (float(np.mean([f["done"] for f in placed]))
                       if placed else 0.0),
        "p5_flip_roi": (float(np.percentile(pnls / locked, 5))
                        if pnls.size else 0.0),
        "p5_flip_gp": float(np.percentile(pnls, 5)) if pnls.size else 0.0,
        "mean_flip_roi": float((pnls / locked).mean()) if pnls.size else 0.0,
        "max_drawdown": max_drawdown(records, method, variant, capital),
        "turnover_per_day": (float(total[_SPENT]) / capital
                             / max(1e-9, total[_WALL] / 24.0)) if capital else 0.0,
        "slots_used": (float(np.mean([mark[2] for mark in marks])) / slots
                       if marks and slots else 0.0),
        "deployed": (float(np.mean([mark[3] / mark[1] for mark in marks
                                    if mark[1] > 0])) if marks else 0.0),
    })
    return point


def bootstrap(records: Sequence[dict], method: str, variant: str,
              baseline: Optional[str] = None, draws: int = BOOTSTRAP_DRAWS,
              seed: int = 20261113, alpha: float = 0.05) -> Dict[str, dict]:
    """Day-block bootstrap. With ``baseline``, also the paired difference.

    Returns metric -> {"lo", "hi"} and, with a baseline, "diff", "diff_lo",
    "diff_hi" and "p_worse": the share of resamples in which the method does
    NOT beat the baseline (a one-sided bootstrap p-value).
    """
    days, sums = _day_sums(records, method, variant)
    if len(days) < 2:
        return {}
    base = None
    if baseline is not None:
        base_days, base_sums = _day_sums(records, baseline, variant)
        lookup = dict(zip(base_days, base_sums))
        base = np.array([lookup.get(day, np.zeros(6)) for day in days])
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(days), size=(draws, len(days)))
    resampled = _ratios(sums[picks].sum(axis=1))
    out = {}
    low, high = 100 * alpha / 2, 100 * (1 - alpha / 2)
    for metric in RATIO_METRICS:
        values = resampled[metric]
        out[metric] = {"lo": float(np.percentile(values, low)),
                       "hi": float(np.percentile(values, high))}
    if base is not None:
        base_point = _ratios(base.sum(axis=0))
        point = _ratios(sums.sum(axis=0))
        base_resampled = _ratios(base[picks].sum(axis=1))
        for metric in RATIO_METRICS:
            diff = resampled[metric] - base_resampled[metric]
            out[metric].update({
                "diff": float(point[metric] - base_point[metric]),
                "diff_lo": float(np.percentile(diff, low)),
                "diff_hi": float(np.percentile(diff, high)),
                "p_worse": float((diff <= 0).mean())})
    return out


# -- calibration -------------------------------------------------------------

P_FILL_BINS = (0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0001)


def reliability(records: Sequence[dict], method: str, variant: str
                ) -> List[dict]:
    """Predicted P(whole round trip in time) against the observed share."""
    placed = [(f["pred"]["p_fill"], f["done"])
              for f in flips(records, method, variant)
              if f["pred"].get("p_fill") is not None]
    rows = []
    for low, high in zip(P_FILL_BINS, P_FILL_BINS[1:]):
        inside = [(p, done) for p, done in placed if low <= p < high]
        if not inside:
            continue
        rows.append({"bin": "{:.0%}-{:.0%}".format(low, min(high, 1.0)),
                     "n": len(inside),
                     "predicted": float(np.mean([p for p, _ in inside])),
                     "observed": float(np.mean([done for _, done in inside]))})
    return rows


def calibration_error(table: Sequence[dict]) -> float:
    """Expected calibration error: n-weighted |predicted - observed|."""
    total = sum(row["n"] for row in table)
    if not total:
        return float("nan")
    return sum(row["n"] * abs(row["predicted"] - row["observed"])
               for row in table) / total


def time_band(records: Sequence[dict], method: str, variant: str) -> dict:
    """Share of offers that finished within their own predicted P50/P80/P90.

    An offer that never completed counts as not finished (censored at the
    deadline), so slow failures cannot flatter the band.
    """
    placed = [f for f in flips(records, method, variant)
              if f["pred"].get("p50") is not None]
    out = {"n": len(placed)}
    for name in ("p50", "p80", "p90"):
        out[name] = (float(np.mean([
            bool(f["done"]) and f["done_s"] <= f["pred"][name]
            for f in placed])) if placed else float("nan"))
    return out


def ev_capture(records: Sequence[dict], method: str, variant: str) -> dict:
    """Realised pnl against the model's expected profit, in aggregate."""
    placed = [f for f in flips(records, method, variant)
              if f["pred"].get("expected_gp") is not None]
    predicted = sum(f["pred"]["expected_gp"] for f in placed)
    realised = sum(f["pnl"] for f in placed)
    return {"predicted_gp": predicted, "realised_gp": realised,
            "capture": realised / predicted if predicted > 0 else float("nan")}


def holm(p_values: Dict[str, float], alpha: float = 0.05) -> Dict[str, bool]:
    """Holm step-down: which comparisons survive family-wise ``alpha``."""
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    survives, still = {}, True
    for index, (name, p) in enumerate(ordered):
        still = still and p <= alpha / (len(ordered) - index)
        survives[name] = still
    return survives


def fmt_gp(value: float) -> str:
    if value != value:
        return "n/a"
    sign = "-" if value < 0 else ""
    value = abs(value)
    for suffix, size in (("m", 1e6), ("k", 1e3)):
        if value >= size:
            return "{}{:.1f}{}".format(sign, value / size, suffix)
    return "{}{:.0f}".format(sign, value)
