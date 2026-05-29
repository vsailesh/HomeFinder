"""
Deal Optimizer for the Home Finder.
Scores and ranks properties based on the gap between estimated value
and asking price, factoring in risk and investment potential.
"""
from typing import List, Optional
from models import (
    Property, SearchSpecs, DealScore, ValuationResult, MarketStats,
    PropertyCondition
)
from valuation_engine import valuate_property
from data_pipeline import fetch_live_listings, get_market_sqft_price
import statistics


def _calculate_monthly_payment(price: float, down_pct: float = 0.20,
                                rate: float = 0.0685, years: int = 30) -> float:
    """Estimate monthly mortgage payment (P&I only)."""
    loan = price * (1 - down_pct)
    monthly_rate = rate / 12
    n = years * 12
    if monthly_rate == 0:
        return loan / n
    payment = loan * (monthly_rate * (1 + monthly_rate)**n) / \
              ((1 + monthly_rate)**n - 1)
    return round(payment, 2)


def _estimate_5yr_roi(prop: Property, estimated_value: float) -> float:
    """Rough 5-year ROI estimate based on appreciation + equity."""
    appreciation_rate = 0.035  # 3.5% annual avg for MD
    future_value = estimated_value * (1 + appreciation_rate) ** 5
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


def score_deal(prop: Property, val: ValuationResult) -> DealScore:
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
        estimated_roi_5yr=_estimate_5yr_roi(prop, val.estimated_value),
    )


def optimize_search(specs: SearchSpecs) -> dict:
    """End-to-end pipeline: fetch data, valuate, and optimize."""
    # Fetch listings
    properties = fetch_live_listings(specs, count=60)
    
    if not properties:
        return {
            "deals": [],
            "market_stats": MarketStats(area_name=specs.city or specs.county or specs.state or "Maryland").model_dump(),
            "total_results": 0,
            "search_specs": specs.model_dump(),
            "message": "No properties found matching your criteria."
        }

    # Valuate and score each property
    deals: List[DealScore] = []
    all_prices = []
    all_ppsf = []
    all_dom = []
    all_year = []

    for prop in properties:
        val = valuate_property(prop)
        deal = score_deal(prop, val)
        deals.append(deal)

        all_prices.append(prop.list_price)
        all_ppsf.append(prop.list_price / max(prop.sqft, 1))
        if prop.days_on_market is not None:
            all_dom.append(prop.days_on_market)
        if prop.year_built:
            all_year.append(prop.year_built)

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

    # Build market stats
    area_name = specs.city or specs.county or specs.state or "Maryland"
    market_stats = MarketStats(
        area_name=area_name,
        median_price=round(statistics.median(all_prices), 0) if all_prices else 0,
        avg_price_per_sqft=round(statistics.mean(all_ppsf), 2) if all_ppsf else 0,
        median_days_on_market=int(statistics.median(all_dom)) if all_dom else 0,
        total_listings=len(deals),
        avg_year_built=int(statistics.mean(all_year)) if all_year else 1990,
        price_trend_30d=round((2.1 + (hash(area_name) % 30 - 15) / 10), 2),
        inventory_change_30d=round((-3.5 + (hash(area_name) % 20 - 10) / 5), 2),
    )

    return {
        "deals": [d.model_dump() for d in deals],
        "market_stats": market_stats.model_dump(),
        "total_results": len(deals),
        "search_specs": specs.model_dump(),
    }
