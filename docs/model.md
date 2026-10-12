# How the model works

Each layer is a separate module in [`sitescore/model/`](../sitescore/model/) with its own tests. Every assumption is in [`config/`](../config/).

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

## Site-specific rent

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

## Uncertainty bands

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

## Known limitations

- Absolute dollar figures depend on spend assumptions in YAML. The backtest validates the **ranking** of sites, not absolute revenue.
- Walking distance is straight-line distance × a detour factor (1.3). Using the OSM walking network is a planned upgrade.
- Workers are only published down to SA2. Within an SA2 they are spread over commercial, industrial, education and health mesh blocks.
- OSM was less complete in earlier years, so historical competitor counts are slightly low.
