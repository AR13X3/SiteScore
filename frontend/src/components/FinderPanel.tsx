import { bulkAdd } from "../lib/finder";
import { money, pct } from "../lib/format";
import type { RankBy, SearchResult, SearchWhere, Spot } from "../lib/types";

export interface FinderSettings {
  lat: number;
  lon: number;
  radius: number;
  where: SearchWhere;
  retailOnly: boolean;
  rankBy: RankBy;
}

interface Props {
  settings: FinderSettings;
  onChange: (patch: Partial<FinderSettings>) => void;
  result: SearchResult | null;
  searching: boolean;
  elapsed: number;
  error: string | null;
  hasCosts: boolean;
  /** How many more sites the comparison can take. */
  room: number;
  maxSites: number;
  addedIds: Set<string>;
  activeId: string | null;
  onSearch: () => void;
  onSelect: (id: string) => void;
  onAdd: (spot: Spot) => void;
  onAddTop: (n: number) => void;
}

export const spotLetter = (rank: number) => String.fromCharCode(64 + rank);
const km = (m: number) => (m >= 1000 ? `${(m / 1000).toFixed(m % 1000 ? 1 : 0)} km` : `${m} m`);

/** Find the best spots inside a circle: vacant shopfronts or anywhere, by revenue or profit. */
export function FinderPanel(props: Props) {
  const { settings: s, onChange, result, searching, elapsed, error, hasCosts, room, addedIds } = props;
  const canAdd = room > 0;
  const profit = result?.rank_by === "profit";
  const bulk = bulkAdd(result?.spots.map((sp) => sp.id) ?? [], addedIds, room, props.maxSites);
  const stale = result && (result.lat !== round5(s.lat) || result.lon !== round5(s.lon) ||
    result.radius_m !== s.radius || result.where !== s.where || result.rank_by !== s.rankBy);

  return (
    <div className="finder">
      <p className="muted small finder__hint">
        Click the map to centre the search area, set its size, and SiteScore scores every candidate inside it.
      </p>
      <label className="finder__row">
        <span>Radius</span>
        <input
          type="range"
          min={250}
          max={3000}
          step={50}
          value={s.radius}
          onChange={(e) => onChange({ radius: Number(e.target.value) })}
          aria-valuetext={km(s.radius)}
        />
        <strong className="num">{km(s.radius)}</strong>
      </label>
      <div className="finder__row">
        <span>Look at</span>
        <div className="segmented" role="group" aria-label="Which candidates">
          {(["anywhere", "vacant"] as const).map((w) => (
            <button key={w} className={s.where === w ? "is-on" : ""} aria-pressed={s.where === w} onClick={() => onChange({ where: w })}>
              {w === "anywhere" ? "Anywhere" : "Vacant shopfronts"}
            </button>
          ))}
        </div>
      </div>
      {s.where === "anywhere" && (
        <label className="finder__check">
          <input type="checkbox" checked={s.retailOnly} onChange={(e) => onChange({ retailOnly: e.target.checked })} />
          Only shopping strips (near where similar businesses already trade)
        </label>
      )}
      <div className="finder__row">
        <span>Rank by</span>
        <div className="segmented" role="group" aria-label="Rank by">
          {(["revenue", "profit"] as const).map((r) => (
            <button
              key={r}
              className={s.rankBy === r ? "is-on" : ""}
              aria-pressed={s.rankBy === r}
              disabled={r === "profit" && !hasCosts}
              onClick={() => onChange({ rankBy: r })}
            >
              {r === "revenue" ? "Revenue" : "Profit"}
            </button>
          ))}
        </div>
      </div>
      <button className="btn btn--primary finder__go" onClick={props.onSearch} disabled={searching}>
        {searching ? `Searching… ${elapsed}s` : result && !stale ? "Search again" : "Find the best spots"}
      </button>
      {error && <p className="finder__error">{error}</p>}

      {result && (
        <div className={`finder__results ${searching || stale ? "is-loading" : ""}`}>
          <p className="muted small">
            {result.where === "vacant"
              ? `${result.n_candidates} vacant shopfront${result.n_candidates === 1 ? "" : "s"} in ${km(result.radius_m)}`
              : `${result.n_candidates} spots scored in ${km(result.radius_m)}`}
            {result.n_shortlisted > 0 && `; the best ${result.n_shortlisted} re-run with the full model`}
            {stale && " · settings changed, search again to update"}
          </p>
          {result.spots.length > 0 && (
            <ol className="spot-list">
              {result.spots.map((sp) => {
                const value = profit && sp.total_profit !== null ? sp.total_profit : sp.total_revenue;
                const range = profit ? sp.profit_range : sp.revenue_range;
                const added = addedIds.has(sp.id);
                return (
                  <li
                    key={sp.id}
                    className={`spot ${props.activeId === sp.id ? "is-active" : ""}`}
                    onMouseEnter={() => props.onSelect(sp.id)}
                  >
                    <button className="spot__letter" onClick={() => props.onSelect(sp.id)} aria-label={`Show spot ${spotLetter(sp.rank)} on the map`}>
                      {spotLetter(sp.rank)}
                    </button>
                    <div className="spot__title">
                      <strong>{sp.label}</strong>
                      {sp.kind !== "Location" && <span className={`tag ${sp.former_use === "cafe" ? "tag--strong" : ""}`}>{sp.kind}</span>}
                    </div>
                    <button className="btn btn--small spot__add" disabled={added || !canAdd} onClick={() => props.onAdd(sp)}>
                      {added ? "Added" : "Compare"}
                    </button>
                    {/* The figures get the card's full width, under the name and the button. */}
                    <dl className="spot__stats">
                      <div className="spot__stat--main">
                        <dt>{profit ? "Profit" : "Revenue"}, 36 mo</dt>
                        <dd className="num">{money(value)}</dd>
                      </div>
                      <div>
                        <dt>P10–P90</dt>
                        <dd className="num spot__range">
                          {range ? <>{money(range[0])}–<wbr />{money(range[1])}</> : "–"}
                        </dd>
                      </div>
                      <div>
                        <dt>Loss risk</dt>
                        <dd className="num">{sp.prob_loss === null ? "–" : pct(sp.prob_loss)}</dd>
                      </div>
                      <div>
                        <dt>Rent / month</dt>
                        <dd className="num">{sp.rent_monthly === null ? "–" : money(sp.rent_monthly)}</dd>
                      </div>
                    </dl>
                  </li>
                );
              })}
            </ol>
          )}
          {bulk.count > 0 && (
            <button className="btn btn--ghost btn--small" onClick={() => props.onAddTop(bulk.count)}>
              {bulk.label}
            </button>
          )}
          {bulk.note && <p className="muted small finder__room">{bulk.note}</p>}
          <ul className="finder__notes muted small">
            {result.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export const round5 = (v: number) => Math.round(v * 1e5) / 1e5;
