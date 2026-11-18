/**
 * Shared display formatters — single source of truth so currency and
 * percentage rendering can't drift between components (the compare
 * tray, property cards, tracker, calculator, and page header all
 * render money).
 *
 * Negative currency renders as "-$1,234" (standard accounting style).
 */

export function formatCurrency(val) {
  if (val == null) return '—';
  const n = Number(val);
  if (Number.isNaN(n)) return '—';
  const abs = Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
  return n < 0 ? `-$${abs}` : `$${abs}`;
}

/** Signed currency delta, e.g. "+$1,200" / "-$800". */
export function formatSigned(val, suffix = '') {
  if (val == null) return '—';
  const n = Number(val);
  if (Number.isNaN(n)) return '—';
  return `${n >= 0 ? '+' : ''}${formatCurrency(n)}${suffix}`;
}

/** Signed percentage delta, e.g. "+3.2%" / "-1.4%". */
export function formatPct(val, digits = 1) {
  if (val == null) return '—';
  return `${Number(val) >= 0 ? '+' : ''}${Number(val).toFixed(digits)}%`;
}

/** Plain (unsigned) percentage for rates, e.g. "7.11%". */
export function formatPercent(val, digits = 2) {
  return val == null ? '—' : `${Number(val).toFixed(digits)}%`;
}
