/** "Compare the top 3" adds only what fits in the comparison; this says how many, and
 * the panel shows it on the button, so spots are never dropped silently. */
export interface BulkAdd {
  /** How many spots the button adds (0 or 1: no button, the row buttons do it). */
  count: number;
  label: string;
  /** Shown when the comparison can't take all of them. */
  note: string | null;
}

export function bulkAdd(spotIds: string[], addedIds: Set<string>, room: number, maxSites: number,
                        want = 3): BulkAdd {
  const notAdded = spotIds.filter((id) => !addedIds.has(id)).length;
  const count = Math.max(0, Math.min(want, room, notAdded));
  const label = `Compare the ${notAdded < spotIds.length ? "next" : "top"} ${count}`;
  let note: string | null = null;
  if (spotIds.length > 0 && room < Math.min(want, notAdded)) {
    note = room <= 0
      ? `The comparison is full (${maxSites} sites): remove a site to add a spot.`
      : `Room for ${room} more: the comparison holds ${maxSites} sites.`;
  }
  return { count: count >= 2 ? count : 0, label, note };
}
