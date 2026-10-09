import { money, signedPct } from "../lib/format";
import { siteColor } from "../lib/theme";
import type { CandidateSite, SimulationResult, SiteExplanation, SiteSimulation } from "../lib/types";

interface Props {
  result: SimulationResult;
  sites: CandidateSite[];
  dark: boolean;
}

export function WhyPanel({ result, sites, dark }: Props) {
  const slotOf = new Map(sites.map((s) => [s.id, s.slot]));
  const simOf = new Map(result.sites.map((s) => [s.site.id, s]));
  // One scale for every card so bar lengths compare across sites (log ratio = symmetric).
  const maxLog = Math.max(
    0.05,
    ...result.explanations.flatMap((e) => e.contributions.map((c) => Math.abs(Math.log(c.ratio)))),
  );

  return (
    <div className="why-grid">
      {result.explanations.map((e) => (
        <WhyCard
          key={e.site_id}
          explanation={e}
          sim={simOf.get(e.site_id)!}
          color={siteColor(slotOf.get(e.site_id) ?? 0, dark)}
          number={(slotOf.get(e.site_id) ?? 0) + 1}
          maxLog={maxLog}
          compare={result.explanations.length > 1}
        />
      ))}
    </div>
  );
}

interface CardProps {
  explanation: SiteExplanation;
  sim: SiteSimulation;
  color: string;
  number: number;
  maxLog: number;
  compare: boolean;
}

function WhyCard({ explanation: e, sim, color, number, maxLog, compare }: CardProps) {
  const layers = [...sim.mature.layers, sim.dynamics];
  return (
    <article className="card why-card">
      <header className="why-head">
        <span className="rank">#{e.rank}</span>
        <span className="site-key" style={{ background: color }}>
          {number}
        </span>
        <h3>{sim.site.label || sim.site.id}</h3>
        <div className="why-total">
          <strong>{money(e.total_revenue)}</strong>
          <span className="muted">36-month revenue</span>
        </div>
      </header>
      <p className="why-headline">{e.headline}</p>

      {compare && e.contributions.length > 0 && (
        <div className="contrib" role="table" aria-label="Effect of each layer vs the average candidate">
          {e.contributions.map((c) => {
            const width = (Math.abs(Math.log(c.ratio)) / maxLog) * 50;
            const positive = c.ratio >= 1;
            return (
              <div className="contrib-row" role="row" key={c.key}>
                <span className="contrib-label" role="cell">
                  {c.label}
                </span>
                <span className="contrib-track" role="cell" aria-hidden>
                  <span className="contrib-axis" />
                  <span
                    className={`contrib-bar ${positive ? "pos" : "neg"}`}
                    style={positive ? { left: "50%", width: `${width}%` } : { right: "50%", width: `${width}%` }}
                  />
                </span>
                <span className="contrib-value" role="cell">
                  {Math.abs(c.pct_effect) < 0.005 ? "–" : signedPct(c.pct_effect)}
                </span>
              </div>
            );
          })}
          <p className="muted small">Bars compare each layer with the average candidate.</p>
        </div>
      )}

      <details className="why-details">
        <summary>How the model got here</summary>
        <ul>
          {layers.map((l) => (
            <li key={l.key}>
              <strong>{l.label}.</strong> {l.summary}
            </li>
          ))}
        </ul>
      </details>
    </article>
  );
}
