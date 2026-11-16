import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ReoTracker, { matchesSavedSearch } from '../ReoTracker';

const LISTING = {
  id: 'homesteps-x', address: '1 Main St', city: 'Chicago', state: 'IL',
  zip_code: '60601', list_price: 195000, bedrooms: 3, bathrooms: 2,
  sqft: 1400, is_new: true, price_cut: false,
  first_seen: new Date(Date.now() - 3600_000).toISOString(),
  last_price_change: null, url: 'https://example.com/x',
};

const INVENTORY = (listings, summaryOverrides = {}) => ({
  generated_at: new Date().toISOString(),
  window_days: 7,
  last_sweep: { status: 'ok', finished_at: new Date().toISOString() },
  summary: {
    active: listings.length, new: listings.filter(l => l.is_new).length,
    price_cuts: 0, metros_with_inventory: 1, ...summaryOverrides,
  },
  listings,
});

function mockInventoryResponse(body) {
  vi.stubGlobal('fetch', vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(body) })));
}

describe('matchesSavedSearch (pure)', () => {
  const L = LISTING;

  it('matches on state and price band', () => {
    expect(matchesSavedSearch(L, { state: 'IL', max_price: 200000 })).toBe(true);
    expect(matchesSavedSearch(L, { state: 'IL', max_price: 150000 })).toBe(false);
  });

  it('state is the location gate; city matches equal-or-contains either way', () => {
    expect(matchesSavedSearch(L, { city: 'Chicago' })).toBe(true);
    expect(matchesSavedSearch(L, { city: 'chicago' })).toBe(true);
    expect(matchesSavedSearch(L, { city: 'Detr' })).toBe(false);
    const suburb = { ...L, city: 'Gwynn Oak' };
    expect(matchesSavedSearch(suburb, { city: 'Baltimore', state: 'MD' }))
      .toBe(false); // state mismatch fails even if names overlapped
  });

  it('a suburb listing matches its metro search via the metro tag', () => {
    // Suburb city strings share no substring with the metro name —
    // only the swept-metro tag connects them.
    const suburb = { ...L, city: 'Gwynn Oak', state: 'MD', metro: 'Baltimore' };
    expect(matchesSavedSearch(suburb, { city: 'Baltimore', state: 'MD' }))
      .toBe(true);
    expect(matchesSavedSearch(suburb, { city: 'Chicago', state: 'IL' }))
      .toBe(false); // metro tag must match, not just exist
  });

  it('beds/baths/sqft filters', () => {
    expect(matchesSavedSearch(L, { min_bedrooms: 3 })).toBe(true);
    expect(matchesSavedSearch(L, { min_bedrooms: 4 })).toBe(false);
    expect(matchesSavedSearch(L, { min_sqft: 1500 })).toBe(false);
    // unknown sqft never violates a max filter
    expect(matchesSavedSearch({ ...L, sqft: null }, { max_sqft: 1000 }))
      .toBe(true);
  });

  it('empty params match everything', () => {
    expect(matchesSavedSearch(L, {})).toBe(true);
  });
});

describe('ReoTracker panel', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it('renders nothing when the tracker has no active inventory', async () => {
    mockInventoryResponse(INVENTORY([]));
    const { container } = render(<ReoTracker />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  it('shows the saved-search match count and re-runs the search on click', async () => {
    window.localStorage.setItem('home-finder:saved-searches', JSON.stringify([
      { id: 's1', name: 'Chicago under 200k',
        params: { city: 'Chicago', state: 'IL', max_price: 200000 },
        saved_at: new Date().toISOString() },
      { id: 's2', name: 'Detroit cheap',
        params: { city: 'Detroit', state: 'MI' },
        saved_at: new Date().toISOString() },
    ]));
    mockInventoryResponse(INVENTORY([LISTING]));
    const onLoadSearch = vi.fn();
    render(<ReoTracker onLoadSearch={onLoadSearch} />);

    await waitFor(() =>
      expect(screen.getByText(/42|1 active/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Freddie Mac REO tracker/ }));
    expect(screen.getByText('Chicago under 200k')).toBeInTheDocument();
    expect(screen.queryByText('Detroit cheap')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Chicago under 200k'));
    expect(onLoadSearch).toHaveBeenCalledWith(
      { city: 'Chicago', state: 'IL', max_price: 200000 });
  });

  it('counts listings new since the previous visit', async () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 86400_000).toISOString();
    window.localStorage.setItem('home-finder:last-visit', twoDaysAgo);
    mockInventoryResponse(INVENTORY([LISTING]));
    render(<ReoTracker />);

    await waitFor(() =>
      expect(screen.getByText(/🔔 1 since your last visit/)).toBeInTheDocument());
    // visit stamp refreshed for next time
    const stamp = window.localStorage.getItem('home-finder:last-visit');
    expect(new Date(stamp).getTime()).toBeGreaterThan(
      new Date(twoDaysAgo).getTime());
  });

  it('flags arrivals older than the 7-day is_new window after a long absence', async () => {
    // Back after 3 weeks: the listing arrived 11 days ago — is_new is
    // false, but it postdates the last visit, so it still counts.
    const listing = {
      ...LISTING,
      is_new: false,
      first_seen: new Date(Date.now() - 11 * 86400_000).toISOString(),
    };
    const threeWeeksAgo = new Date(Date.now() - 21 * 86400_000).toISOString();
    window.localStorage.setItem('home-finder:last-visit', threeWeeksAgo);
    mockInventoryResponse(INVENTORY([listing]));
    render(<ReoTracker />);

    await waitFor(() =>
      expect(screen.getByText(/🔔 1 since your last visit/)).toBeInTheDocument());
  });

  it('no since-visit callout on first-ever visit', async () => {
    mockInventoryResponse(INVENTORY([LISTING]));
    render(<ReoTracker />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /REO tracker/ }))
        .toBeInTheDocument());
    expect(screen.queryByText(/since your last visit/)).not.toBeInTheDocument();
  });
});
