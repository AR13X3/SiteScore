# Demo pack

A snapshot of SiteScore's processed real data for the City of Parramatta, so a fresh clone runs on real data, offline, without the first fetch (about 40 minutes, mostly OpenStreetMap history).

- **When it's used:** on startup, any table with no data at all is restored from here, and only then does mock fill the gaps. Data you fetch yourself is never overwritten.
- **Making it:** `python run.py data --make-demo-pack` rebuilds it from your current real tables.
- **Restoring it:** `python run.py data --restore-demo-pack` loads it into empty tables.
- **What's in it:** `manifest.json` lists each table, its row count and its publication range. Every row keeps its `published_at` dating, so "as of" runs and the backtest behave exactly as they did when the pack was made.

**Not included: Google Places.** Its terms don't allow storing results for long or redistributing them. With a key, `python run.py data --only google_places` fetches your own copy.

## Sources and licences

| Table | Source | Licence |
|---|---|---|
| `areas` | ABS Census 2021 General Community Profile, ABS ASGS boundaries | CC BY 4.0 |
| `workers` | ABS Census 2021 Working Population Profile | CC BY 4.0 |
| `station_usage` | Transport for NSW, station entries and exits (station locations from OpenStreetMap) | CC BY 4.0 / ODbL 1.0 |
| `pois` | OpenStreetMap contributors, via Overpass | ODbL 1.0 |
| `poi_history` | OpenStreetMap contributors, via the OSM API | ODbL 1.0 |
| `developments` | NSW Planning Portal, online DA data | CC BY 4.0 |
| `overture_places` | Overture Maps Foundation | CDLA Permissive 2.0 (some sources ODbL) |
| `fsq_places` | Foursquare Open Source Places | Apache 2.0 |
| `business_names` | ASIC Business Names Register (data.gov.au) | CC BY 3.0 AU |

- **Attribution:** © Australian Bureau of Statistics; © State of New South Wales (Transport for NSW; Department of Planning, Housing and Infrastructure); © OpenStreetMap contributors (openstreetmap.org/copyright); Overture Maps Foundation; Foursquare Labs, Inc.; Australian Securities and Investments Commission.
- **Share-alike:** the OpenStreetMap-derived tables are a derived database under the Open Database License. If you publish them or changes to them, publish those under the ODbL too.
