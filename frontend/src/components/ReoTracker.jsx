'use client';

import { useEffect, useState } from 'react';

function formatCurrency(val) {
  if (val == null) return '—';
  return '$' + Number(val).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

function relativeTime(iso) {
  if (!iso) return null;
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return null;
  const mins = Math.round(ms / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

/**
 * REO inventory tracker panel — summary of Freddie Mac HomeSteps
 * listings persisted across daily sweeps, with new/price-cut flags.
 * Listings that arrived (or cut price) since the visitor's previous
 * session get a 🔔 "since your last visit" callout — per-browser via
 * localStorage, no account needed. Renders nothing when the tracker
 * has no active inventory (or the backend is unreachable).
 */
const VISIT_KEY = 'home-finder:last-visit';

export default function ReoTracker() {
  const [data, setData] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [freshIds, setFreshIds] = useState(null); // Set of ids new since last visit

  useEffect(() => {
    let cancelled = false;
    fetch('/api/reo/inventory?days=7')
      .then(res => (res.ok ? res.json() : null))
      .then(json => {
        if (cancelled || !json) return;
        setData(json);
        // Diff against the previous visit's stamp, then restamp —
        // first-ever visits (no stamp) see no callout.
        try {
          const prev = window.localStorage.getItem(VISIT_KEY);
          if (prev) {
            const prevTs = new Date(prev);
            const fresh = (json.listings || []).filter(l =>
              (l.is_new && l.first_seen && new Date(l.first_seen) > prevTs) ||
              (l.price_cut && l.last_price_change &&
                new Date(l.last_price_change) > prevTs));
            setFreshIds(new Set(fresh.map(l => l.id)));
          }
          window.localStorage.setItem(VISIT_KEY, new Date().toISOString());
        } catch {
          // Storage blocked — visit diffing just stays off.
        }
      })
      .catch(() => {}); // panel simply stays hidden
    return () => { cancelled = true; };
  }, []);

  if (!data || !data.summary || data.summary.active === 0) return null;

  const { summary, last_sweep: lastSweep } = data;
  const swept = relativeTime(lastSweep?.finished_at);
  const flagged = (data.listings || []).filter(l => l.is_new || l.price_cut);
  const freshCount = freshIds ? freshIds.size : 0;

  return (
    <section className="reo-tracker">
      <button
        type="button"
        className="reo-tracker-header"
        onClick={() => setExpanded(e => !e)}
      >
        <span>
          🏛 Freddie Mac REO tracker — {summary.active} active across{' '}
          {summary.metros_with_inventory} metro{summary.metros_with_inventory === 1 ? '' : 's'}
          {freshCount > 0 && ` · 🔔 ${freshCount} since your last visit`}
          {summary.new > 0 && ` · ${summary.new} new this week`}
          {summary.price_cuts > 0 && ` · ${summary.price_cuts} price cut${summary.price_cuts === 1 ? '' : 's'}`}
          {swept && ` · swept ${swept}`}
        </span>
        <span className="reo-tracker-toggle">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="reo-tracker-body">
          {flagged.length === 0 && (
            <div className="reo-tracker-empty">
              No new or price-cut listings in the last {data.window_days} days.
            </div>
          )}
          {flagged.map(l => (
            <a
              key={l.id}
              className={`reo-tracker-row${freshIds?.has(l.id) ? ' reo-row-fresh' : ''}`}
              href={l.url || '#'}
              target="_blank"
              rel="noopener noreferrer"
            >
              <span className="reo-tracker-tags">
                {l.is_new && <span className="reo-tag-new">NEW</span>}
                {l.price_cut && (
                  <span className="reo-tag-cut">
                    PRICE CUT {l.price_change_pct}%
                  </span>
                )}
              </span>
              <span className="reo-tracker-addr">
                {l.address}, {l.city}, {l.state}
              </span>
              <span className="reo-tracker-price">
                {l.price_cut && l.prev_price != null && (
                  <s className="reo-prev-price">{formatCurrency(l.prev_price)}</s>
                )}
                {formatCurrency(l.list_price)}
              </span>
            </a>
          ))}
        </div>
      )}
    </section>
  );
}
