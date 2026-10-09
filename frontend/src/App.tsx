import { useEffect, useState } from "react";
import { DataBadge } from "./components/DataBadge";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { api } from "./lib/api";
import { useDarkMode } from "./lib/theme";
import type { AsOfRange, BusinessType, Region, TableStatus } from "./lib/types";
import { BacktestView } from "./views/BacktestView";
import { CompareView } from "./views/CompareView";

type Screen = "compare" | "backtest";
const SCREENS: { id: Screen; label: string }[] = [
  { id: "compare", label: "Compare sites" },
  { id: "backtest", label: "Backtest" },
];

/** The screen lives in the URL hash (#backtest), so it survives reloads and can be linked. */
function useScreen(): [Screen, (s: Screen) => void] {
  const read = (): Screen => (window.location.hash === "#backtest" ? "backtest" : "compare");
  const [screen, setScreen] = useState<Screen>(read);
  useEffect(() => {
    const onHash = () => setScreen(read());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return [screen, (s) => (window.location.hash = s === "compare" ? "" : s)];
}

const longDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-AU", { day: "numeric", month: "long", year: "numeric" });

export default function App() {
  const dark = useDarkMode();
  const [screen, setScreen] = useScreen();
  const [region, setRegion] = useState<Region | null>(null);
  const [types, setTypes] = useState<BusinessType[]>([]);
  const [tables, setTables] = useState<TableStatus[]>([]);
  const [range, setRange] = useState<AsOfRange | null>(null);
  const [businessType, setBusinessType] = useState("cafe");
  const [asOf, setAsOf] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Both screens stay mounted once visited, so switching never loses your sites or results.
  const [visitedBacktest, setVisitedBacktest] = useState(screen === "backtest");
  useEffect(() => {
    if (screen === "backtest") setVisitedBacktest(true);
  }, [screen]);

  useEffect(() => {
    Promise.all([api.region(), api.businessTypes(), api.dataStatus(), api.asOfRange()])
      .then(([r, t, d, a]) => {
        setRegion(r);
        setTypes(t);
        setTables(d);
        setRange(a);
      })
      .catch((e: Error) => setError(`Can't reach the SiteScore API: ${e.message}`));
  }, []);

  const selectedType = types.find((t) => t.id === businessType);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand__mark" aria-hidden>
            ◆
          </span>
          <span className="brand__name">SiteScore</span>
          {region && <span className="muted brand__region">{region.name}</span>}
        </div>
        <nav className="tabs" aria-label="Screens">
          {SCREENS.map((s) => (
            <button
              key={s.id}
              className={`tab ${screen === s.id ? "is-on" : ""}`}
              aria-current={screen === s.id ? "page" : undefined}
              onClick={() => setScreen(s.id)}
            >
              {s.label}
            </button>
          ))}
        </nav>
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
          {screen === "compare" && range && (
            <label className="field">
              <span className="muted">Data as of</span>
              <input
                type="date"
                min={range.min}
                max={range.max}
                value={asOf ?? range.max}
                onChange={(e) => setAsOf(e.target.value && e.target.value !== range.max ? e.target.value : null)}
              />
              {asOf && (
                <button className="btn btn--ghost btn--small" onClick={() => setAsOf(null)}>
                  Today
                </button>
              )}
            </label>
          )}
          <DataBadge tables={tables} />
        </div>
      </header>

      {error && <div className="alert">{error}</div>}
      {selectedType?.status === "draft" && (
        <div className="alert alert--info">
          The {selectedType.name.toLowerCase()} profile is a draft: its assumptions haven't been validated yet.
        </div>
      )}
      {screen === "compare" && asOf && (
        <div className="alert alert--info">
          <strong>Looking back to {longDate(asOf)}.</strong> The model sees only data published by then (the map,
          patronage and approved developments as they were), as if you were choosing a site that day. Each site opens the
          month after.
        </div>
      )}

      {region && (
        <div hidden={screen !== "compare"}>
          <ErrorBoundary what="Compare screen">
            <CompareView region={region} businessType={businessType} asOf={asOf} dark={dark} />
          </ErrorBoundary>
        </div>
      )}
      {region && visitedBacktest && (
        <div hidden={screen !== "backtest"}>
          <ErrorBoundary what="Backtest screen">
            <BacktestView region={region} businessType={businessType} dark={dark} />
          </ErrorBoundary>
        </div>
      )}
    </div>
  );
}
