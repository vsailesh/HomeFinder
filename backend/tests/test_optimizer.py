"""Optimizer tests — scoring bounds, grades, robustness, rate wiring."""
import pytest
from models import Property, PropertyType, PropertyCondition, SearchSpecs
from optimizer import (
    optimize_search, score_deal, _calculate_monthly_payment,
    _estimate_5yr_roi, _grade_from_score,
)
from valuation_engine import valuate_property


def make_property(**overrides):
    defaults = dict(
        id="p1", address="1 Main St", city="Bethesda", state="MD",
        zip_code="20814", list_price=500000, sqft=2000, bedrooms=3,
        bathrooms=2.0, year_built=2010,
        condition=PropertyCondition.GOOD,
    )
    defaults.update(overrides)
    return Property(**defaults)


class TestCalculateMonthlyPayment:
    def test_percent_rate_semantics(self):
        # 6.85% annual, not 0.0685 — must match loan_engine convention
        p = _calculate_monthly_payment(500000, rate=6.85)
        # $400k loan @ 6.85%/30yr -> ~$2622
        assert 2500 < p < 2750

    def test_known_rate(self):
        # $360k loan @ 6% -> ~$2158
        p = _calculate_monthly_payment(450000, down_pct=0.20, rate=6.0)
        assert abs(p - 2158.38) < 1.0


class TestGrade:
    def test_thresholds(self):
        assert _grade_from_score(95) == "A+"
        assert _grade_from_score(90) == "A+"
        assert _grade_from_score(85) == "A"
        assert _grade_from_score(75) == "B+"
        assert _grade_from_score(65) == "B"
        assert _grade_from_score(55) == "C+"
        assert _grade_from_score(45) == "C"
        assert _grade_from_score(30) == "D"
        assert _grade_from_score(10) == "F"


class TestScoreDeal:
    def test_score_in_bounds_and_consistent(self):
        prop = make_property()
        val = valuate_property(prop)
        deal = score_deal(prop, val)
        assert 0 <= deal.deal_score <= 100
        assert deal.deal_grade
        assert deal.reasons
        assert deal.risk_factors
        assert deal.monthly_payment_estimate > 0

    def test_underpriced_scores_higher(self):
        # Same home, cheaper list price -> higher deal score
        cheap = make_property(list_price=350000)
        pricey = make_property(list_price=800000, id="p2")
        deal_cheap = score_deal(cheap, valuate_property(cheap))
        deal_pricey = score_deal(pricey, valuate_property(pricey))
        assert deal_cheap.deal_score > deal_pricey.deal_score

    def test_roi_positive_for_underpriced(self):
        prop = make_property(list_price=300000)
        roi = _estimate_5yr_roi(prop, valuate_property(prop).estimated_value)
        assert roi > 0


class TestOptimizeSearch:
    def test_mock_search_returns_deals(self, monkeypatch):
        monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
        result = optimize_search(SearchSpecs(city="Bethesda", state="MD"))
        assert result["total_results"] > 0
        stats = result["market_stats"]
        assert stats["area_name"] == "Bethesda"
        assert stats["median_price"] > 0
        # Fabricated trend fields are gone
        assert "price_trend_30d" not in stats
        assert "inventory_change_30d" not in stats

    def test_unknown_city_not_substituted(self, monkeypatch):
        """Searching an unknown city must not silently return another city."""
        monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
        result = optimize_search(SearchSpecs(city="Austin", state="TX"))
        assert result["market_stats"]["area_name"] == "Austin"
        cities = {d["property"]["city"] for d in result["deals"]}
        assert cities == {"Austin"}

    def test_filters_respected(self, monkeypatch):
        monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
        result = optimize_search(SearchSpecs(
            city="Bethesda", state="MD", max_price=200000))
        # Mock generator may legitimately return zero at that price point
        for d in result["deals"]:
            assert d["property"]["list_price"] <= 200000

    def test_bad_property_does_not_crash_search(self, monkeypatch):
        """A valuation-rejected listing must be skipped, not fatal."""
        monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
        from data_pipeline import generate_mock_listings

        good = generate_mock_listings(
            SearchSpecs(city="Bethesda", state="MD"), count=5)
        bad = make_property(id="bad", sqft=0)  # valuation rejects sqft<=0
        monkeypatch.setattr(
            "optimizer.fetch_live_listings",
            lambda specs, count=60: good + [bad],
        )
        result = optimize_search(SearchSpecs(city="Bethesda", state="MD"))
        assert result["total_results"] == len(good)
        assert all(d["property"]["id"] != "bad" for d in result["deals"])


