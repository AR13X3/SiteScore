import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useMemo, useState } from "react";
import { Circle, CircleMarker, MapContainer, Marker, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import { siteColor, token } from "../lib/theme";
import type { CandidateSite, Region, SiteSimulation } from "../lib/types";

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
    if (focus) map.flyTo([focus.lat, focus.lon], Math.max(map.getZoom(), 15), { duration: 0.8 });
  }, [focus?.key]);
  return null;
}

function FitSites({ sites, fitKey }: { sites: CandidateSite[]; fitKey?: number }) {
  const map = useMap();
  useEffect(() => {
    if (fitKey && sites.length) {
      map.flyToBounds(L.latLngBounds(sites.map((s) => [s.lat, s.lon])), { padding: [60, 60], maxZoom: 15, duration: 0.8 });
    }
  }, [fitKey]);
  return null;
}

function pinIcon(color: string, n: number, selected: boolean): L.DivIcon {
  const size = selected ? 36 : 30;
  return L.divIcon({
    className: `site-pin ${selected ? "is-selected" : ""}`,
    html: `<span style="--pin:${color}">${n}</span>`,
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
  const [lon0, lat0, lon1, lat1] = region.bbox;
  const bounds = useMemo(
    () => L.latLngBounds([lat0 - 0.03, lon0 - 0.05], [lat1 + 0.03, lon1 + 0.05]),
    [lat0, lon0, lat1, lon1],
  );
  const selected = sites.find((s) => s.id === selectedId);
  const data = overlay && selected ? overlayData(overlay) : null;
  const color = selected ? siteColor(selected.slot, dark) : "";
  const maxShare = Math.max(0.0001, ...(data?.rivals.map((r) => r.share_of_local_demand) ?? []));
  const surface = token("--surface");
  const contextInk = token("--text-secondary");

  return (
    <MapContainer
      center={region.map.center}
      zoom={region.map.zoom}
      minZoom={12}
      maxBounds={bounds}
      className={`map ${canAdd ? "map--adding" : ""}`}
      attributionControl
    >
      <TileLayer url={TILES} attribution={ATTRIBUTION} maxZoom={19} />
      <ClickToAdd enabled={canAdd} onAdd={onAdd} />
      <FlyTo focus={focus} />
      <FitSites sites={sites} fitKey={fitKey} />
      <AutoResize />

      {data && selected && (
        <>
          {data.rings.map((r) => (
            <Circle
              key={r.segment}
              center={[selected.lat, selected.lon]}
              radius={r.radius}
              interactive={false}
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
          position={[s.lat, s.lon]}
          icon={pinIcon(siteColor(s.slot, dark), s.slot + 1, s.id === selectedId)}
          draggable
          zIndexOffset={s.id === selectedId ? 1000 : 0}
          eventHandlers={{
            click: () => onSelect(s.id),
            dragend: (e) => {
              const p = (e.target as L.Marker).getLatLng();
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
