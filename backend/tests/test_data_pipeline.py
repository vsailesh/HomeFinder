"""Data pipeline tests — registry, mock generator honesty, outage cache."""
import pytest

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


class TestZillowOutageCache:
    """RapidAPI provider outages last days — the last good Zillow
    results per market are served stale (within a grace window)
    before falling through to HomeSteps/mock."""

    @pytest.fixture(autouse=True)
    def clean_cache(self, monkeypatch):
        monkeypatch.setattr(dp, "_zillow_cache", type(dp._zillow_cache)())

    def _specs(self, city="Chicago", **kw):
        return SearchSpecs(city=city, state="IL", **kw)

    def _with_sources(self, monkeypatch, rapidapi, homesteps):
        monkeypatch.setattr(dp, "fetch_rapidapi_properties", rapidapi)
        monkeypatch.setattr(dp, "fetch_homesteps_properties", homesteps)

    def test_success_populates_cache(self, monkeypatch):
        props = [make_property("z1", source="rapidapi-zillow")]
        self._with_sources(
            monkeypatch,
            lambda specs, limit=50: props,
            lambda city, state, zip_code=None: [])
        out, info = dp.fetch_live_listings(self._specs())
        assert out == props
        assert info == {"tier": "zillow", "cached_at": None}
        assert dp._zillow_cache  # remembered

    def test_outage_serves_stale_before_homesteps(self, monkeypatch):
        props = [make_property("z1", source="rapidapi-zillow")]
        reo = [make_property("reo1", source="homesteps-freddie-mac")]
        calls = {"rapid": 0, "reo": 0}

        def rapid(specs, limit=50):
            calls["rapid"] += 1
            return props if calls["rapid"] == 1 else []  # then outage

        self._with_sources(
            monkeypatch, rapid,
            lambda city, state, zip_code=None:
                calls.__setitem__("reo", calls["reo"] + 1) or reo)
        first, info1 = dp.fetch_live_listings(self._specs())
        assert first == props
        assert info1["tier"] == "zillow"
        second, info2 = dp.fetch_live_listings(self._specs())  # outage
        assert second == props  # stale cache, not REO
        assert calls["reo"] == 0
        assert info2["tier"] == "zillow-cache"
        assert info2["cached_at"] is not None

    def test_stale_cache_refiltered_against_current_specs(self, monkeypatch):
        """The cache holds whatever the POPULATING search fetched — a
        later search with different filters must not see those listings
        as matches."""
        cheap = make_property("z1", list_price=200000,
                              source="rapidapi-zillow")
        pricey = make_property("z2", list_price=800000,
                               source="rapidapi-zillow")
        calls = {"rapid": 0}

        def rapid(specs, limit=50):
            calls["rapid"] += 1
            return [cheap, pricey] if calls["rapid"] == 1 else []

        self._with_sources(
            monkeypatch, rapid,
            lambda city, state, zip_code=None: [])
        dp.fetch_live_listings(self._specs())  # populate unfiltered
        # Outage + min_price filter: only the matching cached listing
        # survives, labeled as cache tier.
        out, info = dp.fetch_live_listings(self._specs(min_price=500000))
        assert [p.id for p in out] == ["z2"]
        assert info["tier"] == "zillow-cache"
        # Outage + a filter nothing satisfies: fall through, don't
        # serve non-matching stale listings.
        out2, info2 = dp.fetch_live_listings(self._specs(min_price=900000))
        assert all(p.source == "mock-generator" for p in out2)
        assert info2["tier"] == "mock"

    def test_expired_cache_falls_through(self, monkeypatch):
        props = [make_property("z1", source="rapidapi-zillow")]
        calls = {"n": 0}

        def rapid(specs, limit=50):
            calls["n"] += 1
            return props if calls["n"] == 1 else []  # then outage

        self._with_sources(
            monkeypatch, rapid,
            lambda city, state, zip_code=None: [])
        dp.fetch_live_listings(self._specs())
        key = dp._cache_key(self._specs())
        ts = dp._zillow_cache[key][1]
        dp._zillow_cache[key] = (props, ts - dp._STALE_GRACE_SECONDS - 1)
        out, info = dp.fetch_live_listings(self._specs())  # outage + expired
        assert all(p.source == "mock-generator" for p in out)
        assert info["tier"] == "mock"

    def test_env_int_tolerates_bad_values(self, monkeypatch):
        # Import-time env parse must never crash boot on placeholders.
        assert dp._env_int("NO_SUCH_VAR_X", 604800) == 604800
        monkeypatch.setenv("NO_SUCH_VAR_X", "")
        assert dp._env_int("NO_SUCH_VAR_X", 604800) == 604800
        monkeypatch.setenv("NO_SUCH_VAR_X", "7d")
        assert dp._env_int("NO_SUCH_VAR_X", 604800) == 604800
        monkeypatch.setenv("NO_SUCH_VAR_X", " 90 ")
        assert dp._env_int("NO_SUCH_VAR_X", 604800) == 90

    def test_cache_key_market_scoped(self):
        a = dp._cache_key(SearchSpecs(city="Chicago", state="IL"))
        b = dp._cache_key(SearchSpecs(city="chicago ", state="il"))
        c = dp._cache_key(SearchSpecs(city="Detroit", state="MI"))
        assert a == b          # normalization: case/whitespace insensitive
        assert a != c          # markets don't collide

    def test_cache_cap_eviction(self, monkeypatch):
        monkeypatch.setattr(dp, "_ZILLOW_CACHE_CAP", 2)
        monkeypatch.setattr(dp, "_zillow_cache", type(dp._zillow_cache)())
        for city in ("a", "b", "c"):
            dp._remember_zillow((city, "IL", ""), [make_property(city)])
        assert len(dp._zillow_cache) == 2
        assert ("a", "IL", "") not in dp._zillow_cache  # oldest evicted


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
        props, info = dp.fetch_live_listings(self._specs())
        assert [p.source for p in props] == ["homesteps-freddie-mac"]
        assert info["tier"] == "homesteps"

    def test_mock_when_homesteps_empty(self, monkeypatch):
        monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
        monkeypatch.setattr(dp, "fetch_rapidapi_properties",
                            lambda specs, limit=50: [])
        monkeypatch.setattr(dp, "fetch_homesteps_properties",
                            lambda c, s, z=None: [])
        props, info = dp.fetch_live_listings(self._specs())
        assert props and props[0].source == "mock-generator"
        assert info["tier"] == "mock"

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
        props, info = dp.fetch_live_listings(self._specs())
        assert props[0].source == "RapidAPI-ZillowLive"
        assert info["tier"] == "zillow"
        assert not called  # HomeSteps never queried


class TestSqftEstimateConfidence:
    def test_estimated_sqft_lowers_confidence(self):
        from valuation_engine import valuate_property
        solid = Property(
            id="p-solid", address="1 A St", city="Bethesda", state="MD",
            zip_code="20814", list_price=500000, sqft=2000,
            year_built=2010, condition=PropertyCondition.GOOD)
        soft = solid.model_copy(update={"sqft_estimated": True,
                                        "id": "p-soft"})
        v_solid = valuate_property(solid)
        v_soft = valuate_property(soft)
        assert v_soft.confidence_score < v_solid.confidence_score
