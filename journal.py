"""SQLite log of actual flips, to compare predicted margins with reality.

Library use:  Journal(path).open_flip(...) / close_flip(...) / rows() / stats()
Terminal use: python3 journal.py open --name "Steel bar" --qty 1000 --buy 571 \
                  [--id 2353] [--predicted 16]
              python3 journal.py close 1 --sell 598
              python3 journal.py list
              python3 journal.py stats
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

import engine

DEFAULT_DB = Path(__file__).parent / "journal.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS flips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER,                 -- optional; needed only for tax exemption
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    buy_price INTEGER NOT NULL CHECK (buy_price > 0),
    predicted_margin INTEGER,        -- engine margin at the moment of buying
    sell_price INTEGER,              -- NULL while the position is open
    bought_at INTEGER NOT NULL,      -- unix seconds
    sold_at INTEGER
)
"""


class Journal:
    def __init__(self, db_path=DEFAULT_DB):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def open_flip(self, item_name: str, quantity: int, buy_price: int,
                  item_id: Optional[int] = None,
                  predicted_margin: Optional[int] = None,
                  bought_at: Optional[int] = None) -> int:
        if quantity <= 0 or buy_price <= 0:
            raise ValueError("quantity and buy_price must be positive")
        cur = self.conn.execute(
            "INSERT INTO flips (item_id, item_name, quantity, buy_price,"
            " predicted_margin, bought_at) VALUES (?, ?, ?, ?, ?, ?)",
            (item_id, item_name, quantity, buy_price, predicted_margin,
             bought_at if bought_at is not None else int(time.time())))
        self.conn.commit()
        return cur.lastrowid

    def close_flip(self, flip_id: int, sell_price: int,
                   sold_at: Optional[int] = None) -> None:
        if sell_price <= 0:
            raise ValueError("sell_price must be positive")
        row = self.conn.execute(
            "SELECT sell_price FROM flips WHERE id = ?", (flip_id,)).fetchone()
        if row is None:
            raise ValueError("no flip with id {}".format(flip_id))
        if row["sell_price"] is not None:
            raise ValueError("flip {} is already closed".format(flip_id))
        self.conn.execute(
            "UPDATE flips SET sell_price = ?, sold_at = ? WHERE id = ?",
            (sell_price, sold_at if sold_at is not None else int(time.time()),
             flip_id))
        self.conn.commit()

    def rows(self):
        return self.conn.execute("SELECT * FROM flips ORDER BY id").fetchall()

    def stats(self) -> dict:
        """Aggregate realised results and predicted-vs-realised comparison."""
        closed = [r for r in self.rows() if r["sell_price"] is not None]
        predicted = [r for r in closed if r["predicted_margin"] is not None]
        return {
            "flips_closed": len(closed),
            "realised_profit": sum(realised_profit(r) for r in closed),
            "flips_with_prediction": len(predicted),
            "predicted_profit": sum(
                r["predicted_margin"] * r["quantity"] for r in predicted),
            "realised_on_predicted": sum(
                realised_profit(r) for r in predicted),
        }


def realised_profit(row) -> Optional[int]:
    """Net gp for a closed flip (after tax); None while still open."""
    if row["sell_price"] is None:
        return None
    tax_exempt = row["item_id"] in engine.TAX_EXEMPT_ITEM_IDS
    margin = engine.net_margin(row["buy_price"], row["sell_price"], tax_exempt)
    return margin * row["quantity"]


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
    o.add_argument("--id", type=int, default=None,
                   help="item id (only matters for tax-exempt items like bonds)")
    o.add_argument("--predicted", type=int, default=None,
                   help="net margin the tool predicted when you bought")

    c = sub.add_parser("close", help="record the matching filled sell offer")
    c.add_argument("flip_id", type=int)
    c.add_argument("--sell", required=True, type=int, help="sell price per item")

    sub.add_parser("list", help="show all flips")
    sub.add_parser("stats", help="realised totals and prediction accuracy")
    return p.parse_args(argv)


def cmd_list(journal):
    rows = journal.rows()
    if not rows:
        print("Journal is empty.")
        return
    print("{:>4} {:<24} {:>8} {:>10} {:>10} {:>7} {:>12}  {}".format(
        "ID", "ITEM", "QTY", "BUY", "SELL", "PRED", "REALISED", "STATUS"))
    for r in rows:
        profit = realised_profit(r)
        print("{:>4} {:<24.24} {:>8,} {:>10,} {:>10} {:>7} {:>12}  {}".format(
            r["id"], r["item_name"], r["quantity"], r["buy_price"],
            "{:,}".format(r["sell_price"]) if r["sell_price"] is not None else "-",
            "{:,}".format(r["predicted_margin"]) if r["predicted_margin"] is not None else "-",
            "{:,}".format(profit) if profit is not None else "-",
            "closed" if profit is not None else "OPEN"))


def cmd_stats(journal):
    s = journal.stats()
    print("Closed flips:      {:,}".format(s["flips_closed"]))
    print("Realised profit:   {:,} gp".format(s["realised_profit"]))
    if s["flips_with_prediction"]:
        print("Of which predicted ({} flips):".format(s["flips_with_prediction"]))
        print("  predicted: {:,} gp | realised: {:,} gp | capture: {:.0%}".format(
            s["predicted_profit"], s["realised_on_predicted"],
            s["realised_on_predicted"] / s["predicted_profit"]
            if s["predicted_profit"] else 0.0))


def main(argv=None):
    opts = parse_args(argv if argv is not None else sys.argv[1:])
    journal = Journal(opts.db)
    try:
        if opts.command == "open":
            flip_id = journal.open_flip(opts.name, opts.qty, opts.buy,
                                        item_id=opts.id,
                                        predicted_margin=opts.predicted)
            print("Opened flip {}: {} x{:,} @ {:,} gp".format(
                flip_id, opts.name, opts.qty, opts.buy))
        elif opts.command == "close":
            journal.close_flip(opts.flip_id, opts.sell)
            profit = realised_profit(self_row(journal, opts.flip_id))
            print("Closed flip {}: realised {:,} gp after tax".format(
                opts.flip_id, profit))
        elif opts.command == "list":
            cmd_list(journal)
        elif opts.command == "stats":
            cmd_stats(journal)
    except ValueError as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1
    finally:
        journal.close()
    return 0


def self_row(journal, flip_id):
    for row in journal.rows():
        if row["id"] == flip_id:
            return row
    raise ValueError("no flip with id {}".format(flip_id))


if __name__ == "__main__":
    sys.exit(main())
