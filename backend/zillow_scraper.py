"""
Zillow Scraper Engine (Playwright)
Uses a real headless browser to bypass advanced anti-bot protections.
"""
import json
import asyncio
from typing import List, Optional
from bs4 import BeautifulSoup
from models import Property, PropertyType, PropertyCondition, SearchSpecs
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from playwright_stealth import stealth

def build_zillow_url(specs: SearchSpecs) -> str:
    location_parts = []
    if specs.city:
        location_parts.append(specs.city.replace(' ', '-'))
    if specs.state:
        location_parts.append(specs.state)
    elif not location_parts and specs.zip_code:
        location_parts.append(specs.zip_code)

    location_str = "-".join(location_parts) if location_parts else "USA"
    return f"https://www.zillow.com/homes/{location_str}_rb/"


async def async_scrape_zillow(specs: SearchSpecs, limit: int = 50) -> List[Property]:
    url = build_zillow_url(specs)
    print(f"Scraping Zillow URL via Playwright: {url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        # Add basic stealth scripts or headers if needed
        page = await context.new_page()
        await stealth(page)
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            # Wait a bit just in case
            await asyncio.sleep(2)
            content = await page.content()
        except Exception as e:
            print(f"Playwright navigation error: {e}")
            await browser.close()
            return []

        await browser.close()

    soup = BeautifulSoup(content, "html.parser")
    next_data_tag = soup.find("script", id="__NEXT_DATA__")
    if not next_data_tag:
        print("Scraper failed to find Next.js __NEXT_DATA__ JSON blob. Captcha blocked?")
        return []

    try:
        data = json.loads(next_data_tag.string)
    except json.JSONDecodeError as e:
        print(f"Scraper failed to parse Next.js JSON blob: {e}")
        return []

    try:
        search_state = data["props"]["pageProps"]["searchPageState"]
        list_results = search_state.get("cat1", {}).get("searchResults", {}).get("listResults", [])
    except KeyError as e:
        print(f"Scraper payload structure changed: missing key {e}")
        list_results = []

    properties = []
    for item in list_results:
        if "id" not in item:
            continue

        z_type = item.get("statusType", "FOR_SALE")
        hdp = item.get("hdpData", {}).get("homeInfo", {})
        
        home_type = hdp.get("homeType", "SINGLE_FAMILY")
        prop_type = PropertyType.SINGLE_FAMILY
        if home_type == "CONDO":
            prop_type = PropertyType.CONDO
        elif home_type == "TOWNHOUSE":
            prop_type = PropertyType.TOWNHOUSE
        elif home_type == "MULTI_FAMILY":
            prop_type = PropertyType.MULTI_FAMILY
            
        list_price = item.get("unformattedPrice") or hdp.get("price")
        if not list_price:
            continue
            
        sqft = item.get("area") or hdp.get("livingArea")
        bedrooms = item.get("beds") or hdp.get("bedrooms", 0)
        bathrooms = item.get("baths") or hdp.get("bathrooms", 0)
        zip_code = item.get("addressZipcode") or hdp.get("zipcode", "")
        city = item.get("addressCity") or hdp.get("city", "")
        state = item.get("addressState") or hdp.get("state", "")
        address = item.get("addressStreet") or hdp.get("streetAddress", "")
        lat = item.get("latLong", {}).get("latitude")
        lng = item.get("latLong", {}).get("longitude")
        
        year_built = hdp.get("yearBuilt")
        days_on_market = hdp.get("daysOnZillow", 0)
        condition = PropertyCondition.GOOD
        
        properties.append(Property(
            id=item["id"],
            address=address,
            city=city,
            state=state,
            zip_code=zip_code,
            latitude=lat,
            longitude=lng,
            list_price=list_price,
            property_type=prop_type,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            sqft=sqft if sqft else int(list_price / 200),
            year_built=year_built,
            condition=condition,
            days_on_market=days_on_market,
            listing_date=datetime.now() - timedelta(days=days_on_market),
            source="Zillow",
            url=item.get("detailUrl"),
            image_url=item.get("imgSrc"),
            tax_assessed_value=hdp.get("taxAssessedValue"),
            annual_tax=hdp.get("taxAssessedValue", 0) * 0.01 if hdp.get("taxAssessedValue") else None
        ))

        if len(properties) >= limit:
            break

    filtered = []
    for p in properties:
        if specs.min_price and p.list_price < specs.min_price: continue
        if specs.max_price and p.list_price > specs.max_price: continue
        if specs.min_bedrooms and p.bedrooms < specs.min_bedrooms: continue
        if specs.min_sqft and p.sqft < specs.min_sqft: continue
        filtered.append(p)

    return filtered

def scrape_zillow_properties(specs: SearchSpecs, limit: int = 50) -> List[Property]:
    """Synchronous wrapper for the async scraper."""
    import nest_asyncio
    nest_asyncio.apply()
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(async_scrape_zillow(specs, limit))
