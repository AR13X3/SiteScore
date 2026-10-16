import { useEffect, useRef } from "react";
import { prefersReducedMotion } from "../lib/hooks";
import { token } from "../lib/theme";

/** Matches the grid paper (fixed to the viewport, 28 px cells), so pulses land on its lines. */
export const GRID_CELL = 28;
const REACH = 9;        // cells the ring travels
const STEP_MS = 42;     // ring speed: one cell per step
const BAND = 1.25;      // ring thickness, in cells
const MAX_PULSES = 6;

interface Pulse {
  cx: number;
  cy: number;
  born: number;
  ink: string;
  signal: string;
}

/**
 * A click sends one ring out through the grid cells around it: the clicked cell flashes
 * red, and a thin band of ink cells travels outwards and fades. The canvas sits under
 * the app, so it shows on the page background and grid paper and never covers text.
 */
export function GridPulse() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || prefersReducedMotion()) return;
    const ctx = canvas.getContext("2d")!;
    const pulses: Pulse[] = [];
    let raf = 0;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    const cell = (x: number, y: number, inset: number) =>
      ctx.fillRect(x * GRID_CELL + 1 + inset, y * GRID_CELL + 1 + inset, GRID_CELL - 1 - 2 * inset, GRID_CELL - 1 - 2 * inset);

    const frame = () => {
      const now = performance.now();
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      for (let k = pulses.length - 1; k >= 0; k--) {
        const p = pulses[k];
        const age = now - p.born;
        const ring = age / STEP_MS; // the ring's radius now, in cells
        if (ring > REACH + BAND) {
          pulses.splice(k, 1);
          continue;
        }
        // The ring: cells near its radius, fainter the further it has travelled.
        ctx.fillStyle = p.ink;
        for (let dy = -REACH; dy <= REACH; dy++) {
          for (let dx = -REACH; dx <= REACH; dx++) {
            const d = Math.hypot(dx, dy);
            if (d < 0.5 || d > REACH) continue;
            const near = 1 - Math.abs(d - ring) / BAND;
            if (near <= 0) continue;
            ctx.globalAlpha = 0.26 * near * (1 - d / (REACH + 1));
            cell(p.cx + dx, p.cy + dy, 0);
          }
        }
        // The clicked cell: solid red, shrinking to nothing as the ring leaves.
        const life = Math.min(1, age / (STEP_MS * 9));
        if (life < 1) {
          ctx.globalAlpha = 1 - life * 0.6;
          ctx.fillStyle = p.signal;
          cell(p.cx, p.cy, (GRID_CELL / 2 - 1) * life * life);
        }
      }
      ctx.globalAlpha = 1;
      raf = pulses.length ? requestAnimationFrame(frame) : 0;
    };

    const onDown = (e: PointerEvent) => {
      if (e.button !== 0) return;
      pulses.push({
        cx: Math.floor(e.clientX / GRID_CELL),
        cy: Math.floor(e.clientY / GRID_CELL),
        born: performance.now(),
        ink: token("--text-primary") || "#161616",
        signal: token("--signal") || "#e5484d",
      });
      if (pulses.length > MAX_PULSES) pulses.shift();
      if (!raf) raf = requestAnimationFrame(frame);
    };

    resize();
    window.addEventListener("resize", resize);
    window.addEventListener("pointerdown", onDown, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointerdown", onDown);
    };
  }, []);

  return <canvas ref={ref} className="grid-pulse" aria-hidden />;
}
