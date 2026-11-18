# Home Finder

Real estate deal analyzer. Searches listings, values each property variable-by-variable, scores the deal (0–100 + letter grade), and quotes mortgages against the live market rate.

- **Backend** — Python 3.12 / FastAPI (`backend/`)
- **Frontend** — Next.js / React (`frontend/`)
- **Live data** — Zillow listings via RapidAPI (`zillow-com-live-data-scraper-api`); Freddie Mac REO listings via HomeSteps (no key); mortgage base rate via FRED (`MORTGAGE30US`, no key); per-metro market baselines from Zillow Research public CSVs (no key): home values & trailing-12mo appreciation, median list, rents (metro + ZIP), and market heat (sale-to-list ratio, price-cut share, days-to-pending)

Listing sources cascade in order: RapidAPI Zillow (full inventory, needs quota) → Freddie Mac HomeSteps REO (real bank-owned listings, no key, thin inventory; cards badged "🏦 Freddie Mac REO", sqft estimated from room count and flagged) → mock generator (labeled "⚠️ Demo data"). Mortgage rates and metro trends are always live.

20 cities across 11 states (MD core + Charlotte, Raleigh, Tampa, Jacksonville, Atlanta, Chicago, Cleveland, Detroit, Kansas City, Philadelphia, Phoenix, Indianapolis), each joined to its Zillow Research metro baseline.

**Investor analysis** — every scored deal carries: estimated rent (Zillow ZORI, ZIP-level when published, metro fallback), P&I payment, full monthly carry (P&I + property tax + insurance + HOA), and cashflow net of carry. Deal scoring factors rental coverage; metro heat (price cuts, pace, sale-to-list) adds negotiation-leverage reasons/risks. Search filters include `min_rent_coverage` (rent ÷ P&I) and `sort_by=cashflow_desc` ranks by net cashflow.

**REO tracker** — a daily sweep (GitHub Actions cron → `POST /api/reo/sweep`, plus a freshness-gated sweep on backend startup) records every HomeSteps listing ever sighted in SQLite (`REO_DB_PATH`, default `backend/reo_history.db`), so REO inventory that appeared and vanished between searches isn't lost. `GET /api/reo/inventory` reports active listings with new-this-week / price-cut flags; the frontend shows a tracker panel under the search form. Sweep history lives on the host disk — on Render's free tier it resets on deploy and rebuilds on the next sweep.

**REO price history** — every sweep records each listing's asks; the inventory API now carries `price_history` per listing (last 12 points), and the tracker panel + property cards render it as a sparkline showing how the bank has been stepping the price down. Hover the sparkline for the full ask ladder.

**Investor heatmap** — metro vs metro at a glance: what the typical home in each served market costs to carry (P&I + tax + insurance at the live rate, 20% down) versus what it rents for, ranked best cashflow first (`GET /api/market/heatmap`). Suburbs collapse into their metro row (Baltimore + Columbia + Annapolis are one row), active REO inventory joins per metro, and clicking a row runs a search there. Metros without a published rent show "—" and sort last.

**Compare tray** — shortlist up to 4 deals with the ± Compare chip on any card; the tray under the search form lines them up side-by-side (score, price vs value, rent, P&I, full carry, net cashflow, rent coverage, $/sqft, 5-yr ROI, REO badges). Shortlist persists in the browser (localStorage), surviving reloads and pagination.

**10-year hold projection** — every card has a lazy "10-Year Hold Projection" toggle: rent vs full carry year by year, property value along the metro's ZHVI trend (3.5%/yr national fallback), loan amortization, equity build, cumulative cashflow, and net position at exit after 6% selling costs (`POST /api/property/projection`).

**Deal alerts** — the REO tracker panel counts listings new or price-cut **since your last visit** (per-browser timestamp) and highlights those rows; optionally set `ALERT_WEBHOOK_URL` and every sweep POSTs new/price-cut listings to that webhook (Slack/Discord/Zapier). Unset = no-op.

## Running locally

Backend (port 8001):

```bash
cd backend
pip install -r requirements-dev.txt   # includes test deps; requirements.txt for prod
RAPIDAPI_KEY=... python main.py       # omit the key to run on mock data
```

Frontend (proxies `/api/*` to `http://localhost:8001` via `next.config.js`):

```bash
cd frontend
npm install
npm run dev
```

## Environment variables

| Var | Where | Purpose |
|---|---|---|
| `RAPIDAPI_KEY` | backend | Live Zillow listings. Unset → mock generator |
| `SWEEP_TOKEN` | backend + GH secret | Locks `POST /api/reo/sweep` (sent as `X-Sweep-Token` header). Unset → endpoint refuses |
| `ALERT_WEBHOOK_URL` | backend | Optional webhook (Slack/Discord/Zapier) receiving new/price-cut REO listings after each sweep. Unset → no-op |
| `REO_DB_PATH` | backend | REO tracker SQLite path. Default `backend/reo_history.db` |
| `REO_SWEEP_ON_STARTUP` | backend | `0` disables the startup sweep |
| `ALLOWED_ORIGINS` | backend | CORS allowlist, comma-separated. Default `*` (no credentials) |
| `BACKEND_URL` | Vercel | Backend origin for the frontend's `/api` rewrites |

## API

| Endpoint | Description |
|---|---|
| `GET /api/search` | Search + valuate + score. Filters (city/state/zip, price, beds/baths, sqft, type, year, HOA, DOM, `min_rent_coverage`), `sort_by` (deal_score, cashflow_desc, price_asc/desc, newest), opt-in `page`/`page_size` |
| `GET /api/property/{id}/valuation` | Full valuation for a previously served listing (in-memory registry — run a search first) |
| `POST /api/property/projection` | 10-year hold projection: rent vs carry, appreciation, amortization, equity, exit net position. Body: the deal's price/value/city/state/zip/tax/HOA |
| `GET /api/loan/rate` | Current 30yr fixed base rate (live FRED, cached 6h) |
| `POST /api/loan/quote` | Prorated mortgage quote (credit/loan-type/LTV/term adjustments, DTI, lender comparison) |
| `GET /api/cities` | Supported cities + market $/sqft + metro trend |
| `GET /api/market/baselines` | Real per-metro baselines from Zillow Research public data (appreciation, typical value, median list, typical rent, market heat). No key needed |
| `GET /api/market/heatmap` | Per-metro investor comparison: carry vs rent on the typical home at the live rate, cashflow/coverage, active REO count. No key needed |
| `GET /api/reo/inventory` | Tracked Freddie Mac REO inventory: active listings, new/price-cut flags, sweep history. No key needed |
| `POST /api/reo/sweep` | Trigger a REO sweep across all metros. Requires `X-Sweep-Token` = `SWEEP_TOKEN` |
| `GET /api/debug/source` | Diagnoses live-data failures: key presence (masked), RapidAPI reachability, quota/outage verdict |
| `GET /api/status` | Health check |

## Testing

```bash
cd backend
python3 -m pytest tests/ -q
```

## Deployment

- Backend: Render blueprint (`render.yaml`), service `homefinder-cqjv.onrender.com`
- Frontend: Vercel (`BACKEND_URL` → Render service)
- CI: GitHub Actions runs backend tests + frontend build on every push
