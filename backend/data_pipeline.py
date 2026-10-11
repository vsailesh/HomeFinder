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
    # Multi-state expansion — Freddie Mac HomeSteps has real REO
    # inventory in each of these metros (probed 2026-10-11), and
    # Zillow Research baselines cover all of them.
    "Charlotte": {
        "state": "NC", "county": "Mecklenburg County",
        "median_sqft_price": 195, "lat": 35.2271, "lng": -80.8431,
        "zip_codes": ["28202", "28203", "28204", "28205", "28206",
                      "28207", "28208", "28209", "28210", "28212",
                      "28213", "28227", "28262", "28273"],
        "neighborhoods": ["Uptown", "NoDa", "Dilworth", "Myers Park",
                          "South End", "Plaza Midwood", "Elizabeth",
                          "Ballantyne"]
    },
    "Raleigh": {
        "state": "NC", "county": "Wake County",
        "median_sqft_price": 195, "lat": 35.7796, "lng": -78.6382,
        "zip_codes": ["27601", "27603", "27604", "27605", "27606",
                      "27607", "27608", "27609", "27610", "27612",
                      "27613", "27614", "27615", "27616"],
        "neighborhoods": ["Downtown", "Five Points", "Hayes Barton",
                          "Cameron Village", "North Hills", "Oakwood",
                          "Mordecai"]
    },
    "Tampa": {
        "state": "FL", "county": "Hillsborough County",
        "median_sqft_price": 215, "lat": 27.9506, "lng": -82.4572,
        "zip_codes": ["33602", "33603", "33604", "33605", "33606",
                      "33607", "33609", "33610", "33611", "33612",
                      "33629"],
        "neighborhoods": ["Hyde Park", "Ybor City", "Seminole Heights",
                          "Downtown", "Channelside", "Davis Islands",
                          "Tampa Heights"]
    },
    "Jacksonville": {
        "state": "FL", "county": "Duval County",
        "median_sqft_price": 165, "lat": 30.3322, "lng": -81.6557,
        "zip_codes": ["32202", "32204", "32205", "32206", "32207",
                      "32208", "32210", "32211", "32216", "32217",
                      "32250"],
        "neighborhoods": ["Riverside", "Avondale", "San Marco",
                          "Springfield", "Five Points", "Brooklyn"]
    },
    "Atlanta": {
        "state": "GA", "county": "Fulton County",
        "median_sqft_price": 175, "lat": 33.7490, "lng": -84.3880,
        "zip_codes": ["30303", "30305", "30306", "30307", "30308",
                      "30309", "30310", "30311", "30312", "30314",
                      "30315", "30316", "30317", "30319", "30324"],
        "neighborhoods": ["Midtown", "Old Fourth Ward", "Inman Park",
                          "West End", "Buckhead", "Cabbagetown",
                          "Reynoldstown"]
    },
    "Chicago": {
        "state": "IL", "county": "Cook County",
        "median_sqft_price": 175, "lat": 41.8781, "lng": -87.6298,
        "zip_codes": ["60601", "60602", "60605", "60607", "60608",
                      "60610", "60614", "60616", "60618", "60622",
                      "60625", "60657"],
        "neighborhoods": ["Lincoln Park", "Logan Square", "Pilsen",
                          "Bronzeville", "Hyde Park", "Wicker Park",
                          "Lakeview"]
    },
    "Cleveland": {
        "state": "OH", "county": "Cuyahoga County",
        "median_sqft_price": 105, "lat": 41.4993, "lng": -81.6944,
        "zip_codes": ["44102", "44103", "44104", "44105", "44106",
                      "44107", "44108", "44109", "44110", "44113",
                      "44114", "44115", "44120"],
        "neighborhoods": ["Ohio City", "Tremont", "Detroit-Shoreway",
                          "Edgewater", "University Circle", "Gordon Square"]
    },
    "Detroit": {
        "state": "MI", "county": "Wayne County",
        "median_sqft_price": 75, "lat": 42.3314, "lng": -83.0458,
        "zip_codes": ["48201", "48202", "48204", "48206", "48207",
                      "48208", "48209", "48210", "48212", "48213",
                      "48214", "48216", "48219", "48226", "48238"],
        "neighborhoods": ["Corktown", "Midtown", "Downtown",
                          "Eastern Market", "Southwest Detroit",
                          "Palmer Woods"]
    },
    "Kansas City": {
        "state": "MO", "county": "Jackson County",
        "median_sqft_price": 140, "lat": 39.0997, "lng": -94.5786,
        "zip_codes": ["64101", "64102", "64105", "64106", "64108",
                      "64109", "64110", "64111", "64112", "64113",
                      "64123", "64124", "64127", "64128", "64130"],
        "neighborhoods": ["River Market", "Crossroads", "Westport",
                          "Brookside", "Waldo", "Country Club Plaza",
                          "Columbus Park"]
    },
    "Philadelphia": {
        "state": "PA", "county": "Philadelphia County",
        "median_sqft_price": 130, "lat": 39.9526, "lng": -75.1652,
        "zip_codes": ["19102", "19103", "19104", "19106", "19107",
                      "19119", "19120", "19121", "19122", "19123",
                      "19125", "19127", "19128", "19130", "19143",
                      "19146", "19147", "19148"],
        "neighborhoods": ["Fishtown", "Graduate Hospital", "Point Breeze",
                          "Northern Liberties", "West Philadelphia",
                          "South Philadelphia", "Manayunk"]
    },
    "Phoenix": {
        "state": "AZ", "county": "Maricopa County",
        "median_sqft_price": 230, "lat": 33.4484, "lng": -112.0740,
        "zip_codes": ["85004", "85006", "85007", "85008", "85009",
                      "85012", "85014", "85015", "85016", "85018",
                      "85020", "85028"],
        "neighborhoods": ["Downtown", "Roosevelt Row", "Arcadia",
                          "Biltmore", "Melrose", "Sunnyslope"]
    },
    "Indianapolis": {
        "state": "IN", "county": "Marion County",
        "median_sqft_price": 125, "lat": 39.7684, "lng": -86.1581,
        "zip_codes": ["46201", "46202", "46203", "46204", "46205",
                      "46208", "46218", "46220", "46222", "46225",
                      "46226", "46227", "46228"],
        "neighborhoods": ["Fountain Square", "Broad Ripple", "Mass Ave",
                          "Irvington", "Butler-Tarkington", "Downtown"]
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
