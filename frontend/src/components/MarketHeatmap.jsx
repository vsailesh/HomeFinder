'use client';

import { useEffect, useState } from 'react';
import { formatCurrency, formatPercent, formatPct } from '../lib/format';

/**
 * Investor heatmap — every served metro's typical home, side by
 * side: what it costs to carry (P&I + tax + insurance at the live
 * rate) versus what it rents for, ranked best cashflow first.
 * Metros without a published rent sit at the bottom with cashflow
 * "—". Clicking a row runs a search in that metro. Renders nothing
 * when the backend is unreachable or has no valued rows.
 */
export default function MarketHeatmap({ onLoadSearch }) {
  const [data, setData] = useState(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/market/heatmap')
      .then(res => (res.ok ? res.json() : null))
      .then(json => {
        if (!cancelled && json && Array.isArray(json.rows) && json.rows.length) {
          setData(json);
        }
      })
      .catch(() => {}); // panel simply stays hidden
    return () => { cancelled = true; };
  }, []);

  if (!data) return null;

  const best = data.rows.find(r => r.monthly.cashflow != null);

  return (
    <section className="market-heatmap">
      <button
        type="button"
        className="market-heatmap-header"
        onClick={() => setExpanded(e => !e)}
      >
        <span>
          🔥 Investor heatmap — {data.rows.length} metro{data.rows.length === 1 ? '' : 's'} by cashflow
          {best && ` · best: ${best.metro.split(',')[0]} ${formatCurrency(best.monthly.cashflow)}/mo`}
          {data.rate && ` · @ ${formatPercent(data.rate.rate)} 30yr`}
        </span>
        <span className="market-heatmap-toggle">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="market-heatmap-body">
          <table className="heat-table">
            <thead>
              <tr>
                <th>Metro</th>
                <th>Price basis</th>
                <th>Rent</th>
                <th>P&amp;I</th>
                <th>Carry</th>
                <th>Cashflow</th>
                <th>Rent/P&amp;I</th>
                <th>1-yr value</th>
                <th>REO</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map(r => {
                const cf = r.monthly.cashflow;
                const cfClass = cf == null ? 'heat-na'
                  : cf > 0 ? 'heat-pos' : 'heat-neg';
                // Prefer the city that names the metro when picking
                // the search target (Baltimore row lists its suburbs
                // too).
                const target = r.cities.find(c =>
                  r.metro.toLowerCase().startsWith(c.toLowerCase()))
                  || r.cities[0];
                return (
                  <tr
                    key={r.metro}
                    className="heat-row"
                    onClick={() => onLoadSearch && onLoadSearch(
                      { city: target, state: r.state })}
                    title={`Search ${target}, ${r.state} — ${r.cities.join(', ')}`}
                  >
                    <td className="heat-metro">{r.metro}</td>
                    <td>{formatCurrency(r.monthly.price_basis)}</td>
                    <td>{r.typical_rent ? formatCurrency(r.typical_rent) : '—'}</td>
                    <td>{formatCurrency(r.monthly.payment)}</td>
                    <td>{formatCurrency(r.monthly.carry)}</td>
                    <td className={cfClass}>
                      {cf == null ? '—' : formatCurrency(cf)}
                    </td>
                    <td>
                      {r.monthly.rent_coverage != null
                        ? `${r.monthly.rent_coverage}×`
                        : '—'}
                    </td>
                    <td>
                      {r.appreciation_1y != null
                        ? formatPct(r.appreciation_1y * 100)
                        : '—'}
                    </td>
                    <td>{r.reo_active > 0 ? r.reo_active : '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="heat-footnote">
            Typical metro home at {formatPercent(data.rate ? data.rate.rate : 0)} —
            20% down, 30-yr fixed; carry = P&amp;I + tax + insurance (no HOA,
            no vacancy). Cashflow = typical rent − carry. Click a row to search
            that metro.
          </div>
        </div>
      )}
    </section>
  );
}
