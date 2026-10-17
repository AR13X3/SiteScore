import type { Screen } from "./route";

/**
 * Visit counts for the live site, through GoatCounter: no cookies and nothing personal
 * stored, so no consent banner. Off unless the build sets VITE_GOATCOUNTER, so local
 * runs and forks count nothing.
 */

// count.js pinned to a version and checked against its hash.
const SCRIPT = "https://gc.zgo.at/count.v5.js";
const INTEGRITY = "sha384-atnOLvQb9t+jTSipvd75X2yginT4PjVbqDdlJAmxMm+wYElFmeR6EmLP5bYeoRVQ";

const TITLES: Record<Screen, string> = { home: "Home", workspace: "Workspace", evidence: "Evidence", data: "Data" };

/** "joy" or a full https count URL -> the URL to count to; anything else -> null (off). */
export function countEndpoint(setting: string | undefined): string | null {
  const s = (setting ?? "").trim();
  if (!s) return null;
  if (/^[a-z0-9-]+$/i.test(s)) return `https://${s.toLowerCase()}.goatcounter.com/count`;
  try {
    const url = new URL(s);
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

/** One path per screen, so "#backtest" and stray hashes count as the screen they show. */
export function pagePath(pathname: string, screen: Screen): { path: string; title: string } {
  return {
    path: screen === "home" ? pathname : `${pathname}#${screen}`,
    title: `SiteScore · ${TITLES[screen]}`,
  };
}

type Hit = { path: string; title: string; referrer?: () => string };
type GoatCounter = { count?: (hit: Hit) => void };

/** Load count.js and count the landing screen, then every screen change after it. */
export function startAnalytics(setting: string | undefined, screen: () => Screen): void {
  const endpoint = countEndpoint(setting);
  if (!endpoint) return;

  const landing = pagePath(window.location.pathname, screen());
  let last = "";
  const count = (page: { path: string; title: string }, inApp: boolean) => {
    const gc = (window as { goatcounter?: GoatCounter }).goatcounter;
    if (!gc?.count || page.path === last) return;
    last = page.path;
    // A move inside the app has no referrer: otherwise every screen would repeat the
    // site that sent the visitor, and that site would look several times as big.
    gc.count(inApp ? { ...page, referrer: () => "" } : page);
  };
  const current = () => pagePath(window.location.pathname, screen());

  const script = document.createElement("script");
  script.async = true;
  script.src = SCRIPT;
  script.integrity = INTEGRITY;
  script.crossOrigin = "anonymous";
  script.dataset.goatcounter = endpoint;
  script.dataset.goatcounterSettings = JSON.stringify({ no_onload: true });
  script.addEventListener("load", () => {
    count(landing, false);
    count(current(), true); // moved on while the script was loading
  });
  document.head.appendChild(script);
  window.addEventListener("hashchange", () => count(current(), true));
}
