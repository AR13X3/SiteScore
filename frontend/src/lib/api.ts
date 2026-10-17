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

/**
 * Where the API lives. Empty (same origin) when FastAPI serves this page; the GitHub
 * Pages build sets VITE_API_BASE to Joy's server, which runs the model.
 */
export const API_BASE = (((import.meta as { env?: Record<string, string | undefined> }).env?.VITE_API_BASE) ?? "")
  .replace(/\/+$/, "");

export const OFFLINE_MESSAGE = "Joy's server is offline and under maintenance.";

/** The API couldn't be reached at all (down, unreachable, or too slow to answer). */
export class ServerOffline extends Error {
  constructor() {
    super(OFFLINE_MESSAGE);
    this.name = "ServerOffline";
  }
}

/** Every finished API call, for the status strip: which endpoint, how long, did it work. */
export interface ApiCall {
  endpoint: string;
  ms: number;
  ok: boolean;
  /** The server itself couldn't be reached (rather than answering with an error). */
  offline?: boolean;
}
export const API_EVENT = "sitescore:api";

/** Tell the page the server is unreachable (the analyst stream uses this too). */
export function reportOffline(endpoint: string): void {
  window.dispatchEvent(new CustomEvent<ApiCall>(API_EVENT, { detail: { endpoint, ms: 0, ok: false, offline: true } }));
}

// A proxy in front of the API (Tailscale Funnel) answers these when the server behind it is down.
const GATEWAY_DOWN = new Set([502, 503, 504]);

async function request<T>(path: string, init?: RequestInit, timeoutMs?: number): Promise<T> {
  const t0 = performance.now();
  const endpoint = path.replace(/^\/api\//, "").split("?")[0];
  const report = (ok: boolean, offline = false) =>
    window.dispatchEvent(new CustomEvent<ApiCall>(API_EVENT, {
      detail: { endpoint, ms: performance.now() - t0, ok, offline },
    }));
  // Our own abort (a timeout) and the caller's (a superseded search) are told apart.
  const ctrl = new AbortController();
  const outer = init?.signal;
  if (outer) {
    if (outer.aborted) ctrl.abort();
    else outer.addEventListener("abort", () => ctrl.abort(), { once: true });
  }
  let timedOut = false;
  const timer = timeoutMs ? setTimeout(() => {
    timedOut = true;
    ctrl.abort();
  }, timeoutMs) : undefined;
  let res: Response;
  try {
    res = await fetch(API_BASE + path, {
      ...init,
      signal: ctrl.signal,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (e) {
    if (timedOut || (e as Error).name !== "AbortError") {
      report(false, true);
      throw new ServerOffline();
    }
    throw e; // the caller cancelled: not a failure
  } finally {
    clearTimeout(timer);
  }
  const json = (res.headers.get("content-type") ?? "").includes("application/json");
  if (GATEWAY_DOWN.has(res.status) && !json) {
    report(false, true);
    throw new ServerOffline();
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

// The start-up calls give up after this long, so a server that's down can't leave the
// page waiting: it says so instead.
const BOOT_TIMEOUT_MS = 15_000;

export const api = {
  health: () => request<{ status: string }>("/api/health", undefined, 8_000),
  region: () => request<Region>("/api/region", undefined, BOOT_TIMEOUT_MS),
  businessTypes: () => request<BusinessType[]>("/api/business-types", undefined, BOOT_TIMEOUT_MS),
  businessProfile: (id: string) => request<BusinessProfile>(`/api/business-types/${encodeURIComponent(id)}`),
  dataStatus: () => request<TableStatus[]>("/api/data/status", undefined, BOOT_TIMEOUT_MS),
  sources: () => request<SourceInfo[]>("/api/sources"),
  analystStatus: () => request<AnalystStatus>("/api/analyst/status", undefined, BOOT_TIMEOUT_MS),
  asOfRange: () => request<AsOfRange>("/api/data/as-of-range", undefined, BOOT_TIMEOUT_MS),
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
