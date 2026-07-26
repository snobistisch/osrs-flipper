"""Private tick archive: the one edge that cannot be copied off the same API.

Every flipper polling prices.runescape.wiki sees the same numbers at the same
latency, so any signal read off the current snapshot has already been read by
everyone else. What nobody else has is *your* history at higher resolution than
the API serves. /timeseries hands out 6h buckets; polling /latest every 30
seconds and keeping it builds a record of individual trades that the API will
never give you retroactively. The archive is worth nothing today and a great
deal in three months, which is the entire argument for starting it now.

What it makes measurable that the live API cannot:
- fill rates at a given distance from the touch, so the queue-share and
  aggressiveness parameters stop being priors and become measurements
- competing-offer detection: the touch moves but your price never trades,
  meaning somebody stepped in front of you
- intraday volume seasonality, so a 1-hour bucket sampled at peak stops being
  extrapolated across a quiet night
- realised spread, i.e. what a market maker actually kept after the price moved

Storage is kept honest by only writing a tick when the trade timestamps
changed. /latest re-serves the same last trade until a new one happens, so
storing every poll would write ~13 million identical rows a day; storing
changes only follows actual trading activity.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_DB = Path(__file__).parent / "cache" / "ticks.db"

# SQLite blocks writers while another connection holds the write lock. A
# generous timeout costs nothing on an idle database and keeps the collector
# from dying when a dashboard query overlaps a write.
BUSY_TIMEOUT_SECONDS = 120

SCHEMA = """
CREATE TABLE IF NOT EXISTS ticks (
    item_id INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,   -- unix seconds of the poll
    high INTEGER,                 -- latest instant-buy price
    high_time INTEGER,            -- when that trade occurred
    low INTEGER,                  -- latest instant-sell price
    low_time INTEGER,
    PRIMARY KEY (item_id, timestamp)
);

CREATE TABLE IF NOT EXISTS bucket_activity (
    item_id INTEGER NOT NULL,
    timestep TEXT NOT NULL,       -- '5m' or '1h'
    bucket_start INTEGER NOT NULL,
    avg_high INTEGER,
    high_volume INTEGER,
    avg_low INTEGER,
    low_volume INTEGER,
    PRIMARY KEY (item_id, timestep, bucket_start)
);

CREATE INDEX IF NOT EXISTS ticks_by_time ON ticks (timestamp);
CREATE INDEX IF NOT EXISTS buckets_by_time
    ON bucket_activity (timestep, bucket_start);
