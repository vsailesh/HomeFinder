# Home Finder

Real estate deal analyzer. Searches listings, values each property variable-by-variable, scores the deal (0–100 + letter grade), and quotes mortgages against the live market rate.

- **Backend** — Python 3.12 / FastAPI (`backend/`)
- **Frontend** — Next.js / React (`frontend/`)
- **Live data** — Zillow listings via RapidAPI (`zillow-com-live-data-scraper-api`); mortgage base rate via FRED (`MORTGAGE30US`, no key); per-metro market baselines (appreciation, list prices) from Zillow Research public CSVs (no key)

When no RapidAPI key is configured — or the API errors/quota-exhausts — the app falls back to a realistic mock generator and labels every card "⚠️ Demo data". Mortgage rates are always live (FRED needs no key).

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
| `GET /api/search` | Search + valuate + score. Filters (city/state/zip, price, beds/baths, sqft, type, year, HOA, DOM), `sort_by`, opt-in `page`/`page_size` |
| `GET /api/property/{id}/valuation` | Full valuation for a previously served listing (in-memory registry — run a search first) |
| `GET /api/loan/rate` | Current 30yr fixed base rate (live FRED, cached 6h) |
| `POST /api/loan/quote` | Prorated mortgage quote (credit/loan-type/LTV/term adjustments, DTI, lender comparison) |
| `GET /api/cities` | Supported cities + market $/sqft |
| `GET /api/market/baselines` | Real per-metro baselines from Zillow Research public data (trailing-12mo appreciation, typical value, median list price). No key needed |
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
