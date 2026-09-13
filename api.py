"""HTTP client for the OSRS Wiki real-time prices API.

Acceptable-use constraints (https://prices.runescape.wiki):
- Every request carries a descriptive User-Agent; default agents are blocked.
- Bulk data comes from the all-items routes (/latest, /5m, /1h). The only
  per-item route used is /timeseries, for the detail view of a single item —
  never called in a loop.
- The in-memory TTL on /latest doubles as the 30-second poll limit.
"""
from __future__ import annotations

import json
import math
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Callable, Dict, List, Optional, Tuple

from storage import write_json

# v1 and v2 return byte-identical payloads on every route used here (/latest,
# /5m, /1h, /mapping, /timeseries) — checked directly, not assumed. There is
# nothing to gain by moving, so the version stays configurable rather than
# switched: if v2 ever grows a route worth having, pass base_url to WikiClient.
BASE_URL = "https://prices.runescape.wiki/api/v1/osrs"
BASE_URL_V2 = "https://prices.runescape.wiki/api/v2/osrs"
# Wiki AUP wants a way to reach whoever runs this. If you fork or deploy the
# tool, put your own contact here.
USER_AGENT = ("osrs-flipper/0.2 - GE flipping dashboard - "
              "https://github.com/snobistisch/osrs-flipper")

LATEST_TTL = 30          # seconds; also the minimum poll interval
INTERVAL_TTL = {"5m": 60, "1h": 300}
MAPPING_MAX_AGE = 24 * 3600
TIMESERIES_TTL = 1800    # per-item history moves slowly at 6h buckets
STALE_GRACE = 300       # at most five extra minutes after an endpoint's TTL
TIMESTEPS = ("5m", "1h", "6h", "24h")

# Per-item history also caches to DISK, keyed by timestep. The in-memory cache
# above is useless to anything run from cron: each invocation is a new process
# and starts empty, so a job polling every 15 minutes would refetch the whole
# watchlist every time — precisely the per-item polling the wiki asks people
# not to do. The TTLs are the bucket sizes: a 24h bucket cannot change more
# than once a day, so re-reading it hourly learns nothing.
TIMESERIES_DISK_TTL = {"5m": 300, "1h": 900, "6h": 1800, "24h": 21600}


class ApiError(Exception):
    """The wiki API was unreachable or returned something unusable."""


@dataclass(frozen=True)
class Item:
    id: int
    name: str
    members: bool
    limit: Optional[int]      # buy limit per rolling 4h; None = not published
    value: int
    highalch: Optional[int]


@dataclass(frozen=True)
class Quote:
    high: Optional[int]       # last instant-buy price
    high_time: Optional[int]  # unix seconds
    low: Optional[int]        # last instant-sell price
    low_time: Optional[int]


@dataclass(frozen=True)
class Activity:
    """One row of /5m or /1h: average prices and traded volume in the bucket."""
    avg_high: Optional[int]
    high_volume: int
    avg_low: Optional[int]
    low_volume: int


def _opt_int(value: object) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if (value < 0 or value > 2 ** 53 - 1
            or not math.isfinite(value) or int(value) != value):
        return None
    return int(value)


def _positive_int(value: object) -> Optional[int]:
    return _opt_int(value) or None


def _timestamp(value: object) -> Optional[int]:
    value = _positive_int(value)
    return value if value is not None and value <= time.time() + 60 else None


def clean_history(data: object) -> List[dict]:
    """Validate history before it reaches statistics; keep missing sides null."""
    if not isinstance(data, list):
        raise ApiError("/timeseries: response has no 'data' list")
    rows = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        timestamp = _positive_int(row.get("timestamp"))
        if timestamp is None or timestamp > time.time() + 60:
            continue
        cleaned = dict(row)
        for side in ("High", "Low"):
            price = _positive_int(row.get("avg" + side + "Price"))
            cleaned["avg" + side + "Price"] = price
            cleaned[side.lower() + "PriceVolume"] = (
                _opt_int(row.get(side.lower() + "PriceVolume")) or 0
            ) if price is not None else 0
        rows[timestamp] = cleaned
    return [rows[key] for key in sorted(rows)]


