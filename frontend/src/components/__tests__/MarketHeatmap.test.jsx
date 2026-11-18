import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import MarketHeatmap from '../MarketHeatmap';

const BODY = {
  generated_at: '2026-11-18T00:00:00Z',
  rate: { rate: 6.5, source: 'fred' },
  assumptions: { down_pct: 0.2, tax_rate: 0.011, insurance_rate: 0.0035 },
  rows: [
    {
      metro: 'Detroit, MI', state: 'MI', cities: ['Detroit'],
      typical_value: 90000, median_list_price: 95000, typical_rent: 1350,
      appreciation_1y: 0.041, reo_active: 9,
      monthly: {
        price_basis: 95000, payment: 479.31, tax: 87, insurance: 28,
        carry: 594, cashflow: 756, rent_coverage: 2.82,
      },
    },
    {
      metro: 'Washington, DC', state: 'MD', cities: ['Bethesda', 'Silver Spring'],
      typical_value: 620000, median_list_price: 642000, typical_rent: null,
      appreciation_1y: 0.019, reo_active: 0,
      monthly: {
        price_basis: 642000, payment: 3239.6, tax: 588, insurance: 187,
        carry: 4015, cashflow: null, rent_coverage: null,
      },
    },
  ],
};

function mockResponse(body) {
  vi.stubGlobal('fetch', vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(body) })));
}

describe('MarketHeatmap', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('renders nothing when the backend is unreachable or empty', async () => {
    vi.stubGlobal('fetch', vi.fn(() =>
      Promise.resolve({ ok: false, json: () => Promise.resolve({}) })));
    const { container } = render(<MarketHeatmap />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  it('ranks metros with cashflow colored, unknown rent dashed', async () => {
    mockResponse(BODY);
    render(<MarketHeatmap />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Investor heatmap/ }))
        .toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Investor heatmap/ }));

    const cells = document.querySelectorAll('.heat-table tbody td');
    expect(cells.length).toBeGreaterThan(0);
    const detroitCash = screen.getByText('$756');
    expect(detroitCash.className).toContain('heat-pos');
    // DC row: rent, cashflow, coverage all unknown -> dashed cells
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText('2.82×')).toBeTruthy();
    expect(screen.getByText('+4.1%')).toBeTruthy();
  });

  it('clicking a row searches that metro, preferring its namesake city', async () => {
    mockResponse(BODY);
    const onLoadSearch = vi.fn();
    render(<MarketHeatmap onLoadSearch={onLoadSearch} />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Investor heatmap/ }))
        .toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Investor heatmap/ }));

    fireEvent.click(screen.getByText('Washington, DC'));
    expect(onLoadSearch).toHaveBeenCalledWith(
      { city: 'Bethesda', state: 'MD' });
    fireEvent.click(screen.getByText('Detroit, MI'));
    expect(onLoadSearch).toHaveBeenCalledWith({ city: 'Detroit', state: 'MI' });
  });
});
