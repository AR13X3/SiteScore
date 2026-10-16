import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";
import { money, pct } from "../lib/format";
import { HEAT_BREAKS, type HeatIndex, type Heatmap, topShare } from "../lib/heat";
import { ordinalColor } from "../lib/theme";
import type { BusinessType, Region, SiteSimulation, SiteUncertainty } from "../lib/types";
import { AnimatedNumber } from "./AnimatedNumber";
import { HexLayer } from "./HexLayer";
import { ScrambleText } from "./Motion";
import { IconArrowRight, IconX } from "./Icons";
import { ATTRIBUTION, AutoResize, TILES, whenSized } from "./SiteMap";
import { Sparkline } from "./Sparkline";

export interface Probe {
  lat: number;
  lon: number;
  key: number;
}

interface Props {
  region: Region;
  dark: boolean;
  heat: Heatmap | null;
  index: HeatIndex | null;
  heatError: string | null;
  types: BusinessType[];
  businessType: string;
  businessName: string;
  onBusinessType: (id: string) => void;
  probe: Probe | null;
  sim: SiteSimulation | null;
  odds?: SiteUncertainty;
  label: string;
  scoring: boolean;
  onProbe: (lat: number, lon: number) => void;
  onClear: () => void;
  onOpen: () => void;
  onExplain: () => void;
}

const probeIcon = L.divIcon({ className: "probe-pin", html: "<span></span><i></i>", iconSize: [22, 22], iconAnchor: [11, 11] });

function Pointer({ index, onHover, onProbe }: {
  index: HeatIndex | null;
  onHover: (h: { i: number; x: number; y: number } | null) => void;
  onProbe: (lat: number, lon: number) => void;
}) {
  useMapEvents({
    mousemove(e) {
      if (!index) return;
      const i = index.nearest(e.latlng.lat, e.latlng.lng);
      onHover(i >= 0 ? { i, x: e.containerPoint.x, y: e.containerPoint.y } : null);
    },
    mouseout: () => onHover(null),
    dragstart: () => onHover(null),
    click: (e) => onProbe(e.latlng.lat, e.latlng.lng),
  });
  return null;
}

const CARD_PX = 324; // the result card's width plus its margin

/** Keep the scored point clear of the result card that floats over the map's right side. */
function KeepProbeVisible({ probe }: { probe: Probe | null }) {
  const map = useMap();
  const first = useRef(true);
  useEffect(() => {
    if (!probe) return;
    return whenSized(map, () => {
      const size = map.getSize();
      const initial = first.current;
      first.current = false;
      if (size.x < 700) return; // the card sits under the map on small screens
      const p = map.latLngToContainerPoint([probe.lat, probe.lon]);
      if (!initial && p.x < size.x - CARD_PX - 24) return;
      const target = L.point((size.x - CARD_PX) / 2, size.y / 2);
      map.panBy(p.subtract(target), { animate: !initial, duration: 0.6 });
    });
  }, [probe?.key]);
  return null;
}

