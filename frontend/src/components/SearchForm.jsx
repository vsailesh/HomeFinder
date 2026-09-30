'use client';

import { useState } from 'react';

const CITIES = [
  { name: 'Baltimore', state: 'MD', county: 'Baltimore City' },
  { name: 'Columbia', state: 'MD', county: 'Howard County' },
  { name: 'Bethesda', state: 'MD', county: 'Montgomery County' },
  { name: 'Silver Spring', state: 'MD', county: 'Montgomery County' },
  { name: 'Annapolis', state: 'MD', county: 'Anne Arundel County' },
  { name: 'Rockville', state: 'MD', county: 'Montgomery County' },
  { name: 'Frederick', state: 'MD', county: 'Frederick County' },
  { name: 'Bowie', state: 'MD', county: "Prince George's County" },
];

/** Strip empty/false values so they don't hit the query string. */
export function cleanParams(specs) {
  const params = {};
  Object.entries(specs).forEach(([key, val]) => {
    if (val !== '' && val !== false && val != null && val !== undefined) {
      params[key] = val;
    }
  });
  return params;
}

export const DEFAULT_SPECS = {
  city: '',
  state: 'MD',
  county: '',
  min_price: '',
  max_price: '',
  min_bedrooms: '',
  max_bedrooms: '',
  min_bathrooms: '',
  max_bathrooms: '',
  min_sqft: '',
  max_sqft: '',
  property_type: '',
  min_year_built: '',
  max_year_built: '',
  max_hoa: '',
  must_have_pool: false,
  must_have_basement: false,
  must_have_garage: false,
  max_days_on_market: '',
  sort_by: 'deal_score',
};

export default function SearchForm({ specs, onSpecsChange, onSearch, loading }) {
  const [expanded, setExpanded] = useState(true);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    onSpecsChange(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSearch(cleanParams(specs));
  };

  const handleReset = () => {
    onSpecsChange(DEFAULT_SPECS);
  };

  return (
    <form className="search-panel" onSubmit={handleSubmit} id="search-form">
      <div className="search-panel-header">
        <div className="search-panel-title">
          🔍 Search Specifications
        </div>
        <button
          type="button"
          className="search-panel-toggle"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? '▲ Collapse' : '▼ Expand'}
        </button>
      </div>

      {expanded && (
        <>
          <div className="search-grid">
            {/* Location */}
            <div className="form-group">
              <label htmlFor="city-select">City</label>
              <select id="city-select" name="city" value={specs.city} onChange={handleChange}>
                <option value="">All Cities</option>
                {CITIES.map(c => (
                  <option key={c.name} value={c.name}>{c.name}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="county-select">County</label>
              <select id="county-select" name="county" value={specs.county} onChange={handleChange}>
                <option value="">All Counties</option>
                {[...new Set(CITIES.map(c => c.county))].map(co => (
                  <option key={co} value={co}>{co}</option>
                ))}
              </select>
            </div>

            {/* Price */}
            <div className="form-group">
              <label htmlFor="min-price">Min Price</label>
              <input id="min-price" name="min_price" type="number"
                placeholder="$0" value={specs.min_price} onChange={handleChange} />
            </div>
            <div className="form-group">
              <label htmlFor="max-price">Max Price</label>
              <input id="max-price" name="max_price" type="number"
                placeholder="$1,000,000" value={specs.max_price} onChange={handleChange} />
            </div>

            {/* Beds / Baths */}
            <div className="form-group">
              <label htmlFor="min-beds">Min Beds</label>
              <select id="min-beds" name="min_bedrooms" value={specs.min_bedrooms} onChange={handleChange}>
                <option value="">Any</option>
                {[1,2,3,4,5,6].map(n => <option key={n} value={n}>{n}+</option>)}
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="max-beds">Max Beds</label>
              <select id="max-beds" name="max_bedrooms" value={specs.max_bedrooms} onChange={handleChange}>
                <option value="">Any</option>
                {[2,3,4,5,6].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="min-baths">Min Baths</label>
              <select id="min-baths" name="min_bathrooms" value={specs.min_bathrooms} onChange={handleChange}>
                <option value="">Any</option>
                {[1,1.5,2,2.5,3,3.5,4].map(n => <option key={n} value={n}>{n}+</option>)}
              </select>
            </div>

            {/* Size */}
            <div className="form-group">
              <label htmlFor="min-sqft">Min Sqft</label>
              <input id="min-sqft" name="min_sqft" type="number"
                placeholder="Any" value={specs.min_sqft} onChange={handleChange} />
            </div>
            <div className="form-group">
              <label htmlFor="max-sqft">Max Sqft</label>
              <input id="max-sqft" name="max_sqft" type="number"
                placeholder="Any" value={specs.max_sqft} onChange={handleChange} />
            </div>

            {/* Type */}
            <div className="form-group">
              <label htmlFor="prop-type">Property Type</label>
              <select id="prop-type" name="property_type" value={specs.property_type} onChange={handleChange}>
                <option value="">All Types</option>
                <option value="single_family">Single Family</option>
                <option value="condo">Condo</option>
                <option value="townhouse">Townhouse</option>
                <option value="multi_family">Multi Family</option>
              </select>
            </div>

            {/* Year Built */}
            <div className="form-group">
              <label htmlFor="min-year">Min Year Built</label>
              <input id="min-year" name="min_year_built" type="number"
                placeholder="Any" value={specs.min_year_built} onChange={handleChange} />
            </div>
            <div className="form-group">
              <label htmlFor="max-year">Max Year Built</label>
              <input id="max-year" name="max_year_built" type="number"
                placeholder="Any" value={specs.max_year_built} onChange={handleChange} />
            </div>

            {/* HOA & DOM */}
            <div className="form-group">
              <label htmlFor="max-hoa">Max HOA ($/mo)</label>
              <input id="max-hoa" name="max_hoa" type="number"
                placeholder="Any" value={specs.max_hoa} onChange={handleChange} />
            </div>
            <div className="form-group">
              <label htmlFor="max-dom">Max Days on Market</label>
              <input id="max-dom" name="max_days_on_market" type="number"
                placeholder="Any" value={specs.max_days_on_market} onChange={handleChange} />
            </div>

            {/* Checkboxes */}
            <div className="checkbox-row">
              <label className="checkbox-label">
                <input type="checkbox" name="must_have_pool"
                  checked={specs.must_have_pool} onChange={handleChange} />
                🏊 Pool Required
              </label>
              <label className="checkbox-label">
                <input type="checkbox" name="must_have_basement"
                  checked={specs.must_have_basement} onChange={handleChange} />
                🏠 Basement Required
              </label>
              <label className="checkbox-label">
                <input type="checkbox" name="must_have_garage"
                  checked={specs.must_have_garage} onChange={handleChange} />
                🚗 Garage Required
              </label>
            </div>
          </div>

          <div className="search-actions">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading}
              id="search-btn"
            >
              {loading ? '⏳ Analyzing...' : '🚀 Find Best Deals'}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleReset}
              id="reset-btn"
            >
              ↩ Reset
            </button>
          </div>
        </>
      )}
    </form>
  );
}
