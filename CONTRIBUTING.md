# Contributing to SiteScore

Thanks for helping. SiteScore models one council (City of Parramatta) and one business type (café) well. Most of what would make it better is **data**, not code.

## Help train SiteScore

The model's structure comes from open data, but the parameters that turn customers into dollars (spend per visit, how often people buy, how far they walk, how rent scales) are hand-set assumptions in `config/`. Today they are only *tested* against real openings. With enough outcome data we can *fit* them to reality: that is the training step, and it is the most valuable contribution you can make.

| Data | Why it matters | Share it via |
|---|---|---|
| Opening dates (name, address or coordinates, month opened) | More real openings to predict: a sharper test and the evidence to fit parameters | [Data contribution issue](https://github.com/AR13X3/SiteScore/issues/new?template=data-contribution.yml), or a CSV in `backtests/cohorts/` (see below) |
| Monthly sales or foot counts, anonymised | Ground truth for spend and participation: the biggest single improvement | [Data contribution issue](https://github.com/AR13X3/SiteScore/issues/new?template=data-contribution.yml); we agree a private, anonymised format before anything is shared |
| Commercial rents or lease prices | Calibrates the rent model, which today is an index | [Data contribution issue](https://github.com/AR13X3/SiteScore/issues/new?template=data-contribution.yml) |
| Closures you know about, with dates | Survival is the hardest outcome to observe from public data | [Data contribution issue](https://github.com/AR13X3/SiteScore/issues/new?template=data-contribution.yml) |

**How contributed data is handled**

- Only data you have the right to share. Say where it comes from and its licence.
- Business-level figures (sales, rents) are never committed as-is: they are aggregated or anonymised first, and only with your agreement.
- No personal information, and nothing whose terms forbid redistribution (for example Google Places results, which stay in a gitignored local cache).
- Every change to the model's parameters is reported with before and after backtest numbers, including when it doesn't help.

The app's **Data** page shows what feeds the model right now and the most wanted contributions.

## Set up

Requires Python 3.11+ and Node.js 20+ (22.18+ to run the frontend tests, which use Node's built-in TypeScript support).

```bash
python run.py install    # virtualenv, dependencies, frontend build
python run.py start      # http://127.0.0.1:8000, runs offline on the bundled demo pack
python run.py test       # backend tests (mock data, no network, no keys)
cd frontend && npm test  # frontend logic tests
python run.py dev        # backend + frontend with hot reload while you work
```

No API keys are needed to develop. Tests blank every key, and every data source has a mock with identical columns.

## Ways to contribute

### 1. Add a business type (easy)

A business type is one YAML file in `config/business_types/`. Copy `cafe.yaml` and change:

- `competitors` and `anchors`: OpenStreetMap tags for rivals and traffic generators
- `segments`: how residents, workers and commuters use this kind of business
- `fit`: which demographics help, with weights
- `spend`, `pricing` and `costs`: per-visit spend and running costs (cite your source in a comment)
- `status: draft` until someone has checked the assumptions

No code changes are needed. `python run.py test` validates every profile.

### 2. Add a region (medium)

Copy `config/regions/parramatta.yaml` to `config/regions/<id>.yaml` and set:

- `lga_code`: the ABS LGA code (ASGS 2021)
- `bbox` and `map`: the area and the map's starting view
- `planning_portal.council_names`: the council's name in the NSW Planning Portal (outside NSW, the DA adapter falls back to mock until someone adds your state's source)
- `place_words`: suburb names, so matching business names across sources ignores them

Then run with `SITESCORE_REGION=<id>` in `.env` and `python run.py data`. Census, OpenStreetMap and boundaries are national. Station patronage and DA data are NSW sources; outside NSW, add adapters for your state's equivalents or let them fall back to mock while you work.

### 3. Add ground truth (easy, high value)

- **Known openings:** add a CSV to `backtests/cohorts/` with `name,opened,lat,lon` (opened as `YYYY-MM`). Run `python run.py backtest --cohort <name>` (the file name without `.csv`).
- **Sales figures:** even a few businesses' monthly takings, anonymised, would test the model far better than Google reviews can. Open an issue first so we can agree how to store them without identifying anyone.
- **Commercial rents:** asking rents or NSW Valuer General land values would calibrate `sitescore/model/rent.py`, which today is an index on a typical-site rent.

### 4. Add a data source (medium)

Each source is an adapter in `sitescore/pipeline/` (see `base.py`):

```python
class MySource(Adapter):
    source_id = "my_source"          # key in config/sources.yaml
    tables = ("my_table",)           # declared in sitescore/datastore/schema.py

    def fetch(self, ctx):            # download and process the real data
        ...
        return {"my_table": stamp(df, published_at=..., valid_from=...)}

    def mock(self, ctx):             # same columns, same dating, synthetic values
        ...
```

Rules that keep the model honest:

1. **Date every row by when it became public** (`published_at`), not only when it was true. The model runs "as of" past dates and must never see data that didn't exist yet.
2. **Model code reads data only through `AsOfView`.** `tests/test_architecture.py` fails if a model module touches files or the store directly.
3. **Outcome data is never a model input.** Tables used to score the backtest are marked `model_visible: False`.
4. **Always provide a mock.** A failed fetch falls back to it, so the app never breaks.
5. Record the source, licence and publication rule in `config/sources.yaml`.

### 5. Improve the AI analyst

The analyst (`sitescore/analyst/`) is an LLM that calls SiteScore's own functions as tools via OpenRouter. To add a tool, add a `tool_<name>` method to `Toolbox` in `tools.py`, its schema to `TOOL_SPECS`, and a label in `step_label`. Tools must return compact, rounded numbers (no 36-month arrays) and every number the analyst quotes must come from a tool. `tests/test_analyst.py` uses a scripted model, so tests never call an LLM.

### 6. Frontend

React + TypeScript + Leaflet + ECharts in `frontend/`. Design tokens are CSS variables at the top of `src/styles.css`, with light and dark themes. Keep pure logic in `src/lib/*.ts` with a `*.test.ts` beside it.

## Pull requests

- One topic per PR. Say where any data comes from and its licence.
- `python run.py test` and `cd frontend && npm test` pass; `ruff check sitescore tests` is clean.
- If a change moves backtest results, include the before and after numbers. Results that don't improve are still worth reporting.

## Data licences

Code is MIT (see `LICENSE`). Data keeps its own licence: ABS and Transport for NSW data are CC BY 4.0, OpenStreetMap data is © OpenStreetMap contributors under the ODbL. Don't commit data whose terms forbid redistribution (for example, Google Places results: they stay in the gitignored cache).
