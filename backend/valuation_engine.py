"""
Valuation Engine for the Home Finder.
Estimates the fair market value of a property by analyzing multiple price-driving
variables and comparing against market data (comparable sales approach).
"""
import math
import logging
from typing import List, Tuple, Optional
from models import (
    Property, PropertyType, PropertyCondition,
    ValuationResult, PriceVariable
)
from data_pipeline import get_market_sqft_price


logger = logging.getLogger(__name__)


class ValuationError(Exception):
    """Base exception for valuation errors."""
    pass


class InsufficientDataError(ValuationError):
    """Raised when required property data is missing."""
    pass


class MarketDataError(ValuationError):
    """Raised when market data cannot be retrieved."""
    pass


# ── Weight Configuration ──────────────────────────────────────────────────────
# These weights determine how much each category impacts the final valuation.

CATEGORY_WEIGHTS = {
    "location": 0.30,
    "physical": 0.35,
    "features": 0.15,
    "market": 0.20,
}


def _location_score(prop: Property, market_sqft: float) -> Tuple[float, List[PriceVariable]]:
    """Evaluate location-based value factors."""
    variables = []
    base = prop.sqft * market_sqft

    if base <= 0:
        logger.warning(f"Property {prop.id}: Invalid base value for location score: {base}")
        base = max(prop.sqft, 1) * max(market_sqft, 1)

    try:
        # County premium / discount
        county_premiums = {
            "montgomery county": 1.18,
            "howard county": 1.12,
            "anne arundel county": 1.05,
            "frederick county": 0.95,
            "baltimore city": 0.88,
            "prince george's county": 0.92,
        }
        county_key = (prop.county or "").lower()
        county_mult = county_premiums.get(county_key, 1.0)
        county_impact = base * (county_mult - 1.0)
        variables.append(PriceVariable(
            name="County Premium",
            category="location",
            raw_impact=round(county_impact, 2),
            percentage_impact=round((county_mult - 1.0) * 100, 2),
            description=f"{prop.county or 'Unknown'} county {'premium' if county_mult > 1 else 'discount'}",
            comparable_avg=market_sqft * county_mult,
        ))

        # School district proxy (ZIP code based heuristic)
        zip_first3 = prop.zip_code[:3] if prop.zip_code and len(prop.zip_code) >= 3 else "000"
        school_mult = 1.0
        high_school_zips = {"208", "217", "210"}  # Montgomery, Howard, north Baltimore
        if zip_first3 in high_school_zips:
            school_mult = 1.06
        school_impact = base * (school_mult - 1.0)
        variables.append(PriceVariable(
            name="School District Quality",
            category="location",
            raw_impact=round(school_impact, 2),
            percentage_impact=round((school_mult - 1.0) * 100, 2),
            description=f"School district quality index for ZIP {prop.zip_code or 'N/A'}",
        ))

        # Walkability / urban premium
        urban_mult = 1.0
        urban_cities = {"bethesda", "silver spring", "rockville", "annapolis"}
        if prop.city and prop.city.lower() in urban_cities:
            urban_mult = 1.04
        urban_impact = base * (urban_mult - 1.0)
        variables.append(PriceVariable(
            name="Walkability & Urban Access",
            category="location",
            raw_impact=round(urban_impact, 2),
            percentage_impact=round((urban_mult - 1.0) * 100, 2),
            description=f"Urban walkability premium for {prop.city or 'Unknown'}",
        ))

        total_location = base * county_mult * school_mult * urban_mult
        return total_location, variables
    except Exception as e:
        logger.error(f"Error calculating location score for property {prop.id}: {e}")
        return base, variables


