import logging
import os
import time
import requests
from typing import List, Dict
from models import Property, PropertyType, PropertyCondition, SearchSpecs

logger = logging.getLogger(__name__)

API_HOST = "zillow-com-live-data-scraper-api.p.rapidapi.com"
BASE_URL = f"https://{API_HOST}"

# Raw location responses cached this long — cuts quota usage + latency on
# repeated searches of the same area within a short window.
RAW_CACHE_TTL_SECONDS = 20 * 60

_raw_cache: Dict[str, dict] = {}  # location -> {"items": [...], "ts": float}

_PTYPE_MAP = {
    "SINGLE_FAMILY": PropertyType.SINGLE_FAMILY,
    "CONDO": PropertyType.CONDO,
    "TOWNHOUSE": PropertyType.TOWNHOUSE,
    "MULTI_FAMILY": PropertyType.MULTI_FAMILY,
    "APARTMENT": PropertyType.MULTI_FAMILY,
}


def _parse_address(full: str, specs: SearchSpecs) -> tuple[str, str, str]:
    """Parse 'Street, City, ST ZIP' -> (city, state, zip)."""
    city = specs.city or "Unknown"
    state = specs.state or "Unk"
    zip_code = specs.zip_code or "00000"
    try:
        parts = [p.strip() for p in full.split(",")]
        if len(parts) >= 3:
            city = parts[-2] or city
            sz = parts[-1].split()
            if len(sz) >= 2:
                state = sz[0]
                zip_code = sz[1]
            elif len(sz) == 1:
                state = sz[0]
    except Exception:
        pass
    return city, state, zip_code


def _passes_filters(price: float, beds: int, baths: float, sqft: int,
                    specs: SearchSpecs) -> bool:
    if specs.min_price and price < specs.min_price:
        return False
    if specs.max_price and price > specs.max_price:
        return False
    if specs.min_bedrooms and beds < specs.min_bedrooms:
        return False
    if specs.max_bedrooms and beds > specs.max_bedrooms:
        return False
    if specs.min_bathrooms and baths < specs.min_bathrooms:
        return False
    if specs.min_sqft and sqft < specs.min_sqft:
        return False
    if specs.max_sqft and sqft > specs.max_sqft:
        return False
    return True


def _build_location(specs: SearchSpecs) -> str:
    if specs.city and specs.state:
        return f"{specs.city}, {specs.state}"
    if specs.zip_code:
        return specs.zip_code
    if specs.city:
        return specs.city
    return "USA"


def _fetch_raw_location(location: str, api_key: str) -> List[dict]:
    """Fetch raw listing items for a location, served from cache when fresh."""
    cached = _raw_cache.get(location)
    now = time.time()
    if cached and (now - cached["ts"]) < RAW_CACHE_TTL_SECONDS:
        logger.info("Using cached listings for '%s' (%d items).",
                    location, len(cached["items"]))
        return cached["items"]

    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": API_HOST,
    }

    items: List[dict] = []
    page = 1
    max_pages = 5  # safety cap on free tier

    while page <= max_pages:
        try:
            resp = requests.get(
                f"{BASE_URL}/bylocation",
                headers=headers,
                params={"location": location, "page": page},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("RapidAPI fetch error for '%s' (page %s): %s",
                           location, page, e)
            break

        results = data.get("results", [])
        if not results:
            break

        items.extend(results)

        if data.get("count", 0) <= page * len(results):
            break
        page += 1

    logger.info("Fetched %d raw listings for '%s'.", len(items), location)
    _raw_cache[location] = {"items": items, "ts": now}
    return items


def fetch_rapidapi_properties(specs: SearchSpecs, limit: int = 50) -> List[Property]:
    """
    Fetch real-time listings from the Zillow Live Data Scraper API
    (zillow-com-live-data-scraper-api) via the /bylocation endpoint.
    Requires RAPIDAPI_KEY in the environment.
    """
    api_key = os.environ.get("RAPIDAPI_KEY")
    if not api_key:
        logger.info("RAPIDAPI_KEY not found in environment. Returning empty list.")
        return []

    location = _build_location(specs)
    raw_items = _fetch_raw_location(location, api_key)

    properties: List[Property] = []
    skipped_no_data = 0

    for item in raw_items:
        if str(item.get("status", "")).upper() not in ("FOR_SALE", "FORSALE", ""):
            continue

        price = float(item.get("price") or 0)
        if price <= 0:
            continue

        beds = int(item.get("beds") or 0)
        baths = float(item.get("baths") or 0)
        sqft = int(item.get("sqft") or 0)

        # sqft drives the valuation engine — inventing it (old behavior:
        # price/200 estimate) would silently corrupt valuations. Skip instead.
        if sqft <= 0:
            skipped_no_data += 1
            continue

        if not _passes_filters(price, beds, baths, sqft, specs):
            continue

        ptype = _PTYPE_MAP.get(
            str(item.get("property_type", "")).upper(),
            PropertyType.SINGLE_FAMILY,
        )
        full_addr = item.get("address", "")
        city, state, zip_code = _parse_address(full_addr, specs)
        zpid = item.get("zpid", "")

        properties.append(Property(
            id=str(zpid),
            address=full_addr,
            city=city,
            state=state,
            zip_code=zip_code,
            latitude=item.get("latitude"),
            longitude=item.get("longitude"),
            list_price=price,
            property_type=ptype,
            bedrooms=beds,
            bathrooms=baths,
            sqft=sqft,
            condition=PropertyCondition.GOOD,
            source="RapidAPI-ZillowLive",
            image_url=item.get("photo_url"),
            url=item.get("url") or f"https://www.zillow.com/homedetails/{zpid}_zpid/",
        ))

        if len(properties) >= limit:
            break

    if skipped_no_data:
        logger.info("Skipped %d '%s' listings missing sqft/price data.",
                    skipped_no_data, location)
    logger.info("Returning %d filtered live listings for '%s'.",
                len(properties), location)
    return properties
