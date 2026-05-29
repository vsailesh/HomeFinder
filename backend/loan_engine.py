"""
Loan engine — server-side mortgage rate proration + payment math.

Base 30yr rate is pulled live from FRED (MORTGAGE30US, no API key needed)
and cached in-process with a TTL. Falls back to a static default if the
fetch fails so the API never hard-errors.

Rate proration logic mirrors the original client formula (credit score,
loan type, property type, down payment / LTV, term) so quotes are
consistent and auditable in one place.
"""
from __future__ import annotations

import time
import csv
import io
from dataclasses import dataclass
from typing import Optional

import requests

# ── Live base-rate fetch (FRED, no key) ───────────────────────────────────────
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=MORTGAGE30US"
_STATIC_FALLBACK_RATE = 7.0
_CACHE_TTL_SECONDS = 60 * 60 * 6  # 6h

_rate_cache: dict = {"rate": None, "ts": 0.0, "source": "none"}


def get_market_base_rate(force_refresh: bool = False) -> dict:
    """
    Return current 30yr fixed market base rate.
    {"rate": float, "source": "fred"|"cache"|"fallback", "as_of": <epoch>}
    """
    now = time.time()
    cached = _rate_cache.get("rate")
    if (not force_refresh) and cached is not None and (now - _rate_cache["ts"]) < _CACHE_TTL_SECONDS:
        return {"rate": cached, "source": "cache", "as_of": _rate_cache["ts"]}

    try:
        resp = requests.get(FRED_CSV_URL, timeout=8)
        resp.raise_for_status()
        reader = csv.reader(io.StringIO(resp.text))
        rows = [r for r in reader if r]
        # header row first; data rows: [date, value]; "." means missing
        latest = None
        for row in rows[1:]:
            if len(row) >= 2 and row[1] not in (".", "", None):
                latest = float(row[1])
        if latest is None:
            raise ValueError("no valid FRED rows")
        _rate_cache.update({"rate": latest, "ts": now, "source": "fred"})
        return {"rate": latest, "source": "fred", "as_of": now}
    except Exception as exc:  # network down, parse fail, etc.
        print(f"FRED rate fetch failed ({exc}); using fallback/cache.")
        if cached is not None:
            return {"rate": cached, "source": "cache", "as_of": _rate_cache["ts"]}
        return {"rate": _STATIC_FALLBACK_RATE, "source": "fallback", "as_of": now}


# ── Static reference tables ───────────────────────────────────────────────────
PROPERTY_TYPE_ADJ = {
    "primary": 0.0,
    "second_home": 0.25,
    "investment": 0.5,
}

LOAN_TYPE_MIN_CREDIT = {
    "conventional": 620,
    "fha": 500,
    "va": 580,
    "usda": 640,
}

LOAN_TYPE_ADJ = {
    "conventional": 0.0,
    "fha": -0.25,
    "va": -0.5,
    "usda": -0.25,
}

LENDERS = [
    {"name": "Bank of America", "rate_adjustment": -0.125},
    {"name": "Wells Fargo", "rate_adjustment": 0.0},
    {"name": "Chase", "rate_adjustment": -0.0625},
    {"name": "Quicken Loans", "rate_adjustment": 0.0625},
    {"name": "Better.com", "rate_adjustment": -0.1875},
]

_RATE_FLOOR = 3.0


def _credit_adjustment(credit_score: int) -> float:
    if credit_score >= 780:
        return -0.75
    if credit_score >= 760:
        return -0.625
    if credit_score >= 740:
        return -0.5
    if credit_score >= 720:
        return -0.375
    if credit_score >= 700:
        return -0.25
    if credit_score >= 680:
        return -0.125
    if credit_score >= 660:
        return 0.125
    if credit_score >= 640:
        return 0.375
    if credit_score >= 620:
        return 0.625
    return 1.0


def _down_payment_adjustment(down_payment_percent: float) -> float:
    if down_payment_percent < 5:
        return 0.5
    if down_payment_percent < 10:
        return 0.25
    if down_payment_percent < 20:
        return 0.125
    return 0.0


def _term_adjustment(loan_term: int) -> float:
    return {10: -0.75, 15: -0.5, 20: -0.25, 30: 0.0}.get(loan_term, 0.0)


