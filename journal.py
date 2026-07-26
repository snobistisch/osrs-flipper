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

Library use:  Journal(path).open_flip(...) / close_flip(...) / rows() / stats()
Terminal use: python3 journal.py open --name "Steel bar" --qty 1000 --buy 571 \
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
from pathlib import Path
from typing import Dict, List, Optional, Sequence

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
)


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
                  offer_placed_at: Optional[int] = None) -> int:
        """Record a filled buy offer.

        Pass `row` (a filters.FlipRow) to capture the whole prediction rather
        than just its headline margin. Everything else stays optional so the
        terminal interface remains a three-flag command.
        """
        if quantity <= 0 or buy_price <= 0:
            raise ValueError("quantity and buy_price must be positive")
        now = int(time.time())
        bought_at = bought_at if bought_at is not None else now

        fields: Dict[str, object] = {
            "item_id": item_id,
            "item_name": item_name,
            "quantity": quantity,
            "buy_price": buy_price,
            "predicted_margin": predicted_margin,
            "bought_at": bought_at,
            "outcome": "open",
            "tax_exempt": int(bool(tax_exempt)) if tax_exempt is not None else None,
            "snapshot_at": snapshot_at,
            "offer_placed_at": offer_placed_at,
            "buy_filled_at": bought_at,
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
                "tax_exempt": int(bool(getattr(row, "tax_exempt", False))),
                "factors_json": json.dumps(getattr(row, "factors", {}) or {}),
            })
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

    def close_flip(self, flip_id: int, sell_price: int,
                   sold_at: Optional[int] = None) -> None:
        if sell_price <= 0:
            raise ValueError("sell_price must be positive")
        row = self._row(flip_id)
        if row["sell_price"] is not None:
            raise ValueError("flip {} is already closed".format(flip_id))
        if row["outcome"] == "cancelled":
            raise ValueError("flip {} was cancelled".format(flip_id))
        self.conn.execute(
            "UPDATE flips SET sell_price = ?, sold_at = ?, outcome = 'filled'"
            " WHERE id = ?",
            (sell_price, sold_at if sold_at is not None else int(time.time()),
             flip_id))
        self.conn.commit()

    def cancel_flip(self, flip_id: int, reason: str = "",
                    cancelled_at: Optional[int] = None) -> None:
        """Record an offer that never filled.

        These are the observations that keep the fill-time estimates honest.
        A journal of completed flips only measures the flips that completed.
        """
        row = self._row(flip_id)
        if row["sell_price"] is not None:
            raise ValueError("flip {} already sold".format(flip_id))
        self.conn.execute(
            "UPDATE flips SET outcome = 'cancelled', cancelled_at = ?,"
            " cancel_reason = ?, cancel_count = COALESCE(cancel_count, 0) + 1"
            " WHERE id = ?",
            (cancelled_at if cancelled_at is not None else int(time.time()),
             reason, flip_id))
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
        predicted = [r for r in closed if r["predicted_margin"] is not None]
        durations = [d for d in (flip_seconds(r) for r in closed) if d]
        predicted_profit = sum(
            r["predicted_margin"] * r["quantity"] for r in predicted)
        realised_on_predicted = sum(realised_profit(r) for r in predicted)
        return {
            "flips_closed": len(closed),
            "flips_cancelled": len(cancelled),
            "fill_rate": (len(closed) / (len(closed) + len(cancelled))
                          if closed or cancelled else 0.0),
            "realised_profit": sum(realised_profit(r) for r in closed),
            "flips_with_prediction": len(predicted),
            "predicted_profit": predicted_profit,
            "realised_on_predicted": realised_on_predicted,
            "capture": (realised_on_predicted / predicted_profit
                        if predicted_profit else 0.0),
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
                and r["predicted_margin"] is not None
                and r["predicted_margin"] * r["quantity"] > 0]
        if not rows:
            return []
        rows.sort(key=lambda r: r["predicted_margin"] * r["quantity"],
                  reverse=True)
        size = max(1, len(rows) // deciles)
        out = []
        for index in range(0, len(rows), size):
            group = rows[index:index + size]
            promised = sum(r["predicted_margin"] * r["quantity"] for r in group)
            got = sum(realised_profit(r) for r in group)
            out.append({
                "bucket": len(out) + 1,
                "flips": len(group),
                "predicted": promised,
                "realised": got,
                "capture": got / promised if promised else 0.0,
            })
        return out

    def fill_time_calibration(self) -> Optional[dict]:
        """Predicted versus actual time from buy fill to sell fill.

        The old ranking assumed four hours for every flip. This is the number
        that says by how much.
        """
        pairs = []
        for row in self.rows():
            predicted = row["predicted_sell_seconds"]
            actual = _sell_seconds(row)
            if predicted and actual and predicted > 0:
                pairs.append((predicted, actual))
        if not pairs:
            return None
        ratios = [actual / predicted for predicted, actual in pairs]
        return {
            "n": len(pairs),
            "median_ratio": _median(ratios),
            "median_predicted": _median([p for p, _ in pairs]),
            "median_actual": _median([a for _, a in pairs]),
        }

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
            predicted = (row["predicted_margin"] or 0) * row["quantity"]
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
# Derived quantities
# ---------------------------------------------------------------------------

def realised_profit(row) -> Optional[int]:
    """Net gp for a closed flip (after tax); None while still open."""
    if row["sell_price"] is None:
        return None
    exempt = _row_is_exempt(row)
    margin = engine.net_margin(row["buy_price"], row["sell_price"], exempt)
    return margin * row["quantity"]


def _row_is_exempt(row) -> bool:
    """Exemption as recorded at entry, falling back to the id-only list.

    Recorded rather than re-derived: the exempt list is maintained by hand and
    may change between the flip and the analysis, and what mattered for the
    profit is the rule in force when it was sold.
    """
    keys = row.keys()
    if "tax_exempt" in keys and row["tax_exempt"] is not None:
        return bool(row["tax_exempt"])
    return row["item_id"] in exemptions.resolve().ids


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
    o.add_argument("--tax-exempt", action="store_true",
                   help="item pays no GE tax (see tax_exempt.json)")

    c = sub.add_parser("close", help="record the matching filled sell offer")
    c.add_argument("flip_id", type=int)
    c.add_argument("--sell", required=True, type=int, help="sell price per item")

    x = sub.add_parser("cancel", help="record an offer that never filled")
    x.add_argument("flip_id", type=int)
    x.add_argument("--reason", default="", help="why it was pulled")

    sub.add_parser("list", help="show all flips")
    sub.add_parser("stats", help="realised totals and prediction accuracy")
    sub.add_parser("calibration",
                   help="capture by rank bucket, fill-time and factor diagnostics")
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

    fill = journal.fill_time_calibration()
    if fill:
        print("\nSell-leg fill time, predicted vs actual ({} flips):".format(
            fill["n"]))
        print("  predicted {}  actual {}  ratio {:.2f}x".format(
            engine.format_duration(fill["median_predicted"]),
            engine.format_duration(fill["median_actual"]),
            fill["median_ratio"]))

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


def main(argv=None):
    opts = parse_args(argv if argv is not None else sys.argv[1:])
    journal = Journal(opts.db)
    try:
        if opts.command == "open":
            flip_id = journal.open_flip(
                opts.name, opts.qty, opts.buy, item_id=opts.id,
                predicted_margin=opts.predicted,
                offer_placed_at=opts.placed_at,
                tax_exempt=opts.tax_exempt)
            print("Opened flip {}: {} x{:,} @ {:,} gp".format(
                flip_id, opts.name, opts.qty, opts.buy))
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
    except ValueError as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1
    finally:
        journal.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
