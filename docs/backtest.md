# Backtest: how accurate is SiteScore?

SiteScore is tested the hard way: each real opening is predicted using only data published before it opened, then compared with what happened. Results are reported as they are, including where the model doesn't beat a naive baseline.

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

## Which layers help? (layer by layer)

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

## Cross-section: today's cafés (NOT time-safe)

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
