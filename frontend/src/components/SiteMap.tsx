import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { Circle, CircleMarker, MapContainer, Marker, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import { money } from "../lib/format";
import { type HeatIndex, type Heatmap, topShare } from "../lib/heat";
import { prefersReducedMotion } from "../lib/hooks";
import { ORDINAL_BINS, ordinalColor, siteInk, token } from "../lib/theme";
import type { CandidateSite, GridPoint, Region, SiteSimulation, Spot, Vacancy } from "../lib/types";
import { HexLayer } from "./HexLayer";

interface Props {
  region: Region;
  sites: CandidateSite[];
  dark: boolean;
  canAdd: boolean;
  selectedId: string | null;
  /** The selected site's simulation: draws its catchments, competitors and anchors. */
  overlay?: SiteSimulation;
  /** Fly here when `key` changes (a picked address, a selected site). */
  focus?: { lat: number; lon: number; key: number };
  /** Frame all sites when `key` changes (e.g. after loading the demo sites). */
  fitKey?: number;
  onAdd: (lat: number, lon: number) => void;
  onMove: (id: string, lat: number, lon: number) => void;
  onSelect: (id: string) => void;
  /** Spot finder: the search circle. While set, map clicks move it instead of adding sites. */
  finder?: { lat: number; lon: number; radius: number } | null;
  onFinderMove?: (lat: number, lon: number) => void;
  spots?: Spot[];
  grid?: GridPoint[];
  vacancies?: Vacancy[];
  activeSpotId?: string | null;
  onSpotSelect?: (id: string) => void;
  /** The region-wide quick score: drawn under everything when showHeat, read while dragging a pin. */
  heat?: { heat: Heatmap; index: HeatIndex } | null;
  showHeat?: boolean;
  /** Site hovered anywhere in the workspace (card, chart, table), and who to tell about pin hovers. */
  hoverId?: string | null;
  onHover?: (id: string | null) => void;
}

// Standard OSM tiles (no key). They're desaturated in CSS so the coloured pins
// carry the identity, and inverted for dark mode.
export const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
export const ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const SEGMENT_NAMES: Record<string, string> = { residents: "residents", workers: "workers", commuters: "commuters" };

interface Ring { segment: string; minutes: number; radius: number }
interface Rival { name: string; lat: number; lon: number; distance_m: number; share_of_local_demand: number }
interface Anchor { name: string; lat: number; lon: number; distance_m: number }

function ClickToAdd({ enabled, onAdd }: { enabled: boolean; onAdd: Props["onAdd"] }) {
  useMapEvents({
    click(e) {
      if (enabled) onAdd(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

const centreIcon = L.divIcon({ className: "finder-centre", html: "<span></span>", iconSize: [18, 18], iconAnchor: [9, 9] });
const vacancyIcon = L.divIcon({ className: "vacancy-mark", html: "<span></span>", iconSize: [12, 12], iconAnchor: [6, 6] });

function spotIcon(letter: string, active: boolean): L.DivIcon {
  return L.divIcon({
    className: `spot-pin ${active ? "is-active" : ""}`,
    html: `<span>${letter}</span>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  });
}

/** Quintile bins of the quick score, so the ramp shows rank within this circle. */
function gridBins(grid: GridPoint[]): (v: number) => number {
  const v = grid.map((g) => g.quick_monthly).sort((a, b) => a - b);
  const cuts = [...Array(ORDINAL_BINS - 1).keys()].map((i) => v[Math.floor(((i + 1) * v.length) / ORDINAL_BINS)] ?? 0);
  return (x: number) => cuts.filter((c) => x >= c).length;
}

/**
 * Run a map move once the map has a real size. A map that was hidden (another
 * screen) measures 0 x 0 until Leaflet re-measures, and moving it then throws.
 */
export function whenSized(map: L.Map, run: () => void): () => void {
  const ready = () => {
    map.invalidateSize();
    const size = map.getSize();
    return size.x > 0 && size.y > 0;
  };
  if (ready()) {
    run();
    return () => {};
  }
  const ro = new ResizeObserver(() => {
    if (ready()) {
      ro.disconnect();
      run();
    }
  });
  ro.observe(map.getContainer());
  return () => ro.disconnect();
}

/** Leaflet measures its container once; re-measure when it resizes or is un-hidden. */
export function AutoResize() {
  const map = useMap();
  useEffect(() => {
    const ro = new ResizeObserver(() => map.invalidateSize());
    ro.observe(map.getContainer());
    return () => ro.disconnect();
  }, [map]);
  return null;
}

function FlyTo({ focus }: { focus?: Props["focus"] }) {
  const map = useMap();
  useEffect(() => {
    if (!focus) return;
    return whenSized(map, () => map.flyTo([focus.lat, focus.lon], Math.max(map.getZoom(), 15), { duration: 0.8 }));
  }, [focus?.key]);
  return null;
}

function FitSites({ sites, fitKey }: { sites: CandidateSite[]; fitKey?: number }) {
  const map = useMap();
  useEffect(() => {
    if (!fitKey || !sites.length) return;
    const bounds = L.latLngBounds(sites.map((s) => [s.lat, s.lon]));
    return whenSized(map, () => map.flyToBounds(bounds, { padding: [60, 60], maxZoom: 15, duration: 0.8 }));
  }, [fitKey]);
  return null;
}

// The same icon object for the same look: a new one would make Leaflet swap the pin's
// element, which breaks a drag in progress (the map re-renders while a pin is dragged).
const pinIcons = new Map<string, L.DivIcon>();

function pinIcon(n: number, selected: boolean, isNew = false): L.DivIcon {
  const key = `${n}|${selected}|${isNew}`;
  let icon = pinIcons.get(key);
  if (!icon) pinIcons.set(key, (icon = makePinIcon(n, selected, isNew)));
  return icon;
}

/** A hex cell like the logo's: ink with its number, the selected one red and larger. */
function makePinIcon(n: number, selected: boolean, isNew: boolean): L.DivIcon {
  const size = selected ? 38 : 32;
  return L.divIcon({
    className: `site-pin ${selected ? "is-selected" : ""} ${isNew ? "is-new" : ""}`,
    html: `<span><b>${n}</b></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

const anchorIcon = L.divIcon({ className: "anchor-mark", html: "<span></span>", iconSize: [12, 12], iconAnchor: [6, 6] });

/** Ring labels at each ring's top edge, skipping any that would collide at this zoom. */
function RingLabels({ lat, lon, rings }: { lat: number; lon: number; rings: Ring[] }) {
  const map = useMap();
  const [zoom, setZoom] = useState(map.getZoom());
  useMapEvents({ zoomend: () => setZoom(map.getZoom()) });
  const centre = map.project([lat, lon], zoom);
  let lastY = Infinity;
  const shown = rings.filter((r) => {
    const y = map.project([lat + r.radius / 111_320, lon], zoom).y;
    if (Math.abs(centre.y - y) < 22 || Math.abs(lastY - y) < 16) return false;
    lastY = y;
    return true;
  });
  return (
    <>
      {shown.map((r) => (
        <Marker
          key={`label-${r.segment}`}
          position={[lat + r.radius / 111_320, lon]}
          icon={ringLabel(`${r.minutes} min · ${SEGMENT_NAMES[r.segment] ?? r.segment}`)}
          interactive={false}
          keyboard={false}
        />
      ))}
    </>
  );
}

function ringLabel(text: string): L.DivIcon {
  return L.divIcon({ className: "ring-label", html: `<span>${text}</span>`, iconSize: [0, 0] });
}

/** A catchment ring that grows out from its site when the site is selected. */
function GrowingCircle({ center, radius, delay, pathOptions }: {
  center: [number, number];
  radius: number;
  delay: number;
  pathOptions: L.PathOptions;
}) {
  const ref = useRef<L.Circle>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c || prefersReducedMotion()) return;
    const start = performance.now() + delay;
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.max(0, Math.min(1, (t - start) / 650));
      c.setRadius(Math.max(1, radius * (1 - (1 - p) ** 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    c.setRadius(1);
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      c.setRadius(radius);
    };
  }, [center[0], center[1], radius, delay]);
  return <Circle ref={ref} center={center} radius={radius} interactive={false} pathOptions={pathOptions} />;
}

type DragAt = { lat: number; lon: number } | null;

/**
 * While a pin is dragged: the quick score of the corner under it, next to the pin.
 * It listens on its own channel so only it re-renders during a drag: re-rendering the
 * map would hand every marker its position again and snap the dragged pin back.
 */
function DragReadout({ channel, heat }: { channel: { current: (at: DragAt) => void }; heat: Props["heat"] }) {
  const map = useMap();
  const [at, setAt] = useState<DragAt>(null);
  useEffect(() => {
    channel.current = setAt;
    return () => {
      channel.current = () => {};
    };
  }, [channel]);
  if (!at || !heat) return null;
  const i = heat.index.nearest(at.lat, at.lon);
  if (i < 0) return null;
  const v = heat.heat.value[i];
  const p = map.latLngToContainerPoint([at.lat, at.lon]);
  return (
    <div className="drag-readout" style={{ left: p.x, top: p.y }}>
      <strong className="num">≈ {money(v)}</strong> a month
      <span>{topShare(heat.index.percentile(v))} of the region · quick estimate</span>
    </div>
  );
}

/** Read what the map draws from the selected site's layer details. */
export function overlayData(sim: SiteSimulation) {
  const layer = (key: string) => sim.mature.layers.find((l) => l.key === key)?.details ?? {};
  const segments = (layer("demand").segments ?? {}) as Record<string, { walk_minutes: number; straight_radius_m?: number; radius_m: number }>;
  const rings: Ring[] = Object.entries(segments)
    .map(([segment, s]) => ({ segment, minutes: s.walk_minutes, radius: s.straight_radius_m ?? s.radius_m }))
    .sort((a, b) => b.radius - a.radius);
  const rivals = ((layer("competition").top_competitors ?? []) as Rival[]).filter((r) => r.lat && r.lon);
  const anchors = ((layer("anchors").anchors ?? []) as Anchor[]).filter((a) => a.lat && a.lon);
  return { rings, rivals, anchors };
}

export function SiteMap(props: Props) {
  const { region, sites, dark, canAdd, selectedId, overlay, focus, fitKey, onAdd, onMove, onSelect } = props;
  const { finder, onFinderMove, spots = [], grid = [], vacancies = [], activeSpotId, onSpotSelect } = props;
  const { heat, showHeat = false, hoverId = null, onHover } = props;
  const dragChannel = useRef<(at: DragAt) => void>(() => {});
  const markers = useRef(new Map<string, L.Marker>());
  // New pins drop in; pins that already existed don't replay it when their icon changes.
  const born = useRef(new Map<string, number>());
  const now = performance.now();
  for (const s of sites) if (!born.current.has(s.id)) born.current.set(s.id, now);
  useEffect(() => {
    for (const [id, m] of markers.current) m.getElement()?.classList.toggle("is-hover", id === hoverId);
  });
  const bin = useMemo(() => gridBins(grid), [grid]);
  const [lon0, lat0, lon1, lat1] = region.bbox;
  const bounds = useMemo(
    () => L.latLngBounds([lat0 - 0.03, lon0 - 0.05], [lat1 + 0.03, lon1 + 0.05]),
    [lat0, lon0, lat1, lon1],
  );
  const selected = sites.find((s) => s.id === selectedId);
  const data = overlay && selected ? overlayData(overlay) : null;
  const color = siteInk(true, dark); // the selected site's catchments are the red signal
  const maxShare = Math.max(0.0001, ...(data?.rivals.map((r) => r.share_of_local_demand) ?? []));
  const surface = token("--surface");
  const contextInk = token("--text-secondary");

  return (
    <MapContainer
      center={region.map.center}
      zoom={region.map.zoom}
      minZoom={12}
      maxBounds={bounds}
      className={`map ${canAdd || finder ? "map--adding" : ""}`}
      attributionControl
    >
      <TileLayer url={TILES} attribution={ATTRIBUTION} maxZoom={19} />
      {showHeat && heat && <HexLayer heat={heat.heat} index={heat.index} dark={dark} opacity={sites.length ? 0.55 : 0.85} />}
      <DragReadout channel={dragChannel} heat={heat} />
      <ClickToAdd
        enabled={finder ? true : canAdd}
        onAdd={finder && onFinderMove ? onFinderMove : onAdd}
      />
      {finder && (
        <>
          <Circle
            center={[finder.lat, finder.lon]}
            radius={finder.radius}
            interactive={false}
            pathOptions={{ color: token("--text-primary"), weight: 1.5, opacity: 0.6, fillOpacity: 0.03 }}
          />
          {grid.map((g, i) => (
            <CircleMarker
              key={`g${i}`}
              center={[g.lat, g.lon]}
              radius={3.5}
              interactive={false}
              pathOptions={{ weight: 0, fillColor: ordinalColor(bin(g.quick_monthly), dark), fillOpacity: 0.85 }}
            />
          ))}
          {vacancies.map((v) => (
            <Marker key={v.id} position={[v.lat, v.lon]} icon={vacancyIcon} keyboard={false}>
              <Tooltip direction="top" offset={[0, -6]}>
                <strong>{v.kind}</strong>
                <br />
                {v.label}
              </Tooltip>
            </Marker>
          ))}
          <Marker
            position={[finder.lat, finder.lon]}
            icon={centreIcon}
            draggable
            keyboard={false}
            eventHandlers={{
              dragend: (e) => {
                const p = (e.target as L.Marker).getLatLng();
                onFinderMove?.(p.lat, p.lng);
              },
            }}
          >
            <Tooltip direction="top" offset={[0, -10]}>Drag to move the search area</Tooltip>
          </Marker>
          {spots.map((sp) => (
            <Marker
              key={sp.id}
              position={[sp.lat, sp.lon]}
              icon={spotIcon(String.fromCharCode(64 + sp.rank), sp.id === activeSpotId)}
              zIndexOffset={sp.id === activeSpotId ? 900 : 500}
              eventHandlers={{ click: () => onSpotSelect?.(sp.id) }}
            >
              <Tooltip direction="top" offset={[0, -12]}>
                <strong>{String.fromCharCode(64 + sp.rank)}. {sp.label}</strong>
                <br />
                {sp.kind}
              </Tooltip>
            </Marker>
          ))}
        </>
      )}
      <FlyTo focus={focus} />
      <FitSites sites={sites} fitKey={fitKey} />
      <AutoResize />

      {data && selected && (
        <>
          {data.rings.map((r, i) => (
            <GrowingCircle
              key={`${selected.id}-${r.segment}`}
              center={[selected.lat, selected.lon]}
              radius={r.radius}
              delay={(data.rings.length - 1 - i) * 90}
              pathOptions={{ color, weight: 1.5, opacity: 0.85, fillColor: color, fillOpacity: dark ? 0.06 : 0.05 }}
            />
          ))}
          <RingLabels lat={selected.lat} lon={selected.lon} rings={data.rings} />
          {data.anchors.map((a, i) => (
            <Marker key={`anchor-${i}`} position={[a.lat, a.lon]} icon={anchorIcon} keyboard={false}>
              <Tooltip direction="top" offset={[0, -6]}>
                <strong>{a.name}</strong>
                <br />
                Anchor, {a.distance_m} m walk
              </Tooltip>
            </Marker>
          ))}
          {data.rivals.map((r, i) => (
            <CircleMarker
              key={`rival-${i}`}
              center={[r.lat, r.lon]}
              radius={4 + 9 * Math.sqrt(r.share_of_local_demand / maxShare)}
              bubblingMouseEvents={false}
              pathOptions={{ color: surface, weight: 2, fillColor: contextInk, fillOpacity: 0.8 }}
            >
              <Tooltip direction="top">
                <strong>{r.name}</strong>
                <br />
                {r.distance_m} m walk · takes {(r.share_of_local_demand * 100).toFixed(1)}% of this site's local demand
              </Tooltip>
            </CircleMarker>
          ))}
        </>
      )}

      {sites.map((s) => (
        <Marker
          key={s.id}
          ref={(m) => {
            if (m) markers.current.set(s.id, m);
            else markers.current.delete(s.id);
          }}
          position={[s.lat, s.lon]}
          icon={pinIcon(s.slot + 1, s.id === selectedId, now - (born.current.get(s.id) ?? 0) < 700)}
          draggable
          zIndexOffset={s.id === selectedId ? 1000 : 0}
          eventHandlers={{
            click: () => onSelect(s.id),
            mouseover: () => onHover?.(s.id),
            mouseout: () => onHover?.(null),
            drag: (e) => {
              const p = (e.target as L.Marker).getLatLng();
              dragChannel.current({ lat: p.lat, lon: p.lng });
            },
            dragend: (e) => {
              const p = (e.target as L.Marker).getLatLng();
              dragChannel.current(null);
              onMove(s.id, p.lat, p.lng);
              onSelect(s.id);
            },
          }}
        >
          <Tooltip direction="top" offset={[0, -16]}>
            {s.label}
          </Tooltip>
        </Marker>
      ))}
    </MapContainer>
  );
}
