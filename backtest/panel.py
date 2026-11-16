"""Compact price panel and point-in-time market snapshots.

The raw download is one JSON file per bucket. ``build`` turns it into dense
``time x item`` arrays (prices and volumes per side, 0 = nothing traded) that
are memory-mapped, so a walk-forward run can slice any window cheaply.

Everything a model may see at decision time ``t`` goes through ``Panel``
methods that take ``t`` and return only buckets that had *closed* by then
(``bucket_start + step <= t``). That single rule is the look-ahead guard;
tests/test_backtest.py checks it by corrupting the future and asserting the
snapshot does not change.

What the snapshot can and cannot reproduce:

- ``/5m`` and ``/1h`` are reproduced exactly: they are the same buckets the
  live endpoints served at the time.
- ``/latest`` has no history. It is approximated per side by the most recent
  5-minute bucket in which that side traded: the bucket's average price, time
  stamped at the bucket's midpoint. A live ``/latest`` is one single trade and
  therefore noisier than this proxy, so the backtest *understates* the damage
  outlier prints do to the live tool.
- ``/timeseries`` at 6h is rebuilt from complete, aligned 1-hour buckets.
- ``/mapping`` is today's: buy limits are assumed unchanged over the window.
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from api import Activity, Item, Quote

from . import fetch

STEP_5M = 300
STEP_1H = 3600
STEP_6H = 21600
FIELDS = ("hp", "lp", "hv", "lv")      # avg high price, avg low price, volumes
LATEST_LOOKBACK_BUCKETS = 36            # 3h: the 1h gate needs both sides anyway
_KEYS = {"hp": "avgHighPrice", "lp": "avgLowPrice",
         "hv": "highPriceVolume", "lv": "lowPriceVolume"}


@dataclass(frozen=True)
class Snapshot:
    now: int
    items: Dict[int, Item]
    quotes: Dict[int, Quote]
    activity_5m: Dict[int, Activity]
    activity_1h: Dict[int, Activity]


def parse_mapping(raw: Sequence[dict]) -> Dict[int, Item]:
    items = {}
    for row in raw:
        try:
            item_id = int(row["id"])
            name = str(row["name"])
        except (KeyError, TypeError, ValueError):
            continue
        limit = row.get("limit")
        highalch = row.get("highalch")
        items[item_id] = Item(
            id=item_id, name=name, members=row.get("members") is not False,
            limit=int(limit) if isinstance(limit, (int, float)) and limit > 0 else None,
            value=int(row.get("value") or 0),
            highalch=int(highalch) if isinstance(highalch, (int, float)) else None)
    return items


def _clean(value: object) -> int:
    """Non-negative integer or 0. Prices above uint32 cannot occur in v1."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if value != value or value <= 0 or value > 4_294_967_295:
        return 0
    return int(round(value))


