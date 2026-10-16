import { useEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "../lib/hooks";

interface Props {
  value: number;
  format: (n: number) => string;
  /** Count up from here on first render (default: start at the value, no animation). */
  from?: number;
  duration?: number;
  className?: string;
}

const easeOut = (t: number) => 1 - (1 - t) ** 3;

/**
 * A number that glides to its new value instead of jumping, so a change (a dragged
 * pin, a new cost) reads as a change. Screen readers get the final value only.
 */
export function AnimatedNumber({ value, format, from, duration = 650, className }: Props) {
  const [shown, setShown] = useState(from ?? value);
  const current = useRef(from ?? value);
  useEffect(() => {
    if (prefersReducedMotion() || !Number.isFinite(value)) {
      current.current = value;
      setShown(value);
      return;
    }
    const start = performance.now();
    const a = current.current;
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / duration);
      const v = a + (value - a) * easeOut(p);
      current.current = v;
      setShown(v);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);
  return (
    <span className={`num ${className ?? ""}`}>
      <span aria-hidden>{format(shown)}</span>
      <span className="sr-only">{format(value)}</span>
    </span>
  );
}
