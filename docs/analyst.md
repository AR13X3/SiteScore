# AI analyst

An LLM that answers location questions by running SiteScore's own tools. Turn it on with `OPENROUTER_API_KEY` in `.env`.

The analyst is a language model (through [OpenRouter](https://openrouter.ai), so any tool-calling model works) that answers location questions by **running SiteScore**, not by recalling facts. It plans an investigation, calls the model's own functions as tools, reads the results and answers with the numbers they returned. The person watches each step as it runs.

| Tool | What it runs | What it changes in the app |
|---|---|---|
| `geocode` | Address search in the region | |
| `find_spots` | The spot finder over a circle (anywhere or vacant shopfronts, by revenue or profit) | Shows the circle and ranked spots on the map |
| `simulate_sites` | 36-month simulation of 1–5 sites with 300 scenarios; optional cost overrides and `as_of` for what-ifs | |
| `inspect_site` | One site's catchments, competitors, anchors, demographics, pricing and rent | Flies the map there |
| `model_track_record` | The time-safe backtest summary | |
| `data_coverage` | Which tables are real or mock, and the known gaps | |
| `show_on_map` | | Puts the shortlist on the map, which fills the chart and why-cards |
| `write_brief` | | Adds a decision brief (verdict, key numbers, reasons, risks, checks) the user can download as Markdown |

How it stays honest:

- **Numbers come from tools.** The system prompt forbids figures, rents or competitor names that no tool returned, and says how far to trust the model (the backtest results below).
- **It sees your workspace.** Each question carries the business type, as-of date, running costs, the sites on the map and the search circle, so "why does site 2 lose?" or "stress-test my sites with higher rent" work.
- **Compact tool results.** Tools return rounded summaries (no 36-month arrays), capped in size; at most 10 model turns per question.
- **Follow-ups replay text only.** Earlier answers are sent back as plain text; tool internals are not replayed.

`POST /api/analyst/chat` streams server-sent events (`status`, `text`, `step`, `step_done`, `ui`, `error`, `done`); `GET /api/analyst/status` reports the mode: `live` (a key is set), `replay` (no key, recorded runs only) or `off`. Code is in `sitescore/analyst/`, and `tests/test_analyst.py` drives the whole loop with a scripted model, so tests never call an LLM. Each question costs a few model calls on your OpenRouter account. **If you host SiteScore publicly with a key set, anyone who can reach it spends your credit:** put it behind authentication, set a spending limit on the key in OpenRouter, or leave the key unset.

## Recorded runs (the hosted demo)

The live demo has no model key, so it can't call a language model. Instead it replays **recorded runs**: real runs of the analyst on its standard questions, saved with every event and when it arrived. A replay sends the same events in the same order (text, tool steps with their real durations, map actions, the decision brief), with long waits shortened, so a 40-second run plays in about ten. The map and model behind it stay live. The answer is tagged with its recording date. Any other question gets a card explaining how to run SiteScore locally with your own key.

Replay mode switches on by itself whenever no key is set and `data/analyst-replays/` holds recordings, including on a fresh clone. With a key set, recordings are ignored.

```bash
python -m sitescore.analyst.replay record      # re-record the standard questions (needs a key; a few cents)
python -m sitescore.analyst.replay record "Where should I open a café near Rosehill?"
python -m sitescore.analyst.replay list
```

The numbers in a recording are from its recording date. Re-record after a data refresh or a model change, so the demo's answers match what the model says now.
