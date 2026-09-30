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