class Panel:
    """Dense history for one fixed item universe."""

    def __init__(self, item_ids: np.ndarray, items: Dict[int, Item],
                 t0_5m: int, arrays_5m: Dict[str, np.ndarray],
                 t0_1h: int, arrays_1h: Dict[str, np.ndarray],
                 present_5m: Optional[np.ndarray] = None,
                 present_1h: Optional[np.ndarray] = None):
        self.item_ids = np.asarray(item_ids, dtype=np.int64)
        self.items = items
        self.column = {int(item_id): index
                       for index, item_id in enumerate(self.item_ids)}
        self.t0_5m, self.t0_1h = int(t0_5m), int(t0_1h)
        self.a5, self.a1 = arrays_5m, arrays_1h
        self.n5 = int(arrays_5m["hp"].shape[0])
        self.n1 = int(arrays_1h["hp"].shape[0])
        self.present_5m = present_5m
        self.present_1h = present_1h
        self._six_hour: Optional[Dict[str, np.ndarray]] = None

    # -- construction -------------------------------------------------------

    @classmethod
    def load(cls, path: "str | Path") -> "Panel":
        """Load a built panel directory (memory-mapped) or an .npz fixture."""
        path = Path(path)
        if path.is_dir():
            meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
            a5 = {f: np.load(path / "5m_{}.npy".format(f), mmap_mode="r")
                  for f in FIELDS}
            a1 = {f: np.load(path / "1h_{}.npy".format(f), mmap_mode="r")
                  for f in FIELDS}
            present5 = np.load(path / "5m_present.npy")
            present1 = np.load(path / "1h_present.npy")
            return cls(np.array(meta["item_ids"]), parse_mapping(meta["mapping"]),
                       meta["t0_5m"], a5, meta["t0_1h"], a1, present5, present1)
        with np.load(path, allow_pickle=False) as data:
            meta = json.loads(str(data["meta"]))
            a5 = {f: data["5m_" + f] for f in FIELDS}
            a1 = {f: data["1h_" + f] for f in FIELDS}
            return cls(data["item_ids"], parse_mapping(meta["mapping"]),
                       meta["t0_5m"], a5, meta["t0_1h"], a1)

    def save_npz(self, path: "str | Path", mapping: Sequence[dict]) -> None:
        meta = {"t0_5m": self.t0_5m, "t0_1h": self.t0_1h,
                "mapping": list(mapping)}
        arrays = {"5m_" + f: np.asarray(self.a5[f]) for f in FIELDS}
        arrays.update({"1h_" + f: np.asarray(self.a1[f]) for f in FIELDS})
        np.savez_compressed(path, item_ids=self.item_ids,
                            meta=np.array(json.dumps(meta)), **arrays)

    # -- time ---------------------------------------------------------------

    @property
    def start(self) -> int:
        return self.t0_5m

    @property
    def end(self) -> int:
        return self.t0_5m + self.n5 * STEP_5M

    def closed_5m(self, t: int) -> int:
        """Number of 5m buckets that had closed by ``t`` (exclusive index)."""
        return max(0, min(self.n5, (int(t) - self.t0_5m) // STEP_5M))

    def closed_1h(self, t: int) -> int:
        return max(0, min(self.n1, (int(t) - self.t0_1h) // STEP_1H))

    # -- snapshots ----------------------------------------------------------

    def _activity(self, arrays: Dict[str, np.ndarray], row: int
                  ) -> Dict[int, Activity]:
        hp, lp = arrays["hp"][row], arrays["lp"][row]
        hv, lv = arrays["hv"][row], arrays["lv"][row]
        out = {}
        for column in np.nonzero((hp > 0) | (lp > 0))[0]:
            high, low = int(hp[column]), int(lp[column])
            out[int(self.item_ids[column])] = Activity(
                avg_high=high or None, high_volume=int(hv[column]) if high else 0,
                avg_low=low or None, low_volume=int(lv[column]) if low else 0)
        return out

    def snapshot(self, t: int) -> Snapshot:
        """What the live endpoints would have returned at time ``t``."""
        t = int(t)
        closed5, closed1 = self.closed_5m(t), self.closed_1h(t)
        if closed5 < 1 or closed1 < 1:
            raise ValueError("no closed bucket before t={}".format(t))
        activity_5m = self._activity(self.a5, closed5 - 1)
        activity_1h = self._activity(self.a1, closed1 - 1)

        first = max(0, closed5 - LATEST_LOOKBACK_BUCKETS)
        quotes: Dict[int, Quote] = {}
        sides = {}
        for side in ("h", "l"):
            volume = np.asarray(self.a5[side + "v"][first:closed5])
            price = np.asarray(self.a5[side + "p"][first:closed5])
            traded = (volume > 0) & (price > 0)
            # Index of the newest traded bucket per item; -1 when none.
            newest = traded.shape[0] - 1 - np.argmax(traded[::-1], axis=0)
            newest[~traded.any(axis=0)] = -1
            sides[side] = (newest, price)
        for column, item_id in enumerate(self.item_ids):
            high_row, low_row = sides["h"][0][column], sides["l"][0][column]
            if high_row < 0 and low_row < 0:
                continue
            quotes[int(item_id)] = Quote(
                high=int(sides["h"][1][high_row, column]) if high_row >= 0 else None,
                high_time=(self.t0_5m + (first + int(high_row)) * STEP_5M
                           + STEP_5M // 2) if high_row >= 0 else None,
                low=int(sides["l"][1][low_row, column]) if low_row >= 0 else None,
                low_time=(self.t0_5m + (first + int(low_row)) * STEP_5M
                          + STEP_5M // 2) if low_row >= 0 else None)
        return Snapshot(t, self.items, quotes, activity_5m, activity_1h)

    # -- per-item history (the /timeseries stand-ins) -----------------------

    def _six_hour_arrays(self) -> Dict[str, np.ndarray]:
        """Aligned 6h buckets aggregated from 1h ones; volume-weighted price."""
        if self._six_hour is None:
            offset = (-self.t0_1h // STEP_1H) % 6       # hours to next 6h edge
            usable = (self.n1 - offset) // 6
            out = {"t0": self.t0_1h + offset * STEP_1H}
            for side in ("h", "l"):
                price = np.asarray(
                    self.a1[side + "p"][offset:offset + usable * 6],
                    dtype=np.float64).reshape(usable, 6, -1)
                volume = np.asarray(
                    self.a1[side + "v"][offset:offset + usable * 6],
                    dtype=np.float64).reshape(usable, 6, -1)
                total = volume.sum(axis=1)
                weighted = (price * volume).sum(axis=1)
                out[side + "v"] = total
                out[side + "p"] = np.divide(weighted, total,
                                            out=np.zeros_like(weighted),
                                            where=total > 0)
            self._six_hour = out
        return self._six_hour

    @staticmethod
    def _point(timestamp: int, hp: float, hv: float, lp: float, lv: float) -> dict:
        return {"timestamp": int(timestamp),
                "avgHighPrice": int(round(hp)) if hp > 0 and hv > 0 else None,
                "highPriceVolume": int(hv) if hp > 0 else 0,
                "avgLowPrice": int(round(lp)) if lp > 0 and lv > 0 else None,
                "lowPriceVolume": int(lv) if lp > 0 else 0}

    def history_6h(self, item_id: int, t: int, buckets: int = 56) -> List[dict]:
        """The last ``buckets`` complete 6h buckets before ``t``, oldest first."""
        column = self.column.get(int(item_id))
        if column is None:
            return []
        six = self._six_hour_arrays()
        closed = max(0, min(six["hp"].shape[0], (int(t) - six["t0"]) // STEP_6H))
        first = max(0, closed - buckets)
        return [self._point(six["t0"] + row * STEP_6H,
                            six["hp"][row, column], six["hv"][row, column],
                            six["lp"][row, column], six["lv"][row, column])
                for row in range(first, closed)]

    def recent_5m(self, item_id: int, t: int, hours: float = 6.0) -> List[dict]:
        column = self.column.get(int(item_id))
        if column is None:
            return []
        closed = self.closed_5m(t)
        first = max(0, closed - int(hours * 3600 // STEP_5M))
        return [self._point(self.t0_5m + row * STEP_5M,
                            float(self.a5["hp"][row, column]),
                            float(self.a5["hv"][row, column]),
                            float(self.a5["lp"][row, column]),
                            float(self.a5["lv"][row, column]))
                for row in range(first, closed)]


    # -- the future, for the fill simulator only ----------------------------

    def future_5m(self, item_id: int, t: int, seconds: int) -> Dict[str, np.ndarray]:
        """Buckets starting at or after ``t``. Never call this from a model."""
        column = self.column[int(item_id)]
        first = max(0, -(-(int(t) - self.t0_5m) // STEP_5M))
        last = min(self.n5, first + int(seconds) // STEP_5M)
        return {f: np.asarray(self.a5[f][first:last, column]) for f in FIELDS}

    # -- coverage report ----------------------------------------------------

    def coverage(self) -> dict:
        def describe(arrays, t0, step, present):
            n = arrays["hp"].shape[0]
            traded = (np.asarray(arrays["hv"]) > 0) | (np.asarray(arrays["lv"]) > 0)
            per_bucket = traded.sum(axis=1)
            return {
                "start": int(t0), "end": int(t0 + n * step), "buckets": int(n),
                "days": round(n * step / 86400.0, 2),
                "missing_buckets": (int((~present).sum())
                                    if present is not None else None),
                "items_ever_traded": int(traded.any(axis=0).sum()),
                "median_items_per_bucket": float(np.median(per_bucket)),
            }
        return {"5m": describe(self.a5, self.t0_5m, STEP_5M, self.present_5m),
                "1h": describe(self.a1, self.t0_1h, STEP_1H, self.present_1h),
                "items_in_mapping": len(self.items)}


def build(data_dir: Path = fetch.DATA_DIR, begin_5m: Optional[int] = None,
          end: Optional[int] = None, begin_1h: Optional[int] = None,
          progress=None, out_dir: Optional[Path] = None) -> Path:
    """Raw gzip buckets -> ``data/panel`` arrays. Returns the panel directory.

    ``end`` cuts both series (exclusive), which is how a partial download is
    turned into a consistent panel.
    """
    data_dir = Path(data_dir)
    mapping = json.loads((data_dir / "raw" / "mapping.json").read_text("utf-8"))
    items = parse_mapping(mapping)
    item_ids = np.array(sorted(items), dtype=np.int64)
    column = {int(item_id): index for index, item_id in enumerate(item_ids)}
    out = Path(out_dir) if out_dir else data_dir / "panel"
    out.mkdir(parents=True, exist_ok=True)
    meta = {"item_ids": [int(i) for i in item_ids], "mapping": mapping}

    for timestep, step, begin in (("5m", STEP_5M, begin_5m),
                                  ("1h", STEP_1H, begin_1h)):
        available = sorted(int(p.name.split(".")[0])
                           for p in (data_dir / "raw" / timestep).glob("*.json.gz"))
        if end is not None:
            available = [start for start in available if start + step <= end]
        if not available:
            raise FileNotFoundError("no raw {} buckets under {}".format(
                timestep, data_dir))
        first = available[0] if begin is None else int(begin)
        last = (available[-1] + step) if end is None else int(end)
        count = (last - first) // step
        arrays = {f: np.lib.format.open_memmap(
            out / "{}_{}.npy".format(timestep, f), mode="w+",
            dtype=np.uint32, shape=(count, len(item_ids))) for f in FIELDS}
        present = np.zeros(count, dtype=bool)
        wanted = set(range(first, last, step))
        for start in available:
            if start not in wanted:
                continue
            row = (start - first) // step
            with gzip.open(fetch.bucket_path(data_dir, timestep, start), "rt",
                           encoding="utf-8") as handle:
                data = json.load(handle)["data"]
            for raw_id, entry in data.items():
                index = column.get(int(raw_id))
                if index is None or not isinstance(entry, dict):
                    continue
                for f in ("h", "l"):
                    price = _clean(entry.get(_KEYS[f + "p"]))
                    volume = _clean(entry.get(_KEYS[f + "v"]))
                    if price and volume:
                        arrays[f + "p"][row, index] = price
                        arrays[f + "v"][row, index] = volume
            present[row] = True
            if progress and row % 2000 == 0:
                progress("{} {}/{}".format(timestep, row, count))
        for array in arrays.values():
            array.flush()
        np.save(out / "{}_present.npy".format(timestep), present)
        meta["t0_" + timestep] = first
    (out / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return out


def make_fixture(panel: Panel, mapping: Sequence[dict], out: "str | Path",
                 items: int = 60, days_5m: float = 2.75,
                 history_days: int = 15) -> Path:
    """A small real slice for tests: liquid items with a repeating margin.

    The fixture has to hold markets the pipeline actually plans in, so items
    qualify when, over the slice, both sides traded in most hours, the hourly
    spread survived the 2% tax in at least half of them and one unit costs at
    most 500k. The busiest of those are kept. Deterministic for a given panel.
    """
    out = Path(out)
    n5 = int(days_5m * 86400) // STEP_5M
    end = panel.t0_5m + n5 * STEP_5M
    first_1h = max(0, (panel.t0_5m - history_days * 86400 - panel.t0_1h) // STEP_1H)
    last_1h = (end - panel.t0_1h) // STEP_1H
    window = slice((panel.t0_5m - panel.t0_1h) // STEP_1H, last_1h)
    high = np.asarray(panel.a1["hp"][window], dtype=np.float64)
    low = np.asarray(panel.a1["lp"][window], dtype=np.float64)
    thin = np.minimum(np.asarray(panel.a1["hv"][window], dtype=np.float64),
                      np.asarray(panel.a1["lv"][window], dtype=np.float64))
    two_sided = (thin > 0).mean(axis=0)
    margin = ((high - np.floor(high / 50.0) - low > 0) & (thin > 0)).mean(axis=0)
    qualifies = ((two_sided >= 0.8) & (margin >= 0.5)
                 & (np.median(low, axis=0) <= 500_000))
    score = np.where(qualifies, np.median(thin, axis=0), -1.0)
    order = np.lexsort((panel.item_ids, -score))[:items]
    columns = np.sort(order)
    chosen = {int(panel.item_ids[c]) for c in columns}
    a5 = {f: np.ascontiguousarray(np.asarray(panel.a5[f][:n5])[:, columns])
          for f in FIELDS}
    a1 = {f: np.ascontiguousarray(
        np.asarray(panel.a1[f][first_1h:last_1h])[:, columns]) for f in FIELDS}
    keep = [row for row in mapping if int(row.get("id", -1)) in chosen]
    keep = [{k: row.get(k) for k in ("id", "name", "members", "limit", "value",
                                     "highalch")} for row in keep]
    small = Panel(panel.item_ids[columns], parse_mapping(keep), panel.t0_5m, a5,
                  panel.t0_1h + first_1h * STEP_1H, a1)
    out.parent.mkdir(parents=True, exist_ok=True)
    small.save_npz(out, keep)
    return out