def _physical_score(prop: Property, market_sqft: float) -> Tuple[float, List[PriceVariable]]:
    """Evaluate physical attribute value factors."""
    variables = []

    try:
        base = prop.sqft * market_sqft
        if base <= 0:
            logger.warning(f"Property {prop.id}: Invalid base value for physical score: {base}")
            base = max(prop.sqft, 1) * max(market_sqft, 1)

        # Square footage value
        sqft_value = max(prop.sqft, 0) * market_sqft
        variables.append(PriceVariable(
            name="Living Area (sqft)",
            category="physical",
            raw_impact=round(sqft_value, 2),
            percentage_impact=round((sqft_value / max(base, 1)) * 100, 2),
            description=f"{prop.sqft:,} sqft at ${market_sqft:.0f}/sqft market rate",
            comparable_avg=market_sqft,
        ))

        # Age / year built
        current_year = 2026
        year_built = prop.year_built if prop.year_built and prop.year_built > 1800 else 1980
        year_built = min(year_built, current_year)  # Can't be built in the future
        age = current_year - year_built

        if age < 0:
            logger.warning(f"Property {prop.id}: Invalid age calculated: {age}, using default")
            age = 0

        if age < 5:
            age_mult = 1.15
            age_desc = "New construction premium"
        elif age < 15:
            age_mult = 1.08
            age_desc = "Modern build premium"
        elif age < 30:
            age_mult = 1.0
            age_desc = "Standard age, no adjustment"
        elif age < 50:
            age_mult = 0.92
            age_desc = "Older home discount"
        else:
            age_mult = 0.85
            age_desc = "Significantly aged, major discount"

        age_impact = base * (age_mult - 1.0)
        variables.append(PriceVariable(
            name="Year Built / Age",
            category="physical",
            raw_impact=round(age_impact, 2),
            percentage_impact=round((age_mult - 1.0) * 100, 2),
            description=f"Built {prop.year_built or 'N/A'} ({max(age, 0)} yrs old) – {age_desc}",
        ))

        # Condition
        condition_mults = {
            PropertyCondition.EXCELLENT: 1.12,
            PropertyCondition.GOOD: 1.0,
            PropertyCondition.FAIR: 0.88,
            PropertyCondition.POOR: 0.72,
            PropertyCondition.UNKNOWN: 0.95,
        }
        cond_mult = condition_mults.get(prop.condition, 1.0)
        cond_impact = base * (cond_mult - 1.0)
        variables.append(PriceVariable(
            name="Property Condition",
            category="physical",
            raw_impact=round(cond_impact, 2),
            percentage_impact=round((cond_mult - 1.0) * 100, 2),
            description=f"Condition: {prop.condition.value if hasattr(prop.condition, 'value') else prop.condition} – {'premium' if cond_mult > 1 else 'discount' if cond_mult < 1 else 'neutral'}",
        ))

        # Bedrooms
        bed_premium = 0
        if prop.bedrooms >= 4:
            bed_premium = base * 0.05
        elif prop.bedrooms <= 1:
            bed_premium = base * -0.08
        variables.append(PriceVariable(
            name="Bedroom Count",
            category="physical",
            raw_impact=round(bed_premium, 2),
            percentage_impact=round((bed_premium / max(base, 1)) * 100, 2),
            description=f"{prop.bedrooms} bedrooms",
        ))

        # Bathrooms
        bath_premium = 0
        if prop.bathrooms >= 3:
            bath_premium = base * 0.04
        elif prop.bathrooms < 1.5:
            bath_premium = base * -0.06
        variables.append(PriceVariable(
            name="Bathroom Count",
            category="physical",
            raw_impact=round(bath_premium, 2),
            percentage_impact=round((bath_premium / max(base, 1)) * 100, 2),
            description=f"{prop.bathrooms} bathrooms",
        ))

        # Lot size
        lot_premium = 0
        if prop.lot_sqft and prop.lot_sqft > 0:
            if prop.lot_sqft > 10890:  # > 0.25 acres
                lot_premium = (prop.lot_sqft - 10890) * 5.0
            elif prop.lot_sqft < 3000:
                lot_premium = -8000
        variables.append(PriceVariable(
            name="Lot Size",
            category="physical",
            raw_impact=round(lot_premium, 2),
            percentage_impact=round((lot_premium / max(base, 1)) * 100, 2),
            description=f"Lot: {prop.lot_sqft:,} sqft" if prop.lot_sqft else "No lot data",
        ))

        # Property type
        type_mults = {
            PropertyType.SINGLE_FAMILY: 1.0,
            PropertyType.TOWNHOUSE: 0.90,
            PropertyType.CONDO: 0.85,
            PropertyType.MULTI_FAMILY: 1.10,
            PropertyType.LAND: 0.5,
            PropertyType.OTHER: 0.9,
        }
        type_mult = type_mults.get(prop.property_type, 1.0)
        type_impact = base * (type_mult - 1.0)
        variables.append(PriceVariable(
            name="Property Type",
            category="physical",
            raw_impact=round(type_impact, 2),
            percentage_impact=round((type_mult - 1.0) * 100, 2),
            description=f"Type: {prop.property_type.value if hasattr(prop.property_type, 'value') else prop.property_type}",
        ))

        total_physical = sqft_value * age_mult * cond_mult + bed_premium + bath_premium + lot_premium + type_impact
        return total_physical, variables
    except Exception as e:
        logger.error(f"Error calculating physical score for property {prop.id}: {e}")
        return base, variables


