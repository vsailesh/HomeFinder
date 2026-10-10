"""
Freddie Mac HomeSteps REO listings — no API key required.

HomeSteps (homesteps.com) publishes Freddie Mac's for-sale REO
inventory as a public Drupal site. The listing search renders
server-side HTML with per-listing map markers (lat/lng + detail URL),
and every detail page carries full schema.org RealEstateListing
JSON-LD (address, geo, price, beds, baths, year, photos).

Coverage is thin (REO inventory only — a handful of listings per
metro) but 100% real and free, so it serves as the live-data fallback
between RapidAPI quota cycles.

HomeSteps does not publish square footage. We estimate it from room
count (transparently flagged via Property.sqft_estimated) so the
valuation engine can run; confidence in those valuations is
correspondingly soft.
"""
import json
import logging
import re
import threading
import time
from typing import Dict, List, Optional
from urllib.parse import quote_plus

import requests

from models import Property, PropertyType

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.homesteps.com/listing/search"
DETAIL_URL = "https://www.homesteps.com"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko)"),
}
_TIMEOUT = 25

_SEARCH_CACHE_TTL = 20 * 60   # search page: 20 minutes
_DETAIL_CACHE_TTL = 60 * 60   # detail JSON-LD: 1 hour
_MAX_DETAIL_FETCHES = 12      # politeness cap per search

_lock = threading.Lock()
_search_cache: Dict[str, tuple] = {}   # query -> (ts, hrefs)
_detail_cache: Dict[str, tuple] = {}   # slug -> (ts, prop_dict or None)

# Search page renders map markers in order, each carrying the listing
# coordinates and the detail-page href (whose slug ends -st-12345).
_ROW_RE = re.compile(
    r'data-lat="(-?[\d.]+)"\s+data-lng="(-?[\d.]+)"\s+'
    r'data-set-marker="true"'
    r'.*?href="(/listingdetails/[^"]+)"', re.S)
_SLUG_RE = re.compile(r"-([a-z]{2})-(\d{5})/?$")
_PRICE_RE = re.compile(r'property-price[^"]*">\s*\$([\d,]+)')

_TYPE_MAP = {
    "townhome": PropertyType.TOWNHOUSE,
    "townhouse": PropertyType.TOWNHOUSE,
    "condo": PropertyType.CONDO,
    "condominium": PropertyType.CONDO,
    "multi": PropertyType.MULTI_FAMILY,
    "land": PropertyType.LAND,
}


def _parse_search_rows(html: str) -> List[Dict]:
    rows = []
    for m in _ROW_RE.finditer(html):
        lat, lng, href = m.groups()
        slug_state = _SLUG_RE.search(href)
        # Price sits in the row markup right after the href.
        tail = html[m.end():m.end() + 600]
        price_m = _PRICE_RE.search(tail)
        rows.append({
            "lat": float(lat),
            "lng": float(lng),
            "href": href,
            "slug": href.rsplit("/", 1)[-1],
            "state": slug_state.group(1) if slug_state else None,
            "zip": slug_state.group(2) if slug_state else None,
            "price": float(price_m.group(1).replace(",", ""))
            if price_m else None,
        })
    return rows


def _estimate_sqft(total_rooms: Optional[int], beds: int) -> int:
    """Rough interior size from room count (fallback: bedrooms).
    HomeSteps publishes no square footage — always flagged estimated."""
    base = total_rooms if total_rooms and total_rooms > 0 else beds * 2 + 2
    return max(500, min(6000, int(base * 220)))


