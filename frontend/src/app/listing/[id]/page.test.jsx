import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import ListingPage from './page';

vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'homesteps-x' }),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));
vi.mock('../../../components/PropertyCard', () => ({
  default: ({ deal }) => <div data-testid="deal-card">{deal.property.id}</div>,
}));
vi.mock('../../../components/PriceSpark', () => ({
  default: ({ points }) => (
    <div data-testid="spark">{points.length} pts</div>
  ),
}));

const BODY = {
  listing: {
    id: 'homesteps-x', address: '1 Main St', city: 'Chicago', state: 'IL',
    zip_code: '60601', list_price: 195000, prev_price: 210000,
    price_change_pct: -7.1, is_active: true,
    first_seen: '2026-11-01T00:00:00Z', last_seen: '2026-11-17T00:00:00Z',
    metro: 'Chicago', url: 'https://www.homesteps.com/x',
    price_history: [
      { price: 210000, seen_at: '2026-11-01T00:00:00Z' },
      { price: 195000, seen_at: '2026-11-10T00:00:00Z' },
    ],
  },
  deal: { property: { id: 'homesteps-x' } },
};

function mockResponse(ok, body) {
  vi.stubGlobal('fetch', vi.fn(() =>
    Promise.resolve({ ok, json: () => Promise.resolve(body) })));
}

describe('ListingPage', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('renders the tracker record, ask ladder, and the scored deal', async () => {
    mockResponse(true, BODY);
    render(<ListingPage />);
    await waitFor(() =>
      expect(screen.getByTestId('deal-card')).toBeInTheDocument());
    expect(screen.getByText(/1 Main St, Chicago, IL/)).toBeInTheDocument();
    expect(screen.getByText('● Active on HomeSteps')).toBeInTheDocument();
    expect(screen.getByText(/Ask ladder: \$210,000 → \$195,000/))
      .toBeInTheDocument();
    expect(screen.getByRole('link', { name: /HomeSteps listing/ })
      .getAttribute('href')).toBe('https://www.homesteps.com/x');
  });

  it('shows the gone-from-source state for inactive listings', async () => {
    mockResponse(true, {
      ...BODY, listing: { ...BODY.listing, is_active: false },
      deal: null,
    });
    render(<ListingPage />);
    await waitFor(() =>
      expect(screen.getByText('○ Gone from HomeSteps')).toBeInTheDocument());
    expect(screen.queryByTestId('deal-card')).toBeNull();
    expect(screen.getByText(/Tracker record only/)).toBeInTheDocument();
  });

  it('renders a not-found page only for genuine 404s', async () => {
    vi.stubGlobal('fetch', vi.fn(() =>
      Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) })));
    render(<ListingPage />);
    await waitFor(() =>
      expect(screen.getByText('Listing not found')).toBeInTheDocument());
  });

  it('a 500/network failure is an error state, not "not found"', async () => {
    vi.stubGlobal('fetch', vi.fn(() =>
      Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) })));
    render(<ListingPage />);
    await waitFor(() =>
      expect(screen.getByText(/Couldn't load this listing/))
        .toBeInTheDocument());
    expect(screen.queryByText('Listing not found')).toBeNull();
  });

  it('renders the price cut as a signed percent, not currency', async () => {
    mockResponse(true, BODY);
    render(<ListingPage />);
    await waitFor(() =>
      expect(screen.getByTestId('deal-card')).toBeInTheDocument());
    // price_change_pct -7.1 → "-7.1%" (was "+$7%" pre-fix)
    expect(screen.getByText('-7.1%')).toBeInTheDocument();
  });
});