"""


@dataclass(frozen=True)
class VolumeEstimate:
    """Smoothed throughput for one item, and how much data is behind it."""
    thin_per_hour: float
    high_per_hour: float
    low_per_hour: float
    buckets: int

    @property
    def usable(self) -> bool:
        return self.buckets >= 6


class Archive:
    def __init__(self, db_path: "str | Path" = DEFAULT_DB):
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_SECONDS)
        self.conn.row_factory = sqlite3.Row
        # WAL lets the dashboard read while the collector writes.
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Archive":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- writing ------------------------------------------------------------

    def record_latest(self, quotes: Dict[int, object],
                      polled_at: Optional[int] = None) -> int:
        """Store the quotes whose last-trade timestamps moved since last poll.

        Returns how many rows were written, which is the count of items that
        actually traded — a useful liveness signal in its own right.
        """
        polled_at = int(polled_at if polled_at is not None else time.time())
        previous = self._latest_trade_times()
        rows: List[Tuple] = []
        for item_id, quote in quotes.items():
            high_time = getattr(quote, "high_time", None)
            low_time = getattr(quote, "low_time", None)
            if high_time is None and low_time is None:
                continue
            if previous.get(item_id) == (high_time, low_time):
                continue
            rows.append((int(item_id), polled_at,
                         getattr(quote, "high", None), high_time,
                         getattr(quote, "low", None), low_time))
        if not rows:
            return 0
        before = self.conn.total_changes
        self.conn.executemany(
            "INSERT OR IGNORE INTO ticks"
            " (item_id, timestamp, high, high_time, low, low_time)"
            " VALUES (?, ?, ?, ?, ?, ?)", rows)
        self.conn.commit()
        return self.conn.total_changes - before

    def _latest_trade_times(self) -> Dict[int, Tuple[Optional[int], Optional[int]]]:
        cursor = self.conn.execute(
            "SELECT item_id, high_time, low_time FROM ticks t"
            " WHERE timestamp = (SELECT MAX(timestamp) FROM ticks t2"
            "                    WHERE t2.item_id = t.item_id)")
        return {row["item_id"]: (row["high_time"], row["low_time"])
                for row in cursor}

    def record_buckets(self, timestep: str, activity: Dict[int, object],
                       bucket_start: Optional[int] = None) -> int:
        """Store one /5m or /1h snapshot.

        bucket_start defaults to the current wall clock floored to the bucket
        size, which is what the endpoint is reporting on.
        """
        size = {"5m": 300, "1h": 3600}.get(timestep)
        if size is None:
            raise ValueError("timestep must be '5m' or '1h'")
        if bucket_start is None:
            bucket_start = int(time.time()) // size * size
        rows = []
        for item_id, entry in activity.items():
            high_volume = getattr(entry, "high_volume", 0) or 0
            low_volume = getattr(entry, "low_volume", 0) or 0
            if high_volume <= 0 and low_volume <= 0:
                continue          # empty buckets are the overwhelming majority
            rows.append((int(item_id), timestep, int(bucket_start),
                         getattr(entry, "avg_high", None), high_volume,
                         getattr(entry, "avg_low", None), low_volume))
        if not rows:
            return 0
        # Report rows actually stored, not rows offered: re-polling inside the
        # same bucket is normal and every one of those is ignored.
        before = self.conn.total_changes
        self.conn.executemany(
            "INSERT OR IGNORE INTO bucket_activity"
            " (item_id, timestep, bucket_start, avg_high, high_volume,"
            "  avg_low, low_volume) VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        self.conn.commit()
        return self.conn.total_changes - before

    def prune(self, keep_days: int = 120) -> int:
        """Drop data older than keep_days. Returns rows removed."""
        cutoff = int(time.time()) - keep_days * 86400
        removed = self.conn.execute(
            "DELETE FROM ticks WHERE timestamp < ?", (cutoff,)).rowcount
        removed += self.conn.execute(
            "DELETE FROM bucket_activity WHERE bucket_start < ?",
            (cutoff,)).rowcount
        self.conn.commit()
        return removed

    # -- reading ------------------------------------------------------------

    def volume_ewma(self, item_id: int, half_life_hours: float = 6.0,
                    timestep: str = "1h",
                    lookback_hours: float = 72.0) -> Optional[VolumeEstimate]:
        """Exponentially weighted throughput, newest buckets weighted most.

        The old engine took one 1-hour bucket and multiplied it by four to get
        a 4-hour figure. Volume over a day is strongly U-shaped, so that number
        is roughly double the truth when sampled at peak and half of it at 4am.
        Averaging several days of buckets with a 6-hour half-life keeps the
        estimate responsive without letting one hot bucket set it.
        """
        size = {"5m": 300, "1h": 3600}[timestep]
        cutoff = int(time.time() - lookback_hours * 3600)
        cursor = self.conn.execute(
            "SELECT bucket_start, high_volume, low_volume FROM bucket_activity"
            " WHERE item_id = ? AND timestep = ? AND bucket_start >= ?"
            " ORDER BY bucket_start", (item_id, timestep, cutoff))
        rows = cursor.fetchall()
        if not rows:
            return None
        newest = rows[-1]["bucket_start"]
        per_hour = 3600.0 / size
        weight_sum = high_sum = low_sum = 0.0
        for row in rows:
            age_hours = (newest - row["bucket_start"]) / 3600.0
            weight = 0.5 ** (age_hours / max(half_life_hours, 1e-6))
            weight_sum += weight
            high_sum += weight * (row["high_volume"] or 0) * per_hour
            low_sum += weight * (row["low_volume"] or 0) * per_hour
        if weight_sum <= 0:
            return None
        high_rate = high_sum / weight_sum
        low_rate = low_sum / weight_sum
        return VolumeEstimate(thin_per_hour=min(high_rate, low_rate),
                              high_per_hour=high_rate, low_per_hour=low_rate,
                              buckets=len(rows))

    def summary(self) -> dict:
        ticks = self.conn.execute(
            "SELECT COUNT(*) AS rows, MIN(timestamp) AS first,"
            " MAX(timestamp) AS last, COUNT(DISTINCT item_id) AS items"
            " FROM ticks").fetchone()
        buckets = self.conn.execute(
            "SELECT COUNT(*) AS rows, MIN(bucket_start) AS first"
            " FROM bucket_activity").fetchone()
        span = 0.0
        if ticks and ticks["first"] and ticks["last"]:
            span = (ticks["last"] - ticks["first"]) / 86400.0
        return {
            "ticks": ticks["rows"] if ticks else 0,
            "items": ticks["items"] if ticks else 0,
            "buckets": buckets["rows"] if buckets else 0,
            "days": span,
        }
