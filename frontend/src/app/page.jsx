'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import SearchForm, { DEFAULT_SPECS, cleanParams } from '../components/SearchForm';
import SavedSearches from '../components/SavedSearches';
import ReoTracker from '../components/ReoTracker';
import MarketHeatmap from '../components/MarketHeatmap';
import PropertyCard from '../components/PropertyCard';
import CompareTray from '../components/CompareTray';
import MortgageCalculator from '../components/MortgageCalculator';
import { PriceDistributionChart, DealScoreChart, ValueVsPriceChart, SqftVsPriceScatter } from '../components/Charts';
import { formatCurrency } from '../lib/format';

const PAGE_SIZE = 12;
const COMPARE_KEY = 'home-finder:compare';
const MAX_COMPARE = 4;

// URL <-> search sync: every search is reflected in the address bar
// (shareable/bookmarkable), and a URL carrying search params runs that
// search on load. Page numbers stay out — a bookmark should land on
// page 1 of a fresh search, not a stale offset.
const NUMERIC_URL_KEYS = new Set([
  'min_price', 'max_price', 'min_bedrooms', 'max_bedrooms',
  'min_bathrooms', 'max_bathrooms', 'min_sqft', 'max_sqft',
  'min_year_built', 'max_year_built', 'max_hoa', 'max_days_on_market',
  'min_rent_coverage',
]);
// Backend declares these as ints (FastAPI 422s on 2.5) — URL values
// must be whole numbers or the shared link is a dead end.
const INTEGER_URL_KEYS = new Set([
  'min_bedrooms', 'max_bedrooms', 'min_sqft', 'max_sqft',
  'min_year_built', 'max_year_built', 'max_days_on_market',
]);
const URL_KEYS = new Set([
  'city', 'state', 'county', 'property_type', 'sort_by',
  'must_have_pool', 'must_have_basement', 'must_have_garage',
  ...NUMERIC_URL_KEYS,
]);
const PROPERTY_TYPES = new Set([
  'single_family', 'condo', 'townhouse', 'multi_family', 'land',
]);
const SORT_OPTIONS = new Set([
  'deal_score', 'price_asc', 'price_desc', 'cashflow_desc', 'newest',
]);

export function specsFromUrl() {
  const out = {};
  new URLSearchParams(window.location.search).forEach((raw, key) => {
    if (!URL_KEYS.has(key) || raw === '') return;
    if (key.startsWith('must_have_')) {
      if (raw === 'true') out[key] = true;
    } else if (NUMERIC_URL_KEYS.has(key)) {
      const n = Number(raw);
      // Negative values fail backend ge=0 constraints — a mistyped
      // link degrades to "param ignored", not a 422 banner.
      if (!Number.isNaN(n) && n >= 0
          && (!INTEGER_URL_KEYS.has(key) || Number.isInteger(n))) {
        out[key] = n;
      }
    } else if (key === 'property_type') {
      if (PROPERTY_TYPES.has(raw)) out[key] = raw;
    } else if (key === 'sort_by') {
      if (SORT_OPTIONS.has(raw)) out[key] = raw;
    } else {
      out[key] = raw;
    }
  });
  return out;
}

export function toQuery(obj) {
  const q = new URLSearchParams();
  Object.entries(obj).forEach(([key, val]) => {
    if (val !== '' && val !== false && val != null) q.set(key, String(val));
  });
  return q;
}

