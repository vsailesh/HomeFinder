import { afterEach, describe, expect, it } from 'vitest';
import { specsFromUrl, toQuery } from './page';

describe('shareable-search URL helpers', () => {
  afterEach(() =>
    window.history.replaceState(null, '', '/'));

  it('parses a shared URL into typed spec values', () => {
    window.history.replaceState(null, '',
      '/?city=Detroit&state=MI&max_price=100000&min_bedrooms=3'
      + '&must_have_garage=true&sort_by=cashflow_desc');
    expect(specsFromUrl()).toEqual({
      city: 'Detroit', state: 'MI', max_price: 100000,
      min_bedrooms: 3, must_have_garage: true,
      sort_by: 'cashflow_desc',
    });
  });

  it('ignores unknown keys, junk numbers, and empty values', () => {
    window.history.replaceState(null, '',
      '/?city=&page=3&min_price=abc&evil=<script>&must_have_pool=1');
    expect(specsFromUrl()).toEqual({});
  });

  it('toQuery drops empty/false/null and stringifies the rest', () => {
    const q = toQuery({
      city: 'Chicago', state: '', min_price: null, must_have_pool: false,
      max_price: 200000, min_bedrooms: 2,
    });
    expect(q.toString()).toBe(
      'city=Chicago&max_price=200000&min_bedrooms=2');
  });
});
