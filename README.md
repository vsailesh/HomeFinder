# Home Finder

Real estate deal analyzer. Searches listings, values each property variable-by-variable, scores the deal (0–100 + letter grade), and quotes mortgages against the live market rate.

- **Backend** — Python 3.12 / FastAPI (`backend/`)
- **Frontend** — Next.js / React (`frontend/`)
- **Live data** — Zillow listings via RapidAPI (`zillow-com-live-data-scraper-api`); Freddie Mac REO listings via HomeSteps (no key); mortgage base rate via FRED (`MORTGAGE30US`, no key); per-metro market baselines from Zillow Research public CSVs (no key): home values & trailing-12mo appreciation, median list, rents (metro + ZIP), and market heat (sale-to-list ratio, price-cut share, days-to-pending)

Listing sources cascade in order: RapidAPI Zillow (full inventory, needs quota) → Freddie Mac HomeSteps REO (real bank-owned listings, no key, thin inventory; cards badged "🏦 Freddie Mac REO", sqft estimated from room count and flagged) → mock generator (labeled "⚠️ Demo data"). Mortgage rates and metro trends are always live.

20 cities across 11 states (MD core + Charlotte, Raleigh, Tampa, Jacksonville, Atlanta, Chicago, Cleveland, Detroit, Kansas City, Philadelphia, Phoenix, Indianapolis), each joined to its Zillow Research metro baseline.

**Investor analysis** — every scored deal carries: estimated rent (Zillow ZORI, ZIP-level when published, metro fallback), P&I payment, full monthly carry (P&I + property tax + insurance + HOA), and cashflow net of carry. Deal scoring factors rental coverage; metro heat (price cuts, pace, sale-to-list) adds negotiation-leverage reasons/risks. Search filters include `min_rent_coverage` (rent ÷ P&I) and `sort_by=cashflow_desc` ranks by net cashflow.

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
| `ALLOWED_ORIGINS` | backend | CORS allowlist, comma-separated. Default `*` (no credentials) |
| `BACKEND_URL` | Vercel | Backend origin for the frontend's `/api` rewrites |

## API

| Endpoint | Description |
|---|---|
| `GET /api/search` | Search + valuate + score. Filters (city/state/zip, price, beds/baths, sqft, type, year, HOA, DOM, `min_rent_coverage`), `sort_by` (deal_score, cashflow_desc, price_asc/desc, newest), opt-in `page`/`page_size` |
| `GET /api/property/{id}/valuation` | Full valuation for a previously served listing (in-memory registry — run a search first) |
| `GET /api/loan/rate` | Current 30yr fixed base rate (live FRED, cached 6h) |
| `POST /api/loan/quote` | Prorated mortgage quote (credit/loan-type/LTV/term adjustments, DTI, lender comparison) |
| `GET /api/cities` | Supported cities + market $/sqft + metro trend |
| `GET /api/market/baselines` | Real per-metro baselines from Zillow Research public data (appreciation, typical value, median list, typical rent, market heat). No key needed |
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
