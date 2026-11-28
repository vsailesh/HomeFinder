'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import PropertyCard from '../../../components/PropertyCard';
import PriceSpark from '../../../components/PriceSpark';
import { formatCurrency, formatPct, relativeTime } from '../../../lib/format';

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
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!params?.id) return;
    let cancelled = false;
    setMissing(false);
    setFailed(false);
    setData(null);
    fetch(`/api/reo/listing/${encodeURIComponent(params.id)}`)
      .then(res => {
        // 404 = genuinely unknown id. Anything else (a 500 from a
        // transient DB error, a blip mid-deploy) is OUR failure, not
        // the link's — a bookmarked listing must not read as gone.
        if (res.status === 404) return { __missing: true };
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(json => {
        if (cancelled) return;
        if (json?.__missing) setMissing(true);
        else setData(json);
      })
      .catch(() => { if (!cancelled) setFailed(true); });
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

  if (failed) {
    return (
      <main className="listing-page">
        <Link className="listing-back" href="/">← Home Finder</Link>
        <div className="listing-missing">
          <h1>Couldn&apos;t load this listing</h1>
          <p>The backend is unreachable or erroring — try refreshing.
            The listing itself may be fine.</p>
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
              {formatPct(l.price_change_pct)}
            </span>
          )}
        </div>
        <div className="listing-meta-row listing-meta-dim">
          <span>First seen {relativeTime(l.first_seen) || '—'}</span>
          <span>Last swept {relativeTime(l.last_seen) || '—'}</span>
          <span>Swept under {l.metro || l.city}</span>
          {(l.price_history || []).length > 1 && (
            <PriceSpark points={l.price_history} />
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
