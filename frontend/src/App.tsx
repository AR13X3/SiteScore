import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DataBadge } from "./components/DataBadge";
import { RevenueChart } from "./components/RevenueChart";
import { SiteList } from "./components/SiteList";
import { SiteMap } from "./components/SiteMap";
import { WhyPanel } from "./components/WhyPanel";
import { api } from "./lib/api";
import { money } from "./lib/format";
import { MAX_SITES, useDarkMode } from "./lib/theme";
import type { BusinessType, CandidateSite, Region, SimulationResult, TableStatus } from "./lib/types";

const DEMO_SITES: Omit<CandidateSite, "id" | "slot">[] = [
  { label: "Church St, Parramatta", lat: -33.815, lon: 151.0035 },
  { label: "Harris Park", lat: -33.8226, lon: 151.0085 },
  { label: "Wentworth Point", lat: -33.829, lon: 151.075 },
];

let nextId = 1;
const newId = () => `s${nextId++}`;

function freeSlot(sites: CandidateSite[]): number {
  const used = new Set(sites.map((s) => s.slot));
  return [...Array(MAX_SITES).keys()].find((i) => !used.has(i)) ?? 0;
}

export default function App() {
  const dark = useDarkMode();
  const [region, setRegion] = useState<Region | null>(null);
  const [types, setTypes] = useState<BusinessType[]>([]);
  const [tables, setTables] = useState<TableStatus[]>([]);
  const [businessType, setBusinessType] = useState("cafe");
  const [sites, setSites] = useState<CandidateSite[]>([]);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSeq = useRef(0);

  useEffect(() => {
    Promise.all([api.region(), api.businessTypes(), api.dataStatus()])
      .then(([r, t, d]) => {
        setRegion(r);
        setTypes(t);
        setTables(d);
      })
      .catch((e: Error) => setError(`Can't reach the SiteScore API: ${e.message}`));
  }, []);

  // Re-simulate shortly after any change; ignore responses from superseded requests.
  useEffect(() => {
    if (sites.length === 0) {
      setResult(null);
      return;
    }
    const seq = ++requestSeq.current;
    const timer = setTimeout(() => {
      setLoading(true);
      api
        .simulate({
          business_type: businessType,
          sites: sites.map(({ id, label, lat, lon }) => ({ id, label, lat, lon })),
        })
        .then((r) => {
          if (seq !== requestSeq.current) return;
          setResult(r);
          setError(null);
        })
        .catch((e: Error) => seq === requestSeq.current && setError(e.message))
        .finally(() => seq === requestSeq.current && setLoading(false));
    }, 350);
    return () => clearTimeout(timer);
  }, [sites, businessType]);

  const addSite = useCallback((lat: number, lon: number) => {
    setSites((prev) => {
      if (prev.length >= MAX_SITES) return prev;
      const slot = freeSlot(prev);
      return [...prev, { id: newId(), slot, label: `Site ${slot + 1}`, lat, lon }];
    });
  }, []);
  const moveSite = useCallback((id: string, lat: number, lon: number) => {
    setSites((prev) => prev.map((s) => (s.id === id ? { ...s, lat, lon } : s)));
  }, []);
  const renameSite = useCallback((id: string, label: string) => {
    setSites((prev) => prev.map((s) => (s.id === id ? { ...s, label } : s)));
  }, []);
  const removeSite = useCallback((id: string) => setSites((prev) => prev.filter((s) => s.id !== id)), []);
  const loadDemo = useCallback(
    () => setSites(DEMO_SITES.map((s, i) => ({ ...s, id: newId(), slot: i }))),
    [],
  );

  const selectedType = types.find((t) => t.id === businessType);
  // While a refetch runs, keep showing the previous result (dimmed), minus removed sites.
  const current = useMemo<SimulationResult | null>(() => {
    if (!result) return null;
    const ids = new Set(sites.map((s) => s.id));
    const kept = result.sites.filter((s) => ids.has(s.site.id));
    if (!kept.length) return null;
    return { ...result, sites: kept, explanations: result.explanations.filter((e) => ids.has(e.site_id)) };
  }, [result, sites]);
  const winner = current?.explanations[0];

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand__mark" aria-hidden>
            ◆
          </span>
          <span className="brand__name">SiteScore</span>
          {region && <span className="muted">· {region.name}</span>}
        </div>
        <div className="topbar__controls">
          <label className="field">
            <span className="muted">Business</span>
            <select value={businessType} onChange={(e) => setBusinessType(e.target.value)}>
              {types.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                  {t.status === "draft" ? " (draft)" : ""}
                </option>
              ))}
            </select>
          </label>
          <DataBadge tables={tables} />
        </div>
      </header>

      {error && <div className="alert">{error}</div>}
      {selectedType?.status === "draft" && (
        <div className="alert alert--info">
          The {selectedType.name.toLowerCase()} profile is a draft: its assumptions haven't been validated yet.
        </div>
      )}

      <main className="layout">
        <section className="card map-card">
          {region ? (
            <SiteMap
              region={region}
              sites={sites}
              dark={dark}
              canAdd={sites.length < MAX_SITES}
              onAdd={addSite}
              onMove={moveSite}
            />
          ) : (
            <div className="map placeholder" />
          )}
        </section>

        <aside className="card side">
          <h2>Candidate sites</h2>
          <SiteList
            sites={sites}
            result={current}
            dark={dark}
            onRename={renameSite}
            onRemove={removeSite}
            onDemo={loadDemo}
            onClear={() => setSites([])}
          />
          {winner && current && current.sites.length > 1 && (
            <div className="winner">
              <span className="muted">Best over 36 months</span>
              <strong>{current.sites.find((s) => s.site.id === winner.site_id)?.site.label}</strong>
              <span>
                {money(winner.total_revenue)} · opens {new Date(`${current.open_date}T00:00:00`).toLocaleDateString("en-AU", { month: "long", year: "numeric" })}
              </span>
            </div>
          )}
        </aside>

        {current && (
          <section className={`card chart-card ${loading ? "is-loading" : ""}`}>
            <div className="card-head">
              <h2>Projected monthly revenue</h2>
              <span className="muted">
                Median scenario · ramp-up, seasons and approved developments included · data as of {current.as_of}
              </span>
            </div>
            <RevenueChart result={current} sites={sites} dark={dark} />
          </section>
        )}

        {current && (
          <section className={`why ${loading ? "is-loading" : ""}`}>
            <h2>Why each site wins or loses</h2>
            <WhyPanel result={current} sites={sites} dark={dark} />
          </section>
        )}
      </main>
    </div>
  );
}
