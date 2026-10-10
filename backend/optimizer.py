"""
Deal Optimizer for the Home Finder.
Scores and ranks properties based on the gap between estimated value
and asking price, factoring in risk and investment potential.
"""
import logging
import statistics
from typing import List, Optional
from models import (
    Property, SearchSpecs, DealScore, ValuationResult, MarketStats,
    PropertyCondition
)
from valuation_engine import valuate_property, ValuationError
from data_pipeline import fetch_live_listings, get_market_sqft_price
from loan_engine import get_market_base_rate
from market_baselines import get_metro_baseline

logger = logging.getLogger(__name__)

# Fallback appreciation for the 5yr ROI projection when the search metro
# has no match in Zillow Research data (or the data is unreachable).
APPRECIATION_ASSUMPTION = 0.035


def _calculate_monthly_payment(price: float, down_pct: float = 0.20,
                                rate: Optional[float] = None,
                                years: int = 30) -> float:
    """Estimate monthly mortgage payment (P&I only).

    Rate is an annual percentage (e.g. 6.85); pulled live from FRED when
    not supplied.
    """
    if rate is None:
        rate = get_market_base_rate()["rate"]
    loan = price * (1 - down_pct)
    monthly_rate = rate / 100 / 12
    n = years * 12
    if monthly_rate == 0:
        return loan / n
    payment = loan * (monthly_rate * (1 + monthly_rate)**n) / \
              ((1 + monthly_rate)**n - 1)
    return round(payment, 2)


def _estimate_5yr_roi(prop: Property, estimated_value: float,
                      appreciation: Optional[float] = None) -> float:
    """Rough 5-year ROI estimate based on appreciation + equity."""
    if appreciation is None:
        appreciation = APPRECIATION_ASSUMPTION
    future_value = estimated_value * (1 + appreciation) ** 5
    down_payment = prop.list_price * 0.20
    equity_gained = future_value - prop.list_price
    roi = (equity_gained / max(down_payment, 1)) * 100
    return round(roi, 2)


def _grade_from_score(score: float) -> str:
    """Convert numeric score to letter grade."""
    if score >= 90:
        return "A+"
    elif score >= 80:
        return "A"
    elif score >= 70:
        return "B+"
    elif score >= 60:
        return "B"
    elif score >= 50:
        return "C+"
    elif score >= 40:
        return "C"
    elif score >= 25:
        return "D"
    else:
        return "F"


def _build_reasons(prop: Property, val: ValuationResult) -> List[str]:
    """Generate human-readable reasons for the deal score."""
    reasons = []

    if val.price_difference > 0:
        reasons.append(
            f"Estimated value ${val.estimated_value:,.0f} is "
            f"${val.price_difference:,.0f} above asking price "
            f"({val.price_difference_pct:+.1f}%)"
        )
    else:
        reasons.append(
            f"Asking price is ${abs(val.price_difference):,.0f} above "
            f"estimated value ({val.price_difference_pct:+.1f}%)"
        )

    if val.price_per_sqft < val.market_price_per_sqft * 0.90:
        reasons.append(
            f"Price/sqft (${val.price_per_sqft:.0f}) is well below "
            f"market average (${val.market_price_per_sqft:.0f})"
        )

    if prop.days_on_market and prop.days_on_market > 60:
        reasons.append(
            f"Listed {prop.days_on_market} days – seller may be motivated"
        )

    if prop.condition == PropertyCondition.EXCELLENT:
        reasons.append("Property in excellent condition")

    if prop.year_built and prop.year_built >= 2020:
        reasons.append(f"Nearly new construction (built {prop.year_built})")

    return reasons if reasons else ["Standard market deal"]


