import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Wordmark } from "./components/Brand";
import { type Command, CommandPalette } from "./components/CommandPalette";
import { DataBadge } from "./components/DataBadge";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { IconArrowUpRight, IconGithub, IconMonitor, IconMoon, IconSun } from "./components/Icons";
import { GridPulse } from "./components/GridPulse";
import { MaintenancePage, OfflineBanner } from "./components/ServerStatus";
import { Splash } from "./components/Splash";
import { StatusStrip } from "./components/StatusStrip";
import { type AnalystStatus, analystMode } from "./lib/analyst";
import { api } from "./lib/api";
import { prefetchHeatmap } from "./lib/hooks";
import { REPO_URL } from "./lib/project";
import { type Screen, useScreen } from "./lib/route";
import { type ThemePref, useTheme } from "./lib/theme";
import type { AsOfRange, BusinessType, Region, TableStatus } from "./lib/types";
import { BacktestView } from "./views/BacktestView";
import { DataView } from "./views/DataView";
import { HomeView } from "./views/HomeView";
import { type WorkspaceCommand, WorkspaceView } from "./views/WorkspaceView";

const NAV: { id: Screen; label: string }[] = [
  { id: "home", label: "Overview" },
  { id: "workspace", label: "Workspace" },
  { id: "evidence", label: "Evidence" },
  { id: "data", label: "Data" },
];

const longDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-AU", { day: "numeric", month: "long", year: "numeric" });

const NEXT_THEME: Record<ThemePref, ThemePref> = { system: "light", light: "dark", dark: "system" };
const SPLASH_KEY = "sitescore.splash-seen";

