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

  it('drops values the backend would 422 on: fractional ints, negatives, bad enums', () => {
    window.history.replaceState(null, '',
      '/?min_bedrooms=2.5&min_rent_coverage=-1&property_type=multifamily'
      + '&sort_by=bogus&max_price=-500&max_days_on_market=1.5');
    expect(specsFromUrl()).toEqual({});
  });

  it('accepts valid enum values and integer bounds', () => {
    window.history.replaceState(null, '',
      '/?property_type=multi_family&sort_by=cashflow_desc&min_bedrooms=2'
      + '&min_rent_coverage=1.25');
    expect(specsFromUrl()).toEqual({
      property_type: 'multi_family', sort_by: 'cashflow_desc',
      min_bedrooms: 2, min_rent_coverage: 1.25,
    });
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
