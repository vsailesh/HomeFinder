"""Hold-projection tests — offline via conftest fixture baselines
(Baltimore metro present, conftest pins the rate at 6.5)."""
import pytest
from fastapi.testclient import TestClient

import main as main_module
import projection
from projection import build_projection, _balance_after

BALT = {"city": "Baltimore", "state": "MD", "zip_code": "21201"}
NO_METRO = {"city": "Nowhere", "state": "ZZ"}


@pytest.fixture(autouse=True)
def offline_projection(monkeypatch):
    """conftest stubs optimizer's ZIP-rent reference; projection
    imported its own — stub that too (keeps these tests offline;
    ZIP-rent preference has its own dedicated test below)."""
    monkeypatch.setattr(projection, "get_zip_rent", lambda z: None)


class TestBalanceAfter:
    def test_full_term_pays_off(self):
        assert _balance_after(300000, 0.06 / 12, 360, 360) == 0.0

    def test_zero_rate_linear(self):
        # Interest-free: balance falls linearly.
        assert abs(_balance_after(120000, 0.0, 120, 60) - 60000) < 1e-6

    def test_month_one_barely_moves(self):
        bal = _balance_after(300000, 0.06 / 12, 360, 1)
        assert 299000 < bal < 300000


class TestBuildProjection:
    def test_shape_and_years(self):
        p = build_projection(list_price=300000, **BALT)
        assert [r["year"] for r in p["rows"]] == list(range(11))
        a = p["assumptions"]
        assert a["appreciation_source"] == "zillow-research-metro"
        assert a["rent_source"] == "zillow-zori-metro"
        assert a["rent"] == 1820  # Baltimore metro ZORI fixture
        assert a["rate_pct"] == 6.5  # conftest-pinned

    def test_equity_monotonic_and_beats_down(self):
        p = build_projection(list_price=300000, **BALT)
        equity = [r["equity"] for r in p["rows"]]
        assert equity == sorted(equity)
        # Fixture Baltimore happens to decline slightly (−0.9%/yr) —
        # amortization alone still builds equity past the down payment.
        assert p["rows"][-1]["equity"] > 0.20 * 300000

    def test_amortization_spot_check(self):
        # Equity = value − balance; verify the year-10 balance against
        # the closed-form amortization at the pinned rate.
        p = build_projection(list_price=300000, estimated_value=300000,
                             **BALT)
        mr = (p["assumptions"]["rate_pct"] / 100) / 12
        loan = 300000 * 0.8
        growth = (1 + mr) ** 360
        elapsed = (1 + mr) ** 120
        expected_balance = loan * (growth - elapsed) / (growth - 1)
        row10 = p["rows"][10]
        assert abs(row10["equity"]
                   - (row10["property_value"] - expected_balance)) < 2

    def test_cashflow_accumulates(self):
        p = build_projection(list_price=300000, **BALT)
        rows = p["rows"]
        assert rows[0]["cum_cf"] == 0
        for prev, cur in zip(rows, rows[1:]):
            assert cur["cum_cf"] == pytest.approx(
                prev["cum_cf"] + 12 * cur["net_cf_mo"], abs=8)

    def test_net_position_accounts_for_selling_cost(self):
        p = build_projection(list_price=300000, **BALT)
        r = p["rows"][7]
        assert r["net_position"] == pytest.approx(
            r["equity"] + r["cum_cf"] - 0.06 * r["property_value"], abs=2)

    def test_no_metro_falls_back(self):
        p = build_projection(list_price=200000, **NO_METRO)
        a = p["assumptions"]
        assert a["appreciation"] == 0.035
        assert a["appreciation_source"] == "national-default"
        # Nowhere has no metro rent either → cashflow columns null,
        # carry/equity still real.
        assert a["rent"] is None
        assert a["rent_source"] is None
        assert all(r["rent_mo"] is None and r["cum_cf"] is None
                   and r["net_cf_mo"] is None for r in p["rows"])
        assert all(r["carry_mo"] > 0 and r["equity"] > 0
                   for r in p["rows"])

    def test_zero_published_tax_is_honored(self):
        # HomeSteps REO publishes real $0 taxes — 0 must not be
        # replaced by the 1.1%-of-list assumption.
        p = build_projection(list_price=300000, annual_tax=0.0, **BALT)
        assert p["assumptions"]["annual_tax"] == 0
        pi = p["assumptions"]["monthly_pi"]
        ins_mo = 300000 * 0.0035 / 12
        assert abs(p["rows"][0]["carry_mo"] - (pi + ins_mo)) < 0.51

    def test_zip_rent_preferred_when_available(self, monkeypatch):
        import projection
        monkeypatch.setattr(projection, "get_zip_rent", lambda z: 2500.0)
        p = build_projection(list_price=300000, **BALT)
        assert p["assumptions"]["rent_source"] == "zillow-zori-zip"
        assert p["assumptions"]["rent"] == 2500.0

    def test_rent_grows_after_year_one(self):
        p = build_projection(list_price=300000, **BALT)
        rows = p["rows"]
        assert rows[1]["rent_mo"] == rows[0]["rent_mo"]
        assert rows[2]["rent_mo"] > rows[1]["rent_mo"]
        assert rows[10]["rent_mo"] == pytest.approx(
            rows[1]["rent_mo"] * 1.03 ** 9, rel=0.01)


@pytest.fixture
def client():
    return TestClient(main_module.app)


class TestProjectionEndpoint:
    def test_ok(self, client):
        r = client.post("/api/property/projection", json={
            "list_price": 300000, "city": "Baltimore", "state": "MD",
        })
        assert r.status_code == 200
        body = r.json()
        assert len(body["rows"]) == 11
        assert body["assumptions"]["rate_pct"] == 6.5

    def test_missing_price_422(self, client):
        r = client.post("/api/property/projection", json={"city": "x"})
        assert r.status_code == 422

    def test_nonpositive_price_422(self, client):
        r = client.post("/api/property/projection",
                        json={"list_price": -5})
        assert r.status_code == 422
