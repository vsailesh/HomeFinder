import { describe, expect, it } from 'vitest';
import {
  formatCurrency, formatFraction, formatPct, relativeTime,
} from './format';

describe('formatFraction (fractions, owns ×100)', () => {
  it('renders signed percents from fractions', () => {
    expect(formatFraction(0.041)).toBe('+4.1%');
    expect(formatFraction(-0.009)).toBe('-0.9%');
  });

  it('formatPct takes percent-numbers — the two never mix', () => {
    expect(formatPct(4.1)).toBe('+4.1%');
    expect(formatFraction(0.041)).toBe(formatPct(4.1));
  });

  it('null/undefined render an em dash, never NaN', () => {
    expect(formatFraction(null)).toBe('—');
    expect(formatFraction(undefined)).toBe('—');
  });
});

describe('relativeTime (shared "3d ago" helper)', () => {
  it('buckets by minutes, hours, then days', () => {
    const now = Date.now();
    expect(relativeTime(new Date(now - 12 * 60_000).toISOString()))
      .toBe('12m ago');
    expect(relativeTime(new Date(now - 5 * 3600_000).toISOString()))
      .toBe('5h ago');
    expect(relativeTime(new Date(now - 3 * 86400_000).toISOString()))
      .toBe('3d ago');
  });

  it('clamps sub-minute stamps to "1m ago", never "0m ago"', () => {
    expect(relativeTime(new Date().toISOString())).toBe('1m ago');
  });

  it('missing or unparseable input returns null (caller decides fallback)', () => {
    expect(relativeTime(null)).toBeNull();
    expect(relativeTime('')).toBeNull();
    expect(relativeTime('not-a-date')).toBeNull();
  });
});

describe('formatCurrency basics (regression guard)', () => {
  it('accounting-style negatives, commas, em dash for missing', () => {
    expect(formatCurrency(1234)).toBe('$1,234');
    expect(formatCurrency(-1234)).toBe('-$1,234');
    expect(formatCurrency(null)).toBe('—');
  });
});
