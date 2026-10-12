import { useState } from "react";
import {
  IconArrowRight,
  IconChat,
  IconChart,
  IconCheck,
  IconFile,
  IconGithub,
  IconPin,
  IconSearch,
} from "../components/Icons";
import type { AnalystStatus } from "../lib/analyst";
import { CONTRIBUTING_URL, REPO_URL } from "../lib/project";
import type { Screen } from "../lib/route";
import type { BusinessType, Region, TableStatus } from "../lib/types";

interface Props {
  region: Region | null;
  businessName: string;
  types: BusinessType[];
  tables: TableStatus[];
  analyst: AnalystStatus | null;
  onAsk: (question: string) => void;
  go: (s: Screen) => void;
}

const LAYERS = [
  ["Demand", "Residents, workers and commuters within walking reach, weighted by when they're around."],
  ["Demographic fit", "Local demographics against the business's customer profile: age, income, housing."],
  ["Anchors", "Stations, supermarkets, schools and hospitals that bring people past the door."],
  ["Competition", "A Huff gravity model over every rival, plus an 'elsewhere' option."],
  ["Customer agents", "Thousands of simulated customers choosing by distance, price, quality and habit."],
  ["Price response", "Nearby rivals re-price in best-response rounds after you open."],
  ["Time", "Ramp-up, seasons, school holidays and approved developments landing on schedule."],
  ["Uncertainty", "300 Monte Carlo scenarios give P10–P90 ranges and the chance of a loss."],
];

const CAPABILITIES = [
  { icon: IconSearch, title: "Find spots", text: "Score every corner in a circle, or only vacant shopfronts, and rank them by revenue or profit." },
  { icon: IconPin, title: "Compare sites", text: "Up to five candidates side by side: 36-month revenue, profit, estimated rent and chance of a loss." },
  { icon: IconChart, title: "See why", text: "Revenue is the product of the layers below, so every gap between two sites is explained." },
  { icon: IconChat, title: "Ask the analyst", text: "A language model that runs these tools for you, tests what-ifs and writes a decision brief." },
];

const compactCount = (n: number) =>
  new Intl.NumberFormat("en-AU", { notation: "compact", maximumFractionDigits: 1 }).format(n);

export function HomeView({ region, businessName, types, tables, analyst, onAsk, go }: Props) {
  const [q, setQ] = useState("");
  const used = tables.filter((t) => t.model_visible);
  const real = used.filter((t) => t.provenance === "real").length;
  const rows = tables.filter((t) => t.provenance === "real").reduce((a, t) => a + (t.rows ?? 0), 0);
  const b = businessName.toLowerCase();
  const examples = [
    `Best ${b} spot within 1 km of Parramatta station, ranked by profit`,
    "Compare Church St, Harris Park and Wentworth Point",
    "Are any vacant shopfronts near Westmead Hospital worth a look?",
  ];
  const ask = (text: string) => (text.trim() ? onAsk(text.trim()) : go("workspace"));

  return (
    <main className="page home">
      <section className="home-head">
        <div className="home-head__main">
          <span className="crumb">Open-source location intelligence</span>
          <h1 className="home-title">Where should your next business open?</h1>
          <p className="home-lede">
            SiteScore simulates the customers, competitors and rent at any street corner and projects 36 months of revenue,
            with ranges rather than a single guess. Built on official and open data, and tested against real openings.
          </p>
          <form
            className="ask-box"
            onSubmit={(e) => {
              e.preventDefault();
              ask(q);
            }}
          >
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={`Ask about a location, e.g. where to open a ${b} near…`}
              aria-label="Ask the analyst"
            />
            <button className="btn btn--dark" type="submit">
              {analyst?.enabled === false ? "Open workspace" : "Ask"} <IconArrowRight size={15} />
            </button>
          </form>
          <ul className="example-list">
            {examples.map((x) => (
              <li key={x}>
                <button onClick={() => ask(x)}>
                  <span>{x}</span>
                  <IconArrowRight size={14} />
                </button>
              </li>
            ))}
          </ul>
          {analyst?.enabled === false && (
            <p className="muted small">The analyst needs an OpenRouter key (the Workspace shows how). Everything else works without one.</p>
          )}
        </div>

        <aside className="card coverage-card">
          <header>
            <span className="muted small">Coverage</span>
            <h2>{region?.name ?? "–"}</h2>
          </header>
          <dl className="kv">
            <div>
              <dt>Business types</dt>
              <dd>
                {types.map((t) => (
                  <span key={t.id} className="tag">
                    {t.name}
                    {t.status === "draft" ? " · draft" : ""}
                  </span>
                ))}
              </dd>
            </div>
            <div>
              <dt>Model inputs on real data</dt>
              <dd className="num">{used.length ? `${real} of ${used.length}` : "–"}</dd>
            </div>
            <div>
              <dt>Rows of real data</dt>
              <dd className="num">{rows ? compactCount(rows) : "–"}</dd>
            </div>
            <div>
              <dt>Horizon</dt>
              <dd>36 months, monthly</dd>
            </div>
            <div>
              <dt>Scenarios per site</dt>
              <dd className="num">300</dd>
            </div>
            <div>
              <dt>Analyst</dt>
              <dd>{analyst ? (analyst.enabled ? analyst.model : "off (no key)") : "–"}</dd>
            </div>
          </dl>
          <footer className="coverage-card__foot">
            <button className="btn btn--small" onClick={() => go("data")}>
              Data sources
            </button>
            <button className="btn btn--small btn--accent" onClick={() => go("workspace")}>
              Open workspace <IconArrowRight size={14} />
            </button>
          </footer>
        </aside>
      </section>

      <section className="cap-grid">
        {CAPABILITIES.map((c) => (
          <article key={c.title} className="card cap">
            <span className="icon-tile">
              <c.icon size={18} />
            </span>
            <h3>{c.title}</h3>
            <p className="muted">{c.text}</p>
          </article>
        ))}
      </section>

      <section className="card model-card">
        <div className="card-head card-head--split">
          <div>
            <h2>How the model works</h2>
            <span className="muted small">Mature monthly revenue is exactly the product of these layers. Every assumption is in YAML.</span>
          </div>
          <button className="btn btn--small" onClick={() => go("workspace")}>
            Try it <IconArrowRight size={14} />
          </button>
        </div>
        <ol className="layer-table">
          {LAYERS.map(([name, text], i) => (
            <li key={name}>
              <span className="layer-table__n num">{String(i + 1).padStart(2, "0")}</span>
              <span className="layer-table__name">{name}</span>
              <span className="layer-table__text muted">{text}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="home-pair">
        <article className="card evidence-card">
          <div className="card-head">
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
          <div className="card-head">
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
        <span>SiteScore · MIT licence · built at Hack48 Sydney</span>
        <span className="muted">
          Data: ABS (CC BY 4.0), © OpenStreetMap contributors (ODbL), Transport for NSW, NSW Planning Portal. Projections are
          model estimates, not advice.
        </span>
      </footer>
    </main>
  );
}
