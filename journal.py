"""SQLite log of actual flips, for calibrating the model against reality.

The first version recorded a name, a quantity, two prices and one predicted
margin. That is enough to say "the tool over-promised by 40%" and nothing more.
It cannot say which part over-promised, because a single realised number cannot
be decomposed into the factors that produced the prediction — and the whole
argument for the rebuild was that an unidentifiable model cannot be fixed by
collecting more outcomes of the same shape.

So every prediction is stored with its parts: the fill-time estimate for each
leg, the probability both legs clear, and every discount factor separately.
Then a shortfall can be attributed. If realised profit tracks predicted profit
but fills take four times as long as forecast, the fill model is wrong and the
price model is fine, and the numbers say so.

Two other things the first version could not record, both of which bias
everything estimated from it:

- Offers that never filled. Dropping them keeps only the flips that worked,
  which is the textbook way to conclude that every flip works. Cancellations
  are censored observations and the fill-time distribution needs them.
- Time. Ranking is by gp per slot-hour, so a flip with no duration attached
  cannot test the metric the tool is optimising.

Library use:  Journal(path).place_offer(...) / mark_bought(...) /
              open_flip(...) / close_flip(...) / cancel_flip(...) / rows()
Terminal use: python3 journal.py place --name "Steel bar" --qty 1000 --buy 571
              python3 journal.py bought 1 [--qty 800]
              python3 journal.py open --name "Steel bar" --qty 1000 --buy 571 \
                  [--id 2353] [--predicted 16]
              python3 journal.py close 1 --sell 598
              python3 journal.py cancel 1 --reason "never filled"
              python3 journal.py list
              python3 journal.py stats
              python3 journal.py calibration
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import engine
import exemptions

DEFAULT_DB = Path(__file__).parent / "journal.db"

BUSY_TIMEOUT_SECONDS = 120

SCHEMA = """
CREATE TABLE IF NOT EXISTS flips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    buy_price INTEGER NOT NULL CHECK (buy_price > 0),
    predicted_margin INTEGER,
    sell_price INTEGER,
    bought_at INTEGER NOT NULL,
    sold_at INTEGER
)
"""

# Added after v1. SQLite has no "ADD COLUMN IF NOT EXISTS", so these are
# applied by diffing against PRAGMA table_info.
COLUMNS_V2 = (
    # No default: NULL means "the tool did not record it", which is different
    # from "recorded as taxable" and falls back to the id list.
    ("tax_exempt", "INTEGER"),
    ("outcome", "TEXT DEFAULT 'open'"),          # open | filled | cancelled
    ("predicted_buy_price", "INTEGER"),
    ("predicted_sell_price", "INTEGER"),
    ("predicted_expected_gp", "REAL"),
    ("predicted_gp_per_slot_hour", "REAL"),
    ("predicted_buy_seconds", "REAL"),
    ("predicted_sell_seconds", "REAL"),
    ("predicted_p_fill", "REAL"),
    ("predicted_rank", "INTEGER"),               # position in the ranking
    ("factors_json", "TEXT"),                    # every discount, separately
    ("calibration_json", "TEXT"),                # parameters in force
    ("snapshot_at", "INTEGER"),                  # when the API was polled
    ("offer_placed_at", "INTEGER"),              # when the offer went in
    ("buy_filled_at", "INTEGER"),
    ("cancel_count", "INTEGER DEFAULT 0"),
    ("cancelled_at", "INTEGER"),
    ("cancel_reason", "TEXT"),
    # Horizon-aware predictions. Public Wiki data cannot tell whether a
    # private offer filled, so these are calibrated only from user-recorded
    # executions rather than inferred from market prints.
    ("trade_mode", "TEXT"),
    ("prediction_horizon_hours", "REAL"),
    ("predicted_ranking_value", "REAL"),
    ("predicted_stranded_probability", "REAL"),
    ("predicted_downside_risk_gp", "REAL"),
    # The fill-time distribution behind the prediction. The *_seconds columns
    # above hold its leg medians; with the log-width every other percentile
    # can be rebuilt, which is what the censored backtest needs.
    ("predicted_fill_log_sigma", "REAL"),
    ("predicted_round_trip_p50_seconds", "REAL"),
    ("predicted_round_trip_p80_seconds", "REAL"),
    ("predicted_round_trip_p90_seconds", "REAL"),
    ("predicted_reprice_check_seconds", "REAL"),
    # Liquidity at entry, to split the backtest into thin/liquid/busy items.
    ("predicted_volume_1h", "REAL"),
    ("predicted_competitors", "REAL"),
)

# Outcome values. 'placed' is a buy offer in the book with nothing recorded as
# bought yet; cancelling one is a censored BUY leg, cancelling an 'open' row a
# censored SELL leg. Without 'placed', an offer that never filled could not be
# written down at all, so the journal only ever saw buys that worked.
OUTCOMES = ("placed", "open", "filled", "cancelled")


class Journal:
    def __init__(self, db_path=DEFAULT_DB):
        self.conn = sqlite3.connect(str(db_path), timeout=BUSY_TIMEOUT_SECONDS)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        existing = {row["name"] for row in
                    self.conn.execute("PRAGMA table_info(flips)")}
        for name, definition in COLUMNS_V2:
            if name not in existing:
                self.conn.execute(
                    "ALTER TABLE flips ADD COLUMN {} {}".format(name, definition))
        # v1 rows predate the outcome column; infer it from what they have.
        self.conn.execute(
            "UPDATE flips SET outcome = CASE WHEN sell_price IS NOT NULL"
            " THEN 'filled' ELSE 'open' END WHERE outcome IS NULL")

    def close(self):
        self.conn.close()

    def __enter__(self) -> "Journal":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- writing ------------------------------------------------------------

    def open_flip(self, item_name: str, quantity: int, buy_price: int,
                  item_id: Optional[int] = None,
                  predicted_margin: Optional[int] = None,
                  bought_at: Optional[int] = None,
                  row: Optional[object] = None,
                  calibration: Optional[engine.Calibration] = None,
                  rank: Optional[int] = None,
                  tax_exempt: Optional[bool] = None,
                  snapshot_at: Optional[int] = None,
                  offer_placed_at: Optional[int] = None,
                  _placed: bool = False) -> int:
        """Record a filled buy offer.

        Pass `row` (a filters.FlipRow) to capture the whole prediction rather
        than just its headline margin. Everything else stays optional so the
        terminal interface remains a three-flag command.
        """
        if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0
               for v in (quantity, buy_price)):
            raise ValueError("quantity and buy_price must be positive integers")
        now = int(time.time())
        bought_at = bought_at if bought_at is not None else now

        fields: Dict[str, object] = {
            "item_id": item_id,
            "item_name": item_name,
            "quantity": quantity,
            "buy_price": buy_price,
            "predicted_margin": predicted_margin,
            "bought_at": bought_at,
            "outcome": "placed" if _placed else "open",
            "tax_exempt": int(bool(tax_exempt)) if tax_exempt is not None else None,
            "snapshot_at": snapshot_at,
            "offer_placed_at": offer_placed_at,
            "buy_filled_at": None if _placed else bought_at,
            "predicted_rank": rank,
        }
        if row is not None:
            fields.update({
                "item_id": item_id if item_id is not None
                else getattr(row, "item_id", None),
                "predicted_margin": (predicted_margin if predicted_margin is not None
                                     else getattr(row, "margin", None)),
                "predicted_buy_price": getattr(row, "buy", None),
                "predicted_sell_price": getattr(row, "sell", None),
                "predicted_expected_gp": getattr(row, "expected_gp", None),
                "predicted_gp_per_slot_hour": getattr(row, "gp_per_slot_hour", None),
                "predicted_buy_seconds": getattr(row, "expected_buy_seconds", None),
                "predicted_sell_seconds": getattr(row, "expected_sell_seconds", None),
                "predicted_p_fill": getattr(row, "p_fill", None),
                "trade_mode": getattr(getattr(row, "trade_mode", None),
                                      "value", None),
                "prediction_horizon_hours": getattr(row, "horizon_hours", None),
                "predicted_ranking_value": getattr(row, "ranking_value", None),
                "predicted_stranded_probability": getattr(row, "p_stranded", None),
                "predicted_downside_risk_gp": getattr(row, "downside_risk_gp", None),
                "predicted_fill_log_sigma": getattr(row, "fill_log_sigma", None) or None,
                "predicted_round_trip_p50_seconds": _finite(getattr(
                    row, "round_trip_p50_seconds", None)),
                "predicted_round_trip_p80_seconds": _finite(getattr(
                    row, "round_trip_p80_seconds", None)),
                "predicted_round_trip_p90_seconds": _finite(getattr(
                    row, "round_trip_p90_seconds", None)),
                "predicted_reprice_check_seconds": _finite(getattr(
                    row, "reprice_check_seconds", None)),
                "predicted_volume_1h": getattr(row, "thin_volume_1h", None),
                "predicted_competitors": getattr(row, "competitors", None),
                "tax_exempt": int(bool(getattr(row, "tax_exempt", False))),
                "factors_json": json.dumps(getattr(row, "factors", {}) or {}),
            })
        for key in ("predicted_buy_seconds", "predicted_sell_seconds"):
            fields[key] = _finite(fields.get(key))
        if calibration is not None:
            fields["calibration_json"] = json.dumps(calibration.__dict__,
                                                    default=str)

        names = [k for k, v in fields.items() if v is not None]
        placeholders = ", ".join("?" for _ in names)
        cursor = self.conn.execute(
            "INSERT INTO flips ({}) VALUES ({})".format(", ".join(names),
                                                        placeholders),
            [fields[name] for name in names])
        self.conn.commit()
        return cursor.lastrowid

    def place_offer(self, item_name: str, quantity: int, buy_price: int,
                    placed_at: Optional[int] = None, **kwargs) -> int:
        """Record a buy offer the moment it goes in, before anything fills.

        This is the only way an offer that never fills reaches the journal.
        Follow with mark_bought when it fills, or cancel_flip when you pull
        it; either way the buy leg is an observation, completed or censored.
        """
        placed_at = placed_at if placed_at is not None else int(time.time())
        return self.open_flip(item_name, quantity, buy_price,
                              bought_at=placed_at, offer_placed_at=placed_at,
                              _placed=True, **kwargs)

    def mark_bought(self, flip_id: int, filled_at: Optional[int] = None,
                    quantity: Optional[int] = None) -> None:
        """The placed buy completed (or was cut to what had filled)."""
        row = self._row(flip_id)
        if row["outcome"] != "placed":
            raise ValueError("flip {} is not a placed, unfilled offer"
                             .format(flip_id))
        filled_at = filled_at if filled_at is not None else int(time.time())
        if row["offer_placed_at"] and filled_at < row["offer_placed_at"]:
            raise ValueError("a fill cannot precede its offer")
        quantity = row["quantity"] if quantity is None else quantity
        if (isinstance(quantity, bool) or not isinstance(quantity, int)
                or not 0 < quantity <= row["quantity"]):
            raise ValueError("quantity must be between 1 and the offer size")
        cursor = self.conn.execute(
            "UPDATE flips SET outcome = 'open', buy_filled_at = ?,"
            " bought_at = ?, quantity = ? WHERE id = ? AND outcome = 'placed'",
            (filled_at, filled_at, quantity, flip_id))
        if cursor.rowcount != 1:
            self.conn.rollback()
            raise ValueError("flip was changed by another writer; reload it")
        self.conn.commit()

    def close_flip(self, flip_id: int, sell_price: int,
                   sold_at: Optional[int] = None) -> None:
        if isinstance(sell_price, bool) or not isinstance(sell_price, int) or sell_price <= 0:
            raise ValueError("sell_price must be a positive integer")
        row = self._row(flip_id)
        if row["sell_price"] is not None:
            raise ValueError("flip {} is already closed".format(flip_id))
        if row["outcome"] == "cancelled":
            raise ValueError("flip {} was cancelled".format(flip_id))
        if row["outcome"] == "placed":
            raise ValueError("flip {} has no recorded buy fill; mark it "
                             "bought first".format(flip_id))
        sold_at = sold_at if sold_at is not None else int(time.time())
        if sold_at < row["bought_at"]:
            raise ValueError("sale cannot precede the purchase")
        cursor = self.conn.execute(
            "UPDATE flips SET sell_price = ?, sold_at = ?, outcome = 'filled'"
            " WHERE id = ? AND outcome = 'open' AND sell_price IS NULL",
            (sell_price, sold_at, flip_id))
        if cursor.rowcount != 1:
            self.conn.rollback()
            raise ValueError("flip was changed by another writer; reload it")
        self.conn.commit()

    def cancel_flip(self, flip_id: int, reason: str = "",
                    cancelled_at: Optional[int] = None) -> None:
        """Record an offer that never filled.

        These are the observations that keep the fill-time estimates honest.
        A journal of completed flips only measures the flips that completed.
        A 'placed' row censors the buy leg; an 'open' row the sell leg.
        """
        row = self._row(flip_id)
        if row["sell_price"] is not None:
            raise ValueError("flip {} already sold".format(flip_id))
        if row["outcome"] == "cancelled":
            raise ValueError("flip {} was already cancelled".format(flip_id))
        cursor = self.conn.execute(
            "UPDATE flips SET outcome = 'cancelled', cancelled_at = ?,"
            " cancel_reason = ?, cancel_count = COALESCE(cancel_count, 0) + 1"
            " WHERE id = ? AND outcome IN ('placed', 'open')"
            " AND sell_price IS NULL",
            (cancelled_at if cancelled_at is not None else int(time.time()),
             reason, flip_id))
        if cursor.rowcount != 1:
            self.conn.rollback()
            raise ValueError("flip was changed by another writer; reload it")
        self.conn.commit()

    def _row(self, flip_id: int):
        row = self.conn.execute(
            "SELECT * FROM flips WHERE id = ?", (flip_id,)).fetchone()
        if row is None:
            raise ValueError("no flip with id {}".format(flip_id))
        return row

    def rows(self):
        return self.conn.execute("SELECT * FROM flips ORDER BY id").fetchall()

    # -- reading ------------------------------------------------------------

    def stats(self) -> dict:
        """Realised totals, capture rate, and how long flips actually took."""
        all_rows = self.rows()
        closed = [r for r in all_rows if r["sell_price"] is not None]
        cancelled = [r for r in all_rows if r["outcome"] == "cancelled"]
        predicted = [r for r in closed if predicted_profit(r) is not None]
        durations = [d for d in (flip_seconds(r) for r in closed) if d]
        predicted_total = sum(predicted_profit(r) or 0 for r in predicted)
        realised_on_predicted = sum(realised_profit(r) for r in predicted)
        return {
            "flips_closed": len(closed),
            "flips_cancelled": len(cancelled),
            "fill_rate": (len(closed) / (len(closed) + len(cancelled))
                          if closed or cancelled else 0.0),
            "realised_profit": sum(realised_profit(r) for r in closed),
            "flips_with_prediction": len(predicted),
            "predicted_profit": predicted_total,
            "realised_on_predicted": realised_on_predicted,
            "capture": (realised_on_predicted / predicted_total
                        if predicted_total else 0.0),
            "median_flip_seconds": _median(durations),
            "realised_gp_per_slot_hour": _realised_rate(closed),
            "sharpe": _sharpe(closed),
        }

    def capture_by_decile(self, deciles: int = 5) -> List[dict]:
        """Capture rate split by predicted rank.

        This is the direct test for the optimizer's curse. If the top of the
        ranking is mostly estimation error, the highest-predicted flips capture
        the least of what they promised, and capture rises as you move down the
        list. If the shrinkage is doing its job the buckets look alike.
        """
        rows = [r for r in self.rows()
                if r["sell_price"] is not None
                and predicted_profit(r) is not None
                and (predicted_profit(r) or 0) > 0]
        if not rows:
            return []
        rows.sort(key=lambda r: predicted_profit(r) or 0, reverse=True)
        size = max(1, len(rows) // deciles)
        out = []
        for index in range(0, len(rows), size):
            group = rows[index:index + size]
            promised = sum(predicted_profit(r) or 0 for r in group)
            got = sum(realised_profit(r) for r in group)
            out.append({
                "bucket": len(out) + 1,
                "flips": len(group),
                "predicted": promised,
                "realised": got,
                "capture": got / promised if promised else 0.0,
            })
        return out

    def fill_time_backtest(self, now: Optional[int] = None,
                           calibration: engine.Calibration
                           = engine.DEFAULT_CALIBRATION) -> List[dict]:
        """Predicted against realised fill times, per leg and liquidity tier.

        The old version compared only flips that sold, which is the textbook
        way to conclude that fills are fast: every offer that sat for hours
        and was pulled simply vanished from the sample. Here an offer that was
        cancelled or is still waiting is a censored observation — it took at
        least that long — and it enters every statistic that can use it.
        """
        now = int(time.time()) if now is None else int(now)
        return backtest_summary(fill_observations(self.rows(), now,
                                                  calibration), calibration)

    def factor_errors(self) -> List[dict]:
        """Mean value of each recorded factor, split by whether the flip beat
        its prediction.

        Not a regression — with the sample sizes a manual journal reaches, a
        regression would be fitting noise. It is the cheap version of the same
        question: are the flips that underperform systematically the ones where
        a particular factor was doing the work?
        """
        beat: Dict[str, List[float]] = {}
        missed: Dict[str, List[float]] = {}
        for row in self.rows():
            if row["sell_price"] is None or not row["factors_json"]:
                continue
            predicted = predicted_profit(row) or 0
            if predicted <= 0:
                continue
            try:
                factors = json.loads(row["factors_json"])
            except (TypeError, ValueError):
                continue
            target = beat if realised_profit(row) >= predicted else missed
            for name, value in factors.items():
                if isinstance(value, (int, float)):
                    target.setdefault(name, []).append(float(value))
        names = sorted(set(beat) | set(missed))
        out = []
        for name in names:
            out.append({
                "factor": name,
                "when_beat": _mean(beat.get(name, [])),
                "when_missed": _mean(missed.get(name, [])),
                "n_beat": len(beat.get(name, [])),
                "n_missed": len(missed.get(name, [])),
            })
        return out


# ---------------------------------------------------------------------------
# Fill-time backtest with censoring
# ---------------------------------------------------------------------------

LEGS = ("buy", "sell", "round_trip")
# Below this many observations a fitted width is noise; report, do not fit.
MIN_FIT_OBSERVATIONS = 20
MIN_FIT_COMPLETED = 5


@dataclass(frozen=True)
class FillObservation:
    leg: str
    predicted_p50: float     # seconds, including the human overhead
    sigma: Optional[float]   # None: a legacy point estimate with no band
    seconds: float           # realised, or time waited so far if censored
    censored: bool           # True: it took at least this long
    cancelled: bool
    tier: str


def _finite(value) -> Optional[float]:
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def liquidity_tier(volume_1h: Optional[float], competitors: Optional[float],
                   calibration: engine.Calibration
                   = engine.DEFAULT_CALIBRATION) -> str:
    """thin: under 100 units/h on the thin side. busy: the crowd term binds,
    so the queue, not the volume, sets the rate. liquid: everything else."""
    if volume_1h is None:
        return "unknown"
    if volume_1h < 100:
        return "thin"
    if (competitors is not None
            and competitors > calibration.competitors_at_touch + 1e-9):
        return "busy"
    return "liquid"


def fill_observations(rows: Sequence, now: int,
                      calibration: engine.Calibration
                      = engine.DEFAULT_CALIBRATION) -> List[FillObservation]:
    """Every leg with a prediction becomes an observation, finished or not."""
    out: List[FillObservation] = []
    for row in rows:
        keys = row.keys()

        def get(name):
            return row[name] if name in keys else None

        sigma = _finite(get("predicted_fill_log_sigma"))
        tier = liquidity_tier(get("predicted_volume_1h"),
                              get("predicted_competitors"), calibration)
        outcome = get("outcome") or "open"
        placed, bought = get("offer_placed_at"), get("buy_filled_at")
        sold, cancelled_at = get("sold_at"), get("cancelled_at")
        cancelled = outcome == "cancelled"
        buy_p50 = _finite(get("predicted_buy_seconds"))
        sell_p50 = _finite(get("predicted_sell_seconds"))
        trip_p50 = _finite(get("predicted_round_trip_p50_seconds"))
        if trip_p50 is None and buy_p50 and sell_p50:
            trip_p50 = buy_p50 + sell_p50

        def add(leg, predicted, start, end, censored):
            if not predicted or predicted <= 0 or not start or not end:
                return
            if end <= start:
                return
            out.append(FillObservation(leg, predicted, sigma,
                                       float(end - start), censored,
                                       cancelled and censored, tier))

        if outcome == "placed" or (cancelled and not bought):
            add("buy", buy_p50, placed, cancelled_at if cancelled else now,
                True)
        elif bought:
            add("buy", buy_p50, placed, bought, False)
        if bought:
            if sold:
                add("sell", sell_p50, bought, sold, False)
            else:
                add("sell", sell_p50, bought,
                    cancelled_at if cancelled else now, True)
        if sold:
            add("round_trip", trip_p50, placed, sold, False)
        else:
            add("round_trip", trip_p50, placed,
                cancelled_at if cancelled else now, True)
    return out


def kaplan_meier_median(values: Sequence[Tuple[float, bool]]
                        ) -> Optional[float]:
    """Median of (value, censored) pairs; None when the censoring hides it.

    Censored values are lower bounds: a pulled offer would have taken longer.
    Dropping them biases the median down; treating them as completions does
    too. Kaplan-Meier uses them exactly as far as they are informative.
    """
    ordered = sorted(values, key=lambda pair: (pair[0], pair[1]))
    at_risk = len(ordered)
    survival = 1.0
    index = 0
    while index < len(ordered):
        value = ordered[index][0]
        events = censored = 0
        while index < len(ordered) and ordered[index][0] == value:
            if ordered[index][1]:
                censored += 1
            else:
                events += 1
            index += 1
        if events:
            survival *= 1.0 - events / at_risk
            if survival <= 0.5:
                return value
        at_risk -= events + censored
    return None


def kaplan_meier_survival(values: Sequence[Tuple[float, bool]],
                          threshold: float) -> Optional[float]:
    """P(value > threshold) from (value, censored) pairs.

    Simply dropping the censored waits that stopped short of the threshold is
    itself a bias: the offers a player gave up on are, by selection, the slow
    ones. Kaplan-Meier keeps their information up to the moment they stopped.
    """
    if not values:
        return None
    ordered = sorted(values, key=lambda pair: (pair[0], pair[1]))
    at_risk = len(ordered)
    survival = 1.0
    index = 0
    while index < len(ordered) and ordered[index][0] <= threshold:
        value = ordered[index][0]
        events = censored = 0
        while index < len(ordered) and ordered[index][0] == value:
            if ordered[index][1]:
                censored += 1
            else:
                events += 1
            index += 1
        if events:
            survival *= 1.0 - events / at_risk
        at_risk -= events + censored
    return survival


def _log_survival(z: float) -> float:
    return math.log(max(0.5 * math.erfc(z / math.sqrt(2.0)), 1e-300))


def fit_censored_lognormal(residuals: Sequence[Tuple[float, bool]]
                           ) -> Optional[Tuple[float, float]]:
    """Censored (Tobit) maximum likelihood for log-residuals ~ N(bias, width).

    A residual is log((realised - overhead) / (predicted median - overhead)).
    If the model is calibrated, bias is 0 and width equals the predicted
    fill_log_sigma. A grid, not an optimiser: a few hundred rows at most, and
    a grid cannot silently diverge on a censored likelihood.
    """
    completed = [value for value, censored in residuals if not censored]
    if (len(residuals) < MIN_FIT_OBSERVATIONS
            or len(completed) < MIN_FIT_COMPLETED):
        return None
    best, best_ll = None, float("-inf")
    for bias_step in range(-60, 61):
        bias = bias_step * 0.05
        for width_step in range(1, 61):
            width = width_step * 0.05
            ll = 0.0
            for value, censored in residuals:
                z = (value - bias) / width
                ll += (_log_survival(z) if censored
                       else -0.5 * z * z - math.log(width))
            if ll > best_ll:
                best_ll, best = ll, (bias, width)
    return best


def backtest_summary(observations: Sequence[FillObservation],
                     calibration: engine.Calibration
                     = engine.DEFAULT_CALIBRATION) -> List[dict]:
    """One row per leg and tier (plus 'all'), censoring-aware throughout."""
    groups: Dict[Tuple[str, str], List[FillObservation]] = {}
    for obs in observations:
        groups.setdefault((obs.leg, "all"), []).append(obs)
        groups.setdefault((obs.leg, obs.tier), []).append(obs)
    z80 = engine.normal_quantile(0.80)
    z90 = engine.normal_quantile(0.90)
    out = []
    for leg in LEGS:
        for tier in ("all", "thin", "liquid", "busy", "unknown"):
            group = groups.get((leg, tier))
            if not group:
                continue
            overhead = calibration.min_leg_seconds * (
                engine.LEGS_PER_ROUND_TRIP if leg == "round_trip" else 1)
            ratios = [(obs.seconds / obs.predicted_p50, obs.censored)
                      for obs in group]
            km_ratio = kaplan_meier_median(ratios)
            residuals = []       # log error, for the fit
            standardised = []    # log error in units of the predicted width
            for obs in group:
                if obs.sigma is None:
                    continue
                work = max(1.0, obs.predicted_p50 - overhead)
                error = math.log(max(1.0, obs.seconds - overhead) / work)
                residuals.append((error, obs.censored))
                standardised.append((error / max(obs.sigma, 1e-6),
                                     obs.censored))
            fit = fit_censored_lognormal(residuals)
            completed = [obs for obs in group if not obs.censored]
            banded = [obs.sigma for obs in group if obs.sigma is not None]
            out.append({
                "leg": leg, "tier": tier, "n": len(group),
                "completed": len(completed),
                "censored": len(group) - len(completed),
                "never_filled": sum(1 for obs in group if obs.cancelled),
                "median_predicted": _median([o.predicted_p50 for o in group]),
                "median_realised_completed": _median(
                    [o.seconds for o in completed]),
                "km_median_realised_over_predicted": km_ratio,
                "predicted_over_realised": (1.0 / km_ratio
                                            if km_ratio else None),
                # Share of trips slower than their own predicted P80 / P90.
                "p80_exceedance": kaplan_meier_survival(standardised, z80),
                "p90_exceedance": kaplan_meier_survival(standardised, z90),
                "banded": len(standardised),
                "predicted_sigma": _median(banded),
                "fitted_log_bias": fit[0] if fit else None,
                "fitted_sigma": fit[1] if fit else None,
            })
    return out


# ---------------------------------------------------------------------------
# Derived quantities
# ---------------------------------------------------------------------------

def realised_profit(row) -> Optional[int]:
    """Net gp for a closed flip (after tax); None while still open."""
    if row["sell_price"] is None:
        return None
    exempt = _row_is_exempt(row)
    bond = (row["item_id"] == exemptions.BOND_ID
            or str(row["item_name"]).strip().lower() == "old school bond")
    margin = engine.net_margin(row["buy_price"], row["sell_price"], exempt,
                               bond)
    return margin * row["quantity"]


def predicted_profit(row) -> Optional[float]:
    """Risk-adjusted prediction when available, legacy gross fallback else.

    Comparing realised profit with margin × quantity silently evaluates a
    different, best-case model and makes every fill/risk discount look like an
    error. v2 rows store the actual prediction the decision used.
    """
    if "predicted_expected_gp" in row.keys() and row["predicted_expected_gp"] is not None:
        return float(row["predicted_expected_gp"])
    if row["predicted_margin"] is None:
        return None
    return float(row["predicted_margin"] * row["quantity"])


def _row_is_exempt(row) -> bool:
    """Exemption as recorded at entry, falling back to the id-only list.

    Recorded rather than re-derived: the exempt list is maintained by hand and
    may change between the flip and the analysis, and what mattered for the
    profit is the rule in force when it was sold.
    """
    keys = row.keys()
    if "tax_exempt" in keys and row["tax_exempt"] is not None:
        return bool(row["tax_exempt"])
    return exemptions.is_exempt_item(row["item_id"], row["item_name"])


def flip_seconds(row) -> Optional[float]:
    """Total slot time: from the offer going in to the sell filling."""
    start = row["offer_placed_at"] or row["bought_at"]
    end = row["sold_at"]
    if not start or not end or end <= start:
        return None
    return float(end - start)


def _sell_seconds(row) -> Optional[float]:
    start = row["buy_filled_at"] or row["bought_at"]
    end = row["sold_at"]
    if not start or not end or end <= start:
        return None
    return float(end - start)


def _realised_rate(closed: Sequence) -> Optional[float]:
    """Actual gp per slot-hour, the metric the ranking claims to maximise."""
    total_profit = 0
    total_hours = 0.0
    for row in closed:
        seconds = flip_seconds(row)
        profit = realised_profit(row)
        if seconds and profit is not None:
            total_profit += profit
            total_hours += seconds / engine.SECONDS_PER_HOUR
    if total_hours <= 0:
        return None
    return total_profit / total_hours


def _sharpe(closed: Sequence) -> Optional[float]:
    """Per-flip Sharpe, annualised by the mean flip duration.

    Wants ~30 closed flips before it means anything, and the report's power
    analysis puts detection of a real edge at four figures. Reported early so
    the number of flips behind it stays visible.
    """
    returns = []
    hours = []
    for row in closed:
        profit = realised_profit(row)
        seconds = flip_seconds(row)
        capital = row["buy_price"] * row["quantity"]
        if profit is None or not seconds or capital <= 0:
            continue
        returns.append(profit / capital)
        hours.append(seconds / engine.SECONDS_PER_HOUR)
    if len(returns) < 2:
        return None
    average = sum(returns) / len(returns)
    variance = sum((r - average) ** 2 for r in returns) / (len(returns) - 1)
    if variance <= 0:
        return None
    mean_hours = sum(hours) / len(hours)
    if mean_hours <= 0:
        return None
    periods_per_year = (365 * 24) / mean_hours
    return (average / math.sqrt(variance)) * math.sqrt(periods_per_year)


def _median(values) -> Optional[float]:
    values = [v for v in values if v is not None]
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _mean(values) -> Optional[float]:
    values = [v for v in values if v is not None]
    if not values:
        return None
    return sum(values) / len(values)


# -- terminal interface -------------------------------------------------------

def parse_args(argv):
    p = argparse.ArgumentParser(description="Log actual flips against predictions")
    p.add_argument("--db", type=Path, default=DEFAULT_DB,
                   help="database file (default journal.db next to this script)")
    sub = p.add_subparsers(dest="command", required=True)

    o = sub.add_parser("open", help="record a filled buy offer")
    o.add_argument("--name", required=True, help="item name")
    o.add_argument("--qty", required=True, type=int, help="quantity bought")
    o.add_argument("--buy", required=True, type=int, help="price paid per item")
    o.add_argument("--id", type=int, default=None, help="item id")
    o.add_argument("--predicted", type=int, default=None,
                   help="net margin the tool predicted when you bought")
    o.add_argument("--placed-at", type=int, default=None,
                   help="unix time the buy offer went in, if not now — the "
                        "gap to the fill is the buy-leg fill time")
    o.add_argument("--tax-exempt", action=argparse.BooleanOptionalAction,
                   default=None,
                   help="override whether the item pays GE tax; by default "
                        "it is looked up by --id and --name in "
                        "tax_exempt.json")

    pl = sub.add_parser("place", help="record a buy offer as it goes in, "
                                      "before anything has filled")
    pl.add_argument("--name", required=True, help="item name")
    pl.add_argument("--qty", required=True, type=int, help="offer quantity")
    pl.add_argument("--buy", required=True, type=int, help="offer price per item")
    pl.add_argument("--id", type=int, default=None, help="item id")
    pl.add_argument("--placed-at", type=int, default=None,
                    help="unix time the offer went in, if not now")

    bt = sub.add_parser("bought", help="the placed buy offer has filled")
    bt.add_argument("flip_id", type=int)
    bt.add_argument("--qty", type=int, default=None,
                    help="units actually bought, if you cut the offer short")

    c = sub.add_parser("close", help="record the matching filled sell offer")
    c.add_argument("flip_id", type=int)
    c.add_argument("--sell", required=True, type=int, help="sell price per item")

    x = sub.add_parser("cancel", help="record an offer that never filled")
    x.add_argument("flip_id", type=int)
    x.add_argument("--reason", default="", help="why it was pulled")

    sub.add_parser("list", help="show all flips")
    sub.add_parser("stats", help="realised totals and prediction accuracy")
    sub.add_parser("calibration",
                   help="capture by rank bucket, censored fill-time backtest "
                        "and factor diagnostics")
    return p.parse_args(argv)


def cmd_list(journal):
    rows = journal.rows()
    if not rows:
        print("Journal is empty.")
        return
    print("{:>4} {:<24} {:>8} {:>10} {:>10} {:>7} {:>12} {:>8}  {}".format(
        "ID", "ITEM", "QTY", "BUY", "SELL", "PRED", "REALISED", "TOOK",
        "STATUS"))
    for r in rows:
        profit = realised_profit(r)
        seconds = flip_seconds(r)
        print("{:>4} {:<24.24} {:>8,} {:>10,} {:>10} {:>7} {:>12} {:>8}  {}".format(
            r["id"], r["item_name"], r["quantity"], r["buy_price"],
            "{:,}".format(r["sell_price"]) if r["sell_price"] is not None else "-",
            "{:,}".format(r["predicted_margin"]) if r["predicted_margin"] is not None else "-",
            "{:,}".format(profit) if profit is not None else "-",
            engine.format_duration(seconds) if seconds else "-",
            r["outcome"] or "open"))


def cmd_stats(journal):
    s = journal.stats()
    print("Closed flips:      {:,}".format(s["flips_closed"]))
    print("Cancelled:         {:,}  ({:.0%} of offers ever filled)".format(
        s["flips_cancelled"], s["fill_rate"]))
    print("Realised profit:   {:,} gp".format(s["realised_profit"]))
    if s["median_flip_seconds"]:
        print("Median flip took:  {}  (the old ranking assumed 4h for every "
              "flip)".format(engine.format_duration(s["median_flip_seconds"])))
    if s["realised_gp_per_slot_hour"] is not None:
        print("Realised gp/slot/h: {:,.0f}".format(s["realised_gp_per_slot_hour"]))
    if s["sharpe"] is not None:
        print("Sharpe (annualised): {:.2f}  [{} flips — treat below ~30 as "
              "noise]".format(s["sharpe"], s["flips_closed"]))
    if s["flips_with_prediction"]:
        print("Of which predicted ({} flips):".format(s["flips_with_prediction"]))
        print("  predicted: {:,} gp | realised: {:,} gp | capture: {:.0%}".format(
            s["predicted_profit"], s["realised_on_predicted"], s["capture"]))


def cmd_calibration(journal):
    buckets = journal.capture_by_decile()
    if not buckets:
        print("No closed flips with predictions yet.")
    else:
        print("Capture by predicted rank (bucket 1 = highest predicted):")
        print("  {:>6} {:>6} {:>14} {:>14} {:>9}".format(
            "BUCKET", "FLIPS", "PREDICTED", "REALISED", "CAPTURE"))
        for b in buckets:
            print("  {:>6} {:>6} {:>14,} {:>14,} {:>8.0%}".format(
                b["bucket"], b["flips"], b["predicted"], b["realised"],
                b["capture"]))
        print("  Capture falling as you go UP the ranking is the optimizer's "
              "curse showing through the shrinkage.")

    print_backtest(journal.fill_time_backtest())

    factors = journal.factor_errors()
    if factors:
        print("\nFactor values, flips that beat vs missed their prediction:")
        print("  {:<20} {:>10} {:>10}".format("FACTOR", "BEAT", "MISSED"))
        for f in factors:
            print("  {:<20} {:>10} {:>10}".format(
                f["factor"],
                "{:.3f}".format(f["when_beat"]) if f["when_beat"] is not None else "-",
                "{:.3f}".format(f["when_missed"]) if f["when_missed"] is not None else "-"))
        print("  A factor that differs sharply between the columns is the one "
              "carrying the error; adjust it in engine.Calibration.")


def print_backtest(summary: List[dict]) -> None:
    """The fill-time backtest, censored offers included."""
    if not summary:
        print("\nFill-time backtest: no offers with a recorded prediction and "
              "timestamps yet. Log offers with `place` when they go in, "
              "`bought` when they fill and `cancel` when you pull them — an "
              "offer that never fills is the observation this needs most.")
        return

    def duration(value):
        return engine.format_duration(value) if value else "-"

    def share(value):
        return "{:.0%}".format(value) if value is not None else "-"

    print("\nFill time, predicted vs realised (censored = cancelled or still "
          "waiting; they count as 'at least this long'):")
    print("  {:<10} {:<7} {:>4} {:>5} {:>5} {:>6} {:>8} {:>8} {:>9} "
          "{:>7} {:>7} {:>11}".format(
              "LEG", "TIER", "N", "DONE", "CENS", "PULLED", "PRED P50",
              "REAL P50", "PRED/REAL", ">P80", ">P90", "FIT b/sigma"))
    for row in summary:
        real = (row["km_median_realised_over_predicted"]
                * row["median_predicted"]
                if row["km_median_realised_over_predicted"] else None)
        fit = ("{:+.2f}/{:.2f}".format(row["fitted_log_bias"],
                                       row["fitted_sigma"])
               if row["fitted_sigma"] is not None else "n<{}".format(
                   MIN_FIT_OBSERVATIONS))
        print("  {:<10} {:<7} {:>4} {:>5} {:>5} {:>6} {:>8} {:>8} {:>9} "
              "{:>7} {:>7} {:>11}".format(
                  row["leg"], row["tier"], row["n"], row["completed"],
                  row["censored"], row["never_filled"],
                  duration(row["median_predicted"]),
                  duration(real) if real else ">cens",
                  "{:.2f}x".format(row["predicted_over_realised"])
                  if row["predicted_over_realised"] else "-",
                  share(row["p80_exceedance"]), share(row["p90_exceedance"]),
                  fit))
    print("  REAL P50 is the Kaplan-Meier median, so pulled offers push it up "
          "instead of vanishing. A calibrated model shows PRED/REAL near 1, "
          ">P80 near 20% and >P90 near 10%. FIT is the censored fit of the "
          "log error: b > 0 means slower than predicted; compare sigma with "
          "Calibration.fill_rate_log_sigma, volume_forecast_log_sigma and "
          "unverified_fill_log_sigma before changing them.")


def main(argv=None):
    opts = parse_args(argv if argv is not None else sys.argv[1:])
    journal = Journal(opts.db)
    try:
        if opts.command == "open":
            # Record the rule in force at entry, so a later edit of the
            # hand-maintained list cannot rewrite this flip's history.
            tax_exempt = (opts.tax_exempt if opts.tax_exempt is not None
                          else exemptions.is_exempt_item(opts.id, opts.name))
            flip_id = journal.open_flip(
                opts.name, opts.qty, opts.buy, item_id=opts.id,
                predicted_margin=opts.predicted,
                offer_placed_at=opts.placed_at,
                tax_exempt=tax_exempt)
            print("Opened flip {}: {} x{:,} @ {:,} gp".format(
                flip_id, opts.name, opts.qty, opts.buy))
        elif opts.command == "place":
            flip_id = journal.place_offer(
                opts.name, opts.qty, opts.buy, placed_at=opts.placed_at,
                item_id=opts.id,
                tax_exempt=exemptions.is_exempt_item(opts.id, opts.name))
            print("Placed offer {}: {} x{:,} @ {:,} gp. Record `bought` when "
                  "it fills or `cancel` if you pull it.".format(
                      flip_id, opts.name, opts.qty, opts.buy))
        elif opts.command == "bought":
            journal.mark_bought(opts.flip_id, quantity=opts.qty)
            print("Flip {}: buy filled.".format(opts.flip_id))
        elif opts.command == "close":
            journal.close_flip(opts.flip_id, opts.sell)
            profit = realised_profit(journal._row(opts.flip_id))
            print("Closed flip {}: realised {:,} gp after tax".format(
                opts.flip_id, profit))
        elif opts.command == "cancel":
            journal.cancel_flip(opts.flip_id, opts.reason)
            print("Flip {} recorded as never filled. Cancellations are what "
                  "keep the fill-time estimates honest.".format(opts.flip_id))
        elif opts.command == "list":
            cmd_list(journal)
        elif opts.command == "stats":
            cmd_stats(journal)
        elif opts.command == "calibration":
            cmd_calibration(journal)
    except (ValueError, sqlite3.Error) as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1
    finally:
        journal.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
