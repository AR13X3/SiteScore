import { useEffect, useState } from "react";
import { IconArrowRight, IconArrowUpRight, IconCheck, IconGithub, IconKey, IconPlus } from "../components/Icons";
import { CountUpText } from "../components/Motion";
import { licenceParts } from "../lib/format";
import { Kicker, PageHead } from "../components/PageHead";
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
      <PageHead kicker="data.sources(open=true)" title="Open data in, open model out.">
        <p className="muted page-top__lede">
          Every input is official or open data, dated by when it became public so the model can run "as of" any past day. Here's
          what feeds it right now, and the data that would make it better.
        </p>
      </PageHead>

      <section className="card coverage">
        <div className="coverage__card">
          <Kicker text="regions/" />
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
        <div className="coverage__card">
          <Kicker text="business_types/" />
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
        <div className="coverage__card">
          <Kicker text="model_inputs/" />
          <h2>Model inputs</h2>
          <div className="big-number">
            <CountUpText text={String(real)} />
            <span className="big-number__of">/{inputs.length || "–"}</span>
          </div>
          <p className="muted small">
            tables on real data. Mock data stands in for anything missing, with identical columns, so the app always runs.
          </p>
        </div>
      </section>

      <DataCatalog inputs={inputs} outcomes={outcomes} sources={sources} />

      <section className="section">
        <div className="section-head">
          <Kicker text="most_wanted/" />
          <h2>Data that would make SiteScore sharper</h2>
          <p className="muted">
            Pick one, open an issue to say you're on it, and send a pull request. Small contributions count: one region file or one
            CSV of openings is a real improvement.
          </p>
        </div>
        <div className="card wanted-grid">
          {WANTED.map((w, i) => (
            <a key={w.title} className="wanted" href={repoFile(w.where)} target="_blank" rel="noreferrer">
              <header>
                <span className="mono wanted__n">{String(i + 1).padStart(2, "0")}</span>
                <span className={`tag ${w.level === "Easy" ? "tag--easy" : ""}`}>{w.level}</span>
              </header>
              <h3>{w.title}</h3>
              <p>{w.why}</p>
              <span className="wanted__where mono">
                {w.where} <IconArrowUpRight size={14} />
              </span>
            </a>
          ))}
        </div>
      </section>

      <section className="steps-card card">
        <Kicker text="git clone && contribute/" />
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

    </main>
  );
}

type CatalogTab = "inputs" | "outcomes" | "sources";
const year = (iso: string) => new Date(`${iso}T00:00:00`).getFullYear() + new Date(`${iso}T00:00:00`).getMonth() / 12;

/**
 * Everything the app holds, in one place: what the model reads, what scores it, and
 * where it all comes from. One tab at a time, so each list gets the room to be read.
 */
function DataCatalog({ inputs, outcomes, sources }: { inputs: TableStatus[]; outcomes: TableStatus[]; sources: SourceInfo[] }) {
  const [tab, setTab] = useState<CatalogTab>("inputs");
  const realOf = (ts: TableStatus[]) => ts.filter((t) => t.provenance === "real").length;
  const keyed = sources.filter((x) => x.needs_key).length;
  const tabs: { id: CatalogTab; title: string; meta: string; note: string }[] = [
    { id: "inputs", title: "What the model reads", meta: `${inputs.length} tables · ${realOf(inputs)} real`,
      note: "Each row is visible to a prediction only once it was published, so the model can run as of any past day." },
    { id: "outcomes", title: "Outcome data", meta: `${outcomes.length} tables · backtest only`,
      note: "The model can never read these: they're how its predictions are scored." },
    { id: "sources", title: "Sources and licences", meta: `${sources.length} sources · ${keyed} need${keyed === 1 ? "s" : ""} a key`,
      note: "Where each source comes from, what it feeds, its licence, and whether it needs an API key." },
  ];
  const current = tabs.find((t) => t.id === tab)!;
  // One timeline and one row scale across both table lists, so they compare.
  const all = [...inputs, ...outcomes];
  const starts = all.flatMap((t) => (t.published_range ? [year(t.published_range[0])] : []));
  const ends = all.flatMap((t) => (t.published_range ? [year(t.published_range[1])] : []));
  const span: [number, number] = [Math.floor(Math.min(...starts, 2019)), Math.ceil(Math.max(...ends, 2026))];
  const maxRows = Math.max(...all.map((t) => t.rows ?? 0), 1);

  return (
    <section className="card catalog">
      <div className="card-head">
        <Kicker text="data.catalog()" />
        <h2>What's in the data</h2>
      </div>
      <div className="tab-cells" role="tablist" aria-label="Data catalog">
        {tabs.map((t, i) => (
          <button key={t.id} role="tab" aria-selected={t.id === tab} className={`tab-cell ${t.id === tab ? "is-on" : ""}`} onClick={() => setTab(t.id)}>
            <span className="tab-cell__n mono">{String(i + 1).padStart(2, "0")}</span>
            <span className="tab-cell__label">{t.title}</span>
            <span className="tab-cell__meta mono">{t.meta}</span>
          </button>
        ))}
      </div>
      <div className="catalog__panel" key={tab}>
        <p className="catalog__note muted small">{current.note}</p>
        {tab === "sources" ? (
          <SourceRows sources={sources} />
        ) : (
          <TableRows tables={tab === "inputs" ? inputs : outcomes} span={span} maxRows={maxRows} />
        )}
      </div>
    </section>
  );
}

