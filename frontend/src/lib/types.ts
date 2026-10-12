// Mirrors the API's response models (sitescore/model/types.py).

export interface Site {
  id: string;
  label: string;
  lat: number;
  lon: number;
}

/** A site on the map; `slot` fixes its colour for as long as it exists. */
export interface CandidateSite extends Site {
  slot: number;
}

export interface Layer {
  key: string;
  label: string;
  factor: number;
  unit: string;
  summary: string;
  details: Record<string, unknown>;
}

export interface DataUsed {
  table: string;
  provenance: string;
  rows: number;
  version: string | null;
  latest_published: string | null;
}

export interface RentEstimate {
  monthly: number;
  base: number;
  index: number;
  footfall_index: number;
  area_index: number;
  summary: string;
}

export interface SiteResult {
  site: Site;
  business_type: string;
  as_of: string;
  monthly_visits: number;
  monthly_revenue: number;
  monthly_profit: number | null;
  avg_transaction_value: number;
  segment_visits: Record<string, number>;
  rent?: RentEstimate | null;
  layers: Layer[];
  data_used: DataUsed[];
}

export interface MonthPoint {
  month: string;
  revenue: number;
  visits: number;
  profit: number | null;
  development_revenue: number;
}

export interface SiteSimulation {
  site: Site;
  mature: SiteResult;
  months: MonthPoint[];
  total_revenue: number;
  total_profit: number | null;
  dynamics: Layer;
}

export interface Contribution {
  key: string;
  label: string;
  ratio: number;
  pct_effect: number;
  dollars: number;
}

export interface SiteExplanation {
  site_id: string;
  rank: number;
  total_revenue: number;
  vs_average_pct: number;
  headline: string;
  contributions: Contribution[];
}

export interface Band {
  p10: number[];
  p50: number[];
  p90: number[];
}

export interface Range3 {
  p10: number;
  p50: number;
  p90: number;
}

export interface SiteUncertainty {
  site_id: string;
  revenue: Band;
  total_revenue: Range3;
  total_profit: Range3 | null;
  prob_best: number;
  prob_loss: number | null;
}

export interface ParameterRange {
  path: string;
  base: number;
  p10: number;
  p90: number;
}

export interface Uncertainty {
  n_runs: number;
  mode: string;
  seed: number;
  percentiles: number[];
  parameters: ParameterRange[];
  sites: SiteUncertainty[];
}

export interface SimulationResult {
  business_type: string;
  as_of: string;
  open_date: string;
  horizon_months: number;
  baseline_total_revenue: number;
  sites: SiteSimulation[];
  ranking: string[];
  explanations: SiteExplanation[];
  data_used: DataUsed[];
  uncertainty: Uncertainty | null;
}

export interface BusinessType {
  id: string;
  name: string;
  description: string;
  status: "ready" | "draft";
}

export interface Region {
  id: string;
  name: string;
  bbox: [number, number, number, number];
  map: { center: [number, number]; zoom: number };
}

export interface TableStatus {
  table: string;
  source: string;
  description: string;
  provenance: "real" | "mock" | null;
  rows: number | null;
  published_range: [string, string] | null;
  note: string;
  model_visible: boolean;
}

export interface SourceInfo {
  id: string;
  title: string;
  provider: string;
  licence: string;
  used_for: string;
  needs_key: boolean;
  key_configured: boolean | null;
}

export interface Costs {
  rent_per_month: number;
  wages_per_month: number;
  cogs_share: number;
  other_fixed_per_month: number;
}

export interface AsOfRange {
  min: string;
  max: string;
}

export interface GeocodeHit {
  label: string;
  lat: number;
  lon: number;
}

// --- Backtest (sitescore/backtest/types.py) ------------------------------------------

export interface Evidence {
  source: string;
  open: boolean;
  weight: number;
  detail: string;
  as_of: string | null;
}

export type HorizonStatus = "closed" | "survived" | "censored" | "unknown";

export interface Horizon {
  status: HorizonStatus;
  horizon: string;
  closed_on: string | null;
  kind: string | null;
  failure: string | null;
  last_seen_trading: string | null;
  detail: string;
  site_closures: number;
  site_closures_before: number;
}

export interface Actual {
  still_open: boolean | null;
  status_source: string;
  survival_score: number | null;
  evidence: Evidence[];
  months_open: number;
  reviews_per_month: number | null;
  rating: number | null;
  hours_change: number | null;
  notes: string[];
  horizon: Horizon | null;
}

