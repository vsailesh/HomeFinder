"""
Home Finder & Optimizer – FastAPI Backend
Serves property data, valuations, and optimized deal rankings.
"""
import asyncio
import logging
import os
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from models import (Property, SearchSpecs, PropertyType, LoanQuoteRequest,
                    LoanQuoteResponse, ProjectionRequest)
from optimizer import optimize_search, score_deal_from_property
from data_pipeline import get_all_cities, get_property_by_id
from valuation_engine import valuate_property
from loan_engine import get_market_base_rate, quote_loan
from market_baselines import get_baselines_snapshot, get_metro_baseline
from projection import build_projection
from heatmap import build_heatmap
import reo_tracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Background REO sweep on cold start (freshness-gated, killable
    # via REO_SWEEP_ON_STARTUP=0) — never blocks serving.
    threading.Thread(target=reo_tracker.maybe_sweep_on_startup,
                     name="reo-startup-sweep", daemon=True).start()
    yield


app = FastAPI(
    title="Home Finder & Optimizer API",
    description="Find the best real estate deals with variable-by-variable price analysis",
    version="1.0.0",
    lifespan=lifespan,
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
    """List all supported cities with market data, joined with the
    real metro trend from Zillow Research where available."""
    cities = []
    for city in get_all_cities():
        baseline = get_metro_baseline(city["name"], city["state"])
        entry = dict(city)
        if baseline:
            entry["metro_appreciation_1y"] = baseline.get(
                "appreciation_1y")
            entry["metro_median_list_price"] = baseline.get(
                "median_list_price")
            entry["metro_as_of"] = baseline.get("as_of")
        cities.append(entry)
    return {"cities": cities}


@app.get("/api/market/baselines")
async def market_baselines():
    """Real per-metro baselines from Zillow Research public data
    (trailing-12mo appreciation, typical value, median list price)."""
    return get_baselines_snapshot()


@app.get("/api/market/heatmap")
def market_heatmap():
    """Per-metro investor comparison: carry vs rent on the typical
    home at the live rate. Sync def on purpose — a cold run fetches
    the Zillow Research CSVs (multi-MB) and must stay off the event
    loop (same rationale as the projection endpoint)."""
    return build_heatmap()


@app.post("/api/reo/sweep")
async def reo_sweep(force: bool = False, request: Request = None):
    """Trigger a HomeSteps REO sweep across all served metros.

    Protected: requires the X-Sweep-Token header to match the
    SWEEP_TOKEN env var. Refuses everyone while SWEEP_TOKEN is unset
    (request.client.host is unreliable behind the Render proxy, and
    local runs get the startup sweep for free).
    """
    expected = os.environ.get("SWEEP_TOKEN", "")
    provided = (request.headers.get("X-Sweep-Token") or "") if request else ""
    if not expected or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=403,
            detail="Sweep endpoint locked. Set SWEEP_TOKEN on the server "
                   "and send it as the X-Sweep-Token header.")
    result = await asyncio.to_thread(reo_tracker.run_sweep, force=force)
    return result


@app.get("/api/reo/inventory")
async def reo_inventory(city: Optional[str] = None,
                        days: int = Query(default=7, ge=1, le=30),
                        include_inactive: bool = False):
    """Tracked Freddie Mac REO inventory across metros: active
    listings with new-this-window / price-cut flags and history."""
    return reo_tracker.get_inventory(city=city, days=days,
                                     include_inactive=include_inactive)


@app.get("/api/reo/listing/{listing_id}")
def reo_listing_detail(listing_id: str):
    """One tracked REO listing by id: tracker record, full price
    history, and a scored deal (same valuation/scoring as search).
    SQLite-backed, so it survives deploys and serves listings the
    in-memory registry never saw — active or long gone. Valuation
    failure degrades to the tracker record alone (deal: null)."""
    listing = reo_tracker.get_listing_detail(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Unknown listing id")

    deal = None
    try:
        prop = Property(
            id=listing["id"], address=listing["address"],
            city=listing["city"], state=listing["state"],
            zip_code=listing["zip_code"],
            latitude=listing["latitude"], longitude=listing["longitude"],
            list_price=listing["list_price"],
            property_type=PropertyType(
                listing["property_type"] or "single_family"),
            bedrooms=listing["bedrooms"] or 0,
            bathrooms=listing["bathrooms"] or 0.0,
            sqft=listing["sqft"] or 0,
            sqft_estimated=True,
            year_built=listing["year_built"],
            url=listing["url"], image_url=listing["image_url"],
            source="homesteps-freddie-mac",
        )
        # The swept metro tag, not the (often suburb) listing city —
        # 'Gwynn Oak' resolves to no Zillow metro, 'Baltimore' does.
        deal = score_deal_from_property(
            prop, location=listing.get("metro")).model_dump()
    except Exception:
        logger.exception("Listing %s valuation failed — serving the "
                         "tracker record only", listing_id)

    return {"listing": listing, "deal": deal}


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
    min_rent_coverage: Optional[float] = Query(default=None, ge=0),
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
        min_rent_coverage=min_rent_coverage,
        sort_by=sort_by,
    )

    results = optimize_search(specs, page=page, page_size=page_size)
    _attach_reo_tracker(results)
    return results


def _attach_reo_tracker(results: dict) -> None:
    """Enrich HomeSteps deals in search results with tracker state
    (new sighting / price-cut history). Other sources untouched.
    Deals arrive as dicts (optimizer model_dumps them)."""
    deals = results.get("deals", [])
    reo_ids = [d["property"]["id"] for d in deals
               if d["property"].get("source") == "homesteps-freddie-mac"]
    if not reo_ids:
        return
    try:
        state = reo_tracker.get_tracker_state(reo_ids)
    except Exception:
        logger.exception("REO tracker enrichment failed (non-fatal)")
        return
    for d in deals:
        if d["property"]["id"] in state:
            d["reo_tracker"] = state[d["property"]["id"]]


@app.post("/api/property/projection")
def property_projection(req: ProjectionRequest):
    """10-year hold projection: rent vs full carry year by year, plus
    value appreciation, amortization, equity build, and net position at
    exit. Inputs come from the client's deal object (no server-side
    property lookup — live caches shift between calls).

    Plain `def` (not async): a cache-cold build fetches multi-MB Zillow
    Research CSVs, which must run in the threadpool — not on the event
    loop, where it would stall every concurrent request."""
    return build_projection(
        list_price=req.list_price,
        estimated_value=req.estimated_value,
        city=req.city,
        state=req.state,
        zip_code=req.zip_code,
        annual_tax=req.annual_tax,
        hoa_fee=req.hoa_fee,
    )


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
