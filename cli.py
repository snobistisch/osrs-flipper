"""Ranked flips as a plain terminal table.

Usage: python3 cli.py [--capital N] [--slots N] [--members] [--top N]
                      [--max-age S] [--min-vol N] [--min-roi F] [--min-depth N]

The filter flags now narrow what is *displayed*. They no longer decide what
gets scored: everything tradable is scored and shrunk first, so hiding rows
never reorders the ones that remain.
"""
from __future__ import annotations

import argparse
import sys
import time

import api
import archive
import engine
import exemptions
import filters
import merch


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Rank GE flips by expected gp per offer slot per hour")
    p.add_argument("--capital", type=engine.parse_gp, default=1_000_000,
                   help="gp available across all slots, e.g. 250k or 1.5m")
    p.add_argument("--slots", type=int, default=engine.F2P_SLOTS,
                   help="concurrent GE offers: 3 free-to-play, 8 members")
    p.add_argument("--members", action="store_true",
                   help="include members-only items")
    p.add_argument("--top", type=int, default=20, help="rows to show")
    p.add_argument("--deep", type=int, default=15,
                   help="deep-check this many top candidates against 14 days "
                        "of /timeseries history (0 disables). Three times this "
                        "many are actually fetched, so the deep stage can "
                        "reorder rather than just confirm.")
    p.add_argument("--mode", choices=("flip", "crash"), default="flip",
                   help="flip ranks by gp per slot per hour; crash lists the "
                        "deep-checked candidates standing furthest from their "
                        "own 14-day median, ranked by how tradable the "
                        "recovery is. Both read the same fetch. For the "
                        "long-horizon merch view run: python3 agent.py merch")
    p.add_argument("--archive", default=None,
                   help="tick archive to smooth volume estimates with "
                        "(default: use it if cache/ticks.db exists)")
    p.add_argument("--no-archive", action="store_true",
                   help="ignore the tick archive even if present")

    view = p.add_argument_group(
        "display filters", "Applied after scoring. These hide rows; they do "
                           "not change the ranking of what is left.")
    view.add_argument("--max-age", type=int, default=None,
                      help="max seconds since the OLDER of the two quotes")
    view.add_argument("--min-vol", type=int, default=0,
                      help="min units traded on the thin side per 1h")
    view.add_argument("--min-roi", type=float, default=0.0,
                      help="min net ROI per flip, e.g. 0.01 = 1%%")
    view.add_argument("--min-depth", type=int, default=0,
                      help="min gp of undercut room")
    view.add_argument("--min-price", type=engine.parse_gp, default=1,
                      help="min buy price per item, e.g. 100 or 5k")
    view.add_argument("--max-price", type=engine.parse_gp, default=None,
                      help="max buy price per item, e.g. 10k or 1m")
    view.add_argument("--tax-free", action="store_true",
                      help="only flips that pay zero GE tax (sell under 50 gp)")
    view.add_argument("--no-bots", action="store_true",
                      help="hide bot-supplied f2p staples: free-to-play, buy "
                           "limit over 10,000, under 100 gp")
    return p.parse_args(argv)


def config_from(opts, nature_cost: int) -> filters.FilterConfig:
    return filters.FilterConfig(
        capital=opts.capital, slots=opts.slots, include_members=opts.members,
        nature_rune_cost=nature_cost,
        max_quote_age=opts.max_age, min_thin_volume_1h=opts.min_vol,
        min_roi=opts.min_roi, min_undercut_depth=opts.min_depth,
        min_price=opts.min_price, max_price=opts.max_price,
        tax_free_only=opts.tax_free, hide_botted=opts.no_bots)


def print_crash_table(result, opts):
    """The same rows, read for dislocation instead of for throughput."""
    crashed = [(row, merch.crash_context(row)) for row in result.rows]
    crashed = [(row, ctx) for row, ctx in crashed
               if ctx.signal is not None and ctx.signal.score > 0]
    if not crashed:
        print("Nothing among the {} deep-checked candidates is standing far "
              "enough from its own median to call. That is the normal state of "
              "the market.".format(result.deep_checked))
        return
    crashed.sort(key=lambda pair: -pair[1].recovery)

    header = "{:<26} {:>9} {:>8} {:>7} {:>6} {:>8} {:>16} {:>9}"
    print(header.format("ITEM", "BUY", "VS 14D", "VOL", "FILL", "REVERTS",
                        "BADGE", "RECOVERY"))
    for row, ctx in crashed[:opts.top]:
        print("{:<26.26} {:>9,} {:>7.0f}% {:>6.1f}x {:>5.0f}% {:>8} {:>16} "
              "{:>9.0f}".format(
                  row.name, row.buy, ctx.signal.depth * 100, ctx.volume_ratio,
                  (row.fill_share or 0) * 100,
                  "yes" if row.mean_reverting else "no",
                  merch.BADGE_LABELS[ctx.signal.kind], ctx.recovery))
    print()
    print("RECOVERY ranks depth by how much of it you can actually trade: a "
          "70% collapse nobody deals in scores below a 25% dip on a liquid "
          "item that mean-reverts. This covers the candidates the ranking "
          "deep-checked, not every item in the game — scanning all of them "
          "would mean the per-item polling the wiki asks people not to do.")


