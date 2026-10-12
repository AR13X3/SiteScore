import { useEffect, useState } from "react";
import { Logo } from "./components/Brand";
import { DataBadge } from "./components/DataBadge";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { IconGithub, IconMonitor, IconMoon, IconSun } from "./components/Icons";
import type { AnalystStatus } from "./lib/analyst";
import { api } from "./lib/api";
import { REPO_URL } from "./lib/project";
import { type Screen, useScreen } from "./lib/route";
import { type ThemePref, useTheme } from "./lib/theme";
import type { AsOfRange, BusinessType, Region, TableStatus } from "./lib/types";
import { BacktestView } from "./views/BacktestView";
import { DataView } from "./views/DataView";
import { HomeView } from "./views/HomeView";
import { WorkspaceView } from "./views/WorkspaceView";

const NAV: { id: Screen; label: string }[] = [
  { id: "home", label: "Overview" },
  { id: "workspace", label: "Workspace" },
  { id: "evidence", label: "Evidence" },
  { id: "data", label: "Data" },
];

const longDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-AU", { day: "numeric", month: "long", year: "numeric" });

const NEXT_THEME: Record<ThemePref, ThemePref> = { system: "light", light: "dark", dark: "system" };

export default function App() {
  const { pref, setPref, dark } = useTheme();
  const [screen, go] = useScreen();
  const [region, setRegion] = useState<Region | null>(null);
  const [types, setTypes] = useState<BusinessType[]>([]);
  const [tables, setTables] = useState<TableStatus[]>([]);
  const [range, setRange] = useState<AsOfRange | null>(null);
  const [analyst, setAnalyst] = useState<AnalystStatus | null>(null);
  const [businessType, setBusinessType] = useState("cafe");
  const [asOf, setAsOf] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [incoming, setIncoming] = useState<{ question: string; key: number } | null>(null);
  // Heavy screens stay mounted once visited, so switching never loses sites, chats or results.
  const [visited, setVisited] = useState<Set<Screen>>(() => new Set([screen]));
  useEffect(() => {
    setVisited((v) => (v.has(screen) ? v : new Set([...v, screen])));
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
    api.analystStatus()
      .then(setAnalyst)
      .catch(() => setAnalyst({ enabled: false, model: "anthropic/claude-haiku-5.5", provider: "OpenRouter" }));
  }, []);

  const selectedType = types.find((t) => t.id === businessType);
  const businessName = selectedType?.name ?? "Café";
  const ask = (question: string) => {
    setIncoming({ question, key: Date.now() });
    go("workspace");
  };
  const ThemeIcon = pref === "light" ? IconSun : pref === "dark" ? IconMoon : IconMonitor;

  const businessSelect = (
    <label className="field">
      <span className="field__label">Business</span>
      <select value={businessType} onChange={(e) => setBusinessType(e.target.value)}>
        {types.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
            {t.status === "draft" ? " (draft)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
  const workspaceControls = (
    <>
      {businessSelect}
      {range && (
        <label className="field">
          <span className="field__label">Data as of</span>
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
    </>
  );

  return (
    <div className={`app app--${screen}`}>
      <header className="topbar">
        <a className="brand" href="#" onClick={(e) => { e.preventDefault(); go("home"); }}>
          <Logo size={26} />
          <span className="brand__name">SiteScore</span>
        </a>
        <nav className="nav" aria-label="Screens">
          {NAV.map((s) => (
            <button
              key={s.id}
              className={`nav__link ${screen === s.id ? "is-on" : ""}`}
              aria-current={screen === s.id ? "page" : undefined}
              onClick={() => go(s.id)}
            >
              {s.label}
            </button>
          ))}
        </nav>
        <div className="topbar__controls">
          <DataBadge tables={tables} onClick={() => go("data")} />
          <a className="icon-btn" href={REPO_URL} target="_blank" rel="noreferrer" title="SiteScore on GitHub" aria-label="SiteScore on GitHub">
            <IconGithub size={18} />
          </a>
          <button
            className="icon-btn"
            onClick={() => setPref(NEXT_THEME[pref])}
            title={`Theme: ${pref} (click to change)`}
            aria-label={`Theme: ${pref}. Switch to ${NEXT_THEME[pref]}`}
          >
            <ThemeIcon size={18} />
          </button>
        </div>
      </header>

      {error && <div className="alert">{error}</div>}
      {screen === "workspace" && selectedType?.status === "draft" && (
        <div className="alert alert--info">
          The {selectedType.name.toLowerCase()} profile is a draft: its assumptions haven't been validated yet.
        </div>
      )}
      {screen === "workspace" && asOf && (
        <div className="alert alert--info">
          <strong>Looking back to {longDate(asOf)}.</strong> The model sees only data published by then (the map,
          patronage and approved developments as they were), as if you were choosing a site that day. Each site opens the
          month after.
        </div>
      )}

      {screen === "home" && (
        <HomeView region={region} businessName={businessName} types={types} tables={tables} analyst={analyst} onAsk={ask} go={go} />
      )}
      {region && visited.has("workspace") && (
        <div hidden={screen !== "workspace"}>
          <ErrorBoundary what="workspace">
            <WorkspaceView
              region={region}
              businessType={businessType}
              businessName={businessName}
              asOf={asOf}
              dark={dark}
              analyst={analyst}
              incoming={incoming}
              controls={workspaceControls}
            />
          </ErrorBoundary>
        </div>
      )}
      {region && visited.has("evidence") && (
        <div hidden={screen !== "evidence"}>
          <ErrorBoundary what="evidence screen">
            <BacktestView region={region} businessType={businessType} dark={dark} controls={businessSelect} />
          </ErrorBoundary>
        </div>
      )}
      {screen === "data" && <DataView region={region} types={types} tables={tables} />}
    </div>
  );
}
