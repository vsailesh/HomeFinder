"""
Data Pipeline for the Home Finder.
Handles fetching property listings from multiple sources and normalizing them.
Includes realistic mock data generator for demo/development.
"""
import random
import hashlib
import math
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from models import Property, PropertyType, PropertyCondition, SearchSpecs
from rapidapi_zillow import fetch_rapidapi_properties

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


def fetch_live_listings(specs: SearchSpecs, count: int = 50) -> List[Property]:
    """Fetch realtime listings from RapidAPI Zillow."""
    print("Fetching realtime listings from Zillow via RapidAPI...")
    live_props = fetch_rapidapi_properties(specs, limit=max(count, 50))
    if live_props and len(live_props) > 0:
        print(f"Successfully scraped {len(live_props)} properties realtime.")
        return live_props
    else:
        print("API returned empty results or failed.")
        
    return []


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
