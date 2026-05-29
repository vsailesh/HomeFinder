'use client';

import { useState } from 'react';

function formatCurrency(val) {
  if (val == null) return '—';
  return '$' + Number(val).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

function gradeClass(grade) {
  const g = (grade || '').replace('+', '-plus').toLowerCase();
  return `grade-${g}`;
}

function categoryClass(cat) {
  return `cat-${cat}`;
}

export default function PropertyCard({ deal }) {
  const [showVars, setShowVars] = useState(false);

  const { property: prop, valuation: val, deal_score, deal_grade,
          reasons, risk_factors, monthly_payment_estimate, estimated_roi_5yr } = deal;

  const priceDiff = val.price_difference;
  const priceDiffPct = val.price_difference_pct;
  const isGoodDeal = priceDiff > 0;

  return (
    <div className={`property-card ${gradeClass(deal_grade)}`} id={`property-${prop.id}`}>
      {/* Top: Score + Address */}
      <div className="property-card-top">
        <div className="property-headline">
          <div className="property-address" title={prop.address}>
            {prop.address}
          </div>
          <div className="property-location">
            {prop.city}, {prop.state} {prop.zip_code}
            {prop.county && ` · ${prop.county}`}
          </div>
        </div>
        <div className="deal-badge">
          <div className="deal-score-circle">{Math.round(deal_score)}</div>
          <div className="deal-grade-label">{deal_grade}</div>
        </div>
      </div>

      {/* Stats row */}
      <div className="property-stats">
        <span className="prop-stat">🛏 <strong>{prop.bedrooms}</strong> Beds</span>
        <span className="prop-stat">🛁 <strong>{prop.bathrooms}</strong> Baths</span>
        <span className="prop-stat">📐 <strong>{prop.sqft?.toLocaleString()}</strong> sqft</span>
        {prop.lot_sqft && (
          <span className="prop-stat">🌳 <strong>{(prop.lot_sqft / 43560).toFixed(2)}</strong> acres</span>
        )}
        {prop.year_built && (
          <span className="prop-stat">📅 <strong>{prop.year_built}</strong></span>
        )}
        <span className="prop-stat">📊 <strong>{prop.condition}</strong></span>
        {prop.days_on_market != null && (
          <span className="prop-stat">⏱ <strong>{prop.days_on_market}</strong> days</span>
        )}
      </div>

      {/* Price comparison */}
      <div className="price-comparison">
        <div className="price-block">
          <div className="price-block-label">Asking Price</div>
          <div className="price-block-value price-asking">
            {formatCurrency(prop.list_price)}
          </div>
        </div>
        <div className="price-block">
          <div className="price-block-label">Estimated Value</div>
          <div className="price-block-value price-estimated">
            {formatCurrency(val.estimated_value)}
          </div>
        </div>
      </div>

      {/* Price difference */}
      <div className="price-diff">
        <span className={`price-diff-value ${isGoodDeal ? 'price-diff-positive' : 'price-diff-negative'}`}>
          {isGoodDeal ? '▲' : '▼'} {formatCurrency(Math.abs(priceDiff))} ({priceDiffPct > 0 ? '+' : ''}{priceDiffPct.toFixed(1)}%)
        </span>
      </div>

      {/* Monthly payment & ROI */}
      <div className="monthly-info">
        <div>
          <div className="monthly-label">Est. Monthly (20% down)</div>
          <div className="monthly-value">{formatCurrency(monthly_payment_estimate)}/mo</div>
        </div>
        <div>
          <div className="monthly-label">5yr ROI Estimate</div>
          <div className={`roi-value ${estimated_roi_5yr >= 0 ? 'roi-positive' : 'roi-negative'}`}>
            {estimated_roi_5yr >= 0 ? '+' : ''}{estimated_roi_5yr?.toFixed(1)}%
          </div>
        </div>
        <div>
          <div className="monthly-label">$/sqft vs Market</div>
          <div className="monthly-value" style={{ fontSize: 14 }}>
            ${val.price_per_sqft?.toFixed(0)} vs ${val.market_price_per_sqft?.toFixed(0)}
          </div>
        </div>
      </div>

      {/* Variables breakdown */}
      <div className="variables-section">
        <button
          className="variables-toggle"
          onClick={() => setShowVars(!showVars)}
          type="button"
        >
          {showVars ? '▲' : '▼'} Price Variables Breakdown ({val.variables?.length || 0} factors)
        </button>

        {showVars && (
          <div className="variables-list">
            {(val.variables || []).map((v, i) => (
              <div className="variable-row" key={i}>
                <span className="variable-name">{v.name}</span>
                <span className={`variable-category ${categoryClass(v.category)}`}>
                  {v.category}
                </span>
                <span className={`variable-impact ${
                  v.raw_impact > 0 ? 'impact-positive' :
                  v.raw_impact < 0 ? 'impact-negative' : 'impact-neutral'
                }`}>
                  {v.raw_impact > 0 ? '+' : ''}{formatCurrency(v.raw_impact)}
                  {' '}({v.percentage_impact > 0 ? '+' : ''}{v.percentage_impact?.toFixed(1)}%)
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Reasons & Risks */}
      <div className="card-footer">
        <div className="footer-list reasons-list">
          <div className="footer-list-title reasons">✓ Why It's a Deal</div>
          <ul>
            {(reasons || []).slice(0, 3).map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
        <div className="footer-list risks-list">
          <div className="footer-list-title risks">⚠ Risk Factors</div>
          <ul>
            {(risk_factors || []).slice(0, 3).map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
