"""Drive the browser app's own planning code on a backtest snapshot.

The browser applies gates the Python pipeline does not (liquidity, ROI,
undercut room, a per-position bank cap, a stricter plan filter). Measuring
"the tool as most people use it" therefore means running the real inline
script, not a Python approximation of it. ``tests/js_plan.cjs`` does that
under Node; this module is the pipe to it.

Node is optional. Without it the ``browser`` method is simply unavailable.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from .panel import Panel, Snapshot

NODE = shutil.which("node")
RUNNER = Path(__file__).resolve().parent.parent / "tests" / "js_plan.cjs"
# The live /timeseries route returns 365 five-minute buckets; the app reads
# its recent-execution evidence, its reach and its replay from that one series.
RECENT_HOURS = 365 / 12.0


def snapshot_payload(snapshot: Snapshot, capital: int, account: str,
                     strategy: str, horizon_hours: float,
                     nature_cost: int, bank_risk_percent: int = 25) -> dict:
    """The snapshot in the shape the browser's fetchers hand to screen()."""
    def activity(table):
        return {str(item_id): {
            "avgHighPrice": a.avg_high, "highPriceVolume": a.high_volume,
            "avgLowPrice": a.avg_low, "lowPriceVolume": a.low_volume}
            for item_id, a in table.items()}
    return {
        "items": {str(item.id): {"name": item.name, "members": item.members,
                                 "limit": item.limit, "highalch": item.highalch,
                                 "icon": None}
                  for item in snapshot.items.values()},
        "quotes": {str(item_id): {"high": q.high, "low": q.low,
                                  "highTime": q.high_time, "lowTime": q.low_time}
                   for item_id, q in snapshot.quotes.items()},
        "act5m": activity(snapshot.activity_5m),
        "act1h": activity(snapshot.activity_1h),
        "now": snapshot.now, "capital": capital, "account": account,
        "strategy": strategy, "horizonHours": horizon_hours,
        "natureCost": nature_cost, "bankRiskPercent": bank_risk_percent,
    }


class BrowserPlanner:
    """One long-lived Node process answering plan requests."""

    def __init__(self):
        if NODE is None:
            raise RuntimeError("Node.js is required for the browser methods")
        self.process = subprocess.Popen(
            [NODE, str(RUNNER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self._key = 0

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.stdin.close()
            self.process.wait(timeout=10)

    def _call(self, request: dict) -> dict:
        self.process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("the Node plan runner exited unexpectedly")
        reply = json.loads(line)
        if "error" in reply:
            raise RuntimeError("browser plan failed: {}".format(reply["error"]))
        return reply


    def prepare(self, panel: Panel, snapshot: Snapshot, capital: int,
                account: str, strategy: str, horizon_hours: float,
                nature_cost: int, bank_risk_percent: int = 25,
                limit_used: Optional[dict] = None,
                order_size: Optional[str] = None) -> int:
        """Screen, deep-check and order one snapshot; returns its key.

        Fetches exactly the history the app asks for.

        ``limit_used`` is the browser's usage map, ``{"items": {id: units},
        "groups": {group: units}}``; None plans on whole buy limits.
        """
        payload = snapshot_payload(snapshot, capital, account, strategy,
                                   horizon_hours, nature_cost,
                                   bank_risk_percent)
        if limit_used is not None:
            payload["limitUsed"] = limit_used
        if order_size is not None:
            payload["orderSize"] = order_size
        self._key += 1
        targets = self._call({"op": "targets", "key": self._key,
                              "snapshot": payload})["targets"]
        self._call({
            "op": "prepare", "key": self._key,
            "history": {str(item_id): panel.history_6h(item_id, snapshot.now)
                        for item_id in targets},
            "recent": {str(item_id): panel.recent_5m(item_id, snapshot.now,
                                                     RECENT_HOURS)
                       for item_id in targets}})
        return self._key

    def allocate(self, key: int, capital: int, slots: int,
                 exclude: Optional[List[int]] = None) -> List[dict]:
        """The offers the automatic plan funds from this bank and these slots."""
        return self._call({"op": "allocate", "key": key, "capital": capital,
                           "slots": slots, "exclude": exclude or []})["plan"]

    def release(self, key: int) -> None:
        self._call({"op": "release", "key": key})