def _features_score(prop: Property, market_sqft: float) -> Tuple[float, List[PriceVariable]]:
    """Evaluate feature-based value additions."""
    variables = []
    base = prop.sqft * market_sqft
    total = 0

    if base <= 0:
        base = max(prop.sqft, 1) * max(market_sqft, 1)

    try:
        features = [
            ("Swimming Pool", prop.has_pool, 28000, "Pool adds significant value in MD market"),
            ("Basement", prop.has_basement, 22000, "Finished/unfinished basement space"),
            ("Fireplace", prop.has_fireplace, 6500, "Fireplace adds modest value"),
            ("Central Air", prop.has_central_air, 8000, "Central HVAC system"),
            ("Garage", prop.has_garage, 18000, "Attached/detached garage"),
        ]

        for name, has_feature, value, desc in features:
            impact = value if has_feature else 0
            total += impact
            variables.append(PriceVariable(
                name=name,
                category="features",
                raw_impact=round(impact, 2),
                percentage_impact=round((impact / max(base, 1)) * 100, 2),
                description=f"{'Has' if has_feature else 'No'} {name.lower()} – {desc}",
            ))

        # HOA penalty
        if prop.hoa_fee and prop.hoa_fee > 0:
            # HOA reduces effective value (buyer pays monthly)
            annual_hoa = prop.hoa_fee * 12
            hoa_penalty = -annual_hoa * 10  # capitalize ~10 years
            total += hoa_penalty
            variables.append(PriceVariable(
                name="HOA Fees",
                category="features",
                raw_impact=round(hoa_penalty, 2),
                percentage_impact=round((hoa_penalty / max(base, 1)) * 100, 2),
                description=f"${prop.hoa_fee:.0f}/mo HOA reduces effective value",
            ))

        return total, variables
    except Exception as e:
        logger.error(f"Error calculating features score for property {prop.id}: {e}")
        return total, variables


def _market_score(prop: Property, market_sqft: float) -> Tuple[float, List[PriceVariable]]:
    """Evaluate market-condition value factors."""
    variables = []
    base = prop.sqft * market_sqft
    total_adjustment = 0

    if base <= 0:
        base = max(prop.sqft, 1) * max(market_sqft, 1)

    try:
        # Days on market signal
        dom = prop.days_on_market if prop.days_on_market is not None and prop.days_on_market >= 0 else 30
        if dom > 90:
            dom_adj = base * -0.05
            dom_desc = "Stale listing, possible price reduction coming"
        elif dom > 60:
            dom_adj = base * -0.02
            dom_desc = "Moderately stale, some negotiation room"
        elif dom < 7:
            dom_adj = base * 0.03
            dom_desc = "Hot listing, competitive market"
        else:
            dom_adj = 0
            dom_desc = "Normal market timing"
        total_adjustment += dom_adj
        variables.append(PriceVariable(
            name="Days on Market",
            category="market",
            raw_impact=round(dom_adj, 2),
            percentage_impact=round((dom_adj / max(base, 1)) * 100, 2),
            description=f"{dom} days – {dom_desc}",
        ))

        # Tax assessed vs list price divergence
        if prop.tax_assessed_value and prop.tax_assessed_value > 0 and prop.list_price and prop.list_price > 0:
            ratio = prop.tax_assessed_value / prop.list_price
            if ratio > 0.95:
                tax_adj = base * 0.02
                tax_desc = "Tax assessment close to list – well-priced"
            elif ratio < 0.70:
                tax_adj = base * -0.03
                tax_desc = "Large gap between tax value and list price"
            else:
                tax_adj = 0
                tax_desc = "Normal assessment-to-list ratio"
            total_adjustment += tax_adj
            variables.append(PriceVariable(
                name="Tax Assessment Ratio",
                category="market",
                raw_impact=round(tax_adj, 2),
                percentage_impact=round((tax_adj / max(base, 1)) * 100, 2),
                description=f"Assessed ${prop.tax_assessed_value:,.0f} vs List ${prop.list_price:,.0f} – {tax_desc}",
                comparable_avg=0.82,
            ))

        # Price per sqft vs market
        prop_sqft = max(prop.sqft, 1)
        prop_list_price = max(prop.list_price, 1) if prop.list_price else base
        prop_ppsf = prop_list_price / prop_sqft
        market_sqft_safe = max(market_sqft, 1)
        ppsf_ratio = prop_ppsf / market_sqft_safe

        if ppsf_ratio < 0.85:
            ppsf_adj = base * 0.05
            ppsf_desc = "Priced well below market $/sqft – potential deal"
        elif ppsf_ratio > 1.15:
            ppsf_adj = base * -0.04
            ppsf_desc = "Priced above market $/sqft – possibly overpriced"
        else:
            ppsf_adj = 0
            ppsf_desc = "In line with market $/sqft"
        total_adjustment += ppsf_adj
        variables.append(PriceVariable(
            name="Price/SqFt vs Market",
            category="market",
            raw_impact=round(ppsf_adj, 2),
            percentage_impact=round((ppsf_adj / max(base, 1)) * 100, 2),
            description=f"${prop_ppsf:.0f}/sqft vs ${market_sqft:.0f}/sqft market avg – {ppsf_desc}",
            comparable_avg=market_sqft,
        ))

        return total_adjustment, variables
    except Exception as e:
        logger.error(f"Error calculating market score for property {prop.id}: {e}")
        return total_adjustment, variables


