interface Props {
  values: number[];
  /** Optional P10–P90 band behind the line. */
  band?: { p10: number[]; p90: number[] } | null;
  height?: number;
  /** Changes re-run the draw-in animation (e.g. a new site). */
  animateKey?: string | number;
  label: string;
}

const W = 300; // viewBox width; the SVG stretches to its container

/** A 36-month line that draws itself in, with its scenario range shaded behind it. */
export function Sparkline({ values, band, height = 64, animateKey, label }: Props) {
  if (values.length < 2) return null;
  const all = [...values, ...(band?.p90 ?? []), ...(band?.p10 ?? [])];
  const lo = Math.min(0, ...all);
  const hi = Math.max(...all) || 1;
  const pad = 4;
  const x = (i: number) => (i / (values.length - 1)) * W;
  const y = (v: number) => pad + (1 - (v - lo) / (hi - lo)) * (height - pad * 2);
  const line = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const area = band
    ? band.p90.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("") +
      band.p10.map((_, j) => {
        const i = band.p10.length - 1 - j;
        return `L${x(i).toFixed(1)},${y(band.p10[i]).toFixed(1)}`;
      }).join("") + "Z"
    : null;
  const last = values.length - 1;
  return (
    <div className="spark" style={{ height }} role="img" aria-label={label}>
      <svg viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" aria-hidden>
        {area && <path className="spark__band" d={area} />}
        <path key={animateKey} className="spark__line" d={line} pathLength={1} vectorEffect="non-scaling-stroke" />
      </svg>
      {/* HTML, not SVG: the stretched viewBox would squash a circle into an ellipse. */}
      <span key={`dot-${animateKey}`} className="spark__dot" style={{ top: `${(y(values[last]) / height) * 100}%` }} />
    </div>
  );
}
