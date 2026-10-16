import { useEffect, useState } from "react";
import { API_EVENT, type ApiCall } from "../lib/api";
import type { Region, TableStatus } from "../lib/types";
import { ScrambleText } from "./Motion";

interface Props {
  region: Region | null;
  businessType: string;
  tables: TableStatus[];
  asOf: string | null;
  onPalette: () => void;
}

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

/** A terminal-style line above the top bar: where you are, the data, and the model's last run, live. */
export function StatusStrip({ region, businessType, tables, asOf, onPalette }: Props) {
  const [last, setLast] = useState<ApiCall | null>(null);
  useEffect(() => {
    const onCall = (e: Event) => {
      const call = (e as CustomEvent<ApiCall>).detail;
      if (call.endpoint === "geocode") return; // keystroke noise
      setLast(call);
    };
    window.addEventListener(API_EVENT, onCall);
    return () => window.removeEventListener(API_EVENT, onCall);
  }, []);
  const used = tables.filter((t) => t.model_visible);
  const real = used.filter((t) => t.provenance === "real").length;
  const today = new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD, local

  return (
    <div className="strip" role="status" aria-live="off">
      <span className="strip__path">
        <ScrambleText start="mount" text={`sitescore/${region?.id ?? "…"}/${businessType}`} cursor />
      </span>
      <span className="strip__item strip__hide-sm">
        data <b>{used.length ? `${real}/${used.length} real` : "…"}</b>
      </span>
      <span className="strip__item strip__hide-sm">
        as_of <b>{asOf ?? today}</b>
      </span>
      <span className="strip__item strip__hide-sm">
        {last ? (
          <>
            last_run <b className={last.ok ? "" : "is-bad"}>{last.endpoint}{last.ok ? "" : " failed"}</b>{" "}
            <b className="strip__ms">{last.ms < 1000 ? `${Math.round(last.ms)}ms` : `${(last.ms / 1000).toFixed(2)}s`}</b>
          </>
        ) : (
          <>model <b>ready</b></>
        )}
        <span className="strip__pulse" aria-hidden />
      </span>
      <button className="strip__palette" onClick={onPalette} aria-label="Open the command palette">
        <kbd>{isMac ? "⌘" : "Ctrl"}</kbd>
        <kbd>K</kbd>
        <span className="strip__hide-sm">commands</span>
      </button>
    </div>
  );
}
