import { useEffect, useMemo, useRef, useState } from "react";
import {
  IconArrowRight,
  IconArrowUpRight,
  IconChat,
  IconChart,
  IconCheck,
  IconFile,
  IconGithub,
  IconPin,
  IconSearch,
} from "../components/Icons";
import { ModelEquation } from "../components/ModelEquation";
import { StatBand } from "../components/StatBand";
import { BlockReveal, ScrambleText, useTypewriter } from "../components/Motion";
import { OpportunityMap, type Probe } from "../components/OpportunityMap";
import type { AnalystStatus } from "../lib/analyst";
import { api } from "../lib/api";
import { heatIndex } from "../lib/heat";
import { useHeatmap } from "../lib/hooks";
import { CONTRIBUTING_URL, REPO_URL } from "../lib/project";
import type { Screen } from "../lib/route";
import type { BusinessType, Region, SimulationResult, SiteSimulation, TableStatus } from "../lib/types";
import type { WorkspaceCommand } from "./WorkspaceView";

interface Props {
  region: Region | null;
  businessType: string;
  businessName: string;
  onBusinessType: (id: string) => void;
  types: BusinessType[];
  tables: TableStatus[];
  analyst: AnalystStatus | null;
  dark: boolean;
  onAsk: (question: string) => void;
  onOpenSite: (site: { label: string; lat: number; lon: number }) => void;
  onWorkspace: (command: WorkspaceCommand) => void;
  go: (s: Screen) => void;
}

type Action = "find" | "demo" | "why" | "ask";
const CAPABILITIES: { icon: typeof IconSearch; code: string; title: string; text: string; cta: string; action: Action }[] = [
  { icon: IconSearch, code: "spots.find()", title: "Find spots", cta: "Open the finder", action: "find",
    text: "Score every corner in a circle, or only vacant shopfronts, and rank them by revenue or profit." },
  { icon: IconPin, code: "sites.compare()", title: "Compare sites", cta: "Load 3 demo sites", action: "demo",
    text: "Up to five candidates side by side: 36-month revenue, profit, estimated rent and chance of a loss." },
  { icon: IconChart, code: "forecast.explain()", title: "See why", cta: "See the equation", action: "why",
    text: "Revenue is the product of the layers above, so every gap between two sites is explained." },
  { icon: IconChat, code: "analyst.ask()", title: "Ask the analyst", cta: "Ask a question", action: "ask",
    text: "A language model that runs these tools for you, tests what-ifs and writes a decision brief." },
];

/** One capability as a cell you can press: it fills with ink from the bottom when pointed at. */
function CapCell({ c, n, onRun }: { c: (typeof CAPABILITIES)[number]; n: number; onRun: () => void }) {
  const [replay, setReplay] = useState(0);
  return (
    <button className="cap" onClick={onRun} onMouseEnter={() => setReplay((r) => r + 1)}>
      <span className="cap__top">
        <span className="mono cap__n">{String(n).padStart(2, "0")}</span>
        <ScrambleText className="cap__code" text={c.code} replay={replay} />
      </span>
      <span className="icon-tile">
        <c.icon size={18} />
      </span>
      <span className="cap__title">{c.title}</span>
      <span className="cap__text">{c.text}</span>
      <span className="cap__go mono">
        {c.cta} <IconArrowUpRight size={14} />
      </span>
    </button>
  );
}


/** "Near Parramatta Square": the closest named anchor, else rival, within a short walk. */
function placeLabel(sim: SiteSimulation): string {
  const details = (key: string) => sim.mature.layers.find((l) => l.key === key)?.details ?? {};
  type Named = { name?: string; distance_m: number };
  const closest = (list: Named[], within: number) =>
    list.filter((x) => x.name && x.distance_m <= within).sort((a, b) => a.distance_m - b.distance_m)[0];
  const near =
    closest((details("anchors").anchors ?? []) as Named[], 300) ??
    closest((details("competition").top_competitors ?? []) as Named[], 200);
  return near ? `Near ${near.name}` : `${sim.site.lat.toFixed(4)}, ${sim.site.lon.toFixed(4)}`;
}

