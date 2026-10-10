"""
Data Pipeline for the Home Finder.
Handles fetching property listings from multiple sources and normalizing them.
Includes realistic mock data generator for demo/development.
"""
import logging
import random
import hashlib
import math
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from models import Property, PropertyType, PropertyCondition, SearchSpecs
from rapidapi_zillow import fetch_rapidapi_properties
from homesteps_provider import fetch_homesteps_properties

logger = logging.getLogger(__name__)

# ── Property Registry ─────────────────────────────────────────────────────────
# Every listing served through fetch_live_listings is registered here so
# /api/property/{id}/valuation can look a property up directly instead of
# re-fetching (live listings shift between calls, which made ID scans fail).

_REGISTRY_CAP = 2000
_property_registry: "OrderedDict[str, Property]" = OrderedDict()


def register_listings(properties: List[Property]) -> None:
    """Store properties for later lookup by ID (most recent first)."""
    for prop in properties:
        _property_registry[prop.id] = prop
        _property_registry.move_to_end(prop.id)
    while len(_property_registry) > _REGISTRY_CAP:
        _property_registry.popitem(last=False)


def get_property_by_id(property_id: str) -> Optional[Property]:
    """Return a previously served property by ID, if still registered."""
    return _property_registry.get(property_id)

# ── Realistic Market Data for Mock Generation ─────────────────────────────────
# Based on real-world 2026 market averages

MARKET_DATA = {
    "Baltimore": {
        "state": "MD", "county": "Baltimore City",
        "median_sqft_price": 165, "lat": 39.2904, "lng": -76.6122,
        "zip_codes": ["21201", "21202", "21205", "21206", "21209", "21210",
                       "21211", "21212", "21213", "21214", "21215", "21216",
                       "21217", "21218", "21223", "21224", "21225", "21229",
                       "21230", "21231", "21234", "21236", "21237", "21239"],
        "neighborhoods": ["Canton", "Federal Hill", "Fells Point", "Hampden",
                          "Roland Park", "Mount Vernon", "Remington",
                          "Locust Point", "Charles Village", "Guilford",
                          "Inner Harbor", "Patterson Park", "Highlandtown"]
    },
    "Columbia": {
        "state": "MD", "county": "Howard County",
        "median_sqft_price": 235, "lat": 39.2037, "lng": -76.8610,
        "zip_codes": ["21044", "21045", "21046"],
        "neighborhoods": ["Wilde Lake", "Harper's Choice", "Owen Brown",
                          "Long Reach", "King's Contrivance", "River Hill"]
    },
    "Bethesda": {
        "state": "MD", "county": "Montgomery County",
        "median_sqft_price": 425, "lat": 38.9847, "lng": -77.0947,
        "zip_codes": ["20814", "20815", "20816", "20817"],
        "neighborhoods": ["Downtown Bethesda", "Burning Tree", "Bradley Hills",
                          "Glen Echo Heights", "Carderock Springs"]
    },
    "Silver Spring": {
        "state": "MD", "county": "Montgomery County",
        "median_sqft_price": 310, "lat": 38.9907, "lng": -77.0261,
        "zip_codes": ["20901", "20902", "20903", "20904", "20910"],
        "neighborhoods": ["Downtown", "Woodside", "East Silver Spring",
                          "North Hills", "Sligo Creek"]
    },
    "Annapolis": {
        "state": "MD", "county": "Anne Arundel County",
        "median_sqft_price": 295, "lat": 38.9784, "lng": -76.4922,
        "zip_codes": ["21401", "21402", "21403", "21409"],
        "neighborhoods": ["Historic District", "Eastport", "West Annapolis",
                          "Parole", "Bay Ridge"]
    },
    "Rockville": {
        "state": "MD", "county": "Montgomery County",
        "median_sqft_price": 345, "lat": 39.0840, "lng": -77.1528,
        "zip_codes": ["20850", "20851", "20852", "20853"],
        "neighborhoods": ["Town Center", "King Farm", "Fallsgrove",
                          "Twinbrook", "Woodley Gardens"]
    },
    "Frederick": {
        "state": "MD", "county": "Frederick County",
        "median_sqft_price": 215, "lat": 39.4143, "lng": -77.4105,
        "zip_codes": ["21701", "21702", "21703", "21704"],
        "neighborhoods": ["Downtown", "Baker Park", "Ballenger Creek",
                          "Westview", "Tuscarora"]
    },
    "Bowie": {
        "state": "MD", "county": "Prince George's County",
        "median_sqft_price": 205, "lat": 38.9429, "lng": -76.7303,
        "zip_codes": ["20715", "20716", "20720", "20721"],
        "neighborhoods": ["Bowie Town Center", "Northview", "Southview",
                          "Pointer Ridge", "Collington"]
    },
}

