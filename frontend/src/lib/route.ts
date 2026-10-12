import { useEffect, useState } from "react";

export type Screen = "home" | "workspace" | "evidence" | "data";
const SCREENS: Screen[] = ["home", "workspace", "evidence", "data"];

/** "#workspace" -> "workspace"; the old "#backtest" link still lands on the evidence page. */
export function parseHash(hash: string): Screen {
  const h = hash.replace(/^#\/?/, "");
  if (h === "backtest") return "evidence";
  return (SCREENS as string[]).includes(h) ? (h as Screen) : "home";
}

/** The screen lives in the URL hash, so it survives reloads and can be linked. */
export function useScreen(): [Screen, (s: Screen) => void] {
  const [screen, setScreen] = useState<Screen>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onHash = () => {
      setScreen(parseHash(window.location.hash));
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return [screen, (s) => (window.location.hash = s === "home" ? "" : s)];
}
