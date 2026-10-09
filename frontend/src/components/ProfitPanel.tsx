import { money, pct } from "../lib/format";
import { siteColor } from "../lib/theme";
import type { CandidateSite, Costs, SimulationResult } from "../lib/types";

interface Props {
  costs: Costs;
  defaults: Costs;
  onChange: (costs: Costs) => void;
  result: SimulationResult | null;
  sites: CandidateSite[];
  dark: boolean;
}

function MoneyInput({ label, value, onChange, step = 500 }: {
  label: string; value: number; onChange: (v: number) => void; step?: number;
}) {
  return (
    <label className="cost-field">
      <span>{label}</span>
      <span className="cost-input">
        <span className="muted">$</span>
        <input
          type="number"
          min={0}
          step={step}
          value={Math.round(value)}
          onChange={(e) => onChange(Math.max(0, Number(e.target.value) || 0))}
        />
        <span className="muted">/mo</span>
      </span>
    </label>
  );
}

/** Running costs for the profit view, and what they mean for each site. */
export function ProfitPanel({ costs, defaults, onChange, result, sites, dark }: Props) {
  const set = (patch: Partial<Costs>) => onChange({ ...costs, ...patch });
  const fixed = costs.rent_per_month + costs.wages_per_month + costs.other_fixed_per_month;
  const breakEven = fixed / Math.max(0.01, 1 - costs.cogs_share);
  const edited = JSON.stringify(costs) !== JSON.stringify(defaults);
  const slotOf = new Map(sites.map((s) => [s.id, s.slot]));
  const odds = new Map(result?.uncertainty?.sites.map((u) => [u.site_id, u]));

  return (
    <div className="profit">
      <div className="profit__head">
        <h2>Running costs</h2>
        {edited && (
          <button className="btn btn--ghost btn--small" onClick={() => onChange(defaults)}>
            Reset to profile
          </button>
        )}
      </div>
      <div className="cost-grid">
        <MoneyInput label="Rent" value={costs.rent_per_month} onChange={(v) => set({ rent_per_month: v })} />
        <MoneyInput label="Wages" value={costs.wages_per_month} onChange={(v) => set({ wages_per_month: v })} />
      </div>
      <details className="cost-more">
        <summary>Cost of goods and other costs</summary>
        <div className="cost-grid">
          <label className="cost-field">
            <span>Cost of goods</span>
            <span className="cost-input">
              <input
                type="number"
                min={0}
                max={90}
                step={1}
                value={Math.round(costs.cogs_share * 100)}
                onChange={(e) => set({ cogs_share: Math.min(0.9, Math.max(0, Number(e.target.value) / 100 || 0)) })}
              />
              <span className="muted">% of revenue</span>
            </span>
          </label>
          <MoneyInput
            label="Other fixed"
            value={costs.other_fixed_per_month}
            onChange={(v) => set({ other_fixed_per_month: v })}
            step={250}
          />
        </div>
      </details>
      <p className="muted small">
        Breaks even at {money(breakEven)} revenue a month ({money(fixed)} fixed costs, {pct(costs.cogs_share)} cost of
        goods).
      </p>
      {result && (
        <table className="profit-table">
          <thead>
            <tr>
              <th scope="col">Site</th>
              <th scope="col">36-month profit</th>
              <th scope="col">Chance of loss</th>
            </tr>
          </thead>
          <tbody>
            {result.sites.map((s) => {
              const u = odds.get(s.site.id);
              return (
                <tr key={s.site.id}>
                  <td>
                    <span className="site-key site-key--small" style={{ background: siteColor(slotOf.get(s.site.id) ?? 0, dark) }}>
                      {(slotOf.get(s.site.id) ?? 0) + 1}
                    </span>
                    <span className="profit-name">{s.site.label}</span>
                  </td>
                  <td className="num">
                    {s.total_profit === null ? "–" : money(s.total_profit)}
                    {u?.total_profit && (
                      <span className="site-range">
                        {money(u.total_profit.p10)} to {money(u.total_profit.p90)}
                      </span>
                    )}
                  </td>
                  <td className="num">{u?.prob_loss == null ? "…" : pct(u.prob_loss)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
