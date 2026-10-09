import { useEffect, useState } from "react";

export const MAX_SITES = 5;

// Categorical slots, fixed order, validated for colour-vision deficiency
// (adjacent pairs) in both modes. A site keeps its slot for its whole life,
// so removing one never repaints the others.
const SITE_COLORS = {
  light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"],
  dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"],
};

export function siteColor(slot: number, dark: boolean): string {
  return SITE_COLORS[dark ? "dark" : "light"][slot % MAX_SITES];
}

export function useDarkMode(): boolean {
  const query = "(prefers-color-scheme: dark)";
  const [dark, setDark] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setDark(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return dark;
}

/** Read a CSS custom property (theme token) from :root. */
export function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// Status colours are fixed (never themed) and always shown with a label or shape:
// colour never carries a status on its own.
export const STATUS = { good: "#0ca30c", critical: "#d03b3b" } as const;

// Ordinal single-hue ramp (blue), validated per mode: light end clears 2:1 on the
// surface, steps read monotone. More = darker on light, more = lighter on dark.
const ORDINAL = {
  light: ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"],
  dark: ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4"],
};

export function ordinalColor(bin: number, dark: boolean): string {
  const ramp = ORDINAL[dark ? "dark" : "light"];
  return ramp[Math.max(0, Math.min(ramp.length - 1, bin))];
}

export const ORDINAL_BINS = ORDINAL.light.length;
