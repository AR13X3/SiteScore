import { useEffect, useState } from "react";

export const MAX_SITES = 5;

// Sites are told apart by number (and, in charts, by line pattern), not by hue: colour
// is kept for the one that matters, so the selected site is the red signal and the
// rest are ink. A site keeps its slot for its whole life, so its number and pattern
// never change when another site is removed.
const SITE_DASH: ("solid" | number[])[] = ["solid", [7, 4], [2, 3], [10, 3, 2, 3], [14, 5]];

/** "01".."05" */
export const siteNumber = (slot: number) => String(slot + 1).padStart(2, "0");

/** The line pattern that identifies a site in charts. */
export function siteDash(slot: number): "solid" | number[] {
  return SITE_DASH[slot % MAX_SITES];
}

/** Red for the selected site, ink for the others. */
export function siteInk(selected: boolean, dark: boolean): string {
  if (selected) return dark ? "#ef6b6f" : "#e5484d";
  return dark ? "#bdbdb8" : "#4a4a47";
}

export type ThemePref = "system" | "light" | "dark";
const KEY = "sitescore.theme";
const QUERY = "(prefers-color-scheme: dark)";

function readPref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

/** Put the preference on <html> (CSS tokens key off data-theme). Call before first render. */
export function applyThemePref(pref: ThemePref = readPref()): void {
  const root = document.documentElement;
  if (pref === "system") delete root.dataset.theme;
  else root.dataset.theme = pref;
}

/** The theme preference (system / light / dark) and whether the page is dark right now. */
export function useTheme(): { pref: ThemePref; setPref: (p: ThemePref) => void; dark: boolean } {
  const [pref, setPrefState] = useState<ThemePref>(readPref);
  const [systemDark, setSystemDark] = useState(() => window.matchMedia(QUERY).matches);
  useEffect(() => {
    const mq = window.matchMedia(QUERY);
    const onChange = () => setSystemDark(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  const setPref = (p: ThemePref) => {
    try {
      if (p === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, p);
    } catch {
      // private mode: the choice lasts for this visit only
    }
    applyThemePref(p); // before the re-render, so charts read the new tokens
    setPrefState(p);
  };
  return { pref, setPref, dark: pref === "dark" || (pref === "system" && systemDark) };
}

/** Read a CSS custom property (theme token) from :root. */
export function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// Status colours are fixed (never themed) and always shown with a label or shape:
// colour never carries a status on its own.
export const STATUS = { good: "#0ca30c", critical: "#d03b3b" } as const;

// Ordinal single-hue ramp (red, the brand signal), checked per mode: the faint end
// clears 2:1 on the map tiles and the card surface, and each step is ~1.4x the last,
// so the order reads at a glance. More = darker on light, more = lighter on dark.
const ORDINAL = {
  light: ["#ec8f8a", "#e2655f", "#d0433c", "#ac2c26", "#7e1d1a"],
  dark: ["#9c3632", "#bd423d", "#dd5550", "#f2847f", "#fab8b4"],
};

export function ordinalColor(bin: number, dark: boolean): string {
  const ramp = ORDINAL[dark ? "dark" : "light"];
  return ramp[Math.max(0, Math.min(ramp.length - 1, bin))];
}

export const ORDINAL_BINS = ORDINAL.light.length;
