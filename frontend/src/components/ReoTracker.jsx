'use client';

import { useEffect, useState } from 'react';

const SAVED_KEY = 'home-finder:saved-searches';

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
 * Does a tracker listing satisfy a saved search's criteria? Only the
 * fields the tracker carries are enforced (location, price, beds,
 * baths, sqft) — rent-coverage/sort criteria don't apply to raw REO
 * inventory. A saved metro ("Baltimore") matches listings in its
 * suburbs ("Gwynn Oak") via the tracker's metro tag — the metro each
 * listing was swept under — with city equal-or-contains as fallback.
 * State is the real gate.
 */
export function matchesSavedSearch(l, p = {}) {
  if (p.state && (l.state || '').toUpperCase() !== String(p.state).toUpperCase()) return false;
  if (p.city) {
    const want = String(p.city).toLowerCase();
    const have = (l.city || '').toLowerCase();
    const metro = (l.metro || '').toLowerCase();
    const cityHit = have === want || have.includes(want) || want.includes(have);
    if (!cityHit && metro !== want) return false;
  }
  if (p.zip_code && l.zip_code && String(l.zip_code) !== String(p.zip_code)) return false;
  if (p.max_price != null && l.list_price > Number(p.max_price)) return false;
  if (p.min_price != null && l.list_price < Number(p.min_price)) return false;
  if (p.min_bedrooms != null && (l.bedrooms || 0) < Number(p.min_bedrooms)) return false;
  if (p.max_bedrooms != null && l.bedrooms != null && l.bedrooms > Number(p.max_bedrooms)) return false;
  if (p.min_bathrooms != null && (l.bathrooms || 0) < Number(p.min_bathrooms)) return false;
  if (p.min_sqft != null && l.sqft != null && l.sqft < Number(p.min_sqft)) return false;
  if (p.max_sqft != null && l.sqft != null && l.sqft > Number(p.max_sqft)) return false;
  return true;
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

export default function ReoTracker({ onLoadSearch }) {
  const [data, setData] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [freshIds, setFreshIds] = useState(null); // Set of ids new since last visit
  const [savedSearches, setSavedSearches] = useState([]);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(SAVED_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) setSavedSearches(parsed);
      }
    } catch {
      // Corrupt storage — no saved-search matching this visit.
    }
  }, []);

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
            // Timestamp-driven, not flag-driven: the is_new/price_cut
            // flags age out after 7 days, but a visitor back after a
            // month still wants everything that moved since their
            // visit. Cuts only (prev_price above current) — price
            // increases aren't "fresh".
            const fresh = (json.listings || []).filter(l =>
              (l.first_seen && new Date(l.first_seen) > prevTs) ||
              (l.last_price_change &&
                new Date(l.last_price_change) > prevTs &&
                l.prev_price != null && l.list_price < l.prev_price));
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

  // Saved searches × active REO inventory (client-side; the tracker
  // already holds every swept listing, so no extra requests).
  const savedMatches = savedSearches
    .map(search => ({
      search,
      listings: (data.listings || []).filter(l => matchesSavedSearch(l, search.params)),
    }))
    .filter(m => m.listings.length > 0);

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
          {savedMatches.length > 0 && (
            <div className="reo-saved-matches">
              <div className="reo-saved-matches-title">📌 Saved-search REO matches</div>
              {savedMatches.map(({ search, listings }) => (
                <button
                  key={search.id}
                  type="button"
                  className="reo-saved-match-row"
                  onClick={() => onLoadSearch && onLoadSearch(search.params)}
                  title={listings.map(l => `${l.address}, ${l.city} — ${formatCurrency(l.list_price)}`).join('\n')}
                >
                  <span className="reo-saved-match-name">{search.name}</span>
                  <span className="reo-saved-match-count">
                    {listings.length} REO match{listings.length === 1 ? '' : 'es'}
                    {listings.some(l => l.is_new) && ' · new arrivals'}
                  </span>
                </button>
              ))}
            </div>
          )}
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
