import { useEffect, useId, useRef, useState } from "react";
import { api } from "../lib/api";
import type { GeocodeHit } from "../lib/types";

interface Props {
  disabled: boolean;
  onPick: (hit: GeocodeHit) => void;
}

/** Type an address, pick a match, and it becomes a candidate site. */
export function AddressSearch({ disabled, onPick }: Props) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<GeocodeHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [status, setStatus] = useState<"idle" | "searching" | "none" | "error">("idle");
  const listId = useId();
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const query = q.trim();
    if (query.length < 3) {
      setHits([]);
      setStatus("idle");
      return;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(async () => {
      setStatus("searching");
      try {
        const found = await api.geocode(query, ctrl.signal);
        setHits(found);
        setActive(0);
        setStatus(found.length ? "idle" : "none");
        setOpen(true);
      } catch (e) {
        if ((e as Error).name !== "AbortError") setStatus("error");
      }
    }, 300);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [q]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const pick = (hit: GeocodeHit) => {
    onPick(hit);
    setQ("");
    setHits([]);
    setOpen(false);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, hits.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && open && hits[active]) {
      e.preventDefault();
      pick(hits[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const showList = open && hits.length > 0;
  return (
    <div className="search" ref={box}>
      <input
        className="search__input"
        type="search"
        placeholder={disabled ? "Remove a site to add another" : "Add a site by address…"}
        value={q}
        disabled={disabled}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => hits.length && setOpen(true)}
        onKeyDown={onKey}
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showList ? `${listId}-${active}` : undefined}
      />
      {status === "searching" && <span className="search__hint muted">Searching…</span>}
      {status === "none" && <span className="search__hint muted">No address found in the region</span>}
      {status === "error" && <span className="search__hint muted">Address search unavailable</span>}
      {showList && (
        <ul className="search__list" id={listId} role="listbox">
          {hits.map((h, i) => (
            <li
              key={`${h.lat},${h.lon},${i}`}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? "is-active" : ""}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(h);
              }}
            >
              {h.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** "12 Church Street, Parramatta NSW 2150" -> "12 Church Street" */
export function shortAddress(label: string): string {
  const first = label.split(",")[0].trim();
  return first.length > 40 ? `${first.slice(0, 39)}…` : first;
}
