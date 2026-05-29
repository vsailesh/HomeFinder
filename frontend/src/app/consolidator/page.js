'use client';

import { useState } from 'react';
import MLSBrowser from '../../components/MLSBrowser';
import MortgageCalculator from '../../components/MortgageCalculator';

export default function ConsolidatorPage() {
  const [viewMode, setViewMode] = useState('split'); // 'split', 'tabs', 'stacked'
  const [activeTab, setActiveTab] = useState('mls');

  return (
    <main className="consolidator-page">
      <header className="consolidator-header">
        <div className="header-content">
          <div className="logo-section">
            <div className="logo-icon">🏠</div>
            <div className="logo-text">
              <h1>Home Finder Consolidator</h1>
              <p>Browse Listings & Calculate Mortgages</p>
            </div>
          </div>
          <div className="view-mode-selector">
            <span className="view-mode-label">View:</span>
            <button
              type="button"
              className={`view-mode-btn ${viewMode === 'split' ? 'active' : ''}`}
              onClick={() => setViewMode('split')}
              title="Side by side view"
            >
              ⬛ Split
            </button>
            <button
              type="button"
              className={`view-mode-btn ${viewMode === 'tabs' ? 'active' : ''}`}
              onClick={() => setViewMode('tabs')}
              title="Tabbed view"
            >
              📑 Tabs
            </button>
            <button
              type="button"
              className={`view-mode-btn ${viewMode === 'stacked' ? 'active' : ''}`}
              onClick={() => setViewMode('stacked')}
              title="Stacked view"
            >
              📄 Stacked
            </button>
          </div>
        </div>
      </header>

      {viewMode === 'tabs' && (
        <div className="tab-navigation">
          <button
            type="button"
            className={`tab-btn ${activeTab === 'mls' ? 'active' : ''}`}
            onClick={() => setActiveTab('mls')}
          >
            🏘️ MLS Listings
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'calculator' ? 'active' : ''}`}
            onClick={() => setActiveTab('calculator')}
          >
            🧮 Mortgage Calculator
          </button>
        </div>
      )}

      <div className={`consolidator-content view-mode-${viewMode}`}>
        {(viewMode === 'tabs' ? activeTab === 'mls' : true) && (
          <div className="consolidator-section mls-section">
            <MLSBrowser />
          </div>
        )}

        {(viewMode === 'tabs' ? activeTab === 'calculator' : true) && (
          <div className="consolidator-section calculator-section">
            <MortgageCalculator />
          </div>
        )}
      </div>
    </main>
  );
}
