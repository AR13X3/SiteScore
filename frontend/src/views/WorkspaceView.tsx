import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AddressSearch, shortAddress } from "../components/AddressSearch";
import { AnalystPanel } from "../components/AnalystPanel";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { type FinderSettings, FinderPanel, round5, spotLetter } from "../components/FinderPanel";
import { IconChat, IconInfo, IconPin, IconSliders } from "../components/Icons";
import { ProfitPanel } from "../components/ProfitPanel";
import { type Metric, RevenueChart } from "../components/RevenueChart";
import { SiteCards } from "../components/SiteCards";
import { SiteDetail } from "../components/SiteDetail";
import { SiteMap } from "../components/SiteMap";
import type { AnalystStatus, UiAction, WorkspaceContext } from "../lib/analyst";
import { api } from "../lib/api";
import { money, parameterLabel, pct } from "../lib/format";
import { useElapsed } from "../lib/hooks";
import { MAX_SITES, ordinalColor, siteColor } from "../lib/theme";
import type { CandidateSite, Costs, GeocodeHit, Region, SearchResult, SimulationResult, Spot } from "../lib/types";

const DEMO_SITES: Omit<CandidateSite, "id" | "slot">[] = [
  { label: "Church St, Parramatta", lat: -33.815, lon: 151.0035 },
  { label: "Harris Park", lat: -33.8226, lon: 151.0085 },
  { label: "Wentworth Point", lat: -33.829, lon: 151.075 },
];

let nextId = 1;
const newId = () => `s${nextId++}`;
const fmt = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2));
const monthYear = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-AU", { month: "long", year: "numeric" });

function freeSlot(sites: CandidateSite[]): number {
  const used = new Set(sites.map((s) => s.slot));
  return [...Array(MAX_SITES).keys()].find((i) => !used.has(i)) ?? 0;
}

/** Left column: your candidate sites, or a spot search. Right column: what you look at. */
type ListMode = "sites" | "find";
type Panel = "details" | "analyst" | "costs";
/** What the map overlays: the comparison (catchments) or a spot search (circle, spots). */
type MapLayer = "sites" | "search";

interface Props {
  region: Region;
  businessType: string;
  businessName: string;
  asOf: string | null;
  dark: boolean;
  analyst: AnalystStatus | null;
  incoming: { question: string; key: number } | null;
  /** Business type and as-of controls, shown in the page header. */
  controls: ReactNode;
}