def prorate_rate(
    base_rate: float,
    credit_score: int,
    loan_type: str,
    property_type: str,
    down_payment_percent: float,
    loan_term: int,
) -> Optional[float]:
    """Prorate the market base rate by borrower/loan attributes.
    Returns None if credit below the loan type minimum (ineligible)."""
    min_credit = LOAN_TYPE_MIN_CREDIT.get(loan_type, 620)
    if credit_score < min_credit:
        return None

    rate = base_rate
    rate += _credit_adjustment(credit_score)
    rate += LOAN_TYPE_ADJ.get(loan_type, 0.0)
    rate += PROPERTY_TYPE_ADJ.get(property_type, 0.0)
    rate += _down_payment_adjustment(down_payment_percent)
    rate += _term_adjustment(loan_term)
    return round(max(rate, _RATE_FLOOR), 3)


def monthly_payment(principal: float, annual_rate: float, term_years: int) -> float:
    if principal <= 0 or annual_rate <= 0:
        return 0.0
    monthly_rate = annual_rate / 100 / 12
    n = term_years * 12
    return principal * (monthly_rate * (1 + monthly_rate) ** n) / ((1 + monthly_rate) ** n - 1)


@dataclass
class LoanQuote:
    eligible: bool
    base_rate: float
    base_rate_source: str
    interest_rate: Optional[float]
    apr: Optional[float]
    loan_amount: float
    down_payment: float
    down_payment_percent: float
    monthly_pi: float
    monthly_tax: float
    monthly_insurance: float
    monthly_hoa: float
    total_monthly: float
    dti: float
    max_affordable_home: float
    lender_quotes: list
    ineligible_reason: Optional[str] = None


def quote_loan(
    home_price: float,
    down_payment: float,
    annual_income: float,
    monthly_debts: float,
    credit_score: int,
    property_type: str = "primary",
    loan_term: int = 30,
    loan_type: str = "conventional",
    annual_property_tax: float = 0.0,
    annual_home_insurance: float = 0.0,
    monthly_hoa: float = 0.0,
    base_rate_override: Optional[float] = None,
) -> LoanQuote:
    base_info = (
        {"rate": base_rate_override, "source": "override"}
        if base_rate_override is not None
        else get_market_base_rate()
    )
    base_rate = base_info["rate"]

    loan_amount = max(0.0, home_price - down_payment)
    dp_pct = (down_payment / home_price * 100) if home_price > 0 else 0.0

    rate = prorate_rate(base_rate, credit_score, loan_type, property_type, dp_pct, loan_term)
    eligible = rate is not None

    monthly_tax = annual_property_tax / 12
    monthly_ins = annual_home_insurance / 12
    monthly_escrow = monthly_tax + monthly_ins + monthly_hoa

    monthly_pi = monthly_payment(loan_amount, rate, loan_term) if (eligible and loan_amount > 0) else 0.0
    total_monthly = monthly_pi + monthly_escrow

    monthly_income = annual_income / 12 if annual_income > 0 else 0.0
    dti = ((monthly_debts + total_monthly) / monthly_income * 100) if monthly_income > 0 else 0.0

    # Max affordable home @ 43% DTI back-end
    max_affordable = 0.0
    if eligible and monthly_income > 0:
        max_payment = monthly_income * 0.43 - monthly_debts - monthly_escrow
        if max_payment > 0:
            mr = rate / 100 / 12
            n = loan_term * 12
            if mr > 0:
                max_loan = max_payment * ((1 + mr) ** n - 1) / (mr * (1 + mr) ** n)
                max_affordable = max_loan + down_payment

    lender_quotes = []
    if eligible:
        for ld in LENDERS:
            lr = round(max(rate + ld["rate_adjustment"], _RATE_FLOOR), 3)
            lender_quotes.append({
                "name": ld["name"],
                "rate": lr,
                "monthly_payment": round(monthly_payment(loan_amount, lr, loan_term), 2),
            })

    return LoanQuote(
        eligible=eligible,
        base_rate=round(base_rate, 3),
        base_rate_source=base_info["source"],
        interest_rate=rate,
        apr=round(rate + 0.3, 3) if eligible else None,
        loan_amount=round(loan_amount, 2),
        down_payment=round(down_payment, 2),
        down_payment_percent=round(dp_pct, 2),
        monthly_pi=round(monthly_pi, 2),
        monthly_tax=round(monthly_tax, 2),
        monthly_insurance=round(monthly_ins, 2),
        monthly_hoa=round(monthly_hoa, 2),
        total_monthly=round(total_monthly, 2),
        dti=round(dti, 2),
        max_affordable_home=round(max_affordable, 2),
        lender_quotes=lender_quotes,
        ineligible_reason=(
            None if eligible
            else f"Credit score {credit_score} below {loan_type} minimum {LOAN_TYPE_MIN_CREDIT.get(loan_type, 620)}"
        ),
    )
