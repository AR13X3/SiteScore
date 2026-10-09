# SiteScore

**Pick a business type and 2–5 candidate addresses. SiteScore simulates each site and projects monthly revenue over 36 months, with P10/P50/P90 bands, and explains why each site wins or loses.**

Built at Hack48 Sydney. The first region is the City of Parramatta and the first business type is café. Gym and childcare are drafts, defined in config only.

## Quick start

Requires Python 3.11+ and Node.js 20+.

```bash
python run.py install    # one-time: virtualenv, dependencies, frontend build
python run.py start      # opens http://127.0.0.1:8000
```

To use the app (**Compare sites** screen):

1. Add up to 5 candidate sites:
   - type an address in the search box
   - click the map
   - or press **Load 3 demo sites**
2. Drag pins to adjust them, and rename sites in the side panel.
3. Select a site (its pin or its row) to see its catchment on the map:
   - walking rings for residents, workers and commuters
   - competitors, sized by the share of the site's demand they take
   - nearby anchors such as supermarkets, stations and schools

Results update automatically:

- a 36-month chart with P10–P90 bands, switchable between **revenue** and **profit**
- a ranking
- a "why each site wins or loses" card per site, with a per-layer breakdown against the average candidate

More controls:

- **Running costs:** the rent, wages, cost-of-goods and other-cost inputs drive profit, break-even and each site's chance of a 36-month loss. The defaults come from the business profile, and changes are sent to the model as overrides.
- **Data as of:** run the model as it would have looked on a past date. Only data published by then is used, from 12 Oct 2022 (when the last Census release came out) to today.
- **Backtest screen:** the time-safe backtest, with:
  - a cohort map and the opening check
  - closures by predicted third
  - a "which layers help?" dot plot with 90% intervals
  - a predicted-vs-actual table, where each café expands to show its evidence

  Another switch shows **today's cafés** (the cross-section), clearly marked as not time-safe.

The badge in the top bar shows whether the results use real or mock data. Hover over it for each source.

Other commands:

| Command | What it does |
|---|---|
| `python run.py data` | Fetch and process all data sources. Any source that fails falls back to mock data. |
| `python run.py test` | Run the test suite |
| `python run.py backtest` | Predict past openings with past data and score them against reality |
| `python run.py backtest --cross-section` | Score every café open today with today's data (not time-safe) |
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
| OpenStreetMap element history (OSM API) | Backtest outcomes only: when each café was mapped, when it closed and what replaced it | Every edit of every café element | 245 elements, 701 versions |
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
   - **Or discovery from OSM history.** A business counts as new when it first appears on the map inside the window set in `config/backtest.yaml` (Nov 2022 to Dec 2024). The date comes from the element's edit history, so it's exact to the day the café was mapped. A café that takes over an existing map element (renamed "Steaming Mug" → "Four Cups") is an opening too.
2. **Predict with the past only.** Each business is predicted as of the day before it was first mapped. Four rules hold:
   - Its market is built only through the dated as-of view.
   - It is excluded from its own competitor set. For a takeover, the café it replaced is left out too.
   - Every data source it touched is checked again: anything published after the as-of date raises `LeakageError`.
   - The prediction code never reads outcome data.

   Tests plant future data and check that predictions don't move.
3. **Check the opening was real.** "First mapped" often means an old café was mapped for the first time: the map's café count tripled between 2019 and 2026, mostly because mappers caught up. After predicting, each discovered café gets a verdict:

   | Verdict | Rule | Counted? |
   |---|---|---|
   | new | took over from another business at the same spot, or Foursquare added it (or its exact name was registered with ASIC) around the opening | yes |
   | unverified | no other source knows when it opened, or the sources disagree | yes |
   | older | Foursquare listed it more than 12 months before it was mapped | no |
   | remapped | the same business was already on the map nearby (a redrawn outline or a retag) | no |

   ASIC can't mark a café "older": the register has no addresses, so an old registration of the same name may belong to another outlet or another town.
4. **Then look at reality.** All outcome data is read only after every prediction is fixed.
   - **Survival at 18 months (secondary).** Did the café close within 18 months of opening? This is decided from OpenStreetMap **element histories**: every edit of every café ever mapped, with its date (OSM API, keyless, cached). Only strong evidence counts:

     | Status | Means |
     |---|---|
     | closed | a closure was recorded on or before the 18-month mark (dated by the edit; the real closure was on or before it) |
     | survived | it was still trading after the mark: a mapper edited or checked it then, or it is still on the map **and** an independent listing confirms it after the mark (Google operational, Foursquare refreshed, Overture with confidence ≥ 0.75) |
     | censored | the 18-month mark hasn't arrived yet |
     | unknown | anything weaker or contradictory |

     **What a closure became.** "Replaced" means another café took over: the element was renamed, or it was deleted and a different café appeared within 25 m. That's an operator failure, and the site may be fine. "Vacant" (tagged disused) and "other use" (e.g. a café that became a sandwich bar or a gaming centre) are site failures. "Removed" means it was deleted with no successor seen. Name corrections, retags of the same business and re-mapping (deleted, then redrawn nearby under the same name) are not closures.

     **Site churn.** How many cafés have closed at the same spot (within 25 m) since 2019.

     The report gives closure rates by predicted third, for the model and for the baseline.
   - **Still trading today?** This is a weighted vote of every source that knows the business. The weights are in `config/backtest.yaml`, and the report lists each café's evidence.

     | Source | What it says | Weight |
     |---|---|---|
     | OpenStreetMap | Closed, replaced or vacant (from the element history) | 2.0 |
     | OpenStreetMap | Still on the map | 1.0 |
     | Overture | Listed with a confidence score | 1.0 × confidence |
     | Overture | Not listed | 0.4 (weak) |
     | Foursquare | Date marked closed, or still listed | 1.0 |
     | ASIC business names | A unique exact name registered around the opening is still registered, or cancelled | 0.75 |
     | Google (with key) | Business status | 3.0 |

     Older data counts for less: weights halve every 12 months since the data was collected.
   - change in weekly opening hours
   - with a Google Places key: reviews per month since opening, and rating. This is the main performance measure. Survival is secondary.
