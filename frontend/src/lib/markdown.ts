/**
 * A small markdown parser for the analyst's answers: headings, paragraphs, lists, tables,
 * code, bold, italics, inline code and links. It builds a tree (never HTML strings), so
 * model output can't inject markup. Unfinished syntax while streaming degrades to text.
 */

export type Inline =
  | { t: "text"; v: string }
  | { t: "strong"; c: Inline[] }
  | { t: "em"; c: Inline[] }
  | { t: "code"; v: string }
  | { t: "link"; href: string; c: Inline[] };

export type Block =
  | { t: "h"; level: number; c: Inline[] }
  | { t: "p"; c: Inline[] }
  | { t: "ul" | "ol"; items: Inline[][] }
  | { t: "table"; head: Inline[][]; rows: Inline[][][]; align: ("left" | "right" | "center" | null)[] }
  | { t: "code"; v: string }
  | { t: "hr" };

const LIST = /^\s*([-*+]|\d+[.)])\s+(.*)$/;
const TABLE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

export function parseMarkdown(src: string): Block[] {
  const lines = src.replace(/\r\n?/g, "\n").split("\n");
  const out: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    if (line.trimStart().startsWith("```")) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trimStart().startsWith("```")) body.push(lines[i++]);
      i++;
      out.push({ t: "code", v: body.join("\n") });
      continue;
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) {
      out.push({ t: "h", level: h[1].length, c: parseInline(h[2].trim()) });
      i++;
      continue;
    }
    if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(line)) {
      out.push({ t: "hr" });
      i++;
      continue;
    }
    if (line.includes("|") && i + 1 < lines.length && TABLE_SEP.test(lines[i + 1])) {
      const head = cells(line);
      const align = cells(lines[i + 1]).map((c) => {
        const l = c.startsWith(":"), r = c.endsWith(":");
        return l && r ? "center" : r ? "right" : l ? "left" : null;
      });
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(cells(lines[i++]));
      out.push({
        t: "table",
        head: head.map(parseInline),
        rows: rows.map((r) => head.map((_, j) => parseInline(r[j] ?? ""))),
        align: head.map((_, j) => align[j] ?? null),
      });
      continue;
    }
    const li = LIST.exec(line);
    if (li) {
      const ordered = /\d/.test(li[1]);
      const items: string[] = [];
      while (i < lines.length) {
        const m = LIST.exec(lines[i]);
        if (m && /\d/.test(m[1]) === ordered) items.push(m[2]);
        else if (lines[i].trim() && /^\s{2,}/.test(lines[i]) && items.length) items[items.length - 1] += ` ${lines[i].trim()}`;
        else break;
        i++;
      }
      out.push({ t: ordered ? "ol" : "ul", items: items.map(parseInline) });
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !startsBlock(lines, i)) para.push(lines[i++].trim());
    out.push({ t: "p", c: parseInline(para.join(" ")) });
  }
  return out;
}

function startsBlock(lines: string[], i: number): boolean {
  const l = lines[i];
  return (
    /^#{1,6}\s/.test(l) || LIST.test(l) || l.trimStart().startsWith("```") ||
    (l.includes("|") && i + 1 < lines.length && TABLE_SEP.test(lines[i + 1]))
  );
}

function cells(line: string): string[] {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((c) => c.trim());
}

export function parseInline(src: string): Inline[] {
  const out: Inline[] = [];
  let text = "";
  const flush = () => {
    if (text) out.push({ t: "text", v: text });
    text = "";
  };
  let i = 0;
  while (i < src.length) {
    const rest = src.slice(i);
    let m: RegExpExecArray | null;
    if ((m = /^`([^`]+)`/.exec(rest))) {
      flush();
      out.push({ t: "code", v: m[1] });
    } else if ((m = /^\*\*(.+?)\*\*/.exec(rest)) || (m = /^__(.+?)__/.exec(rest))) {
      flush();
      out.push({ t: "strong", c: parseInline(m[1]) });
    } else if ((m = /^\*(?!\s)(.+?)\*/.exec(rest)) || (m = /^_(?!\s)(.+?)_(?![a-z0-9])/i.exec(rest))) {
      // "_" only opens emphasis at a word boundary (snake_case stays text).
      if (rest[0] === "_" && /[a-z0-9]/i.test(src[i - 1] ?? "")) {
        text += rest[0];
        i++;
        continue;
      }
      flush();
      out.push({ t: "em", c: parseInline(m[1]) });
    } else if ((m = /^\[([^\]]+)\]\(([^)\s]+)\)/.exec(rest)) && /^(https?:\/\/|#|\/)/.test(m[2])) {
      flush();
      out.push({ t: "link", href: m[2], c: parseInline(m[1]) });
    } else {
      text += src[i];
      i++;
      continue;
    }
    i += m[0].length;
  }
  flush();
  return out;
}

/** Plain text of inline nodes (for copy-to-clipboard and accessible labels). */
export function inlineText(nodes: Inline[]): string {
  return nodes.map((n) => ("v" in n ? n.v : inlineText(n.c))).join("");
}