def _build_risks(prop: Property, val: ValuationResult) -> List[str]:
    """Generate risk factors for the deal."""
    risks = []

    if val.confidence_score < 0.7:
        risks.append("Low data confidence – limited comparable information")

    if prop.condition in (PropertyCondition.FAIR, PropertyCondition.POOR):
        risks.append(
            f"Property condition is {prop.condition.value} – "
            f"may require significant repairs"
        )

    if prop.year_built and prop.year_built < 1970:
        risks.append("Built before 1970 – potential lead paint, asbestos concerns")

    if prop.hoa_fee and prop.hoa_fee > 300:
        risks.append(f"High HOA fee: ${prop.hoa_fee:.0f}/month")

    if val.price_difference_pct < -10:
        risks.append("Asking price significantly above estimated value")

    if prop.days_on_market and prop.days_on_market < 5:
        risks.append("Very new listing – limited price discovery")

    return risks if risks else ["No significant risks identified"]


def score_deal(prop: Property, val: ValuationResult,
               appreciation: Optional[float] = None) -> DealScore:
    """
    Score a single property deal on a 0-100 scale.
    Higher = better deal.
    """
    score = 50.0  # Start neutral

    # Value gap (biggest factor: +/- 25 points)
    value_gap_pct = val.price_difference_pct
    score += min(25, max(-25, value_gap_pct * 1.5))

    # Price per sqft vs market (+/- 10 points)
    if val.market_price_per_sqft > 0:
        ppsf_ratio = val.price_per_sqft / val.market_price_per_sqft
        if ppsf_ratio < 0.85:
            score += 10
        elif ppsf_ratio < 0.95:
            score += 5
        elif ppsf_ratio > 1.15:
            score -= 10
        elif ppsf_ratio > 1.05:
            score -= 5

    # Condition (+/- 8 points)
    condition_scores = {
        PropertyCondition.EXCELLENT: 8,
        PropertyCondition.GOOD: 3,
        PropertyCondition.FAIR: -3,
        PropertyCondition.POOR: -8,
        PropertyCondition.UNKNOWN: -2,
    }
    score += condition_scores.get(prop.condition, 0)

    # Age bonus for newer properties (+/- 5 points)
    if prop.year_built:
        age = 2026 - prop.year_built
        if age < 5:
            score += 5
        elif age < 15:
            score += 2
        elif age > 50:
            score -= 3

    # Days on market opportunity (+/- 5 points)
    if prop.days_on_market:
        if prop.days_on_market > 90:
            score += 5  # Motivated seller
        elif prop.days_on_market > 60:
            score += 3

    # Feature bonuses (up to +5 points)
    if prop.has_pool:
        score += 1
    if prop.has_basement:
        score += 1
    if prop.has_garage:
        score += 1
    if prop.has_central_air:
        score += 1
    if prop.has_fireplace:
        score += 1

    # HOA penalty
    if prop.hoa_fee and prop.hoa_fee > 300:
        score -= 3

    # Confidence weight
    score *= (0.7 + 0.3 * val.confidence_score)

    # Clamp
    score = max(0, min(100, score))

    return DealScore(
        property=prop,
        valuation=val,
        deal_score=round(score, 1),
        deal_grade=_grade_from_score(score),
        reasons=_build_reasons(prop, val),
        risk_factors=_build_risks(prop, val),
        monthly_payment_estimate=_calculate_monthly_payment(prop.list_price),
        estimated_roi_5yr=_estimate_5yr_roi(
            prop, val.estimated_value, appreciation),
    )


