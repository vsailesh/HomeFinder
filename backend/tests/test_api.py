"""API endpoint tests via FastAPI TestClient (mock data — no API key)."""
import pytest
from fastapi.testclient import TestClient

import main as main_module

@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    return TestClient(main_module.app)


class TestHealth:
    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert r.json()["status"] == "online"

    def test_status_tz_aware_timestamp(self, client):
        r = client.get("/api/status")
        assert r.status_code == 200
        # timezone-aware ISO — no naive utcnow()
        assert r.json()["timestamp"].endswith("+00:00")

    def test_cities(self, client):
        r = client.get("/api/cities")
        assert r.status_code == 200
        cities = r.json()["cities"]
        assert len(cities) > 0

    def test_cities_joins_metro_trend(self, client):
        """Baltimore matches its metro directly; Bethesda routes
        through the override to the Washington, DC fixture row."""
        cities = client.get("/api/cities").json()["cities"]
        balt = next(c for c in cities if c["name"] == "Baltimore")
        assert balt["metro_appreciation_1y"] == round(
            311200 / 314000 - 1, 4)
        assert balt["metro_median_list_price"] == 372000
        assert balt["metro_as_of"] == "2026-08-31"
        bethesda = next(c for c in cities if c["name"] == "Bethesda")
        assert bethesda["metro_appreciation_1y"] == round(
            624000 / 608000 - 1, 4)  # Washington override
        assert bethesda["metro_median_list_price"] == 642000


class TestSearch:
    def test_search_returns_deals(self, client):
        r = client.get("/api/search",
                       params={"city": "Bethesda", "state": "MD"})
        assert r.status_code == 200
        body = r.json()
        assert body["total_results"] > 0
        for deal in body["deals"]:
            assert 0 <= deal["deal_score"] <= 100
            assert deal["valuation"]["estimated_value"] > 0

    def test_market_stats_no_fabricated_trends(self, client):
        r = client.get("/api/search",
                       params={"city": "Bethesda", "state": "MD"})
        stats = r.json()["market_stats"]
        assert "price_trend_30d" not in stats
        assert "inventory_change_30d" not in stats

    def test_search_deterministic_across_calls(self, client):
        """Same specs twice -> same stats (old hash() impl was unstable)."""
        p = {"city": "Columbia", "state": "MD"}
        s1 = client.get("/api/search", params=p).json()["market_stats"]
        s2 = client.get("/api/search", params=p).json()["market_stats"]
        assert s1["area_name"] == s2["area_name"]

    def test_search_pagination_params(self, client):
        p = {"city": "Columbia", "state": "MD", "page": 1, "page_size": 5}
        body = client.get("/api/search", params=p).json()
        assert len(body["deals"]) == 5
        assert body["page"] == 1
        assert body["page_size"] == 5
        assert body["total_results"] > 5
        assert body["total_pages"] == -(-body["total_results"] // 5)

    def test_search_pagination_rejects_bad_page(self, client):
        r = client.get("/api/search",
                       params={"city": "Columbia", "page": 0})
        assert r.status_code == 422
        r = client.get("/api/search",
                       params={"city": "Columbia", "page_size": 500})
        assert r.status_code == 422


class TestPropertyValuationEndpoint:
    def test_registered_property_found(self, client):
        search = client.get("/api/search",
                            params={"city": "Bethesda", "state": "MD"}).json()
        pid = search["deals"][0]["property"]["id"]
        r = client.get(f"/api/property/{pid}/valuation")
        assert r.status_code == 200
        assert r.json()["property"]["id"] == pid
        assert r.json()["valuation"]["estimated_value"] > 0

    def test_unknown_property_404(self, client):
        r = client.get("/api/property/does-not-exist/valuation")
        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()


class TestLoanEndpoints:
    def test_rate(self, client):
        r = client.get("/api/loan/rate")
        assert r.status_code == 200
        body = r.json()
        assert body["base_rate"] > 0
        assert body["source"] in ("fred", "cache", "fallback")

    def test_quote(self, client):
        r = client.post("/api/loan/quote", json={
            "home_price": 500000, "down_payment": 100000,
            "annual_income": 150000, "monthly_debts": 500,
            "credit_score": 750,
            "annual_property_tax": 6000, "annual_home_insurance": 1500,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["eligible"] is True
        assert body["monthly_pi"] > 0

    def test_quote_validation_error(self, client):
        r = client.post("/api/loan/quote", json={
            "home_price": -5, "down_payment": 0,
            "annual_income": 0, "credit_score": 700,
        })
        assert r.status_code == 422
