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
from market_baselines import get_metro_baseline, get_zip_rent

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
               appreciation: Optional[float] = None,
               metro_rent: Optional[float] = None,
               market_heat: Optional[dict] = None) -> DealScore:
    """
    Score a single property deal on a 0-100 scale.
    Higher = better deal.

    market_heat carries the metro-level negotiation signals from
    Zillow Research (pct_listings_price_cut, median_days_to_pending,
    sale_to_list_ratio); None = unavailable, scoring skips them.
    """
    score = 50.0  # Start neutral
    heat_reasons: List[str] = []
    heat_risks: List[str] = []

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

    # Market heat — metro-level negotiation signals. Small adjustments
    # (net capped at +/-5) since they apply to every listing in the
    # search equally; they shape strategy, not ranking much.
    heat = market_heat or {}
    heat_adj = 0.0
    price_cuts = heat.get("pct_listings_price_cut")
    if price_cuts is not None:
        if price_cuts >= 0.30:
            heat_adj += 3
            heat_reasons.append(
                f"Buyer's market: {price_cuts:.0%} of metro listings cut "
                f"price — negotiating leverage")
        elif price_cuts <= 0.15:
            heat_adj -= 2
            heat_risks.append(
                f"Firm market: only {price_cuts:.0%} of metro listings "
                f"cut price — sellers holding asking")
    days_pending = heat.get("median_days_to_pending")
    if days_pending is not None:
        if days_pending >= 30:
            heat_adj += 2
            heat_reasons.append(
                f"Slow market: median {days_pending:.0f} days to pending "
                f"— sellers may flex on price")
        elif days_pending <= 7:
            heat_adj -= 2
            heat_risks.append(
                f"Fast market: median {days_pending:.0f} days to pending "
                f"— expect competition")
    stl = heat.get("sale_to_list_ratio")
    if stl is not None:
        if stl <= 0.98:
            heat_adj += 2
            heat_reasons.append(
                f"Metro homes close {1 - stl:.1%} below list on median "
                f"— below-asking offers common")
        elif stl >= 1.02:
            heat_adj -= 2
            heat_risks.append(
                f"Metro homes close {stl - 1:.1%} above list — bidding "
                f"wars common")
    score += max(-5.0, min(5.0, heat_adj))

    # Rental yield — ZIP-level rent when Zillow publishes one for the
    # listing (much sharper than metro; metro as fallback). Coverage of
    # the P&I payment is the investment signal. +/- 6 points.
    payment = _calculate_monthly_payment(prop.list_price)
    rent = get_zip_rent(prop.zip_code) or metro_rent
    cashflow = None
    if rent is not None:
        cashflow = round(rent - payment, 2)
        coverage = rent / max(payment, 1)
        if coverage >= 2.0:
            score += 6
        elif coverage >= 1.0:
            score += 3
        elif coverage < 0.5:
            score -= 3

    # Confidence weight
    score *= (0.7 + 0.3 * val.confidence_score)

    # Clamp
    score = max(0, min(100, score))

    # Full monthly carry: P&I + tax/12 + insurance estimate + HOA.
    # Real tax when the listing publishes it (HomeSteps does, mock
    # fabricates it); otherwise ~1.1%/yr of list. Insurance assumed
    # 0.35%/yr of list when unknown.
    annual_tax = prop.annual_tax or prop.list_price * 0.011
    insurance = prop.list_price * 0.0035 / 12
    hoa = prop.hoa_fee or 0.0
    carry = round(payment + annual_tax / 12 + insurance + hoa, 2)
    net_cf = round(rent - carry, 2) if rent is not None else None

    reasons = _build_reasons(prop, val)
    reasons.extend(heat_reasons)
    if cashflow is not None and cashflow > 0:
        reasons.insert(
            0, f"Rent covers P&I with +${cashflow:,.0f}/mo cashflow "
               f"(rent yield signal)")
    risks = _build_risks(prop, val)
    risks.extend(heat_risks)

    return DealScore(
        property=prop,
        valuation=val,
        deal_score=round(score, 1),
        deal_grade=_grade_from_score(score),
        reasons=reasons,
        risk_factors=risks,
        monthly_payment_estimate=payment,
        estimated_roi_5yr=_estimate_5yr_roi(
            prop, val.estimated_value, appreciation),
        estimated_rent=rent,
        estimated_monthly_cashflow=cashflow,
        monthly_carry_estimate=carry,
        net_monthly_cashflow=net_cf,
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
    metro_rent = (market_baseline or {}).get("typical_rent")
    market_heat = {k: market_baseline[k] for k in (
        "pct_listings_price_cut", "median_days_to_pending",
        "sale_to_list_ratio") if k in (market_baseline or {})}
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

    for prop in properties:
        try:
            val = valuate_property(prop)
        except ValuationError as e:
            logger.warning("Skipping property %s in search: %s", prop.id, e)
            continue
        deal = score_deal(prop, val, appreciation=metro_appreciation,
                          metro_rent=metro_rent, market_heat=market_heat)
        deals.append(deal)

    # Investor filter: keep only deals whose estimated rent covers at
    # least min_rent_coverage x the P&I payment. Deals with no rent
    # data can't demonstrate coverage — dropped too.
    if specs.min_rent_coverage is not None:
        before = len(deals)
        deals = [
            d for d in deals
            if d.estimated_rent is not None
            and d.estimated_rent / max(d.monthly_payment_estimate, 1)
            >= specs.min_rent_coverage
        ]
        logger.info("Rent coverage >= %.2fx: %d of %d deals kept",
                    specs.min_rent_coverage, len(deals), before)

    # Stats describe the filtered result set, so derive them here.
    all_prices = [d.property.list_price for d in deals]
    all_ppsf = [d.property.list_price / max(d.property.sqft, 1)
                for d in deals]
    all_dom = [d.property.days_on_market for d in deals
               if d.property.days_on_market is not None]
    all_year = [d.property.year_built for d in deals
                if d.property.year_built]

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
    elif sort_key == "cashflow_desc":
        deals.sort(
            key=lambda d: (d.estimated_monthly_cashflow
                           if d.estimated_monthly_cashflow is not None
                           else float("-inf")),
            reverse=True)

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
