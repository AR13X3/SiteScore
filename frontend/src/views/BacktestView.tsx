import { Fragment, useEffect, useMemo, useState } from "react";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { LadderChart, ladderVerdict } from "../components/LadderChart";
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
}

const dateShort = (iso: string | null) =>
  iso ? new Date(`${iso}T00:00:00`).toLocaleDateString("en-AU", { month: "short", year: "numeric" }) : "–";
const num2 = (v: number | null) => (v === null ? "n/a" : v.toFixed(2));

export function BacktestView({ region, businessType, dark }: Props) {
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
    <main className="bt">
      <section className="bt-head">
        <div>
          <h1>Would SiteScore have picked the winners?</h1>
          <p className="muted">
            {mode === "backtest"
              ? "Each café is predicted using only data published before it opened, then compared with what happened."
              : "Every café open today, scored with today's data. A bigger sample, but not a fair test of prediction."}
          </p>
        </div>
        <div className="bt-controls">
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
      </section>

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
  const maxScore = Math.max(...result.rows.map((r) => r.predicted_score), 1);
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

      <div className="kpis">
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
          <h2>Opening check</h2>
          <p className="muted small">
            "First mapped" often means an old café mapped for the first time, so each one is checked against Foursquare,
            ASIC and the map's own history.
          </p>
          <ul className="counts">
            {Object.entries(result.opening_checks).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
              <li key={k}>
                <span>{OPENING_LABELS[k] ?? k}</span>
                <strong>{v}</strong>
              </li>
            ))}
          </ul>
          <h2>Closures by predicted third</h2>
          <ThirdsTable title="Ranked by the model" rows={s.by_third} />
          <ThirdsTable title="Ranked by foot traffic only" rows={s.baseline_by_third} />
        </section>
      </div>

      <Ladders ladder={result.ladder} />

      <section className="card bt-table-card">
        <div className="card-head">
          <h2>Predicted vs what happened</h2>
          <span className="muted card-head__note">Click a row for its evidence · predictions use data up to the date shown</span>
        </div>
        <div className="table-scroll">
          <table className="bt-table">
            <thead>
              <tr>
                <th scope="col" className="num">#</th>
                <th scope="col">Café</th>
                <th scope="col">Opened</th>
                <th scope="col">Predicted, first {result.score_months} months</th>
                <th scope="col">{months}-month outcome</th>
                <th scope="col">Today</th>
                <th scope="col" className="num">Closures at spot</th>
              </tr>
            </thead>
            <tbody>
              {result.rows.map((r) => {
                const id = r.osm_id || r.name;
                return (
                  <Fragment key={id}>
                    <tr
                      id={`bt-row-${id}`}
                      className={`${selected === id ? "is-selected" : ""} is-clickable`}
                      onClick={() => select(id)}
                      aria-expanded={expanded === id}
                    >
                      <td className="num">{r.predicted_rank}</td>
                      <td>
                        <strong>{r.name}</strong>
                        {r.opening_check && <span className="tag">{r.opening_check}</span>}
                      </td>
                      <td>{dateShort(r.opened)}</td>
                      <td>
                        <span className="inline-bar">
                          <span style={{ width: `${(r.predicted_score / maxScore) * 100}%` }} />
                        </span>
                        <span className="num">{money(r.predicted_score)}</span>
                      </td>
                      <td>{r.actual.horizon ? <StatusChip status={r.actual.horizon.status} months={months} /> : "–"}</td>
                      <td>{r.actual.still_open === null ? "?" : r.actual.still_open ? "Trading" : "Closed"}</td>
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
            </tbody>
          </table>
        </div>
      </section>

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

function Evidence({ row: r }: { row: BacktestRow }) {
  const h = r.actual.horizon;
  return (
    <div className="evidence">
      <dl>
        <dt>Opening</dt>
        <dd>
          {r.opened_note}
          {r.opening_detail && <> · {r.opening_check}: {r.opening_detail}</>}
        </dd>
        <dt>Predicted with</dt>
        <dd>data published up to {r.data_cutoff ?? r.as_of} (as of {r.as_of})</dd>
        {h && (
          <>
            <dt>Outcome by {dateShort(h.horizon)}</dt>
            <dd>
              {h.detail}
              {h.failure && <> · {h.failure === "operator" ? "operator failure (another café took over)" : h.failure === "site" ? "site failure" : "type unknown"}</>}
            </dd>
            <dt>Same spot</dt>
            <dd>
              {h.site_closures === 0
                ? "no café closures here since 2019"
                : `${h.site_closures} café closure${h.site_closures > 1 ? "s" : ""} here since 2019 (${h.site_closures_before} before this one opened)`}
            </dd>
          </>
        )}
      </dl>
      {r.actual.evidence.length > 0 && (
        <table className="evidence-table">
          <caption className="muted small">Still trading today? Each source's vote, weighted by strength and age</caption>
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">Says</th>
              <th scope="col" className="num">Weight</th>
              <th scope="col">Detail</th>
            </tr>
          </thead>
          <tbody>
            {r.actual.evidence.map((e, i) => (
              <tr key={i}>
                <td>{SOURCE_NAMES[e.source] ?? e.source}</td>
                <td>{e.open ? "open" : "closed"}</td>
                <td className="num">{e.weight.toFixed(2)}</td>
                <td>
                  {e.detail}
                  {e.as_of && <span className="muted"> · {e.as_of}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function ThirdsTable({ title, rows }: { title: string; rows: ThirdRow[] }) {
  return (
    <table className="mini-table">
      <caption>{title}</caption>
      <thead>
        <tr>
          <th scope="col">Third</th>
          <th scope="col" className="num">Closed / judged</th>
          <th scope="col" className="num">Closures at spot</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((t) => (
          <tr key={t.third}>
            <td>{t.third}</td>
            <td className="num">
              {t.closed} / {t.judged}
              {t.closure_rate !== null && t.closed > 0 && <span className="muted"> ({pct(t.closure_rate)})</span>}
            </td>
            <td className="num">{t.mean_site_closures === null ? "–" : t.mean_site_closures.toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
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
      <div className="kpis">
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
  const available = ladder.filter((o) => o.available);
  const missing = ladder.filter((o) => !o.available);
  return (
    <section className="card ladders">
      <div className="card-head">
        <h2>Which layers help?</h2>
        <span className="muted card-head__note">
          Each row switches on one more model layer. Higher is better; the bar is a 90% interval.
        </span>
      </div>
      <div className="ladder-grid-wrap">
        {available.map((o) => (
          <div key={o.outcome} className="ladder-panel">
            <LadderChart comparison={o} />
            <p className="ladder-verdict">{ladderVerdict(o)}</p>
          </div>
        ))}
      </div>
      {missing.length > 0 && (
        <ul className="missing muted small">
          {missing.map((o) => (
            <li key={o.outcome}>
              {o.label}: not compared ({o.note})
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="tile card">
      <span className="tile__label">{label}</span>
      <span className="tile__value">{value}</span>
      <span className="tile__note muted">{note}</span>
    </div>
  );
}

function Caveats({ caveats }: { caveats: string[] }) {
  if (!caveats.length) return null;
  return (
    <section className="card bt-notes">
      <h2>Caveats</h2>
      <ul className="caveats">
        {caveats.map((c, i) => (
          <li key={i}>{c}</li>
        ))}
      </ul>
    </section>
  );
}
