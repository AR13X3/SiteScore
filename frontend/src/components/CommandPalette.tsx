import { useEffect, useMemo, useRef, useState } from "react";
import { IconArrowRight, IconChat } from "./Icons";

export interface Command {
  id: string;
  group: string;
  label: string;
  /** Extra words it should match ("dark", "night"). */
  keywords?: string;
  hint?: string;
  run: () => void;
}

interface Props {
  open: boolean;
  onClose: () => void;
  commands: Command[];
  /** With text typed: offer it to the analyst as a question. */
  onAsk?: (question: string) => void;
}

function matches(c: Command, q: string): boolean {
  const hay = `${c.group} ${c.label} ${c.keywords ?? ""}`.toLowerCase();
  return q.toLowerCase().split(/\s+/).filter(Boolean).every((w) => hay.includes(w));
}

/** Ctrl/Cmd+K: jump anywhere, load demo sites, switch business or theme, or ask the analyst. */
export function CommandPalette({ open, onClose, commands, onAsk }: Props) {
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (!open) return;
    setQ("");
    setActive(0);
    requestAnimationFrame(() => input.current?.focus());
  }, [open]);

  const items = useMemo(() => {
    const found = commands.filter((c) => matches(c, q));
    const text = q.trim();
    if (text && onAsk) {
      found.push({
        id: "ask", group: "Analyst", label: `Ask: “${text}”`, hint: "Enter",
        run: () => onAsk(text),
      });
    }
    return found;
  }, [commands, q, onAsk]);

  useEffect(() => {
    list.current?.querySelector(".is-active")?.scrollIntoView({ block: "nearest" });
  }, [active]);

  if (!open) return null;
  const run = (c: Command | undefined) => {
    if (!c) return;
    onClose();
    c.run();
  };
  let lastGroup = "";

  return (
    <div className="palette-scrim" onMouseDown={onClose}>
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose();
          else if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(items.length - 1, a + 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(0, a - 1));
          } else if (e.key === "Enter") {
            e.preventDefault();
            run(items[active]);
          }
        }}
      >
        <div className="palette__input">
          <span className="mono palette__prompt" aria-hidden>
            &gt;
          </span>
          <input
            ref={input}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setActive(0);
            }}
            placeholder="Type a command, or a question for the analyst"
            aria-label="Command"
            aria-controls="palette-list"
            aria-activedescendant={items[active] ? `cmd-${items[active].id}` : undefined}
          />
          <kbd>Esc</kbd>
        </div>
        <ul className="palette__list" id="palette-list" role="listbox" ref={list}>
          {items.length === 0 && <li className="palette__empty muted">No commands match.</li>}
          {items.map((c, i) => {
            const head = c.group !== lastGroup ? c.group : null;
            lastGroup = c.group;
            return (
              <li key={c.id} role="presentation">
                {head && <span className="palette__group mono">{head.toLowerCase()}/</span>}
                <button
                  id={`cmd-${c.id}`}
                  role="option"
                  aria-selected={i === active}
                  className={`palette__item ${i === active ? "is-active" : ""}`}
                  onMouseMove={() => setActive(i)}
                  onClick={() => run(c)}
                >
                  {c.id === "ask" ? <IconChat size={15} /> : <IconArrowRight size={15} />}
                  <span>{c.label}</span>
                  {c.hint && <kbd>{c.hint}</kbd>}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
