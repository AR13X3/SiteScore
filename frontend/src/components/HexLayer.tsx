import L from "leaflet";
import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";
import { HEAT_BREAKS, type HeatIndex, type Heatmap } from "../lib/heat";
import { prefersReducedMotion } from "../lib/hooks";
import { ordinalColor, token } from "../lib/theme";

interface Props {
  heat: Heatmap;
  index: HeatIndex;
  dark: boolean;
  /** Overall strength: lower when pins and catchments sit on top. */
  opacity?: number;
  /** Cell to outline (the one under the pointer). */
  highlight?: number;
  /** Where new data ripples in from (default: the map centre). */
  revealFrom?: [number, number];
}

const SQRT3 = Math.sqrt(3);
const PANE = "hexPane";
// Lower steps are fainter, so streets and suburbs stay readable under the mosaic.
const STEP_ALPHA = [0.22, 0.42, 0.6, 0.8, 0.94];
const REVEAL_SPREAD_MS = 900; // the ripple reaches the furthest cell after this
const REVEAL_GROW_MS = 380;   // each cell grows over this

const easeOutBack = (t: number) => 1 + 2.2 * (t - 1) ** 3 + 1.2 * (t - 1) ** 2;

function hexPath(ctx: CanvasRenderingContext2D, x: number, y: number, r: number) {
  // Pointy-top: matches the API's grid (rows sqrt(3)/2 apart, odd rows offset by half).
  const h = (r * SQRT3) / 2;
  ctx.moveTo(x, y - r);
  ctx.lineTo(x + h, y - r / 2);
  ctx.lineTo(x + h, y + r / 2);
  ctx.lineTo(x, y + r);
  ctx.lineTo(x - h, y + r / 2);
  ctx.lineTo(x - h, y - r / 2);
  ctx.closePath();
}

/**
 * The opportunity map as a hex mosaic on a canvas in its own pane (above the tiles,
 * below catchments and pins). Redraws on pan and follows Leaflet's zoom animation.
 */
export function HexLayer(props: Props) {
  const map = useMap();
  const propsRef = useRef(props);
  propsRef.current = props;
  const ctl = useRef<{ draw: () => void; reveal: () => void } | null>(null);

  useEffect(() => {
    const pane = map.getPane(PANE) ?? map.createPane(PANE);
    pane.style.zIndex = "350";
    pane.style.pointerEvents = "none";
    const canvas = L.DomUtil.create("canvas", "hex-canvas leaflet-zoom-animated", pane);
    const ctx = canvas.getContext("2d")!;
    let delays: Float32Array | null = null;
    let revealStart = 0;
    let raf = 0;

    const draw = () => {
      const { heat, index, dark, opacity = 1, highlight = -1 } = propsRef.current;
      const size = map.getSize();
      ctx.clearRect(0, 0, size.x, size.y);
      const n = heat.lat.length;
      if (!n) return;
      const lat = heat.lat[0];
      const a = map.latLngToContainerPoint([lat, heat.lon[0]]);
      const b = map.latLngToContainerPoint([lat, heat.lon[0] + heat.spacing_m / (111_320 * Math.cos((lat * Math.PI) / 180))]);
      const R = Math.abs(b.x - a.x) / SQRT3;
      const r = R - (R > 4 ? Math.min(1.25, R * 0.08) : 0);
      const now = performance.now();
      const animating = delays !== null;
      const pts = heat.lat.map((la, i) => map.latLngToContainerPoint([la, heat.lon[i]]));
      const bins = heat.value.map(index.bin);
      let done = true;
      for (let step = 0; step <= HEAT_BREAKS.length; step++) {
        ctx.beginPath();
        for (let i = 0; i < n; i++) {
          if (bins[i] !== step) continue;
          const p = pts[i];
          if (p.x < -R || p.y < -R || p.x > size.x + R || p.y > size.y + R) continue;
          let rr = r;
          if (animating) {
            const t = (now - revealStart - delays![i]) / REVEAL_GROW_MS;
            if (t < 1) done = false;
            if (t <= 0) continue;
            rr = r * Math.min(1.08, easeOutBack(Math.min(1, t)));
          }
          hexPath(ctx, p.x, p.y, rr);
        }
        ctx.globalAlpha = STEP_ALPHA[step] * opacity;
        ctx.fillStyle = ordinalColor(step, dark);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      if (highlight >= 0 && highlight < n) {
        const p = pts[highlight];
        ctx.beginPath();
        hexPath(ctx, p.x, p.y, R + 1);
        ctx.lineWidth = 2;
        ctx.strokeStyle = token("--text-primary");
        ctx.stroke();
      }
      if (animating) {
        cancelAnimationFrame(raf); // one frame loop, however many redraws were asked for
        if (done) delays = null;
        else raf = requestAnimationFrame(draw);
      }
    };

    const reposition = () => {
      L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]));
      cancelAnimationFrame(raf);
      draw();
    };
    const resize = () => {
      const size = map.getSize();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = size.x * dpr;
      canvas.height = size.y * dpr;
      canvas.style.width = `${size.x}px`;
      canvas.style.height = `${size.y}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      reposition();
    };
    const animateZoom = (e: L.ZoomAnimEvent) => {
      const scale = map.getZoomScale(e.zoom);
      // Leaflet's own overlays use this (private) helper to follow the zoom animation.
      const offset = (map as unknown as { _latLngBoundsToNewLayerBounds: (b: L.LatLngBounds, z: number, c: L.LatLng) => L.Bounds })
        ._latLngBoundsToNewLayerBounds(map.getBounds(), e.zoom, e.center).min!;
      L.DomUtil.setTransform(canvas, offset, scale);
    };
    const reveal = () => {
      const { heat, revealFrom } = propsRef.current;
      cancelAnimationFrame(raf);
      if (prefersReducedMotion() || !heat.lat.length) {
        delays = null;
        draw();
        return;
      }
      const o = revealFrom ? map.latLngToContainerPoint(revealFrom) : map.getSize().divideBy(2);
      const d = heat.lat.map((la, i) => o.distanceTo(map.latLngToContainerPoint([la, heat.lon[i]])));
      const far = Math.max(1, ...d);
      delays = Float32Array.from(d, (x) => (x / far) * REVEAL_SPREAD_MS);
      revealStart = performance.now();
      raf = requestAnimationFrame(draw);
    };

    ctl.current = { draw, reveal };
    map.on("move zoomend viewreset", reposition);
    map.on("resize", resize);
    map.on("zoomanim", animateZoom);
    resize();
    return () => {
      cancelAnimationFrame(raf);
      map.off("move zoomend viewreset", reposition);
      map.off("resize", resize);
      map.off("zoomanim", animateZoom);
      canvas.remove();
      ctl.current = null;
    };
  }, [map]);

  // New data ripples in; anything else just redraws.
  useEffect(() => ctl.current?.reveal(), [props.heat]);
  useEffect(() => ctl.current?.draw(), [props.dark, props.opacity, props.highlight, props.index]);
  return null;
}
