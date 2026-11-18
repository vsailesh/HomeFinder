"""Investor heatmap tests — offline via the conftest fixture
baselines (Baltimore, MD and Washington, DC are the metros the
fixture data can resolve)."""
import pytest
from fastapi.testclient import TestClient

import heatmap as hm
import main as main_module
import optimizer as opt
import reo_tracker as rt
from models import Property, PropertyType


def _reo_prop(pid="reo-balt", price=150000.0):
    return Property(
        id=pid, address="1 Main St", city="Baltimore", state="MD",
        zip_code="21201", list_price=price, bedrooms=2, bathrooms=1.0,
        sqft=1100, property_type=PropertyType.CONDO,
        url="https://www.homesteps.com/listingdetails/x")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    return TestClient(main_module.app)


def test_metros_dedupe_and_carry_math():
    rows = hm.build_heatmap()["rows"]
    metros = [r["metro"] for r in rows]
    # Suburbs collapse: Baltimore + Columbia + Annapolis -> one row.
    assert metros.count("Baltimore, MD") == 1
    balt = next(r for r in rows if r["metro"] == "Baltimore, MD")
    assert "Columbia" in balt["cities"] and "Annapolis" in balt["cities"]
    # Median list beats typical value as the price basis.
    m = balt["monthly"]
    assert m["price_basis"] == balt["median_list_price"]
    # Payment/carry recompute from the shared constants — the heatmap
    # can never drift from what a deal card would show.
    assert m["payment"] == opt._calculate_monthly_payment(
        m["price_basis"], rate=6.5)
    assert m["tax"] == round(m["price_basis"] * opt.TAX_RATE_DEFAULT / 12)
    assert m["insurance"] == round(
        m["price_basis"] * opt.INSURANCE_RATE / 12)
    assert m["carry"] == round(m["payment"] + m["tax"] + m["insurance"])
    assert m["cashflow"] == balt["typical_rent"] - m["carry"]
    assert m["rent_coverage"] == round(
        balt["typical_rent"] / m["payment"], 2)


def test_missing_rent_sorts_last_with_null_cashflow():
    rows = hm.build_heatmap()["rows"]
    dc = next(r for r in rows if r["metro"] == "Washington, DC")
    # Fixture ZORI publishes no DC rent: unknown, not zero — cashflow
    # and coverage stay null and the row sinks below every valued one.
    assert dc["typical_rent"] is None
    assert dc["monthly"]["cashflow"] is None
    assert dc["monthly"]["rent_coverage"] is None
    assert rows[-1] is dc


def test_rows_ordered_best_cashflow_first():
    rows = hm.build_heatmap()["rows"]
    valued = [r["monthly"]["cashflow"] for r in rows
              if r["monthly"]["cashflow"] is not None]
    assert valued == sorted(valued, reverse=True)


def test_reo_count_joins_and_tracker_failure_never_breaks():
    rt.run_sweep(force=True, fetcher=lambda city, state: (
        [_reo_prop()] if city == "Baltimore" else []))
    balt = next(r for r in hm.build_heatmap()["rows"]
                if r["metro"] == "Baltimore, MD")
    assert balt["reo_active"] == 1

    # Tracker blowup zeroes the column, never the heatmap.
    orig = rt.get_inventory

    def boom(**kwargs):
        raise RuntimeError("db gone")

    rt.get_inventory = boom
    try:
        balt = next(r for r in hm.build_heatmap()["rows"]
                    if r["metro"] == "Baltimore, MD")
        assert balt["reo_active"] == 0
    finally:
        rt.get_inventory = orig


def test_endpoint_shape(client):
    r = client.get("/api/market/heatmap")
    assert r.status_code == 200
    body = r.json()
    assert body["rate"]["rate"] == 6.5
    assert body["assumptions"]["tax_rate"] == opt.TAX_RATE_DEFAULT
    assert len(body["rows"]) >= 2  # Baltimore + DC from the fixtures
