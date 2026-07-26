"""Background poller that fills the tick archive.

    python3 collect.py               # run until interrupted
    python3 collect.py --once        # single poll, for cron
    python3 collect.py --status      # what the archive holds so far

Poll intervals match the wiki's cache TTLs exactly — polling faster returns the
same bytes and only burns their bandwidth. /latest has a 30-second floor under
the acceptable-use policy, and that is what this uses.

Leave it running. Every day it is not running is a day of resolution that
cannot be recovered later, because the API serves no history finer than 6-hour
buckets.
"""
from __future__ import annotations

import argparse
import sys
import time

import api
import archive


def poll_once(client: api.WikiClient, store: archive.Archive,
              last_interval: dict) -> dict:
    """One pass. Returns counts written per endpoint."""
    written = {"latest": 0, "5m": 0, "1h": 0, "errors": []}
    now = time.time()
    try:
        written["latest"] = store.record_latest(client.latest(), int(now))
    except api.ApiError as exc:
        written["errors"].append("latest: {}".format(exc))

    for timestep, period in (("5m", 300), ("1h", 3600)):
        if now - last_interval.get(timestep, 0) < period:
            continue
        try:
            written[timestep] = store.record_buckets(
                timestep, client.interval(timestep))
            last_interval[timestep] = now
        except api.ApiError as exc:
            written["errors"].append("{}: {}".format(timestep, exc))
    return written


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(archive.DEFAULT_DB),
                        help="archive database path")
    parser.add_argument("--interval", type=float, default=api.LATEST_TTL,
                        help="seconds between /latest polls (30 is the floor "
                             "the wiki asks for; lower is not honoured anyway)")
    parser.add_argument("--once", action="store_true",
                        help="single poll then exit, for cron")
    parser.add_argument("--status", action="store_true",
                        help="print what the archive holds and exit")
    parser.add_argument("--prune-days", type=int, default=None,
                        help="drop data older than this many days, then exit")
    parser.add_argument("--quiet", action="store_true")
    opts = parser.parse_args(argv if argv is not None else sys.argv[1:])

    store = archive.Archive(opts.db)
    try:
        if opts.status:
            summary = store.summary()
            print("Archive: {:,} ticks across {:,} items, {:,} bucket rows, "
                  "spanning {:.1f} days".format(
                      summary["ticks"], summary["items"], summary["buckets"],
                      summary["days"]))
            if summary["days"] < 90:
                print("Fill-rate calibration needs roughly 90 days before it "
                      "beats the priors in engine.Calibration.")
            return 0
        if opts.prune_days is not None:
            print("Removed {:,} rows".format(store.prune(opts.prune_days)))
            return 0

        client = api.WikiClient()
        interval = max(opts.interval, api.LATEST_TTL)
        last_interval: dict = {}
        while True:
            started = time.time()
            written = poll_once(client, store, last_interval)
            if not opts.quiet:
                parts = ["{} traded".format(written["latest"])]
                for step in ("5m", "1h"):
                    if written[step]:
                        parts.append("{} {} buckets".format(written[step], step))
                for problem in written["errors"]:
                    parts.append("ERROR " + problem)
                print("{}  {}".format(time.strftime("%H:%M:%S"),
                                      ", ".join(parts)), flush=True)
            if opts.once:
                return 0
            time.sleep(max(0.0, interval - (time.time() - started)))
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
