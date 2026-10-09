import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { type ReactNode, useEffect, useMemo, useRef } from "react";
import { CircleMarker, MapContainer, TileLayer, Tooltip, useMap } from "react-leaflet";
import { token } from "../lib/theme";
import type { Region } from "../lib/types";
import { ATTRIBUTION, TILES, whenSized } from "./SiteMap";

export interface MapPoint {
  id: string;
  lat: number;
  lon: number;
  fill: string;
  hollow?: boolean;
  tooltip: ReactNode;
}

interface Props {
  region: Region;
  points: MapPoint[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  label: string;
}

/** Fit the points once per point set, as soon as the map has a size (it may start hidden). */
function FitTo({ points }: { points: MapPoint[] }) {
  const map = useMap();
  const fitted = useRef("");
  useEffect(() => {
    const key = `${points.length}:${points[0]?.id ?? ""}`;
    const fit = () => {
      if (!points.length || fitted.current === key || map.getSize().x === 0) return;
      map.fitBounds(L.latLngBounds(points.map((p) => [p.lat, p.lon])), { padding: [24, 24], maxZoom: 15 });
      fitted.current = key;
    };
    fit();
    const ro = new ResizeObserver(() => {
      map.invalidateSize();
      fit();
    });
    ro.observe(map.getContainer());
    return () => ro.disconnect();
  }, [map, points]);
  return null;
}

function FlyToSelected({ point }: { point?: MapPoint }) {
  const map = useMap();
  useEffect(() => {
    if (!point) return;
    return whenSized(map, () => {
      if (!map.getBounds().pad(-0.1).contains([point.lat, point.lon])) map.panTo([point.lat, point.lon]);
    });
  }, [map, point]);
  return null;
}

/** Businesses as dots: ≥8 px marks with a 2 px surface ring, selectable. */
export function PointsMap({ region, points, selectedId, onSelect, label }: Props) {
  const [lon0, lat0, lon1, lat1] = region.bbox;
  const bounds = useMemo(
    () => L.latLngBounds([lat0 - 0.03, lon0 - 0.05], [lat1 + 0.03, lon1 + 0.05]),
    [lat0, lon0, lat1, lon1],
  );
  const surface = token("--surface");
  const ink = token("--text-primary");
  const muted = token("--text-muted");
  const selected = points.find((p) => p.id === selectedId);
  // Draw the selected point last so it sits on top.
  const ordered = selected ? [...points.filter((p) => p.id !== selectedId), selected] : points;

  return (
    <MapContainer center={region.map.center} zoom={region.map.zoom} minZoom={11} maxBounds={bounds} className="map" aria-label={label}>
      <TileLayer url={TILES} attribution={ATTRIBUTION} maxZoom={19} />
      <FitTo points={points} />
      <FlyToSelected point={selected} />
      {ordered.map((p) => {
        const on = p.id === selectedId;
        return (
          <CircleMarker
            key={p.id}
            center={[p.lat, p.lon]}
            radius={on ? 9 : 6}
            pathOptions={{
              color: on ? ink : p.hollow ? muted : surface,
              weight: 2,
              fillColor: p.hollow ? surface : p.fill,
              fillOpacity: 1,
            }}
            eventHandlers={{ click: () => onSelect(p.id) }}
          >
            <Tooltip direction="top" offset={[0, -6]}>
              {p.tooltip}
            </Tooltip>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
