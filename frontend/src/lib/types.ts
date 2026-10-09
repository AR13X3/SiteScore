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

export interface SiteResult {
  site: Site;
  business_type: string;
  as_of: string;
  monthly_visits: number;
  monthly_revenue: number;
  monthly_profit: number | null;
  avg_transaction_value: number;
  segment_visits: Record<string, number>;
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
  note: string;
  model_visible: boolean;
}
