import type { TableStatus } from "../lib/types";

/** Shows how much of the data behind the results is real vs mock. */
export function DataBadge({ tables }: { tables: TableStatus[] }) {
  if (!tables.length) return null;
  const used = tables.filter((t) => t.model_visible);
  const real = used.filter((t) => t.provenance === "real").length;
  const state = real === used.length ? "real" : real === 0 ? "mock" : "mixed";
  const label = { real: "Real data", mock: "Mock data", mixed: `${real}/${used.length} sources real` }[state];
  const detail = tables
    .map((t) => `${t.provenance === "real" ? "●" : "○"} ${t.source}: ${t.provenance ?? "missing"}${t.note ? ` (${t.note})` : ""}`)
    .join("\n");
  return (
    <span className={`badge badge--${state}`} title={detail}>
      <span className="badge__dot" aria-hidden />
      {label}
    </span>
  );
}
