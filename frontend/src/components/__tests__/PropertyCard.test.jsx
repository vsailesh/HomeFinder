import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import PropertyCard from '../PropertyCard';

const makeDeal = (overrides = {}) => ({
  property: {
    id: 'p1', address: '742 Evergreen Terrace', city: 'Chicago',
    state: 'IL', zip_code: '60601', list_price: 199000, bedrooms: 3,
    bathrooms: 2, sqft: 1400, sqft_estimated: false, year_built: 1955,
    url: 'https://example.com/p1', source: 'mock-generator',
    condition: 'good', days_on_market: 12,
  },
  valuation: {
    estimated_value: 205000, price_difference: 6000,
    price_difference_pct: 3.0, confidence_score: 0.8, variables: [],
    base_land_value: 40000, structure_value: 150000,
    feature_adjustments: 5000, location_premium: 8000,
    market_adjustment: 2000, price_per_sqft: 142, market_price_per_sqft: 150,
  },
  deal_score: 74, deal_grade: 'B+',
  reasons: ['Priced under estimated value'],
  risk_factors: ['Older roof'],
  monthly_payment_estimate: 1075, estimated_roi_5yr: 21.4,
  estimated_rent: 1820, estimated_monthly_cashflow: 745,
  monthly_carry_estimate: 1500, net_monthly_cashflow: 320,
  ...overrides,
});

describe('PropertyCard', () => {
  it('renders the address, score, and demo badge for mock data', () => {
    render(<PropertyCard deal={makeDeal()} />);
    expect(screen.getByText('742 Evergreen Terrace')).toBeInTheDocument();
    expect(screen.getByText('74')).toBeInTheDocument();
    expect(screen.getByText(/Demo data/i)).toBeInTheDocument();
  });

  it('compare chip toggles via onToggleCompare with the deal', () => {
    const onToggleCompare = vi.fn();
    const deal = makeDeal();
    render(<PropertyCard deal={deal} compareOn={false}
      compareDisabled={false} onToggleCompare={onToggleCompare} />);
    fireEvent.click(screen.getByText('± Compare'));
    expect(onToggleCompare).toHaveBeenCalledWith(deal);
  });

  it('active compare chip shows the selected state', () => {
    render(<PropertyCard deal={makeDeal()} compareOn
      compareDisabled={false} onToggleCompare={() => {}} />);
    expect(screen.getByText('✓ Comparing')).toBeInTheDocument();
  });

  describe('projection toggle', () => {
    beforeEach(() => {
      vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          assumptions: {
            rate_pct: 7.11, appreciation: 0.036,
            appreciation_source: 'zillow-research-metro',
            rent_growth: 0.03, selling_cost_pct: 0.06,
          },
          rows: [{ year: 0, property_value: 199000, equity: 39800,
                   cum_cf: 0, net_position: 28000, rent_mo: 1820,
                   carry_mo: 1500, net_cf_mo: 320 }],
        }),
      })));
    });

    afterEach(() => vi.unstubAllGlobals());

    it('lazy-fetches the projection on first expand and renders the chart', async () => {
      render(<PropertyCard deal={makeDeal()} />);
      fireEvent.click(screen.getByText(/10-Year Hold Projection/i));
      await waitFor(() =>
        expect(screen.getByText(/metro trend/)).toBeInTheDocument());
      expect(fetch).toHaveBeenCalledTimes(1);
      const [url, init] = fetch.mock.calls[0];
      expect(url).toBe('/api/property/projection');
      expect(init.method).toBe('POST');
      expect(JSON.parse(init.body).list_price).toBe(199000);
    });

    it('does not fetch while collapsed', () => {
      render(<PropertyCard deal={makeDeal()} />);
      expect(fetch).not.toHaveBeenCalled();
    });
  });
});
