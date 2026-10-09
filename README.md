# SiteScore

**Pick a business type and 2–5 candidate addresses. SiteScore simulates each site and projects monthly revenue over 36 months, with P10/P50/P90 bands, and explains why each site wins or loses.**

Built at Hack48 Sydney. The first region is the City of Parramatta and the first business type is café. Gym and childcare are drafts, defined in config only.

## Quick start

Requires Python 3.11+ and Node.js 20+.

```bash
python run.py install    # one-time: virtualenv, dependencies, frontend build
python run.py start      # opens http://127.0.0.1:8000
```

To use the app:

1. Click the map to drop up to 5 candidate sites, or press **Load 3 demo sites**.
2. Drag pins to adjust, and rename sites in the side panel.

Results update automatically:

- a 36-month revenue chart
- a ranking
- a "why each site wins or loses" card per site, with a per-layer breakdown against the average candidate

The badge in the top bar shows whether the results use real or mock data. Hover over it for each source.

Other commands:

| Command | What it does |
|---|---|
| `python run.py data` | Fetch and process all data sources. Any source that fails falls back to mock data. |
| `python run.py test` | Run the test suite |
| `python run.py dev` | Backend and frontend with hot reload |

If the repo is inside OneDrive or Dropbox, the virtualenv and raw downloads go to `%LOCALAPPDATA%\SiteScore` instead, so you don't sync about 1 GB of packages. Set `SITESCORE_CACHE_DIR` to choose another location.

## API keys (`.env`)

All keys are optional. `install` creates `.env` from `.env.example`.

| Key | Needed for | Without it |
|---|---|---|
| `GOOGLE_PLACES_API_KEY` | Backtest ground truth: rating, review count, open/closed | Backtest uses OSM-only outcome proxies |
| `TFNSW_API_KEY` | GTFS stop locations (bus stops) | Station patronage still works, since it needs no key |

ABS, OpenStreetMap, NSW Planning Portal and Transport for NSW station patronage need no keys.

## Data sources

All sources are official or open data. Details and licences are in [config/sources.yaml](config/sources.yaml).

| Source | Used for | Granularity | Parramatta (LGA + 1.5 km) |
|---|---|---|---|
| ABS Census 2021 General Community Profile | Residents, age, income, households, dwellings | SA1 | 1,120 SA1s, 505k residents |
| ABS Census 2021 Working Population Profile | Workers by place of work | SA2, spread onto mesh blocks by land use | 234k workers on 4,551 blocks |
| ABS ASGS 2021 boundaries | Study area, SA1 centroids, mesh-block land use | SA1 / SA2 / MB | fetched for the area only |
| Transport for NSW station entries/exits | Commuter foot traffic | Station × month, Jul 2016 onwards | 41 train, metro and light-rail stations |
| OpenStreetMap (Overpass) | Competitors, anchor tenants, stations | Point; **quarterly historical snapshots** | ~900 points per snapshot |
| NSW Planning Portal online DA data | Future residents from development applications | Application → lodged and determined events | 2,767 DAs with new dwellings |
| NSW Spatial Services address points (Nominatim fallback) | Address search in the UI (`GET /api/geocode?q=`) | Address | live |
| Google Places (optional) | Backtest outcome proxies only | Place | real adapter arrives with the backtest |

`python run.py data` downloads about 140 MB the first time and caches everything under the raw folder. Re-runs reuse that cache.

**OpenStreetMap snapshots are slow.** Each historical snapshot is a heavy query, and public Overpass servers are often overloaded. Snapshots are fetched in priority order: today, then the backtest window, then the rest. Failures are retried once and then skipped. Run `python run.py data --only osm` again later to fill any gaps. The model always uses the latest snapshot on or before the as-of date.

#### Data caveats

- **Planning Portal outcomes:** the Portal reports "Determined" without saying approved or refused, so those dwellings count at a 90% approval rate (in config).
- **Re-lodged projects:** a project re-lodged as a new DA at the same site is counted once.
- **Small Census areas:** values ABS suppressed in small SA1s are filled with the population-weighted median.
- **Station locations:** these come from OpenStreetMap, because the patronage files only have station names.

### No leakage ("as of" dating)

Every stored row records when it was true (`valid_from` / `valid_to`) and when it became public (`published_at`). A model run as of date *D* only sees rows published on or before *D*. For example, Census 2021 describes August 2021 but was published on 28 June 2022, and its employment data on 12 October 2022.

Four rules enforce this in code:

