import { Fragment, useEffect, useMemo, useState } from "react";
import { type RunningUnit, type Term, equationTerms, runningLabel } from "../lib/equation";
import { money } from "../lib/format";
import { useInView } from "../lib/hooks";
import type { SiteSimulation, SiteUncertainty } from "../lib/types";
import { AnimatedNumber } from "./AnimatedNumber";
import { ScrambleText } from "./Motion";
import { IconArrowRight, IconChevronLeft, IconChevronRight, IconPause, IconPlay } from "./Icons";

interface Props {
  sim: SiteSimulation | null;
  odds?: SiteUncertainty;
  label: string;
  onTry: () => void;
}

const ABOUT: Record<string, string> = {
  demand: "Residents, workers and commuters within walking reach, weighted by when they're around.",
  fit: "Local demographics against the business's customer profile: age, income, housing.",
  anchors: "Stations, supermarkets, schools and hospitals that bring people past the door.",
  competition: "A Huff gravity model over every rival, plus an 'elsewhere' option: the share of local demand this site wins.",
  behaviour: "Thousands of simulated customers choosing by distance, price, quality and habit, against the plain gravity model.",
  price: "Nearby rivals re-price in best-response rounds after you open.",
  spend: "How often a regular comes each month, times what they spend per visit.",
  capacity: "Seats and service time cap how many customers can be served.",
  months: "Revenue is projected month by month for three years from opening.",
  time: "Ramp-up from opening, seasons, school holidays and approved developments landing on schedule.",
};

const STEP_MS = 2800;
const whole = (n: number) => Math.round(n).toLocaleString("en-AU");

/** The sum in three rows: who comes, what they spend, and how that plays out over the horizon. */
type RowId = "customers" | "revenue" | "horizon";
interface Row {
  id: RowId;
  terms: { term: Term; index: number }[];
  /** The previous row's result, carried in as this row's first factor. */
  carry: { value: number; unit: RunningUnit } | null;
  result: number;
  caption: string;
}

const rowOf = (u: RunningUnit): RowId => (u === "people" || u === "customers" ? "customers" : u === "month" ? "revenue" : "horizon");

function buildRows(terms: Term[], months: number): Row[] {
  const rows: Row[] = [];
  terms.forEach((term, index) => {
    const id = rowOf(term.unit);
    let row = rows[rows.length - 1];
    if (!row || row.id !== id) {
      const carry = row ? { value: row.result, unit: (row.id === "customers" ? "customers" : "month") as RunningUnit } : null;
      row = { id, terms: [], carry, result: 0, caption: "" };
      rows.push(row);
    }
    row.terms.push({ term, index });
    row.result = term.after;
  });
  for (const r of rows) r.caption = r.id === "customers" ? "customers" : r.id === "revenue" ? "a month" : `over ${months} months`;
  return rows;
}

/**
 * The forecast for one site written out as the worked sum it is: a row each for who
 * comes, what they spend, and the horizon, with the results lined up on the right.
 * Steps through the terms on its own while in view; pointing at a term takes over.
 */
