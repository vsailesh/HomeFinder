"""RapidAPI Zillow client tests — address parsing, filters, caching."""
import rapidapi_zillow as rz
from models import SearchSpecs


class TestParseAddress:
    def test_full_address(self):
        specs = SearchSpecs()
        city, state, zc = rz._parse_address(
            "123 Main St, Bethesda, MD 20814", specs)
        assert city == "Bethesda"
        assert state == "MD"
        assert zc == "20814"

    def test_no_zip(self):
        specs = SearchSpecs()
        city, state, zc = rz._parse_address("1 A St, Austin, TX", specs)
        assert city == "Austin"
        assert state == "TX"

    def test_malformed_falls_back_to_specs(self):
        specs = SearchSpecs(city="Denver", state="CO", zip_code="80202")
        city, state, zc = rz._parse_address("", specs)
        assert city == "Denver"
        assert state == "CO"
        assert zc == "80202"


class TestPassesFilters:
    def base(self, **kw):
        return SearchSpecs(**kw)

    def test_min_price(self):
        specs = self.base(min_price=200000)
        assert not rz._passes_filters(199999, 3, 2, 1500, specs)
        assert rz._passes_filters(200000, 3, 2, 1500, specs)

    def test_max_price(self):
        specs = self.base(max_price=500000)
        assert rz._passes_filters(499999, 3, 2, 1500, specs)
        assert not rz._passes_filters(500001, 3, 2, 1500, specs)

    def test_bedrooms(self):
        specs = self.base(min_bedrooms=3)
        assert not rz._passes_filters(300000, 2, 2, 1500, specs)
        assert rz._passes_filters(300000, 3, 2, 1500, specs)

    def test_sqft(self):
        specs = self.base(min_sqft=1000, max_sqft=2000)
        assert not rz._passes_filters(300000, 3, 2, 999, specs)
        assert not rz._passes_filters(300000, 3, 2, 2001, specs)
        assert rz._passes_filters(300000, 3, 2, 1500, specs)

    def test_no_filters_passes(self):
        assert rz._passes_filters(1, 0, 0, 1, SearchSpecs())


class TestBuildLocation:
    def test_city_state(self):
        assert rz._build_location(
            SearchSpecs(city="Austin", state="TX")) == "Austin, TX"

    def test_zip_only(self):
        assert rz._build_location(SearchSpecs(zip_code="20814")) == "20814"

    def test_default_usa(self):
        assert rz._build_location(SearchSpecs()) == "USA"


class TestRawCache:
    def test_no_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
        assert rz.fetch_rapidapi_properties(SearchSpecs(), limit=10) == []

    def test_missing_sqft_skipped(self, monkeypatch):
        """Listings without sqft must be dropped, never invented."""
        monkeypatch.setenv("RAPIDAPI_KEY", "test-key")
        raw = [
            {"zpid": 1, "price": 400000, "beds": 3, "baths": 2,
             "sqft": 0, "status": "FOR_SALE",
             "address": "1 A St, Austin, TX 78701"},      # no sqft -> skip
            {"zpid": 2, "price": 0, "beds": 3, "baths": 2,
             "sqft": 1500, "status": "FOR_SALE",
             "address": "2 B St, Austin, TX 78701"},      # no price -> skip
            {"zpid": 3, "price": 450000, "beds": 4, "baths": 3,
             "sqft": 2000, "status": "FOR_SALE",
             "address": "3 C St, Austin, TX 78701"},      # good
            {"zpid": 4, "price": 450000, "beds": 4, "baths": 3,
             "sqft": 2000, "status": "SOLD",
             "address": "4 D St, Austin, TX 78701"},      # not for sale -> skip
        ]
        monkeypatch.setattr(rz, "_fetch_raw_location", lambda loc, key: raw)
        props = rz.fetch_rapidapi_properties(SearchSpecs(), limit=10)
        assert len(props) == 1
        assert props[0].id == "3"
        assert props[0].sqft == 2000

    def test_cache_hit_avoids_refetch(self, monkeypatch):
        """Second fetch of the same location within TTL must not hit HTTP."""
        calls = []
        item = {"zpid": 9, "price": 100000, "beds": 1, "baths": 1,
                "sqft": 800, "status": "FOR_SALE", "address": "x"}

        class FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"results": [item], "count": 1}

        def fake_get(url, **kwargs):
            calls.append(url)
            return FakeResp()

        monkeypatch.setattr(rz.requests, "get", fake_get)
        monkeypatch.setattr(rz, "_raw_cache", {})

        first = rz._fetch_raw_location("Austin, TX", "key")
        second = rz._fetch_raw_location("Austin, TX", "key")

        assert len(calls) == 1, "second call should be served from cache"
        assert first == second == [item]

    def test_expired_cache_refetches(self, monkeypatch):
        calls = []
        item = {"zpid": 9, "price": 100000, "beds": 1, "baths": 1,
                "sqft": 800, "status": "FOR_SALE", "address": "x"}

        class FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"results": [item], "count": 1}

        monkeypatch.setattr(rz.requests, "get", lambda url, **kw: (
            calls.append(url), FakeResp())[1])
        # Pre-seed an expired cache entry (ts = 0)
        monkeypatch.setattr(rz, "_raw_cache",
                            {"Austin, TX": {"items": [], "ts": 0.0}})

        rz._fetch_raw_location("Austin, TX", "key")
        assert len(calls) == 1, "expired cache should trigger refetch"