STREET_NAMES = [
    "Oak", "Maple", "Cedar", "Pine", "Elm", "Birch", "Willow", "Cherry",
    "Dogwood", "Magnolia", "Hickory", "Walnut", "Chestnut", "Poplar",
    "Sycamore", "Spruce", "Beech", "Laurel", "Holly", "Ivy",
    "Main", "Church", "Park", "Washington", "Liberty", "Franklin",
    "Jefferson", "Adams", "Madison", "Monroe", "Lincoln", "Grant",
    "Academy", "Bridge", "Center", "College", "Court", "Cross",
    "Garden", "Highland", "Lake", "Meadow", "Mill", "Pleasant",
    "Ridge", "River", "Spring", "Valley", "View", "Forest"
]

STREET_TYPES = ["St", "Ave", "Blvd", "Dr", "Ln", "Ct", "Way", "Pl", "Rd", "Cir"]


def _generate_property_id(address: str, city: str) -> str:
    return hashlib.md5(f"{address}-{city}".encode()).hexdigest()[:12]


def _random_address() -> str:
    num = random.randint(100, 9999)
    street = random.choice(STREET_NAMES)
    stype = random.choice(STREET_TYPES)
    return f"{num} {street} {stype}"


def _price_for_property(base_sqft_price: float, sqft: int, bedrooms: int,
                         bathrooms: float, year_built: int,
                         has_pool: bool, has_basement: bool,
                         has_garage: bool, condition: PropertyCondition,
                         lot_sqft: Optional[int]) -> float:
    """Calculate a realistic price based on property attributes."""
    # Base price from sqft
    price = base_sqft_price * sqft

    # Year built adjustment (newer = more valuable)
    age = 2026 - year_built
    if age < 5:
        price *= 1.15
    elif age < 15:
        price *= 1.08
    elif age < 30:
        price *= 1.0
    elif age < 50:
        price *= 0.92
    else:
        price *= 0.85

    # Condition adjustment
    condition_mult = {
        PropertyCondition.EXCELLENT: 1.12,
        PropertyCondition.GOOD: 1.0,
        PropertyCondition.FAIR: 0.88,
        PropertyCondition.POOR: 0.72,
        PropertyCondition.UNKNOWN: 0.95,
    }
    price *= condition_mult.get(condition, 1.0)

    # Feature premiums
    if has_pool:
        price += random.uniform(15000, 45000)
    if has_basement:
        price += random.uniform(10000, 35000)
    if has_garage:
        price += random.uniform(8000, 25000)

    # Bedroom / bathroom adjustments beyond baseline
    if bedrooms >= 4:
        price *= 1.05
    if bathrooms >= 3:
        price *= 1.04

    # Lot size premium (above 0.25 acres = 10890 sqft)
    if lot_sqft and lot_sqft > 10890:
        price += (lot_sqft - 10890) * random.uniform(2.5, 8.0)

    # Market noise (-8% to +8%)
    price *= random.uniform(0.92, 1.08)

    return round(price, -2)  # round to nearest 100


