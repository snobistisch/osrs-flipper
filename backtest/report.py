"""Turn a walk-forward result file into tables (Markdown) and a JSON summary."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import engine

from . import metrics
from .run import DEFAULT_VARIANT, TOUCH_VARIANT, load

BASELINE = "random"
DETAILED = (DEFAULT_VARIANT, TOUCH_VARIANT)


def summary(path: "str | Path", baseline: str = BASELINE,
            draws: int = metrics.BOOTSTRAP_DRAWS) -> dict:
    meta, records = load(path)
    slots = engine.AccountType(meta["account"]).slots
    out = {"meta": meta, "strategies": {}}
    for strategy in sorted({r["strategy"] for r in records}):
        rows = [r for r in records if r["strategy"] == strategy]
        block = {"segments": len(rows),
                 "steps": sum(r["steps"] for r in rows), "methods": {}}
        for method in meta["methods"]:
            per_variant = {}
            for variant in meta["variants"]:
                point = metrics.summarise(rows, method, variant,
                                          meta["capital"], slots)
                if point is None:
                    continue
                point["ci"] = metrics.bootstrap(
                    rows, method, variant,
                    baseline if method != baseline
                    and baseline in meta["methods"] else None,
                    draws, meta["seed"])
                if variant in DETAILED:
                    table = metrics.reliability(rows, method, variant)
                    point["reliability"] = table
                    point["calibration_error"] = metrics.calibration_error(table)
                    point["time_band"] = metrics.time_band(rows, method, variant)
                    point["ev_capture"] = metrics.ev_capture(rows, method, variant)
                per_variant[variant] = point
            block["methods"][method] = per_variant
        out["strategies"][strategy] = block
    return out


def _ci(point: dict, metric: str) -> str:
    ci = point.get("ci", {}).get(metric)
    if not ci:
        return ""
    return " [{} .. {}]".format(metrics.fmt_gp(ci["lo"]), metrics.fmt_gp(ci["hi"]))


def _table(block: dict, variant: str, baseline: str) -> List[str]:
    lines = ["| method | bank gp/h [95% CI] | patient | gp/slot-h | gp/1m-cap-h "
             "| roi | win | loss | fill | done | p5 flip | max DD | slots "
             "| deployed | offers/day | vs {} [95% CI] | p |".format(baseline),
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for method, variants in block["methods"].items():
        point = variants.get(variant)
        if point is None:
            continue
        ci = point.get("ci", {}).get("bank_gp_hour", {})
        versus = ("—" if "diff" not in ci else "{} [{} .. {}]".format(
            metrics.fmt_gp(ci["diff"]), metrics.fmt_gp(ci["diff_lo"]),
            metrics.fmt_gp(ci["diff_hi"])))
        lines.append(
            "| {} | {}{} | {} | {} | {} | {:.2%} | {:.0%} | {:.0%} | {:.0%} "
            "| {:.0%} | {:.2%} | {:.2%} | {:.0%} | {:.0%} | {:.1f} | {} | {} |"
            .format(
                method, metrics.fmt_gp(point["bank_gp_hour"]),
                _ci(point, "bank_gp_hour"),
                metrics.fmt_gp(point["bank_gp_hour_patient"]),
                metrics.fmt_gp(point["gp_slot_hour"]),
                metrics.fmt_gp(point["gp_capital_hour"]), point["roi"],
                point["win_rate"], point["loss_rate"], point["fill_rate"],
                point["completion"], point["p5_flip_roi"],
                point["max_drawdown"], point["slots_used"], point["deployed"],
                point["offers_per_day"], versus,
                "—" if "p_worse" not in ci else "{:.3f}".format(ci["p_worse"])))
    return lines


def markdown(data: dict, baseline: str = BASELINE) -> str:
    meta = data["meta"]
    lines: List[str] = []
    for strategy, block in data["strategies"].items():
        lines += ["", "### {} — {} period, bank {}, {} segments, {} decisions"
                  .format(strategy, meta["period"],
                          metrics.fmt_gp(meta["capital"]), block["segments"],
                          block["steps"])]
        for variant in DETAILED:
            lines += ["", "Fill rule `{}`:".format(variant), ""]
            lines += _table(block, variant, baseline)
        lines += ["", "Bank gp/h under every fill assumption (rule_capture):",
                  "", "| method | " + " | ".join(meta["variants"]) + " |",
                  "|---|" + "---|" * len(meta["variants"])]
        for method, variants in block["methods"].items():
            lines.append("| {} | {} |".format(method, " | ".join(
                metrics.fmt_gp(variants[v]["bank_gp_hour"]) if v in variants
                else "" for v in meta["variants"])))
    return "\n".join(lines) + "\n"


def calibration_markdown(data: dict, methods: Sequence[str]) -> str:
    lines: List[str] = []
    for strategy, block in data["strategies"].items():
        for method in methods:
            for variant in DETAILED:
                point = block["methods"].get(method, {}).get(variant)
                if not point or not point.get("reliability"):
                    continue
                band, capture = point["time_band"], point["ev_capture"]
                lines += ["", "#### {} / {} — calibration under `{}`".format(
                    strategy, method, variant), "",
                    "| predicted P(full trip) | offers | mean predicted "
                    "| observed |", "|---|---|---|---|"]
                for row in point["reliability"]:
                    lines.append("| {} | {} | {:.0%} | {:.0%} |".format(
                        row["bin"], row["n"], row["predicted"], row["observed"]))
                lines += ["", "Calibration error {:.1%}. Finished within own "
                          "P50/P80/P90: {:.0%} / {:.0%} / {:.0%} (targets 50 / "
                          "80 / 90). Realised {} of {} predicted gp ({:.0%})."
                          .format(point["calibration_error"], band["p50"],
                                  band["p80"], band["p90"],
                                  metrics.fmt_gp(capture["realised_gp"]),
                                  metrics.fmt_gp(capture["predicted_gp"]),
                                  capture["capture"])]
    return "\n".join(lines) + "\n"


def write(path: "str | Path", out_dir: Optional["str | Path"] = None,
          calibrate: Optional[Sequence[str]] = None) -> Dict[str, str]:
    path = Path(path)
    out_dir = Path(out_dir) if out_dir else path.parent
    data = summary(path)
    calibrate = calibrate or [m for m in data["meta"]["methods"]
                              if not m.startswith(("naive", "random"))]
    stem = path.stem
    json_path = out_dir / (stem + ".summary.json")
    md_path = out_dir / (stem + ".md")
    json_path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    md_path.write_text(markdown(data) + calibration_markdown(data, calibrate),
                       encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
