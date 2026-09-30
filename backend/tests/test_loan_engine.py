"""Loan engine math tests — rate proration, payments, quotes."""
from loan_engine import (
    prorate_rate, monthly_payment, quote_loan, _credit_adjustment,
)


class TestProrateRate:
    def test_excellent_credit_discounts(self):
        rate = prorate_rate(7.0, 800, "conventional", "primary", 20, 30)
        assert rate < 7.0

    def test_poor_credit_adds(self):
        rate = prorate_rate(7.0, 620, "conventional", "primary", 20, 30)
        assert rate > 7.0

    def test_below_min_credit_ineligible(self):
        # FHA minimum is 500
        assert prorate_rate(7.0, 480, "fha", "primary", 20, 30) is None

    def test_va_min_credit(self):
        assert prorate_rate(7.0, 570, "va", "primary", 20, 30) is None
        assert prorate_rate(7.0, 590, "va", "primary", 20, 30) is not None

    def test_rate_floor(self):
        # Big stack of discounts can't go below 3.0
        rate = prorate_rate(3.5, 800, "va", "primary", 25, 10)
        assert rate == 3.0

    def test_credit_adjustment_monotonic(self):
        scores = [620, 660, 700, 740, 780]
        adj = [_credit_adjustment(s) for s in scores]
        # Adjustment declines as score rises (better credit = lower add-on)
        assert adj == sorted(adj, reverse=True)
        assert adj[0] > adj[-1]


class TestMonthlyPayment:
    def test_known_value(self):
        # $360k @ 6% 30yr -> P&I ~$2158.38
        p = monthly_payment(360000, 6.0, 30)
        assert abs(p - 2158.38) < 1.0

    def test_zero_inputs(self):
        assert monthly_payment(0, 6.0, 30) == 0.0
        assert monthly_payment(100000, 0, 30) == 0.0


class TestQuoteLoan:
    def test_eligible_quote_shape(self):
        q = quote_loan(
            home_price=500000, down_payment=100000, annual_income=150000,
            monthly_debts=500, credit_score=750,
            annual_property_tax=6000, annual_home_insurance=1500,
        )
        assert q.eligible
        assert q.loan_amount == 400000
        assert q.down_payment_percent == 20.0
        assert q.monthly_pi > 0
        assert q.total_monthly == round(
            q.monthly_pi + 500 + 125 + 0, 2)
        assert len(q.lender_quotes) == 5
        assert q.ineligible_reason is None

    def test_ineligible_quote(self):
        q = quote_loan(
            home_price=300000, down_payment=15000, annual_income=80000,
            monthly_debts=300, credit_score=590, loan_type="conventional",
        )
        assert not q.eligible
        assert q.interest_rate is None
        assert q.monthly_pi == 0
        assert "minimum" in q.ineligible_reason
        assert q.lender_quotes == []

    def test_dti(self):
        q = quote_loan(
            home_price=500000, down_payment=100000, annual_income=120000,
            monthly_debts=1000, credit_score=740,
            annual_property_tax=6000, annual_home_insurance=1200,
        )
        # DTI = (debts + total_monthly) / monthly_income
        expected = (1000 + q.total_monthly) / (120000 / 12) * 100
        assert abs(q.dti - expected) < 0.5

    def test_rate_override(self):
        q = quote_loan(
            home_price=400000, down_payment=80000, annual_income=100000,
            monthly_debts=0, credit_score=780, base_rate_override=10.0,
        )
        assert q.base_rate == 10.0
        assert q.base_rate_source == "override"
