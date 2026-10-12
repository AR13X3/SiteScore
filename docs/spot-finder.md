# Finding the best spots

The spot finder searches an area for the best places to open.

The **Find spots** tab in the Workspace searches an area for you (the AI analyst can run it too). Click the map to centre a circle (250 m to 3 km), choose where to look, and SiteScore ranks the best places inside it. It's also available as `POST /api/search`.

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