def optimize_search(specs: SearchSpecs, page: Optional[int] = None,
                    page_size: int = 20) -> dict:
    """End-to-end pipeline: fetch data, valuate, and optimize.

    Pagination is opt-in: pass page >= 1 to get a slice (1-indexed) of
    page_size deals; without it the full result set is returned.
    """
    if page_size < 1:
        page_size = 1
    page_size = min(page_size, 100)
    area_name = specs.city or specs.county or specs.state or "the search area"

    # Real trailing-12mo appreciation for the metro when Zillow Research
    # has it; otherwise the national default.
    market_baseline = get_metro_baseline(specs.city, specs.state)
    metro_appreciation = (market_baseline or {}).get("appreciation_1y")
    if metro_appreciation is not None:
        logger.info("Using Zillow Research metro appreciation %.1f%% for %s",
                    metro_appreciation * 100, area_name)
    appreciation_meta = {
        "value": (metro_appreciation
                  if metro_appreciation is not None
                  else APPRECIATION_ASSUMPTION),
        "source": ("zillow-research-metro" if metro_appreciation is not None
                   else "national-default"),
    }

    # Fetch listings
    properties = fetch_live_listings(specs, count=60)

    if not properties:
        return {
            "deals": [],
            "market_stats": MarketStats(
                area_name=area_name,
                median_price=0,
                avg_price_per_sqft=0,
                median_days_on_market=0,
                total_listings=0,
                avg_year_built=1990,
            ).model_dump(),
            "total_results": 0,
            "total_pages": 0,
            "page": page,
            "page_size": page_size,
            "search_specs": specs.model_dump(),
            "message": "No properties found matching your criteria."
        }

    # Valuate and score each property; skip (rather than crash on) any
    # listing the valuation engine rejects.
    deals: List[DealScore] = []
    all_prices = []
    all_ppsf = []
    all_dom = []
    all_year = []

    for prop in properties:
        try:
            val = valuate_property(prop)
        except ValuationError as e:
            logger.warning("Skipping property %s in search: %s", prop.id, e)
            continue
        deal = score_deal(prop, val, appreciation=metro_appreciation)
        deals.append(deal)

        all_prices.append(prop.list_price)
        all_ppsf.append(prop.list_price / max(prop.sqft, 1))
        if prop.days_on_market is not None:
            all_dom.append(prop.days_on_market)
        if prop.year_built:
            all_year.append(prop.year_built)

    if not deals:
        return {
            "deals": [],
            "market_stats": MarketStats(
                area_name=area_name,
                median_price=0,
                avg_price_per_sqft=0,
                median_days_on_market=0,
                total_listings=0,
                avg_year_built=1990,
            ).model_dump(),
            "total_results": 0,
            "total_pages": 0,
            "page": page,
            "page_size": page_size,
            "search_specs": specs.model_dump(),
            "message": "No properties could be valuated with the available data."
        }

    # Sort
    sort_key = specs.sort_by or "deal_score"
    if sort_key == "deal_score":
        deals.sort(key=lambda d: d.deal_score, reverse=True)
    elif sort_key == "price_asc":
        deals.sort(key=lambda d: d.property.list_price)
    elif sort_key == "price_desc":
        deals.sort(key=lambda d: d.property.list_price, reverse=True)
    elif sort_key == "newest":
        deals.sort(key=lambda d: d.property.days_on_market or 999)

    # Build market stats (computed from the actual result set — no
    # fabricated trend numbers)
    market_stats = MarketStats(
        area_name=area_name,
        median_price=round(statistics.median(all_prices), 0) if all_prices else 0,
        avg_price_per_sqft=round(statistics.mean(all_ppsf), 2) if all_ppsf else 0,
        median_days_on_market=int(statistics.median(all_dom)) if all_dom else 0,
        total_listings=len(deals),
        avg_year_built=int(statistics.mean(all_year)) if all_year else 1990,
    )

    # Opt-in pagination slice (1-indexed page of the sorted list)
    total = len(deals)
    response_deals = deals
    current_page = page
    if page is not None:
        current_page = max(1, page)
        start = (current_page - 1) * page_size
        response_deals = deals[start:start + page_size]

    return {
        "deals": [d.model_dump() for d in response_deals],
        "market_stats": market_stats.model_dump(),
        "total_results": total,
        "total_pages": (-(-total // page_size)) if current_page else None,
        "page": current_page,
        "page_size": page_size,
        "search_specs": specs.model_dump(),
        "appreciation_assumption": appreciation_meta,
        "market_baseline": market_baseline,
    }
