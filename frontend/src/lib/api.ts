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
  SourceInfo,
  TableStatus,
} from "./types";
import type { AnalystStatus } from "./analyst";
import type { Heatmap } from "./heat";

/** Every finished API call, for the status strip: which endpoint, how long, did it work. */
export interface ApiCall {
  endpoint: string;
  ms: number;
  ok: boolean;
}
export const API_EVENT = "sitescore:api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const t0 = performance.now();
  const report = (ok: boolean) =>
    window.dispatchEvent(new CustomEvent<ApiCall>(API_EVENT, {
      detail: { endpoint: path.replace(/^\/api\//, "").split("?")[0], ms: performance.now() - t0, ok },
    }));
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (e) {
    if ((e as Error).name !== "AbortError") report(false); // a superseded search isn't a failure
    throw e;
  }
  report(res.ok);
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
  sources: () => request<SourceInfo[]>("/api/sources"),
  analystStatus: () => request<AnalystStatus>("/api/analyst/status"),
  asOfRange: () => request<AsOfRange>("/api/data/as-of-range"),
  geocode: (q: string, signal?: AbortSignal) =>
    request<GeocodeHit[]>(`/api/geocode?q=${encodeURIComponent(q)}`, { signal }),
  simulate: (body: SimulateRequest) =>
    request<SimulationResult>("/api/simulate", { method: "POST", body: JSON.stringify(body) }),
  heatmap: (businessType: string, asOf?: string | null) =>
    request<Heatmap>(
      `/api/heatmap?business_type=${encodeURIComponent(businessType)}${asOf ? `&as_of=${asOf}` : ""}`,
    ),
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
