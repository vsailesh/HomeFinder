'use client';

import { useState, useCallback } from 'react';
import PropertyCard from './PropertyCard';

// Iframe embedding is blocked by major MLS sites (X-Frame-Options / CSP
// frame-ancestors), so direct URLs are opened in a new tab instead. Listings
// themselves are scraped server-side and rendered as native cards below.
const QUICK_LINKS = [
  { name: 'Zillow', url: 'https://www.zillow.com/', logo: '🏠' },
  { name: 'Realtor.com', url: 'https://www.realtor.com/', logo: '🏘️' },
  { name: 'Redfin', url: 'https://www.redfin.com/', logo: '🔴' },
  { name: 'Trulia', url: 'https://www.trulia.com/', logo: '🏡' },
  { name: 'MLS.com', url: 'https://www.mls.com/', logo: '🔑' },
];

export default function MLSBrowser() {
  const [search, setSearch] = useState({
    city: 'Baltimore',
    state: 'MD',
    zip_code: '',
    min_price: '',
    max_price: '',
    min_bedrooms: '',
  });
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [directUrl, setDirectUrl] = useState('');

  const runSearch = useCallback(async (e) => {
    if (e) e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const query = new URLSearchParams();
      Object.entries(search).forEach(([k, v]) => {
        if (v !== '' && v != null) query.set(k, String(v));
      });
      query.set('sort_by', 'deal_score');
      const res = await fetch(`/api/search?${query.toString()}`);
      if (!res.ok) throw new Error(`Search failed (${res.status})`);
      const data = await res.json();
      setResults(data);
      if (!data.deals?.length) setError('No listings found. Try a broader search.');
    } catch (err) {
      setError(err.message || 'Search failed. Is the backend running?');
      setResults(null);
    } finally {
      setLoading(false);
    }
  }, [search]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setSearch(prev => ({ ...prev, [name]: value }));
  };

  const openDirect = (e) => {
    e.preventDefault();
    let url = directUrl.trim();
    if (!url) return;
    if (!/^https?:\/\//.test(url)) url = 'https://' + url;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const deals = results?.deals || [];
  const stats = results?.market_stats;

  return (
    <div className="mls-browser">
      <div className="mls-browser-header">
        <h3>🏘️ MLS Listings</h3>
        <p>Search live listings — rendered as cards (no blocked iframes). Open any source listing directly.</p>
      </div>

      {/* Direct-URL launcher */}
      <form onSubmit={openDirect} className="direct-url-bar">
        <input
          type="text"
          value={directUrl}
          onChange={(e) => setDirectUrl(e.target.value)}
          placeholder="Paste a listing URL (zillow.com/...) to open it directly"
          className="direct-url-input"
        />
        <button type="submit" className="btn-go">Open ↗</button>
        <div className="quick-links">
          {QUICK_LINKS.map((s, i) => (
            <button
              key={i}
              type="button"
              className="quick-link-btn"
              onClick={() => window.open(s.url, '_blank', 'noopener,noreferrer')}
              title={`Open ${s.name} in a new tab`}
            >
              <span className="site-logo">{s.logo}</span>{s.name}
            </button>
          ))}
        </div>
      </form>

      {/* Listing search */}
      <form onSubmit={runSearch} className="mls-search-form">
        <div className="mls-search-grid">
          <div className="form-group">
            <label htmlFor="city">City</label>
            <input id="city" name="city" value={search.city} onChange={handleChange} placeholder="Baltimore" />
          </div>
          <div className="form-group">
            <label htmlFor="state">State</label>
            <input id="state" name="state" value={search.state} onChange={handleChange} placeholder="MD" maxLength={2} />
          </div>
          <div className="form-group">
            <label htmlFor="zip_code">ZIP</label>
            <input id="zip_code" name="zip_code" value={search.zip_code} onChange={handleChange} placeholder="21201" />
          </div>
          <div className="form-group">
            <label htmlFor="min_price">Min Price</label>
            <input id="min_price" name="min_price" type="number" value={search.min_price} onChange={handleChange} placeholder="0" step="10000" />
          </div>
          <div className="form-group">
            <label htmlFor="max_price">Max Price</label>
            <input id="max_price" name="max_price" type="number" value={search.max_price} onChange={handleChange} placeholder="1000000" step="10000" />
          </div>
          <div className="form-group">
            <label htmlFor="min_bedrooms">Min Beds</label>
            <input id="min_bedrooms" name="min_bedrooms" type="number" value={search.min_bedrooms} onChange={handleChange} placeholder="0" min="0" />
          </div>
        </div>
        <button type="submit" className="btn-search" disabled={loading}>
          {loading ? 'Searching…' : '🔍 Search Listings'}
        </button>
      </form>

      {stats && (
        <div className="mls-stats-bar">
          <span><strong>{results.total_results}</strong> listings</span>
          <span>Median <strong>${stats.median_price?.toLocaleString()}</strong></span>
          <span><strong>${stats.avg_price_per_sqft?.toFixed(0)}</strong>/sqft</span>
          <span><strong>{stats.median_days_on_market}</strong>d on market</span>
        </div>
      )}

      {loading && (
        <div className="loading-container">
          <div className="loader" />
          <div className="loading-text">Fetching listings…</div>
        </div>
      )}

      {error && !loading && <div className="mls-error">{error}</div>}

      <div className="mls-results-grid">
        {deals.map((deal, idx) => (
          <PropertyCard key={deal.property.id || idx} deal={deal} />
        ))}
      </div>

      {!loading && !results && !error && (
        <div className="mls-empty">
          <span className="mls-empty-icon">🔍</span>
          <p>Enter a location and search to browse listings.</p>
        </div>
      )}
    </div>
  );
}
