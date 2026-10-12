import { money, pct, signedPct } from "../lib/format";
import { siteColor } from "../lib/theme";
import type { CandidateSite, SimulationResult } from "../lib/types";
import { IconChat, IconInfo, IconSearch, IconTrash } from "./Icons";

interface Props {
  site: CandidateSite | undefined;
  result: SimulationResult | null;
  siteCount: number;
  dark: boolean;
  loading: boolean;
  onRemove: (id: string) => void;
  onFindNearby: (site: CandidateSite) => void;
  onAsk: (question: string) => void;
}

/** Everything about the selected site: numbers, why it ranks where it does, each layer. */
export function SiteDetail({ site, result, siteCount, dark, loading, onRemove, onFindNearby, onAsk }: Props) {
  if (!site) {
    return (
      <div className="detail-empty hatch">
        <IconInfo size={20} />
        <p className="empty__title">Select a site</p>
        <p className="muted small">Its 36-month numbers, rent, and why it ranks where it does appear here.</p>
      </div>
    );
  }
  const sim = result?.sites.find((s) => s.site.id === site.id);
  const expl = result?.explanations.find((e) => e.site_id === site.id);
  const odds = result?.uncertainty?.sites.find((u) => u.site_id === site.id);
  if (!sim || !expl) {
    return (
      <div className="detail-empty hatch">
        <span className="spinner" aria-hidden />
        <p className="muted small">Simulating {site.label}…</p>
      </div>
    );
  }
  const layers = [...sim.mature.layers, sim.dynamics];
  const compare = siteCount > 1 && expl.contributions.length > 0;
  const maxLog = Math.max(0.05, ...expl.contributions.map((c) => Math.abs(Math.log(c.ratio))));

  return (
    <div className={`detail ${loading ? "is-loading" : ""}`}>
      <div className="detail__scroll">
        <header className="detail__head">
          <span className="detail__kicker">
            <span className="site-key site-key--small" style={{ background: siteColor(site.slot, dark) }}>
              {site.slot + 1}
            </span>
            Site {site.slot + 1} · rank {expl.rank} of {siteCount}
          </span>
          <h2>{site.label}</h2>
          <span className="muted small num">
            {site.lat.toFixed(5)}, {site.lon.toFixed(5)}
          </span>
        </header>

        <dl className="stat-grid">
          <Stat label="Revenue, 36 months" value={money(sim.total_revenue)}
            note={odds ? `${money(odds.total_revenue.p10)}–${money(odds.total_revenue.p90)}` : "range pending"} />
          <Stat label="Profit, 36 months" value={sim.total_profit === null ? "–" : money(sim.total_profit)}
            note={odds?.total_profit ? `${money(odds.total_profit.p10)}–${money(odds.total_profit.p90)}` : "with estimated rent"} />
          <Stat label="Mature month" value={money(sim.mature.monthly_revenue)} note="once ramped up" />
          <Stat label="Estimated rent" value={sim.mature.rent ? money(sim.mature.rent.monthly) : "–"}
            note={sim.mature.rent ? `${sim.mature.rent.index.toFixed(2)}× a typical site` : "no cost profile"} />
          {siteCount > 1 && <Stat label="Best in" value={odds ? pct(odds.prob_best) : "…"} note="of 300 scenarios" />}
          <Stat label="Chance of a loss" value={odds?.prob_loss == null ? "…" : pct(odds.prob_loss)} note="over 36 months" />
        </dl>

        <p className="detail__headline">{expl.headline}</p>

        {compare && (
          <section className="detail__section">
            <h3>Against the average candidate</h3>
            <ul className="layer-rows" aria-label="Effect of each layer vs the average candidate">
              {expl.contributions.map((c) => {
                const width = (Math.abs(Math.log(c.ratio)) / maxLog) * 50;
                const positive = c.ratio >= 1;
                return (
                  <li key={c.key} className="layer-row">
                    <span className="layer-row__label">{c.label}</span>
                    <span className="contrib-track" aria-hidden>
                      <span className="contrib-axis" />
                      <span
                        className={`contrib-bar ${positive ? "pos" : "neg"}`}
                        style={positive ? { left: "50%", width: `${width}%` } : { right: "50%", width: `${width}%` }}
                      />
                    </span>
                    <span className="layer-row__value num">{Math.abs(c.pct_effect) < 0.005 ? "–" : signedPct(c.pct_effect)}</span>
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        <section className="detail__section">
          <h3>How the model got here</h3>
          <ul className="layer-list">
            {layers.map((l) => (
              <li key={l.key}>
                <span className="layer-list__name">{l.label}</span>
                <span className="layer-list__text muted">{l.summary}</span>
              </li>
            ))}
            {sim.mature.rent && (
              <li>
                <span className="layer-list__name">Rent</span>
                <span className="layer-list__text muted">{sim.mature.rent.summary}</span>
              </li>
            )}
          </ul>
        </section>
      </div>

      <footer className="detail__foot">
        <div className="detail__totals">
          <div>
            <span className="muted small">Revenue</span>
            <strong className="num">{money(sim.total_revenue)}</strong>
          </div>
          <div>
            <span className="muted small">Profit</span>
            <strong className="num">{sim.total_profit === null ? "–" : money(sim.total_profit)}</strong>
          </div>
          <div>
            <span className="muted small">Loss risk</span>
            <strong className="num">{odds?.prob_loss == null ? "…" : pct(odds.prob_loss)}</strong>
          </div>
        </div>
        <div className="detail__actions">
          <button className="btn btn--small" onClick={() => onRemove(site.id)}>
            <IconTrash size={14} /> Remove
          </button>
          <button className="btn btn--small" onClick={() => onFindNearby(site)}>
            <IconSearch size={14} /> Search nearby
          </button>
          <button
            className="btn btn--small btn--accent"
            onClick={() => onAsk(`Why does ${site.label} rank ${expl.rank} of ${siteCount}, and what would make it a better site?`)}
          >
            <IconChat size={14} /> Ask analyst
          </button>
        </div>
      </footer>
    </div>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="stat-cell">
      <dt>{label}</dt>
      <dd className="num">{value}</dd>
      <span className="muted small">{note}</span>
    </div>
  );
}