/** The overview's hero: the whole region scored on a hex grid, and a full run of the model wherever you click. */
export function OpportunityMap(props: Props) {
  const { region, dark, heat, index, heatError, types, businessType, businessName, onBusinessType } = props;
  const { probe, sim, odds, label, scoring, onProbe, onClear, onOpen, onExplain } = props;
  const [hover, setHover] = useState<{ i: number; x: number; y: number } | null>(null);
  const hoverValue = hover && heat ? heat.value[hover.i] : null;
  const probeCell = useMemo(
    () => (probe && index && heat ? index.nearest(probe.lat, probe.lon) : -1),
    [probe, index, heat],
  );
  const areaRank = probeCell >= 0 && heat && index ? topShare(index.percentile(heat.value[probeCell])) : null;
  const ready = sim && !scoring;
  const b = businessName.toLowerCase();

  return (
    <div className="opp">
      <div className="opp__stage">
        <MapContainer
          center={region.map.center}
          zoom={13}
          minZoom={12}
          maxZoom={17}
          scrollWheelZoom={false}
          className="map opp__map"
          attributionControl
        >
          <TileLayer url={TILES} attribution={ATTRIBUTION} maxZoom={19} />
          <AutoResize />
          {heat && index && (
            <HexLayer heat={heat} index={index} dark={dark} highlight={hover?.i ?? probeCell} revealFrom={region.map.center} />
          )}
          <Pointer index={index} onHover={setHover} onProbe={onProbe} />
          <KeepProbeVisible probe={probe} />
          {probe && <Marker key={probe.key} position={[probe.lat, probe.lon]} icon={probeIcon} interactive={false} keyboard={false} />}
        </MapContainer>

        <div className="opp__top">
          <div className="segmented opp__types" role="group" aria-label="Business type">
            {types.map((t) => (
              <button
                key={t.id}
                className={t.id === businessType ? "is-on" : ""}
                aria-pressed={t.id === businessType}
                onClick={() => onBusinessType(t.id)}
                title={t.status === "draft" ? `${t.name}: draft profile, assumptions not yet validated` : t.name}
              >
                {t.name}
                {t.status === "draft" && <span className="opp__draft">draft</span>}
              </button>
            ))}
          </div>
          {!heat && !heatError && (
            <span className="opp__status">
              <span className="spinner spinner--sm" aria-hidden /> Scoring every corner of {region.name} for a {b}…
            </span>
          )}
          {heatError && <span className="opp__status">Couldn't score the map: {heatError}</span>}
        </div>

        {hover && hoverValue !== null && index && (
          <div className="opp__readout" style={{ left: hover.x, top: hover.y }} aria-hidden>
            <strong className="num">≈ {money(hoverValue)}</strong>
            <span> a month</span>
            <span className="opp__readout-rank">{topShare(index.percentile(hoverValue))} of the region</span>
            <span className="opp__readout-hint">Quick estimate · click for the full model</span>
          </div>
        )}

        {heat && index && (
          <div className="opp__legend" aria-label="Map key">
            <span className="opp__legend-title">Quick estimate, monthly revenue</span>
            <div className="opp__ramp">
              {[0, ...index.cuts].map((c, step) => (
                <span key={step}>
                  <i style={{ background: ordinalColor(step, dark) }} />
                  <span className="num">{step === 0 ? "less" : `${money(c)}+`}</span>
                </span>
              ))}
            </div>
            <span className="opp__legend-note">
              {heat.lat.length.toLocaleString("en-AU")} cells, {heat.spacing_m} m apart · top {Math.round((1 - HEAT_BREAKS[HEAT_BREAKS.length - 1]) * 100)}% darkest
            </span>
          </div>
        )}

        {!probe && heat && (
          <div className="opp__hint">
            <ScrambleText start="mount" text="click_any_corner_to_score_it/" cursor delay={900} />
          </div>
        )}
      </div>

      {probe && (
        <aside className={`probe-card ${ready ? "" : "is-busy"}`} aria-live="polite">
          <header className="probe-card__head">
            <ScrambleText
              key={probe.key}
              className="probe-card__kicker"
              start="mount"
              text={`model.run(${businessName.toLowerCase().normalize("NFD").replace(/[^a-z]/g, "")})`}
            />
            <button className="icon-btn icon-btn--small" aria-label="Close" onClick={onClear}>
              <IconX size={14} />
            </button>
          </header>
          {sim ? (
            <>
              <h3 className="probe-card__title">{label}</h3>
              <div className="probe-card__value">
                <AnimatedNumber value={sim.total_revenue} from={0} format={money} />
                <span className="muted small">revenue over {sim.months.length} months</span>
              </div>
              <Sparkline
                values={sim.months.map((m) => m.revenue)}
                band={odds ? { p10: odds.revenue.p10, p90: odds.revenue.p90 } : null}
                animateKey={probe.key}
                label={`Monthly revenue over ${sim.months.length} months`}
              />
              <dl className="probe-card__stats">
                <div>
                  <dt>Mature month</dt>
                  <dd className="num">{money(sim.mature.monthly_revenue)}</dd>
                </div>
                <div>
                  <dt>Area</dt>
                  <dd>{areaRank ?? "–"}</dd>
                </div>
                <div>
                  <dt>Loss risk</dt>
                  <dd className="num">{odds?.prob_loss == null ? <span className="skeleton skeleton--text" /> : pct(odds.prob_loss)}</dd>
                </div>
              </dl>
              <div className="probe-card__actions">
                <button className="btn btn--small btn--accent" onClick={onOpen}>
                  Open in workspace <IconArrowRight size={14} />
                </button>
                <button className="btn btn--small btn--ghost" onClick={onExplain}>
                  How it's built
                </button>
              </div>
            </>
          ) : (
            <div className="probe-card__loading">
              <span className="skeleton skeleton--title" />
              <span className="skeleton skeleton--big" />
              <span className="skeleton skeleton--chart" />
              <span className="muted small">Running the full model: agents, price game, 36 months…</span>
            </div>
          )}
        </aside>
      )}
    </div>
  );
}
