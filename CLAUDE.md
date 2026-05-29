# Home Finder

Real estate analysis tool with Python backend + Next.js frontend.

## Project Structure
- `backend/` - Python scrapers, valuation engine, API endpoints
  - `main.py` - FastAPI server
  - `zillow_scraper.py` - Zillow data extraction
  - `redfin_scraper.py` - Redfin data extraction
  - `valuation_engine.py` - Property valuation models
  - `optimizer.py` - Investment optimization algorithms
  - `data_pipeline.py` - ETL pipeline for property data
- `frontend/` - Next.js web application
  - `src/` - React components
- `file-lister/` - File listing utility

## Tech Stack
- Backend: Python 3, FastAPI
- Frontend: Next.js, React
- Data Sources: Zillow API, Redfin scraper, RapidAPI

## Common Tasks
- Add new property data sources
- Update valuation models
- Modify frontend UI components
- Run data pipeline
- Debug scraping issues

## Running
- Backend: `cd backend && python main.py`
- Frontend: `cd frontend && npm run dev`