def valuate_property(prop: Property) -> ValuationResult:
    """
    Run the full valuation engine on a single property.
    Returns a detailed ValuationResult with variable-by-variable breakdown.

    Raises:
        InsufficientDataError: If required property data is missing
        MarketDataError: If market data cannot be retrieved
        ValuationError: For other valuation errors
    """
    # Validate required fields
    if not prop.id:
        raise InsufficientDataError("Property ID is required")
    if not prop.city:
        raise InsufficientDataError("Property city is required")
    if prop.sqft <= 0:
        raise InsufficientDataError(f"Property square footage must be positive, got: {prop.sqft}")
    if not prop.list_price or prop.list_price <= 0:
        raise InsufficientDataError(f"Property list price must be positive, got: {prop.list_price}")

    logger.debug(f"Starting valuation for property {prop.id} at {prop.address}")

    try:
        # Get market data with fallback
        try:
            market_sqft = get_market_sqft_price(prop.city)
            if market_sqft <= 0:
                logger.warning(f"Invalid market_sqft from data_pipeline: {market_sqft}, using fallback")
                market_sqft = 250.0  # Fallback to $250/sqft
        except Exception as e:
            logger.error(f"Error getting market_sqft for {prop.city}: {e}, using fallback")
            market_sqft = 250.0

        all_variables: List[PriceVariable] = []

        # Run each scoring category
        location_value, loc_vars = _location_score(prop, market_sqft)
        physical_value, phys_vars = _physical_score(prop, market_sqft)
        features_value, feat_vars = _features_score(prop, market_sqft)
        market_adj, mkt_vars = _market_score(prop, market_sqft)

        all_variables.extend(loc_vars)
        all_variables.extend(phys_vars)
        all_variables.extend(feat_vars)
        all_variables.extend(mkt_vars)

        # Weighted composite
        base = prop.sqft * market_sqft
        if base <= 0:
            logger.warning(f"Invalid base value for property {prop.id}: {base}")
            base = max(prop.list_price, 100000) * 0.5

        estimated_value = (
            location_value * CATEGORY_WEIGHTS["location"] +
            physical_value * CATEGORY_WEIGHTS["physical"] +
            features_value * CATEGORY_WEIGHTS["features"] +
            (base + market_adj) * CATEGORY_WEIGHTS["market"]
        )

        # Ensure estimated value is reasonable (within 60%-160% of base)
        estimated_value = max(base * 0.60, min(estimated_value, base * 1.60))
        estimated_value = max(estimated_value, 10000)  # Minimum value of $10k
        estimated_value = round(estimated_value, -2)

        # Decompose into categories
        base_land = round(estimated_value * 0.30, 2)
        structure = round(estimated_value * 0.50, 2)
        feature_adj = round(features_value, 2)
        loc_premium = round(location_value - base, 2)
        mkt_adjustment = round(market_adj, 2)

        price_diff = estimated_value - prop.list_price
        price_diff_pct = round((price_diff / max(prop.list_price, 1)) * 100, 2)

        # Confidence score based on data completeness
        completeness = 0.5
        if prop.year_built:
            completeness += 0.1
        if prop.lot_sqft:
            completeness += 0.1
        if prop.tax_assessed_value:
            completeness += 0.1
        if prop.condition != PropertyCondition.UNKNOWN:
            completeness += 0.1
        if prop.days_on_market is not None:
            completeness += 0.1
        if getattr(prop, "sqft_estimated", False):
            # Sqft is the core size input — an estimate (HomeSteps REO)
            # makes the whole valuation softer.
            completeness -= 0.1
        completeness = max(0.3, min(completeness, 0.95))

        result = ValuationResult(
            property_id=prop.id,
            estimated_value=estimated_value,
            confidence_score=round(completeness, 2),
            price_per_sqft=round(prop.list_price / max(prop.sqft, 1), 2),
            market_price_per_sqft=market_sqft,
            base_land_value=base_land,
            structure_value=structure,
            feature_adjustments=feature_adj,
            location_premium=loc_premium,
            market_adjustment=mkt_adjustment,
            variables=all_variables,
            list_price=prop.list_price,
            price_difference=round(price_diff, 2),
            price_difference_pct=price_diff_pct,
        )

        logger.debug(f"Valuation complete for property {prop.id}: ${estimated_value:,.0f}")
        return result

    except InsufficientDataError:
        raise
    except MarketDataError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error valuating property {prop.id}: {e}")
        raise ValuationError(f"Failed to valuate property {prop.id}: {e}") from e