def _listing_from_jsonld(data: Dict, fallback: Dict) -> Optional[dict]:
    """Map a RealEstateListing JSON-LD object to Property fields."""
    try:
        loc = data.get("location") or data["@location"]
        addr = loc["address"]
        offers = data.get("offers", {})
        item = offers.get("itemOffered", {})
        props = {p.get("name"): p.get("value")
                 for p in item.get("additionalProperty", [])}

        price_s = str(offers.get("price", "")).replace("$", "").replace(",", "")
        price = float(price_s) if price_s else fallback.get("price") or 0
        if price <= 0:
            return None

        beds = int(item.get("numberOfBedrooms") or 0)
        baths = float(item.get("numberOfBathroomsTotal") or 0)
        total_rooms = None
        try:
            total_rooms = int(props.get("Total Rooms"))
        except (TypeError, ValueError):
            pass

        lot_acres = None
        m = re.search(r"([\d.]+)", props.get("Lot Size") or "")
        if m:
            lot_acres = float(m.group(1))

        amenity = {a.get("name"): a.get("value")
                   for a in item.get("amenityFeature", [])}
        images = data.get("image") or []
        image_url = None
        if images and isinstance(images, list):
            first = images[0]
            image_url = (first.get("url") if isinstance(first, dict)
                         else first)

        category = str(item.get("accommodationCategory") or "").lower()
        ptype = next((v for k, v in _TYPE_MAP.items() if k in category),
                     PropertyType.SINGLE_FAMILY)

        year_built = None
        try:
            year_built = int(item.get("yearBuilt"))
        except (TypeError, ValueError):
            pass

        return {
            "id": "homesteps-" + fallback.get("slug", addr["streetAddress"]
                                              .lower().replace(" ", "-")),
            "address": addr["streetAddress"],
            "city": addr.get("addressLocality") or "",
            "state": addr.get("addressRegion") or "",
            "zip_code": addr.get("postalCode") or fallback.get("zip") or "",
            "latitude": float(loc["geo"]["latitude"]),
            "longitude": float(loc["geo"]["longitude"]),
            "list_price": price,
            "property_type": ptype.value,
            "bedrooms": beds,
            "bathrooms": baths,
            "sqft": _estimate_sqft(total_rooms, beds),
            "sqft_estimated": True,
            "lot_sqft": int(lot_acres * 43560) if lot_acres else None,
            "year_built": year_built,
            "has_basement": str(props.get("Basement", "")).lower() == "yes",
            "has_central_air": "air" in str(
                amenity.get("Air Conditioning", "")).lower(),
            "condition": "unknown",
            "source": "homesteps-freddie-mac",
            "url": DETAIL_URL + fallback.get("href", ""),
            "image_url": image_url,
            "annual_tax": _money(props.get("Property Tax")),
        }
    except (KeyError, ValueError, TypeError) as e:
        logger.warning("HomeSteps JSON-LD parse failed: %s", e)
        return None


def _money(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    digits = re.sub(r"[^\d.]", "", str(s))
    return float(digits) if digits else None


def _fetch_detail(href: str, fallback: Dict) -> Optional[dict]:
    slug = fallback.get("slug") or href.rsplit("/", 1)[-1]
    now = time.time()
    with _lock:
        cached = _detail_cache.get(slug)
        if cached and now - cached[0] < _DETAIL_CACHE_TTL:
            return cached[1]

    try:
        resp = requests.get(DETAIL_URL + href, headers=_HEADERS,
                            timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("HomeSteps detail fetch failed (%s): %s", href, e)
        with _lock:
            _detail_cache[slug] = (now, None)
        return None

    for m in re.finditer(
            r'<script type="application/ld\+json">(.*?)</script>',
            resp.text, re.S):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        types = data.get("@type") if isinstance(data, dict) else None
        if types and "RealEstateListing" in types:
            parsed = _listing_from_jsonld(data, fallback)
            with _lock:
                _detail_cache[slug] = (now, parsed)
            return parsed
    with _lock:
        _detail_cache[slug] = (now, None)
    return None


def fetch_homesteps_properties(city: Optional[str],
                               state: Optional[str],
                               zip_code: Optional[str] = None,
                               max_results: int = 12) -> List[Property]:
    """Real Freddie Mac REO listings for the area, no API key.

    Returns [] on any failure — callers fall through to other sources.
    """
    if not (city and state) and not state and not zip_code:
        return []
    query = quote_plus(" ".join(filter(None, [city, state])) or zip_code)
    now = time.time()

    with _lock:
        cached = _search_cache.get(query)
    if cached and now - cached[0] < _SEARCH_CACHE_TTL:
        rows = cached[1]
    else:
        try:
            resp = requests.get(
                f"{SEARCH_URL}?search={query}",
                headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            rows = _parse_search_rows(resp.text)
            with _lock:
                _search_cache[query] = (now, rows)
        except requests.RequestException as e:
            logger.warning("HomeSteps search failed: %s", e)
            return []
    if not rows:
        return []

    wanted_state = (state or "").lower()
    candidates = [r for r in rows if r["state"] == wanted_state] \
        if wanted_state else rows
    # Strict city filter first; if the city has no REO inventory keep
    # the state's (real listings elsewhere beat an empty page).
    if city:
        city_rows = [r for r in candidates
                     if city.lower() in r["slug"].replace("-", " ")]
        if city_rows:
            candidates = city_rows
    candidates = candidates[:_MAX_DETAIL_FETCHES]

    props: List[Property] = []
    for row in candidates:
        detail = _fetch_detail(row["href"], row)
        if detail and detail["sqft"] > 0 and detail["list_price"] > 0:
            props.append(Property(**detail))
        if len(props) >= max_results:
            break
    logger.info("HomeSteps: %d real REO listings for query '%s'",
                len(props), query)
    return props