class TestPagination:
    @pytest.fixture()
    def fixed_props(self, monkeypatch):
        """One shared dataset so repeated optimize_search calls line up."""
        monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
        from data_pipeline import generate_mock_listings
        props = generate_mock_listings(
            SearchSpecs(city="Columbia", state="MD"), count=60)
        assert len(props) == 60
        monkeypatch.setattr(
            "optimizer.fetch_live_listings", lambda specs, count=60: props)
        return props

    def test_no_page_returns_everything(self, fixed_props):
        result = optimize_search(SearchSpecs(city="Columbia", state="MD"))
        assert result["total_results"] == len(result["deals"]) == 60
        assert result["page"] is None
        assert result["total_pages"] is None

    def test_page_slices_results(self, fixed_props):
        specs = SearchSpecs(city="Columbia", state="MD")
        full = optimize_search(specs)
        p1 = optimize_search(specs, page=1, page_size=20)
        p2 = optimize_search(specs, page=2, page_size=20)

        assert len(p1["deals"]) == 20
        assert p1["page"] == 1
        assert p1["total_results"] == 60  # total, not page count
        assert p1["total_pages"] == 3
        assert len(p2["deals"]) == 20
        assert p2["page"] == 2

        # Pages follow the full sorted order exactly, disjointly
        full_ids = [d["property"]["id"] for d in full["deals"]]
        assert [d["property"]["id"] for d in p1["deals"]] == full_ids[:20]
        assert [d["property"]["id"] for d in p2["deals"]] == full_ids[20:40]

    def test_beyond_last_page_empty(self, fixed_props):
        specs = SearchSpecs(city="Columbia", state="MD")
        last = optimize_search(specs, page=4, page_size=20)
        assert last["deals"] == []
        assert last["total_results"] == 60

    def test_sort_applies_before_pagination(self, fixed_props):
        specs = SearchSpecs(city="Columbia", state="MD", sort_by="price_asc")
        p1 = optimize_search(specs, page=1, page_size=10)
        prices = [d["property"]["list_price"] for d in p1["deals"]]
        assert prices == sorted(prices)


class TestAppreciation:
    def test_metro_appreciation_wired_into_response(self, monkeypatch):
        monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
        monkeypatch.setattr(
            "optimizer.get_metro_baseline",
            lambda city, state: {"appreciation_1y": 0.10,
                                 "typical_value": 400000,
                                 "as_of": "2026-08-31"})
        result = optimize_search(SearchSpecs(city="Columbia", state="MD"))
        meta = result["appreciation_assumption"]
        assert meta == {"value": 0.10, "source": "zillow-research-metro"}
        assert result["market_baseline"]["typical_value"] == 400000

    def test_default_when_metro_unknown(self, monkeypatch):
        monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
        monkeypatch.setattr("optimizer.get_metro_baseline",
                            lambda city, state: None)
        result = optimize_search(SearchSpecs(city="Columbia", state="MD"))
        meta = result["appreciation_assumption"]
        assert meta["source"] == "national-default"
        assert meta["value"] > 0
        assert result["market_baseline"] is None

    def test_higher_appreciation_raises_roi(self):
        prop = make_property(list_price=300000)
        val = valuate_property(prop)
        low = _estimate_5yr_roi(prop, val.estimated_value, appreciation=0.0)
        high = _estimate_5yr_roi(prop, val.estimated_value, appreciation=0.10)
        assert high > low


class TestRentCashflow:
    def test_rent_and_cashflow_wired(self, monkeypatch):
        monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
        monkeypatch.setattr(
            "optimizer.get_metro_baseline",
            lambda city, state: {"appreciation_1y": 0.01,
                                 "typical_rent": 1820.0})
        result = optimize_search(SearchSpecs(city="Columbia", state="MD"))
        deal = result["deals"][0]
        assert deal["estimated_rent"] == 1820.0
        assert deal["estimated_monthly_cashflow"] == round(
            1820.0 - deal["monthly_payment_estimate"], 2)
        assert deal["estimated_monthly_cashflow"] < 0  # P&I > metro rent

    def test_no_rent_data_leaves_fields_none(self, monkeypatch):
        monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
        monkeypatch.setattr(
            "optimizer.get_metro_baseline", lambda city, state: None)
        result = optimize_search(SearchSpecs(city="Columbia", state="MD"))
        for deal in result["deals"]:
            assert deal["estimated_rent"] is None
            assert deal["estimated_monthly_cashflow"] is None


class TestValuation:
    def test_rejects_zero_sqft(self):
        with pytest.raises(Exception):
            valuate_property(make_property(sqft=0))

    def test_rejects_zero_price(self):
        with pytest.raises(Exception):
            valuate_property(make_property(list_price=0))

    def test_reasonable_estimate(self):
        val = valuate_property(make_property())
        base = 2000 * 425  # Bethesda market $/sqft
        assert base * 0.5 < val.estimated_value < base * 1.7
        assert 0 <= val.confidence_score <= 1


class TestCashflowScoring:
    def _deal(self, monkeypatch, rent=None, **over):
        monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
        prop = make_property(**over)
        val = valuate_property(prop)
        return prop, score_deal(prop, val, metro_rent=rent)

    def test_rent_coverage_boosts_score(self, monkeypatch):
        _, no_rent = self._deal(monkeypatch, rent=None,
                                list_price=400000)
        _, covered = self._deal(monkeypatch, rent=4000,
                                list_price=400000)
        assert covered.deal_score > no_rent.deal_score

    def test_weak_coverage_penalizes(self, monkeypatch):
        _, no_rent = self._deal(monkeypatch, rent=None,
                                list_price=800000, id="p9")
        _, weak = self._deal(monkeypatch, rent=1000,
                             list_price=800000, id="p8")
        assert weak.deal_score < no_rent.deal_score

    def test_cashflow_reason_added(self, monkeypatch):
        _, deal = self._deal(monkeypatch, rent=5000, list_price=300000)
        assert any("cashflow" in r for r in deal.reasons)

    def test_no_rent_no_cashflow_reason(self, monkeypatch):
        _, deal = self._deal(monkeypatch, rent=None, list_price=300000)
        assert not any("cashflow" in r for r in deal.reasons)
