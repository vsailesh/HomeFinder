'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

const PROPERTY_TYPES = [
  { value: 'primary', label: 'Primary Residence', rateAdjustment: 0 },
  { value: 'second_home', label: 'Second Home', rateAdjustment: 0.25 },
  { value: 'investment', label: 'Investment Property', rateAdjustment: 0.5 },
];

const LOAN_TERMS = [
  { value: 30, label: '30-Year Fixed' },
  { value: 20, label: '20-Year Fixed' },
  { value: 15, label: '15-Year Fixed' },
  { value: 10, label: '10-Year Fixed' },
];

const LOAN_TYPES = [
  { value: 'conventional', label: 'Conventional', minCredit: 620 },
  { value: 'fha', label: 'FHA', minCredit: 500 },
  { value: 'va', label: 'VA', minCredit: 580 },
  { value: 'usda', label: 'USDA', minCredit: 640 },
];

const LENDERS = [
  { name: 'Bank of America', rateAdjustment: -0.125 },
  { name: 'Wells Fargo', rateAdjustment: 0 },
  { name: 'Chase', rateAdjustment: -0.0625 },
  { name: 'Quicken Loans', rateAdjustment: 0.0625 },
  { name: 'Better.com', rateAdjustment: -0.1875 },
];

const RATE_FLOOR = 3.0;

// ── Local fallback math (mirrors backend loan_engine) ─────────────────────────
function creditAdjustment(score) {
  if (score >= 780) return -0.75;
  if (score >= 760) return -0.625;
  if (score >= 740) return -0.5;
  if (score >= 720) return -0.375;
  if (score >= 700) return -0.25;
  if (score >= 680) return -0.125;
  if (score >= 660) return 0.125;
  if (score >= 640) return 0.375;
  if (score >= 620) return 0.625;
  return 1.0;
}

function calculateInterestRate(baseRate, creditScore, loanType, propertyType, downPaymentPercent, loanTerm) {
  const loanTypeInfo = LOAN_TYPES.find(lt => lt.value === loanType);
  if (creditScore < loanTypeInfo.minCredit) return null;

  let rate = baseRate;
  rate += creditAdjustment(creditScore);
  if (loanType === 'fha') rate -= 0.25;
  if (loanType === 'va') rate -= 0.5;
  if (loanType === 'usda') rate -= 0.25;
  rate += PROPERTY_TYPES.find(pt => pt.value === propertyType).rateAdjustment;
  if (downPaymentPercent < 5) rate += 0.5;
  else if (downPaymentPercent < 10) rate += 0.25;
  else if (downPaymentPercent < 20) rate += 0.125;
  if (loanTerm === 15) rate -= 0.5;
  else if (loanTerm === 20) rate -= 0.25;
  else if (loanTerm === 10) rate -= 0.75;
  return Math.max(rate, RATE_FLOOR);
}

function monthlyPayment(principal, annualRate, termYears) {
  if (principal <= 0 || annualRate <= 0) return 0;
  const r = annualRate / 100 / 12;
  const n = termYears * 12;
  return principal * (r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1);
}

function localQuote(form, downPayment, baseRate) {
  const loanAmount = Math.max(0, form.homePrice - downPayment);
  const dpPct = form.homePrice > 0 ? (downPayment / form.homePrice) * 100 : 0;
  const rate = calculateInterestRate(baseRate, form.creditScore, form.loanType, form.propertyType, dpPct, form.loanTerm);
  const eligible = rate !== null;

  const monthlyTax = form.propertyTax / 12;
  const monthlyIns = form.homeInsurance / 12;
  const escrow = monthlyTax + monthlyIns + form.hoa;
  const monthlyPI = eligible && loanAmount > 0 ? monthlyPayment(loanAmount, rate, form.loanTerm) : 0;
  const totalMonthly = monthlyPI + escrow;

  const monthlyIncome = form.annualIncome / 12;
  const dti = monthlyIncome > 0 ? ((form.monthlyDebts + totalMonthly) / monthlyIncome) * 100 : 0;

  let maxAffordable = 0;
  if (eligible && monthlyIncome > 0) {
    const maxPayment = monthlyIncome * 0.43 - form.monthlyDebts - escrow;
    if (maxPayment > 0) {
      const r = rate / 100 / 12;
      const n = form.loanTerm * 12;
      if (r > 0) maxAffordable = maxPayment * (Math.pow(1 + r, n) - 1) / (r * Math.pow(1 + r, n)) + downPayment;
    }
  }

  const lenderQuotes = eligible ? LENDERS.map(l => {
    const lr = Math.max(rate + l.rateAdjustment, RATE_FLOOR);
    return { name: l.name, rate: lr, monthly_payment: monthlyPayment(loanAmount, lr, form.loanTerm) };
  }) : [];

  return {
    eligible,
    base_rate: baseRate,
    base_rate_source: 'fallback',
    interest_rate: rate,
    apr: eligible ? rate + 0.3 : null,
    loan_amount: loanAmount,
    down_payment: downPayment,
    down_payment_percent: dpPct,
    monthly_pi: monthlyPI,
    monthly_tax: monthlyTax,
    monthly_insurance: monthlyIns,
    monthly_hoa: form.hoa,
    total_monthly: totalMonthly,
    dti,
    max_affordable_home: maxAffordable,
    lender_quotes: lenderQuotes,
    ineligible_reason: eligible ? null
      : `Credit score below ${LOAN_TYPES.find(l => l.value === form.loanType)?.minCredit} minimum`,
  };
}

