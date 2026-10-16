import { siteNumber } from "../lib/theme";

/** A site's number as a small mono badge; the selected site's is the red one. */
export function SiteKey({ slot, selected = false }: { slot: number; selected?: boolean }) {
  return <span className={`site-key ${selected ? "is-selected" : ""}`}>{siteNumber(slot)}</span>;
}
