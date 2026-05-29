'use client';

import { useState, useCallback } from 'react';
import SearchForm from '../components/SearchForm';
import PropertyCard from '../components/PropertyCard';
import MortgageCalculator from '../components/MortgageCalculator';
import { PriceDistributionChart, DealScoreChart, ValueVsPriceChart, SqftVsPriceScatter } from '../components/Charts';

function formatCurrency(val) {
  if (val == null) return '—';
  return '$' + Number(val).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

export default function HomePage() {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sortBy, setSortBy] = useState('deal_score');

  const handleSearch = useCallback(async (params) => {
    setLoading(true);
    try {
      const query = new URLSearchParams();
      Object.entries(params).forEach(([key, val]) => {
        if (val !== '' && val !== false && val != null) {
          query.set(key, String(val));
        }
      });
      const res = await fetch(`/api/search?${query.toString()}`);
      const data = await res.json();
      setResults(data);
      setSortBy(params.sort_by || 'deal_score');
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSort = useCallback((newSort) => {
    if (!results) return;
    setSortBy(newSort);
    const sorted = [...results.deals];
    if (newSort === 'deal_score') {
      sorted.sort((a, b) => b.deal_score - a.deal_score);
    } else if (newSort === 'price_asc') {
      sorted.sort((a, b) => a.property.list_price - b.property.list_price);
    } else if (newSort === 'price_desc') {
      sorted.sort((a, b) => b.property.list_price - a.property.list_price);
    } else if (newSort === 'newest') {
      sorted.sort((a, b) => (a.property.days_on_market || 999) - (b.property.days_on_market || 999));
    }
    setResults({ ...results, deals: sorted });
  }, [results]);

  const stats = results?.market_stats;
  const deals = results?.deals || [];

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
      <SearchForm onSearch={handleSearch} loading={loading} />

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
                <div className={`market-stat-trend ${stats.price_trend_30d >= 0 ? 'trend-up' : 'trend-down'}`}>
                  {stats.price_trend_30d >= 0 ? '▲' : '▼'} {Math.abs(stats.price_trend_30d)}% (30d)
                </div>
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
                <div className={`market-stat-trend ${stats.inventory_change_30d >= 0 ? 'trend-up' : 'trend-down'}`}>
                  {stats.inventory_change_30d >= 0 ? '▲' : '▼'} {Math.abs(stats.inventory_change_30d)}% (30d)
                </div>
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
              Showing <strong>{deals.length}</strong> properties ranked by deal quality
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
