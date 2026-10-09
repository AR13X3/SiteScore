import type {
  AsOfRange,
  BacktestResult,
  BusinessProfile,
  BusinessType,
  Cohort,
  Costs,
  CrossSectionResult,
  GeocodeHit,
  Region,
  SearchRequest,
  SearchResult,
  SimulationResult,
  Site,
  TableStatus,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // keep the status line
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export interface SimulateRequest {
  business_type: string;
  sites: Site[];
  as_of?: string;
  open_date?: string;
  uncertainty?: boolean;
  costs?: Costs;
}

export const api = {
  region: () => request<Region>("/api/region"),
  businessTypes: () => request<BusinessType[]>("/api/business-types"),
  businessProfile: (id: string) => request<BusinessProfile>(`/api/business-types/${encodeURIComponent(id)}`),
  dataStatus: () => request<TableStatus[]>("/api/data/status"),
  asOfRange: () => request<AsOfRange>("/api/data/as-of-range"),
  geocode: (q: string, signal?: AbortSignal) =>
    request<GeocodeHit[]>(`/api/geocode?q=${encodeURIComponent(q)}`, { signal }),
  simulate: (body: SimulateRequest) =>
    request<SimulationResult>("/api/simulate", { method: "POST", body: JSON.stringify(body) }),
  search: (body: SearchRequest) =>
    request<SearchResult>("/api/search", { method: "POST", body: JSON.stringify(body) }),
  cohorts: () => request<Cohort[]>("/api/backtest/cohorts"),
  backtest: (cohort: string, businessType: string) =>
    request<BacktestResult>("/api/backtest", {
      method: "POST",
      body: JSON.stringify({ cohort, business_type: businessType }),
    }),
  crossSection: (businessType: string) =>
    request<CrossSectionResult>(`/api/backtest/cross-section?business_type=${encodeURIComponent(businessType)}`),
};