def print_table(result, opts, config, exempt, nature_cost, archive_note):
    print("Budget {} gp across {} slots | {} tax-exempt items loaded | "
          "nature rune {} gp | {}".format(
              engine.format_gp(opts.capital), opts.slots, len(exempt),
              nature_cost, archive_note))
    if exempt.unmatched_names:
        print("  tax_exempt.json has {} names no item matched: {}".format(
            len(exempt.unmatched_names), ", ".join(exempt.unmatched_names[:5])))
    print("Scored:  " + "  ->  ".join(
        "{} {}".format(v, k) for k, v in result.funnel.items() if v))
    if result.deep_checked:
        print("Deep-checked against 14d history: {}".format(result.deep_checked))
    shrink = result.shrinkage
    if shrink is not None and shrink.applied:
        if not shrink.informative:
            print("Shrinkage: every difference between these scores is within "
                  "estimation noise — today's ranking is not meaningful.")
        else:
            print("Shrinkage: market-wide mean {} gp/slot/h; scores are pulled "
                  "toward it, hardest where volume is thinnest.".format(
                      engine.format_gp(int(shrink.prior_mean_gp))))
    hidden = {k: v for k, v in result.hidden.items() if v and k != "shown"}
    if hidden:
        print("Hidden by display filters:  " + "  ".join(
            "{} {}".format(v, k) for k, v in hidden.items()))
    print()
    if not result.rows:
        print("Nothing to show. Loosen the display filters, or the market is "
              "genuinely offering nothing right now.")
        return

    header = ("{:<24} {:>8} {:>8} {:>7} {:>6} {:>5} {:>7} {:>8} {:>10} {:>7} "
              "{:>11} {:>11}")
    print(header.format("ITEM", "BUY", "SELL", "MARGIN", "ROI", "ROOM",
                        "QTY", "TIED UP", "ROUND TRIP", "P(FILL)", "MEASURED",
                        "EV/SLOT/H"))
    for row in result.rows[:opts.top]:
        print("{:<24.24} {:>8,} {:>8,} {:>7,} {:>5.1f}% {:>5,} {:>7,} {:>8} "
              "{:>10} {:>6.0f}% {:>11,.0f} {:>11,.0f}".format(
                  row.name, row.buy, row.sell, row.margin,
                  row.roi * 100, row.undercut_depth, row.qty_per_window,
                  engine.format_gp(row.capital_needed),
                  engine.format_duration(row.expected_total_seconds),
                  row.p_fill * 100, row.raw_gp_per_slot_hour,
                  row.gp_per_slot_hour))
        if row.allocated_capital is not None:
            print("{:<24} · commit {} gp of the bank here (score-weighted, "
                  "not an equal split)".format(
                      "", engine.format_gp(row.allocated_capital)))
        for note in row.warnings:
            print("{:<24} · {}".format("", note))
    print()
    print("ROUND TRIP = expected time for both legs, from the traded volume "
          "you can reach at your queue position. It is the denominator of "
          "EV/SLOT/H — a slot freed in 20 minutes is worth more than one held "
          "for four hours at twice the margin.")
    print("MEASURED = the score before shrinkage; EV/SLOT/H is after. Ranking "
          "hundreds of noisy estimates surfaces the biggest errors rather than "
          "the biggest values, so each score is pulled toward the market "
          "average by an amount set by how much volume it rests on. A wide gap "
          "between the two columns means the measured number was mostly the "
          "thinness of the data.")


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

    exempt = exemptions.resolve(items)
    nature_cost = exemptions.nature_rune_cost(quotes)
    config = config_from(opts, nature_cost)

    store = None
    volume_lookup = None
    archive_note = "no tick archive (run collect.py to build one)"
    if not opts.no_archive:
        path = opts.archive or archive.DEFAULT_DB
        try:
            store = archive.Archive(path)
            summary = store.summary()
            if summary["buckets"]:
                volume_lookup = _archive_lookup(store)
                archive_note = "archive: {:.1f} days, {:,} bucket rows".format(
                    summary["days"], summary["buckets"])
            else:
                store.close()
                store = None
        except Exception as exc:               # a missing archive is not fatal
            archive_note = "archive unavailable ({})".format(exc)
            store = None

    def fetch(item_id):
        try:
            return client.timeseries(item_id, engine.HISTORY_TIMESTEP)
        except api.ApiError:
            return None

    try:
        result = filters.rank_flips(
            items, quotes, activity_5m, activity_1h, config, now=time.time(),
            fetch_history=fetch if opts.deep > 0 else None,
            top_k=opts.deep, exempt=exempt, volume_lookup=volume_lookup)
        if opts.mode == "crash":
            print_crash_table(result, opts)
        else:
            print_table(result, opts, config, exempt, nature_cost, archive_note)
    finally:
        if store is not None:
            store.close()
    return 0


def _archive_lookup(store):
    """(buyer-initiated, seller-initiated) units/hour, smoothed over days."""
    def lookup(item_id):
        estimate = store.volume_ewma(item_id)
        if estimate is None or not estimate.usable:
            return None
        return estimate.high_per_hour, estimate.low_per_hour
    return lookup


if __name__ == "__main__":
    sys.exit(main())
