'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import PropertyCard from '../../../components/PropertyCard';
import PriceSpark from '../../../components/PriceSpark';
import { formatCurrency, formatSigned } from '../../../lib/format';

function relativeTime(iso) {
  if (!iso) return '—';
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return '—';
  const days = Math.floor(ms / 86400_000);
  if (days >= 1) return `${days}d ago`;
  const hours = Math.floor(ms / 3600_000);
  if (hours >= 1) return `${hours}h ago`;
  return `${Math.max(1, Math.round(ms / 60_000))}m ago`;
}

/**
 * Permalink page for a tracked REO listing — durable by id (the
 * tracker's SQLite history, not the in-memory registry). Shows the
 * tracker's record of the bank's asks, then the same scored deal
 * card the search results render. Listings that sold and vanished
 * from HomeSteps stay reachable here.
 */
export default function ListingPage() {
  const params = useParams();
  const [data, setData] = useState(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    if (!params?.id) return;
    let cancelled = false;
    fetch(`/api/reo/listing/${encodeURIComponent(params.id)}`)
      .then(res => (res.ok ? res.json() : null))
      .then(json => {
        if (cancelled) return;
        if (json) setData(json);
        else setMissing(true);
      })
      .catch(() => { if (!cancelled) setMissing(true); });
    return () => { cancelled = true; };
  }, [params?.id]);

  if (missing) {
    return (
      <main className="listing-page">
        <Link className="listing-back" href="/">← Home Finder</Link>
        <div className="listing-missing">
          <h1>Listing not found</h1>
          <p>No tracked REO listing with this id — it may predate the
            tracker or the link is wrong.</p>
        </div>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="listing-page">
        <Link className="listing-back" href="/">← Home Finder</Link>
        <p className="listing-loading">Loading listing…</p>
      </main>
    );
  }

  const l = data.listing;
  const ladder = (l.price_history || []).map(p => formatCurrency(p.price));

  return (
    <main className="listing-page">
      <Link className="listing-back" href="/">← Home Finder</Link>

      <section className="listing-meta">
        <h1>{l.address}, {l.city}, {l.state} {l.zip_code}</h1>
        <div className="listing-meta-row">
          <span className={`listing-status ${l.is_active ? 'on' : 'off'}`}>
            {l.is_active ? '● Active on HomeSteps' : '○ Gone from HomeSteps'}
          </span>
          <span className="listing-price">{formatCurrency(l.list_price)}</span>
          {l.prev_price != null && (
            <s className="listing-prev">{formatCurrency(l.prev_price)}</s>
          )}
          {l.price_change_pct != null && (
            <span className="listing-cut">
              {formatSigned(-l.price_change_pct)}%
            </span>
          )}
        </div>
        <div className="listing-meta-row listing-meta-dim">
          <span>First seen {relativeTime(l.first_seen)}</span>
          <span>Last swept {relativeTime(l.last_seen)}</span>
          <span>Swept under {l.metro || l.city}</span>
          {(l.price_history || []).length > 1 && (
            <PriceSpark
              points={l.price_history}
              title={`Asked ${ladder.join(' → ')}`}
            />
          )}
          {l.url && (
            <a href={l.url} target="_blank" rel="noopener noreferrer">
              HomeSteps listing ↗
            </a>
          )}
        </div>
        {(l.price_history || []).length > 1 && (
          <div className="listing-ladder">Ask ladder: {ladder.join(' → ')}</div>
        )}
      </section>

      {data.deal ? (
        <PropertyCard deal={data.deal} />
      ) : (
        <p className="listing-loading">
          Tracker record only — this listing couldn&apos;t be valuated
          (missing sqft/beds or unsupported type).
        </p>
      )}
    </main>
  );
}
