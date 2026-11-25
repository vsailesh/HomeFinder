"""
Investor heatmap — one row per served metro, comparing deal math
across markets from the Zillow Research baselines already in hand.

For each metro: price basis (median list, else typical value), the
P&I payment on it at the live FRED rate, full monthly carry (P&I +
tax + insurance, same constants the deal scoring uses), typical
metro rent, and the resulting cashflow / rent coverage. REO active
inventory joins in when the tracker has rows. Pure derivation — no
new data sources, no new assumptions beyond the carry constants the
rest of the app shares.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from data_pipeline import get_all_cities
from loan_engine import get_market_base_rate
from market_baselines import get_baselines_snapshot, resolve_metro_name
from optimizer import (
    INSURANCE_RATE, TAX_RATE_DEFAULT, _calculate_monthly_payment,
)

logger = logging.getLogger(__name__)


def _reo_active_by_metro() -> Dict[str, int]:
    """{served-city name: active tracked REO count}. The tracker
    stores each listing under the MARKET_DATA key it was swept with,
    so counts join on served city names, not Zillow metro names.
    Tracker failures just zero out the column."""
    try:
        import reo_tracker
        return {str(k).strip().casefold(): int(v)
                for k, v in reo_tracker.get_active_counts_by_metro().items()}
    except Exception:
        logger.exception("REO inventory join failed — heatmap continues")
        return {}


def build_heatmap() -> Dict:
    """Compare every served metro: what the typical home costs to
    carry vs what it rents for, at the live mortgage rate."""
    # Resolve each served city to its Zillow metro; suburbs collapse
    # into one row (Columbia/Annapolis/Baltimore -> "Baltimore, MD").
    metro_cities: Dict[str, List[Dict]] = {}
    for city in get_all_cities():
        metro = resolve_metro_name(city["name"], city["state"])
        if not metro:
            continue  # no baseline for this market (fetch down or new city)
        metro_cities.setdefault(metro, []).append(city)

    baselines = get_baselines_snapshot()["metros"]
    reo_counts = _reo_active_by_metro()
    rate_info = get_market_base_rate()
    rate = rate_info["rate"]

    rows = []
    for metro, cities in metro_cities.items():
        entry = baselines.get(metro, {})
        basis = entry.get("median_list_price") or entry.get(
            "typical_value")
        if not basis:
            continue  # nothing to price a payment against

        payment = _calculate_monthly_payment(basis, rate=rate)
        # Round each carry component before summing so the displayed
        # carry always equals the sum of the displayed parts.
        tax_mo = round(basis * TAX_RATE_DEFAULT / 12)
        ins_mo = round(basis * INSURANCE_RATE / 12)
        carry = round(payment + tax_mo + ins_mo)
        rent = entry.get("typical_rent")
        cashflow = round(rent - carry) if rent else None
        coverage = round(rent / payment, 2) if rent else None
        reo_active = sum(
            reo_counts.get(c["name"].casefold(), 0) for c in cities)

        rows.append({
            "metro": metro,
            "state": cities[0]["state"],
            "cities": [c["name"] for c in cities],
            "as_of": entry.get("as_of"),
            "typical_value": entry.get("typical_value"),
            "median_list_price": entry.get("median_list_price"),
            "typical_rent": rent,
            "appreciation_1y": entry.get("appreciation_1y"),
            "sale_to_list_ratio": entry.get("sale_to_list_ratio"),
            "pct_listings_price_cut": entry.get("pct_listings_price_cut"),
            "median_days_to_pending": entry.get("median_days_to_pending"),
            "reo_active": reo_active,
            "monthly": {
                "price_basis": basis,
                "payment": payment,
                "tax": tax_mo,
                "insurance": ins_mo,
                "carry": carry,
                "cashflow": cashflow,
                "rent_coverage": coverage,
            },
        })

    # Best cashflow first; metros with no published rent sink to the
    # bottom rather than sorting as None-vs-number.
    rows.sort(key=lambda r: (
        r["monthly"]["cashflow"] is None,
        -(r["monthly"]["cashflow"] or 0),
    ))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rate": {"rate": rate, "source": rate_info.get("source")},
        "assumptions": {
            "down_pct": 0.20,
            "tax_rate": TAX_RATE_DEFAULT,
            "insurance_rate": INSURANCE_RATE,
            "loan_term_years": 30,
        },
        "rows": rows,
    }
