import os
import requests
from typing import List
from datetime import datetime, timedelta
from models import Property, PropertyType, PropertyCondition, SearchSpecs

def fetch_rapidapi_properties(specs: SearchSpecs, limit: int = 50) -> List[Property]:
    """
    Fetch real-time data from Zillow.com RapidAPI.
    Requires RAPIDAPI_KEY in the environment.
    """
    api_key = os.environ.get("RAPIDAPI_KEY")
    if not api_key:
        print("RAPIDAPI_KEY not found in environment. Returning empty list.")
        return []

    url = "https://zillow-com1.p.rapidapi.com/propertyExtendedSearch"
    
    # Construct location string
    location = "USA"
    if specs.city and specs.state:
        location = f"{specs.city}, {specs.state}"
    elif specs.zip_code:
        location = specs.zip_code
        
    querystring = {
        "location": location,
        "home_type": "Houses,Condos,Townhomes",
        "status_type": "ForSale"
    }
    
    if specs.min_bedrooms:
        querystring["bedsMin"] = specs.min_bedrooms
    if specs.max_bedrooms:
        querystring["bedsMax"] = specs.max_bedrooms
    if specs.min_bathrooms:
        querystring["bathsMin"] = specs.min_bathrooms
    if specs.min_price:
        querystring["minPrice"] = specs.min_price
    if specs.max_price:
        querystring["maxPrice"] = specs.max_price
    if specs.min_sqft:
        querystring["sqftMin"] = specs.min_sqft

    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "zillow-com1.p.rapidapi.com"
    }

    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"RapidAPI fetch error: {e}")
        return []

    properties = []
    results = data.get("props", [])
    
    for item in results:
        prop_type = PropertyType.SINGLE_FAMILY
        ht = item.get("propertyType", "").upper()
        if "CONDO" in ht:
            prop_type = PropertyType.CONDO
        elif "TOWNHOUSE" in ht:
            prop_type = PropertyType.TOWNHOUSE
        elif "MULTI_FAMILY" in ht:
            prop_type = PropertyType.MULTI_FAMILY
            
        list_price = item.get("price", 0)
        if list_price == 0:
            continue
            
        days = item.get("daysOnZillow", 0)
        
        properties.append(Property(
            id=str(item.get("zpid", "")),
            address=item.get("address", ""),
            city=specs.city or "Unknown",
            state=specs.state or "Unk",
            zip_code=specs.zip_code or "00000",
            latitude=item.get("latitude", 0),
            longitude=item.get("longitude", 0),
            list_price=list_price,
            property_type=prop_type,
            bedrooms=item.get("bedrooms", 0),
            bathrooms=item.get("bathrooms", 0),
            sqft=item.get("livingArea", 0) or int(list_price / 200),
            year_built=item.get("yearBuilt"),
            condition=PropertyCondition.GOOD,
            days_on_market=days,
            listing_date=datetime.now() - timedelta(days=days),
            source="RapidAPI-Zillow",
            image_url=item.get("imgSrc"),
            url=f"https://www.zillow.com/homedetails/{item.get('zpid')}_zpid/",
            has_pool=specs.must_have_pool,
            has_garage=specs.must_have_garage,
        ))
        
        if len(properties) >= limit:
            break
            
    return properties