function formatCurrency(val) {
  if (val == null) return '—';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val);
}

function formatPercent(val) {
  return val == null ? '—' : val.toFixed(2) + '%';
}

export default function MortgageCalculator({ collapsible = false, defaultExpanded = true }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [formData, setFormData] = useState({
    homePrice: 400000,
    downPayment: 80000,
    downPaymentPercent: 20,
    annualIncome: 100000,
    monthlyDebts: 500,
    creditScore: 740,
    propertyType: 'primary',
    loanTerm: 30,
    loanType: 'conventional',
    propertyTax: 4000,
    homeInsurance: 1200,
    hoa: 0,
  });
  const [useDownPaymentPercent, setUseDownPaymentPercent] = useState(true);
  const [baseRate, setBaseRate] = useState(7.0);
  const [quote, setQuote] = useState(null);
  const debounceRef = useRef(null);

  const downPaymentValue = useDownPaymentPercent
    ? formData.homePrice * (formData.downPaymentPercent / 100)
    : formData.downPayment;

  // Fetch live base market rate once on mount.
  useEffect(() => {
    let cancelled = false;
    fetch('/api/loan/rate')
      .then(r => r.json())
      .then(d => { if (!cancelled && d?.base_rate) setBaseRate(d.base_rate); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const refreshQuote = useCallback(async (form, downPayment) => {
    const payload = {
      home_price: form.homePrice,
      down_payment: downPayment,
      annual_income: form.annualIncome,
      monthly_debts: form.monthlyDebts,
      credit_score: form.creditScore,
      property_type: form.propertyType,
      loan_term: form.loanTerm,
      loan_type: form.loanType,
      annual_property_tax: form.propertyTax,
      annual_home_insurance: form.homeInsurance,
      monthly_hoa: form.hoa,
    };
    try {
      const res = await fetch('/api/loan/quote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('quote failed');
      const data = await res.json();
      setQuote(data);
    } catch {
      // Backend unreachable → instant local fallback using live (or default) base rate.
      setQuote(localQuote(form, downPayment, baseRate));
    }
  }, [baseRate]);

  // Debounced authoritative quote on any input change; instant local quote meanwhile.
  useEffect(() => {
    setQuote(prev => prev ?? localQuote(formData, downPaymentValue, baseRate));
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => refreshQuote(formData, downPaymentValue), 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formData, useDownPaymentPercent, baseRate]);

  const handleChange = (e) => {
    const { name, value, type } = e.target;
    const newValue = type === 'number' || type === 'range' ? parseFloat(value) || 0 : value;
    setFormData(prev => {
      const updated = { ...prev, [name]: newValue };
      if (name === 'downPaymentPercent' && useDownPaymentPercent) {
        updated.downPayment = prev.homePrice * (newValue / 100);
      } else if (name === 'downPayment' && !useDownPaymentPercent) {
        updated.downPaymentPercent = prev.homePrice > 0 ? (newValue / prev.homePrice) * 100 : 0;
      } else if (name === 'homePrice') {
        if (useDownPaymentPercent) updated.downPayment = newValue * (prev.downPaymentPercent / 100);
        else updated.downPaymentPercent = newValue > 0 ? (prev.downPayment / newValue) * 100 : 0;
      }
      return updated;
    });
  };

  const creditRating = formData.creditScore >= 780 ? 'Excellent (780-850)' :
    formData.creditScore >= 740 ? 'Very Good (740-779)' :
    formData.creditScore >= 700 ? 'Good (700-739)' :
    formData.creditScore >= 650 ? 'Fair (650-699)' : 'Poor (300-649)';

  const q = quote || localQuote(formData, downPaymentValue, baseRate);
  const sourceLabel = q.base_rate_source === 'fred' ? 'Live · FRED'
    : q.base_rate_source === 'cache' ? 'Live · cached'
    : q.base_rate_source === 'override' ? 'Custom'
    : 'Estimated';

  return (
    <div className="mortgage-calculator">
      <div
        className="calculator-header"
        onClick={collapsible ? () => setExpanded(!expanded) : undefined}
        style={collapsible ? { cursor: 'pointer' } : undefined}
      >
        <div>
          <h3>Mortgage Calculator</h3>
          <p>Personalized rate from your credit, income & loan profile</p>
        </div>
        <div className="base-rate-badge" title={`Market 30yr base rate: ${formatPercent(q.base_rate)}`}>
          <span className="base-rate-source">{sourceLabel}</span>
          <span className="base-rate-value">Base {formatPercent(q.base_rate)}</span>
          {collapsible && <span className="collapse-caret">{expanded ? '▲' : '▼'}</span>}
        </div>
      </div>

      {(!collapsible || expanded) && (
      <div className="calculator-grid">
        {/* Inputs */}
        <div className="calculator-inputs">
          <div className="input-section">
            <h4>Property Information</h4>
            <div className="form-group">
              <label htmlFor="homePrice">Home Price</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input id="homePrice" name="homePrice" type="number" value={formData.homePrice} onChange={handleChange} min="0" step="1000" />
              </div>
            </div>
            <div className="form-group">
              <label htmlFor="propertyType">Property Type</label>
              <select id="propertyType" name="propertyType" value={formData.propertyType} onChange={handleChange}>
                {PROPERTY_TYPES.map(pt => <option key={pt.value} value={pt.value}>{pt.label}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label>Down Payment</label>
              <div className="down-payment-toggle">
                <button type="button" className={`toggle-btn ${useDownPaymentPercent ? 'active' : ''}`} onClick={() => setUseDownPaymentPercent(true)}>By Percentage</button>
                <button type="button" className={`toggle-btn ${!useDownPaymentPercent ? 'active' : ''}`} onClick={() => setUseDownPaymentPercent(false)}>By Amount</button>
              </div>
              {useDownPaymentPercent ? (
                <div className="input-with-suffix">
                  <input name="downPaymentPercent" type="number" value={formData.downPaymentPercent} onChange={handleChange} min="0" max="100" step="0.1" />
                  <span className="input-suffix">%</span>
                </div>
              ) : (
                <div className="input-with-prefix">
                  <span className="input-prefix">$</span>
                  <input name="downPayment" type="number" value={Math.round(formData.downPayment)} onChange={handleChange} min="0" step="1000" />
                </div>
              )}
              <small className="down-payment-amount">Down payment: {formatCurrency(downPaymentValue)}</small>
            </div>
            <div className="form-group">
              <label htmlFor="loanTerm">Loan Term</label>
              <select id="loanTerm" name="loanTerm" value={formData.loanTerm} onChange={handleChange}>
                {LOAN_TERMS.map(lt => <option key={lt.value} value={lt.value}>{lt.label}</option>)}
              </select>
            </div>
          </div>

          <div className="input-section">
            <h4>Loan Information</h4>
            <div className="form-group">
              <label htmlFor="loanType">Loan Type</label>
              <select id="loanType" name="loanType" value={formData.loanType} onChange={handleChange}>
                {LOAN_TYPES.map(lt => <option key={lt.value} value={lt.value}>{lt.label} (Min: {lt.minCredit}+)</option>)}
              </select>
            </div>
          </div>

          <div className="input-section">
            <h4>Financial Profile</h4>
            <div className="form-group">
              <label htmlFor="creditScore">Credit Score: <strong>{creditRating}</strong></label>
              <input id="creditScore" name="creditScore" type="range" min="300" max="850" value={formData.creditScore} onChange={handleChange} className="credit-range" />
              <div className="range-value">{formData.creditScore}</div>
            </div>
            <div className="form-group">
              <label htmlFor="annualIncome">Annual Household Income</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input id="annualIncome" name="annualIncome" type="number" value={formData.annualIncome} onChange={handleChange} min="0" step="1000" />
              </div>
            </div>
            <div className="form-group">
              <label htmlFor="monthlyDebts">Monthly Debt Payments</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input id="monthlyDebts" name="monthlyDebts" type="number" value={formData.monthlyDebts} onChange={handleChange} min="0" step="50" />
              </div>
              <small>Car loans, student loans, credit cards, etc.</small>
            </div>
          </div>

          <div className="input-section">
            <h4>Additional Costs (Optional)</h4>
            <div className="form-group-inline">
              <div>
                <label htmlFor="propertyTax">Annual Property Tax</label>
                <div className="input-with-prefix">
                  <span className="input-prefix">$</span>
                  <input id="propertyTax" name="propertyTax" type="number" value={formData.propertyTax} onChange={handleChange} min="0" step="100" />
                </div>
              </div>
              <div>
                <label htmlFor="homeInsurance">Annual Home Insurance</label>
                <div className="input-with-prefix">
                  <span className="input-prefix">$</span>
                  <input id="homeInsurance" name="homeInsurance" type="number" value={formData.homeInsurance} onChange={handleChange} min="0" step="100" />
                </div>
              </div>
            </div>
            <div className="form-group">
              <label htmlFor="hoa">Monthly HOA Fees</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input id="hoa" name="hoa" type="number" value={formData.hoa} onChange={handleChange} min="0" step="10" />
              </div>
            </div>
          </div>
        </div>

        {/* Results */}
        <div className="calculator-results">
          <div className="results-card primary">
            <div className="results-header">
              <h4>Your Estimated Rate</h4>
              {!q.eligible && <span className="ineligible-badge">Not Eligible</span>}
            </div>
            {q.eligible ? (
              <>
                <div className="rate-display">
                  <span className="rate-value">{formatPercent(q.interest_rate)}</span>
                  <span className="rate-term">{formData.loanTerm}-Year Fixed</span>
                </div>
                <div className="rate-details">
                  <div className="rate-detail"><span>APR</span><strong>{formatPercent(q.apr)}</strong></div>
                  <div className="rate-detail"><span>Loan Amount</span><strong>{formatCurrency(q.loan_amount)}</strong></div>
                </div>
              </>
            ) : (
              <div className="ineligible-message">{q.ineligible_reason}</div>
            )}
          </div>

          {q.eligible && (
            <div className="results-card">
              <h4>Monthly Payment Breakdown</h4>
              <div className="payment-breakdown">
                <div className="payment-row"><span>Principal & Interest</span><strong>{formatCurrency(q.monthly_pi)}</strong></div>
                <div className="payment-row"><span>Property Tax</span><strong>{formatCurrency(q.monthly_tax)}</strong></div>
                <div className="payment-row"><span>Home Insurance</span><strong>{formatCurrency(q.monthly_insurance)}</strong></div>
                {q.monthly_hoa > 0 && <div className="payment-row"><span>HOA Fees</span><strong>{formatCurrency(q.monthly_hoa)}</strong></div>}
                <div className="payment-row total"><span>Total Monthly Payment</span><strong>{formatCurrency(q.total_monthly)}</strong></div>
              </div>
            </div>
          )}

          <div className="results-card">
            <h4>Affordability Analysis</h4>
            <div className="affordability-metrics">
              <div className="metric">
                <span className="metric-label">Debt-to-Income Ratio</span>
                <span className={`metric-value ${q.dti > 43 ? 'warning' : q.dti > 36 ? 'caution' : 'good'}`}>{q.dti.toFixed(1)}%</span>
              </div>
              <div className="metric">
                <span className="metric-label">Max Affordable Home</span>
                <span className="metric-value">{formatCurrency(q.max_affordable_home)}</span>
              </div>
              <div className="metric">
                <span className="metric-label">Income Required</span>
                <span className="metric-value">{formatCurrency((q.total_monthly * 12) / 0.28)}</span>
              </div>
            </div>
          </div>

          {q.eligible && (
            <div className="results-card">
              <h4>Compare Rates from Lenders</h4>
              <div className="lender-list">
                {q.lender_quotes.map((lender, idx) => (
                  <div key={idx} className="lender-row">
                    <div className="lender-info">
                      <span className="lender-logo">🏦</span>
                      <span className="lender-name">{lender.name}</span>
                    </div>
                    <div className="lender-rate">
                      <span className="rate">{formatPercent(lender.rate)}</span>
                      <span className="payment">{formatCurrency(lender.monthly_payment)}/mo</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
      )}
    </div>
  );
}
