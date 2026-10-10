# SiteScore

**Pick a business type and 2–5 candidate addresses. SiteScore simulates each site and projects monthly revenue over 36 months, with P10/P50/P90 bands, and explains why each site wins or loses.**

Built at Hack48 Sydney. The first region is the City of Parramatta and the first business type is café. Gym and childcare are drafts, defined in config only.

## Quick start

Requires Python 3.11+ and Node.js 20+.

```bash
python run.py install    # one-time: virtualenv, dependencies, frontend build
python run.py start      # opens http://127.0.0.1:8000 (--port to change it)
```

A fresh clone runs on **real data straight away, offline**: the repo includes a demo pack (`data/demo-pack/`, a 3 MB snapshot from 10 Oct 2026 of every real table except Google Places), which is loaded on first start. `python run.py data` refreshes everything from the sources.

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

- **Running costs:** the rent, wages, cost-of-goods and other-cost inputs drive profit, break-even and each site's chance of a 36-month loss. The defaults come from the business profile, and changes are sent to the model as overrides. The rent input is the rent of a typical site; each site's own rent is estimated from it (see [Site-specific rent](#site-specific-rent)).
- **Data as of:** run the model as it would have looked on a past date. Only data published by then is used, from 12 Oct 2022 (when the last Census release came out) to today.
- **Find spots:** draw a circle on the map and get the best places inside it, either vacant shopfronts or anywhere on a shopping strip, ranked by revenue or profit (see [Finding the best spots](#finding-the-best-spots)).
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
| `python run.py data` | Fetch and process all data sources. Any source that fails falls back to mock data. With a Google key this includes Google Places (guarded, see [Google Places](#google-places-fetched-once-kept-30-days)). |
| `python run.py data --only google_places` | Fetch Google Places only. Within 30 days of a fetch it does nothing unless you add `--force` (which re-matches from the cache) |
| `python run.py test` | Run the test suite |
| `cd frontend && npm test` | Frontend logic tests (Node's built-in runner, no extra packages) |
| `python run.py backtest` | Predict past openings with past data and score them against reality |
| `python run.py backtest --cross-section` | Score every café open today with today's data (not time-safe) |
| `python run.py dev` | Backend and frontend with hot reload |
| `python run.py data --make-demo-pack` | Snapshot your current real tables into `data/demo-pack/` (to commit) |

If the repo is inside OneDrive or Dropbox, the virtualenv and raw downloads go to `%LOCALAPPDATA%\SiteScore` instead, so you don't sync about 1 GB of packages. Set `SITESCORE_CACHE_DIR` to choose another location.

## API keys (`.env`)

All keys are optional. `install` creates `.env` from `.env.example`.

| Key | Needed for | Without it |
|---|---|---|
| `GOOGLE_PLACES_API_KEY` | Backtest ground truth: rating, review count, open/closed (fetched once, see below) | Backtest uses the free outcome sources only |
| `HF_TOKEN` | Latest Foursquare Open Source Places (free Hugging Face account; accept the dataset terms) | Foursquare data comes from a public mirror whose newest release is Feb 2025 |
| `TFNSW_API_KEY` | Nothing yet (reserved for GTFS bus stops, not built) | Station patronage works either way: it needs no key |

ABS, OpenStreetMap, NSW Planning Portal and Transport for NSW station patronage need no keys.

### Google Places: fetched once, kept 30 days

Google bills every Places request. Its terms allow keeping results for 30 days and forbid redistributing them. So:

- **One request per business.** `python run.py data --only google_places` sends one Text Search for each café, gym and childcare centre mapped since 2022. On 10 Oct 2026 that was 311 requests for 316 businesses: names repeated within 60 m share one. Every field asked for bills as one "Text Search Enterprise" request, and Google gives 1,000 of those free each month.
- **Request ledger.** `data/raw/google_places/ledger.json` counts every request ever sent. A run that would take the total past `max_requests` is refused before it sends anything. That limit is 400 in `config/sources.yaml` and can't be raised above 400 there. There are no retries: a failed request stops the run, and a re-run sends only the rest.
- **No refetching.** If the processed table is under 30 days old, the adapter does nothing unless you pass `--force`. Answers are cached in `data/raw/google_places/` inside the repo (gitignored), so every machine shares them. Re-running the matching from that cache with `--force` costs nothing.
- **Never committed or packed.** The demo pack leaves Places out. After 30 days the backtest ignores the table and says how to delete it (keep `ledger.json`). The current data is usable until 9 Nov 2026.
- **Matching.** A Google result counts if it is the same business within 150 m, or has exactly the same name within 250 m. The name check is the cross-source matcher, and suburb names don't count as a match ("Cotti Coffee (Parramatta)" isn't "Crunch Fitness Parramatta"). 232 of 316 matched: 177 of 249 cafés, 38 of 45 gyms and 17 of 22 childcare centres. Google lists 209 as operational, 20 as permanently closed (13 of them still on the map) and 3 as temporarily closed.

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

- **First start with no data:** the app loads the demo pack (real data). It generates mock only for tables the pack doesn't have, such as Google Places.
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

### Site-specific rent

There's no open data on commercial asking rents, so each site's rent is an index on the business profile's `rent_per_month`, which is now the rent of a **typical** site:

```
rent = rent_per_month × (foot traffic / typical)^0.5 × (local residential rent / regional)^0.5
```

The index is clipped to 0.5–2.5×.

- **Foot traffic:** people within walking reach of the site, weighted by how much they're around when the business trades, times the anchor boost. It deliberately leaves out participation, so rent doesn't move with assumptions about who buys coffee. "Typical" is the median at the places where this kind of business already trades.
- **Local rents:** the Census 2021 median weekly rent, population-weighted within 800 m, compared with the median across the market. It stands in for land values.
- **The idea:** landlords price shopfronts by passing trade.

For example, Church St CBD gets 3× typical foot traffic and is estimated at $11.7k a month, Epping at $10.5k, and suburban Carlingford at $5.1k. That's roughly the 2–3× gap between prime and suburban retail rents, but nothing calibrates it yet.

Rent changes profit, break-even, the chance of a loss (Monte Carlo), the spot finder's profit ranking, and an extra "profit after site-specific rent" rung in the backtest's "which layers help?" comparison. The elasticities, radius and range are assumptions, set in `config/model.yaml` under `rent`. Better sources would replace them:

- **NSW Valuer General bulk land values:** free, CC BY 4.0, monthly CSVs per council. The site blocks automated downloads, though, so someone has to download a file in a browser first.
- **Real asking rents:** from a listings API such as Domain's (needs an account).

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

## Finding the best spots

The **Find spots** tab on the Compare screen searches an area for you. Click the map to centre a circle (250 m to 3 km), choose where to look, and SiteScore ranks the best places inside it. It's also available as `POST /api/search`.

- **Look at:**
  - **Vacant shopfronts:** empty shops mapped on OpenStreetMap, tagged `shop=vacant` or with a former use such as `disused:amenity=cafe`. Mappers often tag these after seeing a "for lease" sign. Former cafés are flagged, since a fit-out is likely.
  - **Anywhere:** a grid over the circle, by default only along shopping strips, meaning within 150 m of where similar businesses already trade. Schools and hospitals don't count.
- **How it ranks:**
  1. Every candidate gets a quick score: the model with the agents and the price game off, about 2 ms each.
  2. The best 12, kept at least 150 m apart so suggestions don't pile onto one corner, re-run through the full model over 36 months.
  3. The top 5 get Monte Carlo ranges and a chance of a loss.
  4. Any result can be added to the comparison, or "Compare the top 3" adds three at once.
- **Speed:** about 3–9 s per search; the dense CBD is the slowest. In three test areas, the full model's top 5 were always the quick score's top 5 (Spearman 0.88–0.99), so the shortlist of 12 leaves a wide margin.
- **Revenue or profit:** ranking by profit uses each spot's estimated rent, so a busy corner with a high rent can rank below a quieter, cheaper one. In a 3 km search around the CBD, the spot by Parramatta station (about $17k a month) drops out of the profit top 5 in favour of a cheaper strip.
- **Limits:**
  - Vacant shopfronts are leads to check, not listings: coverage depends on local mappers, and there's no rent, size or agent.
  - A vacancy is only known from the day it was fetched, so a run "as of" an earlier date sees none.
  - Real listings would need an API account such as Domain's commercial listings search.
  - Settings are in `config/model.yaml` under `search`.

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
     | survived | it was still trading after the mark: a mapper edited or checked it then, or it is still on the map **and** an independent listing confirms it after the mark (Google operational, Foursquare refreshed, Overture with confidence ≥ 0.75). Listings lag, so they only count while no source has recorded a closure. |
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
     | Google (with key) | Operational or permanently closed | 3.0 |

     Older data counts for less: weights halve every 12 months since the data was collected.
   - change in weekly opening hours
   - with a Google Places key: reviews per month since opening, and rating. This is the main performance measure. Survival is secondary. A café Google lists as permanently closed is judged on its closure: its reviews stopped when it closed.
5. **Accuracy,** always compared with a naive "foot traffic only" baseline:
   - share of pairs ranked correctly (50% = coin flip) and Spearman correlation, against the combined actual-performance score. That score is a weighted mean of standardised reviews per month (1.0), rating (0.5), the "still trading" verdict (0.5: open +1, closed −1) and the change in opening hours (0.5). It uses the vote's verdict, not its margin, because the margin mostly says how many sources know a café.
   - top-third vs bottom-third actual percentile
   - for survival: AUC (survivors above closures), closure rate by predicted third, and whether spots without café closures are predicted above spots with them

**Real Parramatta results (10 Oct 2026, with Google Places):**

Discovery found 56 cafés first mapped from Nov 2022 to Dec 2024. The opening check rejected 27 of them:
- 26 were older cafés mapped late (e.g. Three Beans and Nadia's, both on Foursquare since 2010)
- 1 had only been redrawn (Gatehouse Tea Rooms)

That leaves 29 cafés: 18 confirmed new (8 of them took over another café's spot) and 11 unverified. Google matched 26 of them (not Quattro, Mehry's Cafe or Cafe W). Two of those 26 are permanently closed, so the review measures cover 24 cafés.

| Measure | Model | Foot traffic only |
|---|---|---|
| Closed within 18 months | **none of 29** (25 survived, 4 unknown) | |
| Still trading today | 27 of 29. Yellow Stage Eastwood and Chaffee House have closed; both closures were recorded after their 18-month mark | |
| Google reviews per month since opening, Spearman (24 cafés) | 0.23 [−0.15, 0.57] | 0.08 [−0.27, 0.39] |
| Google review count (log), Spearman (24 cafés) | 0.33 [−0.08, 0.64] | 0.18 [−0.16, 0.48] |
| Combined actual-performance score: pairs ranked correctly, Spearman | 60%, 0.28 | 58%, 0.22 |
| Café closures at the same spot since 2019, mean per café, top / middle / bottom predicted third | 0.10 / 0.40 / 0.44 | 0.30 / 0.20 / 0.44 |
| Spots without closures predicted above spots with them (AUC) | 0.70 | 0.55 |

**What this does and doesn't show:**
- **The model points the right way on reviews, but 24 cafés can't show it's real.** The full model beats foot traffic by about 0.15 on both review measures. The gain's 90% interval runs from about −0.15 to +0.45, so every gain interval includes zero.
- **Still no survival signal.** None of the genuinely new cafés closed within 18 months. Google's "operational" moved 6 cafés from unknown to survived. Chaffee House went the other way: Google says it has closed, and only a lagging Overture listing had said it traded past the mark.
- **The site-churn hint is unchanged.** The model ranks spots where a café closed before lower than the baseline does (AUC 0.70 vs 0.55). But the 8 spots with any closure are exactly the 8 takeover openings, and those predecessors' closures were knowable before opening. It's 8 cafés against 21: a hint, not evidence.
- **The two earlier "closures" weren't 18-month closures.** Koko 'n' Beans and Mulberry Tree were older cafés: Foursquare listed them from 2014 and 2016.

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
- still trading per Google: cafés still on the map that Google lists as permanently closed, against open ones (these are left out of the review outcomes)
- site churn

The sample is about six times the genuine openings. But it is **not time-safe**: today's map already reflects which cafés succeeded (rivals cluster near busy spots, and weak cafés have closed), so it measures association, not prediction. The report and the API mark it `time_safe: false`.

**Results (10 Oct 2026, with Google).** Google matched 144 of the 186 cafés: 131 operational, 12 permanently closed and 1 temporarily closed. Spearman with each outcome, with 90% intervals for the baseline and the full model:

| Rung | Reviews per month (132) | Review count, log (132) | Still trading per Google (143, 12 closed) | Fewer closures at the spot (186) |
|---|---|---|---|---|
| Foot traffic only | 0.06 [−0.08, 0.19] | 0.03 [−0.12, 0.16] | −0.08 [−0.24, 0.09] | 0.03 [−0.06, 0.13] |
| + fit and anchors | 0.06 | 0.04 | −0.07 | 0.03 |
| + competition (Huff) | 0.09 | 0.07 | 0.12 [−0.01, 0.24] | 0.08 |
| + customer agents | 0.09 | 0.07 | 0.10 | 0.07 |
| + price response | 0.09 | 0.08 | 0.10 | 0.07 |
| Full model | 0.08 [−0.07, 0.22] | 0.06 [−0.09, 0.21] | 0.06 [−0.08, 0.20] | 0.08 [−0.05, 0.20] |

The time-safe backtest on the same outcomes:

| Rung | Reviews per month (24) | Review count, log (24) | Fewer closures at the spot (29) |
|---|---|---|---|
| Foot traffic only | 0.08 [−0.27, 0.39] | 0.18 [−0.16, 0.48] | 0.09 [−0.24, 0.36] |
| + fit and anchors | 0.09 | 0.18 | 0.14 |
| + competition (Huff) | 0.14 | 0.22 | 0.39 [0.11, 0.62] |
| + customer agents | 0.18 | 0.27 | 0.35 |
| + price response | 0.20 | 0.29 | 0.35 |
| Full model | 0.23 [−0.15, 0.57] | 0.33 [−0.08, 0.64] | 0.27 [−0.01, 0.51] |

**What it shows:**
- **No layer beats foot traffic convincingly on reviews.** In the time-safe cohort, the full model leads foot traffic by about 0.15, but on 24 cafés that gain's interval includes zero. In the six-times-larger cross-section, no rung relates to reviews at all: every Spearman is under 0.1. The bigger sample doesn't back up the small one.
- **One lead: competition and closures.** The 12 cafés Google lists as permanently closed sit at busy but crowded spots: their median competition factor is 0.033, against 0.078 for open cafés. Foot traffic alone ranks them slightly *above* open cafés (−0.08). Adding Huff competition reverses that (0.12), a gain of [+0.10, +0.29]. That's the only gain interval in either analysis that clears zero. Don't read much into it:
  - there are only 12 closures, and 3 of them are in one CBD block
  - it's not time-safe
  - the rung's own correlation interval still includes zero
  - 4 outcomes × 6 rungs × 2 analyses were compared, so one 90% interval clearing zero is about what chance gives

  It's worth re-testing on new closures.
- **Reviews may be a poor revenue proxy for grab-and-go cafés.** Three of the model's top five in the cross-section have 0.4 to 2.6 reviews a month: a hospital café (Westend Coffee, Westmead Hospital), a station bakery (Eastern Concourse Bakery Cafe, Parramatta Station) and Coco Lane Cafe by Westfield. Reviews follow sit-down "destination" cafés more than takings. Real sales figures would settle what reviews can't.
- **Site churn:** no gain clears the noise. In the small cohort competition looks helpful, but that's its 8 takeover spots, and the effect disappears in the cross-section.

On the mock city, where reviews come from a known "true" performance, the same pipeline recovers the planted signal (Spearman ≈ 0.36 with reviews per month). So the comparison works; on real data, reviews don't show a model signal.


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
data/demo-pack/  snapshot of the processed real data (loaded on a fresh clone)
data/raw/        Google Places cache and request ledger (gitignored, never committed)
tests/
```

## Known limitations

- Absolute dollar figures depend on spend assumptions in YAML. The backtest validates the **ranking** of sites, not absolute revenue.
- Walking distance is straight-line distance × a detour factor (1.3). Using the OSM walking network is a planned upgrade.
- Workers are only published down to SA2. Within an SA2 they are spread over commercial, industrial, education and health mesh blocks.
- OSM was less complete in earlier years, so historical competitor counts are slightly low.
