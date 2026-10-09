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
| `python run.py backtest` | Predict past openings with past data and score them against reality |
| `python run.py dev` | Backend and frontend with hot reload |

If the repo is inside OneDrive or Dropbox, the virtualenv and raw downloads go to `%LOCALAPPDATA%\SiteScore` instead, so you don't sync about 1 GB of packages. Set `SITESCORE_CACHE_DIR` to choose another location.

## API keys (`.env`)

All keys are optional. `install` creates `.env` from `.env.example`.

| Key | Needed for | Without it |
|---|---|---|
| `GOOGLE_PLACES_API_KEY` | Backtest ground truth: rating, review count, open/closed | Backtest uses OSM-only outcome proxies |
| `HF_TOKEN` | Latest Foursquare Open Source Places (free Hugging Face account; accept the dataset terms) | Foursquare data comes from a public mirror whose newest release is Feb 2025 |
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
| Google Places (optional) | Backtest outcomes only: reviews, rating, status | Place | needs a key |
| Overture Maps Places | Backtest outcomes only: still listed? with what confidence | Place, monthly | 21.6k places |
| Foursquare Open Source Places | Backtest outcomes only: date added, refreshed, closed | Place | 24.5k places (Feb 2025 snapshot) |
| ASIC Business Names | Backtest outcomes only: name registered or cancelled | Business name | 8.8k matching names |

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

### Uncertainty bands

Each simulation draws the uncertain assumptions 300 times. The list and the distributions are in `config/model.yaml` under `montecarlo`:

- spend per visit
- participation and visit frequency per segment
- ramp-up speed
- distance decay
- the pull of other options
- price sensitivity
- habit strength

All candidate sites see the same draws. That makes "best in 94% of scenarios" a fair comparison. The chart shows the central estimate as a line and the P10–P90 range as a shaded band. Each site also gets its chance of a 36-month loss.

Re-running the full model 300 × 5 times would take about a minute, so **fast mode** uses the model's exact factor structure instead:

| Assumption | How fast mode applies it |
|---|---|
| Spend, participation, visit frequency | Exact rescaling |
| Distance decay, pull of other options | The real choice model (Huff plus agents) is re-run on a small grid and interpolated |
| Price sensitivity | The price game is re-solved on a grid |
| Ramp-up and habit | Recomputed in closed form |

At the central values, fast mode reproduces the base run exactly. Against full re-runs, its per-scenario error is about 1% (median), and the tests check both. Five sites × 300 scenarios take about 2 seconds. The UI shows the central estimate immediately and fades the bands in when they arrive.

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

## Backtest (our proof)

```bash
python run.py backtest                  # cafés discovered from OpenStreetMap history
python run.py backtest --cohort demo    # backtests/cohorts/demo.csv
```

1. **Cohort.**
   - **Your own CSV** in `backtests/cohorts/`, with name, opening month, and lat/lon or an address.
   - **Or discovery from OSM history.** A business counts as new when it first appears in a quarterly snapshot inside the window set in `config/backtest.yaml` (Nov 2022 to Dec 2024).
2. **Predict with the past only.** Each business is predicted as of the day before it opened, or the last snapshot before it appeared. Four rules hold:
   - Its market is built only through the dated as-of view.
   - It is excluded from its own competitor set.
   - Every data source it touched is checked again: anything published after the as-of date raises `LeakageError`.
   - The prediction code never reads outcome data.

   Tests plant future data and check that predictions don't move.
3. **Then look at reality.** These signals count as actual performance:
   - **Survival**, as a weighted vote of every source that knows the business. The weights are in `config/backtest.yaml`, and the report lists each café's evidence.

     | Source | What it says | Weight |
     |---|---|---|
     | OpenStreetMap | A mapper saw it removed, replaced or tagged disused | 2.0 |
     | OpenStreetMap | Still on the map | 1.0 |
     | Overture | Listed with a confidence score | 1.0 × confidence |
     | Overture | Not listed | 0.4 (weak) |
     | Foursquare | Date marked closed, or still listed | 1.0 |
     | ASIC business names | A unique exact name registered around the opening is still registered, or cancelled | 0.75 |
     | Google (with key) | Business status | 3.0 |

     **Name changes:** a corrected name ("Picollo Me" → "Piccolo Me") counts as the same business, while a different business at the same spot counts as a replacement.

     **Older data counts for less:** weights halve every 12 months since the data was collected, so the free Foursquare snapshot from February 2025 counts for about a third.
   - change in weekly opening hours
   - with a Google Places key: reviews per month since opening and rating
4. **Accuracy.** Four measures, each compared with a naive "foot traffic only" baseline:
   - share of pairs ranked correctly (50% = coin flip)
   - Spearman correlation
   - survival AUC (does the model rank survivors above closures?)
   - top-third vs bottom-third actual percentile

**Real Parramatta results (10 Oct 2026, free outcome sources, no Google):**

| Measure | Model | Foot traffic only |
|---|---|---|
| Pairs ranked correctly | 48% | 51% |
| Survival AUC | 0.48 | 0.48 |

46 cafés were scored, and the evidence vote marks 2 as closed:
- **Koko 'n' Beans:** replaced by "XA Expresso"
- **Mulberry Tree:** replaced by "The Chai Nook"

OSM alone had said 4 closed. Two of those were cafés whose names were corrected on the map, not real closures.

**So far, neither the model nor the baseline beats a coin flip.** Two closures are too few to judge anything. Among open cafés, the survival score mostly reflects how many datasets list a business, not how well it trades.

The missing ingredient is a performance measure for businesses that are still open. Adding `GOOGLE_PLACES_API_KEY` and running `python run.py data --only google_places` adds reviews per month and rating (about 300 requests, capped in `config/sources.yaml`, and likely inside Google's free monthly allowance).

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