def _apply_specs_filter(props: List[Property],
                        specs: SearchSpecs) -> List[Property]:
    """Filter fetched listings against the search specs (HomeSteps has
    no server-side filtering; the mock and RapidAPI paths already
    apply specs at fetch time)."""
    def keep(p: Property) -> bool:
        if specs.zip_code and p.zip_code != specs.zip_code:
            return False
        if specs.min_price is not None and p.list_price < specs.min_price:
            return False
        if specs.max_price is not None and p.list_price > specs.max_price:
            return False
        if specs.min_bedrooms is not None and p.bedrooms < specs.min_bedrooms:
            return False
        if specs.max_bedrooms is not None and p.bedrooms > specs.max_bedrooms:
            return False
        if specs.min_bathrooms is not None and p.bathrooms < specs.min_bathrooms:
            return False
        if specs.max_bathrooms is not None and p.bathrooms > specs.max_bathrooms:
            return False
        if specs.min_sqft is not None and p.sqft < specs.min_sqft:
            return False
        if specs.max_sqft is not None and p.sqft > specs.max_sqft:
            return False
        if specs.property_types and p.property_type not in specs.property_types:
            return False
        if specs.min_year_built is not None and (
                p.year_built is None or p.year_built < specs.min_year_built):
            return False
        if specs.max_year_built is not None and (
                p.year_built is None or p.year_built > specs.max_year_built):
            return False
        if specs.must_have_basement and not p.has_basement:
            return False
        if specs.must_have_pool and not p.has_pool:
            return False
        if specs.must_have_garage and not p.has_garage:
            return False
        return True

    return [p for p in props if keep(p)]


def fetch_live_listings(specs: SearchSpecs, count: int = 50) -> List[Property]:
    """Fetch listings, preferring real sources at each tier:

    1. RapidAPI Zillow (full market inventory; needs quota)
    2. Freddie Mac HomeSteps REO (real but thin; no key)
    3. Mock generator (labeled demo data — last resort)
    """
    logger.info("Fetching realtime listings from Zillow via RapidAPI...")
    live_props = fetch_rapidapi_properties(specs, limit=max(count, 50))
    if live_props and len(live_props) > 0:
        logger.info("Successfully fetched %d live properties.", len(live_props))
        register_listings(live_props)
        return live_props

    logger.info("RapidAPI empty/failed — trying Freddie Mac HomeSteps REO.")
    reo_props = _apply_specs_filter(
        fetch_homesteps_properties(specs.city, specs.state, specs.zip_code),
        specs)
    if reo_props:
        logger.info("HomeSteps returned %d real REO listings.", len(reo_props))
        register_listings(reo_props)
        return reo_props

    logger.info("No real sources available — using mock listing generator.")
    mock_props = generate_mock_listings(specs, count=count)
    register_listings(mock_props)
    return mock_props


def _pick_city(specs: SearchSpecs) -> tuple[str, dict]:
    """Resolve the search to mock-generation market data.

    Known cities (currently MD) use their real market data. Unknown cities
    are generated under the *requested* name with a generic national-average
    $/sqft — never silently substituted with a different city.
    """
    if specs.city:
        for name in MARKET_DATA:
            if specs.city.lower() in name.lower() or name.lower() in specs.city.lower():
                return name, MARKET_DATA[name]
    if specs.zip_code:
        for name, data in MARKET_DATA.items():
            if specs.zip_code in data["zip_codes"]:
                return name, data
    # Match by state if we have data for it
    if specs.state:
        for name, data in MARKET_DATA.items():
            if data["state"].lower() == specs.state.lower():
                return name, data

    # Unknown area: honor the requested city name, generic market constants
    generic = {
        "state": specs.state or "US",
        "county": specs.county or (f"{specs.city} County" if specs.city
                                   else "Unknown County"),
        "median_sqft_price": 225,  # national single-family average
        "lat": 39.5, "lng": -98.35,  # geographic center of the US
        "zip_codes": [specs.zip_code] if specs.zip_code else ["00000"],
        "neighborhoods": [specs.city or "Citywide"],
    }
    return (specs.city or "Unknown City"), generic