1. **Model modules can only read data through `AsOfView`.** A test fails if model code touches the store, files, or the pipeline directly.
2. **`AsOfView` filters on `published_at` and then re-checks its own output.** Any row dated after *D* raises `LeakageError`.
3. **Outcome data is never visible to the model.** For example, today's Google ratings can't be read through the view at all.
4. **Every view logs which tables it read and the newest publication date it used.** Each result can show its data cut-off.

`tests/test_leakage.py` checks these rules, including a property test over 150 random dates. Deleting the filter makes 6 tests fail.

### Mock fallback

Every source has a mock with identical columns and identical dating, generated from one shared synthetic city (`sitescore/pipeline/mock_city.py`). In it, cafés cluster where the jobs are, and weaker locations close sooner. If a real fetch fails, that source falls back to mock and the reason is recorded. `GET /api/data/status` shows real vs mock for each table.

- **First start with no data:** the app generates mock data automatically.
- **Once real data is fetched:** it stays cached and is preferred over mock.
- **`SITESCORE_FORCE_MOCK=1`:** forces mock everywhere, as a demo safety switch.

Mock data checks the plumbing, not the model's accuracy. Only a backtest on real data does that.

## Model

Each layer is a separate module in `sitescore/model/` with its own tests. Every assumption is in `config/`.

Mature monthly revenue is **exactly** the product of the layer factors:

```
potential customers × demographic fit × anchor boost × gravity share
  × customer behaviour × price response × ($ per customer) × capacity
```

**Agents generalise Huff.** An agent is a demand point combined with a customer type. Each agent's choice utility is `α·log(attractiveness) − β·log(distance)` (the Huff model in logit form) plus terms for price, quality and varied tastes. With those extras switched off, the agents reproduce Huff exactly, and a test checks this. The **customer behaviour** factor is therefore only what tastes and quality add.

**Habits shape the ramp-up, not the winner.** Awareness of the new store grows along the profile's ramp curve, and each month only some customers (50%) reconsider where they go. Together these produce the ramp-up curve.

**The price game uses standard industrial-organisation logic.**

1. Each nearby competitor's marginal cost is backed out from today's price, assuming that price is already optimal.
2. When we open, every competitor within 800 m re-optimises, in damped simultaneous best-response rounds, until prices settle.
3. The **price response** factor is the change in our share from competitors' new prices.

Our own price stays at the profile's price by default. The model also reports the price it would choose to maximise margin.

So comparing factors between two sites explains exactly why one out-earns the other. Each layer also returns a one-line summary and a detailed breakdown, for example:

- which demographic features help or hurt
- which competitors take the most local demand

To try it, start the app and open `http://127.0.0.1:8000/docs`, then call `POST /api/evaluate` with up to 5 sites and an optional `as_of` date.

1. **Demand:** residents, workers and commuters within each segment's walking catchment, weighted by time of day.
2. **Fit:** local demographics against the business type's customer profile. Weights are in YAML.
3. **Competition:** Huff gravity model across all competitors, plus an "elsewhere" option.
4. **Agent-based:** a few thousand virtual customers choose stores by distance, price, quality and habit.
5. **Game theory:** nearby competitors' prices respond to our opening through best-response rounds until prices settle.
6. **Time dynamics:** ramp-up, seasonality, school holidays, and developments completing on their expected dates.
7. **Spend:** visits × average transaction value gives revenue. Rent and wages give profit.
8. **Uncertainty:** Monte Carlo over key assumptions gives P10/P50/P90 bands.

## Configuration

| File | Contents |
|---|---|
| `config/regions/parramatta.yaml` | Study area: LGA code, bbox, map view |
| `config/business_types/*.yaml` | One file per business type. Add a file to add a type. |
| `config/model.yaml` | Huff, agent-based, game theory and Monte Carlo assumptions |
| `config/calendars/nsw.yaml` | School-holiday pattern |
| `config/sources.yaml` | Data sources, licences, publication dates |

## Repo layout

```
config/          all assumptions (YAML)
sitescore/
  datastore/     as-of store + leakage guard
  pipeline/      one adapter per data source (real fetch + mock fallback)
  model/         one module per model layer
  backtest/      backtest runner and metrics
  api/           FastAPI app
frontend/        web app: React + TypeScript, Leaflet map, ECharts
backtests/       backtest cohorts (CSV)
tests/
```

## Known limitations

- Absolute dollar figures depend on spend assumptions in YAML. The backtest validates the **ranking** of sites, not absolute revenue.
- Walking distance is straight-line distance × a detour factor (1.3). Using the OSM walking network is a planned upgrade.
- Workers are only published down to SA2. Within an SA2 they are spread over commercial, industrial, education and health mesh blocks.
- OSM was less complete in earlier years, so historical competitor counts are slightly low.