class WikiClient:
    def __init__(self, cache_dir: "str | Path | None" = None,
                 base_url: str = BASE_URL):
        if cache_dir is None:
            cache_dir = Path(__file__).parent / "cache"
        self.cache_dir = Path(cache_dir)
        self.base_url = base_url
        self._memory: Dict[str, Tuple[float, object]] = {}
        self.stale_keys = set()
        self.interval_timestamps: Dict[str, int] = {}
        self._lock = RLock()
        self._retry_at = {}

    # -- transport -----------------------------------------------------------

    def _get(self, path: str, params: Optional[dict] = None) -> object:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        body = None
        last_error = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    body = response.read()
                break
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in (429, 500, 502, 503, 504):
                    break
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    delay = float(retry_after)
                    if not math.isfinite(delay) or delay < 0:
                        raise ValueError("invalid Retry-After")
                    delay = min(5.0, delay)
                except (TypeError, ValueError):
                    delay = 0.35 * (2 ** attempt) + random.random() * 0.10
                if attempt < 2:
                    time.sleep(delay)
            except (urllib.error.URLError, OSError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.35 * (2 ** attempt) + random.random() * 0.10)
        if body is None:
            raise ApiError("GET {} failed after 3 attempts: {}".format(
                url, last_error)) from last_error
        try:
            return json.loads(body)
        except (ValueError, UnicodeError) as exc:
            raise ApiError("GET {} returned invalid JSON".format(url)) from exc

    def _cached(self, key: str, ttl: float, fetch: Callable[[], object]) -> object:
        # The Streamlit resource is shared between sessions. Coalesce fetches
        # and enforce the poll floor even when several sessions refresh at once.
        with self._lock:
            return self._cached_locked(key, ttl, fetch)

    def _cached_locked(self, key: str, ttl: float, fetch: Callable[[], object]) -> object:
        now = time.monotonic()
        hit = self._memory.get(key)
        if hit is not None and now - hit[0] < ttl:
            return hit[1]
        if now < self._retry_at.get(key, 0):
            if hit is not None and now - hit[0] <= ttl + STALE_GRACE:
                return hit[1]
            raise ApiError("{}: retry deferred after API failure".format(key))
        try:
            value = fetch()
        except ApiError:
            # A briefly stale complete snapshot is safer than a half-rendered
            # terminal.  Callers can surface stale_keys while the next refresh
            # retries; a cold start still fails loudly.
            self._retry_at[key] = time.monotonic() + LATEST_TTL
            if hit is not None and now - hit[0] <= ttl + STALE_GRACE:
                self.stale_keys.add(key)
                return hit[1]
            raise
        self.stale_keys.discard(key)
        self._retry_at.pop(key, None)
        self._memory[key] = (time.monotonic(), value)
        return value

    # -- endpoints -----------------------------------------------------------

    def latest(self) -> Dict[int, Quote]:
        """All items' last instant-buy / instant-sell, keyed by item id."""
        return self._cached("latest", LATEST_TTL, self._fetch_latest)

    def _fetch_latest(self) -> Dict[int, Quote]:
        payload = self._get("/latest")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ApiError("/latest: response has no 'data' object")
        quotes = {}
        for raw_id, row in data.items():
            if not isinstance(row, dict):
                continue
            try:
                item_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if item_id <= 0:
                continue
            quotes[item_id] = Quote(
                high=_positive_int(row.get("high")),
                high_time=_timestamp(row.get("highTime")),
                low=_positive_int(row.get("low")),
                low_time=_timestamp(row.get("lowTime")),
            )
        return quotes

    def interval(self, timestep: str = "5m") -> Dict[int, Activity]:
        """Average prices and volumes for the last /5m or /1h bucket."""
        if timestep not in INTERVAL_TTL:
            raise ValueError("timestep must be one of {}".format(sorted(INTERVAL_TTL)))
        return self._cached(
            timestep, INTERVAL_TTL[timestep], lambda: self._fetch_interval(timestep)
        )

    def _fetch_interval(self, timestep: str) -> Dict[int, Activity]:
        payload = self._get("/" + timestep)
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ApiError("/{}: response has no 'data' object".format(timestep))
        activity = {}
        for raw_id, row in data.items():
            if not isinstance(row, dict):
                continue
            try:
                item_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if item_id <= 0:
                continue
            high = _positive_int(row.get("avgHighPrice"))
            low = _positive_int(row.get("avgLowPrice"))
            activity[item_id] = Activity(
                avg_high=high,
                high_volume=(_opt_int(row.get("highPriceVolume")) or 0) if high else 0,
                avg_low=low,
                low_volume=(_opt_int(row.get("lowPriceVolume")) or 0) if low else 0,
            )
        timestamp = _positive_int(payload.get("timestamp"))
        if timestamp is not None and timestamp <= time.time() + 60:
            self.interval_timestamps[timestep] = timestamp
        else:
            self.interval_timestamps.pop(timestep, None)
        return activity

    def mapping(self) -> Dict[int, Item]:
        """Static item metadata, cached on disk and refreshed daily."""
        return self._cached("mapping", MAPPING_MAX_AGE, self._load_mapping)

    def _load_mapping(self) -> Dict[int, Item]:
        path = self.cache_dir / "mapping.json"
        raw = None
        try:
            if 0 <= time.time() - path.stat().st_mtime < MAPPING_MAX_AGE:
                raw = json.loads(path.read_text())
                if not isinstance(raw, list):
                    raw = None
        except (OSError, ValueError):
            raw = None
        if raw is None:
            raw = self._get("/mapping")
            if not isinstance(raw, list):
                raise ApiError("/mapping: expected a list")
            try:
                write_json(path, raw)
            except (OSError, ValueError):
                pass
        if not isinstance(raw, list):
            raise ApiError("/mapping: expected a list")
        items = {}
        for row in raw:
            if not isinstance(row, dict):
                continue
            item_id = _positive_int(row.get("id"))
            name = row.get("name")
            if item_id is None or not isinstance(name, str):
                continue
            items[item_id] = Item(
                id=item_id,
                name=name,
                members=row.get("members") is not False,
                limit=_positive_int(row.get("limit")),
                value=_opt_int(row.get("value")) or 0,
                highalch=_opt_int(row.get("highalch")),
            )
        return items

    def timeseries(self, item_id: int, timestep: str = "1h") -> List[dict]:
        """History for ONE item: the detail view, plus top-K refinement.

        Never called across all items — only for a single selected item or the
        bounded deep/recent shortlist, and cached 30 minutes so repeated
        rankings reuse the same fetch.
        """
        if timestep not in TIMESTEPS:
            raise ValueError("timestep must be one of {}".format(list(TIMESTEPS)))
        key = "ts:{}:{}".format(item_id, timestep)
        return self._cached(
            key, TIMESERIES_TTL,
            lambda: self._timeseries_from_disk(item_id, timestep))

    def _timeseries_path(self, item_id: int, timestep: str) -> Path:
        return self.cache_dir / "timeseries" / timestep / "{}.json".format(item_id)

    def _timeseries_from_disk(self, item_id: int, timestep: str) -> List[dict]:
        """Disk layer under the memory cache, so cron runs do not refetch.

        A stale or corrupt file is treated as a miss rather than an error: the
        worst case is one extra request, and failing a whole scan because a
        cache file was truncated by a killed process would be worse.
        """
        path = self._timeseries_path(item_id, timestep)
        ttl = TIMESERIES_DISK_TTL.get(timestep, TIMESERIES_TTL)
        try:
            with path.open(encoding="utf-8") as handle:
                stored = json.load(handle)
            if 0 <= time.time() - stored["at"] < ttl:
                return clean_history(stored["data"])
        except (OSError, ValueError, KeyError, TypeError, ApiError):
            pass

        data = self._fetch_timeseries(item_id, timestep)
        try:
            write_json(path, {"at": time.time(), "data": data})
        except (OSError, ValueError):
            pass                      # read-only disk: the fetch still worked
        return data

    def cached_timeseries_age(self, item_id: int,
                              timestep: str) -> Optional[float]:
        """Seconds since this item's history was written, or None if absent."""
        try:
            with self._timeseries_path(item_id, timestep).open(
                    encoding="utf-8") as handle:
                return time.time() - json.load(handle)["at"]
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _fetch_timeseries(self, item_id: int, timestep: str) -> List[dict]:
        payload = self._get("/timeseries", {"id": item_id, "timestep": timestep})
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise ApiError("/timeseries: response has no 'data' list")
        return clean_history(data)
