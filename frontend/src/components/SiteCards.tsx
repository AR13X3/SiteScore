import { money, pct, shortMonth } from "../lib/format";
import { MAX_SITES, siteColor } from "../lib/theme";
import type { CandidateSite, SimulationResult } from "../lib/types";
import { IconPin, IconX } from "./Icons";

interface Props {
  sites: CandidateSite[];
  result: SimulationResult | null;
  dark: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, label: string) => void;
  onRemove: (id: string) => void;
  onDemo: () => void;
  onClear: () => void;
}

/**
 * Candidate sites as cards: 36-month revenue, and its P10–P90 range drawn on one scale
 * shared by every card, so the ranges compare at a glance. The selected card is inverted.
 */
export function SiteCards({ sites, result, dark, selectedId, onSelect, onRename, onRemove, onDemo, onClear }: Props) {
  if (sites.length === 0) {
    return (
      <div className="empty hatch">
        <IconPin size={20} />
        <p className="empty__title">No sites yet</p>
        <p className="muted small">Search an address above, click the map, or ask the analyst. Up to {MAX_SITES} sites.</p>
        <button className="btn btn--dark btn--small" onClick={onDemo}>
          Load 3 demo sites
        </button>
      </div>
    );
  }
  const simOf = new Map(result?.sites.map((s) => [s.site.id, s]));
  const rankOf = new Map(result?.explanations.map((e) => [e.site_id, e.rank]));
  const oddsOf = new Map(result?.uncertainty?.sites.map((u) => [u.site_id, u]));
  const lows = [...oddsOf.values()].map((u) => u.total_revenue.p10);
  const highs = [...oddsOf.values()].map((u) => u.total_revenue.p90);
  const lo = Math.min(...lows, ...[...simOf.values()].map((s) => s.total_revenue));
  const hi = Math.max(...highs, ...[...simOf.values()].map((s) => s.total_revenue));
  const x = (v: number) => (hi > lo ? ((v - lo) / (hi - lo)) * 100 : 50);

  return (
    <div className="site-cards">
      <ol className="site-card-list">
        {sites.map((s) => {
          const sim = simOf.get(s.id);
          const odds = oddsOf.get(s.id);
          const rank = rankOf.get(s.id);
          const on = s.id === selectedId;
          return (
            <li key={s.id} className={`site-card ${on ? "is-selected" : ""}`} onClick={() => onSelect(s.id)}>
              <div className="site-card__meta">
                <span>Site {s.slot + 1}</span>
                <span>{rank ? `Rank ${rank} of ${sites.length}` : "–"}</span>
                <span className="num">{odds ? `${money(odds.total_revenue.p10)}–${money(odds.total_revenue.p90)}` : ""}</span>
              </div>
              <div className="site-card__main">
                <span className="site-card__value">{sim ? money(sim.total_revenue) : "…"}</span>
                <span className="site-card__range" aria-hidden>
                  {odds && sim ? (
                    <>
                      <span className="site-card__ci" style={{ left: `${x(odds.total_revenue.p10)}%`, width: `${x(odds.total_revenue.p90) - x(odds.total_revenue.p10)}%` }} />
                      <span className="site-card__dot" style={{ left: `${x(sim.total_revenue)}%` }} />
                    </>
                  ) : (
                    <span className="site-card__ci site-card__ci--pending" />
                  )}
                </span>
                <span className="site-card__aux">
                  {odds && sites.length > 1 ? (
                    <>
                      <strong>{pct(odds.prob_best)}</strong> best
                    </>
                  ) : sim?.total_profit != null ? (
                    <>{money(sim.total_profit)} profit</>
                  ) : null}
                </span>
              </div>
              <div className="site-card__foot">
                <span className="site-key site-key--small" style={{ background: siteColor(s.slot, dark) }}>
                  {s.slot + 1}
                </span>
                <input
                  className="site-name"
                  value={s.label}
                  aria-label={`Name of site ${s.slot + 1}`}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => onRename(s.id, e.target.value)}
                />
                <button
                  className="icon-btn icon-btn--small"
                  aria-label={`Remove ${s.label}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemove(s.id);
                  }}
                >
                  <IconX size={14} />
                </button>
              </div>
            </li>
          );
        })}
      </ol>
      <div className="site-cards__foot">
        <span className="muted small">
          {sites.length}/{MAX_SITES} sites{result ? ` · opens ${shortMonth(result.open_date)}` : ""}
        </span>
        <button className="btn btn--ghost btn--small" onClick={onClear}>
          Clear
        </button>
      </div>
    </div>
  );
}