export function ModelEquation({ sim, odds, label, onTry }: Props) {
  const terms = useMemo(() => (sim ? equationTerms(sim) : []), [sim]);
  const rows = useMemo(() => buildRows(terms, sim?.months.length ?? 36), [terms, sim]);
  const [active, setActive] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [ref, inView] = useInView<HTMLElement>(0.35);
  const n = terms.length;

  useEffect(() => {
    if (!playing || !inView || n === 0) return;
    const t = setInterval(() => setActive((a) => (a + 1) % n), STEP_MS);
    return () => clearInterval(t);
  }, [playing, inView, n]);

  const pick = (i: number) => {
    setActive(i);
    setPlaying(false);
  };
  const term: Term | undefined = terms[Math.min(active, n - 1)];
  const activeRow = term ? rowOf(term.unit) : null;

  return (
    <section className="card equation-card" ref={ref} aria-labelledby="equation-title">
      <div className="card-head card-head--split">
        <div>
          <ScrambleText className="kicker" text="model.explain(site)" cursor />
          <h2 id="equation-title" className="equation-card__title">Every forecast is a product you can read</h2>
          <span className="muted small">
            Shown for <strong className="equation-card__site">{label}</strong>. Pick another spot on the map above to
            change it. Every assumption is a line of YAML.
          </span>
        </div>
        <div className="equation__controls">
          <button className="icon-btn" aria-label="Previous term" onClick={() => pick((active - 1 + n) % Math.max(1, n))} disabled={!n}>
            <IconChevronLeft size={16} />
          </button>
          <button className="icon-btn" aria-label={playing ? "Pause" : "Play"} onClick={() => setPlaying((p) => !p)} disabled={!n}>
            {playing ? <IconPause size={15} /> : <IconPlay size={15} />}
          </button>
          <button className="icon-btn" aria-label="Next term" onClick={() => pick((active + 1) % Math.max(1, n))} disabled={!n}>
            <IconChevronRight size={16} />
          </button>
          <button className="btn btn--small" onClick={onTry}>
            Try it <IconArrowRight size={14} />
          </button>
        </div>
      </div>

      <div className="explain">
        <div className="ledger" role="group" aria-label="The forecast as a product of its layers">
          {sim
            ? rows.map((r, ri) => (
                <div key={r.id} className={`ledger__row ${r.id === activeRow ? "is-active" : ""}`}>
                  <span className="ledger__label mono">
                    <span className="ledger__n">{String(ri + 1).padStart(2, "0")}</span>
                    {r.id}/
                  </span>
                  <div className="ledger__terms">
                    {r.carry && (
                      <span className="term term--carry">
                        <span className="term__value num">{r.carry.unit === "customers" ? whole(r.carry.value) : money(r.carry.value)}</span>
                        <span className="term__caption">{r.carry.unit === "customers" ? "customers" : "a month"}</span>
                      </span>
                    )}
                    {r.terms.map(({ term: t, index: i }, k) => (
                      <Fragment key={t.key}>
                        {(k > 0 || r.carry) && <span className="equation__op" aria-hidden>×</span>}
                        <button
                          className={`term ${i === active ? "is-on" : ""}`}
                          aria-pressed={i === active}
                          onClick={() => pick(i)}
                          onMouseEnter={() => pick(i)}
                          onFocus={() => pick(i)}
                        >
                          <span className="term__value num">{t.shown}</span>
                          <span className="term__caption">{t.caption}</span>
                          {i === active && playing && inView && <span className="term__timer" style={{ animationDuration: `${STEP_MS}ms` }} />}
                        </button>
                      </Fragment>
                    ))}
                  </div>
                  <div className={`ledger__result ${ri === rows.length - 1 ? "is-final" : ""}`}>
                    <span className="ledger__eq" aria-hidden>=</span>
                    <AnimatedNumber className="ledger__value" value={r.result} format={r.id === "customers" ? whole : money} />
                    <span className="term__caption">{r.caption}</span>
                  </div>
                </div>
              ))
            : [0, 1, 2].map((i) => (
                <div key={i} className="ledger__row">
                  <span className="ledger__label" />
                  <div className="ledger__terms">
                    <span className="skeleton term-skel" />
                    <span className="skeleton term-skel" />
                    <span className="skeleton term-skel" />
                  </div>
                  <div className="ledger__result">
                    <span className="skeleton skeleton--big" />
                  </div>
                </div>
              ))}
          {sim && (
            <div className="ledger__row ledger__row--range">
              <span className="ledger__label mono">
                <span className="ledger__n">{String(rows.length + 1).padStart(2, "0")}</span>
                range/
              </span>
              <div className="ledger__terms">
                <span className="muted small">
                  300 scenarios vary spend, distance decay, ramp-up and habit; 80% of them land in this range.
                </span>
              </div>
              <div className="ledger__result">
                {odds ? (
                  <>
                    <span className="ledger__value ledger__value--range num">
                      {money(odds.total_revenue.p10)}–{money(odds.total_revenue.p90)}
                    </span>
                    <span className="term__caption">P10–P90</span>
                  </>
                ) : (
                  <span className="skeleton skeleton--text" />
                )}
              </div>
            </div>
          )}
        </div>

        <aside className="explain__detail" aria-live="polite">
          {term ? (
            <div className="explain__inner" key={term.key}>
              <span className="mono explain__step">
                {String(active + 1).padStart(2, "0")} / {String(n).padStart(2, "0")}
              </span>
              <h3>{term.name}</h3>
              <p className="muted">{ABOUT[term.key] ?? term.summary}</p>
              <span className="mono explain__kicker">at_this_site/</span>
              <p>{term.summary}</p>
              <p className="equation__flow num">
                {term.before !== null && (
                  <>
                    <span>{runningLabel(term.before, terms[active - 1]?.unit ?? "people", money)}</span>
                    <IconArrowRight size={14} />
                  </>
                )}
                <strong>{runningLabel(term.after, term.unit, money)}</strong>
              </p>
            </div>
          ) : (
            <span className="skeleton skeleton--chart" />
          )}
        </aside>
      </div>
    </section>
  );
}
