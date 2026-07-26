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
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

BASE_URL = "https://prices.runescape.wiki/api/v1/osrs"
# Wiki AUP wants a way to reach whoever runs this. If you fork or deploy the
# tool, put your own contact here.
USER_AGENT = ("osrs-flipper/0.1 - GE flipping dashboard - "
              "https://github.com/snobistisch/osrs-flipper")

LATEST_TTL = 30          # seconds; also the minimum poll interval
INTERVAL_TTL = {"5m": 60, "1h": 300}
MAPPING_MAX_AGE = 24 * 3600
TIMESERIES_TTL = 1800    # per-item history moves slowly at 6h buckets
TIMESTEPS = ("5m", "1h", "6h", "24h")


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
    return int(value)


class WikiClient:
    def __init__(self, cache_dir: "str | Path" = None):
        if cache_dir is None:
            cache_dir = Path(__file__).parent / "cache"
        self.cache_dir = Path(cache_dir)
        self._memory: Dict[str, Tuple[float, object]] = {}

    # -- transport -----------------------------------------------------------

    def _get(self, path: str, params: Optional[dict] = None) -> object:
        url = BASE_URL + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
        except (urllib.error.URLError, OSError) as exc:
            raise ApiError("GET {} failed: {}".format(url, exc)) from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ApiError("GET {} returned invalid JSON".format(url)) from exc

    def _cached(self, key: str, ttl: float, fetch: Callable[[], object]) -> object:
        now = time.monotonic()
        hit = self._memory.get(key)
        if hit is not None and now - hit[0] < ttl:
            return hit[1]
        value = fetch()
        self._memory[key] = (now, value)
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
            quotes[item_id] = Quote(
                high=_opt_int(row.get("high")),
                high_time=_opt_int(row.get("highTime")),
                low=_opt_int(row.get("low")),
                low_time=_opt_int(row.get("lowTime")),
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
            activity[item_id] = Activity(
                avg_high=_opt_int(row.get("avgHighPrice")),
                high_volume=_opt_int(row.get("highPriceVolume")) or 0,
                avg_low=_opt_int(row.get("avgLowPrice")),
                low_volume=_opt_int(row.get("lowPriceVolume")) or 0,
            )
        return activity

    def mapping(self) -> Dict[int, Item]:
        """Static item metadata, cached on disk and refreshed daily."""
        return self._cached("mapping", MAPPING_MAX_AGE, self._load_mapping)

    def _load_mapping(self) -> Dict[int, Item]:
        path = self.cache_dir / "mapping.json"
        raw = None
        if path.exists() and time.time() - path.stat().st_mtime < MAPPING_MAX_AGE:
            try:
                raw = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                raw = None
        if raw is None:
            raw = self._get("/mapping")
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(raw))
        if not isinstance(raw, list):
            raise ApiError("/mapping: expected a list")
        items = {}
        for row in raw:
            if not isinstance(row, dict):
                continue
            item_id = _opt_int(row.get("id"))
            name = row.get("name")
            if item_id is None or not isinstance(name, str):
                continue
            items[item_id] = Item(
                id=item_id,
                name=name,
                members=bool(row.get("members", True)),
                limit=_opt_int(row.get("limit")),
                value=_opt_int(row.get("value")) or 0,
                highalch=_opt_int(row.get("highalch")),
            )
        return items

    def timeseries(self, item_id: int, timestep: str = "1h") -> List[dict]:
        """History for ONE item: the detail view, plus top-K refinement.

        Never called across all items — only for a single selected item or a
        shortlist of ~15 candidates, and cached 30 minutes so repeated
        rankings reuse the same fetch.
        """
        if timestep not in TIMESTEPS:
            raise ValueError("timestep must be one of {}".format(list(TIMESTEPS)))
        key = "ts:{}:{}".format(item_id, timestep)
        return self._cached(key, TIMESERIES_TTL,
                            lambda: self._fetch_timeseries(item_id, timestep))

    def _fetch_timeseries(self, item_id: int, timestep: str) -> List[dict]:
        payload = self._get("/timeseries", {"id": item_id, "timestep": timestep})
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise ApiError("/timeseries: response has no 'data' list")
        return [row for row in data if isinstance(row, dict)]
