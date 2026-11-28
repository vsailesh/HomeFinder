import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import PriceSpark from '../PriceSpark';

const PTS = [
  { price: 199000, seen_at: '2026-11-01T00:00:00Z' },
  { price: 189000, seen_at: '2026-11-08T00:00:00Z' },
  { price: 179000, seen_at: '2026-11-15T00:00:00Z' },
];

describe('PriceSpark', () => {
  it('renders nothing without a trend (fewer than 2 points)', () => {
    const { container } = render(<PriceSpark points={PTS.slice(0, 1)} />);
    expect(container.firstChild).toBeNull();
    const { container: empty } = render(<PriceSpark points={[]} />);
    expect(empty.firstChild).toBeNull();
  });

  it('draws a path + end dot for a series, tagged by trend', () => {
    const { container } = render(<PriceSpark points={PTS} />);
    const svg = container.querySelector('svg');
    expect(svg).toBeTruthy();
    expect(svg.getAttribute('class')).toContain('price-spark-down');
    expect(svg.querySelector('path')).toBeTruthy();
    expect(svg.querySelector('circle')).toBeTruthy();
    expect(svg.getAttribute('aria-label')).toContain('down');
  });

  it('tags rising and flat trends distinctly', () => {
    const up = render(<PriceSpark points={[...PTS].reverse()} />).container;
    expect(up.querySelector('svg').getAttribute('class'))
      .toContain('price-spark-up');
    const flat = render(
      <PriceSpark points={[{ price: 5 }, { price: 5 }, { price: 5 }]} />
    ).container;
    expect(flat.querySelector('svg').getAttribute('class'))
      .toContain('price-spark-flat');
    expect(flat.querySelector('path').getAttribute('d')).toContain(','); // straight line
  });

  it('self-titles with the full ask ladder when no title is given', () => {
    const { container } = render(<PriceSpark points={PTS} />);
    expect(container.querySelector('title').textContent)
      .toBe('Asked $199,000 → $189,000 → $179,000');
  });

  it('an explicit title overrides the ask-ladder default', () => {
    const { container } = render(
      <PriceSpark points={PTS} title="custom hover text" />);
    expect(container.querySelector('title').textContent)
      .toBe('custom hover text');
  });
});
