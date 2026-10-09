import type { BusinessType, Region, SimulationResult, Site, TableStatus } from "./types";

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
}

export const api = {
  region: () => request<Region>("/api/region"),
  businessTypes: () => request<BusinessType[]>("/api/business-types"),
  dataStatus: () => request<TableStatus[]>("/api/data/status"),
  simulate: (body: SimulateRequest) =>
    request<SimulationResult>("/api/simulate", { method: "POST", body: JSON.stringify(body) }),
};
