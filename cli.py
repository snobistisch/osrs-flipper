"""Ranked flips as a plain terminal table.

Usage: python3 cli.py [--capital N] [--slots N] [--max-age S] [--min-vol N]
                      [--min-roi F] [--min-depth N] [--members]
"""
from __future__ import annotations

import argparse
import sys
import time

import api
import engine
import filters


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Rank GE flips by expected gp per offer slot per hour")
    p.add_argument("--capital", type=engine.parse_gp, default=1_000_000,
                   help="gp available across all slots, e.g. 250k or 1.5m")
    p.add_argument("--slots", type=int, default=engine.F2P_SLOTS,
                   help="concurrent GE offers: 3 free-to-play, 8 members")
    p.add_argument("--max-age", type=int, default=300,
                   help="max seconds since the OLDER of the two quotes")
    p.add_argument("--min-vol", type=int, default=120,
                   help="min units traded on the thin side per 1h")
    p.add_argument("--min-roi", type=float, default=0.01,
                   help="min net ROI per flip, e.g. 0.01 = 1%%")
    p.add_argument("--min-depth", type=int, default=1,
                   help="min gp of undercut room; 0 shows flips you cannot "
                        "queue-jump, like one-tick rune spreads")
    p.add_argument("--members", action="store_true",
                   help="include members-only items")
    p.add_argument("--top", type=int, default=20, help="rows to show")
    return p.parse_args(argv)


def config_from(opts) -> filters.FilterConfig:
    return filters.FilterConfig(
        capital=opts.capital, slots=opts.slots, include_members=opts.members,
        max_quote_age=opts.max_age, min_thin_volume_1h=opts.min_vol,
        min_roi=opts.min_roi, min_undercut_depth=opts.min_depth)


def print_table(rows, funnel, opts):
    per_slot = engine.capital_per_slot(opts.capital, opts.slots)
    print("Budget {} gp across {} slots = {} gp per flip | quote age <= {}s | "
          "vol >= {}/1h | ROI >= {:.1%} | undercut room >= {} gp".format(
              engine.format_gp(opts.capital), opts.slots,
              engine.format_gp(per_slot), opts.max_age, opts.min_vol,
              opts.min_roi, opts.min_depth))
    print("Funnel:  " + "  ->  ".join(
        "{} {}".format(v, k) for k, v in funnel.items() if v))
    print()
    if not rows:
        print("No flips pass the current filters. Lower --min-roi, --min-vol, "
              "or --min-depth.")
        return

    header = "{:<26} {:>9} {:>9} {:>7} {:>6} {:>6} {:>7} {:>7} {:>11} {:>11}"
    print(header.format("ITEM", "BUY", "SELL", "MARGIN", "ROI", "ROOM",
                        "QTY/4H", "TIED UP", "QUOTED/4H", "EV/SLOT/H"))
    for r in rows[:opts.top]:
        print("{:<26.26} {:>9,} {:>9,} {:>7,} {:>5.1f}% {:>6,} {:>7,} {:>7} "
              "{:>11,} {:>11,.0f}".format(
                  r.name, r.buy, r.sell, r.margin, r.roi * 100,
                  r.undercut_depth, r.qty_per_window,
                  engine.format_gp(r.capital_needed), r.gross_profit,
                  r.gp_per_slot_hour))
        for note in r.warnings:
            print("{:<26} {}".format("", "· " + note))
    print()
    print("ROOM = gp of price improvement you can afford per side and still "
          "profit. The GE fills by price first, then by offer age, so with no "
          "room you wait behind offers that may be days old.")
    print("EV/SLOT/H = expected gp per offer slot per hour: the quoted profit "
          "discounted for queue position, price drift and quote staleness. "
          "QUOTED/4H is the undiscounted best case.")


def main(argv=None):
    opts = parse_args(argv if argv is not None else sys.argv[1:])
    client = api.WikiClient()
    try:
        items = client.mapping()
        quotes = client.latest()
        activity_5m = client.interval("5m")
        activity_1h = client.interval("1h")
    except api.ApiError as exc:
        print("API error: {}".format(exc), file=sys.stderr)
        return 1
    rows, funnel = filters.rank_flips(items, quotes, activity_5m, activity_1h,
                                      config_from(opts), now=time.time())
    print_table(rows, funnel, opts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
