"""Ranked flips as a plain terminal table.

Usage: python3 cli.py [--capital N] [--max-age S] [--min-vol N] [--min-roi F]
"""
from __future__ import annotations

import argparse
import sys
import time

import api
import filters


def parse_args(argv):
    p = argparse.ArgumentParser(description="Rank F2P GE flips from live wiki prices")
    p.add_argument("--capital", type=int, default=1_000_000,
                   help="gp available to invest (default 1,000,000)")
    p.add_argument("--max-age", type=int, default=300,
                   help="max seconds since the OLDER of the two quotes (default 300)")
    p.add_argument("--min-vol", type=int, default=120,
                   help="min units traded on the thin side per 1h (default 120)")
    p.add_argument("--min-roi", type=float, default=0.01,
                   help="min net ROI per flip, e.g. 0.01 = 1%% (default 0.01)")
    p.add_argument("--members", action="store_true",
                   help="include members-only items")
    p.add_argument("--top", type=int, default=20, help="rows to show (default 20)")
    return p.parse_args(argv)


def config_from(opts) -> filters.FilterConfig:
    return filters.FilterConfig(
        capital=opts.capital, include_members=opts.members,
        max_quote_age=opts.max_age, min_thin_volume_1h=opts.min_vol,
        min_roi=opts.min_roi)


def print_table(rows, funnel, opts):
    print("Filters: capital {:,} gp | quote age <= {}s | thin-side vol >= {}/1h "
          "| ROI >= {:.1%}".format(opts.capital, opts.max_age, opts.min_vol, opts.min_roi))
    print("Funnel:  " + "  ->  ".join(
        "{} {}".format(v, k) for k, v in funnel.items() if v))
    print()
    if not rows:
        print("No flips pass the current filters. Loosen --min-roi or --min-vol.")
        return
    header = ("{:<28} {:>10} {:>10} {:>7} {:>7} {:>6} {:>6} {:>6} {:>7} "
              "{:>11} {:>5} {:>11}")
    print(header.format("ITEM", "BUY", "SELL", "TAX", "MARGIN", "ROI",
                        "LIMIT", "V/1H", "QTY/4H", "GP/4H", "AGE", "SCORE"))
    for r in rows[:opts.top]:
        print("{:<28.28} {:>10,} {:>10,} {:>7,} {:>7,} {:>6.1%} {:>6} {:>6,} "
              "{:>7,} {:>11,} {:>4}s {:>11,.0f}".format(
                  r.name, r.buy, r.sell, r.tax, r.margin, r.roi,
                  "{:,}".format(r.limit) if r.limit is not None else "?",
                  r.thin_volume_1h, r.qty_per_window, r.profit_per_window,
                  r.quote_age, r.score))
    print()
    print("BUY/SELL = conservative estimates. Reference price per side = the 5m "
          "and 1h averages weighted by each bucket's own traded volume; the "
          "estimate is the worse of that and the last real trade. QTY/4H = "
          "min(buy limit, 1h thin-side volume x4, capital//buy). SCORE = GP/4H "
          "halved per 10 min of quote age.")


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
