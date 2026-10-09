import { money } from "../lib/format";
import { MAX_SITES, siteColor } from "../lib/theme";
import type { CandidateSite, SimulationResult } from "../lib/types";

interface Props {
  sites: CandidateSite[];
  result: SimulationResult | null;
  dark: boolean;
  onRename: (id: string, label: string) => void;
  onRemove: (id: string) => void;
  onDemo: () => void;
  onClear: () => void;
}

export function SiteList({ sites, result, dark, onRename, onRemove, onDemo, onClear }: Props) {
  const totals = new Map(result?.sites.map((s) => [s.site.id, s.total_revenue]));
  const ranks = new Map(result?.explanations.map((e) => [e.site_id, e.rank]));
  const odds = new Map(result?.uncertainty?.sites.map((u) => [u.site_id, u]));

  if (sites.length === 0) {
    return (
      <div className="empty">
        <p className="empty__title">Click the map to drop up to {MAX_SITES} candidate sites</p>
        <p className="muted">Drag pins to fine-tune. Results update automatically.</p>
        <button className="btn btn--primary" onClick={onDemo}>
          Load 3 demo sites
        </button>
      </div>
    );
  }

  return (
    <div className="sites">
      <ol className="site-list">
        {sites.map((s) => (
          <li key={s.id} className="site-row">
            <span className="site-key" style={{ background: siteColor(s.slot, dark) }}>
              {s.slot + 1}
            </span>
            <input
              className="site-name"
              value={s.label}
              aria-label={`Name of site ${s.slot + 1}`}
              onChange={(e) => onRename(s.id, e.target.value)}
            />
            <span className="site-total">
              {totals.has(s.id) ? (
                <>
                  <span className="muted">#{ranks.get(s.id)}</span> {money(totals.get(s.id)!)}
                  {odds.has(s.id) && (
                    <span className="site-range">
                      {money(odds.get(s.id)!.total_revenue.p10)}–{money(odds.get(s.id)!.total_revenue.p90)}
                    </span>
                  )}
                </>
              ) : (
                <span className="muted">…</span>
              )}
            </span>
            <button className="icon-btn" aria-label={`Remove ${s.label}`} onClick={() => onRemove(s.id)}>
              ×
            </button>
          </li>
        ))}
      </ol>
      <div className="site-actions">
        <span className="muted">
          {sites.length}/{MAX_SITES} sites · totals over 36 months
        </span>
        <button className="btn btn--ghost" onClick={onClear}>
          Clear
        </button>
      </div>
    </div>
  );
}
