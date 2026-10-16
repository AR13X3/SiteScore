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

The demo runs the app in one Docker container (`Dockerfile`) on a free [Hugging Face Space](https://huggingface.co/spaces). Every push to `main` redeploys it (`.github/workflows/deploy-demo.yml`), and the `Demo container` CI job builds and smoke-tests the same image on every pull request. The container runs on the committed demo pack, warms the map and the Evidence page at startup, and has no model key, so the analyst [replays recorded runs](analyst.md#recorded-runs-the-hosted-demo).

To set it up once:

1. Create a free Hugging Face account and a **write** token (Settings → Access Tokens).
2. In the GitHub repository's **Settings → Secrets and variables → Actions**, add the secret `HF_TOKEN` (the token) and the variable `HF_SPACE` (for example `yourname/sitescore`).
3. Run **Actions → Deploy demo → Run workflow**, or push to `main`. The first run creates the Space; Hugging Face then builds the image (about 5 minutes) and serves it at `https://yourname-sitescore.hf.space`.

Free Spaces sleep after about two days without visitors and take a minute or so to wake. To run the same container yourself: `docker build -t sitescore . && docker run -p 7860:7860 sitescore`, then open http://localhost:7860. Add `-e OPENROUTER_API_KEY=...` for a live analyst, but only behind authentication if it's public.

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
deploy/space/    the live demo: its Hugging Face card and deploy script (see Dockerfile)
```
