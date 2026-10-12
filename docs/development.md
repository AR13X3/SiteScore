# Development

Commands, configuration files and the repo layout. See also [CONTRIBUTING.md](../CONTRIBUTING.md).

## Commands

| Command | What it does |
|---|---|
| `python run.py data` | Fetch and process all data sources. Any source that fails falls back to mock data. With a Google key this includes Google Places (guarded, see [Google Places](data.md#google-places-fetched-once-kept-30-days)). |
| `python run.py data --only google_places` | Fetch Google Places only. Within 30 days of a fetch it does nothing unless you add `--force` (which re-matches from the cache) |
| `python run.py test` | Run the test suite |
| `cd frontend && npm test` | Frontend logic tests (Node's built-in runner, no extra packages) |
| `python run.py backtest` | Predict past openings with past data and score them against reality |
| `python run.py backtest --cross-section` | Score every café open today with today's data (not time-safe) |
| `python run.py dev` | Backend and frontend with hot reload |
| `python run.py data --make-demo-pack` | Snapshot your current real tables into `data/demo-pack/` (to commit) |

If the repo is inside OneDrive or Dropbox, the virtualenv and raw downloads go to `%LOCALAPPDATA%\SiteScore` instead, so you don't sync about 1 GB of packages. Set `SITESCORE_CACHE_DIR` to choose another location.

## Configuration

| File | Contents |
|---|---|
| `config/regions/parramatta.yaml` | Study area: LGA code, bbox, map view |
| `config/business_types/*.yaml` | One file per business type. Add a file to add a type. |
| `config/model.yaml` | Huff, agent-based, game theory and Monte Carlo assumptions |
| `config/calendars/nsw.yaml` | School-holiday pattern |
| `config/sources.yaml` | Data sources, licences, publication dates |
| `config/backtest.yaml` | Backtest window, score horizon, outcome weights |

## Repo layout

```
config/          all assumptions (YAML)
sitescore/
  datastore/     as-of store + leakage guard
  pipeline/      one adapter per data source (real fetch + mock fallback)
  model/         one module per model layer
  backtest/      backtest runner and metrics
  analyst/       AI analyst: OpenRouter client, tools, agent loop
  api/           FastAPI app
frontend/        web app: React + TypeScript, Leaflet map, ECharts (home, workspace, evidence, data)
backtests/       backtest cohorts (CSV)
data/demo-pack/  snapshot of the processed real data (loaded on a fresh clone)
data/raw/        Google Places cache and request ledger (gitignored, never committed)
tests/
```
