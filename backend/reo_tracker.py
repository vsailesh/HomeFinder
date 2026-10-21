"""
REO inventory tracker — persistent history of Freddie Mac HomeSteps listings.

HomeSteps REO inventory is thin and rotates weekly (a metro can show a
dozen listings one week and zero the next). On-demand search only sees
what exists right now; this module sweeps all served metros on a
schedule, records every listing ever sighted in SQLite, and reports
what is new or price-cut so inventory that appeared and vanished is
not lost.

Storage is a local SQLite file (REO_DB_PATH, default reo_history.db
next to this module). On hosts with ephemeral disks (Render free
tier) the file wipes on deploy — the schema recreates itself and the
next sweep rebuilds current inventory; first_seen dates are
best-effort after a reset.

Sweeps run either lazily at app startup (maybe_sweep_on_startup) or
via the protected POST /api/reo/sweep endpoint (GitHub Actions cron).
Both are idempotent within _MIN_SWEEP_INTERVAL.
"""
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from data_pipeline import MARKET_DATA
from homesteps_provider import fetch_homesteps_properties
from models import Property

logger = logging.getLogger(__name__)

_DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "reo_history.db")

_MIN_SWEEP_INTERVAL = 3600        # dedupe cron + manual + startup overlaps
_STARTUP_FRESH_SECONDS = 6 * 3600  # startup sweep skip threshold
_METRO_PAUSE_SECONDS = 1.0        # politeness gap between metro searches
# fetch_homesteps_properties returns [] both when a metro is genuinely
# empty and when the fetch failed — deactivate only after consecutive
# misses so one flaky day can't wipe a metro's active inventory.
_DEACTIVATE_AFTER_MISSES = 2

_sweep_lock = threading.Lock()    # non-blocking; serializes sweeps

_SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
  id TEXT PRIMARY KEY,
  address TEXT NOT NULL,
  city TEXT NOT NULL,
  state TEXT NOT NULL,
  zip_code TEXT,
  latitude REAL,
  longitude REAL,
  list_price REAL NOT NULL,
  bedrooms INTEGER,
  bathrooms REAL,
  sqft INTEGER,
  property_type TEXT,
  year_built INTEGER,
  url TEXT,
  image_url TEXT,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  prev_price REAL,
  last_price_change TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  miss_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_listings_active ON listings(is_active);
CREATE INDEX IF NOT EXISTS idx_listings_city ON listings(city);

CREATE TABLE IF NOT EXISTS price_history (
  listing_id TEXT NOT NULL,
  price REAL NOT NULL,
  seen_at TEXT NOT NULL,
  PRIMARY KEY (listing_id, seen_at)
);