def generate_mock_listings(specs: SearchSpecs, count: int = 50) -> List[Property]:
    """Generate realistic mock listings honoring the main search filters."""
    city, data = _pick_city(specs)
    base_ppsf = data["median_sqft_price"]

    conditions = [
        PropertyCondition.EXCELLENT, PropertyCondition.GOOD,
        PropertyCondition.GOOD, PropertyCondition.FAIR, PropertyCondition.POOR,
    ]
    ptypes = list(specs.property_types) if specs.property_types else [
        PropertyType.SINGLE_FAMILY, PropertyType.SINGLE_FAMILY,
        PropertyType.TOWNHOUSE, PropertyType.CONDO,
    ]

    out: List[Property] = []
    attempts = 0
    while len(out) < count and attempts < count * 6:
        attempts += 1
        bedrooms = random.randint(2, 6)
        bathrooms = round(random.uniform(1, 4) * 2) / 2
        sqft = random.randint(900, 4500)
        year_built = random.randint(1920, 2025)
        has_pool = random.random() < 0.18
        has_basement = random.random() < 0.55
        has_garage = random.random() < 0.7
        condition = random.choice(conditions)
        lot_sqft = random.randint(2000, 30000)

        price = _price_for_property(
            base_ppsf, sqft, bedrooms, bathrooms, year_built,
            has_pool, has_basement, has_garage, condition, lot_sqft,
        )

        # Apply spec filters
        if specs.min_price and price < specs.min_price:
            continue
        if specs.max_price and price > specs.max_price:
            continue
        if specs.min_bedrooms and bedrooms < specs.min_bedrooms:
            continue
        if specs.max_bedrooms and bedrooms > specs.max_bedrooms:
            continue
        if specs.min_bathrooms and bathrooms < specs.min_bathrooms:
            continue
        if specs.min_sqft and sqft < specs.min_sqft:
            continue
        if specs.max_sqft and sqft > specs.max_sqft:
            continue
        if specs.must_have_pool and not has_pool:
            continue
        if specs.must_have_basement and not has_basement:
            continue
        if specs.must_have_garage and not has_garage:
            continue

        address = _random_address()
        zip_code = specs.zip_code or random.choice(data["zip_codes"])
        days = random.randint(1, 180)
        out.append(Property(
            id=_generate_property_id(address + str(attempts), city),
            address=address,
            city=city,
            state=data["state"],
            zip_code=zip_code,
            county=data["county"],
            latitude=data["lat"] + random.uniform(-0.05, 0.05),
            longitude=data["lng"] + random.uniform(-0.05, 0.05),
            list_price=price,
            property_type=random.choice(ptypes),
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            sqft=sqft,
            lot_sqft=lot_sqft,
            year_built=year_built,
            garage_spaces=random.randint(1, 3) if has_garage else 0,
            condition=condition,
            has_pool=has_pool,
            has_basement=has_basement,
            has_garage=has_garage,
            has_fireplace=random.random() < 0.4,
            has_central_air=random.random() < 0.8,
            hoa_fee=random.choice([0, 0, 0, 50, 120, 250, 400]),
            days_on_market=days,
            listing_date=datetime.now() - timedelta(days=days),
            source="mock-generator",
            url=None,
            annual_tax=round(price * random.uniform(0.008, 0.018), 0),
        ))

    logger.info("Generated %d mock listings for %s.", len(out), city)
    return out


def get_market_sqft_price(city: str) -> float:
    """Get the market $/sqft for a city."""
    for name, data in MARKET_DATA.items():
        if city.lower() in name.lower():
            return data["median_sqft_price"]
    # Default fallback
    return 225.0


def get_all_cities() -> List[Dict]:
    """Return all supported city data."""
    return [
        {"name": k, "state": v["state"], "county": v["county"],
         "median_sqft_price": v["median_sqft_price"]}
        for k, v in MARKET_DATA.items()
    ]
