"""
Home Finder & Optimizer – FastAPI Backend
Serves property data, valuations, and optimized deal rankings.
"""
import logging
import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from models import SearchSpecs, PropertyType, LoanQuoteRequest, LoanQuoteResponse
from optimizer import optimize_search
from data_pipeline import get_all_cities, get_property_by_id
from valuation_engine import valuate_property
from loan_engine import get_market_base_rate, quote_loan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Home Finder & Optimizer API",
    description="Find the best real estate deals with variable-by-variable price analysis",
    version="1.0.0",
)

# Comma-separated allowlist, e.g. ALLOWED_ORIGINS=https://app.example.com,https://other.com
# Defaults to wildcard (no credentials — wildcard+credentials is rejected by browsers).
_origins_env = os.environ.get("ALLOWED_ORIGINS", "*").strip()
_allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "online", "service": "Home Finder & Optimizer API"}


@app.get("/api/cities")
async def list_cities():
    """List all supported cities with market data."""
    return {"cities": get_all_cities()}


@app.get("/api/search")
async def search_properties(
    city: Optional[str] = None,
    state: Optional[str] = None,
    zip_code: Optional[str] = None,
    county: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_bedrooms: Optional[int] = None,
    max_bedrooms: Optional[int] = None,
    min_bathrooms: Optional[float] = None,
    max_bathrooms: Optional[float] = None,
    min_sqft: Optional[int] = None,
    max_sqft: Optional[int] = None,
    property_type: Optional[str] = None,
    min_year_built: Optional[int] = None,
    max_year_built: Optional[int] = None,
    max_hoa: Optional[float] = None,
    must_have_pool: bool = False,
    must_have_basement: bool = False,
    must_have_garage: bool = False,
    max_days_on_market: Optional[int] = None,
    sort_by: str = "deal_score",
    page: Optional[int] = Query(default=None, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """
    Search properties and get optimized deal rankings.
    Returns properties scored and ranked with full price variable breakdown.

    Pass page (1-indexed) for paginated results; omit it to get everything.
    """
    property_types = None
    if property_type:
        try:
            property_types = [PropertyType(property_type)]
        except ValueError:
            pass

    specs = SearchSpecs(
        city=city,
        state=state,
        zip_code=zip_code,
        county=county,
        min_price=min_price,
        max_price=max_price,
        min_bedrooms=min_bedrooms,
        max_bedrooms=max_bedrooms,
        min_bathrooms=min_bathrooms,
        max_bathrooms=max_bathrooms,
        min_sqft=min_sqft,
        max_sqft=max_sqft,
        property_types=property_types,
        min_year_built=min_year_built,
        max_year_built=max_year_built,
        max_hoa=max_hoa,
        must_have_pool=must_have_pool,
        must_have_basement=must_have_basement,
        must_have_garage=must_have_garage,
        max_days_on_market=max_days_on_market,
        sort_by=sort_by,
    )

    results = optimize_search(specs, page=page, page_size=page_size)
    return results


@app.get("/api/property/{property_id}/valuation")
async def get_property_valuation(property_id: str):
    """Get detailed valuation for a specific property.

    Looks the property up in the in-memory registry of previously served
    listings (live fetches shift between calls, so re-searching for the ID
    is unreliable). Run a search first, then request a detail valuation.
    """
    prop = get_property_by_id(property_id)
    if prop is None:
        raise HTTPException(
            status_code=404,
            detail="Property not found. It may be outside the current "
                   "search cache — run a search for its area first.",
        )
    val = valuate_property(prop)
    return {
        "property": prop.model_dump(),
        "valuation": val.model_dump(),
    }


@app.get("/api/loan/rate")
async def loan_base_rate(force_refresh: bool = False):
    """Current 30yr fixed market base rate (live from FRED, cached)."""
    info = get_market_base_rate(force_refresh=force_refresh)
    return {
        "base_rate": round(info["rate"], 3),
        "source": info["source"],
        "as_of": info.get("as_of"),
    }


@app.post("/api/loan/quote", response_model=LoanQuoteResponse)
async def loan_quote(req: LoanQuoteRequest):
    """Prorated mortgage quote from borrower + property profile."""
    q = quote_loan(
        home_price=req.home_price,
        down_payment=req.down_payment,
        annual_income=req.annual_income,
        monthly_debts=req.monthly_debts,
        credit_score=req.credit_score,
        property_type=req.property_type,
        loan_term=req.loan_term,
        loan_type=req.loan_type,
        annual_property_tax=req.annual_property_tax,
        annual_home_insurance=req.annual_home_insurance,
        monthly_hoa=req.monthly_hoa,
        base_rate_override=req.base_rate_override,
    )
    return LoanQuoteResponse(**q.__dict__)


@app.get("/api/debug/source")
async def debug_data_source():
    """Diagnose why live listings may not be loading.

    Reports (without leaking the key) whether RAPIDAPI_KEY is set and
    the outcome of a single direct RapidAPI call, including the HTTP
    status and a trimmed error/message body.
    """
    import requests as _requests
    import rapidapi_zillow as _rz

    api_key = os.environ.get("RAPIDAPI_KEY", "")
    diag = {
        "key_present": bool(api_key),
        "key_length": len(api_key),
        "key_prefix": api_key[:6] + "…" if api_key else None,
    }

    if not api_key:
        diag["verdict"] = "RAPIDAPI_KEY not set in this service's environment"
        return diag

    try:
        resp = _requests.get(
            f"{_rz.BASE_URL}/bylocation",
            headers={"x-rapidapi-key": api_key, "x-rapidapi-host": _rz.API_HOST},
            params={"location": "Bethesda, MD", "page": 1},
            timeout=20,
        )
        diag["rapidapi_http_status"] = resp.status_code
        body = resp.text[:400]
        diag["rapidapi_body_head"] = body
        if resp.status_code == 200:
            try:
                payload = resp.json() or {}
            except ValueError:
                payload = {}
            if payload.get("success") is False:
                diag["verdict"] = (
                    "Key accepted, but the API's own upstream scrape is "
                    "failing (its 'Data Unavailable' error). Provider-side "
                    "outage — nothing wrong with your key. Retry later or "
                    "check the API's status/plan on RapidAPI."
                )
            else:
                results = payload.get("results", [])
                diag["results_on_page1"] = len(results)
                diag["verdict"] = (
                    "Key works — API is returning data. If the app still "
                    "shows mock data, the search location may have no "
                    "FOR_SALE results."
                    if results else
                    "Key works but page 1 returned zero results for Bethesda, MD"
                )
        elif resp.status_code in (401, 403):
            diag["verdict"] = ("Key rejected — invalid key, or no active "
                               "subscription to zillow-com-live-data-scraper-api")
        elif resp.status_code == 429:
            diag["verdict"] = "Quota exceeded — free plan limit or rate limit hit"
        else:
            diag["verdict"] = f"Unexpected RapidAPI HTTP {resp.status_code}"
    except Exception as e:
        diag["verdict"] = f"Request failed before HTTP: {type(e).__name__}: {e}"

    return diag


@app.get("/api/status")
async def get_system_status():
    """Return system status and health information."""
    import platform

    return {
        "status": "healthy",
        "service": "Home Finder & Optimizer API",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": {
            "platform": platform.system(),
            "python_version": platform.python_version(),
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
