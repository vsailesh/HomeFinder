"""
10-year hold projection for a single listing.

Projects rent income vs full monthly carry (P&I + tax + insurance +
HOA) year by year, alongside value appreciation and loan amortization,
so a buyer can see equity build and net position at exit. All inputs
arrive from the client (the search result already carries them) — no
per-property backend lookup needed.
"""
import logging
from typing import Optional

from loan_engine import get_market_base_rate
from market_baselines import get_metro_baseline, get_zip_rent
from optimizer import (_calculate_monthly_payment, APPRECIATION_ASSUMPTION,
                       DOWN_PCT_DEFAULT, INSURANCE_RATE, TAX_RATE_DEFAULT)

logger = logging.getLogger(__name__)

RENT_GROWTH = 0.03        # annual rent growth assumption
SELLING_COST = 0.06       # round-trip exit cost, as a share of sale value
YEARS = 10


def _balance_after(loan: float, monthly_rate: float, n_payments: int,
                   months_elapsed: int) -> float:
    """Remaining balance on a fixed-rate amortizing loan (closed form).

    months_elapsed beyond the term returns 0.
    """
    if months_elapsed >= n_payments:
        return 0.0
    if monthly_rate == 0:
        return loan * (n_payments - months_elapsed) / n_payments
    growth = (1 + monthly_rate) ** n_payments
    elapsed = (1 + monthly_rate) ** months_elapsed
    return loan * (growth - elapsed) / (growth - 1)


def build_projection(list_price: float,
                     estimated_value: Optional[float] = None,
                     city: Optional[str] = None,
                     state: Optional[str] = None,
                     zip_code: Optional[str] = None,
                     annual_tax: Optional[float] = None,
                     hoa_fee: Optional[float] = None,
                     years: int = YEARS) -> dict:
    """Yearly hold projection, years 0..`years`.

    Rent comes from ZIP-level ZORI when published, else metro typical
    rent; when neither exists the cashflow columns are null but carry,
    amortization, and equity stay valid. Appreciation compounds the
    trailing 12-mo metro ZHVI trend when available, else the national
    default (same assumption the search's 5-yr ROI uses).
    """
    rate_info = get_market_base_rate()
    rate = rate_info["rate"]
    payment = _calculate_monthly_payment(
        list_price, down_pct=DOWN_PCT_DEFAULT, rate=rate)
    loan = list_price * (1 - DOWN_PCT_DEFAULT)
    down = list_price * DOWN_PCT_DEFAULT
    monthly_rate = rate / 100 / 12
    n_payments = 30 * 12  # search payment math is fixed at 30yr

    baseline = get_metro_baseline(city, state) or {}
    appreciation = baseline.get("appreciation_1y")
    if appreciation is not None:
        appreciation_source = "zillow-research-metro"
    else:
        appreciation = APPRECIATION_ASSUMPTION
        appreciation_source = "national-default"

    rent = get_zip_rent(zip_code)
    if rent is not None:
        rent_source = "zillow-zori-zip"
    else:
        rent = baseline.get("typical_rent")
        rent_source = "zillow-zori-metro" if rent is not None else None

    # A published $0 tax is real (HomeSteps bank-owned deals) — only
    # a missing value falls back to the rate assumption.
    base_tax = (annual_tax if annual_tax is not None
                else list_price * TAX_RATE_DEFAULT)
    hoa = hoa_fee if hoa_fee is not None else 0.0

    value0 = estimated_value or list_price

    rows = []
    cum_cf = 0.0
    has_rent = rent is not None
    for year in range(0, years + 1):
        value = value0 * (1 + appreciation) ** year
        balance = _balance_after(loan, monthly_rate, n_payments, year * 12)
        equity = value - balance

        if has_rent:
            rent_y = rent * (1 + RENT_GROWTH) ** max(year - 1, 0)
            # Tax tracks the property value trajectory; insurance is a
            # share of current value.
            tax_y = base_tax * (value / value0)
            ins_y = value * INSURANCE_RATE
            carry_y = payment + tax_y / 12 + ins_y / 12 + hoa
            net_y = rent_y - carry_y
            cum_cf = cum_cf + 12 * net_y if year > 0 else 0.0
            row = {
                "year": year,
                "property_value": round(value, 0),
                "rent_mo": round(rent_y, 2),
                "carry_mo": round(carry_y, 2),
                "net_cf_mo": round(net_y, 2),
                "cum_cf": round(cum_cf, 0),
                "equity": round(equity, 0),
                "net_position": round(
                    equity + cum_cf - SELLING_COST * value, 0),
            }
        else:
            cum_cf = 0.0  # no income side; cashflow columns are null
            row = {
                "year": year,
                "property_value": round(value, 0),
                "rent_mo": None,
                "carry_mo": round(
                    payment + (base_tax * (value / value0)) / 12
                    + value * INSURANCE_RATE / 12 + hoa, 2),
                "net_cf_mo": None,
                "cum_cf": None,
                "equity": round(equity, 0),
                "net_position": round(equity - SELLING_COST * value, 0),
            }
        rows.append(row)

    return {
        "assumptions": {
            "rate_pct": round(rate, 3),
            "rate_source": rate_info["source"],
            "down_pct": DOWN_PCT_DEFAULT,
            "down_payment": round(down, 0),
            "monthly_pi": payment,
            "appreciation": appreciation,
            "appreciation_source": appreciation_source,
            "rent": rent,
            "rent_source": rent_source,
            "rent_growth": RENT_GROWTH,
            "annual_tax": round(base_tax, 0),
            "hoa_fee": hoa,
            "selling_cost_pct": SELLING_COST,
            "loan_years": 30,
        },
        "rows": rows,
    }
