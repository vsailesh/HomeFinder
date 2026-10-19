"""REO tracker tests — offline, throwaway SQLite via conftest fixture."""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import main as main_module
import reo_tracker as rt
from models import Property, PropertyType


def _prop(pid="homesteps-x", price=199000.0, city="Chicago", state="IL"):
    return Property(
        id=pid, address="1 Main St", city=city, state=state,
        zip_code="60601", list_price=price, bedrooms=2, bathrooms=1.0,
        sqft=1100, property_type=PropertyType.CONDO,
        url="https://www.homesteps.com/listingdetails/x")


def _fetcher(*props):
    """Fetcher that returns props for Chicago and nothing elsewhere."""
    return lambda city, state: list(props) if city == "Chicago" else []


def _sweep(*props, force=True):
    return rt.run_sweep(force=force, fetcher=_fetcher(*props))


def _row(pid="homesteps-x"):
    with sqlite3.connect(rt._db_path()) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM listings WHERE id=?", (pid,)).fetchone()


def _history_count(pid="homesteps-x"):
    with sqlite3.connect(rt._db_path()) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM price_history WHERE listing_id=?",
            (pid,)).fetchone()[0]


# --- sweep + store ------------------------------------------------------

def test_sweep_inserts_new_listings():
    result = _sweep(_prop(), _prop("homesteps-y", 250000.0))
    assert result["status"] == "ok"
    assert result["new_listings"] == 2
    row = _row()
    assert row["is_active"] == 1
    assert row["first_seen"] == row["last_seen"]
    assert _history_count() == 1


def test_repeat_sweep_same_price_noop():
    _sweep(_prop())
    result = _sweep(_prop())
    assert result["price_changes"] == 0
    assert _history_count() == 1
    row = _row()
    assert row["last_seen"] >= row["first_seen"]
    assert row["miss_count"] == 0


def test_price_cut_detected():
    _sweep(_prop(price=199000.0))
    result = _sweep(_prop(price=179000.0))
    assert result["price_changes"] == 1
    row = _row()
    assert row["prev_price"] == 199000.0
    assert row["list_price"] == 179000.0
    assert _history_count() == 2

    listing = rt.get_inventory()["listings"][0]
    assert listing["price_cut"] is True
    assert listing["price_change_pct"] == -10.1


def test_price_increase_recorded_not_flagged():
    _sweep(_prop(price=199000.0))
    _sweep(_prop(price=219000.0))
    row = _row()
    assert row["prev_price"] == 199000.0  # change recorded
    listing = rt.get_inventory()["listings"][0]
    assert listing["price_cut"] is False  # but not a cut
    assert listing["price_change_pct"] == 10.1


def test_single_miss_keeps_active():
    _sweep(_prop())
    result = _sweep()  # empty sweep — one miss
    assert result["deactivated"] == 0
    row = _row()
    assert row["is_active"] == 1
    assert row["miss_count"] == 1


def test_two_misses_deactivate():
    _sweep(_prop())
    _sweep()
    result = _sweep()
    assert result["deactivated"] == 1
    assert _row()["is_active"] == 0
    assert rt.get_inventory()["listings"] == []
    inactive = rt.get_inventory(include_inactive=True)["listings"]
    assert len(inactive) == 1


def test_reactivation_preserves_first_seen():
    _sweep(_prop())
    first = _row()["first_seen"]
    _sweep()
    _sweep()  # deactivated
    _sweep(_prop())  # returns
    row = _row()
    assert row["is_active"] == 1
    assert row["first_seen"] == first
    listing = rt.get_inventory()["listings"][0]
    assert listing["is_new"] is True  # first_seen still recent in-test


def test_dedupe_across_metros():
    # Provider state-fallback can return the same listing for two
    # metro queries — the sweep must count it once.
    same = _prop()
    both = lambda city, state: [same] if city in ("Chicago", "Detroit") else []
    result = rt.run_sweep(force=True, fetcher=both)
    assert result["listings_seen"] == 1
    assert result["new_listings"] == 1


def test_sweep_interval_skip():
    _sweep(_prop())
    result = rt.run_sweep()  # no force, last sweep just finished
    assert result["status"] == "skipped"
    assert result["reason"] == "recent_sweep"


def test_already_running_skips():
    assert rt._sweep_lock.acquire(blocking=False)
    try:
        result = rt.run_sweep(force=True)
        assert result["status"] == "skipped"
        assert result["reason"] == "already_running"
    finally:
        rt._sweep_lock.release()


# --- inventory flags ----------------------------------------------------