5. **Accuracy,** always compared with a naive "foot traffic only" baseline:
   - share of pairs ranked correctly (50% = coin flip) and Spearman correlation, against the combined actual-performance score
   - top-third vs bottom-third actual percentile
   - for survival: AUC (survivors above closures), closure rate by predicted third, and whether spots without café closures are predicted above spots with them

**Real Parramatta results (10 Oct 2026, free outcome sources, no Google):**

Discovery found 56 cafés first mapped from Nov 2022 to Dec 2024. The opening check rejected 27 of them:
- 26 were older cafés mapped late (e.g. Three Beans and Nadia's, both on Foursquare since 2010)
- 1 had only been redrawn (Gatehouse Tea Rooms)

That leaves 29 cafés: 18 confirmed new (8 of them took over another café's spot) and 11 unverified.

| Measure | Model | Foot traffic only |
|---|---|---|
| Closed within 18 months | **none of 29** (20 survived, 9 unknown) | |
| Survival AUC | n/a (no closures) | n/a |
| Café closures at the same spot since 2019, mean per café, top / middle / bottom predicted third | 0.10 / 0.40 / 0.44 | 0.30 / 0.20 / 0.44 |
| Spots without closures predicted above spots with them (AUC) | 0.70 | 0.55 |
| Pairs ranked correctly (combined proxy, no Google) | 51% | 59% |

**What this does and doesn't show:**
- **No survival signal can be measured yet.** None of the genuinely new cafés closed within 18 months, so there is nothing to rank against.
- **The two earlier "closures" weren't 18-month closures.** Koko 'n' Beans and Mulberry Tree were older cafés: Foursquare listed them from 2014 and 2016.
- **A weak hint on site churn.** The model ranks spots where a café closed before lower than the baseline does (AUC 0.70 vs 0.55). But the 8 spots with any closure are exactly the 8 takeover openings, so this only says the model rates cafés that replaced a failed café lower. Those predecessors' closures were knowable before opening, and the model didn't use them. It's 8 cafés against 21: a hint, not evidence.
- **The combined performance score is not informative yet.** Without Google it is mostly the "still trading" vote, which barely varies among open cafés.

The missing ingredient is still a performance measure for open cafés. Adding `GOOGLE_PLACES_API_KEY` and running `python run.py data --only google_places` adds reviews per month and rating (about 300 requests, capped in `config/sources.yaml`, and likely inside Google's free monthly allowance).

### Which layers help? (layer by layer)

Revenue is an exact product of layer factors, so switching later layers off gives a ladder of nested models. Each rung is scored against every outcome, with a 90% bootstrap interval. The "gain" is that rung's Spearman minus foot traffic only.

| Rung | Layers |
|---|---|
| Foot traffic only | demand (this is also the baseline) |
| + demographic fit and anchors | × fit × anchors |
| + competition (Huff) | × gravity share |
| + customer agents | × customer behaviour |
| + competitors' price response | × price response |
| Full model | × $ per customer × capacity |

The backtest report and the cross-section below both include it.

### Cross-section: today's cafés (NOT time-safe)

```bash
python run.py backtest --cross-section    # also GET /api/backtest/cross-section
```

Every independent café on today's map (186 in Parramatta) is scored with today's data, against today's market with itself removed. The scores are then compared with today's outcomes:
- Google reviews per month (needs the key)
- Google review count
- site churn

The sample is about six times the genuine openings. But it is **not time-safe**: today's map already reflects which cafés succeeded (rivals cluster near busy spots, and weak cafés have closed), so it measures association, not prediction. The report and the API mark it `time_safe: false`.

**Results so far (10 Oct 2026, no Google).** Spearman with "fewer café closures at the spot since 2019", with 90% intervals:

| Rung | Cross-section, 186 cafés | Backtest, 29 cafés (time-safe) |
|---|---|---|
| Foot traffic only | 0.03 [−0.06, 0.13] | 0.09 [−0.24, 0.36] |
| + fit and anchors | 0.03 | 0.14 |
| + competition (Huff) | 0.08 | 0.39 [0.11, 0.62] |
| + customer agents | 0.07 | 0.35 |
| + price response | 0.07 | 0.35 |
| Full model | 0.08 [−0.05, 0.20] | 0.27 [−0.01, 0.51] |

**No layer has a gain over foot traffic that clears the noise.** Every gain interval includes or touches zero. In the small time-safe cohort, competition looks helpful, but that cohort's churn is entirely its 8 takeover spots. In the six-times-larger cross-section, the effect disappears. Site churn is a blunt outcome: most spots have none.

On the mock city, where reviews come from a known "true" performance, the same pipeline recovers the planted signal (Spearman ≈ 0.36 with reviews per month). The comparison works; the real-data outcome it needs is Google reviews.


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
