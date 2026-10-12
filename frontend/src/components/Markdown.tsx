import { Fragment, type ReactNode, useMemo } from "react";
import { type Inline, parseMarkdown } from "../lib/markdown";

function renderInline(nodes: Inline[]): ReactNode {
  return nodes.map((n, i) => {
    switch (n.t) {
      case "text":
        return <Fragment key={i}>{n.v}</Fragment>;
      case "strong":
        return <strong key={i}>{renderInline(n.c)}</strong>;
      case "em":
        return <em key={i}>{renderInline(n.c)}</em>;
      case "code":
        return <code key={i}>{n.v}</code>;
      case "link":
        return (
          <a key={i} href={n.href} target={n.href.startsWith("http") ? "_blank" : undefined} rel="noreferrer">
            {renderInline(n.c)}
          </a>
        );
    }
  });
}

/** The analyst's markdown, rendered as React elements (no HTML injection). */
export function Markdown({ text }: { text: string }) {
  const blocks = useMemo(() => parseMarkdown(text), [text]);
  return (
    <div className="md">
      {blocks.map((b, i) => {
        switch (b.t) {
          case "h":
            return b.level <= 2 ? <h3 key={i}>{renderInline(b.c)}</h3> : <h4 key={i}>{renderInline(b.c)}</h4>;
          case "p":
            return <p key={i}>{renderInline(b.c)}</p>;
          case "ul":
          case "ol": {
            const List = b.t;
            return (
              <List key={i}>
                {b.items.map((it, j) => (
                  <li key={j}>{renderInline(it)}</li>
                ))}
              </List>
            );
          }
          case "table":
            return (
              <div key={i} className="md-table">
                <table>
                  <thead>
                    <tr>
                      {b.head.map((c, j) => (
                        <th key={j} style={{ textAlign: b.align[j] ?? undefined }}>
                          {renderInline(c)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {b.rows.map((r, j) => (
                      <tr key={j}>
                        {r.map((c, k) => (
                          <td key={k} style={{ textAlign: b.align[k] ?? undefined }}>
                            {renderInline(c)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          case "code":
            return (
              <pre key={i}>
                <code>{b.v}</code>
              </pre>
            );
          case "hr":
            return <hr key={i} />;
        }
      })}
    </div>
  );
}
