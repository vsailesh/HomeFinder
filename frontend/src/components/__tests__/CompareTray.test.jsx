import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import CompareTray from '../CompareTray';

const makeDeal = (id, address, overrides = {}) => ({
  property: {
    id, address, city: 'Chicago', state: 'IL', list_price: 199000,
    sqft: 1100, url: 'https://example.com/' + id,
    source: 'homesteps-freddie-mac', ...overrides.property,
  },
  deal_score: 72, deal_grade: 'B+',
  valuation: {
    estimated_value: 205000, price_difference_pct: 3.0,
    ...overrides.valuation,
  },
  monthly_payment_estimate: 1075,
  monthly_carry_estimate: 1500,
  net_monthly_cashflow: 320,
  estimated_rent: 1820,
  estimated_roi_5yr: 22.5,
  ...overrides.top,
});

describe('CompareTray', () => {
  it('shows the empty hint when no deals are shortlisted', () => {
    render(<CompareTray deals={[]} onRemove={() => {}} onClear={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Compare \(0/ }));
    expect(screen.getByText(/No deals shortlisted yet/i)).toBeInTheDocument();
  });

  it('renders one column per deal with core metrics', () => {
    const deals = [makeDeal('a', '1 Main St'), makeDeal('b', '2 Oak St')];
    render(<CompareTray deals={deals} onRemove={() => {}} onClear={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Compare \(2/ }));
    expect(screen.getByText('1 Main St')).toBeInTheDocument();
    expect(screen.getByText('2 Oak St')).toBeInTheDocument();
    expect(screen.getByText('Net cashflow')).toBeInTheDocument();
    expect(screen.getByText('Rent / P&I')).toBeInTheDocument();
    // REO badge on each column header
    expect(screen.getAllByText('🏦 REO')).toHaveLength(2);
  });

  it('remove button calls onRemove with the deal id', () => {
    const onRemove = vi.fn();
    render(<CompareTray deals={[makeDeal('a', '1 Main St')]}
      onRemove={onRemove} onClear={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Compare \(1/ }));
    fireEvent.click(screen.getByLabelText(/Remove 1 Main St/i));
    expect(onRemove).toHaveBeenCalledWith('a');
  });

  it('clear link calls onClear', () => {
    const onClear = vi.fn();
    render(<CompareTray deals={[makeDeal('a', '1 Main St')]}
      onRemove={() => {}} onClear={onClear} />);
    fireEvent.click(screen.getByRole('button', { name: /Compare \(1/ }));
    fireEvent.click(screen.getByText('clear'));
    expect(onClear).toHaveBeenCalled();
  });
});
