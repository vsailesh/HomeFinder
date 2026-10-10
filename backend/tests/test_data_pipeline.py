"""Data pipeline tests — registry, mock generator honesty."""
import data_pipeline as dp
from models import Property, PropertyType, PropertyCondition, SearchSpecs


def make_property(pid="p1", **overrides):
    defaults = dict(
        id=pid, address="1 Main St", city="Bethesda", state="MD",
        zip_code="20814", list_price=500000, sqft=2000,
        source="test",
    )
    defaults.update(overrides)
    return Property(**defaults)


class TestRegistry:
    def test_register_and_lookup(self):
        prop = make_property("reg-1")
        dp.register_listings([prop])
        assert dp.get_property_by_id("reg-1") is prop

    def test_missing_returns_none(self):
        assert dp.get_property_by_id("no-such-id") is None

    def test_cap_eviction(self, monkeypatch):
        monkeypatch.setattr(dp, "_property_registry", type(dp._property_registry)())
        for i in range(dp._REGISTRY_CAP + 10):
            dp.register_listings([make_property(f"cap-{i}")])
        assert len(dp._property_registry) == dp._REGISTRY_CAP
        # Oldest evicted, newest retained
        assert dp.get_property_by_id("cap-0") is None
        assert dp.get_property_by_id(f"cap-{dp._REGISTRY_CAP + 9}") is not None


class TestMockGenerator:
    def test_respects_hard_filters(self):
        import random
        random.seed(102)  # generator is random; pin for determinism
        specs = SearchSpecs(
            city="Bethesda", state="MD",
            min_price=300000, max_price=600000,
            min_bedrooms=3, min_sqft=1500,
            must_have_garage=True,
        )
        props = dp.generate_mock_listings(specs, count=15)
        assert props, "generator should produce at least some listings"
        for p in props:
            assert 300000 <= p.list_price <= 600000
            assert p.bedrooms >= 3
            assert p.sqft >= 1500
            assert p.has_garage
            assert p.source == "mock-generator"

    def test_unknown_city_uses_requested_name(self):
        props = dp.generate_mock_listings(
            SearchSpecs(city="Boise", state="ID"), count=5)
        assert props
        for p in props:
            assert p.city == "Boise"
            assert p.state == "ID"

    def test_known_city_uses_market_data(self):
        city, data = dp._pick_city(SearchSpecs(city="bethesda", state="MD"))
        assert city == "Bethesda"
        assert data["median_sqft_price"] == 425

    def test_state_fallback_matches_state(self):
        city, data = dp._pick_city(SearchSpecs(state="MD"))
        assert data["state"] == "MD"


class TestMarketSqftPrice:
    def test_known_city(self):
        assert dp.get_market_sqft_price("Bethesda") == 425

    def test_partial_name(self):
        # requested name must be a substring of a known city name
        assert dp.get_market_sqft_price("bethesda") == 425

    def test_unknown_default(self):
        assert dp.get_market_sqft_price("Nowhere") == 225.0


class TestSourceFallbackChain:
    """RapidAPI -> HomeSteps REO -> mock generator."""

    def _specs(self):
        return SearchSpecs(city="Baltimore", state="MD")

    def test_homesteps_beats_mock(self, monkeypatch):
        monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
        monkeypatch.setattr(dp, "fetch_rapidapi_properties",
                            lambda specs, limit=50: [])
        from models import Property, PropertyCondition
        reo = Property(
            id="hs-1", address="1 Real St", city="Baltimore", state="MD",
            zip_code="21201", list_price=100000, sqft=1000,
            condition=PropertyCondition.UNKNOWN,
            source="homesteps-freddie-mac")
        monkeypatch.setattr(dp, "fetch_homesteps_properties",
                            lambda c, s, z=None: [reo])
        props = dp.fetch_live_listings(self._specs())
        assert [p.source for p in props] == ["homesteps-freddie-mac"]

    def test_mock_when_homesteps_empty(self, monkeypatch):
        monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
        monkeypatch.setattr(dp, "fetch_rapidapi_properties",
                            lambda specs, limit=50: [])
        monkeypatch.setattr(dp, "fetch_homesteps_properties",
                            lambda c, s, z=None: [])
        props = dp.fetch_live_listings(self._specs())
        assert props and props[0].source == "mock-generator"

    def test_rapidapi_beats_homesteps(self, monkeypatch):
        monkeypatch.setenv("RAPIDAPI_KEY", "k" * 50)
        from models import Property, PropertyCondition
        live = Property(
            id="z-1", address="1 Zillow St", city="Baltimore", state="MD",
            zip_code="21201", list_price=200000, sqft=1500,
            condition=PropertyCondition.UNKNOWN, source="RapidAPI-ZillowLive")
        monkeypatch.setattr(dp, "fetch_rapidapi_properties",
                            lambda specs, limit=50: [live])
        called = []
        monkeypatch.setattr(dp, "fetch_homesteps_properties",
                            lambda c, s, z=None: called.append(1) or [])
        props = dp.fetch_live_listings(self._specs())
        assert props[0].source == "RapidAPI-ZillowLive"
        assert not called  # HomeSteps never queried