function TableRows({ tables, span, maxRows }: { tables: TableStatus[]; span: [number, number]; maxRows: number }) {
  const x = (y: number) => ((y - span[0]) / (span[1] - span[0])) * 100;
  const ticks = [span[0], Math.round((span[0] + span[1]) / 2), span[1]];
  return (
    <div className="cat" role="table" aria-label="Tables">
      <div className="cat__row cat__row--head" role="row">
        <span role="columnheader">Table</span>
        <span role="columnheader">Source</span>
        <span role="columnheader">Status</span>
        <span role="columnheader">Rows</span>
        <span role="columnheader" className="cat__time-head">
          Published
          <span className="cat__ticks" aria-hidden>
            {ticks.map((t) => (
              <span key={t} style={{ left: `${x(t)}%` }}>{t}</span>
            ))}
          </span>
        </span>
      </div>
      {tables.map((t) => {
        const r = t.published_range;
        const a = r ? x(year(r[0])) : 0;
        const b = r ? x(year(r[1])) : 0;
        return (
          <div key={t.table} className="cat__row" role="row">
            <span role="cell" className="cat__name">
              <strong className="mono">{t.table}</strong>
              <span className="muted small">{t.description}</span>
            </span>
            <span role="cell" className="cat__source">{t.source}</span>
            <span role="cell">
              <span className={`prov prov--${t.provenance ?? "missing"}`} title={t.note || undefined}>
                <span className="prov__dot" />
                {t.provenance ?? "missing"}
              </span>
              {t.note && <span className="muted small block">{t.note}</span>}
            </span>
            <span role="cell" className="cat__rows">
              <span className="num">{t.rows?.toLocaleString("en-AU") ?? "–"}</span>
              <i aria-hidden><b style={{ width: `${((t.rows ?? 0) / maxRows) * 100}%` }} /></i>
            </span>
            <span role="cell" className="cat__time">
              <span className="cat__track" aria-hidden>
                {r && <i className={b - a < 1.5 ? "is-point" : ""} style={{ left: `${a}%`, width: `${Math.max(0, b - a)}%` }} />}
              </span>
              <span className="muted small">{range(r)}</span>
            </span>
          </div>
        );
      })}
    </div>
  );
}

function SourceRows({ sources }: { sources: SourceInfo[] }) {
  return (
    <div className="cat cat--sources" role="table" aria-label="Sources and licences">
      <div className="cat__row cat__row--head" role="row">
        <span role="columnheader">Source</span>
        <span role="columnheader">Used for</span>
        <span role="columnheader">Licence</span>
        <span role="columnheader">Key</span>
      </div>
      {sources.map((x) => (
        <div key={x.id} className="cat__row" role="row">
          <span role="cell" className="cat__name">
            <strong>{x.title}</strong>
            <span className="muted small">{x.provider}</span>
          </span>
          <span role="cell" className="cat__source">{x.used_for}</span>
          <span role="cell" className="cat__licences">
            {licenceParts(x.licence).map((l, i) => (
              <span key={i} className="cat__licence">
                <span className="tag">{l.name}</span>
                {l.note && <span className="muted small">{l.note}</span>}
              </span>
            ))}
          </span>
          <span role="cell">
            {x.needs_key ? (
              <span className="chip">
                <IconKey size={13} /> {x.key_configured ? "configured" : "not set"}
              </span>
            ) : (
              <span className="muted small">none needed</span>
            )}
          </span>
        </div>
      ))}
    </div>
  );
}