/** The nav with one pill that slides to the current screen. */
function Nav({ screen, go }: { screen: Screen; go: (s: Screen) => void }) {
  const nav = useRef<HTMLElement>(null);
  const [bar, setBar] = useState<{ left: number; width: number } | null>(null);
  useLayoutEffect(() => {
    const place = () => {
      const on = nav.current?.querySelector<HTMLElement>(".nav__link.is-on");
      if (on) setBar({ left: on.offsetLeft, width: on.offsetWidth });
    };
    place();
    document.fonts?.ready.then(place); // widths change once Inter has loaded
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [screen]);
  return (
    <nav className="nav" aria-label="Screens" ref={nav}>
      {bar && <span className="nav__bar" style={{ transform: `translateX(${bar.left}px)`, width: bar.width }} aria-hidden />}
      {NAV.map((s, i) => (
        <button
          key={s.id}
          className={`nav__link ${screen === s.id ? "is-on" : ""}`}
          aria-current={screen === s.id ? "page" : undefined}
          onClick={() => go(s.id)}
        >
          <span className="nav__index mono" aria-hidden>
            {String(i + 1).padStart(2, "0")}
          </span>
          {s.label}
        </button>
      ))}
    </nav>
  );
}

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
  // Start-up couldn't reach the server: the maintenance page replaces the screens.
  const [serverDown, setServerDown] = useState(false);
  const [incoming, setIncoming] = useState<{ question: string; key: number } | null>(null);
  const [seed, setSeed] = useState<{ site: { label: string; lat: number; lon: number }; key: number } | null>(null);
  const [command, setCommand] = useState<{ type: WorkspaceCommand; key: number } | null>(null);
  const [palette, setPalette] = useState(false);
  const [booted, setBooted] = useState({ region: false, types: false, data: false, range: false, analyst: false });
  const mark = (k: keyof typeof booted) => setBooted((b) => ({ ...b, [k]: true }));
  // First visit this session: a loading screen, then the screens mount as it lifts.
  const [intro, setIntro] = useState<"splash" | "leaving" | "done">(() => {
    try {
      return sessionStorage.getItem(SPLASH_KEY) ? "done" : "splash";
    } catch {
      return "splash";
    }
  });
  const leaveSplash = useCallback(() => setIntro("leaving"), []);
  const endSplash = useCallback(() => {
    setIntro("done");
    try {
      sessionStorage.setItem(SPLASH_KEY, "1");
    } catch {
      // private mode: it shows again next load, which is fine
    }
  }, []);
  const showScreens = intro !== "splash" && !serverDown;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  // Heavy screens stay mounted once visited, so switching never loses sites, chats or results.
  const [visited, setVisited] = useState<Set<Screen>>(() => new Set([screen]));
  useEffect(() => {
    setVisited((v) => (v.has(screen) ? v : new Set([...v, screen])));
  }, [screen]);

  useEffect(() => {
    prefetchHeatmap("cafe"); // the overview's map, ready when the loading screen lifts
    // Each start-up request ticks off its line on the loading screen as it lands.
    const fail = () => {
      setServerDown(true);
      setIntro("done"); // no loading screen for a server that isn't there
    };
    api.region().then((r) => { setRegion(r); mark("region"); }).catch(fail);
    api.businessTypes().then((t) => { setTypes(t); mark("types"); }).catch(fail);
    api.dataStatus().then((d) => { setTables(d); mark("data"); }).catch(fail);
    api.asOfRange().then((a) => { setRange(a); mark("range"); }).catch(fail);
    api.analystStatus()
      .then(setAnalyst)
      .catch(() => setAnalyst({ enabled: false, mode: "off", model: "anthropic/claude-haiku-5.5", provider: "OpenRouter" }))
      .finally(() => mark("analyst"));
  }, []);

  const selectedType = types.find((t) => t.id === businessType);
  const usedTables = tables.filter((t) => t.model_visible);
  const dataDetail = `${usedTables.filter((t) => t.provenance === "real").length}/${usedTables.length} real`;
  const businessName = selectedType?.name ?? "Café";
  const ask = (question: string) => {
    setIncoming({ question, key: Date.now() });
    go("workspace");
  };
  const openSite = (site: { label: string; lat: number; lon: number }) => {
    setSeed({ site, key: Date.now() });
    go("workspace");
  };
  const workspace = (type: WorkspaceCommand) => {
    setCommand({ type, key: Date.now() });
    go("workspace");
  };
  const commands = useMemo<Command[]>(() => [
    ...NAV.map((s) => ({ id: `go-${s.id}`, group: "Go to", label: s.label, run: () => go(s.id) })),
    { id: "demo", group: "Workspace", label: "Load the 3 demo sites", keywords: "example compare", run: () => workspace("demo") },
    { id: "find", group: "Workspace", label: "Find spots in a circle", keywords: "search best vacant", run: () => workspace("find") },
    { id: "heat", group: "Workspace", label: "Toggle the heat map", keywords: "hex opportunity layer", run: () => workspace("heat") },
    { id: "clear", group: "Workspace", label: "Clear all sites", keywords: "remove reset", run: () => workspace("clear") },
    ...types.map((t) => ({
      id: `type-${t.id}`, group: "Business", label: `${t.name}${t.status === "draft" ? " (draft)" : ""}`,
      hint: t.id === businessType ? "current" : undefined, run: () => setBusinessType(t.id),
    })),
    { id: "theme-light", group: "Theme", label: "Light", run: () => setPref("light") },
    { id: "theme-dark", group: "Theme", label: "Dark", keywords: "night", run: () => setPref("dark") },
    { id: "theme-system", group: "Theme", label: "Match the system", run: () => setPref("system") },
    { id: "repo", group: "Project", label: "Open the GitHub repository", keywords: "source code", run: () => window.open(REPO_URL, "_blank", "noopener") },
  ], [types, businessType]);
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
      {intro !== "done" && (
        <Splash
          onLeave={leaveSplash}
          onDone={endSplash}
          steps={[
            { id: "region", label: "region", done: booted.region, detail: region?.name.toLowerCase() },
            { id: "types", label: "business_types", done: booted.types, detail: `${types.length} profiles` },
            { id: "data", label: "data", done: booted.data, detail: dataDetail },
            { id: "range", label: "as_of_range", done: booted.range, detail: range ? `${range.min.slice(0, 4)}–${range.max.slice(0, 4)}` : undefined },
            { id: "analyst", label: "analyst", done: booted.analyst, detail: { live: "ready", replay: "recorded runs", off: "off" }[analystMode(analyst) ?? "off"] },
          ]}
        />
      )}
      <GridPulse />
      <StatusStrip region={region} businessType={businessType} tables={tables} asOf={asOf} onPalette={() => setPalette(true)} />
      <CommandPalette
        open={palette}
        onClose={() => setPalette(false)}
        commands={commands}
        onAsk={analyst && analystMode(analyst) !== "off" ? ask : undefined}
      />
      <header className="topbar">
        <a className="topbar__brand" href="#" aria-label="SiteScore overview" onClick={(e) => { e.preventDefault(); go("home"); }}>
          <Wordmark />
        </a>
        <Nav screen={screen} go={go} />
        <div className="topbar__controls">
          <div className="topbar__cell">
            <DataBadge tables={tables} onClick={() => go("data")} />
          </div>
          <button
            className="topbar__cell topbar__icon"
            onClick={() => setPref(NEXT_THEME[pref])}
            title={`Theme: ${pref} (click to change)`}
            aria-label={`Theme: ${pref}. Switch to ${NEXT_THEME[pref]}`}
          >
            <ThemeIcon size={18} />
          </button>
          <a className="topbar__cta" href={REPO_URL} target="_blank" rel="noreferrer">
            <IconGithub size={16} />
            <span>Star on GitHub</span>
            <IconArrowUpRight size={15} />
          </a>
        </div>
      </header>

      {serverDown ? <MaintenancePage /> : <OfflineBanner />}
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

      {showScreens && screen === "home" && (
        <div className="screen">
          <HomeView
            region={region}
            businessType={businessType}
            businessName={businessName}
            onBusinessType={setBusinessType}
            types={types}
            tables={tables}
            analyst={analyst}
            dark={dark}
            onAsk={ask}
            onOpenSite={openSite}
            onWorkspace={workspace}
            go={go}
          />
        </div>
      )}
      {showScreens && region && visited.has("workspace") && (
        <div className="screen" hidden={screen !== "workspace"}>
          <ErrorBoundary what="workspace">
            <WorkspaceView
              region={region}
              businessType={businessType}
              businessName={businessName}
              asOf={asOf}
              dark={dark}
              analyst={analyst}
              incoming={incoming}
              seed={seed}
              command={command}
              controls={workspaceControls}
            />
          </ErrorBoundary>
        </div>
      )}
      {showScreens && region && visited.has("evidence") && (
        <div className="screen" hidden={screen !== "evidence"}>
          <ErrorBoundary what="evidence screen">
            <BacktestView region={region} businessType={businessType} dark={dark} controls={businessSelect} />
          </ErrorBoundary>
        </div>
      )}
      {showScreens && screen === "data" && (
        <div className="screen">
          <DataView region={region} types={types} tables={tables} />
        </div>
      )}
    </div>
  );
}
