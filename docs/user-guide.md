# Using the app

Start the app with `python run.py start` and open http://127.0.0.1:8000. There are four screens in the top bar; the button at the top right switches between light, dark and system theme.

![The Workspace](images/workspace.png)

- **Overview:** what SiteScore covers (live from the data), a box to ask the analyst straight away, and how the model works.
- **Workspace:** three columns, with the business type and **Data as of** date in the header.
  - **Left, Sites:** up to 5 candidates, added by address search, by clicking the map, or with **Load 3 demo sites**. Each card shows 36-month revenue and its P10–P90 range on one scale shared by every card; the selected card is highlighted. Rename sites on their card. **Find spots** switches this column to the spot finder: place a circle and get the best places inside it, vacant shopfronts or anywhere on a shopping strip, ranked by revenue or profit (see [Finding the best spots](spot-finder.md)).
  - **Centre, map:** drag pins to adjust them. The selected site shows its walking catchments for residents, workers and commuters, its competitors (sized by the share of demand they take) and nearby anchors such as supermarkets, stations and schools.
  - **Right, Details:** the selected site's 36-month revenue and profit with ranges, mature month, estimated rent, chance of being best and chance of a loss; how each layer compares with the average candidate; and each layer's explanation. Buttons remove it, search around it, or ask the analyst about it.
  - **Right, Analyst:** ask in plain words ("best café spot within 1 km of Parramatta station, by profit"). It runs the model for you, shows each step as it runs, puts its shortlist on the map, and writes a downloadable decision brief. See [AI analyst](analyst.md).
  - **Right, Costs:** rent of a typical site, wages, cost of goods and other costs. They drive profit, break-even and each site's chance of a 36-month loss; each site's own rent is estimated from them (see [Site-specific rent](model.md#site-specific-rent)).

  Below the columns: a 36-month chart with P10–P90 bands, switchable between **revenue** and **profit**, and a comparison table of every site. **Data as of** runs the model as it would have looked on a past date, using only data published by then (from 12 Oct 2022, when the last Census release came out).
![The analyst at work: step timeline and decision brief](images/analyst.png)

- **Evidence:** the time-safe backtest, with a cohort map and the opening check, closures by predicted third, a "which layers help?" dot plot with 90% intervals, and a predicted-vs-actual table where each café expands to show its evidence. Another switch shows **today's cafés** (the cross-section), clearly marked as not time-safe.
- **Data:** every table the model reads (real or mock, rows, publication dates), the outcome tables only the backtest reads, sources and licences, and the data contributions that would help most.

The badge in the top bar shows whether the results use real or mock data; click it for the Data page.

![The Evidence screen](images/evidence.png)

![The Data screen](images/data.png)
