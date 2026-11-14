"""Download all-item history buckets from the OSRS Wiki real-time prices API.

The API serves every item's 5-minute and 1-hour averages for any past bucket
through ``/5m?timestamp=`` and ``/1h?timestamp=`` (checked against the live
documentation on 2026-11-13: one request returns the whole item universe, so
no per-item sweep is needed). Each response is cached as one gzip file under
``data/raw/<timestep>/<bucket_start>.json.gz``; a rerun only fetches what is
missing, which is what makes the dataset reproducible and the download
resumable.

Etiquette, from https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices:
a descriptive User-Agent, no per-item loops, and nothing close to "multiple
large queries per second for a sustained period". This runs one request at a
time with a pause between requests.
"""
from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

BASE_URL = "https://prices.runescape.wiki/api/v1/osrs"
USER_AGENT = ("osrs-flipper-backtest/0.1 - offline walk-forward backtest - "
              "https://github.com/snobistisch/osrs-flipper")
STEP_SECONDS = {"5m": 300, "1h": 3600}
DEFAULT_PAUSE = 0.35            # seconds between requests
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class FetchError(Exception):
    """A bucket could not be downloaded."""


def bucket_path(data_dir: Path, timestep: str, start: int) -> Path:
    return Path(data_dir) / "raw" / timestep / "{}.json.gz".format(int(start))


def bucket_starts(timestep: str, begin: int, end: int) -> List[int]:
    """Bucket start times covering [begin, end), aligned to the step."""
    step = STEP_SECONDS[timestep]
    first = -(-int(begin) // step) * step
    return list(range(first, int(end), step))


def _http_get(url: str, timeout: float = 20.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last: Optional[Exception] = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in (429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, OSError) as exc:
            last = exc
        time.sleep(1.5 * (2 ** attempt))
    raise FetchError("GET {} failed: {}".format(url, last))


def fetch_bucket(timestep: str, start: int,
                 http_get: Callable[[str], bytes] = _http_get) -> dict:
    """One all-item bucket. Raises FetchError on a malformed response."""
    body = http_get("{}/{}?timestamp={}".format(BASE_URL, timestep, int(start)))
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise FetchError("bucket {} {}: invalid JSON".format(timestep, start)) from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise FetchError("bucket {} {}: no data object".format(timestep, start))
    reported = payload.get("timestamp")
    if reported is not None and int(reported) != int(start):
        # The API answers an unknown or future bucket with a different one.
        # Storing it under the requested key would shift prices in time.
        raise FetchError("bucket {} {}: API returned bucket {}".format(
            timestep, start, reported))
    return {"timestamp": int(start), "data": data}


def download(timestep: str, begin: int, end: int,
             data_dir: Path = DATA_DIR, pause: float = DEFAULT_PAUSE,
             http_get: Callable[[str], bytes] = _http_get,
             progress: Optional[Callable[[str], None]] = None,
             newest_first: bool = True) -> Dict[str, int]:
    """Fetch every missing bucket in [begin, end). Returns counts."""
    starts: Iterable[int] = bucket_starts(timestep, begin, end)
    if newest_first:
        starts = reversed(list(starts))
    counts = {"cached": 0, "fetched": 0, "failed": 0}
    for index, start in enumerate(starts):
        path = bucket_path(data_dir, timestep, start)
        if path.exists():
            counts["cached"] += 1
            continue
        try:
            payload = fetch_bucket(timestep, start, http_get)
        except FetchError as exc:
            counts["failed"] += 1
            if progress:
                progress("FAILED {}".format(exc))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        with gzip.open(temporary, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
        temporary.replace(path)
        counts["fetched"] += 1
        if progress and counts["fetched"] % 200 == 0:
            progress("{} {}: {} fetched, {} cached, {} failed".format(
                timestep, time.strftime("%Y-%m-%d %H:%M", time.gmtime(start)),
                counts["fetched"], counts["cached"], counts["failed"]))
        time.sleep(max(0.0, pause))
    return counts


def fetch_mapping(data_dir: Path = DATA_DIR,
                  http_get: Callable[[str], bytes] = _http_get) -> list:
    """Item metadata (buy limits, members flag, alch value), cached once.

    /mapping has no history: today's limits are applied to past buckets. A
    buy limit changed inside the window would be mis-stated; that is a stated
    limitation, not something this file can repair.
    """
    path = Path(data_dir) / "raw" / "mapping.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    raw = json.loads(http_get(BASE_URL + "/mapping"))
    if not isinstance(raw, list):
        raise FetchError("/mapping: expected a list")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw), encoding="utf-8")
    return raw
