import { useCallback, useEffect, useRef, useState } from "react";
import { API_EVENT, type ApiCall, OFFLINE_MESSAGE, api } from "../lib/api";
import { REPO_URL } from "../lib/project";
import { IconArrowUpRight, IconGithub, IconRefresh } from "./Icons";
import { BlockReveal, ScrambleText } from "./Motion";

const RECHECK_S = 30;
const clock = (d: Date) => d.toLocaleTimeString("en-AU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

/**
 * Checks the server every RECHECK_S seconds while `active`, and calls `onBack` once it
 * answers. Returns the countdown and a way to check now.
 */
function useRecheck(active: boolean, onBack: () => void) {
  const [next, setNext] = useState(RECHECK_S);
  const [checking, setChecking] = useState(false);
  const [last, setLast] = useState<Date | null>(null);
  const onBackRef = useRef(onBack);
  onBackRef.current = onBack;
  const left = useRef(RECHECK_S);

  const check = useCallback(async () => {
    left.current = RECHECK_S;
    setNext(RECHECK_S);
    setChecking(true);
    try {
      await api.health();
      onBackRef.current();
    } catch {
      // still down: wait for the next round
    } finally {
      setChecking(false);
      setLast(new Date());
    }
  }, []);

  // One 1-second tick drives the countdown; the count lives in a ref so a re-render
  // can never fire a second check.
  useEffect(() => {
    if (!active) return;
    left.current = RECHECK_S;
    setNext(RECHECK_S);
    const t = setInterval(() => {
      left.current -= 1;
      if (left.current <= 0) void check();
      else setNext(left.current);
    }, 1000);
    return () => clearInterval(t);
  }, [active, check]);

  return { next, checking, last, check };
}

/** The whole page when the app can't start: the model's server is down. */
export function MaintenancePage() {
  // Coming back means reloading: every screen then starts with fresh data.
  const { next, checking, last, check } = useRecheck(true, () => window.location.reload());
  return (
    <main className="page maintenance paper">
      <div className="maintenance__main">
        <ScrambleText className="kicker" start="mount" text="server.status() → offline" cursor />
        <BlockReveal className="page-title maintenance__title" text="Joy's server is offline and under maintenance" />
        <p className="maintenance__lede">
          SiteScore's model runs live on Joy's own server, and it's down for maintenance right now. This page checks
          every {RECHECK_S} seconds and comes back by itself as soon as the server does.
        </p>
        <div className="maintenance__status mono" role="status" aria-live="polite">
          <span className={`maintenance__dot ${checking ? "is-checking" : ""}`} aria-hidden />
          {checking ? "checking…" : last ? `still offline at ${clock(last)} · next check in ${next} s` : `next check in ${next} s`}
        </div>
        <div className="maintenance__actions">
          <button className="btn btn--accent" onClick={() => void check()} disabled={checking}>
            <IconRefresh size={15} /> Check now
          </button>
          <a className="btn" href={REPO_URL} target="_blank" rel="noreferrer">
            <IconGithub size={15} /> View the code
          </a>
          <a className="btn btn--ghost" href={`${REPO_URL}#quick-start`} target="_blank" rel="noreferrer">
            Run it yourself <IconArrowUpRight size={14} />
          </a>
        </div>
      </div>
    </main>
  );
}

/**
 * A thin bar under the top bar when the server stops answering mid-visit. It clears
 * itself on the next successful call, or when a background check gets through.
 */
export function OfflineBanner() {
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    const onCall = (e: Event) => {
      const call = (e as CustomEvent<ApiCall>).detail;
      if (call.offline) setOffline(true);
      else if (call.ok) setOffline(false);
    };
    window.addEventListener(API_EVENT, onCall);
    return () => window.removeEventListener(API_EVENT, onCall);
  }, []);
  const { next, checking, check } = useRecheck(offline, () => setOffline(false));
  if (!offline) return null;
  return (
    <div className="offline-bar" role="status">
      <span className="maintenance__dot" aria-hidden />
      <strong>{OFFLINE_MESSAGE}</strong>
      <span className="mono offline-bar__next">{checking ? "checking…" : `retrying in ${next} s`}</span>
      <button className="offline-bar__retry mono" onClick={() => void check()} disabled={checking}>
        retry now
      </button>
    </div>
  );
}
