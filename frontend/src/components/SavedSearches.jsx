'use client';

import { useEffect, useState } from 'react';

const STORAGE_KEY = 'home-finder:saved-searches';
const MAX_SAVED = 12;

/**
 * Saved searches, persisted to localStorage (per-browser — no account
 * system yet). Each entry stores the full search-criteria object plus a
 * name, so loading one repopulates the form and re-runs the search.
 */
export default function SavedSearches({ currentParams, onLoad }) {
  const [saved, setSaved] = useState([]);
  const [name, setName] = useState('');
  const [nameTaken, setNameTaken] = useState(false);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) setSaved(JSON.parse(raw));
    } catch {
      // Corrupt storage — start fresh rather than crash.
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  const persist = (next) => {
    setSaved(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // Storage full/blocked — keep in-memory copy only.
    }
  };

  const canSave = Object.keys(currentParams || {}).length > 1; // more than just sort_by

  const handleSave = (e) => {
    e.preventDefault();
    const label = name.trim();
    if (!label || !canSave) return;

    if (saved.some(s => s.name === label)) {
      setNameTaken(true);
      return;
    }
    setNameTaken(false);

    const entry = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name: label,
      params: currentParams,
      saved_at: new Date().toISOString(),
    };
    persist([entry, ...saved].slice(0, MAX_SAVED));
    setName('');
  };

  const handleDelete = (id) => {
    persist(saved.filter(s => s.id !== id));
  };

  return (
    <div className="saved-searches">
      <div className="saved-searches-header">📌 Saved Searches</div>

      <form className="saved-search-form" onSubmit={handleSave}>
        <input
          type="text"
          className="saved-search-name-input"
          placeholder={canSave ? 'Name this search…' : 'Run a search first'}
          value={name}
          onChange={(e) => { setName(e.target.value); setNameTaken(false); }}
          disabled={!canSave}
          aria-label="Saved search name"
        />
        <button
          type="submit"
          className="btn btn-secondary saved-search-save-btn"
          disabled={!canSave || !name.trim()}
        >
          Save
        </button>
      </form>
      {nameTaken && (
        <div className="saved-search-error">That name is already saved.</div>
      )}

      {saved.length === 0 ? (
        <div className="saved-search-empty">No saved searches yet.</div>
      ) : (
        <ul className="saved-search-list">
          {saved.map(s => (
            <li key={s.id} className="saved-search-item">
              <button
                type="button"
                className="saved-search-load"
                onClick={() => onLoad(s.params)}
                title={summarize(s.params)}
              >
                <span className="saved-search-item-name">{s.name}</span>
                <span className="saved-search-item-summary">{summarize(s.params)}</span>
              </button>
              <button
                type="button"
                className="saved-search-delete"
                onClick={() => handleDelete(s.id)}
                aria-label={`Delete saved search "${s.name}"`}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function summarize(params = {}) {
  const bits = [];
  if (params.city) bits.push(`${params.city}, ${params.state || ''}`.trim());
  else if (params.county) bits.push(params.county);
  else if (params.state) bits.push(params.state);
  if (params.max_price) bits.push(`≤ $${Number(params.max_price).toLocaleString()}`);
  if (params.min_bedrooms) bits.push(`${params.min_bedrooms}+ bd`);
  return bits.length ? bits.join(' · ') : 'All criteria';
}
