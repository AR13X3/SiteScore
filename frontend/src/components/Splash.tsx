import { useEffect, useState } from "react";
import { prefersReducedMotion } from "../lib/hooks";
import { ScrambleText } from "./Motion";

export interface BootStep {
  id: string;
  label: string;
  done: boolean;
  /** What came back, once it has: "city of parramatta", "6/6 real". */
  detail?: string;
}

interface Props {
  steps: BootStep[];
  /** The screen starts lifting: mount what's underneath, so its intro plays as it's revealed. */
  onLeave: () => void;
  onDone: () => void;
}

const MIN_MS = 1500;  // long enough for the mark to assemble
const MAX_MS = 9000;  // never hold the page hostage to a slow request
const EXIT_MS = 700;

/**
 * The first screen of a visit: the mark assembles cell by cell while the app's real
 * start-up requests tick off, then the screen lifts away. Shown once per session.
 */
export function Splash({ steps, onLeave, onDone }: Props) {
  // Time from the first frame on screen, not from mount: a busy first load can delay the
  // paint, and the mark should still get its moment.
  const [start, setStart] = useState<number | null>(null);
  const [leaving, setLeaving] = useState(false);
  const done = steps.filter((s) => s.done).length;
  const ready = done === steps.length;

  useEffect(() => {
    const r = requestAnimationFrame(() => setStart(performance.now()));
    return () => cancelAnimationFrame(r);
  }, []);

  useEffect(() => {
    if (leaving || start === null) return;
    const shown = performance.now() - start;
    const wait = ready ? MIN_MS - shown : MAX_MS - shown;
    const t = setTimeout(() => {
      setLeaving(true);
      onLeave();
    }, Math.max(0, wait));
    return () => clearTimeout(t);
  }, [ready, leaving, start, onLeave]);

  useEffect(() => {
    if (!leaving) return;
    const t = setTimeout(onDone, prefersReducedMotion() ? 0 : EXIT_MS);
    return () => clearTimeout(t);
  }, [leaving, onDone]);

  return (
    <div className={`splash ${leaving ? "is-leaving" : ""}`} role="status" aria-live="polite" aria-label="Loading SiteScore">
      <div className="splash__inner">
        <svg className="splash__mark" width="76" height="76" viewBox="0 0 32 32" aria-hidden>
          <path className="splash__cell splash__cell--a" d="M10.2 4.5l5.54 3.2v6.4l-5.54 3.2-5.54-3.2V7.7z" />
          <path className="splash__cell splash__cell--b" d="M21.8 4.5l5.54 3.2v6.4l-5.54 3.2-5.54-3.2V7.7z" />
          <path className="splash__cell splash__cell--pick" d="M16 14.7l5.54 3.2v6.4L16 27.5l-5.54-3.2v-6.4z" />
        </svg>
        <div className="splash__name">
          <ScrambleText start="mount" text="sitescore/" cursor delay={350} duration={600} />
        </div>
        <ul className="splash__steps mono">
          {steps.map((s, i) => (
            <li key={s.id} className={s.done ? "is-done" : ""} style={{ animationDelay: `${450 + i * 90}ms` }}>
              <span className="splash__step">{s.label}</span>
              <span className="splash__dots" aria-hidden />
              <span className="splash__detail">{s.done ? s.detail ?? "" : ""}</span>
              <span className="splash__ok">{s.done ? "ok" : "··"}</span>
            </li>
          ))}
        </ul>
        <div className="splash__bar" aria-hidden>
          <i style={{ transform: `scaleX(${done / Math.max(1, steps.length)})` }} />
        </div>
      </div>
    </div>
  );
}
