import { type RefObject, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Heatmap } from "./heat";

/** Seconds since `running` became true (for "Searching… 4s" style progress). */
export function useElapsed(running: boolean): number {
  const [s, setS] = useState(0);
  useEffect(() => {
    if (!running) return;
    setS(0);
    const t = setInterval(() => setS((v) => v + 1), 1000);
    return () => clearInterval(t);
  }, [running]);
  return s;
}

// One request per (business type, date), shared by every screen that draws the map.
const heatCache = new Map<string, Promise<Heatmap>>();

/** Start loading a map early (e.g. behind the loading screen) so it's there when shown. */
export function prefetchHeatmap(businessType: string, asOf: string | null = null): void {
  const key = `${businessType}|${asOf ?? ""}`;
  if (heatCache.has(key)) return;
  const p = api.heatmap(businessType, asOf);
  heatCache.set(key, p);
  p.catch(() => heatCache.delete(key));
}

/** The region-wide opportunity map; null while it loads (the first one takes ~10 s). */
export function useHeatmap(businessType: string, asOf: string | null): { heat: Heatmap | null; error: string | null } {
  const [state, setState] = useState<{ key: string; heat: Heatmap | null; error: string | null }>({
    key: "", heat: null, error: null,
  });
  const key = `${businessType}|${asOf ?? ""}`;
  useEffect(() => {
    let live = true;
    let p = heatCache.get(key);
    if (!p) {
      p = api.heatmap(businessType, asOf);
      heatCache.set(key, p);
      p.catch(() => heatCache.delete(key)); // let a later visit retry
    }
    setState((s) => (s.key === key ? s : { key, heat: null, error: null }));
    p.then(
      (heat) => live && setState({ key, heat, error: null }),
      (e: Error) => live && setState({ key, heat: null, error: e.message }),
    );
    return () => {
      live = false;
    };
  }, [key, businessType, asOf]);
  return state.key === key ? { heat: state.heat, error: state.error } : { heat: null, error: null };
}

/** True when the visitor asked for less motion (animations then jump to their end). */
export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** True once the element has scrolled into view (stays true). */
export function useInView<T extends Element>(threshold = 0.25): [RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    if (seen || !ref.current) return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setSeen(true), { threshold });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [seen, threshold]);
  return [ref, seen];
}
