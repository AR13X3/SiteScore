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

## The live demo

The live site has two halves:

- **The site** is the frontend on GitHub Pages: https://ar13x3.github.io/SiteScore/. `.github/workflows/pages.yml` builds it on every push to `main`, with `VITE_API_BASE` pointing at the API.
- **The API** is the Docker image (`Dockerfile`) running on Joy's own server, made public through Tailscale Funnel (port 10000 only). `deploy/self-host/update.sh` runs from cron every 5 minutes: when `main` has moved it rebuilds the image and swaps the container. `SITESCORE_CORS_ORIGINS` lets the Pages site call it from the browser.

If the API can't be reached, the site shows a maintenance page ("Joy's server is offline and under maintenance") that checks every 30 seconds and comes back by itself. If the API drops mid-visit, a bar says so. The container has no model key, so the analyst [replays recorded runs](analyst.md#recorded-runs-the-hosted-demo). The `Demo container` CI job builds and smoke-tests the image on every pull request.

To host the API yourself on any machine with Docker:

```bash
git clone https://github.com/AR13X3/SiteScore.git && cd SiteScore
SITESCORE_CORS_ORIGINS=https://yourname.github.io deploy/self-host/update.sh   # builds and starts it on 127.0.0.1:7860
```

Then make it public (Tailscale Funnel, a Cloudflare tunnel or a reverse proxy), point `VITE_API_BASE` in `pages.yml` at it, and add the cron line from the top of `update.sh`. To run everything in one container without Pages: `docker run -p 7860:7860 sitescore` serves the site and the API together.

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
  analyst/       AI analyst: OpenRouter client, tools, agent loop, recorded-run replay
  api/           FastAPI app
frontend/        web app: React + TypeScript, Leaflet map, ECharts (home, workspace, evidence, data)
backtests/       backtest cohorts (CSV)
data/demo-pack/  snapshot of the processed real data (loaded on a fresh clone)
data/analyst-replays/  recorded analyst runs, replayed when no model key is set
data/raw/        Google Places cache and request ledger (gitignored, never committed)
tests/
deploy/self-host/  keeps a self-hosted API in step with main (see Dockerfile)
```
