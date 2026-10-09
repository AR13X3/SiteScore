import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useMemo } from "react";
import { MapContainer, Marker, TileLayer, Tooltip, useMapEvents } from "react-leaflet";
import { siteColor } from "../lib/theme";
import type { CandidateSite, Region } from "../lib/types";

interface Props {
  region: Region;
  sites: CandidateSite[];
  dark: boolean;
  canAdd: boolean;
  onAdd: (lat: number, lon: number) => void;
  onMove: (id: string, lat: number, lon: number) => void;
}

// Standard OSM tiles (no key). They're desaturated in CSS so the coloured pins
// carry the identity, and inverted for dark mode.
const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

function ClickToAdd({ enabled, onAdd }: { enabled: boolean; onAdd: Props["onAdd"] }) {
  useMapEvents({
    click(e) {
      if (enabled) onAdd(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

function pinIcon(color: string, n: number): L.DivIcon {
  return L.divIcon({
    className: "site-pin",
    html: `<span style="--pin:${color}">${n}</span>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
}

export function SiteMap({ region, sites, dark, canAdd, onAdd, onMove }: Props) {
  const [lon0, lat0, lon1, lat1] = region.bbox;
  const bounds = useMemo(
    () => L.latLngBounds([lat0 - 0.03, lon0 - 0.05], [lat1 + 0.03, lon1 + 0.05]),
    [lat0, lon0, lat1, lon1],
  );
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
      {sites.map((s) => (
        <Marker
          key={s.id}
          position={[s.lat, s.lon]}
          icon={pinIcon(siteColor(s.slot, dark), s.slot + 1)}
          draggable
          eventHandlers={{
            dragend: (e) => {
              const p = (e.target as L.Marker).getLatLng();
              onMove(s.id, p.lat, p.lng);
            },
          }}
        >
          <Tooltip direction="top" offset={[0, -14]}>
            {s.label}
          </Tooltip>
        </Marker>
      ))}
    </MapContainer>
  );
}
