"""Tests for the Freddie Mac HomeSteps REO provider (no network)."""
import json

import pytest

import homesteps_provider as hs
from homesteps_provider import (
    _estimate_sqft, _listing_from_jsonld, _parse_search_rows,
    fetch_homesteps_properties,
)

SEARCH_HTML = """
<div class="geolocation-location js-hide" data-lat="39.247" data-lng="-76.68"
     data-set-marker="true" typeof="Place"><span property="geo" typeof="GeoCoordinates"></span>
  <div class="location-content"><a href="/listingdetails/2421-saratoga-ave-baltimore-md-21227">
    <div class="property-price weight-medium">$169,900</div>
    <div class="property-status-value">Active</div></a></div></div>
<div class="geolocation-location js-hide" data-lat="45.34" data-lng="-122.83"
     data-set-marker="true" typeof="Place"><span property="geo" typeof="GeoCoordinates"></span>
  <div class="location-content"><a href="/listingdetails/15859-sunset-court-sherwood-or-97140">
    <div class="property-price weight-medium">$344,900</div></a></div></div>
"""

JSONLD = {
    "@type": ["RealEstateListing"],
    "location": {
        "address": {"streetAddress": "2421 Saratoga Ave", "addressLocality":
                    "Baltimore", "addressRegion": "MD", "postalCode": "21227"},
        "geo": {"latitude": "39.247", "longitude": "-76.68"},
    },
    "url": "https://www.homesteps.com/listingdetails/2421-saratoga-ave",
    "image": [{"@type": "ImageObject",
               "url": "https://rbimages.blob.core.windows.net/x/1.jpg"}],
    "offers": {
        "price": "$169,900",
        "itemOffered": {
            "@type": "SingleFamilyResidence",
            "yearBuilt": "1953",
            "numberOfBedrooms": "3",
            "numberOfBathroomsTotal": "1",
            "accommodationCategory": "Townhome",
            "amenityFeature": [
                {"@type": "LocationFeatureSpecification",
                 "name": "Air Conditioning", "value": "Central Air"},
            ],
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "Total Rooms",
                 "value": "6"},
                {"@type": "PropertyValue", "name": "Lot Size",
                 "value": "0.05 acres"},
                {"@type": "PropertyValue", "name": "Basement",
                 "value": "Yes"},
                {"@type": "PropertyValue", "name": "Property Tax",
                 "value": "$3,540"},
            ],
        },
    },
}


@pytest.fixture(autouse=True)
def clear_caches():
    hs._search_cache.clear()
    hs._detail_cache.clear()
    yield


class TestParseSearchRows:
    def test_rows_with_geo_state_zip_price(self):
        rows = _parse_search_rows(SEARCH_HTML)
        assert len(rows) == 2
        balt = rows[0]
        assert balt["state"] == "md"
        assert balt["zip"] == "21227"
        assert balt["price"] == 169900.0
        assert balt["lat"] == 39.247

    def test_out_of_state_row_flagged(self):
        rows = _parse_search_rows(SEARCH_HTML)
        assert rows[1]["state"] == "or"


class TestListingFromJsonld:
    def test_full_mapping(self):
        d = _listing_from_jsonld(
            JSONLD, {"slug": "2421-saratoga-ave-baltimore-md-21227",
                     "href": "/listingdetails/2421-saratoga-ave",
                     "zip": "21227", "price": 169900.0})
        assert d["address"] == "2421 Saratoga Ave"
        assert d["city"] == "Baltimore"
        assert d["list_price"] == 169900.0
        assert d["bedrooms"] == 3
        assert d["bathrooms"] == 1.0
        assert d["year_built"] == 1953
        assert d["property_type"] == "townhouse"
        assert d["sqft_estimated"] is True
        assert d["has_basement"] is True
        assert d["has_central_air"] is True
        assert d["lot_sqft"] == int(0.05 * 43560)
        assert d["annual_tax"] == 3540.0
        assert d["image_url"].startswith("https://rbimages")
        assert d["source"] == "homesteps-freddie-mac"

    def test_at_location_key_variant(self):
        data = json.loads(json.dumps(JSONLD))
        data["@location"] = data.pop("location")
        d = _listing_from_jsonld(data, {"slug": "x", "href": "/x", "zip":
                                        None, "price": None})
        assert d["address"] == "2421 Saratoga Ave"

    def test_missing_price_returns_none(self):
        data = json.loads(json.dumps(JSONLD))
        data["offers"]["price"] = ""
        assert _listing_from_jsonld(
            data, {"slug": "x", "href": "/x", "price": None}) is None


class TestSqftEstimate:
    def test_from_rooms(self):
        assert _estimate_sqft(6, 3) == 1320

    def test_falls_back_to_beds(self):
        assert _estimate_sqft(None, 3) == (3 * 2 + 2) * 220

    def test_clamped(self):
        assert _estimate_sqft(0, 0) == 500


class TestFetch:
    def _stub_search(self, monkeypatch, html):
        class Resp:
            status_code = 200
            text = html
            def raise_for_status(self):
                pass
        monkeypatch.setattr(
            hs.requests, "get", lambda *a, **k: Resp())

    def test_returns_real_props(self, monkeypatch):
        self._stub_search(monkeypatch, SEARCH_HTML)

        def fake_detail(href, fallback):
            return _listing_from_jsonld(
                JSONLD, fallback)
        monkeypatch.setattr(hs, "_fetch_detail", fake_detail)
        props = fetch_homesteps_properties("Baltimore", "MD")
        assert len(props) == 1  # Oregon row filtered by state
        assert props[0].source == "homesteps-freddie-mac"
        assert props[0].sqft_estimated is True
        assert props[0].url.startswith("https://www.homesteps.com/")

    def test_search_failure_returns_empty(self, monkeypatch):
        def boom(*a, **k):
            raise hs.requests.RequestException("down")
        monkeypatch.setattr(hs.requests, "get", boom)
        assert fetch_homesteps_properties("Baltimore", "MD") == []

    def test_no_inputs_returns_empty(self):
        assert fetch_homesteps_properties(None, None) == []
