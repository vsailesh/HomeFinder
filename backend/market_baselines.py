"""
Real market baselines from Zillow Research public data.

Zillow publishes free CSVs on an open S3 bucket
(files.zillowstatic.com/research/public_csvs/...). Two of them replace
hardcoded heuristics in this app:

- zhvi/   Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv
          Typical home value per metro, monthly time series ->
          trailing 12-month appreciation (replaces the flat 3.5%
          national assumption in the 5yr ROI projection).
- mlp/    Metro_mlp_uc_sfrcondo_sm_month.csv
          Median list price per metro -> real baseline for context.

Everything here is failure-safe: if Zillow is unreachable the callers
fall back to their defaults and searches keep working.
"""
import csv
import io
import logging
import threading
import time
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

ZHVI_URL = ("https://files.zillowstatic.com/research/public_csvs/zhvi/"
            "Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv")
MLP_URL = ("https://files.zillowstatic.com/research/public_csvs/mlp/"
           "Metro_mlp_uc_sfrcondo_sm_month.csv")

_BASE_URLS = {"zhvi": ZHVI_URL, "mlp": MLP_URL}

_CACHE_TTL_SECONDS = 24 * 60 * 60  # Zillow publishes monthly; refresh daily
_HTTP_TIMEOUT = 60

# Cities we serve that sit inside a differently-named metro. Zillow's
# metro names (e.g. "Washington, DC") don't list them separately, so
# map them explicitly — keyed (city, state) casefolded.
CITY_METRO_OVERRIDES = {
    ("bethesda", "md"): "Washington, DC",
    ("silver spring", "md"): "Washington, DC",
    ("rockville", "md"): "Washington, DC",
    ("bowie", "md"): "Washington, DC",
    ("frederick", "md"): "Washington, DC",
    ("columbia", "md"): "Baltimore, MD",
    ("annapolis", "md"): "Baltimore, MD",
}

_lock = threading.Lock()
_cache: Optional[Dict] = None
_cache_ts: float = 0.0


def _parse_series_csv(text: str) -> Dict[str, Dict]:
    """Parse a Zillow Research time-series CSV into
    {region_key: {"latest": float, "year_ago": float|None, "as_of": str}}.

    region_key is the RegionName (metros include the state, e.g.
    "Baltimore, MD"). Date columns are everything matching YYYY-MM-DD;
    the last non-empty one is `latest`, and the column closest to 12
    months earlier is `year_ago`.
    """
    reader = csv.DictReader(io.StringIO(text))
    out: Dict[str, Dict] = {}
    for row in reader:
        region = (row.get("RegionName") or "").strip()
        if not region or (row.get("RegionType") or "") not in ("metro", "msa"):
            continue
        dated = sorted(
            (k, v) for k, v in row.items()
            if len(k or "") == 10 and (k or "")[:4].isdigit()
            and (k or "-")[4] == "-" and v not in (None, "", "NaN")
        )
        if not dated:
            continue
        latest_col, latest_val = dated[-1]
        # Column closest to 12 months before the latest (at least 9
        # months back, so a sparse series still yields a sensible rate).
        target_year = int(latest_col[:4]) - 1
        year_ago = None
        for col, val in dated:
            if int(col[:4]) <= target_year:
                year_ago = float(val)
        out[region] = {
            "latest": float(latest_val),
            "year_ago": year_ago,
            "as_of": latest_col,
        }
    return out


def _fetch_series() -> Dict[str, Dict[str, Dict]]:
    """Download and parse both CSVs. Raises on network/HTTP failure."""
    series: Dict[str, Dict[str, Dict]] = {}
    for name, url in _BASE_URLS.items():
        resp = requests.get(url, timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        series[name] = _parse_series_csv(resp.text)
        logger.info("Loaded %d metro rows from %s", len(series[name]), name)
    return series


def _get_baselines(force_refresh: bool = False) -> Dict:
    """Cached access to the parsed Zillow series."""
    global _cache, _cache_ts
    with _lock:
        now = time.time()
        if (not force_refresh and _cache is not None
                and now - _cache_ts < _CACHE_TTL_SECONDS):
            return _cache
        try:
            fetched = _fetch_series()
            zhvi, mlp = fetched["zhvi"], fetched["mlp"]
        except Exception:
            logger.exception("Zillow Research baseline fetch failed")
            if _cache is not None:
                return _cache  # serve stale rather than nothing
            return {"metros": {}, "source": "zillow-research", "ok": False}

        metros = {}
        for region, vals in zhvi.items():
            entry = {
                "typical_value": round(vals["latest"]),
                "as_of": vals["as_of"],
            }
            if vals["year_ago"]:
                entry["appreciation_1y"] = round(
                    vals["latest"] / vals["year_ago"] - 1, 4)
            if region in mlp:
                entry["median_list_price"] = round(mlp[region]["latest"])
            metros[region] = entry
        _cache = {
            "metros": metros,
            "source": "zillow-research",
            "ok": True,
        }
        _cache_ts = now
        return _cache


def _lookup_metro(city: Optional[str], state: Optional[str]) -> Optional[Dict]:
    """Find the baseline entry for the metro matching a city/state
    search. Exact "City, ST" first, then a same-state metro whose name
    starts with the city, then (only without a state) any metro
    starting with the city."""
    if not city:
        return None
    city = city.strip().casefold()
    state = (state or "").strip().casefold()
    metros = _get_baselines()["metros"]

    override = CITY_METRO_OVERRIDES.get((city, state))
    if override:
        entry = next(
            (v for k, v in metros.items()
             if k.casefold() == override.casefold()), None)
        if entry:
            return entry

    exact = f"{city}, {state}" if state else None
    entry = next(
        (v for k, v in metros.items() if k.casefold() == exact), None)
    if entry is None and state:
        entry = next(
            (v for k, v in metros.items()
             if k.casefold().startswith(city + ",")
             and k.casefold().endswith(", " + state)), None)
    if entry is None and not state:
        entry = next(
            (v for k, v in metros.items()
             if k.casefold().startswith(city + ",")), None)
    return entry


def get_appreciation(city: Optional[str],
                     state: Optional[str]) -> Optional[float]:
    """Trailing-12mo home value growth for the metro matching the
    search location, or None when no match / data unavailable."""
    entry = _lookup_metro(city, state)
    if not entry:
        return None
    return entry.get("appreciation_1y")


def get_metro_baseline(city: Optional[str],
                       state: Optional[str]) -> Optional[Dict]:
    """Full baseline entry (typical value, appreciation, median list
    price, as-of date) for the matching metro, or None."""
    return _lookup_metro(city, state)


def get_baselines_snapshot() -> Dict:
    """Public snapshot for the API (region stats only, no raw series)."""
    data = _get_baselines()
    return {
        "source": data["source"],
        "ok": data["ok"],
        "metro_count": len(data["metros"]),
        "metros": data["metros"],
    }
