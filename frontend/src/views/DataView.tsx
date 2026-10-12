import { useEffect, useState } from "react";
import { IconArrowRight, IconCheck, IconGithub, IconKey, IconPlus } from "../components/Icons";
import { api } from "../lib/api";
import { CONTRIBUTING_URL, ISSUES_URL, REPO_URL, repoFile } from "../lib/project";
import type { BusinessType, Region, SourceInfo, TableStatus } from "../lib/types";

interface Props {
  region: Region | null;
  types: BusinessType[];
  tables: TableStatus[];
}

const WANTED = [
  {
    title: "Commercial rents",
    level: "Medium",
    why: "Rent is an index on a typical-site rent today. NSW Valuer General land values or real asking rents would calibrate it.",
    where: "sitescore/model/rent.py",
  },
  {
    title: "Sales figures, even a few",
    level: "Easy",
    why: "Monthly takings from a handful of businesses (anonymised) would test the model far better than Google reviews can.",
    where: "backtests/cohorts/",
  },
  {
    title: "A new region",
    level: "Medium",
    why: "Copy the Parramatta region file, set the council code and bounding box, then run the pipeline. Census, OSM and planning data are national or state-wide.",
    where: "config/regions/parramatta.yaml",
  },
  {
    title: "A business type",
    level: "Easy",
    why: "A profile is one YAML file: who competes, what anchors help, customer segments, spend and costs. Gyms and childcare need validating.",
    where: "config/business_types/cafe.yaml",
  },
  {
    title: "Known openings",
    level: "Easy",
    why: "Businesses you know opened, with the month: a CSV row each. They sharpen the backtest beyond what OpenStreetMap history shows.",
    where: "backtests/cohorts/demo.csv",
  },
  {
    title: "Bus commuters",
    level: "Medium",
    why: "Only rail, metro and light-rail patronage is modelled. GTFS stop frequencies could add bus commuters.",
    where: "sitescore/pipeline/tfnsw.py",
  },
];

const range = (r: [string, string] | null) => {
  if (!r) return "–";
  const f = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-AU", { month: "short", year: "numeric" });
  return r[0] === r[1] ? f(r[0]) : `${f(r[0])} – ${f(r[1])}`;
};

