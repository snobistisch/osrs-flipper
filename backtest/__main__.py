"""Command line entry point: ``python3 -m backtest <command>``."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import fetch, rankers
from .run import SEED, STRATEGIES

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "backtest_panel.npz"


def _log(message: str) -> None:
    print("{}  {}".format(time.strftime("%H:%M:%S"), message), flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m backtest",
                                     description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    get = sub.add_parser("fetch", help="download history into data/ (resumable)")
    get.add_argument("--end", type=int, default=None,
                     help="unix time the window ends (default: today 00:00 UTC)")
    get.add_argument("--days-5m", type=int, default=35)
    get.add_argument("--days-1h", type=int, default=90)
    get.add_argument("--data-dir", default=str(fetch.DATA_DIR))

    build = sub.add_parser("build", help="raw buckets -> compact panel")
    build.add_argument("--data-dir", default=str(fetch.DATA_DIR))

    run = sub.add_parser("run", help="walk-forward evaluation")
    run.add_argument("--panel", default=str(fetch.DATA_DIR / "panel"))
    run.add_argument("--period", choices=("tune", "holdout", "all"),
                     default="tune")
    run.add_argument("--strategy", action="append", choices=sorted(STRATEGIES))
    run.add_argument("--capital", default="20m")
    run.add_argument("--account", default="members",
                     choices=("members", "free-to-play"))
    run.add_argument("--method", action="append",
                     choices=sorted(rankers.METHODS))
    run.add_argument("--workers", type=int, default=0)
    run.add_argument("--seed", type=int, default=SEED)
    run.add_argument("--stride", type=int, default=1,
                     help="keep every n-th session (faster, less precise)")
    run.add_argument("--segment-days", type=float, default=None,
                     help="length of each independent bank history")
    run.add_argument("--out", default=None)
    run.add_argument("--baseline-html", default=None,
                     help="a saved docs/index.html for the browser_baseline "
                          "method, e.g. from `git show <rev>:docs/index.html`")

    report = sub.add_parser("report", help="tables from a result file")
    report.add_argument("results")

    fixture = sub.add_parser("fixture", help="cut the test fixture from a panel")
    fixture.add_argument("--panel", default=str(fetch.DATA_DIR / "panel"))
    fixture.add_argument("--out", default=str(FIXTURE))

    smoke = sub.add_parser("smoke", help="fast run on the committed fixture")
    smoke.add_argument("--panel", default=str(FIXTURE))

    opts = parser.parse_args(argv)

    if opts.command == "fetch":
        end = opts.end or int(time.time()) // 86400 * 86400
        data_dir = Path(opts.data_dir)
        fetch.fetch_mapping(data_dir)
        for timestep, days in (("1h", opts.days_1h), ("5m", opts.days_5m)):
            counts = fetch.download(timestep, end - days * 86400, end, data_dir,
                                    progress=_log)
            _log("{}: {}".format(timestep, counts))
            if counts["failed"]:
                _log("some buckets failed; rerun the command to retry them")
        return 0

    if opts.command == "build":
        from . import panel
        out = panel.build(Path(opts.data_dir), progress=_log)
        print(json.dumps(panel.Panel.load(out).coverage(), indent=1))
        return 0

    if opts.command == "fixture":
        from . import panel
        source = panel.Panel.load(opts.panel)
        mapping = json.loads((Path(opts.panel) / "meta.json").read_text(
            encoding="utf-8"))["mapping"]
        out = panel.make_fixture(source, mapping, opts.out)
        print("{}  {:.0f} KB".format(out, out.stat().st_size / 1024))
        return 0

    from . import report as report_module
    from . import run as run_module
    import engine

    if opts.command == "run":
        capital = engine.parse_gp(opts.capital)
        out = opts.out or str(fetch.DATA_DIR / "results" / "{}-{}-{}.jsonl".format(
            opts.period, opts.account, engine.format_gp(capital)))
        info = run_module.run(
            opts.panel, out, opts.strategy or sorted(STRATEGIES), opts.period,
            capital, opts.account, opts.method, opts.workers, opts.seed,
            opts.stride, progress=_log, baseline_html=opts.baseline_html,
            **({"segment_days": opts.segment_days}
               if opts.segment_days else {}))
        _log("{segments} segments in {seconds:.0f}s -> {out}".format(**info))
        print(json.dumps(report_module.write(out)))
        return 0

    if opts.command == "report":
        paths = report_module.write(opts.results)
        print(Path(paths["markdown"]).read_text(encoding="utf-8"))
        return 0

    if opts.command == "smoke":
        # Seconds, not minutes: every strategy, the old pipeline, the shipped
        # policy and two naive baselines on the committed slice of real
        # prices. The numbers mean nothing (sixty hand-picked items, two
        # days); what is checked is that the harness runs end to end, that
        # the policy places offers, and that every bank's books balance.
        import tempfile
        methods = ["current", "policy", "naive_roi", "random"]
        capital = 2_000_000
        with tempfile.TemporaryDirectory() as folder:
            out = str(Path(folder) / "smoke.jsonl")
            info = run_module.run(opts.panel, out, sorted(STRATEGIES), "all",
                                  capital, "members", methods, 1, SEED)
            paths = report_module.write(out)
            print(Path(paths["markdown"]).read_text(encoding="utf-8"))
            _, records = run_module.load(out)
        problems = []
        if info["segments"] < len(STRATEGIES):
            problems.append("a strategy produced no segment")
        placed = 0
        for record in records:
            for name, by_variant in record["banks"].items():
                for variant, bank in by_variant.items():
                    booked = capital + sum(f["pnl"] for f in bank["flips"])
                    if abs(bank["final"] - booked) > 1:
                        problems.append("{} {} {}: books do not balance".format(
                            record["strategy"], name, variant))
                    if name == "policy":
                        placed += len(bank["flips"])
        if not placed:
            problems.append("the policy placed no offer")
        for problem in problems:
            print("SMOKE FAILED: " + problem, file=sys.stderr)
        return 1 if problems else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