export function WorkspaceView({ region, businessType, businessName, asOf, dark, analyst, incoming, controls }: Props) {
  const [sites, setSites] = useState<CandidateSite[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [bandsLoading, setBandsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [focus, setFocus] = useState<{ lat: number; lon: number; key: number }>();
  const [fitKey, setFitKey] = useState<number>();
  const [defaultCosts, setDefaultCosts] = useState<Costs | null>(null);
  const [costs, setCosts] = useState<Costs | null>(null);
  const [metric, setMetric] = useState<Metric>("revenue");
  const requestSeq = useRef(0);
  const sitesRef = useRef(sites);
  sitesRef.current = sites;
  const [listMode, setListModeState] = useState<ListMode>("sites");
  const [panel, setPanel] = useState<Panel>("details");
  const [mapLayer, setMapLayer] = useState<MapLayer>("sites");
  // Spot finder: a circle the user (or the analyst) places, and its results.
  const [finder, setFinder] = useState<FinderSettings>({
    lat: region.map.center[0], lon: region.map.center[1], radius: 1000,
    where: "anywhere", retailOnly: true, rankBy: "revenue",
  });
  const [search, setSearch] = useState<SearchResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [activeSpot, setActiveSpot] = useState<string | null>(null);
  const [addedSpots, setAddedSpots] = useState<Set<string>>(new Set());
  const searchElapsed = useElapsed(searching);
  // Questions for the analyst: from the home page, or "Ask analyst" on a site.
  const [ask, setAsk] = useState<{ question: string; key: number } | null>(null);

  useEffect(() => {
    if (!incoming) return;
    setAsk(incoming);
    setPanel("analyst");
  }, [incoming]);

  const setListMode = useCallback((m: ListMode) => {
    setListModeState(m);
    setMapLayer(m === "find" ? "search" : "sites");
  }, []);

  useEffect(() => {
    setSearch(null); // results belong to one business type and one as-of date
    setAddedSpots(new Set());
  }, [businessType, asOf]);

  // The business type's running costs are the starting point for the profit view.
  useEffect(() => {
    api.businessProfile(businessType)
      .then((p) => {
        setDefaultCosts(p.costs);
        setCosts(p.costs);
        if (!p.costs) setMetric("revenue");
      })
      .catch(() => setDefaultCosts(null));
  }, [businessType]);

  // Re-simulate shortly after any change: first the central estimate (fast), then the
  // same request with Monte Carlo bands. Responses from superseded requests are ignored.
  useEffect(() => {
    if (sites.length === 0) {
      setResult(null);
      return;
    }
    const seq = ++requestSeq.current;
    const current = () => seq === requestSeq.current;
    const timer = setTimeout(async () => {
      const body = {
        business_type: businessType,
        sites: sites.map(({ id, label, lat, lon }) => ({ id, label, lat, lon })),
        ...(asOf ? { as_of: asOf } : {}),
        ...(costs ? { costs } : {}),
      };
      setLoading(true);
      try {
        const base = await api.simulate(body);
        if (!current()) return;
        setResult(base);
        setError(null);
        setLoading(false);
        setBandsLoading(true);
        const withBands = await api.simulate({ ...body, uncertainty: true });
        if (current()) setResult(withBands);
      } catch (e) {
        if (current()) setError((e as Error).message);
      } finally {
        if (current()) {
          setLoading(false);
          setBandsLoading(false);
        }
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [sites, businessType, asOf, costs]);

  const addSite = useCallback((lat: number, lon: number, label?: string) => {
    const prev = sitesRef.current;
    if (prev.length >= MAX_SITES) return;
    const slot = freeSlot(prev);
    const id = newId();
    setSites([...prev, { id, slot, label: label ?? `Site ${slot + 1}`, lat, lon }]);
    setSelectedId(id);
    setMapLayer("sites");
    setListModeState("sites");
    setPanel((p) => (p === "analyst" ? p : "details"));
  }, []);
  const addAddress = useCallback(
    (hit: GeocodeHit) => {
      addSite(hit.lat, hit.lon, shortAddress(hit.label));
      setFocus({ lat: hit.lat, lon: hit.lon, key: Date.now() });
    },
    [addSite],
  );
  const moveSite = useCallback((id: string, lat: number, lon: number) => {
    setSites((prev) => prev.map((s) => (s.id === id ? { ...s, lat, lon } : s)));
  }, []);
  const renameSite = useCallback((id: string, label: string) => {
    setSites((prev) => prev.map((s) => (s.id === id ? { ...s, label } : s)));
  }, []);
  const removeSite = useCallback((id: string) => {
    const left = sitesRef.current.filter((s) => s.id !== id);
    setSites(left);
    setSelectedId((sel) => (sel === id ? (left[0]?.id ?? null) : sel));
  }, []);
  const loadDemo = useCallback(() => {
    const demo = DEMO_SITES.map((s, i) => ({ ...s, id: newId(), slot: i }));
    setSites(demo);
    setSelectedId(demo[0].id);
    setFitKey(Date.now());
    setMapLayer("sites");
  }, []);
  /** Select a site and bring its catchment into view. */
  const showSite = useCallback((id: string) => {
    const s = sitesRef.current.find((x) => x.id === id);
    setSelectedId(id);
    setMapLayer("sites");
    if (s) setFocus({ lat: s.lat, lon: s.lon, key: Date.now() });
  }, []);
  const clear = useCallback(() => {
    setSites([]);
    setSelectedId(null);
    setAddedSpots(new Set());
  }, []);

  const openFinder = useCallback(() => {
    // Start the search area on the selected site, if there is one.
    const sel = sitesRef.current.find((s) => s.id === selectedId);
    if (sel && !search) setFinder((f) => ({ ...f, lat: sel.lat, lon: sel.lon }));
    setListMode("find");
  }, [selectedId, search, setListMode]);
  const findNearby = useCallback((site: CandidateSite) => {
    setFinder((f) => ({ ...f, lat: site.lat, lon: site.lon, radius: 800 }));
    setSearch(null);
    setListMode("find");
  }, [setListMode]);
  const askAnalyst = useCallback((question: string) => {
    setAsk({ question, key: Date.now() });
    setPanel("analyst");
  }, []);
  const runSearch = useCallback(async () => {
    setSearching(true);
    setSearchError(null);
    try {
      const r = await api.search({
        business_type: businessType, lat: round5(finder.lat), lon: round5(finder.lon),
        radius_m: finder.radius, where: finder.where, retail_only: finder.retailOnly,
        rank_by: finder.rankBy, ...(asOf ? { as_of: asOf } : {}), ...(costs ? { costs } : {}),
      });
      setSearch(r);
      setActiveSpot(r.spots[0]?.id ?? null);
    } catch (e) {
      setSearchError((e as Error).message);
    } finally {
      setSearching(false);
    }
  }, [businessType, finder, asOf, costs]);
  const addSpot = useCallback((spot: Spot) => {
    if (sitesRef.current.length >= MAX_SITES) return;
    addSite(spot.lat, spot.lon, `${spotLetter(spot.rank)}: ${spot.label}`);
    setAddedSpots((prev) => new Set(prev).add(spot.id));
  }, [addSite]);
  const addTop = useCallback((n: number) => {
    const prev = sitesRef.current;
    const free = Math.max(0, MAX_SITES - prev.length);
    const todo = (search?.spots ?? []).filter((s) => !addedSpots.has(s.id)).slice(0, Math.min(n, free));
    // One by one, so each new site takes the next free colour slot.
    const next = [...prev];
    for (const sp of todo) {
      next.push({ id: newId(), slot: freeSlot(next), label: `${spotLetter(sp.rank)}: ${sp.label}`, lat: sp.lat, lon: sp.lon });
    }
    setSites(next);
    if (next.length > prev.length) setSelectedId(next[prev.length].id);
    setAddedSpots((p) => new Set([...p, ...todo.map((t) => t.id)]));
    setListMode("sites");
    setFitKey(Date.now());
  }, [search, addedSpots, setListMode]);

  // --- The analyst works on this workspace ---------------------------------------------
  const ctxRef = useRef<WorkspaceContext>(null!);
  ctxRef.current = {
    business_type: businessType,
    as_of: asOf,
    costs,
    sites: sites.map(({ id, label, lat, lon }) => ({ id, label, lat, lon })),
    selected_id: selectedId,
    finder: mapLayer === "search" || search ? { lat: finder.lat, lon: finder.lon, radius_m: finder.radius } : null,
  };
  const getWorkspace = useCallback(() => ctxRef.current, []);
  const onAction = useCallback((a: UiAction) => {
    if (a.type === "set_sites") {
      const base = a.mode === "add" ? [...sitesRef.current] : [];
      for (const s of a.sites) {
        if (base.length >= MAX_SITES) break;
        base.push({ id: newId(), slot: freeSlot(base), label: s.label, lat: s.lat, lon: s.lon });
      }
      setSites(base);
      setSelectedId(base[0]?.id ?? null);
      setMapLayer("sites");
      setListModeState("sites");
      setFitKey(Date.now());
    } else if (a.type === "search") {
      setFinder({ ...a.settings });
      setSearch(a.result);
      setActiveSpot(a.result.spots[0]?.id ?? null);
      setAddedSpots(new Set());
      setMapLayer("search");
      setListModeState("find");
    } else if (a.type === "focus") {
      const near = sitesRef.current.find((s) => Math.abs(s.lat - a.lat) < 1e-4 && Math.abs(s.lon - a.lon) < 1e-4);
      if (near) {
        setSelectedId(near.id);
        setMapLayer("sites");
      }
      setFocus({ lat: a.lat, lon: a.lon, key: Date.now() });
    }
  }, []);

  // While a refetch runs, keep showing the previous result (dimmed), minus removed sites.
  const current = useMemo<SimulationResult | null>(() => {
    if (!result) return null;
    const ids = new Set(sites.map((s) => s.id));
    const kept = result.sites.filter((s) => ids.has(s.site.id));
    if (!kept.length) return null;
    const uncertainty = result.uncertainty && {
      ...result.uncertainty,
      sites: result.uncertainty.sites.filter((u) => ids.has(u.site_id)),
    };
    return {
      ...result,
      sites: kept,
      explanations: result.explanations.filter((e) => ids.has(e.site_id)),
      uncertainty,
    };
  }, [result, sites]);
  const selectedSim = current?.sites.find((s) => s.site.id === selectedId);
  const selected = sites.find((s) => s.id === selectedId);
  const showProfit = metric === "profit" && !!costs;
  const showSearch = mapLayer === "search";
  const slotOf = new Map(sites.map((s) => [s.id, s.slot]));
  const oddsOf = new Map(current?.uncertainty?.sites.map((u) => [u.site_id, u]));
  const ranked = current
    ? current.explanations
        .map((e) => ({ e, sim: current.sites.find((s) => s.site.id === e.site_id) }))
        .filter((r): r is { e: (typeof current.explanations)[number]; sim: NonNullable<typeof r.sim> } => !!r.sim)
    : [];

  return (
    <div className="workspace">
      <header className="ws-head">
        <div>
          <span className="crumb">
            {region.name} · {businessName}
          </span>
          <h1>Site selection</h1>
        </div>
        <div className="ws-head__controls">{controls}</div>
      </header>
      {error && <div className="alert alert--inline">{error}</div>}

      <div className="ws-grid">
        <aside className="col col--list">
          <div className="col__head">
            <div className="segmented segmented--wide" role="tablist" aria-label="Sites or spot search">
              <button role="tab" aria-selected={listMode === "sites"} className={listMode === "sites" ? "is-on" : ""} onClick={() => setListMode("sites")}>
                Sites{sites.length ? ` · ${sites.length}` : ""}
              </button>
              <button role="tab" aria-selected={listMode === "find"} className={listMode === "find" ? "is-on" : ""} onClick={openFinder}>
                Find spots
              </button>
            </div>
          </div>
          <div className="col__body">
            {listMode === "sites" ? (
              <>
                <AddressSearch disabled={sites.length >= MAX_SITES} onPick={addAddress} />
                <SiteCards
                  sites={sites}
                  result={current}
                  dark={dark}
                  selectedId={selectedId}
                  onSelect={showSite}
                  onRename={renameSite}
                  onRemove={removeSite}
                  onDemo={loadDemo}
                  onClear={clear}
                />
              </>
            ) : (
              <FinderPanel
                settings={finder}
                onChange={(patch) => setFinder((f) => ({ ...f, ...patch }))}
                result={search}
                searching={searching}
                elapsed={searchElapsed}
                error={searchError}
                hasCosts={!!costs}
                room={MAX_SITES - sites.length}
                maxSites={MAX_SITES}
                addedIds={addedSpots}
                activeId={activeSpot}
                onSearch={runSearch}
                onSelect={setActiveSpot}
                onAdd={addSpot}
                onAddTop={addTop}
              />
            )}
          </div>
        </aside>

        <section className="col col--map">
          <ErrorBoundary what="map">
            <SiteMap
              region={region}
              sites={sites}
              dark={dark}
              canAdd={sites.length < MAX_SITES}
              selectedId={selectedId}
              overlay={!showSearch ? selectedSim : undefined}
              focus={focus}
              fitKey={fitKey}
              onAdd={addSite}
              onMove={moveSite}
              onSelect={showSite}
              finder={showSearch ? { lat: finder.lat, lon: finder.lon, radius: finder.radius } : null}
              onFinderMove={(lat, lon) => setFinder((f) => ({ ...f, lat, lon }))}
              spots={showSearch ? search?.spots : undefined}
              grid={showSearch ? search?.grid : undefined}
              vacancies={showSearch ? search?.vacancies : undefined}
              activeSpotId={activeSpot}
              onSpotSelect={setActiveSpot}
            />
          </ErrorBoundary>
          {showSearch && (
            <div className="map-legend" aria-label="Map key for the spot finder">
              <div className="map-legend__title">Spot search</div>
              <div><span className="key-ring key-ring--ink" /><span className="long">Search area (click the map or drag its centre)</span><span className="short">Search area</span></div>
              <div><span className="key-letter">A</span><span className="long">Best spots, ranked</span><span className="short">Best spots</span></div>
              <div><span className="key-square" /><span className="long">Vacant shopfront (OpenStreetMap)</span><span className="short">Vacant</span></div>
              {search?.grid.length ? (
                <div>
                  <span className="key-ramp">
                    {[0, 2, 4].map((b) => <span key={b} style={{ background: ordinalColor(b, dark) }} />)}
                  </span>
                  <span className="long">Quick score of every spot checked, darker is higher</span>
                  <span className="short">Quick score</span>
                </div>
              ) : null}
            </div>
          )}
          {!showSearch && selectedSim && selected && (
            <div className="map-legend" aria-label="Map key for the selected site">
              <div className="map-legend__title">
                <span className="site-key site-key--small" style={{ background: siteColor(selected.slot, dark) }}>
                  {selected.slot + 1}
                </span>
                {selected.label}
              </div>
              <div>
                <span className="key-ring" style={{ borderColor: siteColor(selected.slot, dark) }} />
                <span className="long">Walking catchments by customer type</span>
                <span className="short">Catchments</span>
              </div>
              <div>
                <span className="key-dot" />
                <span className="long">Competitors, sized by the share of this site's demand they take</span>
                <span className="short">Competitors</span>
              </div>
              <div>
                <span className="key-diamond" />
                <span className="long">Anchors (supermarkets, stations, schools)</span>
                <span className="short">Anchors</span>
              </div>
            </div>
          )}
          {!showSearch && sites.length === 0 && (
            <div className="map-hint">
              <IconPin size={14} /> Click the map to drop a site
            </div>
          )}
          {search && (
            <div className="map-switch segmented" role="group" aria-label="Map shows">
              <button className={!showSearch ? "is-on" : ""} aria-pressed={!showSearch} onClick={() => setMapLayer("sites")}>
                Sites
              </button>
              <button className={showSearch ? "is-on" : ""} aria-pressed={showSearch} onClick={() => setMapLayer("search")}>
                Search
              </button>
            </div>
          )}
        </section>

        <aside className="col col--detail">
          <div className="col__head">
            <div className="tabs-line" role="tablist" aria-label="Details, analyst or costs">
              <button role="tab" aria-selected={panel === "details"} className={panel === "details" ? "is-on" : ""} onClick={() => setPanel("details")}>
                <IconInfo size={15} /> Details
              </button>
              <button role="tab" aria-selected={panel === "analyst"} className={panel === "analyst" ? "is-on" : ""} onClick={() => setPanel("analyst")}>
                <IconChat size={15} /> Analyst
              </button>
              <button role="tab" aria-selected={panel === "costs"} className={panel === "costs" ? "is-on" : ""} onClick={() => setPanel("costs")}>
                <IconSliders size={15} /> Costs
              </button>
            </div>
          </div>
          <div className="col__fill" hidden={panel !== "details"}>
            <SiteDetail
              site={selected}
              result={current}
              siteCount={sites.length}
              dark={dark}
              loading={loading}
              onRemove={removeSite}
              onFindNearby={findNearby}
              onAsk={askAnalyst}
            />
          </div>
          {/* Kept mounted so the conversation survives switching tabs. */}
          <div className="col__fill" hidden={panel !== "analyst"}>
            <AnalystPanel
              status={analyst}
              businessName={businessName}
              siteCount={sites.length}
              getWorkspace={getWorkspace}
              onAction={onAction}
              incoming={ask}
            />
          </div>
          {panel === "costs" && (
            <div className="col__body">
              {costs && defaultCosts ? (
                <ProfitPanel costs={costs} defaults={defaultCosts} onChange={setCosts} result={current} sites={sites} dark={dark} />
              ) : (
                <p className="muted">This business type has no cost profile, so only revenue is shown.</p>
              )}
            </div>
          )}
        </aside>
      </div>

      {current && ranked.length > 0 && (
        <div className={`results ${loading ? "is-loading" : ""}`}>
          <section className="card chart-card">
            <div className="card-head card-head--split">
              <div>
                <h2>Projected monthly {showProfit ? "profit" : "revenue"}</h2>
                <span className="muted small">
                  Opens {monthYear(current.open_date)} · line: central estimate ·{" "}
                  {current.uncertainty
                    ? `shaded: 80% of ${current.uncertainty.n_runs} scenarios`
                    : bandsLoading
                      ? "running 300 scenarios…"
                      : "no range"}{" "}
                  · ramp-up, seasons and approved developments · data as of {current.as_of}
                </span>
              </div>
              {costs && (
                <div className="segmented" role="group" aria-label="Show revenue or profit">
                  {(["revenue", "profit"] as const).map((m) => (
                    <button key={m} className={metric === m ? "is-on" : ""} aria-pressed={metric === m} onClick={() => setMetric(m)}>
                      {m === "revenue" ? "Revenue" : "Profit"}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <RevenueChart result={current} sites={sites} dark={dark} metric={showProfit ? "profit" : "revenue"} costs={costs} />
            {current.uncertainty && (
              <details className="assumptions">
                <summary>Assumptions varied in the scenarios</summary>
                <ul>
                  {current.uncertainty.parameters.map((p) => (
                    <li key={p.path}>
                      <span>{parameterLabel(p.path)}</span>
                      <span className="muted">
                        {fmt(p.base)} (P10–P90: {fmt(p.p10)}–{fmt(p.p90)})
                      </span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>

          <section className="card table-card">
            <div className="card-head card-head--split">
              <h2>Comparison</h2>
              <span className="muted small">36 months from opening · ranges are P10–P90 of 300 scenarios</span>
            </div>
            <div className="table-scroll">
              <table className="bt-table compare-table">
                <thead>
                  <tr>
                    <th scope="col" className="num">#</th>
                    <th scope="col">Site</th>
                    <th scope="col" className="num">Revenue</th>
                    <th scope="col" className="num">Range</th>
                    <th scope="col" className="num">Profit</th>
                    <th scope="col" className="num">Est. rent / month</th>
                    {ranked.length > 1 && <th scope="col" className="num">Best in</th>}
                    <th scope="col" className="num">Loss risk</th>
                  </tr>
                </thead>
                <tbody>
                  {ranked.map(({ e, sim }) => {
                    const u = oddsOf.get(e.site_id);
                    const slot = slotOf.get(e.site_id) ?? 0;
                    return (
                      <tr key={e.site_id} className={`is-clickable ${e.site_id === selectedId ? "is-selected" : ""}`} onClick={() => showSite(e.site_id)}>
                        <td className="num">{e.rank}</td>
                        <td>
                          <span className="site-key site-key--small" style={{ background: siteColor(slot, dark) }}>{slot + 1}</span>
                          {sim.site.label}
                        </td>
                        <td className="num"><strong>{money(sim.total_revenue)}</strong></td>
                        <td className="num muted">{u ? `${money(u.total_revenue.p10)}–${money(u.total_revenue.p90)}` : "…"}</td>
                        <td className="num">{sim.total_profit === null ? "–" : money(sim.total_profit)}</td>
                        <td className="num">{sim.mature.rent ? money(sim.mature.rent.monthly) : "–"}</td>
                        {ranked.length > 1 && <td className="num">{u ? pct(u.prob_best) : "…"}</td>}
                        <td className="num">{u?.prob_loss == null ? "…" : pct(u.prob_loss)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
