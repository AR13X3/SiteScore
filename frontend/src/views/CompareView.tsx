import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AddressSearch, shortAddress } from "../components/AddressSearch";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { type FinderSettings, FinderPanel, round5, spotLetter } from "../components/FinderPanel";
import { ProfitPanel } from "../components/ProfitPanel";
import { type Metric, RevenueChart } from "../components/RevenueChart";
import { SiteList } from "../components/SiteList";
import { SiteMap } from "../components/SiteMap";
import { WhyPanel } from "../components/WhyPanel";
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

function freeSlot(sites: CandidateSite[]): number {
  const used = new Set(sites.map((s) => s.slot));
  return [...Array(MAX_SITES).keys()].find((i) => !used.has(i)) ?? 0;
}

interface Props {
  region: Region;
  businessType: string;
  asOf: string | null;
  dark: boolean;
}

export function CompareView({ region, businessType, asOf, dark }: Props) {
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
  // Spot finder: a circle the user places, and its results.
  const [panel, setPanel] = useState<"compare" | "find">("compare");
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
  }, []);
  /** Select a site and bring its catchment into view. */
  const showSite = useCallback((id: string) => {
    const s = sitesRef.current.find((x) => x.id === id);
    setSelectedId(id);
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
    setPanel("find");
  }, [selectedId, search]);
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
    setPanel("compare");
    setFitKey(Date.now());
  }, [search, addedSpots]);

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
  const winner = current?.explanations[0];
  const winnerOdds = current?.uncertainty?.sites.find((u) => u.site_id === winner?.site_id);
  const selectedSim = current?.sites.find((s) => s.site.id === selectedId);
  const selected = sites.find((s) => s.id === selectedId);
  const showProfit = metric === "profit" && !!costs;

  return (
    <>
      {error && <div className="alert">{error}</div>}
      <main className="layout">
        <section className="card map-card">
          <ErrorBoundary what="map">
          <SiteMap
            region={region}
            sites={sites}
            dark={dark}
            canAdd={sites.length < MAX_SITES}
            selectedId={selectedId}
            overlay={panel === "compare" ? selectedSim : undefined}
            focus={focus}
            fitKey={fitKey}
            onAdd={addSite}
            onMove={moveSite}
            onSelect={showSite}
            finder={panel === "find" ? { lat: finder.lat, lon: finder.lon, radius: finder.radius } : null}
            onFinderMove={(lat, lon) => setFinder((f) => ({ ...f, lat, lon }))}
            spots={panel === "find" ? search?.spots : undefined}
            grid={panel === "find" ? search?.grid : undefined}
            vacancies={panel === "find" ? search?.vacancies : undefined}
            activeSpotId={activeSpot}
            onSpotSelect={setActiveSpot}
          />
          </ErrorBoundary>
          {panel === "find" && (
            <div className="map-legend" aria-label="Map key for the spot finder">
              <div className="map-legend__title">Finding the best spots</div>
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
          {panel === "compare" && selectedSim && selected && (
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
        </section>

        <aside className="card side">
          <div className="segmented segmented--wide" role="tablist" aria-label="Side panel">
            <button role="tab" aria-selected={panel === "compare"} className={panel === "compare" ? "is-on" : ""} onClick={() => setPanel("compare")}>
              Compare sites{sites.length ? ` (${sites.length})` : ""}
            </button>
            <button role="tab" aria-selected={panel === "find"} className={panel === "find" ? "is-on" : ""} onClick={openFinder}>
              Find spots
            </button>
          </div>
          {panel === "find" && (
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
          {panel === "compare" && (<>
          <div>
            <h2>Candidate sites</h2>
            <AddressSearch disabled={sites.length >= MAX_SITES} onPick={addAddress} />
          </div>
          <SiteList
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
          {winner && current && current.sites.length > 1 && (
            <div className="winner">
              <span className="muted">Best over 36 months</span>
              <strong>{current.sites.find((s) => s.site.id === winner.site_id)?.site.label}</strong>
              <span>
                {money(winner.total_revenue)} revenue · opens{" "}
                {new Date(`${current.open_date}T00:00:00`).toLocaleDateString("en-AU", { month: "long", year: "numeric" })}
              </span>
              {winnerOdds && current.uncertainty && (
                <span className="muted">
                  Best in {pct(winnerOdds.prob_best)} of {current.uncertainty.n_runs} scenarios
                </span>
              )}
            </div>
          )}
          {costs && defaultCosts && (
            <ProfitPanel
              costs={costs}
              defaults={defaultCosts}
              onChange={setCosts}
              result={current}
              sites={sites}
              dark={dark}
            />
          )}
          </>)}
        </aside>

        {current && (
          <section className={`card chart-card ${loading ? "is-loading" : ""}`}>
            <div className="card-head">
              <h2>Projected monthly {showProfit ? "profit" : "revenue"}</h2>
              {costs && (
                <div className="segmented" role="group" aria-label="Show revenue or profit">
                  {(["revenue", "profit"] as const).map((m) => (
                    <button key={m} className={metric === m ? "is-on" : ""} aria-pressed={metric === m} onClick={() => setMetric(m)}>
                      {m === "revenue" ? "Revenue" : "Profit"}
                    </button>
                  ))}
                </div>
              )}
              <span className="muted card-head__note">
                Line: central estimate ·{" "}
                {current.uncertainty
                  ? `shaded: 80% of ${current.uncertainty.n_runs} scenarios (P10–P90)`
                  : bandsLoading
                    ? "running 300 scenarios for the range…"
                    : "no range"}{" "}
                · includes ramp-up, seasons and approved developments · data as of {current.as_of}
              </span>
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
        )}

        {current && (
          <section className={`why ${loading ? "is-loading" : ""}`}>
            <h2>Why each site wins or loses</h2>
            <WhyPanel result={current} sites={sites} dark={dark} />
          </section>
        )}
      </main>
    </>
  );
}
