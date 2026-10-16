import { Fragment, type ReactNode, useEffect, useMemo, useState } from "react";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { LadderExplorer, ladderVerdict } from "../components/LadderChart";
import { CountUpText } from "../components/Motion";
import { Kicker, PageHead } from "../components/PageHead";
import { type MapPoint, PointsMap } from "../components/PointsMap";
import { api } from "../lib/api";
import { useElapsed } from "../lib/hooks";
import { money, pct } from "../lib/format";
import { ORDINAL_BINS, STATUS, ordinalColor, token } from "../lib/theme";
import type {
  BacktestResult,
  BacktestRow,
  Cohort,
  CrossSectionResult,
  HorizonStatus,
  OutcomeComparison,
  Region,
  ThirdRow,
} from "../lib/types";

type Mode = "backtest" | "today";

interface Props {
  region: Region;
  businessType: string;
  dark: boolean;
  /** The business-type selector, shown with this page's controls. */
  controls?: ReactNode;
}

const dateShort = (iso: string | null) =>
  iso ? new Date(`${iso}T00:00:00`).toLocaleDateString("en-AU", { month: "short", year: "numeric" }) : "–";
const num2 = (v: number | null) => (v === null ? "n/a" : v.toFixed(2));

export function BacktestView({ region, businessType, dark, controls }: Props) {
  const [mode, setMode] = useState<Mode>("backtest");
  const [cohorts, setCohorts] = useState<Cohort[]>([]);
  const [cohort, setCohort] = useState("osm");
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [today, setToday] = useState<CrossSectionResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const elapsed = useElapsed(loading);

  useEffect(() => {
    api.cohorts().then(setCohorts).catch(() => setCohorts([]));
  }, []);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    const run = mode === "backtest"
      ? api.backtest(cohort, businessType).then((r) => live && setBacktest(r))
      : api.crossSection(businessType).then((r) => live && setToday(r));
    run
      .catch((e: Error) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [mode, cohort, businessType]);

  const shown = mode === "backtest" ? backtest : today;
  return (
    <main className="bt page">
      <PageHead
        kicker={mode === "backtest" ? "evidence.backtest(time_safe=true)" : "evidence.cross_section(today)"}
        title="Would SiteScore have picked the winners?"
        aside={
          <div className="bt-controls">
            {controls}
            <div className="segmented" role="group" aria-label="Which test">
              <button className={mode === "backtest" ? "is-on" : ""} aria-pressed={mode === "backtest"} onClick={() => setMode("backtest")}>
                Backtest (time-safe)
              </button>
              <button className={mode === "today" ? "is-on" : ""} aria-pressed={mode === "today"} onClick={() => setMode("today")}>
                Today's cafés (not time-safe)
              </button>
            </div>
            {mode === "backtest" && cohorts.length > 1 && (
              <label className="field">
                <span className="muted">Cohort</span>
                <select value={cohort} onChange={(e) => setCohort(e.target.value)}>
                  {cohorts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
        }
      >
        <p className="muted page-top__lede">
          {mode === "backtest"
            ? "Each café is predicted using only data published before it opened, then compared with what happened."
            : "Every café open today, scored with today's data. A bigger sample, but not a fair test of prediction."}
        </p>
      </PageHead>

      {error && <div className="alert alert--inline">{error}</div>}
      {loading && (
        <div className="bt-loading card" role="status">
          <span className="spinner" aria-hidden />
          <span>
            {mode === "backtest"
              ? "Predicting every café as of the day before it opened, then gathering what happened"
              : "Scoring every café on today's map against its rivals"}
            … {elapsed}s <span className="muted">(about 20–30 s the first time, instant after)</span>
          </span>
        </div>
      )}
      {!loading && !shown && !error && <div className="card bt-empty muted">No results yet.</div>}

      <div className={loading ? "is-loading" : ""}>
        {mode === "backtest" && backtest && <TimeSafe result={backtest} region={region} dark={dark} />}
        {mode === "today" && today && <Today result={today} region={region} dark={dark} />}
      </div>
    </main>
  );
}

// --- Time-safe backtest ------------------------------------------------------------------

function statusMeta(status: HorizonStatus, months: number) {
  return {
    survived: { label: `Survived ${months} months`, fill: STATUS.good, hollow: false },
    closed: { label: `Closed within ${months} months`, fill: STATUS.critical, hollow: false },
    unknown: { label: "Can't tell", fill: token("--text-muted"), hollow: false },
    censored: { label: "Too new to judge", fill: "", hollow: true },
  }[status];
}

function StatusChip({ status, months }: { status: HorizonStatus; months: number }) {
  const m = statusMeta(status, months);
  return (
    <span className="chip">
      <span className={`chip__dot ${m.hollow ? "is-hollow" : ""}`} style={m.hollow ? undefined : { background: m.fill }} />
      {m.label}
    </span>
  );
}

const capitalise = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

const SOURCE_NAMES: Record<string, string> = {
  osm: "OpenStreetMap", google: "Google", overture: "Overture", foursquare: "Foursquare", asic: "ASIC",
};

function TimeSafe({ result, region, dark }: { result: BacktestResult; region: Region; dark: boolean }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const s = result.survival;
  const months = s.horizon_months;
  const judged = s.status_counts.closed + s.status_counts.survived;
  const discovered = Object.values(result.opening_checks).reduce((a, b) => a + b, 0);
  const excluded = (result.opening_checks.older ?? 0) + (result.opening_checks.remapped ?? 0);
  const hasGoogle = result.outcome_sources.includes("google");
  const churn = result.ladder.find((l) => l.outcome === "site_churn");
  const reviews = result.ladder.find((l) => l.outcome === "reviews_per_month");
  const rungs = reviews?.available ? reviews.steps : [];
  const fullRung = rungs.find((st) => st.key === "full");

  const points = useMemo<MapPoint[]>(
    () =>
      result.rows.map((r) => {
        const st = r.actual.horizon?.status ?? "unknown";
        const m = statusMeta(st, months);
        return {
          id: r.osm_id || r.name,
          lat: r.lat,
          lon: r.lon,
          fill: m.fill,
          hollow: m.hollow,
          tooltip: (
            <>
              <strong>{r.name}</strong>
              <br />#{r.predicted_rank} predicted · {money(r.predicted_score)} over {result.score_months} months
              <br />
              {m.label}
            </>
          ),
        };
      }),
    [result, months, dark],
  );

  const select = (id: string) => {
    setSelected(id);
    setExpanded((e) => (e === id ? null : id));
    document.getElementById(`bt-row-${id}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  };

  return (
    <>
      <div className="verdict card">
        <Kicker text="findings/" />
        <h2>What it shows so far</h2>
        <ul>
          {s.status_counts.closed === 0 ? (
            <li>
              <strong>No survival signal yet.</strong> None of the {judged} openings that can be judged closed within {months}{" "}
              months, so survival can't separate good sites from bad ones.
            </li>
          ) : (
            <li>
              {s.status_counts.closed} of {judged} judged openings closed within {months} months. Survivors ranked above
              closures: model {num2(s.auc)} vs foot traffic {num2(s.baseline_auc)} (0.5 = chance).
            </li>
          )}
          {churn?.available && <li>{ladderVerdict(churn)}</li>}
          {reviews?.available && fullRung && (
            <li>
              <strong>Google reviews per month</strong> ({rungs[0].n} cafés): full model {num2(fullRung.spearman)} vs foot
              traffic only {num2(rungs[0].spearman)} (Spearman). {ladderVerdict(reviews)}
            </li>
          )}
          {!hasGoogle && (
            <li>
              <strong>The missing measure is trading performance.</strong> Without Google reviews there is no way to tell a
              busy café from a quiet one, and that's the outcome that would settle it.
            </li>
          )}
        </ul>
      </div>

      <div className="card kpis">
        <Tile label="Real openings scored" value={String(result.accuracy.n)}
          note={discovered ? `of ${discovered} first mapped · ${excluded} older or re-mapped excluded` : `from the ${result.cohort} cohort`} />
        <Tile label={`Closed within ${months} months`} value={`${s.status_counts.closed} of ${judged}`}
          note={`${s.status_counts.unknown} can't tell · ${s.status_counts.censored} too new`} />
        <Tile label="Pairs ranked correctly" value={result.accuracy.pairwise_accuracy === null ? "n/a" : pct(result.accuracy.pairwise_accuracy)}
          note={`foot traffic only: ${result.accuracy.baseline_pairwise_accuracy === null ? "n/a" : pct(result.accuracy.baseline_pairwise_accuracy)} · 50% = coin flip`} />
        <Tile label="Spots without closures ranked higher" value={num2(s.site_churn_auc)}
          note={`foot traffic only: ${num2(s.baseline_site_churn_auc)} · 0.5 = chance`} />
      </div>

      <div className="bt-grid">
        <section className="card bt-map">
          <ErrorBoundary what="map">
            <PointsMap region={region} points={points} selectedId={selected} onSelect={select} label="Map of the backtest cohort" />
          </ErrorBoundary>
          <div className="map-legend map-legend--static">
            {(["survived", "unknown", "closed", "censored"] as const).map((st) => (
              <div key={st}>
                <StatusChip status={st} months={months} /> <span className="muted">{s.status_counts[st]}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="card bt-side">
          <Kicker text="opening_check/" />
          <h2>Opening check</h2>
          <p className="muted small">
            "First mapped" often means an old café mapped for the first time, so each one is checked against Foursquare,
            ASIC and the map's own history.
          </p>
          <OpeningChecks checks={result.opening_checks} />
          <Kicker text="closures.by_third()" />
          <h2>Closures by predicted third</h2>
          <ThirdsCompare model={s.by_third} baseline={s.baseline_by_third} />
        </section>
      </div>

      <Ladders ladder={result.ladder} />

      <OutcomeTable result={result} months={months} selected={selected} expanded={expanded} onSelect={select} />

      <div className="bt-grid bt-grid--even">
        <Caveats caveats={result.caveats} />
        {result.skipped.length > 0 && (
          <section className="card bt-notes">
            <details>
              <summary>
                <h2>Not scored ({result.skipped.length})</h2>
              </summary>
              <ul className="skipped">
                {result.skipped.map((k, i) => (
                  <li key={i}>
                    <strong>{k.name}</strong> <span className="muted">{k.reason}</span>
                  </li>
                ))}
              </ul>
            </details>
          </section>
        )}
      </div>
    </>
  );
}

const OPENING_LABELS: Record<string, string> = {
  new: "Confirmed new",
  unverified: "Unverified (kept)",
  older: "Older café, mapped late (excluded)",
  remapped: "Already on the map (excluded)",
};

type Filter = HorizonStatus | "all";
const FILTERS: { id: Filter; label: (months: number) => string }[] = [
  { id: "all", label: () => "All" },
  { id: "survived", label: (m) => `Survived ${m} mo` },
  { id: "closed", label: () => "Closed" },
  { id: "unknown", label: () => "Can't tell" },
  { id: "censored", label: () => "Too new" },
];

/**
 * Every scored opening, grouped by where the model ranked it (top, middle and bottom
 * third), so the question "did the top third do better?" reads straight off the table.
 * Filter by outcome; a row opens to its evidence.
 */
function OutcomeTable({ result, months, selected, expanded, onSelect }: {
  result: BacktestResult; months: number; selected: string | null; expanded: string | null; onSelect: (id: string) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const rows = useMemo(() => [...result.rows].sort((a, b) => a.predicted_rank - b.predicted_rank), [result]);
  const statusOf = (r: BacktestRow): HorizonStatus => r.actual.horizon?.status ?? "unknown";
  const counts = (st: Filter) => (st === "all" ? rows.length : rows.filter((r) => statusOf(r) === st).length);
  const maxScore = Math.max(...rows.map((r) => r.predicted_score), 1);
  const third = Math.ceil(rows.length / 3);
  const groups = [
    { id: "top_third", title: "Top third", rows: rows.slice(0, third) },
    { id: "middle_third", title: "Middle third", rows: rows.slice(third, third * 2) },
    { id: "bottom_third", title: "Bottom third", rows: rows.slice(third * 2) },
  ].filter((g) => g.rows.length);

  return (
    <section className="card bt-table-card">
      <div className="card-head card-head--split">
        <div>
          <Kicker text="predicted.vs(actual)" />
          <h2>Predicted vs what happened</h2>
          <span className="muted small">
            Ranked by the model with data up to each opening; open a row for its evidence.
          </span>
        </div>
        <div className="segmented" role="group" aria-label="Filter by outcome">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              className={filter === f.id ? "is-on" : ""}
              aria-pressed={filter === f.id}
              disabled={f.id !== "all" && counts(f.id) === 0}
              onClick={() => setFilter(f.id)}
            >
              {f.label(months)} <span className="seg-count">{counts(f.id)}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="table-scroll">
        <table className="bt-table outcome-table">
          <thead>
            <tr>
              <th scope="col">Rank</th>
              <th scope="col">Café</th>
              <th scope="col">Opened</th>
              <th scope="col">Predicted, first {result.score_months} months</th>
              <th scope="col">{months}-month outcome</th>
              <th scope="col">Today</th>
              <th scope="col" className="num">Closures at spot</th>
            </tr>
          </thead>
          {groups.map((g) => {
            const shown = g.rows.filter((r) => filter === "all" || statusOf(r) === filter);
            const closed = g.rows.filter((r) => statusOf(r) === "closed").length;
            const judged = g.rows.filter((r) => ["closed", "survived"].includes(statusOf(r))).length;
            const spot = g.rows.reduce((a, r) => a + (r.actual.horizon?.site_closures ?? 0), 0) / g.rows.length;
            return (
              <tbody key={g.id}>
                <tr className="group-row">
                  <td colSpan={7}>
                    <span className="mono group-row__code">{g.id}/</span>
                    <strong>{g.title}</strong>
                    <span className="group-row__stats">
                      <span>ranks {g.rows[0].predicted_rank}–{g.rows[g.rows.length - 1].predicted_rank}</span>
                      <span>{closed} of {judged} judged closed</span>
                      <span>{spot.toFixed(2)} closures per spot</span>
                    </span>
                  </td>
                </tr>
                {shown.map((r) => {
                  const id = r.osm_id || r.name;
                  return (
                    <Fragment key={id}>
                      <tr
                        id={`bt-row-${id}`}
                        className={`${selected === id ? "is-selected" : ""} is-clickable`}
                        onClick={() => onSelect(id)}
                        aria-expanded={expanded === id}
                      >
                        <td className="mono outcome-table__rank">{String(r.predicted_rank).padStart(2, "0")}</td>
                        <td>
                          <span className="outcome-table__name">{r.name}</span>
                          {r.opening_check && <span className="tag">{r.opening_check}</span>}
                        </td>
                        <td className="muted">{dateShort(r.opened)}</td>
                        <td>
                          <span className="score-bar">
                            <span className="num">{money(r.predicted_score)}</span>
                            <i aria-hidden><b style={{ width: `${(r.predicted_score / maxScore) * 100}%` }} /></i>
                          </span>
                        </td>
                        <td>{r.actual.horizon ? <StatusChip status={r.actual.horizon.status} months={months} /> : "–"}</td>
                        <td>{r.actual.still_open === null ? <span className="muted">?</span> : r.actual.still_open ? "Trading" : "Closed"}</td>
                        <td className="num">{r.actual.horizon?.site_closures ?? "–"}</td>
                      </tr>
                      {expanded === id && (
                        <tr className="evidence-row">
                          <td colSpan={7}>
                            <Evidence row={r} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
                {shown.length === 0 && (
                  <tr className="group-row group-row--empty">
                    <td colSpan={7} className="muted small">None in this third.</td>
                  </tr>
                )}
              </tbody>
            );
          })}
        </table>
      </div>
    </section>
  );
}

function Evidence({ row: r }: { row: BacktestRow }) {
  const h = r.actual.horizon;
  const facts: [string, ReactNode][] = [
    ["opening", <>{r.opened_note}{r.opening_detail && <> · {r.opening_check}: {r.opening_detail}</>}</>],
    ["predicted_with", <>data published up to {r.data_cutoff ?? r.as_of} (as of {r.as_of})</>],
  ];
  if (h) {
    facts.push([`outcome_by_${h.horizon.slice(0, 7)}`, <>
      {h.detail}
      {h.failure && <> · {h.failure === "operator" ? "operator failure (another café took over)" : h.failure === "site" ? "site failure" : "type unknown"}</>}
    </>]);
    facts.push(["same_spot", h.site_closures === 0
      ? "no café closures here since 2019"
      : `${h.site_closures} café closure${h.site_closures > 1 ? "s" : ""} here since 2019 (${h.site_closures_before} before this one opened)`]);
  }
  const maxWeight = Math.max(...r.actual.evidence.map((e) => e.weight), 1);
  return (
    <div className="evidence">
      <dl className="evidence__facts">
        {facts.map(([k, v]) => (
          <div key={k}>
            <dt className="mono">{k}/</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      {r.actual.evidence.length > 0 && (
        <div className="evidence__votes">
          <span className="mono evidence__kicker">still_trading/ · each source's vote, weighted by strength and age</span>
          <ul>
            {r.actual.evidence.map((e, i) => (
              <li key={i}>
                <span className="evidence__source">{SOURCE_NAMES[e.source] ?? e.source}</span>
                <span className={`evidence__says ${e.open ? "is-open" : "is-closed"}`}>{e.open ? "open" : "closed"}</span>
                <span className="evidence__weight">
                  <i aria-hidden><b style={{ width: `${(e.weight / maxWeight) * 100}%` }} /></i>
                  <span className="num">{e.weight.toFixed(2)}</span>
                </span>
                <span className="evidence__detail muted">
                  {e.detail}
                  {e.as_of && <> · {e.as_of}</>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** How the first-mapped openings were checked: one proportion bar, then the counts. */
function OpeningChecks({ checks }: { checks: Record<string, number> }) {
  const entries = Object.entries(checks).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((a, [, v]) => a + v, 0) || 1;
  const kept = (k: string) => k === "new" || k === "unverified";
  return (
    <div className="checks">
      <span className="checks__bar" aria-hidden>
        {entries.map(([k, v]) => (
          <i key={k} className={kept(k) ? "is-kept" : ""} style={{ flexGrow: v / total }} title={`${OPENING_LABELS[k] ?? k}: ${v}`} />
        ))}
      </span>
      <ul className="counts">
        {entries.map(([k, v]) => (
          <li key={k}>
            <span>
              <i className={`checks__key ${kept(k) ? "is-kept" : ""}`} aria-hidden />
              {OPENING_LABELS[k] ?? k}
            </span>
            <strong className="num">{v}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Closures at the spot, by predicted third, for the model against foot traffic alone:
 * paired bars per third, so a ranking that steers away from troubled spots shows as a
 * shorter bar in the top third.
 */
function ThirdsCompare({ model, baseline }: { model: ThirdRow[]; baseline: ThirdRow[] }) {
  const all = [...model, ...baseline].map((t) => t.mean_site_closures ?? 0);
  const max = Math.max(...all, 0.01);
  const w = (v: number | null) => `${((v ?? 0) / max) * 100}%`;
  return (
    <div className="thirds">
      <div className="thirds__legend small">
        <span><i className="is-model" /> Model</span>
        <span><i className="is-base" /> Foot traffic only</span>
      </div>
      {model.map((t, i) => {
        const b = baseline[i];
        return (
          <div key={t.third} className="thirds__row">
            <span className="thirds__label">{capitalise(t.third)}</span>
            <span className="thirds__bars">
              <span className="thirds__bar">
                <i className="is-model" style={{ width: w(t.mean_site_closures) }} />
                <span className="num">{t.mean_site_closures === null ? "–" : t.mean_site_closures.toFixed(2)}</span>
              </span>
              {b && (
                <span className="thirds__bar">
                  <i className="is-base" style={{ width: w(b.mean_site_closures) }} />
                  <span className="num">{b.mean_site_closures === null ? "–" : b.mean_site_closures.toFixed(2)}</span>
                </span>
              )}
            </span>
            <span className="thirds__closed mono">
              {t.closed}/{t.judged}
              {b && <><br />{b.closed}/{b.judged}</>}
            </span>
          </div>
        );
      })}
      <p className="muted small">Bars: café closures at the spot since 2019, per opening. Right: closed of judged.</p>
    </div>
  );
}

// --- Today's cafés (cross-section) ---------------------------------------------------------

function Today({ result, region, dark }: { result: CrossSectionResult; region: Region; dark: boolean }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const rows = useMemo(() => [...result.rows].sort((a, b) => a.predicted_rank - b.predicted_rank), [result]);
  // Quintiles of predicted monthly revenue -> ordinal ramp.
  const cuts = useMemo(() => {
    const v = rows.map((r) => r.mature_monthly).sort((a, b) => a - b);
    return [...Array(ORDINAL_BINS - 1).keys()].map((i) => v[Math.floor(((i + 1) * v.length) / ORDINAL_BINS)] ?? 0);
  }, [rows]);
  const bin = (v: number) => cuts.filter((c) => v >= c).length;
  const points = useMemo<MapPoint[]>(
    () =>
      rows.map((r) => ({
        id: r.osm_id,
        lat: r.lat,
        lon: r.lon,
        fill: ordinalColor(bin(r.mature_monthly), dark),
        tooltip: (
          <>
            <strong>{r.name}</strong>
            <br />#{r.predicted_rank} · {money(r.mature_monthly)}/month predicted
            {r.reviews_per_month !== null && <> · {r.reviews_per_month.toFixed(1)} reviews/month</>}
            {r.google_status === "CLOSED_PERMANENTLY" && <> · permanently closed on Google</>}
            <br />
            {r.site_closures ? `${r.site_closures} other café closure${r.site_closures > 1 ? "s" : ""} at this spot since 2019` : "No other café closures here since 2019"}
          </>
        ),
      })),
    [rows, dark, cuts],
  );
  const ranges = [0, ...cuts].map((lo, i) => [lo, cuts[i]] as const);
  const shownRows = showAll ? rows : rows.slice(0, 20);
  const available = result.outcomes.filter((o) => o.available);

  return (
    <>
      <div className="alert alert--inline alert--warn">
        <strong>Not time-safe.</strong> {capitalise(result.caveats[0].replace(/^Not time-safe:\s*/i, ""))}
      </div>
      <div className="card kpis">
        <Tile label="Independent cafés on today's map" value={String(result.n)} note={`scored with data as of ${result.as_of}`} />
        <Tile label="Outcomes compared" value={`${available.length} of ${result.outcomes.length}`}
          note={result.outcomes.filter((o) => !o.available).map((o) => `${o.label}: ${o.note}`).join(" · ") || "all available"} />
      </div>
      <div className="bt-grid">
        <section className="card bt-map">
          <ErrorBoundary what="map">
            <PointsMap region={region} points={points} selectedId={selected} onSelect={setSelected} label="Map of cafés open today" />
          </ErrorBoundary>
          <div className="map-legend map-legend--static">
            <div className="map-legend__title">Predicted monthly revenue</div>
            {ranges.map(([lo, hi], i) => (
              <div key={i}>
                <span className="swatch" style={{ background: ordinalColor(i, dark) }} />
                {hi === undefined ? `${money(lo)} and up` : i === 0 ? `under ${money(hi)}` : `${money(lo)} to ${money(hi)}`}
              </div>
            ))}
          </div>
        </section>
        <section className="card bt-side">
          <Kicker text="rank.top()" />
          <h2>Top predicted</h2>
          <div className="table-scroll table-scroll--tall">
            <table className="bt-table bt-table--compact">
              <thead>
                <tr>
                  <th scope="col" className="num">#</th>
                  <th scope="col">Café</th>
                  <th scope="col" className="num" title="Predicted monthly revenue">$/month</th>
                  <th scope="col" className="num" title="Google reviews per month">Reviews</th>
                  <th scope="col" className="num" title="Other café closures at this spot since 2019">Closures</th>
                </tr>
              </thead>
              <tbody>
                {shownRows.map((r) => (
                  <tr key={r.osm_id} className={`${selected === r.osm_id ? "is-selected" : ""} is-clickable`} onClick={() => setSelected(r.osm_id)}>
                    <td className="num">{r.predicted_rank}</td>
                    <td>
                      {r.name}
                      {r.google_status === "CLOSED_PERMANENTLY" && <span className="tag" title="Google lists it as permanently closed">closed</span>}
                    </td>
                    <td className="num">{money(r.mature_monthly)}</td>
                    <td className="num">{r.reviews_per_month === null ? "–" : r.reviews_per_month.toFixed(1)}</td>
                    <td className="num">{r.site_closures}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rows.length > 20 && (
            <button className="btn btn--ghost btn--small" onClick={() => setShowAll((v) => !v)}>
              {showAll ? "Show top 20" : `Show all ${rows.length}`}
            </button>
          )}
        </section>
      </div>
      <Ladders ladder={result.outcomes} />
      <Caveats caveats={result.caveats.slice(1)} />
    </>
  );
}

// --- Shared ------------------------------------------------------------------------------

function Ladders({ ladder }: { ladder: OutcomeComparison[] }) {
  return (
    <section className="card ladders">
      <div className="card-head">
        <Kicker text="layers.compare()" />
        <h2>Which layers help?</h2>
        <span className="muted card-head__note">
          Each row switches on one more model layer, starting from plain foot traffic. Pick an outcome to see how the
          ranking holds up against it.
        </span>
      </div>
      <LadderExplorer ladder={ladder} />
    </section>
  );
}

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="tile">
      <span className="tile__label">{label}</span>
      <CountUpText className="tile__value" text={value} />
      <span className="tile__note muted">{note}</span>
    </div>
  );
}

function Caveats({ caveats }: { caveats: string[] }) {
  if (!caveats.length) return null;
  return (
    <section className="card bt-notes">
      <Kicker text="caveats/" />
      <h2>Caveats</h2>
      <ul className="caveats">
        {caveats.map((c, i) => (
          <li key={i}>{c}</li>
        ))}
      </ul>
    </section>
  );
}