export function DataView({ region, types, tables }: Props) {
  const [sources, setSources] = useState<SourceInfo[]>([]);
  useEffect(() => {
    api.sources().then(setSources).catch(() => setSources([]));
  }, []);
  const inputs = tables.filter((t) => t.model_visible);
  const outcomes = tables.filter((t) => !t.model_visible);
  const real = inputs.filter((t) => t.provenance === "real").length;

  return (
    <main className="page">
      <header className="page-head">
        <span className="crumb">Data & contributing</span>
        <h1>Open data in, open model out.</h1>
        <p className="muted">
          Every input is official or open data, dated by when it became public so the model can run "as of" any past day. Here's
          what feeds it right now, and the data that would make it better.
        </p>
      </header>

      <section className="coverage">
        <div className="coverage__card card">
          <h2>Regions</h2>
          <ul className="cov-list">
            {region && (
              <li className="is-ready">
                <IconCheck size={15} /> {region.name} <span className="tag">live</span>
              </li>
            )}
            <li className="is-wanted">
              <IconPlus size={15} />
              <a href={repoFile("config/regions/parramatta.yaml")} target="_blank" rel="noreferrer">
                Your council
              </a>
            </li>
          </ul>
        </div>
        <div className="coverage__card card">
          <h2>Business types</h2>
          <ul className="cov-list">
            {types.map((t) => (
              <li key={t.id} className={t.status === "ready" ? "is-ready" : "is-draft"}>
                {t.status === "ready" ? <IconCheck size={15} /> : <span className="dot-draft" />} {t.name}
                <span className="tag">{t.status === "ready" ? "ready" : "draft"}</span>
              </li>
            ))}
            <li className="is-wanted">
              <IconPlus size={15} />
              <a href={repoFile("config/business_types/cafe.yaml")} target="_blank" rel="noreferrer">
                Your trade
              </a>
            </li>
          </ul>
        </div>
        <div className="coverage__card card">
          <h2>Model inputs</h2>
          <div className="big-number">
            {real}
            <span>/{inputs.length || "–"}</span>
          </div>
          <p className="muted small">
            tables on real data. Mock data stands in for anything missing, with identical columns, so the app always runs.
          </p>
        </div>
      </section>

      <section className="card table-card">
        <div className="card-head">
          <h2>What the model reads</h2>
          <span className="muted card-head__note">Each row is visible to a prediction only once it was published.</span>
        </div>
        <TableList tables={inputs} />
      </section>

      <section className="card table-card">
        <div className="card-head">
          <h2>Outcome data (backtest only)</h2>
          <span className="muted card-head__note">The model can never read these: they're how its predictions are scored.</span>
        </div>
        <TableList tables={outcomes} />
      </section>

      <section className="section">
        <div className="section-head">
          <span className="crumb">Most wanted</span>
          <h2>Data that would make SiteScore sharper</h2>
          <p className="muted">
            Pick one, open an issue to say you're on it, and send a pull request. Small contributions count: one region file or one
            CSV of openings is a real improvement.
          </p>
        </div>
        <div className="wanted-grid">
          {WANTED.map((w) => (
            <article key={w.title} className="wanted card">
              <header>
                <h3>{w.title}</h3>
                <span className={`tag ${w.level === "Easy" ? "tag--easy" : ""}`}>{w.level}</span>
              </header>
              <p className="muted">{w.why}</p>
              <a className="wanted__where" href={repoFile(w.where)} target="_blank" rel="noreferrer">
                <code>{w.where}</code> <IconArrowRight size={14} />
              </a>
            </article>
          ))}
        </div>
      </section>

      <section className="steps-card card">
        <h2>Contribute in four steps</h2>
        <ol className="how">
          <li>
            <strong>Fork and install</strong>
            <code>python run.py install</code>
          </li>
          <li>
            <strong>Add your data or config</strong>
            <span className="muted">An adapter in sitescore/pipeline/, a YAML profile, or a cohort CSV.</span>
          </li>
          <li>
            <strong>Run the tests</strong>
            <code>python run.py test</code>
          </li>
          <li>
            <strong>Open a pull request</strong>
            <span className="muted">Say where the data comes from and its licence.</span>
          </li>
        </ol>
        <div className="oss__ctas">
          <a className="btn btn--primary" href={CONTRIBUTING_URL} target="_blank" rel="noreferrer">
            Read the contributing guide <IconArrowRight size={16} />
          </a>
          <a className="btn" href={ISSUES_URL} target="_blank" rel="noreferrer">
            Open an issue
          </a>
          <a className="btn btn--ghost" href={REPO_URL} target="_blank" rel="noreferrer">
            <IconGithub size={16} /> Repository
          </a>
        </div>
      </section>

      {sources.length > 0 && (
        <section className="card table-card">
          <div className="card-head">
            <h2>Sources and licences</h2>
          </div>
          <div className="table-scroll">
            <table className="bt-table">
              <thead>
                <tr>
                  <th scope="col">Source</th>
                  <th scope="col">Used for</th>
                  <th scope="col">Licence</th>
                  <th scope="col">Key</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <strong>{s.title}</strong>
                      <span className="muted small block">{s.provider}</span>
                    </td>
                    <td>{s.used_for}</td>
                    <td>{s.licence}</td>
                    <td>
                      {s.needs_key ? (
                        <span className="chip">
                          <IconKey size={13} /> {s.key_configured ? "configured" : "not set"}
                        </span>
                      ) : (
                        <span className="muted">none needed</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}

function TableList({ tables }: { tables: TableStatus[] }) {
  return (
    <div className="table-scroll">
      <table className="bt-table">
        <thead>
          <tr>
            <th scope="col">Table</th>
            <th scope="col">Source</th>
            <th scope="col">Status</th>
            <th scope="col" className="num">Rows</th>
            <th scope="col">Published</th>
          </tr>
        </thead>
        <tbody>
          {tables.map((t) => (
            <tr key={t.table}>
              <td>
                <strong>{t.table}</strong>
                <span className="muted small block">{t.description}</span>
              </td>
              <td>{t.source}</td>
              <td>
                <span className={`prov prov--${t.provenance ?? "missing"}`} title={t.note || undefined}>
                  <span className="prov__dot" />
                  {t.provenance ?? "missing"}
                </span>
                {t.note && <span className="muted small block">{t.note}</span>}
              </td>
              <td className="num">{t.rows?.toLocaleString("en-AU") ?? "–"}</td>
              <td>{range(t.published_range)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
