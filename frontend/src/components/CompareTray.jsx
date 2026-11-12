'use client';

import { useState } from 'react';

const MAX_COMPARE = 4;

function formatCurrency(val) {
  if (val == null) return '—';
  return '$' + Number(val).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

function formatSigned(val, suffix = '') {
  if (val == null) return '—';
  return `${val >= 0 ? '+' : ''}${formatCurrency(val).replace('$-', '-$')}${suffix}`;
}

function formatPct(val, digits = 1) {
  if (val == null) return '—';
  return `${val >= 0 ? '+' : ''}${val.toFixed(digits)}%`;
}

/**
 * Side-by-side shortlist. Deals live in localStorage as full result
 * objects (per-browser — no account system, no per-property GET
 * endpoint), so a comparison survives pagination and reloads.
 */
export default function CompareTray({ deals, onRemove, onClear }) {
  const [open, setOpen] = useState(false);
  const list = deals || [];

  const rows = [
    {
      label: 'Score',
      get: (d) => `${Math.round(d.deal_score)} · ${d.deal_grade || '—'}`,
    },
    {
      label: 'Asking',
      get: (d) => formatCurrency(d.property.list_price),
    },
    {
      label: 'Est. value',
      get: (d) => {
        const pct = d.valuation?.price_difference_pct;
        return pct == null ? '—' : `${formatCurrency(d.valuation.estimated_value)} (${formatPct(pct)})`;
      },
    },
    {
      label: 'Est. rent',
      get: (d) => (d.estimated_rent == null ? '—' : `${formatCurrency(d.estimated_rent)}/mo`),
    },
    {
      label: 'P&I (20% down)',
      get: (d) => (d.monthly_payment_estimate == null ? '—' : `${formatCurrency(d.monthly_payment_estimate)}/mo`),
    },
    {
      label: 'Full carry',
      get: (d) => (d.monthly_carry_estimate == null ? '—' : `${formatCurrency(d.monthly_carry_estimate)}/mo`),
    },
    {
      label: 'Net cashflow',
      get: (d) => (d.net_monthly_cashflow == null ? '—' : formatSigned(d.net_monthly_cashflow, '/mo')),
      className: (d) => (d.net_monthly_cashflow >= 0 ? 'cmp-pos' : 'cmp-neg'),
    },
    {
      label: 'Rent / P&I',
      get: (d) => {
        if (d.estimated_rent == null || !d.monthly_payment_estimate) return '—';
        return `${(d.estimated_rent / d.monthly_payment_estimate).toFixed(2)}×`;
      },
    },
    {
      label: '$/sqft',
      get: (d) => (d.property.sqft ? `$${Math.round(d.property.list_price / d.property.sqft)}` : '—'),
    },
    {
      label: '5-yr ROI',
      get: (d) => formatPct(d.estimated_roi_5yr),
      className: (d) => (d.estimated_roi_5yr >= 0 ? 'cmp-pos' : 'cmp-neg'),
    },
  ];

  return (
    <div className="compare-tray">
      <button type="button" className="compare-header" onClick={() => setOpen(!open)}>
        <span>
          ⚖️ Compare <span className="compare-count">({list.length}/{MAX_COMPARE})</span>
        </span>
        <span className="compare-header-right">
          {list.length > 0 && (
            <span
              className="compare-clear"
              role="button"
              tabIndex={0}
              onClick={(e) => { e.stopPropagation(); onClear(); }}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); onClear(); } }}
            >
              clear
            </span>
          )}
          <span className="compare-caret">{open ? '▲' : '▼'}</span>
        </span>
      </button>

      {open && (
        list.length === 0 ? (
          <div className="compare-empty">
            No deals shortlisted yet — tap <strong>± Compare</strong> on any property card.
          </div>
        ) : (
          <div className="compare-scroll">
            <table className="compare-table">
              <thead>
                <tr>
                  <th className="compare-metric-col">Metric</th>
                  {list.map((d) => (
                    <th key={d.property.id}>
                      <div className="compare-col-head">
                        <span className="compare-col-address" title={d.property.address}>
                          {d.property.address}
                        </span>
                        <span className="compare-col-sub">
                          {d.property.city}, {d.property.state}
                        </span>
                        {d.property.source === 'homesteps-freddie-mac' && (
                          <span className="reo-badge">🏦 REO</span>
                        )}
                        {d.property.source === 'mock-generator' && (
                          <span className="demo-badge">Demo</span>
                        )}
                        {d.reo_tracker?.is_new && <span className="reo-badge reo-tag-new">NEW</span>}
                        {d.reo_tracker?.price_cut && (
                          <span className="reo-badge reo-tag-cut">CUT {d.reo_tracker.price_change_pct}%</span>
                        )}
                        <button
                          type="button"
                          className="compare-remove"
                          onClick={() => onRemove(d.property.id)}
                          aria-label={`Remove ${d.property.address} from compare`}
                        >
                          ✕
                        </button>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.label}>
                    <td className="compare-metric-col">{r.label}</td>
                    {list.map((d) => {
                      const cls = r.className ? r.className(d) : '';
                      return (
                        <td key={d.property.id} className={cls}>{r.get(d)}</td>
                      );
                    })}
                  </tr>
                ))}
                <tr>
                  <td className="compare-metric-col">Listing</td>
                  {list.map((d) => (
                    <td key={d.property.id}>
                      {d.property.url ? (
                        <a href={d.property.url} target="_blank" rel="noopener noreferrer">
                          view ↗
                        </a>
                      ) : '—'}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  );
}
