import { formatCurrency } from '../lib/format';

/**
 * Tiny inline SVG price-trend sparkline for REO listings — the sweep
 * records every price change, and this shows the negotiation story at
 * a glance (bank-owned inventory often walks down in steps). Renders
 * nothing when there isn't a trend to show (< 2 points). The default
 * hover title is the full ask ladder — callers only override for a
 * reason.
 */
export default function PriceSpark({ points = [], width = 84, height = 22,
                                     title = null }) {
  const ladder = (points || [])
    .map(p => formatCurrency(p.price)).join(' → ');
  if (!points || points.length < 2) return null;

  const prices = points.map(p => Number(p.price)).filter(n => !Number.isNaN(n));
  if (prices.length < 2) return null;

  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || 1; // flat line when every price is equal
  const stepX = width / (prices.length - 1);
  const y = price => 2 + (height - 4) * (1 - (price - min) / span);

  const path = prices
    .map((price, i) => `${i === 0 ? 'M' : 'L'}${(i * stepX).toFixed(1)},${y(price).toFixed(1)}`)
    .join(' ');
  const lastX = (prices.length - 1) * stepX;
  const lastY = y(prices[prices.length - 1]);

  const trend = prices[prices.length - 1] < prices[0] ? 'down'
    : prices[prices.length - 1] > prices[0] ? 'up' : 'flat';
  const overall = ((prices[prices.length - 1] - prices[0]) / prices[0] * 100).toFixed(1);

  return (
    <svg
      className={`price-spark price-spark-${trend}`}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Price trend ${trend} ${overall}% over ${points.length} recorded prices`}
    >
      <title>{title || `Asked ${ladder}`}</title>
      <path d={path} />
      <circle cx={lastX.toFixed(1)} cy={lastY.toFixed(1)} r="2" />
    </svg>
  );
}
