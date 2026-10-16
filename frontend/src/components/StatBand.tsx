import type { ReactNode } from "react";
import { type HeatIndex, type Heatmap } from "../lib/heat";
import { useInView } from "../lib/hooks";
import { ordinalColor } from "../lib/theme";
import type { SiteSimulation, SiteUncertainty, TableStatus } from "../lib/types";
import { AnimatedNumber } from "./AnimatedNumber";
import { IconArrowRight } from "./Icons";

interface Props {
  heat: Heatmap | null;
  index: HeatIndex | null;
  tables: TableStatus[];
  sim: SiteSimulation | null;
  odds?: SiteUncertainty;
  dark: boolean;
  onData: () => void;
  onWorkspace: () => void;
}

const whole = (n: number) => Math.round(n).toLocaleString("en-AU");
const compact = (n: number) =>
  new Intl.NumberFormat("en-AU", { notation: "compact", maximumFractionDigits: 1 }).format(Math.round(n));
const BINS = 16;

/** How the region's quick scores spread: most corners are quiet, a few are hot. */
function Histogram({ heat, index, dark }: { heat: Heatmap; index: HeatIndex; dark: boolean }) {
  const sorted = [...heat.value].sort((a, b) => a - b);
  const top = sorted[Math.floor(sorted.length * 0.99)] || 1;
  const counts = Array(BINS).fill(0);
  for (const v of heat.value) counts[Math.min(BINS - 1, Math.floor((v / top) * BINS))]++;
  const max = Math.max(...counts, 1);
  return (
    <span className="viz viz--bars" aria-hidden>
      {counts.map((c, i) => (
        <i key={i} style={{ height: `${Math.max(6, (c / max) * 100)}%`, background: ordinalColor(index.bin(((i + 0.5) / BINS) * top), dark) }} />
      ))}
    </span>
  );
}

/** Rows per table, as one split bar. */
function TableSplit({ tables }: { tables: TableStatus[] }) {
  const real = tables.filter((t) => t.provenance === "real" && t.rows).sort((a, b) => (b.rows ?? 0) - (a.rows ?? 0));
  const total = real.reduce((a, t) => a + (t.rows ?? 0), 0) || 1;
  return (
    <span className="viz viz--split" aria-hidden>
      {real.map((t, i) => (
        <i key={t.table} title={`${t.table}: ${whole(t.rows ?? 0)} rows`} style={{ flexGrow: (t.rows ?? 0) / total, opacity: 1 - i * 0.11 }} />
      ))}
    </span>
  );
}

/** One square per model input: filled when it runs on real data. */
function InputSquares({ tables }: { tables: TableStatus[] }) {
  return (
    <span className="viz viz--squares" aria-hidden>
      {tables.filter((t) => t.model_visible).map((t) => (
        <i key={t.table} className={t.provenance === "real" ? "is-real" : ""} title={`${t.table}: ${t.provenance ?? "missing"}`} />
      ))}
    </span>
  );
}

/** 300 dots, one per scenario at the scored corner: red ones end in a loss. */
function ScenarioDots({ odds }: { odds?: SiteUncertainty }) {
  const losses = odds?.prob_loss == null ? null : Math.round(odds.prob_loss * 300);
  return (
    <span className={`viz viz--dots ${losses === null ? "is-pending" : ""}`} aria-hidden>
      {Array.from({ length: 300 }, (_, i) => (
        <i key={i} className={losses !== null && i < losses ? "is-loss" : ""} />
      ))}
    </span>
  );
}

/** The scored corner's 36 months, darker as revenue ramps up. */
function MonthStrip({ sim }: { sim: SiteSimulation | null }) {
  const values = sim?.months.map((m) => m.revenue) ?? Array(36).fill(0);
  const max = Math.max(...values, 1);
  return (
    <span className="viz viz--months" aria-hidden>
      {values.map((v, i) => (
        <i key={i} style={{ opacity: sim ? 0.15 + 0.85 * (v / max) : 0.12 }} />
      ))}
    </span>
  );
}

function Cell({ n, code, viz, value, format, label, note, seen }: {
  n: number; code: string; viz: ReactNode; value: number; format: (v: number) => string; label: string; note?: string; seen: boolean;
}) {
  return (
    <div className="stat-band__item">
      <span className="stat-band__top mono">
        <span className="stat-band__n">{String(n).padStart(2, "0")}</span>
        {code}
      </span>
      {viz}
      <AnimatedNumber className="stat-band__value" value={seen ? value : 0} from={0} duration={1100} format={format} />
      <span className="stat-band__label">{label}</span>
      {note && <span className="stat-band__note mono">{note}</span>}
    </div>
  );
}

/** The model's footprint in five numbers, each with a small picture of the real data behind it. */
export function StatBand({ heat, index, tables, sim, odds, dark, onData, onWorkspace }: Props) {
  const [ref, seen] = useInView<HTMLDivElement>(0.3);
  const used = tables.filter((t) => t.model_visible);
  const real = used.filter((t) => t.provenance === "real").length;
  const rows = tables.filter((t) => t.provenance === "real").reduce((a, t) => a + (t.rows ?? 0), 0);
  const losses = odds?.prob_loss == null ? null : Math.round(odds.prob_loss * 300);

  return (
    <div className="card stat-band" ref={ref}>
      <Cell n={1} code="heat.cells" seen={seen} value={heat?.lat.length ?? 0} format={whole}
        label="corners scored on the map" note="spread of quick scores"
        viz={heat && index ? <Histogram heat={heat} index={index} dark={dark} /> : <span className="viz viz--bars skeleton" />} />
      <Cell n={2} code="data.rows" seen={seen} value={rows} format={compact}
        label="rows of official and open data" note="split by table" viz={<TableSplit tables={tables} />} />
      <Cell n={3} code="inputs.real" seen={seen} value={real} format={(v) => `${Math.round(v)} of ${used.length || 6}`}
        label="model inputs on real data" note="one square per input" viz={<InputSquares tables={tables} />} />
      <Cell n={4} code="scenarios" seen={seen} value={300} format={whole} label="scenarios behind every range"
        note={losses === null ? "running at this corner…" : `${losses} end in a loss here`} viz={<ScenarioDots odds={odds} />} />
      <Cell n={5} code="horizon" seen={seen} value={sim?.months.length ?? 36} format={whole} label="months projected, monthly"
        note="this corner's ramp-up" viz={<MonthStrip sim={sim} />} />
      <div className="stat-band__links">
        <button className="btn btn--small" onClick={onData}>
          Data sources
        </button>
        <button className="btn btn--small btn--accent" onClick={onWorkspace}>
          Open workspace <IconArrowRight size={14} />
        </button>
      </div>
    </div>
  );
}
