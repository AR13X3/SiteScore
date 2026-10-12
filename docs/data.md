# Data

Where the data comes from, how it is dated so the model can never see the future, and which keys unlock what.

All sources are official or open data. Details and licences are in [config/sources.yaml](../config/sources.yaml).

| Source | Used for | Granularity | Parramatta (LGA + 1.5 km) |
|---|---|---|---|
| ABS Census 2021 General Community Profile | Residents, age, income, households, dwellings | SA1 | 1,120 SA1s, 505k residents |
| ABS Census 2021 Working Population Profile | Workers by place of work | SA2, spread onto mesh blocks by land use | 234k workers on 4,551 blocks |
| ABS ASGS 2021 boundaries | Study area, SA1 centroids, mesh-block land use | SA1 / SA2 / MB | fetched for the area only |
| Transport for NSW station entries/exits | Commuter foot traffic | Station × month, Jul 2016 onwards | 41 train, metro and light-rail stations |
| OpenStreetMap (Overpass) | Competitors, anchor tenants, stations | Point; **quarterly historical snapshots** | ~900 points per snapshot |
| OpenStreetMap element history (OSM API) | Backtest outcomes only: when each café was mapped, when it closed and what replaced it | Every edit of every café element | 245 elements, 701 versions |
| OpenStreetMap vacant shopfronts (Overpass) | Candidate sites for the spot finder (never a model input) | Point, today's map | 55 empty shopfronts |
| NSW Planning Portal online DA data | Future residents from development applications | Application → lodged and determined events | 2,767 DAs with new dwellings |
| NSW Spatial Services address points (Nominatim fallback) | Address search in the UI (`GET /api/geocode?q=`) | Address | live |
| Google Places (optional) | Backtest outcomes only: reviews, rating, status | Place | 232 of 316 businesses (fetched 10 Oct 2026) |
| Overture Maps Places | Backtest outcomes only: still listed? with what confidence | Place, monthly | 21.6k places |
| Foursquare Open Source Places | Backtest outcomes only: date added, refreshed, closed | Place | 24.5k places (Feb 2025 snapshot) |
| ASIC Business Names | Backtest outcomes only: name registered or cancelled | Business name | 8.8k matching names |

`python run.py data` downloads about 140 MB the first time and caches everything under the raw folder. Re-runs reuse that cache.

**OpenStreetMap snapshots are slow.** Each historical snapshot is a heavy query, and public Overpass servers are often overloaded. Snapshots are fetched in priority order: today, then the backtest window, then the rest. Failures are retried once and then skipped. Run `python run.py data --only osm` again later to fill any gaps. The model always uses the latest snapshot on or before the as-of date.

**Lagging mirrors are rejected.** Every Overpass answer reports how current its database is. A snapshot is only accepted from a server whose data reaches the snapshot's date, and today's map only from a server at most 2 days behind. Stale cached snapshots are re-fetched. One mirror had served an October 2026 snapshot from a database that stopped in May 2026; the element histories confirm the replacement matches.

## Data caveats

- **Planning Portal outcomes:** the Portal reports "Determined" without saying approved or refused, so those dwellings count at a 90% approval rate (in config).
- **Re-lodged projects:** a project re-lodged as a new DA at the same site is counted once.
- **Small Census areas:** values ABS suppressed in small SA1s are filled with the population-weighted median.
- **Station locations:** these come from OpenStreetMap, because the patronage files only have station names.

## No leakage ("as of" dating)

Every stored row records when it was true (`valid_from` / `valid_to`) and when it became public (`published_at`). A model run as of date *D* only sees rows published on or before *D*. For example, Census 2021 describes August 2021 but was published on 28 June 2022, and its employment data on 12 October 2022.

Four rules enforce this in code:

1. **Model modules can only read data through `AsOfView`.** A test fails if model code touches the store, files, or the pipeline directly.
2. **`AsOfView` filters on `published_at` and then re-checks its own output.** Any row dated after *D* raises `LeakageError`.
3. **Outcome data is never visible to the model.** For example, today's Google ratings can't be read through the view at all.
4. **Every view logs which tables it read and the newest publication date it used.** Each result can show its data cut-off.

`tests/test_leakage.py` checks these rules, including a property test over 150 random dates. Deleting the filter makes 6 tests fail.

## Mock fallback

Every source has a mock with identical columns and identical dating, generated from one shared synthetic city (`sitescore/pipeline/mock_city.py`). In it, cafés cluster where the jobs are, and weaker locations close sooner. If a real fetch fails, that source falls back to mock and the reason is recorded. `GET /api/data/status` shows real vs mock for each table.

- **First start with no data:** the app loads the demo pack (real data). It generates mock only for tables the pack doesn't have, such as Google Places.
- **Once real data is fetched:** it stays cached and is preferred over mock.
- **`SITESCORE_FORCE_MOCK=1`:** forces mock everywhere, as a demo safety switch.

Mock data checks the plumbing, not the model's accuracy. Only a backtest on real data does that.

## API keys (`.env`)

All keys are optional. `install` creates `.env` from `.env.example`.

| Key | Needed for | Without it |
|---|---|---|
| `GOOGLE_PLACES_API_KEY` | Backtest ground truth: rating, review count, open/closed (fetched once, see below) | Backtest uses the free outcome sources only |
| `HF_TOKEN` | Latest Foursquare Open Source Places (free Hugging Face account; accept the dataset terms) | Foursquare data comes from a public mirror whose newest release is Feb 2025 |
| `TFNSW_API_KEY` | Nothing yet (reserved for GTFS bus stops, not built) | Station patronage works either way: it needs no key |
| `OPENROUTER_API_KEY` | The AI analyst (any tool-calling model on OpenRouter; `OPENROUTER_MODEL` picks it, default `anthropic/claude-haiku-5.5`) | The analyst panel explains how to turn it on; everything else works |

ABS, OpenStreetMap, NSW Planning Portal and Transport for NSW station patronage need no keys.

### Google Places: fetched once, kept 30 days

Google bills every Places request. Its terms allow keeping results for 30 days and forbid redistributing them. So:

- **One request per business.** `python run.py data --only google_places` sends one Text Search for each café, gym and childcare centre mapped since 2022. On 10 Oct 2026 that was 311 requests for 316 businesses: names repeated within 60 m share one. Every field asked for bills as one "Text Search Enterprise" request, and Google gives 1,000 of those free each month.
- **Request ledger.** `data/raw/google_places/ledger.json` counts every request ever sent. A run that would take the total past `max_requests` is refused before it sends anything. That limit is 400 in `config/sources.yaml` and can't be raised above 400 there. There are no retries: a failed request stops the run, and a re-run sends only the rest.
- **No refetching.** If the processed table is under 30 days old, the adapter does nothing unless you pass `--force`. Answers are cached in `data/raw/google_places/` inside the repo (gitignored), so every machine shares them. Re-running the matching from that cache with `--force` costs nothing.
- **Never committed or packed.** The demo pack leaves Places out. After 30 days the backtest ignores the table and says how to delete it (keep `ledger.json`). The current data is usable until 9 Nov 2026.
- **Matching.** A Google result counts if it is the same business within 150 m, or has exactly the same name within 250 m. The name check is the cross-source matcher, and suburb names don't count as a match ("Cotti Coffee (Parramatta)" isn't "Crunch Fitness Parramatta"). 232 of 316 matched: 177 of 249 cafés, 38 of 45 gyms and 17 of 22 childcare centres. Google lists 209 as operational, 20 as permanently closed (13 of them still on the map) and 3 as temporarily closed.
