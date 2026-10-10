import { useState } from "react";
import { pct } from "../lib/format";
import type { LadderStep, OutcomeComparison } from "../lib/types";

const TICKS = [-1, -0.5, 0, 0.5, 1];
const x = (v: number) => ((Math.max(-1, Math.min(1, v)) + 1) / 2) * 100; // Spearman -> % across

const num = (v: number | null) => (v === null ? "n/a" : (v >= 0 ? "" : "−") + Math.abs(v).toFixed(2));
const interval = (ci: [number, number] | null) => (ci ? `${num(ci[0])} to ${num(ci[1])}` : "");

export { ladderVerdict } from "../lib/ladder";

/**
 * Dot-and-interval plot: each rung of the model (layers switched on up to there) and
 * how well it ranks one outcome (Spearman, 90% bootstrap interval). One series, so
 * one hue; the numbers sit beside the dots, so the chart is also its own table.
 */
export function LadderChart({ comparison }: { comparison: OutcomeComparison }) {
  const [hover, setHover] = useState<number | null>(null);
  const steps = comparison.steps;
  const n = steps[0]?.n ?? 0;

  return (
    <figure className="ladder">
      <figcaption>
        <strong>{comparison.label}</strong>
        <span className="muted"> · {n} businesses</span>
      </figcaption>
      <div className="ladder-grid" role="table" aria-label={`How each model layer ranks: ${comparison.label}`}>
        <div className="ladder-row ladder-row--head" role="row">
          <span role="columnheader">Model, adding layers</span>
          <span role="columnheader" className="ladder-axis-head">Spearman with the outcome</span>
          <span role="columnheader" className="num">Value · 90% interval</span>
        </div>
        {steps.map((s, i) => (
          <Row key={s.key} step={s} first={i === 0} active={hover === i} onHover={(on) => setHover(on ? i : null)} />
        ))}
        <div className="ladder-row ladder-row--axis" aria-hidden>
          <span />
          <span className="ladder-ticks">
            {TICKS.map((t) => (
              <span key={t} style={{ left: `${x(t)}%` }}>
                {t === 0 ? "0" : num(t)}
              </span>
            ))}
          </span>
          <span />
        </div>
      </div>
      <p className="ladder-note muted small">
        0 = no relation; 1 = the same order as reality. Bars show where the value could land with a different sample of
        the same size.
      </p>
    </figure>
  );
}

function Row({ step: s, first, active, onHover }: {
  step: LadderStep; first: boolean; active: boolean; onHover: (on: boolean) => void;
}) {
  const ci = s.spearman_ci;
  return (
    <div
      className={`ladder-row ${active ? "is-active" : ""} ${first ? "is-baseline" : ""}`}
      role="row"
      tabIndex={0}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
      onFocus={() => onHover(true)}
      onBlur={() => onHover(false)}
    >
      <span role="cell" className="ladder-label">
        {s.label}
        {first && <span className="muted"> (baseline)</span>}
      </span>
      <span role="cell" className="ladder-plot">
        {TICKS.map((t) => (
          <span key={t} className={`ladder-grid-line ${t === 0 ? "is-zero" : ""}`} style={{ left: `${x(t)}%` }} />
        ))}
        {ci && <span className="ladder-ci" style={{ left: `${x(ci[0])}%`, width: `${x(ci[1]) - x(ci[0])}%` }} />}
        {s.spearman !== null && <span className="ladder-dot" style={{ left: `${x(s.spearman)}%` }} />}
        {active && (
          <span className="ladder-tip" role="tooltip">
            <strong>{s.label}</strong>
            <span>Spearman {num(s.spearman)}{ci ? ` (90%: ${interval(ci)})` : ""}</span>
            <span>Pairs ordered correctly {s.pairwise_accuracy === null ? "n/a" : pct(s.pairwise_accuracy)} of {s.pairs}</span>
            {s.gain_ci && <span>Gain over foot traffic: {interval(s.gain_ci)}</span>}
          </span>
        )}
      </span>
      <span role="cell" className="num ladder-value">
        {num(s.spearman)}
        {ci && <span className="muted"> {interval(ci)}</span>}
      </span>
    </div>
  );
}
