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

/**
 * Signed percentage from a FRACTION, e.g. 0.041 → "+4.1%". Owns the
 * ×100 so callers can't double- or half-multiply — Zillow Research
 * series (appreciation, price-cut share) are all fractions, while
 * formatPct takes percent-numbers (price_change_pct etc.).
 */
export function formatFraction(val, digits = 1) {
  return val == null ? '—' : formatPct(val * 100, digits);
}

/** Compact "3d ago" / "5h ago" / "12m ago" for ISO timestamps. */
export function relativeTime(iso) {
  if (!iso) return null;
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return null;
  // Clamp at 1m: sub-minute (or clock-skewed-future) stamps shouldn't
  // render "0m ago".
  const mins = Math.max(1, Math.round(ms / 60000));
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}