def valuate_properties(properties: List[Property]) -> Tuple[List[ValuationResult], List[Tuple[Property, str]]]:
    """
    Run valuation on multiple properties with graceful error handling.

    Args:
        properties: List of properties to valuate

    Returns:
        Tuple of:
            - List of successful ValuationResults
            - List of (property, error_message) tuples for failed valuations
    """
    successful_results = []
    failures = []

    logger.debug(f"Starting batch valuation for {len(properties)} properties")

    for prop in properties:
        try:
            result = valuate_property(prop)
            successful_results.append(result)
        except InsufficientDataError as e:
            logger.warning(f"Skipping property {prop.id}: insufficient data - {e}")
            failures.append((prop, f"Insufficient data: {e}"))
        except MarketDataError as e:
            logger.warning(f"Skipping property {prop.id}: market data error - {e}")
            failures.append((prop, f"Market data error: {e}"))
        except ValuationError as e:
            logger.error(f"Valuation failed for property {prop.id}: {e}")
            failures.append((prop, str(e)))
        except Exception as e:
            logger.error(f"Unexpected error valuating property {prop.id}: {e}")
            failures.append((prop, f"Unexpected error: {e}"))

    logger.debug(f"Batch valuation complete: {len(successful_results)} successful, {len(failures)} failed")
    return successful_results, failures


def safe_valuate_property(prop: Property, fallback_value: Optional[float] = None) -> Optional[ValuationResult]:
    """
    Safely valuate a property, returning None on failure instead of raising.

    Args:
        prop: Property to valuate
        fallback_value: Optional fallback value to use if valuation fails

    Returns:
        ValuationResult or None if valuation failed
    """
    try:
        return valuate_property(prop)
    except (InsufficientDataError, MarketDataError, ValuationError) as e:
        logger.warning(f"Valuation failed for property {prop.id}: {e}")

        if fallback_value is not None and prop.list_price:
            # Return a minimal result with fallback value
            return ValuationResult(
                property_id=prop.id,
                estimated_value=fallback_value,
                confidence_score=0.0,
                price_per_sqft=round(prop.list_price / max(prop.sqft, 1), 2),
                market_price_per_sqft=round(fallback_value / max(prop.sqft, 1), 2),
                base_land_value=round(fallback_value * 0.3, 2),
                structure_value=round(fallback_value * 0.5, 2),
                feature_adjustments=0.0,
                location_premium=0.0,
                market_adjustment=0.0,
                variables=[],
                list_price=prop.list_price,
                price_difference=round(fallback_value - prop.list_price, 2),
                price_difference_pct=round(((fallback_value - prop.list_price) / max(prop.list_price, 1)) * 100, 2),
            )
        return None
    except Exception as e:
        logger.error(f"Unexpected error in safe_valuate_property for {prop.id}: {e}")
        return None