export default function HomePage() {
  const [specs, setSpecs] = useState(DEFAULT_SPECS);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastParams, setLastParams] = useState(null);
  const [page, setPage] = useState(1);
  const [compareDeals, setCompareDeals] = useState([]);

  // Compare shortlist — hydrate from localStorage (full deal objects,
  // so the tray survives pagination and reloads without a per-property
  // backend endpoint).
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(COMPARE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) setCompareDeals(parsed.slice(0, MAX_COMPARE));
      }
    } catch {
      window.localStorage.removeItem(COMPARE_KEY); // corrupt — start fresh
    }
  }, []);

  const persistCompare = useCallback((next) => {
    setCompareDeals(next);
    try {
      window.localStorage.setItem(COMPARE_KEY, JSON.stringify(next));
    } catch {
      // Storage full/blocked — keep in-memory copy only.
    }
  }, []);

  const handleToggleCompare = useCallback((deal) => {
    const id = deal.property.id;
    if (compareDeals.some(d => d.property.id === id)) {
      persistCompare(compareDeals.filter(d => d.property.id !== id));
    } else if (compareDeals.length < MAX_COMPARE) {
      persistCompare([...compareDeals, { ...deal, saved_at: new Date().toISOString() }]);
    }
  }, [compareDeals, persistCompare]);

  const compareIds = new Set(compareDeals.map(d => d.property.id));
  const compareFull = compareDeals.length >= MAX_COMPARE;

  // Sequence token: overlapping searches (a slow first request can
  // resolve after a newer one) — only the latest request may write
  // results/params/page/URL, so a stale response can't clobber it.
  const searchSeq = useRef(0);

  const runSearch = useCallback(async (params, pageNum = 1) => {
    const token = ++searchSeq.current;
    setLoading(true);
    setError(null);
    try {
      const query = toQuery(params);
      query.set('page', String(pageNum));
      query.set('page_size', String(PAGE_SIZE));
      const res = await fetch(`/api/search?${query.toString()}`);
      if (!res.ok) throw new Error(`Search failed (${res.status})`);
      const data = await res.json();
      if (token !== searchSeq.current) return; // superseded mid-flight
      setResults(data);
      setLastParams(params);
      setPage(pageNum);
      // Reflect the search in the address bar (replaceState — no
      // history spam while paginating).
      try {
        const qs = toQuery(params).toString();
        window.history.replaceState(null, '', qs ? `/?${qs}` : '/');
      } catch {
        // history API blocked — sharing stays off, search unaffected
      }
    } catch (err) {
      if (token !== searchSeq.current) return; // superseded — bury it
      console.error('Search failed:', err);
      setError(err.message || 'Search failed. Is the backend reachable?');
    } finally {
      if (token === searchSeq.current) setLoading(false);
    }
  }, []);

  const handleSearch = useCallback((params) => {
    runSearch(params, 1);
  }, [runSearch]);

  // A shared/bookmarked URL (?city=Detroit&max_price=100000) runs
  // its search on load, form pre-filled to match.
  useEffect(() => {
    const fromUrl = specsFromUrl();
    if (Object.keys(fromUrl).length === 0) return;
    const merged = { ...DEFAULT_SPECS, ...fromUrl };
    setSpecs(merged);
    runSearch(cleanParams(merged), 1);
  }, [runSearch]);

  const handleSort = useCallback((newSort) => {
    if (!lastParams) return;
    runSearch({ ...lastParams, sort_by: newSort }, 1);
  }, [lastParams, runSearch]);

  const goToPage = useCallback((pageNum) => {
    if (!lastParams || loading) return;
    if (pageNum < 1) return;
    if (results?.total_pages && pageNum > results.total_pages) return;
    runSearch(lastParams, pageNum);
  }, [lastParams, loading, results, runSearch]);

  // Saved-search load: repopulate the form, then re-run.
  const handleLoadSaved = useCallback((params) => {
    const merged = { ...DEFAULT_SPECS, ...params };
    setSpecs(merged);
    runSearch(cleanParams(merged), 1);
  }, [runSearch]);

  const stats = results?.market_stats;
  const baseline = results?.market_baseline;
  const baselineApprec = baseline?.appreciation_1y;
  const deals = results?.deals || [];
  const sources = new Set(deals.map(d => d.property.source));
  const dataSource = results?.data_source;
  // cached_at arrives as epoch SECONDS (backend time.time()) — JS
  // Dates take milliseconds, so convert before diffing.
  const cacheAgeHours = dataSource?.cached_at
    ? Math.round((Date.now() - new Date(dataSource.cached_at * 1000).getTime()) / 3600000)
    : null;
  const sourceNote = dataSource?.tier === 'zillow-cache'
    ? `⚠️ Live listings API unreachable — showing real Zillow listings cached ${cacheAgeHours != null ? `${cacheAgeHours}h` : ''} ago. Fresh data returns when the provider recovers.`
    : sources.size === 1 && sources.has('homesteps-freddie-mac')
      ? '🏦 Showing real Freddie Mac REO listings — bank-owned inventory is limited. Full Zillow coverage returns when the listings API quota resets.'
      : sources.size === 1 && sources.has('mock-generator')
        ? '⚠️ Demo data — no live listings available for this search right now.'
        : null;
  const totalPages = results?.total_pages || 0;
  const sortBy = results?.search_specs?.sort_by || 'deal_score';
  const rangeStart = results?.total_results
    ? (page - 1) * PAGE_SIZE + 1 : 0;
  const rangeEnd = results?.total_results
    ? Math.min(page * PAGE_SIZE, results.total_results) : 0;

  return (
    <main className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="header-content">
          <div className="logo-section">
            <div className="logo-icon">🏠</div>
            <div className="logo-text">
              <h1>Home Finder</h1>
              <p>Deal Optimizer & Market Analyzer</p>
            </div>
          </div>
          {stats && (
            <div className="header-stats">
              <div className="header-stat">
                <div className="header-stat-value">{results.total_results}</div>
                <div className="header-stat-label">Properties</div>
              </div>
              <div className="header-stat">
                <div className="header-stat-value">{formatCurrency(stats.median_price)}</div>
                <div className="header-stat-label">Median Price</div>
              </div>
              <div className="header-stat">
                <div className="header-stat-value">${stats.avg_price_per_sqft?.toFixed(0)}/sqft</div>
                <div className="header-stat-label">Avg $/Sqft</div>
              </div>
            </div>
          )}
        </div>
      </header>

      {/* Mortgage Calculator */}
      <MortgageCalculator collapsible defaultExpanded={false} />

      {/* Search Form */}
      <SearchForm
        specs={specs}
        onSpecsChange={setSpecs}
        onSearch={handleSearch}
        loading={loading}
      />

      {/* Saved Searches */}
      <SavedSearches
        currentParams={lastParams ? cleanParams(specs) : {}}
        onLoad={handleLoadSaved}
      />

      {/* REO inventory tracker */}
      <ReoTracker onLoadSearch={handleLoadSaved} />

      {/* Investor heatmap — metro vs metro */}
      <MarketHeatmap onLoadSearch={handleLoadSaved} />

      {/* Compare shortlist */}
      <CompareTray
        deals={compareDeals}
        onRemove={(id) => persistCompare(compareDeals.filter(d => d.property.id !== id))}
        onClear={() => persistCompare([])}
      />

      {/* Loading */}
      {loading && (
        <div className="loading-container">
          <div className="loader"></div>
          <div className="loading-text">Analyzing properties and calculating fair market values...</div>
        </div>
      )}

      {/* Search error */}
      {error && !loading && <div className="search-error">{error}</div>}

      {/* Results */}
      {!loading && results && (
        <>
          {/* Market Stats Bar */}
          {stats && (
            <div className="market-stats-bar">
              <div className="market-stat-card">
                <div className="market-stat-value">{formatCurrency(stats.median_price)}</div>
                <div className="market-stat-label">Median Price</div>
              </div>
              <div className="market-stat-card">
                <div className="market-stat-value">${stats.avg_price_per_sqft?.toFixed(0)}</div>
                <div className="market-stat-label">Avg $/Sqft</div>
              </div>
              <div className="market-stat-card">
                <div className="market-stat-value">{stats.median_days_on_market}d</div>
                <div className="market-stat-label">Median Days on Market</div>
              </div>
              <div className="market-stat-card">
                <div className="market-stat-value">{stats.total_listings}</div>
                <div className="market-stat-label">Total Listings</div>
              </div>
              <div className="market-stat-card">
                <div className="market-stat-value">{stats.avg_year_built}</div>
                <div className="market-stat-label">Avg Year Built</div>
              </div>
              <div className="market-stat-card">
                <div className="market-stat-value">{stats.area_name}</div>
                <div className="market-stat-label">Market Area</div>
              </div>
              {baselineApprec != null && (
                <div
                  className="market-stat-card"
                  title={`Trailing 12-month home value trend for the metro (Zillow Research, as of ${baseline.as_of})`}
                >
                  <div className={`market-stat-value ${baselineApprec >= 0 ? 'trend-up' : 'trend-down'}`}>
                    {baselineApprec >= 0 ? '▲' : '▼'} {Math.abs(baselineApprec * 100).toFixed(1)}%
                  </div>
                  <div className="market-stat-label">Metro 12-mo Trend</div>
                </div>
              )}
              {baseline?.median_list_price != null && (
                <div
                  className="market-stat-card"
                  title={`Metro-wide median list price (Zillow Research, as of ${baseline.as_of})`}
                >
                  <div className="market-stat-value">{formatCurrency(baseline.median_list_price)}</div>
                  <div className="market-stat-label">Metro Median List</div>
                </div>
              )}
              {baseline?.sale_to_list_ratio != null && (
                <div
                  className="market-stat-card"
                  title={`Median sale price as a share of list price (Zillow Research, as of ${baseline.as_of}). Above 100% = homes sell over asking.`}
                >
                  <div className={`market-stat-value ${baseline.sale_to_list_ratio >= 1 ? 'trend-up' : 'trend-down'}`}>
                    {(baseline.sale_to_list_ratio * 100).toFixed(1)}%
                  </div>
                  <div className="market-stat-label">Sale-to-List</div>
                </div>
              )}
              {baseline?.pct_listings_price_cut != null && (
                <div
                  className="market-stat-card"
                  title={`Share of listings with a price cut (Zillow Research, as of ${baseline.as_of}). Higher = softer market.`}
                >
                  <div className="market-stat-value">
                    {(baseline.pct_listings_price_cut * 100).toFixed(0)}%
                  </div>
                  <div className="market-stat-label">Price Cuts</div>
                </div>
              )}
              {baseline?.median_days_to_pending != null && (
                <div
                  className="market-stat-card"
                  title={`Median days from listing to pending sale (Zillow Research, as of ${baseline.as_of}). Lower = hotter market.`}
                >
                  <div className="market-stat-value">
                    {Math.round(baseline.median_days_to_pending)}d
                  </div>
                  <div className="market-stat-label">Days to Pending</div>
                </div>
              )}
            </div>
          )}

          {/* Charts */}
          {deals.length > 0 && (
            <div className="charts-section">
              <PriceDistributionChart deals={deals} />
              <DealScoreChart deals={deals} />
              <ValueVsPriceChart deals={deals.slice(0, 12)} />
              <SqftVsPriceScatter deals={deals} />
            </div>
          )}

          {/* Data-source context */}
          {sourceNote && <div className="source-note">{sourceNote}</div>}

          {/* Sort & Results Header */}
          <div className="results-header">
            <div className="results-count">
              Showing <strong>{rangeStart}–{rangeEnd}</strong> of{' '}
              <strong>{results.total_results}</strong> properties ranked by deal quality
            </div>
            <div className="sort-controls">
              {[
                { key: 'deal_score', label: '🏆 Best Deals' },
                { key: 'cashflow_desc', label: '💵 Cashflow ↓' },
                { key: 'price_asc', label: '💰 Price ↑' },
                { key: 'price_desc', label: '💰 Price ↓' },
                { key: 'newest', label: '🆕 Newest' },
              ].map(s => (
                <button
                  key={s.key}
                  className={`sort-btn ${sortBy === s.key ? 'active' : ''}`}
                  onClick={() => handleSort(s.key)}
                  type="button"
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* Property Cards Grid */}
          <div className="deals-grid">
            {deals.map((deal, idx) => (
              <PropertyCard
                key={deal.property.id || idx}
                deal={deal}
                compareOn={compareIds.has(deal.property.id)}
                compareDisabled={compareFull}
                onToggleCompare={handleToggleCompare}
              />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="pagination-controls">
              <button
                type="button"
                className="pagination-btn"
                onClick={() => goToPage(page - 1)}
                disabled={page <= 1 || loading}
              >
                ← Prev
              </button>
              <span className="pagination-info">
                Page <strong>{page}</strong> of <strong>{totalPages}</strong>
              </span>
              <button
                type="button"
                className="pagination-btn"
                onClick={() => goToPage(page + 1)}
                disabled={page >= totalPages || loading}
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}

      {/* Empty State */}
      {!loading && !results && (
        <div className="empty-state">
          <div className="empty-state-icon">🏡</div>
          <h3>Find Your Perfect Home Deal</h3>
          <p>Set your specifications above and click "Find Best Deals" to analyze properties with our AI-powered valuation engine.</p>
        </div>
      )}

      {!loading && results && deals.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">🔍</div>
          <h3>No Properties Found</h3>
          <p>Try adjusting your search criteria to find more properties.</p>
        </div>
      )}
    </main>
  );
}