def test_is_new_window():
    _sweep(_prop())
    eight_days_ago = (datetime.now(timezone.utc)
                      - timedelta(days=8)).isoformat()
    with sqlite3.connect(rt._db_path()) as conn:
        conn.execute("UPDATE listings SET first_seen=?",
                     (eight_days_ago,))
    listing = rt.get_inventory(days=7)["listings"][0]
    assert listing["is_new"] is False

    three_days_ago = (datetime.now(timezone.utc)
                      - timedelta(days=3)).isoformat()
    with sqlite3.connect(rt._db_path()) as conn:
        conn.execute("UPDATE listings SET first_seen=?", (three_days_ago,))
    listing = rt.get_inventory(days=7)["listings"][0]
    assert listing["is_new"] is True


def test_city_filter_matches_listing_city():
    suburb = _prop(pid="homesteps-sub", city="Gwynn Oak", state="MD")
    _sweep(suburb, _prop())
    listing_cities = [l["city"]
                      for l in rt.get_inventory(city="Gwynn Oak")["listings"]]
    assert listing_cities == ["Gwynn Oak"]


def test_inventory_shape():
    _sweep(_prop(), _prop("homesteps-y", 250000.0))
    inv = rt.get_inventory()
    assert set(inv) == {"generated_at", "window_days", "last_sweep",
                        "summary", "listings"}
    assert inv["last_sweep"]["status"] == "ok"
    assert inv["summary"]["active"] == 2
    assert inv["summary"]["new"] == 2
    assert inv["summary"]["metros_with_inventory"] == 1
    first = inv["listings"][0]
    assert first["source"] == "homesteps-freddie-mac"
    assert first["sqft_estimated"] is True
    # new listings sort ahead
    assert inv["listings"][0]["is_new"]


def test_inventory_null_last_sweep_before_any_sweep():
    inv = rt.get_inventory()
    assert inv["last_sweep"] is None
    assert inv["summary"]["active"] == 0
    assert inv["listings"] == []


# --- startup hook -------------------------------------------------------

def test_startup_hook_skips_when_fresh(monkeypatch):
    _sweep(_prop())  # fresh ok sweep on record (before patching run_sweep)
    called = []
    monkeypatch.setattr(rt, "run_sweep",
                        lambda *a, **k: called.append(1) or {})
    monkeypatch.setenv("REO_SWEEP_ON_STARTUP", "1")  # conftest disables it
    rt.maybe_sweep_on_startup()
    assert called == []


def test_startup_hook_sweeps_when_stale(monkeypatch):
    called = []
    monkeypatch.setattr(
        rt, "run_sweep",
        lambda *a, **k: called.append(1) or {"status": "ok"})
    monkeypatch.setenv("REO_SWEEP_ON_STARTUP", "1")
    rt.maybe_sweep_on_startup()  # no sweep on record
    assert called


def test_startup_hook_never_raises(monkeypatch):
    def boom():
        raise RuntimeError("sweep blew up")
    monkeypatch.setattr(rt, "run_sweep", boom)
    rt.maybe_sweep_on_startup()  # must not raise


def test_startup_hook_env_kill_switch(monkeypatch):
    called = []
    monkeypatch.setattr(
        rt, "run_sweep", lambda: called.append(1) or {"status": "ok"})
    monkeypatch.setenv("REO_SWEEP_ON_STARTUP", "0")
    rt.maybe_sweep_on_startup()
    assert called == []


# --- endpoints ----------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SWEEP_TOKEN", "devtoken")
    return TestClient(main_module.app)


def test_sweep_endpoint_403_without_token_header(client):
    r = client.post("/api/reo/sweep")
    assert r.status_code == 403
    r = client.post("/api/reo/sweep", headers={"X-Sweep-Token": "wrong"})
    assert r.status_code == 403


def test_sweep_endpoint_403_when_env_unset(client, monkeypatch):
    monkeypatch.delenv("SWEEP_TOKEN", raising=False)
    r = client.post("/api/reo/sweep",
                    headers={"X-Sweep-Token": "devtoken"})
    assert r.status_code == 403


def test_sweep_endpoint_ok_with_token(client, monkeypatch):
    monkeypatch.setattr(rt, "fetch_homesteps_properties",
                        lambda city, state, zip_code=None: [])
    r = client.post("/api/reo/sweep?force=true",
                    headers={"X-Sweep-Token": "devtoken"})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_inventory_endpoint(client):
    r = client.get("/api/reo/inventory")
    assert r.status_code == 200
    body = r.json()
    assert body["last_sweep"] is None
    assert body["summary"]["active"] == 0


def test_inventory_endpoint_with_data(client, monkeypatch):
    monkeypatch.setattr(
        rt, "fetch_homesteps_properties",
        lambda city, state, zip_code=None:
            [_prop()] if city == "Chicago" else [])
    client.post("/api/reo/sweep?force=true",
                headers={"X-Sweep-Token": "devtoken"})
    body = client.get("/api/reo/inventory").json()
    assert body["summary"]["active"] == 1
    assert body["last_sweep"]["status"] == "ok"
