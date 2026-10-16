// The region-wide opportunity map (GET /api/heatmap): hex cells with a quick score each.

export interface Heatmap {
  business_type: string;
  as_of: string;
  spacing_m: number;
  lat: number[];
  lon: number[];
  value: number[];
}

/**
 * Bin edges as shares of cells: the map spends its darkest steps on the hotspots
 * (top 7%, next 11%...) rather than splitting the region into even fifths, where
 * most of the city would look as good as the CBD.
 */
export const HEAT_BREAKS = [0.4, 0.65, 0.82, 0.93];

export interface HeatIndex {
  /** Value at each break, ascending. */
  cuts: number[];
  /** Colour step of a value: 0 (lowest) to HEAT_BREAKS.length (top). */
  bin: (v: number) => number;
  /** Share of cells scoring below v (0..1). */
  percentile: (v: number) => number;
  /** Index of the cell under (lat, lon), or -1 when no cell is that close. */
  nearest: (lat: number, lon: number) => number;
}

const M_PER_DEG_LAT = 110_574;
const mPerDegLon = (lat: number) => 111_320 * Math.cos((lat * Math.PI) / 180);

export function heatIndex(h: Heatmap): HeatIndex {
  const sorted = [...h.value].sort((a, b) => a - b);
  const n = sorted.length;
  const cuts = HEAT_BREAKS.map((q) => sorted[Math.min(n - 1, Math.floor(q * n))] ?? 0);
  const below = (v: number) => {
    let lo = 0;
    let hi = n;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (sorted[mid] < v) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  };

  // Spatial hash: buckets one cell wide, so the nearest centre is in the 3x3 around a point.
  const lat0 = n ? h.lat.reduce((a, b) => Math.min(a, b)) : 0;
  const kx = mPerDegLon(lat0);
  const size = h.spacing_m;
  const key = (gx: number, gy: number) => `${gx}:${gy}`;
  const buckets = new Map<string, number[]>();
  const gxOf = (lon: number) => Math.floor((lon * kx) / size);
  const gyOf = (lat: number) => Math.floor((lat * M_PER_DEG_LAT) / size);
  h.lat.forEach((lat, i) => {
    const k = key(gxOf(h.lon[i]), gyOf(lat));
    const b = buckets.get(k);
    if (b) b.push(i);
    else buckets.set(k, [i]);
  });

  return {
    cuts,
    bin: (v) => cuts.filter((c) => v >= c).length,
    percentile: (v) => (n ? below(v) / n : 0),
    nearest: (lat, lon) => {
      const gx = gxOf(lon);
      const gy = gyOf(lat);
      let best = -1;
      let bestD = (size * 0.62) ** 2; // a little past a hex's corner (spacing / sqrt 3)
      for (let dx = -1; dx <= 1; dx++) {
        for (let dy = -1; dy <= 1; dy++) {
          for (const i of buckets.get(key(gx + dx, gy + dy)) ?? []) {
            const ex = (h.lon[i] - lon) * kx;
            const ey = (h.lat[i] - lat) * M_PER_DEG_LAT;
            const d = ex * ex + ey * ey;
            if (d < bestD) {
              bestD = d;
              best = i;
            }
          }
        }
      }
      return best;
    },
  };
}

/** Where a share-of-cells-below sits in the region: "Top 8%", or "Bottom 31%" below the median. */
export function topShare(percentile: number): string {
  const top = Math.max(1, Math.ceil((1 - percentile) * 100));
  return top <= 50 ? `Top ${top}%` : `Bottom ${Math.min(100, Math.floor(percentile * 100) + 1)}%`;
}
