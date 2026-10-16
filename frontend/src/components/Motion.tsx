import { type CSSProperties, type ElementType, Fragment, useEffect, useState } from "react";
import { prefersReducedMotion, useInView } from "../lib/hooks";
import { countFrame, scrambleFrame } from "../lib/scramble";

interface ScrambleProps {
  text: string;
  /** Decode when first scrolled into view (default) or straight away. */
  start?: "view" | "mount";
  /** Decode again when pointed at. */
  replayOnHover?: boolean;
  /** Decode again whenever this changes (e.g. a parent card was pointed at). */
  replay?: number;
  /** A blinking block after the text. */
  cursor?: boolean;
  duration?: number;
  delay?: number;
  className?: string;
}

/** Monospace text that decodes out of random glyphs, like a terminal printing it. */
export function ScrambleText({ text, start = "view", replayOnHover, replay = 0, cursor, duration = 700, delay = 0, className }: ScrambleProps) {
  const [ref, inView] = useInView<HTMLSpanElement>(0.1);
  const [shown, setShown] = useState(() => (prefersReducedMotion() ? text : scrambleFrame(text, 0)));
  const [runs, setRuns] = useState(0);
  const go = start === "mount" || inView;

  useEffect(() => {
    if (!go) return;
    if (prefersReducedMotion()) {
      setShown(text);
      return;
    }
    let raf = 0;
    let last = 0;
    const t0 = performance.now() + delay;
    const tick = (t: number) => {
      const p = (t - t0) / duration;
      if (t - last > 45 || p >= 1) { // ~20 fps flicker reads as text, not noise
        last = t;
        setShown(p >= 1 ? text : scrambleFrame(text, Math.max(0, p)));
      }
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [go, text, duration, delay, runs, replay]);

  return (
    <span
      ref={ref}
      className={`mono scramble ${className ?? ""}`}
      aria-label={text}
      onMouseEnter={replayOnHover ? () => setRuns((r) => r + 1) : undefined}
    >
      <span aria-hidden>{shown}</span>
      {cursor && <span className="block-cursor" aria-hidden />}
    </span>
  );
}

/**
 * A headline whose words are uncovered by solid accent blocks: each block sweeps
 * in, then pulls away to leave the word behind it (pure CSS, keyed by --d).
 */
export function BlockReveal({ text, as: Tag = "h1", className, delay = 260 }: {
  text: string;
  as?: ElementType;
  className?: string;
  delay?: number;
}) {
  const words = text.split(" ");
  return (
    <Tag className={`block-reveal ${className ?? ""}`} aria-label={text}>
      {words.map((w, i) => (
        <Fragment key={i}>
          <span className="block-reveal__word" aria-hidden style={{ "--d": `${delay + i * 130}ms` } as CSSProperties}>
            <span className="block-reveal__text">{w}</span>
          </span>
          {i < words.length - 1 ? " " : ""}
        </Fragment>
      ))}
    </Tag>
  );
}

/**
 * Types each line out, holds it, deletes it, moves to the next: a placeholder that
 * shows what you could ask. Returns the text so far and which line it is.
 */
export function useTypewriter(lines: string[], active: boolean): { text: string; line: number } {
  const [state, setState] = useState({ text: "", line: 0 });
  const key = lines.join("|");
  useEffect(() => {
    if (!active || !lines.length) return;
    if (prefersReducedMotion()) {
      setState({ text: lines[0], line: 0 });
      return;
    }
    let line = 0;
    let i = 0;
    let typing = true;
    let timer = 0;
    const step = () => {
      const full = lines[line];
      if (typing) {
        i++;
        if (i >= full.length) {
          typing = false;
          timer = window.setTimeout(step, 2000);
        } else timer = window.setTimeout(step, 26 + Math.random() * 45);
      } else {
        i--;
        if (i <= 0) {
          typing = true;
          line = (line + 1) % lines.length;
          timer = window.setTimeout(step, 380);
        } else timer = window.setTimeout(step, 12);
      }
      setState({ text: lines[line].slice(0, Math.max(0, i)), line });
    };
    timer = window.setTimeout(step, 900);
    return () => clearTimeout(timer);
  }, [active, key]);
  return state;
}

/** Text whose numbers count up from zero the first time it scrolls into view ("0 of 25", "60%"). */
export function CountUpText({ text, duration = 1000, className }: { text: string; duration?: number; className?: string }) {
  const [ref, inView] = useInView<HTMLSpanElement>(0.3);
  const [shown, setShown] = useState(() => (prefersReducedMotion() ? text : countFrame(text, 0)));
  useEffect(() => {
    if (!inView) return;
    if (prefersReducedMotion()) {
      setShown(text);
      return;
    }
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const p = (t - t0) / duration;
      setShown(p >= 1 ? text : countFrame(text, p));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, text, duration]);
  return (
    <span ref={ref} className={`num ${className ?? ""}`} aria-label={text}>
      <span aria-hidden>{shown}</span>
    </span>
  );
}
