'use client';

import { useState, useCallback } from 'react';
import SearchForm, { DEFAULT_SPECS, cleanParams } from '../components/SearchForm';
import SavedSearches from '../components/SavedSearches';
import PropertyCard from '../components/PropertyCard';
import MortgageCalculator from '../components/MortgageCalculator';
import { PriceDistributionChart, DealScoreChart, ValueVsPriceChart, SqftVsPriceScatter } from '../components/Charts';

const PAGE_SIZE = 12;

function formatCurrency(val) {
  if (val == null) return '—';
  return '$' + Number(val).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

export default function HomePage() {
  const [specs, setSpecs] = useState(DEFAULT_SPECS);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastParams, setLastParams] = useState(null);
  const [page, setPage] = useState(1);

  const runSearch = useCallback(async (params, pageNum = 1) => {
    setLoading(true);
    try {
      const query = new URLSearchParams();
      Object.entries(params).forEach(([key, val]) => {
        if (val !== '' && val !== false && val != null) {
          query.set(key, String(val));
        }
      });
      query.set('page', String(pageNum));
      query.set('page_size', String(PAGE_SIZE));
      const res = await fetch(`/api/search?${query.toString()}`);
      const data = await res.json();
      setResults(data);
      setLastParams(params);
      setPage(pageNum);
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSearch = useCallback((params) => {
    runSearch(params, 1);
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
  const deals = results?.deals || [];
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

      {/* Loading */}
      {loading && (
        <div className="loading-container">
          <div className="loader"></div>
          <div className="loading-text">Analyzing properties and calculating fair market values...</div>
        </div>
      )}

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

          {/* Sort & Results Header */}
          <div className="results-header">
            <div className="results-count">
              Showing <strong>{rangeStart}–{rangeEnd}</strong> of{' '}
              <strong>{results.total_results}</strong> properties ranked by deal quality
            </div>
            <div className="sort-controls">
              {[
                { key: 'deal_score', label: '🏆 Best Deals' },
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
              <PropertyCard key={deal.property.id || idx} deal={deal} />
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