CREATE TABLE IF NOT EXISTS sweeps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  metros_done INTEGER DEFAULT 0,
  listings_seen INTEGER DEFAULT 0,
  new_listings INTEGER DEFAULT 0,
  price_changes INTEGER DEFAULT 0,
  deactivated INTEGER DEFAULT 0,
  detail TEXT
);
"""


def _db_path() -> str:
    return os.environ.get("REO_DB_PATH", _DEFAULT_DB)


def _connect() -> sqlite3.Connection:
    """Per-call connection — never shared across threads."""
    conn = sqlite3.connect(_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_seconds(iso: Optional[str]) -> Optional[float]:
    if not iso:
        return None
    try:
        ts = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds()


def _ensure_schema() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def last_sweep_info() -> Optional[Dict]:
    """Most recent sweeps row: the running one, else the latest finished."""
    _ensure_schema()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM sweeps ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    info = dict(row)
    if info.get("detail"):
        try:
            info["detail"] = json.loads(info["detail"])
        except json.JSONDecodeError:
            pass
    return info


def run_sweep(force: bool = False,
              fetcher: Optional[Callable] = None) -> Dict:
    """Sweep every MARKET_DATA metro and upsert listings into history.

    Returns a summary dict; concurrent calls skip, and non-forced calls
    within _MIN_SWEEP_INTERVAL of the last one skip too. Per-metro
    fetch failures surface as empty results (the provider swallows
    network errors) — only store errors propagate.
    """
    if not _sweep_lock.acquire(blocking=False):
        return {"status": "skipped", "reason": "already_running",
                "last_sweep": last_sweep_info()}
    try:
        if not force:
            last = last_sweep_info()
            if last and last.get("status") == "ok" and last.get("finished_at"):
                age = _age_seconds(last["finished_at"])
                if age is not None and age < _MIN_SWEEP_INTERVAL:
                    return {"status": "skipped", "reason": "recent_sweep",
                            "last_sweep": last}
        return _sweep_locked(force=force, fetcher=fetcher)
    finally:
        _sweep_lock.release()


def _sweep_locked(force: bool, fetcher: Optional[Callable]) -> Dict:
    if fetcher is None:
        fetcher = fetch_homesteps_properties
    started = _now()
    _ensure_schema()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO sweeps (started_at, status) VALUES (?, 'running')",
            (started,))
        sweep_id = cur.lastrowid

    seen: Dict[str, Property] = {}
    per_metro = {}
    try:
        for i, (city, meta) in enumerate(MARKET_DATA.items()):
            if i:
                time.sleep(_METRO_PAUSE_SECONDS)
            # Positional (city, state) only — conftest stubs this
            # signature without max_results.
            props = fetcher(city, meta["state"])
            per_metro[city] = len(props)
            for prop in props:
                seen[prop.id] = prop  # dedupe across metros
            logger.info("REO sweep %s: %d listings", city, len(props))

        counts = _upsert_seen(seen)
        deactivated = _deactivate_absent(seen_ids=list(seen.keys()))

        finished = _now()
        with _connect() as conn:
            conn.execute(
                """UPDATE sweeps SET finished_at=?, status='ok',
                   metros_done=?, listings_seen=?, new_listings=?,
                   price_changes=?, deactivated=?, detail=?
                   WHERE id=?""",
                (finished, len(MARKET_DATA), len(seen), counts["new"],
                 counts["price_changes"], deactivated,
                 json.dumps(per_metro), sweep_id))
        with _connect() as conn:
            active_now = conn.execute(
                "SELECT COUNT(*) FROM listings WHERE is_active=1"
            ).fetchone()[0]
        return {"status": "ok", "started_at": started, "finished_at": finished,
                "metros_done": len(MARKET_DATA), "listings_seen": len(seen),
                "new_listings": counts["new"],
                "price_changes": counts["price_changes"],
                "deactivated": deactivated, "active_now": active_now,
                "per_metro": per_metro}
    except Exception as e:
        logger.exception("REO sweep failed")
        with _connect() as conn:
            conn.execute(
                "UPDATE sweeps SET finished_at=?, status='error', detail=? "
                "WHERE id=?",
                (_now(), json.dumps({"error": str(e)}), sweep_id))
        raise


def _upsert_seen(seen: Dict[str, Property]) -> Dict[str, int]:
    """Insert new listings / refresh sightings / record price changes."""
    now = _now()
    new_count = price_changes = 0
    with _connect() as conn:
        for prop in seen.values():
            row = conn.execute(
                "SELECT list_price, first_seen FROM listings WHERE id=?",
                (prop.id,)).fetchone()
            if row is None:
                conn.execute(
                    """INSERT INTO listings (id, address, city, state,
                       zip_code, latitude, longitude, list_price, bedrooms,
                       bathrooms, sqft, property_type, year_built, url,
                       image_url, first_seen, last_seen, is_active,
                       miss_count)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,0)""",
                    (prop.id, prop.address, prop.city, prop.state,
                     prop.zip_code, prop.latitude, prop.longitude,
                     prop.list_price, prop.bedrooms, prop.bathrooms,
                     prop.sqft, prop.property_type.value, prop.year_built,
                     prop.url, prop.image_url, now, now))
                conn.execute(
                    "INSERT OR IGNORE INTO price_history "
                    "(listing_id, price, seen_at) VALUES (?,?,?)",
                    (prop.id, prop.list_price, now))
                new_count += 1
            else:
                price_changed = row["list_price"] != prop.list_price
                conn.execute(
                    """UPDATE listings SET address=?, city=?, state=?,
                       zip_code=?, latitude=?, longitude=?, list_price=?,
                       bedrooms=?, bathrooms=?, sqft=?, property_type=?,
                       year_built=?, url=?, image_url=?, last_seen=?,
                       is_active=1, miss_count=0,
                       prev_price=CASE WHEN ? THEN ? ELSE prev_price END,
                       last_price_change=CASE WHEN ? THEN ?
                                          ELSE last_price_change END
                       WHERE id=?""",
                    (prop.address, prop.city, prop.state, prop.zip_code,
                     prop.latitude, prop.longitude, prop.list_price,
                     prop.bedrooms, prop.bathrooms, prop.sqft,
                     prop.property_type.value, prop.year_built, prop.url,
                     prop.image_url, now,
                     price_changed, row["list_price"],
                     price_changed, now, prop.id))
                if price_changed:
                    conn.execute(
                        "INSERT OR IGNORE INTO price_history "
                        "(listing_id, price, seen_at) VALUES (?,?,?)",
                        (prop.id, prop.list_price, now))
                    price_changes += 1
    return {"new": new_count, "price_changes": price_changes}


def _deactivate_absent(seen_ids: List[str]) -> int:
    """Age out listings absent from this sweep (after N consecutive misses)."""
    with _connect() as conn:
        if seen_ids:
            placeholders = ",".join("?" * len(seen_ids))
            conn.execute(
                f"UPDATE listings SET miss_count = miss_count + 1 "
                f"WHERE is_active = 1 AND id NOT IN ({placeholders})",
                seen_ids)
        else:
            conn.execute(
                "UPDATE listings SET miss_count = miss_count + 1 "
                "WHERE is_active = 1")
        cur = conn.execute(
            "UPDATE listings SET is_active = 0 "
            "WHERE is_active = 1 AND miss_count >= ?",
            (_DEACTIVATE_AFTER_MISSES,))
        return cur.rowcount


def _flags(r, days: int) -> Dict:
    """Read-time new/price-cut flags (age out automatically)."""
    first_age = _age_seconds(r["first_seen"])
    change_age = _age_seconds(r["last_price_change"])
    return {
        "is_new": first_age is not None and first_age <= days * 86400,
        "price_cut": (change_age is not None and change_age <= days * 86400
                      and r["prev_price"] is not None
                      and r["list_price"] < r["prev_price"]),
    }


def get_tracker_state(ids: List[str], days: int = 7) -> Dict[str, Dict]:
    """Tracker snapshot for specific listing ids — used to enrich
    /api/search results for HomeSteps deals. Unknown ids absent."""
    if not ids:
        return {}
    _ensure_schema()
    out = {}
    with _connect() as conn:
        for i in range(0, len(ids), 50):  # SQLite param limit
            chunk = ids[i:i + 50]
            rows = conn.execute(
                f"SELECT * FROM listings WHERE id IN "
                f"({','.join('?' * len(chunk))})", chunk).fetchall()
            for r in rows:
                out[r["id"]] = {
                    **_flags(r, days),
                    "first_seen": r["first_seen"],
                    "last_seen": r["last_seen"],
                    "prev_price": r["prev_price"],
                    "price_change_pct": _pct(r["list_price"], r["prev_price"]),
                }
    return out


def get_inventory(city: Optional[str] = None, days: int = 7,
                  include_inactive: bool = False) -> Dict:
    """Report-style snapshot of tracked REO inventory.

    Flags are computed at read time so they age out automatically:
    is_new (first_seen within `days`), price_cut (price dropped with
    last_price_change within `days`). The optional `city` filter
    matches the listing's own city (e.g. "Gwynn Oak"), not the served
    metro key ("Baltimore").
    """
    _ensure_schema()
    where = "" if include_inactive else "WHERE is_active = 1"
    params: list = []
    if city:
        clause = "city = ? COLLATE NOCASE"
        where = f"{('WHERE' if not where else where + ' AND')} {clause}"
        params.append(city)

    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM listings {where} "
            f"ORDER BY last_seen DESC, list_price ASC", params).fetchall()
        totals = conn.execute(
            "SELECT SUM(is_active) AS active, "
            "SUM(1 - is_active) AS inactive FROM listings").fetchone()

    listings = []
    metros = set()
    for r in rows:
        flags = _flags(r, days)
        if r["is_active"]:
            metros.add(f'{r["city"]}, {r["state"]}')
        listings.append({
            "id": r["id"], "address": r["address"], "city": r["city"],
            "state": r["state"], "zip_code": r["zip_code"],
            "latitude": r["latitude"], "longitude": r["longitude"],
            "list_price": r["list_price"], "prev_price": r["prev_price"],
            "last_price_change": r["last_price_change"],
            "price_change_pct": _pct(r["list_price"], r["prev_price"]),
            "first_seen": r["first_seen"], "last_seen": r["last_seen"],
            "is_active": bool(r["is_active"]),
            "is_new": flags["is_new"],
            "price_cut": flags["price_cut"],
            "bedrooms": r["bedrooms"], "bathrooms": r["bathrooms"],
            "sqft": r["sqft"], "sqft_estimated": True,
            "property_type": r["property_type"],
            "year_built": r["year_built"], "url": r["url"],
            "image_url": r["image_url"],
            "source": "homesteps-freddie-mac",
        })

    active = [l for l in listings if l["is_active"]]
    # New/price-cut first, then freshest sighting, then cheapest —
    # multi-pass stable sorts express the mixed asc/desc order.
    listings.sort(key=lambda l: l["list_price"])
    listings.sort(key=lambda l: l["last_seen"], reverse=True)
    listings.sort(key=lambda l: (not l["is_new"], not l["price_cut"]))
    return {
        "generated_at": _now(),
        "window_days": days,
        "last_sweep": last_sweep_info(),
        "summary": {
            "active": totals["active"] or 0,
            "inactive": totals["inactive"] or 0,
            "new": sum(1 for l in active if l["is_new"]),
            "price_cuts": sum(1 for l in active if l["price_cut"]),
            "metros_with_inventory": len(metros),
        },
        "listings": listings,
    }


def _pct(current: Optional[float], prev: Optional[float]) -> Optional[float]:
    if prev is None or prev <= 0 or current is None:
        return None
    return round((current - prev) / prev * 100, 1)


def maybe_sweep_on_startup() -> None:
    """Lifespan hook body — sweep in background unless fresh/disabled.

    Never raises: a failed startup sweep must not take the API down.
    """
    if os.environ.get("REO_SWEEP_ON_STARTUP", "1") == "0":
        return
    try:
        last = last_sweep_info()
        if last and last.get("status") == "ok" and last.get("finished_at"):
            age = _age_seconds(last["finished_at"])
            if age is not None and age < _STARTUP_FRESH_SECONDS:
                logger.info("REO sweep fresh (%.0fs old) — skipping startup "
                            "sweep", age)
                return
        logger.info("Starting background REO sweep on startup")
        result = run_sweep()
        logger.info("Startup REO sweep: %s", result.get("status"))
    except Exception:
        logger.exception("Startup REO sweep failed (non-fatal)")
