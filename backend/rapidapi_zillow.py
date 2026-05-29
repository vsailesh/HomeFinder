import os
import requests
from typing import List, Optional
from datetime import datetime
from models import Property, PropertyType, PropertyCondition, SearchSpecs

API_HOST = "zillow-com-live-data-scraper-api.p.rapidapi.com"
BASE_URL = f"https://{API_HOST}"

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


def fetch_rapidapi_properties(specs: SearchSpecs, limit: int = 50) -> List[Property]:
    """
    Fetch real-time listings from the Zillow Live Data Scraper API
    (zillow-com-live-data-scraper-api) via the /bylocation endpoint.
    Requires RAPIDAPI_KEY in the environment.
    """
    api_key = os.environ.get("RAPIDAPI_KEY")
    if not api_key:
        print("RAPIDAPI_KEY not found in environment. Returning empty list.")
        return []

    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": API_HOST,
    }
    location = _build_location(specs)

    properties: List[Property] = []
    page = 1
    max_pages = 5  # safety cap on free tier

    while len(properties) < limit and page <= max_pages:
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
            print(f"RapidAPI fetch error (page {page}): {e}")
            break

        results = data.get("results", [])
        if not results:
            break

        for item in results:
            if str(item.get("status", "")).upper() not in ("FOR_SALE", "FORSALE", ""):
                continue

            price = float(item.get("price") or 0)
            if price <= 0:
                continue

            beds = int(item.get("beds") or 0)
            baths = float(item.get("baths") or 0)
            sqft = int(item.get("sqft") or 0)

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
                sqft=sqft or int(price / 200),
                condition=PropertyCondition.GOOD,
                source="RapidAPI-ZillowLive",
                image_url=item.get("photo_url"),
                url=item.get("url") or f"https://www.zillow.com/homedetails/{zpid}_zpid/",
            ))

            if len(properties) >= limit:
                break

        # No more pages available
        if len(results) < 1 or data.get("count", 0) <= page * len(results):
            break
        page += 1

    print(f"Fetched {len(properties)} live listings for '{location}'.")
    return properties