export function HomeView(props: Props) {
  const { region, businessType, businessName, onBusinessType, types, tables, analyst, dark, onAsk, onOpenSite, onWorkspace, go } = props;
  const [q, setQ] = useState("");
  const askInput = useRef<HTMLInputElement>(null);
  const { heat, error: heatError } = useHeatmap(businessType, null);
  const index = useMemo(() => (heat ? heatIndex(heat) : null), [heat]);
  const [probe, setProbe] = useState<Probe | null>(null);
  const [result, setResult] = useState<{ key: number; sim: SimulationResult } | null>(null);
  const [scoring, setScoring] = useState(false);
  const [probeError, setProbeError] = useState<string | null>(null);
  const seq = useRef(0);
  const opened = useRef(false);

  // Open on the CBD so the card and the equation have something to show straight away.
  useEffect(() => {
    if (region && !opened.current) {
      opened.current = true;
      setProbe({ lat: region.map.center[0], lon: region.map.center[1], key: Date.now() });
    }
  }, [region]);

  // The full model at the probe: central estimate first (~1 s), then the 300-scenario range.
  useEffect(() => {
    if (!probe) return;
    const mine = ++seq.current;
    const live = () => mine === seq.current;
    const body = { business_type: businessType, sites: [{ id: "probe", label: "Probe", lat: probe.lat, lon: probe.lon }] };
    setScoring(true);
    setProbeError(null);
    (async () => {
      try {
        const base = await api.simulate(body);
        if (!live()) return;
        setResult({ key: probe.key, sim: base });
        setScoring(false);
        const full = await api.simulate({ ...body, uncertainty: true });
        if (live()) setResult({ key: probe.key, sim: full });
      } catch (e) {
        if (live()) {
          setScoring(false);
          setProbeError((e as Error).message);
        }
      }
    })();
  }, [probe, businessType]);

  const sim = result?.sim.sites[0] ?? null;
  const odds = result?.sim.uncertainty?.sites[0];
  const fresh = !!probe && result?.key === probe.key && !scoring;
  const label = sim ? placeLabel(sim) : "Parramatta CBD";

  const b = businessName.toLowerCase();
  const examples = [
    `Best ${b} spot within 1 km of Parramatta station, ranked by profit`,
    "Compare Church St, Harris Park and Wentworth Point",
    "Are any vacant shopfronts near Westmead Hospital worth a look?",
  ];
  const ask = (text: string) => (text.trim() ? onAsk(text.trim()) : go("workspace"));
  const ghost = useTypewriter(examples, !q);
  // The ghost question scrolls like a terminal line: the newest characters stay in view.
  const field = useRef<HTMLSpanElement>(null);
  const [fits, setFits] = useState(60);
  useEffect(() => {
    const el = field.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setFits(Math.max(12, Math.floor((el.clientWidth - 70) / 8.45))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const ghostText = ghost.text.length > fits ? `…${ghost.text.slice(-(fits - 1))}` : ghost.text;
  const run = (a: Action) => {
    if (a === "find" || a === "demo") onWorkspace(a);
    else if (a === "why") document.getElementById("how")?.scrollIntoView({ behavior: "smooth", block: "start" });
    else {
      askInput.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      askInput.current?.focus({ preventScroll: true });
    }
  };

  return (
    <main className="page home">
      <section className="hero">
        <div className="hero__copy">
          <ScrambleText className="kicker" start="mount" text="open-source_location_intelligence/" cursor />
          <BlockReveal className="home-title" text="Where should your next business open?" />
          <p className="home-lede">
            SiteScore simulates the customers, competitors and rent at any street corner and projects 36 months of revenue,
            with ranges rather than a single guess. Every hexagon on the map is a corner the model has already scored.
          </p>
          <form
            className="ask"
            onSubmit={(e) => {
              e.preventDefault();
              ask(q);
            }}
          >
            <span className="ask__prompt mono" aria-hidden>
              ask&gt;
            </span>
            <span className="ask__field" ref={field}>
              <input
                ref={askInput}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => {
                  // Tab takes the question being typed in the background.
                  if (e.key === "Tab" && !q && ghost.text) {
                    e.preventDefault();
                    setQ(examples[ghost.line]);
                  }
                }}
                aria-label="Ask the analyst about a location"
              />
              {!q && (
                <span className="ask__ghost mono" aria-hidden>
                  {ghostText}
                  <span className="block-cursor" />
                </span>
              )}
              {!q && ghost.text && (
                <kbd className="ask__tab" aria-hidden>
                  Tab
                </kbd>
              )}
            </span>
            <button className="ask__go" type="submit">
              {analyst?.enabled === false ? "Open workspace" : "Ask"} <IconArrowUpRight size={16} />
            </button>
          </form>
          <ul className="example-list">
            {examples.map((x, i) => (
              <li key={x}>
                <button onClick={() => ask(x)}>
                  <span className="example-list__n mono">{String(i + 1).padStart(2, "0")}</span>
                  <span className="example-list__text">{x}</span>
                  <IconArrowUpRight size={15} />
                </button>
              </li>
            ))}
          </ul>
          {analyst?.enabled === false && (
            <p className="muted small">The analyst needs an OpenRouter key (the Workspace shows how). Everything else works without one.</p>
          )}
        </div>

        <div className="card hero-map">
          {region ? (
            <OpportunityMap
              region={region}
              dark={dark}
              heat={heat}
              index={index}
              heatError={heatError}
              types={types}
              businessType={businessType}
              businessName={businessName}
              onBusinessType={onBusinessType}
              probe={probe}
              sim={fresh ? sim : null}
              odds={fresh ? odds : undefined}
              label={label}
              scoring={scoring}
              onProbe={(lat, lon) => setProbe({ lat, lon, key: Date.now() })}
              onClear={() => setProbe(null)}
              onOpen={() => sim && onOpenSite({ label, lat: sim.site.lat, lon: sim.site.lon })}
              onExplain={() => document.getElementById("how")?.scrollIntoView({ behavior: "smooth", block: "start" })}
            />
          ) : (
            <div className="hero-map__wait skeleton" />
          )}
          {probeError && <div className="hero-map__error">{probeError}</div>}
        </div>
      </section>

      <StatBand
        heat={heat}
        index={index}
        tables={tables}
        sim={sim}
        odds={odds}
        dark={dark}
        onData={() => go("data")}
        onWorkspace={() => go("workspace")}
      />

      <div id="how" className="anchor-target">
        <ModelEquation sim={sim} odds={odds} label={label} onTry={() => go("workspace")} />
      </div>

      <section className="card cap-grid" aria-label="What you can do">
        {CAPABILITIES.map((c, i) => (
          <CapCell key={c.title} c={c} n={i + 1} onRun={() => run(c.action)} />
        ))}
      </section>

      <section className="home-pair">
        <article className="card evidence-card">
          <div className="card-head card-head--stack">
            <ScrambleText className="kicker" text="evidence.backtest()" />
            <h2>Tested against real openings</h2>
          </div>
          <p className="muted">
            Every café that opened since late 2022 is predicted using only data published before it opened, then compared
            with what happened. Results are published as they are, including where the model doesn't yet beat plain foot
            traffic.
          </p>
          <ol className="timeline">
            <li>
              <span className="timeline__date">28 Jun 2022</span>
              <strong>Census 2021 is published</strong>
              <span className="muted">It describes August 2021, but the model can't see it before this date.</span>
            </li>
            <li>
              <span className="timeline__date">Day before opening</span>
              <strong>The café is predicted</strong>
              <span className="muted">With the map, patronage and approvals as they were that day, and without itself.</span>
            </li>
            <li className="is-now">
              <span className="timeline__date">Today</span>
              <strong>Reality is scored</strong>
              <span className="muted">Reviews per month, rating, closures within 18 months, still trading.</span>
            </li>
          </ol>
          <button className="btn btn--small" onClick={() => go("evidence")}>
            See the evidence <IconArrowRight size={14} />
          </button>
        </article>

        <article className="card contribute-card">
          <div className="card-head card-head--stack">
            <ScrambleText className="kicker" text="git clone && contribute/" />
            <h2>Contribute</h2>
          </div>
          <p className="muted">
            One council and one trade are covered well. The model is region-agnostic and every profile is a YAML file.
          </p>
          <ul className="check-list">
            <li>
              <IconCheck size={15} />
              <span>
                <strong>A region:</strong> one file with a council code and a bounding box
              </span>
            </li>
            <li>
              <IconCheck size={15} />
              <span>
                <strong>A business type:</strong> gyms and childcare are drafts; bakeries, pharmacies and barbers are open
              </span>
            </li>
            <li>
              <IconCheck size={15} />
              <span>
                <strong>Ground truth:</strong> opening dates, commercial rents, a few months of takings
              </span>
            </li>
          </ul>
          <div className="hatch contribute-card__band">
            <a className="btn btn--small btn--dark" href={REPO_URL} target="_blank" rel="noreferrer">
              <IconGithub size={15} /> Repository
            </a>
            <a className="btn btn--small" href={CONTRIBUTING_URL} target="_blank" rel="noreferrer">
              <IconFile size={15} /> Contributing guide
            </a>
            <button className="btn btn--small" onClick={() => go("data")}>
              Most wanted data
            </button>
          </div>
        </article>
      </section>

      <footer className="footer">
        <span>SiteScore · MIT licence · open source</span>
        <span className="muted">
          Data: ABS (CC BY 4.0), © OpenStreetMap contributors (ODbL), Transport for NSW, NSW Planning Portal. Projections are
          model estimates, not advice.
        </span>
      </footer>
    </main>
  );
}
