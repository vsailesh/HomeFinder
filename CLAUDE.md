# Home Finder

Real estate analysis tool with Python backend + Next.js frontend.

## Project Structure
- `backend/` - Data fetching, valuation engine, API endpoints
  - `main.py` - FastAPI server
  - `rapidapi_zillow.py` - Live Zillow listings via RapidAPI
  - `valuation_engine.py` - Property valuation models
  - `optimizer.py` - Investment optimization algorithms
  - `data_pipeline.py` - ETL pipeline + mock generator + listings cache
  - `loan_engine.py` - Mortgage rate/payment quotes (live FRED base rate)
  - `market_baselines.py` - Per-metro appreciation/list-price baselines (Zillow Research public CSVs, no key)
- `frontend/` - Next.js web application
  - `src/` - React components
- `file-lister/` - File listing utility

## Tech Stack
- Backend: Python 3, FastAPI
- Frontend: Next.js, React
- Data Sources: RapidAPI (Zillow live listings), FRED (mortgage rates)

## Common Tasks
- Add new property data sources
- Update valuation models
- Modify frontend UI components
- Run data pipeline
- Debug scraping issues

## Running
- Backend: `cd backend && python main.py`
- Frontend: `cd frontend && npm run dev`