export interface BacktestRow {
  name: string;
  osm_id: string;
  lat: number;
  lon: number;
  opened: string;
  opened_note: string;
  opening_check: string;
  opening_detail: string;
  as_of: string;
  data_cutoff: string | null;
  predicted_score: number;
  predicted_rank: number;
  mature_monthly: number;
  demand_only: number;
  layers: Record<string, number>;
  actual: Actual;
  actual_score: number | null;
  actual_rank: number | null;
}

export interface Accuracy {
  n: number;
  pairwise_accuracy: number | null;
  pairs: number;
  spearman: number | null;
  top_third_actual_percentile: number | null;
  bottom_third_actual_percentile: number | null;
  baseline_pairwise_accuracy: number | null;
  baseline_spearman: number | null;
}

export interface ThirdRow {
  third: "top" | "middle" | "bottom";
  n: number;
  judged: number;
  closed: number;
  closure_rate: number | null;
  site_failures: number;
  operator_failures: number;
  mean_site_closures: number | null;
}

export interface SurvivalReport {
  horizon_months: number;
  status_counts: Record<HorizonStatus, number>;
  closure_kinds: Record<string, number>;
  auc: number | null;
  baseline_auc: number | null;
  by_third: ThirdRow[];
  baseline_by_third: ThirdRow[];
  site_churn_auc: number | null;
  baseline_site_churn_auc: number | null;
}

export interface LadderStep {
  key: string;
  label: string;
  n: number;
  pairs: number;
  pairwise_accuracy: number | null;
  spearman: number | null;
  spearman_ci: [number, number] | null;
  gain_ci: [number, number] | null;
}

export interface OutcomeComparison {
  outcome: string;
  label: string;
  available: boolean;
  note: string;
  steps: LadderStep[];
}

export interface Skipped {
  name: string;
  reason: string;
}

export interface BacktestResult {
  cohort: string;
  business_type: string;
  run_on: string;
  score_months: number;
  rows: BacktestRow[];
  accuracy: Accuracy;
  survival: SurvivalReport;
  ladder: OutcomeComparison[];
  opening_checks: Record<string, number>;
  skipped: Skipped[];
  provenance: Record<string, string | null>;
  outcome_sources: string[];
  caveats: string[];
}

export interface CrossSectionRow {
  name: string;
  osm_id: string;
  lat: number;
  lon: number;
  first_mapped: string | null;
  predicted_rank: number;
  mature_monthly: number;
  layers: Record<string, number>;
  reviews: number | null;
  reviews_per_month: number | null;
  rating: number | null;
  age_months: number | null;
  site_closures: number;
  google_status: string | null;
}

export interface CrossSectionResult {
  business_type: string;
  run_on: string;
  as_of: string;
  time_safe: boolean;
  n: number;
  rows: CrossSectionRow[];
  outcomes: OutcomeComparison[];
  provenance: Record<string, string | null>;
  caveats: string[];
}

export interface Cohort {
  id: string;
  label: string;
}

/** The full business profile (GET /api/business-types/{id}); only what the UI reads. */
export interface BusinessProfile {
  id: string;
  name: string;
  costs: Costs | null;
}

// --- Spot finder (sitescore/api/routes_search.py) ------------------------------------

export type SearchWhere = "anywhere" | "vacant";
export type RankBy = "revenue" | "profit";

export interface SearchRequest {
  business_type: string;
  lat: number;
  lon: number;
  radius_m: number;
  where: SearchWhere;
  retail_only: boolean;
  rank_by: RankBy;
  as_of?: string;
  costs?: Costs;
}

export interface Spot {
  id: string;
  label: string;
  kind: string;
  former_use: string;
  lat: number;
  lon: number;
  rank: number;
  total_revenue: number;
  total_profit: number | null;
  mature_monthly: number;
  revenue_range: [number, number] | null;
  profit_range: [number, number] | null;
  prob_loss: number | null;
  prob_best: number | null;
  headline: string;
  quick_monthly: number;
  rent_monthly: number | null;
}

export interface GridPoint {
  lat: number;
  lon: number;
  quick_monthly: number;
}

export interface Vacancy {
  id: string;
  lat: number;
  lon: number;
  label: string;
  kind: string;
  former_use: string;
}

export interface SearchResult {
  where: SearchWhere;
  rank_by: RankBy;
  as_of: string;
  open_date: string | null;
  lat: number;
  lon: number;
  radius_m: number;
  n_candidates: number;
  n_shortlisted: number;
  spots: Spot[];
  grid: GridPoint[];
  vacancies: Vacancy[];
  notes: string[];
}
